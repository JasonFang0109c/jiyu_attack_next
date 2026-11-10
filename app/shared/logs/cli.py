"""命令行模式的运行日志。

命令行没有界面，排查问题时只能靠终端回滚，日志文件保留完整过程。写入阈值
与界面共用 :mod:`app.shared.logs.levels`：正常版本只记 ``WARNING`` 及以上，debug
版本从 ``DEBUG`` 起全量记录，运行时不可更改。文件与界面的 ``runtime.log``
分开，两者可以同时运行。

本模块只依赖标准库：``app/cli/`` 不允许引入 ``PySide6``。
"""

import inspect
import threading
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.shared.logs.levels import allows

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
DEFAULT_CATEGORY = "命令行"


class CliLog:
    """把日志按界面的文本格式追加到 ``cli.log``。

    复用文件句柄，每条记录写入后刷新文件缓冲，减少重复打开文件的开销。
    """

    def __init__(self, path=None, category=DEFAULT_CATEGORY):
        """创建日志对象。

        Args:
            path: 日志文件路径；None 表示只在内存里记录，不落盘。
            category: 未显式指定功能分类时使用的名称。
        """
        self._path = Path(path) if path is not None else None
        self._category = category
        self._handle = None
        self.storage_error = ""

    @property
    def path(self):
        """返回日志文件路径。"""
        return self._path

    @property
    def enabled(self):
        """返回是否配置了日志文件。"""
        return self._path is not None

    def close(self):
        """关闭写入句柄并释放文件占用。"""
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        with suppress(OSError):
            handle.close()

    def debug(self, message, category=None, details=""):
        """记录调试信息：参数、路径与中间结果。"""
        self.add("DEBUG", message, category, details)

    def info(self, message, category=None, details=""):
        """记录关键节点：任务开始、完成与结果。"""
        self.add("INFO", message, category, details)

    def warning(self, message, category=None, details=""):
        """记录可恢复的问题：参数不合法、目标未响应。"""
        self.add("WARNING", message, category, details)

    def error(self, message, category=None, details=""):
        """记录失败：任务异常结束。"""
        self.add("ERROR", message, category, details)

    def add(self, level, message, category=None, details="", skip=2):
        """写入一条记录。

        Args:
            level: ``DEBUG``、``INFO``、``WARNING`` 或 ``ERROR``。
            message: 日志正文，允许包含换行。
            category: 功能分类，默认使用构造时的分类。
            details: 附加上下文，按续行写在正文之后。
            skip: 计算调用位置时跳过的栈帧数。
        """
        level = str(level).upper()
        if level not in LEVELS:
            level = "DEBUG"
        if not allows(level):
            return
        category = str(category or self._category)
        logger_name, line_number = self._caller_location(skip + 1)
        text = self._format(
            level, category, str(message), str(details or ""), logger_name, line_number
        )
        self._append(text)

    def _format(self, level, category, message, details, logger_name, line_number):
        """按与界面日志相同的文本格式拼出一条记录。"""
        lines = message.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        text = "%s [%d] [%s] %-7s %s:%d - [%s] %s" % (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            threading.get_ident(),
            threading.current_thread().name,
            level,
            logger_name,
            line_number,
            category,
            lines[0],
        )
        continuation = ["    " + line for line in lines[1:]]
        if details:
            detail_lines = details.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            continuation.extend("    " + line for line in detail_lines)
        if continuation:
            text += "\n" + "\n".join(continuation)
        return text

    @staticmethod
    def _caller_location(skip):
        """沿调用栈上溯，返回“模块.函数”与行号，便于从日志定位代码。"""
        frame = inspect.currentframe()
        try:
            for _ in range(skip):
                if frame is None:
                    break
                frame = frame.f_back
            if frame is None:
                return "app.cli", 0
            module = frame.f_globals.get("__name__", "app.cli")
            return "%s.%s" % (module, frame.f_code.co_name), frame.f_lineno
        finally:
            del frame

    def _append(self, text):
        """追加一行记录；写失败只记录状态，不打断命令本身。"""
        if self._path is None:
            return
        try:
            handle = self._handle
            if handle is None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                handle = self._path.open("a", encoding="utf-8", newline="\n")
                self._handle = handle
            handle.write(text + "\n")
            handle.flush()
        except OSError as error:
            self.storage_error = "命令行日志保存失败：%s" % error
            self.close()


LOG = CliLog()


def configure(path=None, category=DEFAULT_CATEGORY):
    """配置全局日志对象，返回配置后的实例。

    Args:
        path: 日志文件路径；None 关闭落盘。
        category: 默认功能分类。

    Returns:
        CliLog: 全局日志对象。
    """
    LOG.close()
    LOG._path = Path(path) if path is not None else None
    LOG._category = category
    LOG.storage_error = ""
    return LOG


def close():
    """关闭全局日志对象的文件句柄。"""
    LOG.close()
