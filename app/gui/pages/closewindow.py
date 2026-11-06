"""关闭窗口页：按窗口句柄关掉学生机上的某个应用窗口。"""

from PySide6.QtWidgets import QHBoxLayout, QLineEdit
from qfluentwidgets import BodyLabel

from ..components import ReadableSpinBox
from .common import NetworkPage


class CloseWindowPage(NetworkPage):
    """按句柄关闭窗口。

    走的是 MESS 的关闭请求：学生端对目标窗口发 ``WM_CLOSE``，进程本身还在，
    和「结束进程」是两回事。
    """

    def __init__(self, state, parent=None):
        super().__init__("closewindow", "关闭窗口", state, "关闭窗口", parent)
        row = QHBoxLayout()
        row.addWidget(BodyLabel("会话频道", self.content_card))
        self.channel_input = ReadableSpinBox(self)
        self.channel_input.setRange(1, 32)
        self.channel_input.setValue(1)
        self.channel_input.setMinimumWidth(110)
        row.addWidget(self.channel_input)
        row.addSpacing(12)
        row.addWidget(BodyLabel("窗口句柄", self.content_card))
        self.window_input = QLineEdit(self.content_card)
        self.window_input.setPlaceholderText(
            "十进制或 0x 开头的十六进制，例如 0x00120A3C"
        )
        row.addWidget(self.window_input, 1)
        self.body.addLayout(row)

        hint = BodyLabel(
            "窗口句柄可在「学生信息」页把详细信息切到“窗口”查看。"
            "关闭窗口只让目标程序收到关闭消息，进程不会被强制结束。",
            self.content_card,
        )
        hint.setWordWrap(True)
        self.body.addWidget(hint)
        # 多出来的高度交给末尾的空撑，否则提示文字会被拉成一大块。
        self.body.addStretch()

    def channel(self):
        """返回会话频道号。"""
        return self.channel_input.value()

    def window_handle(self):
        """返回解析后的窗口句柄。

        Raises:
            ValueError: 输入不是合法的整数。
        """
        text = self.window_input.text().strip()
        if not text:
            raise ValueError("请填写窗口句柄")
        try:
            handle = int(text, 0)
        except ValueError as error:
            raise ValueError("窗口句柄必须是十进制或 0x 开头的十六进制整数") from error
        if handle <= 0:
            raise ValueError("窗口句柄必须大于 0")
        return handle
