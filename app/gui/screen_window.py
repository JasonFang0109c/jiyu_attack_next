"""屏幕观看窗口：连上学生端拿桌面画面，并把键鼠事件送回去。

学生端把桌面切成 H.264 或 JPEG 记录推上来：JPEG 帧直接交给 Qt 显示，H.264
帧交给核心层的解码器解成位图再画。远控请求与输入发送都走核心层，窗口本身只
负责把鼠标键盘事件翻译成报文。
"""

import time
from contextlib import suppress
from threading import Event, Thread

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
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

# 每个按键同时给出「按下」和「抬起」两种动作，滚轮与移动单独处理。
MOUSE_ACTIONS = {
    Qt.MouseButton.LeftButton: ("leftdown", "leftup"),
    Qt.MouseButton.RightButton: ("rightdown", "rightup"),
    Qt.MouseButton.MiddleButton: ("middledown", "middleup"),
}

# 坐标要映射到 0..65535 的定点范围，这是学生端的坐标系。
COORDINATE_LIMIT = 65535


class ScreenView(QLabel):
    """画面区，同时把鼠标与键盘事件交给窗口转发。

    画面上可能留有黑边，点击坐标要先折算回画面实际占据的矩形再归一化，
    否则远端光标会整体偏移。
    """

    def __init__(self, window, parent=None):
        super().__init__("等待第一帧…", parent)
        self.window = window
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(640, 380)
        self.setStyleSheet("background:#101010;color:#c8c8c8;border-radius:8px;")
        # 键盘事件要靠焦点送进来，点一下画面就应该能接管键盘。
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def image_rect(self):
        """返回画面实际占据的矩形，没有画面时退回整个控件。"""
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return self.rect()
        area = self.rect()
        scaled = pixmap.size().scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRect(
            area.x() + (area.width() - scaled.width()) // 2,
            area.y() + (area.height() - scaled.height()) // 2,
            scaled.width(),
            scaled.height(),
        )

    def normalized(self, position):
        """把控件坐标折算成 0..65535 的远端坐标，落在黑边上返回 None。"""
        area = self.image_rect()
        if area.width() <= 0 or area.height() <= 0:
            return None
        x = position.x() - area.x()
        y = position.y() - area.y()
        if not (0 <= x < area.width() and 0 <= y < area.height()):
            return None
        scale_x = COORDINATE_LIMIT / max(1, area.width() - 1)
        scale_y = COORDINATE_LIMIT / max(1, area.height() - 1)
        return (
            min(COORDINATE_LIMIT, int(x * scale_x)),
            min(COORDINATE_LIMIT, int(y * scale_y)),
        )

    def mouseMoveEvent(self, event):
        point = self.normalized(event.position().toPoint())
        if point is not None:
            self.window.send_mouse("move", point[0], point[1])
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        actions = MOUSE_ACTIONS.get(event.button())
        point = self.normalized(event.position().toPoint())
        if actions is not None and point is not None:
            self.window.send_mouse(actions[0], point[0], point[1])
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        actions = MOUSE_ACTIONS.get(event.button())
        point = self.normalized(event.position().toPoint())
        if actions is not None and point is not None:
            self.window.send_mouse(actions[1], point[0], point[1])
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        point = self.normalized(event.position().toPoint())
        if point is not None:
            # 远端按滚轮增量解析，正数向上，单位沿用 Windows 的 120。
            self.window.send_mouse("wheel", point[0], point[1], event.angleDelta().y())
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        if not event.isAutoRepeat():
            self.window.send_key(event, key_up=False)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if not event.isAutoRepeat():
            self.window.send_key(event, key_up=True)
        super().keyReleaseEvent(event)


class ScreenWindow(QWidget):
    """独立窗口，持续显示一台学生的屏幕。

    Attributes:
        host: 学生地址。
        port: 学生端 UDP 端口。
        channel: 会话频道。
        session: 底层 :class:`app.core.screen.ScreenSession`。
        control: 远控通道，未接管时为 None。
    """

    statusChanged = Signal(str)

    def __init__(self, host, port=4705, channel=1, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.channel = channel
        self.session = None
        self.control = None
        self._last_image = None
        self._frames = 0
        # 位图缓冲区要一直被引用，QImage 不会复制传入的内存。
        self._buffer = None
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
            "画面来自学生端的桌面推送；JPEG 帧直接显示，H.264 帧解码后显示。"
            "接管后可以直接在画面上操作键鼠。",
            header,
        )
        header.body.addWidget(self.hint)
        self.status = BodyLabel("正在连接…", header)
        header.body.addWidget(self.status)
        layout.addWidget(header)

        self.view = ScreenView(self, self)
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
                on_frame=self.show_frame,
            )
            self.session.open()
        except OSError as error:
            self.statusChanged.emit("连接失败：%s" % error)
            return
        self._stop.clear()
        self._pump.start()
        self.statusChanged.emit("已连接，等待画面…")

    def take_control(self):
        """请求接管学生端键鼠，再次点击则解除。"""
        if self.control is not None:
            self.control.close()
            self.control = None
            self.control_button.setText("接管键鼠")
            self.statusChanged.emit("已解除接管")
            return
        try:
            self.control = remote_control(
                self.host, detect_local_ip(), mode=2, udp_port=self.port
            )
        except OSError as error:
            self.statusChanged.emit("远控请求失败：%s" % error)
            return
        self.control_button.setText("解除接管")
        self.view.setFocus(Qt.FocusReason.OtherFocusReason)
        self.statusChanged.emit(
            "已接管键鼠，可直接在画面上操作（输入端口 %d）" % self.control.port
        )

    def send_mouse(self, action, x, y, data=0):
        """把鼠标事件发给学生端，未接管时忽略。"""
        if self.control is None:
            return
        with suppress(OSError):
            self.control.mouse(action, x, y, data)

    def send_key(self, event, key_up):
        """把 Qt 键事件翻译成扫描码与虚拟键码后发出。"""
        if self.control is None:
            return
        # 扩展键（方向键、小键盘回车等）的标志位在 Qt 里挂在扫描码的高位。
        extended = bool(event.nativeScanCode() & 0x100)
        with suppress(OSError):
            self.control.key(
                event.nativeScanCode() & 0xFF,
                event.nativeVirtualKey(),
                key_up=key_up,
                extended=extended,
            )

    def _on_record(self, record):
        """收到一条桌面记录：JPEG 直接显示，H.264 等解码回调。"""
        self._frames += 1
        kind = record.get("kind")
        if kind == "jpeg" and record.get("payload"):
            self._last_image = record["payload"]
            self._show_image()
            return
        if kind == "h264":
            self.statusChanged.emit("已收到第 %d 条记录（H.264）" % self._frames)

    def show_frame(self, width, height, pixels):
        """把解码得到的 RGB 位图画到画面上。"""
        self._buffer = pixels
        image = QImage(pixels, width, height, width * 3, QImage.Format.Format_RGB888)
        self.view.setPixmap(
            QPixmap.fromImage(image).scaled(
                self.view.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.statusChanged.emit("已收到 %d 条记录" % self._frames)

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
        if self.control is not None:
            self.control.close()
            self.control = None
        if self.session is not None:
            self.session.close()
            self.session = None
        with suppress(OSError):
            stop_screen(self.host, self.channel)
        super().closeEvent(event)
