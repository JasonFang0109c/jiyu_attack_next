"""屏幕画面页：拉取学生端缩略图、打开实时画面，并检查远端画面端口。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLineEdit
from qfluentwidgets import BodyLabel, PushButton
from qfluentwidgets import FluentIcon as FIF

from ..components import ReadableSpinBox, SectionCard, StatusFooter, page_heading
from .common import Page


class ScreenPage(Page):
    """按地址拉取缩略图或打开实时画面。

    学生列表在「学生信息」页里，这里改成直接填地址，方便只盯一台机器时
    反复刷新，不用每次都重新发现。
    """

    previewRequested = Signal()
    viewRequested = Signal()
    probeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("screen", parent)
        page_heading(self.vbox, "屏幕画面")
        self.vbox.addWidget(
            BodyLabel("教师端模拟：按地址拉取缩略图或打开实时画面。", self)
        )

        card = SectionCard(self)
        hint = BodyLabel(
            "缩略图由学生端按 LPNT 策略推上来，点一次等一帧；"
            "「观看画面」会另开窗口持续接收桌面画面。"
            "「检查端口」只探测学生端的 4806/TCP 是否可连，不发任何画面请求。",
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
        self.preview_button = PushButton(FIF.CAMERA, "刷新缩略图", card)
        self.preview_button.clicked.connect(self.previewRequested.emit)
        self.view_button = PushButton(FIF.VIDEO, "观看画面", card)
        self.view_button.clicked.connect(self.viewRequested.emit)
        self.probe_button = PushButton(FIF.WIFI, "检查端口", card)
        self.probe_button.clicked.connect(self.probeRequested.emit)
        button_row.addWidget(self.preview_button)
        button_row.addWidget(self.view_button)
        button_row.addWidget(self.probe_button)
        button_row.addStretch()
        card.body.addLayout(button_row)

        self.status = BodyLabel("等待操作", card)
        card.body.addWidget(self.status)
        # 主窗口按 footer 汇报任务进度，这一页没有底栏，转成状态行。
        self.footer = StatusFooter(self.set_status)

        # 缩略图整张交给 Qt 缩放，控件本身不缩放像素，避免失真。
        self.preview_label = BodyLabel("填好学生地址后点“刷新缩略图”拉取一次画面", card)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(240)
        self.preview_label.setScaledContents(False)
        card.body.addWidget(self.preview_label, 1)
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

    def set_preview(self, data):
        """显示缩略图字节，没有数据时回到提示文案。

        Args:
            data: JPEG 字节，或 ``None``。
        """
        if not data:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("暂无缩略图，点“刷新缩略图”重新拉取")
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("缩略图数据无法解析")
            return
        self.preview_label.setText("")
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
