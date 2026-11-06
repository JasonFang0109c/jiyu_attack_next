"""屏幕观看窗口：连上学生端拿桌面画面，并把键鼠事件送回去。

学生端把桌面切成 H.264 或 JPEG 记录推上来，H.264 需要解码器才能显示，这里
只保证 JPEG 帧能直接看，H.264 帧先计数并提示需要外部解码器。远控请求与输入
发送都走核心层，窗口本身只负责把鼠标键盘事件翻译成报文。
"""

import time
from contextlib import suppress
from threading import Event, Thread

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, PushButton, TitleLabel
from qfluentwidgets import FluentIcon as FIF

from ..core import (
    ScreenSession,
    appcmd,
    detect_local_ip,
    remote_control,
    start_screen,
    stop_screen,
)
from .components import SectionCard


class ScreenWindow(QWidget):
    """独立窗口，持续显示一台学生的屏幕。

    Attributes:
        host: 学生地址。
        port: 学生端 UDP 端口。
        channel: 会话频道。
        session: 底层 :class:`app.core.screen.ScreenSession`。
    """

    statusChanged = Signal(str)

    def __init__(self, host, port=4705, channel=1, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.channel = channel
        self.session = None
        self.control_port = 0
        self._last_image = None
        self._frames = 0
        self._stop = Event()
        self._pump = Thread(target=self._pump_loop, daemon=True)

        self.setWindowTitle("观看 %s" % host)
        self.resize(960, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = SectionCard(self)
        header.body.addWidget(TitleLabel("屏幕观看 · %s" % host, header))
        self.hint = CaptionLabel(
            "画面来自学生端的桌面推送；H.264 帧需要外部解码器，JPEG 帧可直接显示。",
            header,
        )
        header.body.addWidget(self.hint)
        self.status = BodyLabel("正在连接…", header)
        header.body.addWidget(self.status)
        layout.addWidget(header)

        self.view = QLabel("等待第一帧…", self)
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.view.setMinimumSize(640, 380)
        self.view.setStyleSheet("background:#101010;color:#c8c8c8;border-radius:8px;")
        layout.addWidget(self.view, 1)

        buttons = QWidget(self)
        row = QVBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        self.control_button = PushButton(FIF.EDIT, "接管键鼠", buttons)
        self.stop_button = PushButton(FIF.CLOSE, "停止观看", buttons)
        row.addWidget(self.control_button)
        row.addWidget(self.stop_button)
        layout.addWidget(buttons)

        self.control_button.clicked.connect(self.take_control)
        self.stop_button.clicked.connect(self.close)
        self.statusChanged.connect(self.status.setText)

    def showEvent(self, event):
        """窗口首次显示时建立连接，避免构造期间就开线程。"""
        super().showEvent(event)
        if self.session is None:
            self.start()

    def start(self):
        """请求学生端推送画面并打开 TCP 会话。"""
        try:
            start_screen(self.host, self.channel, report=self.statusChanged.emit)
            time.sleep(0.2)
            self.session = ScreenSession(
                self.host,
                appcmd.TCP_COMM_PORT,
                appcmd.DESKTOP_CHANNEL,
                on_record=self._on_record,
                on_log=self.statusChanged.emit,
            )
            self.session.open()
        except OSError as error:
            self.statusChanged.emit("连接失败：%s" % error)
            return
        self._stop.clear()
        self._pump.start()
        self.statusChanged.emit("已连接，等待画面…")

    def take_control(self):
        """请求接管学生端键鼠，成功后按钮改为停止。"""
        if self.control_port:
            self.control_port = 0
            self.statusChanged.emit("已停止远控输入")
            return
        try:
            self.control_port = remote_control(
                self.host, detect_local_ip(), mode=2, udp_port=self.port
            )
        except OSError as error:
            self.statusChanged.emit("远控请求失败：%s" % error)
            return
        self.statusChanged.emit("已接管键鼠，输入端口 %d" % self.control_port)

    def _on_record(self, record):
        """收到一条桌面记录：JPEG 直接显示，其余只统计。"""
        self._frames += 1
        kind = record.get("kind")
        if kind == "jpeg" and record.get("payload"):
            self._last_image = record["payload"]
            self._show_image()
            return
        if kind == "h264":
            self.statusChanged.emit(
                "已收到第 %d 条记录（H.264 编码，需外部解码器）" % self._frames
            )

    def _show_image(self):
        """把最近一帧 JPEG 画到标签上。"""
        pixmap = QPixmap()
        if not pixmap.loadFromData(self._last_image):
            self.statusChanged.emit("JPEG 帧无法解析")
            return
        self.view.setPixmap(
            pixmap.scaled(
                self.view.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.statusChanged.emit("已收到 %d 条记录" % self._frames)

    def _pump_loop(self):
        """后台保持会话存活，直到窗口关闭。"""
        while not self._stop.is_set():
            time.sleep(0.2)

    def closeEvent(self, event):
        """关窗时断开连接并通知学生端停止推送。"""
        self._stop.set()
        if self.session is not None:
            self.session.close()
            self.session = None
        with suppress(OSError):
            stop_screen(self.host, self.channel)
        super().closeEvent(event)
