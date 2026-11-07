"""屏幕观看窗口：连上学生端拿桌面画面，并把键鼠事件送回去。

学生端把桌面切成 H.264 或 JPEG 记录推上来：JPEG 帧直接交给 Qt 显示，H.264
帧交给核心层的解码器解成位图再画。远控请求与输入发送都走核心层，窗口本身只
负责把鼠标键盘事件翻译成报文。
"""

from contextlib import suppress
from threading import Event, Thread

from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal, Slot
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


class _ScreenSignals(QObject):
    ready = Signal(object, object)
    record = Signal(object, object)
    frame = Signal(object, int, int, object)
    log = Signal(object, str)
    finished = Signal(object, str)


class _ScreenConnection(Thread):
    """在同一后台线程内建立并清理会话，避免关闭与连接同时操作套接字。"""

    def __init__(self, host, channel, signals):
        super().__init__(name="screen-%s" % host, daemon=True)
        self.host = host
        self.channel = channel
        self.signals = signals
        self.cancelled = Event()
        self.session = None

    def _emit(self, signal, *args):
        if not self.cancelled.is_set():
            with suppress(RuntimeError):
                signal.emit(self, *args)

    def run(self):
        requested = False
        error_message = ""
        try:
            if self.cancelled.is_set():
                return
            requested = True
            start_screen(
                self.host,
                self.channel,
                report=lambda message: self._emit(self.signals.log, message),
            )
            if self.cancelled.wait(0.2):
                return
            self.session = ScreenSession(
                self.host,
                appcmd.TCP_COMM_PORT,
                appcmd.DESKTOP_CHANNEL,
                on_record=lambda record: self._emit(self.signals.record, record),
                on_log=lambda message: self._emit(self.signals.log, message),
                on_frame=lambda width, height, pixels: self._emit(
                    self.signals.frame, width, height, bytes(pixels)
                ),
            )
            self.session.open()
            self._emit(self.signals.ready, self.session)
            # 等待取消只负责安排清理，不循环占用线程，也不在 GUI 中等待网络。
            self.cancelled.wait()
        except (OSError, RuntimeError) as error:
            error_message = "连接失败：%s" % error
        finally:
            control = getattr(self, "control", None)
            if control is not None:
                with suppress(OSError):
                    control.close()
            if self.session is not None:
                with suppress(OSError, RuntimeError):
                    self.session.close()
            if requested:
                with suppress(OSError):
                    stop_screen(self.host, self.channel)
            with suppress(RuntimeError):
                self.signals.finished.emit(self, error_message)


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
    shutdownFinished = Signal()

    def __init__(self, host, port=4705, channel=1, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.host = host
        self.port = port
        self.channel = channel
        self.session = None
        self.control = None
        self._frames = 0
        self._closed = False
        self._connected = False
        self._has_frame = False
        self._control_requested = False
        self._connection = None
        self._pending_finish = None
        self._finish_timer = QTimer(self)
        self._finish_timer.setInterval(10)
        self._finish_timer.timeout.connect(self._finalize_connection)
        self._signals = _ScreenSignals(self)
        queued = Qt.ConnectionType.QueuedConnection
        self._signals.ready.connect(self._connection_ready, queued)
        self._signals.record.connect(self._on_record, queued)
        self._signals.frame.connect(self._render_frame, queued)
        self._signals.log.connect(self._connection_log, queued)
        self._signals.finished.connect(self._connection_finished, queued)

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
        """窗口显示时建立连接，关闭后再次显示会重新连接。"""
        super().showEvent(event)
        self._closed = False
        self.start()

    def start(self):
        """在后台请求画面并连接，连接失败后可再次调用重试。"""
        if self._closed or self._connection is not None:
            return
        self._connected = False
        self._has_frame = False
        self._frames = 0
        self.view.clear()
        self.view.setText("等待第一帧…")
        self.control_button.setEnabled(False)
        self.statusChanged.emit("正在连接…")
        connection = _ScreenConnection(self.host, self.channel, self._signals)
        self._connection = connection
        self.destroyed.connect(connection.cancelled.set)
        connection.start()

    def _active(self, connection):
        return (
            connection is self._connection
            and not self._closed
            and not connection.cancelled.is_set()
        )

    @Slot(object, object)
    def _connection_ready(self, connection, session):
        if not self._active(connection):
            return
        self.session = session
        self._connected = True
        if not self._has_frame:
            self.statusChanged.emit("已连接，等待画面…")
        self._apply_control_request()

    @Slot(object, str)
    def _connection_log(self, connection, message):
        if self._active(connection):
            self.statusChanged.emit(message)

    @Slot(object, str)
    def _connection_finished(self, connection, error_message):
        if connection is not self._connection:
            return
        self._pending_finish = (connection, error_message)
        self._finalize_connection()

    @Slot()
    def _finalize_connection(self):
        if self._pending_finish is None:
            return
        connection, error_message = self._pending_finish
        # queued 通知到达时，工作线程可能仍在 finished.emit 内部；
        # 等线程退出后再允许重连或删除窗口，保留信号对象的完整生命周期。
        if connection.is_alive():
            self._finish_timer.start()
            return
        self._finish_timer.stop()
        self._pending_finish = None
        self._connection = None
        with suppress(RuntimeError):
            self.destroyed.disconnect(connection.cancelled.set)
        self.session = None
        self._connected = False
        self.control_button.setEnabled(False)
        if self._closed:
            self.shutdownFinished.emit()
            return
        if connection.cancelled.is_set():
            self.start()
        elif error_message:
            self._control_requested = False
            self.statusChanged.emit(error_message)

    def request_control(self):
        """记住接管请求，等本轮连接与首帧就绪后执行；关窗会取消请求。"""
        if self._closed or self.control is not None:
            return
        self._control_requested = True
        self._apply_control_request()

    def _apply_control_request(self):
        ready = self._connected and self._has_frame and not self._closed
        self.control_button.setEnabled(ready)
        if ready and self._control_requested:
            self._control_requested = False
            self.take_control()

    def take_control(self):
        """请求接管学生端键鼠，再次点击则解除。"""
        if self._closed:
            return
        if self.control is not None:
            with suppress(OSError):
                self.control.close()
            self.control = None
            self.control_button.setText("接管键鼠")
            self.statusChanged.emit("已解除接管")
            return
        if not (self._connected and self._has_frame):
            self.request_control()
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

    @Slot(object, object)
    def _on_record(self, connection, record):
        """在 GUI 线程处理记录，忽略已经关闭的连接。"""
        if not self._active(connection):
            return
        self._frames += 1
        kind = record.get("kind")
        if kind == "jpeg" and record.get("payload"):
            pixmap = QPixmap()
            if pixmap.loadFromData(record["payload"]):
                self._present_pixmap(pixmap)
            else:
                self.statusChanged.emit("JPEG 帧无法解析")
        elif kind == "h264":
            self.statusChanged.emit("已收到第 %d 条记录（H.264）" % self._frames)

    @Slot(object, int, int, object)
    def _render_frame(self, connection, width, height, pixels):
        if self._active(connection):
            self.show_frame(width, height, pixels)

    def show_frame(self, width, height, pixels):
        """在 GUI 线程把解码得到的 RGB 位图画到画面上。"""
        if self._closed or width <= 0 or height <= 0:
            return
        if len(pixels) < width * height * 3:
            return
        image = QImage(pixels, width, height, width * 3, QImage.Format.Format_RGB888)
        self._present_pixmap(QPixmap.fromImage(image))

    def _present_pixmap(self, pixmap):
        if pixmap.isNull():
            return
        self.view.setPixmap(
            pixmap.scaled(
                self.view.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._has_frame = True
        self.statusChanged.emit("已收到 %d 条记录" % self._frames)
        self._apply_control_request()

    @property
    def is_shutdown_complete(self):
        """返回后台连接是否已经释放全部会话资源。"""
        return self._connection is None

    @property
    def shutdown_complete(self):
        """返回后台连接是否已经释放全部会话资源。"""
        return self.is_shutdown_complete

    def closeEvent(self, event):
        """立即取消当前显示，后台完成清理后发出 shutdownFinished。"""
        if self._closed:
            super().closeEvent(event)
            return
        self._closed = True
        self._connected = False
        self._has_frame = False
        self._control_requested = False
        self.control_button.setEnabled(False)
        self.control_button.setText("接管键鼠")
        connection = self._connection
        if connection is not None:
            connection.control = self.control
            self.control = None
            self.session = None
            connection.cancelled.set()
        else:
            if self.control is not None:
                with suppress(OSError):
                    self.control.close()
                self.control = None
            self.shutdownFinished.emit()
        super().closeEvent(event)
