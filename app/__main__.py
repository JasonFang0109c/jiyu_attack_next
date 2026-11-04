"""统一入口：无参数启动图形界面，有参数运行命令行模式。"""

import locale
import sys
from contextlib import suppress
from multiprocessing import freeze_support


def _console_encoding():
    """取控制台当前输出代码页对应的编码名。"""
    import ctypes

    try:
        codepage = ctypes.windll.kernel32.GetConsoleOutputCP()
    except Exception:
        codepage = 0
    if codepage == 65001:
        return "utf-8"
    return "cp%d" % codepage if codepage else locale.getpreferredencoding(False)


def _stream_from_handle(handle):
    """把标准句柄包装成文本流，句柄不可写时返回 None。"""
    import ctypes
    import msvcrt
    import os

    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_WRONLY)
        # 控制台句柄按当前代码页输出，重定向到文件或管道时与系统命令提示符一致。
        file_type = ctypes.windll.kernel32.GetFileType(handle)
        encoding = (
            _console_encoding()
            if file_type == 2
            else locale.getpreferredencoding(False)
        )
        stream = os.fdopen(
            descriptor,
            "w",
            encoding=encoding,
            errors="replace",
            buffering=1,
        )
        stream.write("")
        stream.flush()
    except OSError:
        return None
    return stream


def _rebind_inherited_streams():
    """沿用调用方传入的标准句柄，返回是否接管了输出。

    窗口化子系统启动时标准流可能为空，但调用方（终端）通常仍会传入
    输出句柄：命令提示符传控制台句柄，Windows Terminal 传伪控制台管道。
    直接用它们输出既不会新建窗口，也能和终端保持同一套编码。
    """
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.GetStdHandle.restype = ctypes.c_void_p
    invalid = ctypes.c_void_p(-1).value
    rebound = False
    for std_id, name in ((-11, "stdout"), (-12, "stderr")):
        if getattr(sys, name) is not None:
            continue
        handle = kernel32.GetStdHandle(std_id)
        # 0 与 INVALID_HANDLE_VALUE 都表示没有可用的标准句柄。
        if not handle or handle == invalid:
            continue
        stream = _stream_from_handle(handle)
        if stream is None:
            continue
        setattr(sys, name, stream)
        rebound = True
    return rebound


def _rebind_console_streams():
    """挂上控制台后重新打开输出设备。"""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is not None:
            continue
        # 控制台可能已断开，重新打开失败时保持空流即可，不影响后续逻辑。
        with suppress(OSError):
            setattr(
                sys,
                name,
                # 输出流必须一直可用，不能交给 with 在退出时关闭。
                open(  # noqa: SIM115
                    "CONOUT$",
                    "w",
                    encoding=_console_encoding(),
                    errors="replace",
                    buffering=1,
                    closefd=False,
                ),
            )


def _silence_streams():
    """没有可用的控制台时丢弃输出，保证命令行不会因为空流而崩溃。"""
    import os

    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            # 空流要一直保留到进程结束，交给解释器关闭。
            stream = open(  # noqa: SIM115
                os.devnull, "w", encoding="utf-8", closefd=False
            )
            setattr(sys, name, stream)


def _show_cli_console():
    """把命令行模式的输出接回调用方的终端。

    打包产物是窗口化子系统，双击启动不会出现控制台窗口；带参数运行时
    标准流可能为空。这里只沿用调用方已有的句柄或挂到父进程的控制台，
    任何情况下都不新建控制台窗口。
    """
    if sys.platform != "win32":
        return
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.GetConsoleWindow.restype = ctypes.c_void_p
        # 先挂到父进程的控制台，让 Windows 自己处理编码与缓冲；已经挂在
        # 控制台上或挂不上去时（例如 Windows Terminal 的伪控制台），再沿用
        # 调用方传进来的句柄。
        if not kernel32.GetConsoleWindow() and kernel32.AttachConsole(-1):
            _rebind_console_streams()
        if sys.stdout is None or sys.stderr is None:
            _rebind_inherited_streams()
    except Exception:
        # 取不到终端时不能让命令本身失败：输出丢失比进程崩溃更容易排查。
        pass
    _silence_streams()


def main(argv=None):
    """按是否带参数分发到命令行或图形界面入口。

    Args:
        argv: 参数列表，None 表示从 ``sys.argv`` 读取。

    Returns:
        int: 对应入口返回的退出码。
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        if arguments[0] != "--firewall-helper":
            _show_cli_console()
        from app.cli.main import main as run_cli

        return run_cli(arguments)
    from app.gui.app import main as run_gui

    return run_gui()


if __name__ == "__main__":
    freeze_support()
    sys.exit(main())
