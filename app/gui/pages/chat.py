"""聊天消息页：走 MESS 会话通道给学生发可见的聊天内容。"""

from PySide6.QtWidgets import QHBoxLayout, QLineEdit
from qfluentwidgets import BodyLabel, PlainTextEdit

from ..components import ReadableSpinBox
from .common import NetworkPage


class ChatPage(NetworkPage):
    """向已登录教师会话的学生发一条聊天消息。

    与「文本消息」页不同：那条走的是弹窗式的消息模板，单向且不需要登录；
    这里的聊天消息走会话通道，学生回发的文本也能被会话收到。
    """

    def __init__(self, state, parent=None):
        super().__init__("chat", "聊天消息", state, "发送消息", parent)
        row = QHBoxLayout()
        row.addWidget(BodyLabel("会话频道", self.content_card))
        self.channel_input = ReadableSpinBox(self)
        self.channel_input.setRange(1, 32)
        self.channel_input.setValue(1)
        self.channel_input.setMinimumWidth(110)
        row.addWidget(self.channel_input)
        row.addSpacing(12)
        row.addWidget(BodyLabel("教师名", self.content_card))
        self.teacher_input = QLineEdit("1", self)
        self.teacher_input.setPlaceholderText("学生端上显示的教师名")
        self.teacher_input.setMaximumWidth(220)
        row.addWidget(self.teacher_input)
        row.addStretch()
        self.body.addLayout(row)

        hint = BodyLabel(
            "聊天消息要求学生端已登录本机模拟的教师会话，发送前会先补发一轮"
            "宣告并等待登录，所以目标没在线时会直接报错而不是静默丢弃。",
            self.content_card,
        )
        hint.setWordWrap(True)
        self.body.addWidget(hint)
        self.editor = PlainTextEdit(self.content_card)
        self.editor.setPlaceholderText("输入要发送的聊天内容")
        self.editor.setMinimumHeight(180)
        self.body.addWidget(self.editor, 1)

    def channel(self):
        """返回会话频道号。"""
        return self.channel_input.value()

    def teacher_name(self):
        """返回教师名，留空时用默认值。"""
        return self.teacher_input.text().strip() or "1"

    def message(self):
        """返回输入框里的聊天内容。

        Raises:
            ValueError: 内容为空。
        """
        text = self.editor.toPlainText()
        if not text.strip():
            raise ValueError("请填写聊天内容")
        return text
