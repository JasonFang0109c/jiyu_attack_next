"""图形界面的后台任务。"""

import time
import traceback

from PySide6.QtCore import QThread, Signal


class _LoggingWorker(QThread):
    """后台线程公共部分：进度、结果、失败信号与可选日志通道。

    Attributes:
        logs: 运行日志存储；为空时不写日志，便于测试单独构造线程。
        category: 写日志时使用的功能分类。
    """

    progress = Signal(str)
    completed = Signal(object)
    failed = Signal(str, str)

    def __init__(self, logs=None, category="应用"):
        super().__init__()
        self.logs = logs
        self.category = category

    def _log(self, level, message, details=""):
        """写线程内日志；没有日志存储时跳过，避免后台线程强依赖界面对象。"""
        if self.logs is None:
            return
        getattr(self.logs, level)(self.category, message, details)


class SendWorker(_LoggingWorker):
    """在后台线程执行报文发送，通过信号回报进度与结果。

    Attributes:
        options: 发送参数，取消时由主窗口置位其中的 cancel_event。
        runner: 实际执行发送的函数，默认是 ``core.execute_send_report``。
    """

    def __init__(self, options, runner, logs=None, category="应用"):
        super().__init__(logs=logs, category=category)
        self.options = options
        self.runner = runner

    def run(self):
        """执行发送；失败时把消息与堆栈一起交给界面。"""
        started = time.monotonic()
        self._log(
            "debug",
            "发送线程开始执行",
            "目标：%s；端口：%s；轮数：%s；消息长度：%d；命令长度：%d"
            % (
                getattr(self.options, "target", ""),
                getattr(self.options, "port", ""),
                getattr(self.options, "loops", ""),
                len(getattr(self.options, "message", "") or ""),
                len(getattr(self.options, "command", "") or ""),
            ),
        )
        try:
            outcome = self.runner(self.options, report=self.progress.emit)
        except RuntimeError as error:
            self._log(
                "debug",
                "发送线程因取消结束",
                "耗时：%.3f 秒；异常：%s" % (time.monotonic() - started, error),
            )
            self.failed.emit(str(error), traceback.format_exc())
        except Exception as error:
            self._log(
                "debug",
                "发送线程因异常结束",
                "耗时：%.3f 秒；异常类型：%s"
                % (time.monotonic() - started, type(error).__name__),
            )
            self.failed.emit("发送失败：%s" % error, traceback.format_exc())
        else:
            self._log(
                "debug",
                "发送线程执行完成",
                "耗时：%.3f 秒" % (time.monotonic() - started),
            )
            self.completed.emit(outcome)


class TaskWorker(_LoggingWorker):
    """在后台线程执行任意带 ``report`` 回调的函数。

    Attributes:
        function: 要执行的函数，调用时会自动注入 ``report`` 关键字参数。
        args: 位置参数。
        kwargs: 关键字参数。
    """

    def __init__(self, function, *args, logs=None, category="应用", **kwargs):
        super().__init__(logs=logs, category=category)
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """执行目标函数；异常统一转成 failed 信号。"""
        started = time.monotonic()
        self._log(
            "debug",
            "后台任务开始执行",
            "函数：%s" % getattr(self.function, "__name__", ""),
        )
        try:
            result = self.function(*self.args, report=self.progress.emit, **self.kwargs)
        except Exception as error:
            self._log(
                "debug",
                "后台任务因异常结束",
                "函数：%s；耗时：%.3f 秒；异常类型：%s"
                % (
                    getattr(self.function, "__name__", ""),
                    time.monotonic() - started,
                    type(error).__name__,
                ),
            )
            self.failed.emit(str(error), traceback.format_exc())
        else:
            self._log(
                "debug",
                "后台任务执行完成",
                "函数：%s；耗时：%.3f 秒"
                % (getattr(self.function, "__name__", ""), time.monotonic() - started),
            )
            self.completed.emit(result)
