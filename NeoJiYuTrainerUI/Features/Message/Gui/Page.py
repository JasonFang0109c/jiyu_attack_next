"""文本消息页：编辑消息正文并统计会被拆成几条报文。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy
from qfluentwidgets import BodyLabel, CaptionLabel, PlainTextEdit
from qfluentwidgets import FluentIcon as FIF

import NeoJiYuTrainer.Packets.Codec as packets_codec
from NeoJiYuTrainerUI.Gui.Widgets.Common import tool_button
from NeoJiYuTrainerUI.Gui.Widgets.Page import NetworkPage


class MessagePage(NetworkPage):
    """编辑消息正文，支持导入与保存 UTF-8 文本。"""

    def __init__(self, state, parent=None):
        super().__init__("message", "文本消息", state, "发送消息", parent)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(BodyLabel("消息正文", self.content_card))
        self.statistics = CaptionLabel("0 字符 | 0 条报文", self.content_card)
        row.addWidget(self.statistics)
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
        # 文件名只在导入或保存后出现，单独一行贴在右下角，平时不占地方。
        self.filename = CaptionLabel("", self.content_card)
        self.filename.setMaximumWidth(320)
        self.filename.setMinimumWidth(0)
        self.filename.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.filename.setAlignment(Qt.AlignRight)
        self.filename.hide()
        self.body.addWidget(self.filename)

    importRequested = Signal()
    saveRequested = Signal()

    def set_filename(self, text):
        """显示当前来源或保存位置，空文本时隐藏这一行。"""
        self.filename.setText(text)
        self.filename.setToolTip(text)
        self.filename.setVisible(bool(text))

    def _request_import(self):
        self.importRequested.emit()

    def _request_save(self):
        self.saveRequested.emit()

    def update_statistics(self):
        """按实际分片结果刷新字符数与报文条数。"""
        text = self.editor.toPlainText()
        try:
            count = sum(1 for _ in packets_codec.split_message(text))
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
