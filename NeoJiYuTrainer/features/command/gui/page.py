"""远程命令页：编辑命令正文并实时统计字符数。"""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import BodyLabel, CaptionLabel, PlainTextEdit
from qfluentwidgets import FluentIcon as FIF

from NeoJiYuTrainer.gui.widgets.common import tool_button
from NeoJiYuTrainer.gui.widgets.page import NetworkPage


class CommandPage(NetworkPage):
    """编辑远程命令，命令经本机托管脚本以 SYSTEM 计划任务执行。"""

    def __init__(self, state, parent=None):
        super().__init__("command", "远程命令", state, "发送命令", parent)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(BodyLabel("命令正文", self.content_card))
        self.statistics = CaptionLabel("", self.content_card)
        self.statistics.setToolTip(
            "命令正文不进报文：由本机临时 HTTP 托管的脚本注册以 SYSTEM 运行的"
            "一次性计划任务并立即触发，执行输出写到公共目录的 out.txt"
        )
        row.addWidget(self.statistics)
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
        self.update_statistics()

    def update_statistics(self):
        """刷新命令长度提示。

        命令正文随脚本下发，不占用命令通道，因此只显示字符数供参考。
        """
        self.statistics.setText("%d 个字符" % len(self.editor.toPlainText()))

    def set_busy(self, busy, cancellable=False, queueable=False):
        """在基类忙碌状态之外锁定编辑框与清空按钮，避免任务中改内容。"""
        super().set_busy(busy, cancellable, queueable)
        self.editor.setReadOnly(busy)
        self.clear_button.setEnabled(not busy)
