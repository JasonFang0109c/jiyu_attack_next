"""远程命令页：编辑命令正文并实时统计报文占用。"""

from .common import *


class CommandPage(NetworkPage):
    """编辑远程命令，超出报文容量时提示并阻止发送。"""

    def __init__(self, state, parent=None):
        super().__init__("command", "远程命令", state, "发送命令", parent)
        row = QHBoxLayout()
        row.addWidget(BodyLabel("命令正文", self.content_card))
        row.addStretch()
        self.clear_button = tool_button(
            FIF.DELETE, "清空命令", self.content_card, lambda: self.editor.clear()
        )
        row.addWidget(self.clear_button)
        self.body.addLayout(row)
        self.editor = PlainTextEdit(self)
        self.editor.setPlaceholderText("cmd.exe /c ...")
        self.editor.setFont(QFont("Consolas", 11))
        self.editor.textChanged.connect(self.update_statistics)
        self.body.addWidget(self.editor, 1)
        self.statistics = CaptionLabel("", self)
        self.body.addWidget(self.statistics)
        self.update_statistics()

    def update_statistics(self):
        """刷新已用容量提示，超出上限时文字转红。"""
        try:
            units = len(self.editor.toPlainText().encode("utf-16le")) // 2
        except UnicodeError:
            self.statistics.setText("文本编码无效")
            return
        limit = core.COMMAND_MAX_BYTES // 2
        self.statistics.setText("%d / %d 个 UTF-16 单元" % (units, limit))
        self.statistics.setStyleSheet("color: #c42b1c;" if units > limit else "")

    def set_busy(self, busy, cancellable=False, queueable=False):
        super().set_busy(busy, cancellable, queueable)
        self.editor.setReadOnly(busy)
        self.clear_button.setEnabled(not busy)
