"""屏幕窗口的离线线程、首帧接管与生命周期回归测试。"""

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QBuffer, QCoreApplication, QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.gui import app as gui
from app.gui import screen_window as screen


class StubScreenSession:
    """记录线程和回调，并允许测试暂停 TCP 连接。"""

    def __init__(self, *args, **kwargs):
        self.on_record = kwargs["on_record"]
        self.on_frame = kwargs["on_frame"]
        self.on_log = kwargs["on_log"]
        self.open_entered = threading.Event()
        self.open_gate = threading.Event()
        self.open_gate.set()
        self.closed = threading.Event()
        self.error = None
        self.frame_on_open = False
        self.open_thread = None
        self.close_thread = None

    def open(self):
        """模拟连接等待和连接完成前先收到首帧的情况。"""
        self.open_thread = threading.get_ident()
        self.open_entered.set()
        self.open_gate.wait(3)
        if self.error:
            raise self.error
        if self.frame_on_open:
            self.on_frame(2, 2, bytes([255, 0, 0] * 4))

    def close(self):
        """记录释放发生的线程。"""
        self.close_thread = threading.get_ident()
        self.closed.set()


class ScreenWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        gui.configure_application(cls.application)

    def setUp(self):
        self.sessions = []
        self.windows = []
        self.configure_session = lambda session: None
        self.main_thread = threading.get_ident()
        self.start_screen = self.start_patch("start_screen")
        self.stop_screen = self.start_patch("stop_screen")
        self.remote_control = self.start_patch("remote_control")
        self.remote_control.return_value.port = 55120
        self.start_patch("detect_local_ip", return_value="127.0.0.1")
        self.start_patch("ScreenSession", side_effect=self.make_session)
        network = patch("socket.socket", side_effect=AssertionError("真实网络已禁用"))
        network.start()
        self.addCleanup(network.stop)

    def start_patch(self, name, **kwargs):
        patcher = patch.object(screen, name, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def make_session(self, *args, **kwargs):
        session = StubScreenSession(*args, **kwargs)
        self.configure_session(session)
        self.sessions.append(session)
        return session

    def make_window(self):
        window = screen.ScreenWindow("127.0.0.1")
        self.windows.append(window)
        return window

    def wait_for(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.application.processEvents()
            QTest.qWait(5)
        self.application.processEvents()
        self.assertTrue(predicate(), "等待测试状态超时")

    def tearDown(self):
        for window in self.windows:
            window.close()
        for session in self.sessions:
            session.open_gate.set()
        for window in self.windows:
            self.wait_for(lambda current=window: current.shutdown_complete)
            window.deleteLater()
            QCoreApplication.sendPostedEvents(window, QEvent.Type.DeferredDelete)
        self.application.processEvents()

    @staticmethod
    def jpeg_record():
        image = QImage(2, 2, QImage.Format.Format_RGB32)
        image.fill(QColor("#ff0000"))
        buffer = QBuffer()
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        image.save(buffer, "JPEG")
        return {"kind": "jpeg", "payload": bytes(buffer.data())}

    def test_slow_connection_keeps_gui_responsive_and_close_is_async(self):
        self.configure_session = lambda session: session.open_gate.clear()
        window = self.make_window()
        finished = MagicMock()
        window.shutdownFinished.connect(finished)
        window.show()
        self.wait_for(
            lambda: bool(self.sessions) and self.sessions[0].open_entered.is_set()
        )
        session = self.sessions[0]
        self.assertNotEqual(session.open_thread, self.main_thread)
        timer_fired = []
        QTimer.singleShot(0, lambda: timer_fired.append(True))
        self.wait_for(lambda: bool(timer_fired))
        window.close()
        self.assertFalse(window.shutdown_complete)
        self.assertFalse(session.closed.is_set())
        session.open_gate.set()
        self.wait_for(lambda: window.shutdown_complete)
        self.assertTrue(session.closed.is_set())
        self.assertNotEqual(session.close_thread, self.main_thread)
        self.stop_screen.assert_called_once_with("127.0.0.1", 1)
        finished.assert_called_once_with()

    def test_receiver_callbacks_present_jpeg_and_rgb_on_gui_thread(self):
        window = self.make_window()
        window.show()
        self.wait_for(lambda: window.session is not None)
        session = self.sessions[0]
        render_threads = []
        present = window._present_pixmap
        with patch.object(
            window,
            "_present_pixmap",
            side_effect=lambda pixmap: (
                render_threads.append(threading.get_ident()),
                present(pixmap),
            ),
        ):
            producer = threading.Thread(
                target=lambda: (
                    session.on_record(self.jpeg_record()),
                    session.on_frame(2, 2, bytes([0, 255, 0] * 4)),
                )
            )
            producer.start()
            producer.join(1)
            self.assertTrue(window.view.pixmap().isNull())
            self.wait_for(lambda: len(render_threads) == 2)
        self.assertEqual(render_threads, [self.main_thread, self.main_thread])
        self.assertFalse(window.view.pixmap().isNull())

    def test_control_request_waits_for_connection_and_first_frame(self):
        self.configure_session = lambda session: setattr(session, "frame_on_open", True)
        window = self.make_window()
        window.request_control()
        self.remote_control.assert_not_called()
        window.show()
        self.wait_for(lambda: window.control is not None)
        self.remote_control.assert_called_once_with(
            "127.0.0.1", "127.0.0.1", mode=2, udp_port=4705
        )
        window.request_control()
        self.remote_control.assert_called_once()
        self.assertEqual(window.control_button.text(), "解除接管")
        control = window.control
        window.close()
        self.wait_for(lambda: window.shutdown_complete)
        control.close.assert_called_once()

    def test_close_cancels_pending_control_and_queued_old_callbacks(self):
        window = self.make_window()
        window.show()
        self.wait_for(lambda: window.session is not None)
        session = self.sessions[0]
        window.request_control()
        producer = threading.Thread(
            target=lambda: session.on_frame(2, 2, bytes([255, 0, 0] * 4))
        )
        producer.start()
        producer.join(1)
        window.close()
        window.take_control()
        window.request_control()
        self.wait_for(lambda: window.shutdown_complete)
        self.assertFalse(window._has_frame)
        self.assertTrue(window.view.pixmap().isNull())
        self.remote_control.assert_not_called()

    def test_reopen_drops_queued_callbacks_from_cancelled_connection(self):
        self.configure_session = lambda session: session.open_gate.clear()
        window = self.make_window()
        window.show()
        self.wait_for(
            lambda: bool(self.sessions) and self.sessions[0].open_entered.is_set()
        )
        first = self.sessions[0]
        old_connection = window._connection
        window.close()
        window.show()
        window.request_control()
        self.assertTrue(old_connection.cancelled.is_set())

        # 模拟旧连接在关闭前已排队的 ready/首帧通知；它们不能复活旧会话。
        window._signals.ready.emit(old_connection, first)
        window._signals.frame.emit(old_connection, 2, 2, bytes([255, 0, 0] * 4))
        self.application.processEvents()
        self.assertIsNone(window.session)
        self.assertFalse(window._has_frame)
        self.remote_control.assert_not_called()

        self.configure_session = lambda session: setattr(session, "frame_on_open", True)
        first.open_gate.set()
        self.wait_for(lambda: len(self.sessions) == 2 and window.control is not None)
        self.remote_control.assert_called_once()

    def test_reopen_waits_for_old_cleanup_then_uses_a_new_session(self):
        self.configure_session = lambda session: session.open_gate.clear()
        window = self.make_window()
        window.show()
        self.wait_for(
            lambda: bool(self.sessions) and self.sessions[0].open_entered.is_set()
        )
        first = self.sessions[0]
        window.close()
        self.configure_session = lambda session: None
        window.show()
        self.assertEqual(len(self.sessions), 1)
        first.open_gate.set()
        self.wait_for(
            lambda: len(self.sessions) == 2 and window.session is self.sessions[1]
        )
        self.assertTrue(first.closed.is_set())
        self.assertEqual(self.start_screen.call_count, 2)
        self.assertEqual(self.stop_screen.call_count, 1)
        first.on_record(self.jpeg_record())
        self.application.processEvents()
        self.assertFalse(window._has_frame)
        self.remote_control.assert_not_called()

    def test_failed_open_releases_session_and_can_retry(self):
        self.configure_session = lambda session: setattr(
            session, "error", OSError("offline")
        )
        window = self.make_window()
        window.show()
        self.wait_for(
            lambda: window.shutdown_complete and "offline" in window.status.text()
        )
        self.assertTrue(self.sessions[0].closed.is_set())
        self.stop_screen.assert_called_once()
        self.configure_session = lambda session: None
        window.start()
        self.wait_for(lambda: window.session is not None)
        self.assertEqual(len(self.sessions), 2)

    def test_invalid_jpeg_does_not_trigger_control(self):
        window = self.make_window()
        window.show()
        self.wait_for(lambda: window.session is not None)
        window.request_control()
        self.sessions[0].on_record({"kind": "jpeg", "payload": b"broken"})
        self.application.processEvents()
        self.assertFalse(window._has_frame)
        self.remote_control.assert_not_called()
        self.sessions[0].on_record(self.jpeg_record())
        self.wait_for(lambda: window.control is not None)

    def test_shutdown_waits_until_finished_emission_and_worker_return(self):
        window = self.make_window()
        window.show()
        self.wait_for(lambda: window.session is not None)
        connection = window._connection
        emitting = threading.Event()
        release = threading.Event()
        completed = []
        window.shutdownFinished.connect(lambda: completed.append(True))

        def hold_finished(*_args):
            emitting.set()
            release.wait(3)

        window._signals.finished.connect(
            hold_finished, Qt.ConnectionType.DirectConnection
        )
        try:
            window.close()
            self.wait_for(emitting.is_set)
            # GUI 已处理 queued finished，但同步发射仍在 worker 栈中。
            self.application.processEvents()
            self.assertTrue(connection.is_alive())
            self.assertIs(window._connection, connection)
            self.assertFalse(window.shutdown_complete)
            self.assertEqual(completed, [])
            release.set()
            self.wait_for(lambda: window.shutdown_complete)
            self.assertFalse(connection.is_alive())
            self.assertEqual(completed, [True])
        finally:
            release.set()

    def test_close_before_connection_delay_skips_session_creation(self):
        started = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        self.start_screen.side_effect = lambda *args, **kwargs: (
            started.set(),
            release.wait(3),
        )
        window = self.make_window()
        window.show()
        self.wait_for(started.is_set)
        window.close()
        release.set()
        self.wait_for(lambda: window.shutdown_complete)
        self.assertEqual(self.sessions, [])
        self.stop_screen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
