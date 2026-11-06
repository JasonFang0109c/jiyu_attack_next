"""远程接管页：打开某台学生的画面并直接进入键鼠接管状态。"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit
from qfluentwidgets import BodyLabel, PushButton
from qfluentwidgets import FluentIcon as FIF

from ..components import ReadableSpinBox, SectionCard, page_heading
from .common import Page


class ControlPage(Page):
    """选一台学生直接进入接管，不经过「学生信息」页。

    接管本身要绑在画面窗口上，所以这里只发请求，窗口由主窗口打开并自动
    切换到接管状态；关闭窗口就是解除接管。
    """

    controlRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("control", parent)
        page_heading(self.vbox, "远程接管")
        self.vbox.addWidget(
            BodyLabel("教师端模拟：打开画面并把键鼠输入转给该学生。", self)
        )

        card = SectionCard(self)
        hint = BodyLabel(
            "点“开始接管”会先请求学生端推送画面，连上后再申请远控通道。"
            "接管期间鼠标与键盘只在画面窗口里生效，关闭窗口即解除接管。"
            "学生端需要允许远程控制，否则只会收到画面、输入不会生效。",
            card,
        )
        # 长段落必须换行，否则一整行文字会把页面的最小宽度撑到屏幕之外。
        hint.setWordWrap(True)
        card.body.addWidget(hint)

        config_row = QHBoxLayout()
        config_row.addWidget(BodyLabel("学生地址", card))
        self.host_input = QLineEdit(card)
        self.host_input.setPlaceholderText("例如 10.1.1.5")
        self.host_input.setMinimumWidth(240)
        config_row.addWidget(self.host_input)
        config_row.addSpacing(12)
        config_row.addWidget(BodyLabel("频道", card))
        self.channel_input = ReadableSpinBox(card)
        self.channel_input.setRange(1, 32)
        self.channel_input.setValue(1)
        self.channel_input.setMinimumWidth(110)
        config_row.addWidget(self.channel_input)
        config_row.addStretch()
        card.body.addLayout(config_row)

        button_row = QHBoxLayout()
        self.control_button = PushButton(FIF.ZOOM, "开始接管", card)
        self.control_button.clicked.connect(self.controlRequested.emit)
        button_row.addWidget(self.control_button)
        button_row.addStretch()
        card.body.addLayout(button_row)

        self.status = BodyLabel("等待操作", card)
        card.body.addWidget(self.status)
        # 多出来的高度交给末尾的空撑，否则标签会被均匀拉高、内容散在整张卡上。
        card.body.addStretch()
        self.vbox.addWidget(card, 1)

    def host(self):
        """返回输入的学生地址。"""
        return self.host_input.text().strip()

    def channel(self):
        """返回当前频道号。"""
        return self.channel_input.value()

    def set_status(self, text):
        """更新状态行。"""
        self.status.setText(text)
