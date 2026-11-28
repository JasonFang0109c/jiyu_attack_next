"""崩溃报告：把未捕获异常与硬崩溃写进数据目录下的 ``Crash`` 文件夹。

对应上游 ``GenerateCrashInfo``：进程异常结束时留下可读的报告，下次启动
由界面提示上次未正常退出。硬崩溃（访问违例、栈溢出）走 ``faulthandler``，
只保留 Python 栈与线程信息，不生成 Windows 内存转储。
"""

from __future__ import annotations

import faulthandler
import sys
import tempfile
import threading
import traceback
from datetime import datetime
from pathlib import Path

DIRECTORY_NAME = "Crash"
PENDING_NAME = "Pending.txt"
FATAL_NAME = "Fatal.log"

_fatal_stream = None
_fatal_dir: Path | None = None
_install_dir: Path | None = None


def crash_dir(directory):
    """返回崩溃报告目录。

    Args:
        directory: 数据目录（通常是 ``Data``）。

    Returns:
        Path: ``Crash`` 子目录路径。
    """
    return Path(directory) / DIRECTORY_NAME


def _timestamp():
    """返回用于文件名的本地时间戳。"""
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]


def _thread_dump():
    """返回当前全部线程的 Python 栈。"""
    # faulthandler 直接写文件描述符，必须给真实文件而不是 StringIO。
    try:
        with tempfile.TemporaryFile("w+b") as stream:
            faulthandler.dump_traceback(file=stream, all_threads=True)
            stream.seek(0)
            return stream.read().decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def write_report(directory, title, details):
    """写入一份崩溃报告并留下待提示标记。

    Args:
        directory: 数据目录（通常是 ``Data``）。
        title: 报告首行标题。
        details: 报告正文，通常是栈信息。

    Returns:
        Path: 新报告文件路径。
    """
    target = crash_dir(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / ("CrashInfo-%s.txt" % _timestamp())
    text = "%s\n时间：%s\n\n%s" % (title, datetime.now().isoformat(" "), details)
    path.write_text(text, encoding="utf-8", errors="replace")
    (target / PENDING_NAME).write_text(str(path), encoding="utf-8")
    return path


def install(directory):
    """接管未捕获异常并为硬崩溃启用 ``faulthandler``。

    Args:
        directory: 数据目录（通常是 ``Data``）。

    Returns:
        Path: 崩溃报告目录。
    """
    global _fatal_stream, _fatal_dir, _install_dir
    target = crash_dir(directory)
    target.mkdir(parents=True, exist_ok=True)
    _install_dir = Path(directory)
    if _fatal_dir != target:
        # 句柄要跟着进程活到底，faulthandler 会在崩溃瞬间直接写它；
        # 数据目录变了（测试、迁移）就换一份新文件，旧句柄关闭。
        previous_stream = _fatal_stream
        _fatal_stream = open(  # noqa: SIM115
            target / FATAL_NAME, "a", encoding="utf-8", errors="replace"
        )
        _fatal_stream.write(
            "\n===== 进程启动 %s =====\n" % datetime.now().isoformat(" ")
        )
        _fatal_stream.flush()
        faulthandler.enable(file=_fatal_stream, all_threads=True)
        _fatal_dir = target
        if previous_stream is not None:
            try:
                previous_stream.close()
            except OSError:
                pass
    _patch_excepthook()
    _patch_thread_hook()
    _patch_unraisable_hook()
    return target


def _patch_excepthook():
    """在 ``sys.excepthook`` 链上追加崩溃报告。"""
    previous = sys.excepthook

    def handle(exception_type, exception, tb):
        try:
            details = "".join(traceback.format_exception(exception_type, exception, tb))
            write_report(Path(_install_dir), "未捕获异常", details + _thread_dump())
        finally:
            previous(exception_type, exception, tb)

    if getattr(previous, "_jiyu_crash_hook", False):
        return
    handle._jiyu_crash_hook = True
    sys.excepthook = handle


def _patch_thread_hook():
    """接管线程内的未捕获异常。"""

    def handle(args):
        details = "".join(
            traceback.format_exception(
                args.exc_type, args.exc_value, args.exc_traceback
            )
        )
        thread_name = getattr(args.thread, "name", "?")
        write_report(Path(_install_dir), "线程未捕获异常（%s）" % thread_name, details)

    threading.excepthook = handle


def _patch_unraisable_hook():
    """接管 ``__del__`` 等无法抛出位置的异常。"""

    def handle(args):
        details = "".join(
            traceback.format_exception(
                args.exc_type, args.exc_value, args.exc_traceback
            )
        )
        write_report(
            Path(_install_dir),
            "未raisable异常（%s）" % getattr(args.obj, "__qualname__", repr(args.obj)),
            details,
        )

    sys.unraisablehook = handle


def pending_report(directory):
    """返回上次异常退出留下的报告路径。

    Args:
        directory: 数据目录（通常是 ``Data``）。

    Returns:
        Path | None: 报告存在时返回路径，否则返回 None。
    """
    marker = crash_dir(directory) / PENDING_NAME
    try:
        text = marker.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return None
    if not text:
        return None
    path = Path(text)
    return path if path.is_file() else None


def clear_pending(directory):
    """清除待提示标记。

    Args:
        directory: 数据目录（通常是 ``Data``）。
    """
    try:
        (crash_dir(directory) / PENDING_NAME).unlink()
    except OSError:
        return


def summary(path):
    """返回报告标题与异常文本，用于界面提示。

    Args:
        path: 报告文件路径。

    Returns:
        str: 单行摘要。
    """
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    lines = [line.strip() for line in lines if line.strip()]
    title = lines[0] if lines else ""
    reason = ""
    for line in reversed(lines):
        if "Error" in line or "Exception" in line:
            reason = line
            break
    if not reason:
        for line in reversed(lines):
            if line.startswith(('File "', "File ", "Current thread", "Thread ")):
                continue
            reason = line
            break
    return "%s：%s" % (title, reason) if reason else title
