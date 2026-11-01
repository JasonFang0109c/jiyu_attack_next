"""文本消息页：编辑消息正文并统计会被拆成几条报文。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy
from qfluentwidgets import BodyLabel, CaptionLabel, FluentIcon as FIF, PlainTextEdit

from ... import core
from ..components import tool_button
from .common import NetworkPage


class MessagePage(NetworkPage):
    """编辑消息正文，支持导入与保存 UTF-8 文本。"""

    def __init__(self, state, parent=None):
        super().__init__("message", "文本消息", state, "发送消息", parent)
        row = QHBoxLayout()
        row.addWidget(BodyLabel("消息正文", self.content_card))
        row.addStretch()
        self.import_button = tool_button(
            FIF.FOLDER, "导入 UTF-8 文本", self.content_card, self._request_import
        )
        self.save_button = tool_button(
            FIF.SAVE, "保存消息正文", self.content_card, self._request_save
        )
        self.clear_button = tool_button(
            FIF.DELETE, "清空消息", self.content_card, lambda: self.editor.clear()
        )
        for button in [self.import_button, self.save_button, self.clear_button]:
            row.addWidget(button)
        self.body.addLayout(row)
        self.editor = PlainTextEdit(self)
        self.editor.setPlaceholderText("输入消息内容")
        self.editor.setMinimumHeight(120)
        self.editor.textChanged.connect(self.update_statistics)
        self.body.addWidget(self.editor, 1)
        foot = QHBoxLayout()
        self.statistics = CaptionLabel("0 字符 | 0 条报文", self)
        self.filename = CaptionLabel("", self)
        self.filename.setMaximumWidth(230)
        self.filename.setMinimumWidth(0)
        self.filename.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        foot.addWidget(self.statistics)
        foot.addStretch()
        foot.addWidget(self.filename, 1, Qt.AlignRight)
        self.body.addLayout(foot)

    importRequested = Signal()
    saveRequested = Signal()

    def _request_import(self):
        self.importRequested.emit()

    def _request_save(self):
        self.saveRequested.emit()

    def update_statistics(self):
        """按实际分片结果刷新字符数与报文条数。"""
        text = self.editor.toPlainText()
        try:
            count = sum(1 for _ in core.split_message(text))
            self.statistics.setText("%d 字符 | %d 条报文" % (len(text), count))
            self.statistics.setToolTip("")
        except (ValueError, UnicodeError) as error:
            self.statistics.setText("文本包含不可发送字符")
            self.statistics.setToolTip(str(error))

    def set_busy(self, busy, cancellable=False, queueable=False):
        """在基类忙碌状态之外锁定编辑框与改动正文的按钮。"""
        super().set_busy(busy, cancellable, queueable)
        self.editor.setReadOnly(busy)
        for button in [self.import_button, self.clear_button]:
            button.setEnabled(not busy)
