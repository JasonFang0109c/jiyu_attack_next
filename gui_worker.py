from PySide6.QtCore import QThread, Signal


class SendWorker(QThread):
    progress = Signal(str)
    completed = Signal(int)
    failed = Signal(str)

    def __init__(self, options, runner):
        super().__init__()
        self.options = options
        self.runner = runner

    def run(self):
        try:
            sent_count = self.runner(
                self.options, report=self.progress.emit)
        except RuntimeError as error:
            self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit("发送失败：%s" % error)
        else:
            self.completed.emit(sent_count)


class TaskWorker(QThread):
    progress = Signal(str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, function, *args):
        super().__init__()
        self.function = function
        self.args = args

    def run(self):
        try:
            result = self.function(
                *self.args, report=self.progress.emit)
        except Exception as error:
            self.failed.emit(str(error))
        else:
            self.completed.emit(result)
