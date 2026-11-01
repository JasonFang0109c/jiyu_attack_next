"""图形界面的后台任务。"""

import traceback

from PySide6.QtCore import QThread, Signal


class SendWorker(QThread):
    """在后台线程执行报文发送，通过信号回报进度与结果。

    Attributes:
        options: 发送参数，取消时由主窗口置位其中的 cancel_event。
        runner: 实际执行发送的函数，默认是 ``core.execute_send``。
    """

    progress = Signal(str)
    completed = Signal(int)
    failed = Signal(str, str)

    def __init__(self, options, runner):
        super().__init__()
        self.options = options
        self.runner = runner

    def run(self):
        """执行发送；失败时把消息与堆栈一起交给界面。"""
        try:
            sent_count = self.runner(self.options, report=self.progress.emit)
        except RuntimeError as error:
            self.failed.emit(str(error), traceback.format_exc())
        except Exception as error:
            self.failed.emit("发送失败：%s" % error, traceback.format_exc())
        else:
            self.completed.emit(sent_count)


class TaskWorker(QThread):
    """在后台线程执行任意带 ``report`` 回调的函数。

    Attributes:
        function: 要执行的函数，调用时会自动注入 ``report`` 关键字参数。
        args: 位置参数。
        kwargs: 关键字参数。
    """

    progress = Signal(str)
    completed = Signal(object)
    failed = Signal(str, str)

    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """执行目标函数；异常统一转成 failed 信号。"""
        try:
            result = self.function(*self.args, report=self.progress.emit, **self.kwargs)
        except Exception as error:
            self.failed.emit(str(error), traceback.format_exc())
        else:
            self.completed.emit(result)
