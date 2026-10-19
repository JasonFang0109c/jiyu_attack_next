import os
import socket
import sys
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import gui


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        gui.configure_application(cls.app)

    def setUp(self):
        guard = patch.object(socket, "socket", side_effect=AssertionError("禁止真实网络通信"))
        guard.start()
        self.addCleanup(guard.stop)
        self.window = gui.MainWindow()
        self.addCleanup(self.dispose_window)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 4
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), "界面任务未在预期时间内结束")

    def dispose_window(self):
        self.window.close()
        if self.window.thread is not None:
            self.wait_for(lambda: self.window.thread is None)
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def test_main_window_constructs_without_network(self):
        self.assertEqual(self.window.windowTitle(), gui.APP_NAME)
        self.assertEqual(self.window.stack.count(), 2)
        self.assertTrue(self.window.send_button.isEnabled())
        self.assertEqual(self.window.port_input.value(), 4705)
        self.assertEqual(self.window.task_badge.text(), "空闲")
        self.assertEqual(self.window.target_input.text(), "")
        self.assertIn("0 / 163", self.window.command_stats.text())

    def test_message_and_command_statistics(self):
        self.window.message_edit.setPlainText("a" * 449)
        self.assertIn("2 条报文", self.window.message_stats.text())
        self.window.command_edit.setPlainText("中文")
        self.assertIn("2 / 163", self.window.command_stats.text())

    def test_device_actions_are_mutually_exclusive(self):
        self.window.message_edit.setPlainText("通知")
        self.window.command_edit.setPlainText("whoami")
        self.window.reboot_check.setChecked(True)
        self.assertEqual(self.window.message_edit.toPlainText(), "通知")
        self.assertEqual(self.window.command_edit.toPlainText(), "whoami")
        self.window.shutdown_check.setChecked(True)
        self.assertFalse(self.window.reboot_check.isChecked())
        self.assertTrue(self.window.shutdown_check.isChecked())

    def test_send_controls_remain_visible_at_minimum_size(self):
        self.window.resize(900, 620)
        self.window.show()
        self.app.processEvents()
        for button in [self.window.send_button, self.window.cancel_button]:
            center = button.mapTo(self.window, button.rect().center())
            self.assertTrue(self.window.rect().contains(center))
            self.assertTrue(button.isVisible())

    def test_invalid_target_does_not_start_worker(self):
        self.window._start_send()
        self.assertIsNone(self.window.thread)
        self.assertIn("目标地址", self.window.log_view.toPlainText())

    def test_worker_completes_and_reenables_controls(self):
        self.window.target_input.setText("模拟目标")
        self.window.message_edit.setPlainText("测试通知")

        def fake_send(options, report):
            report("模拟发送完成")
            return 2

        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            with patch.object(gui.core, "execute_send", side_effect=fake_send) as runner:
                self.window._start_send()
                self.assertFalse(self.window.send_button.isEnabled())
                self.wait_for(lambda: self.window.thread is None)
                runner.assert_called_once()
        self.assertTrue(self.window.send_button.isEnabled())
        self.assertFalse(self.window.cancel_button.isEnabled())
        self.assertIn("已发送 2 个报文", self.window.log_view.toPlainText())

    def test_worker_failure_is_reported(self):
        self.window.target_input.setText("模拟目标")
        self.window.message_edit.setPlainText("测试通知")
        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            with patch.object(gui.core, "execute_send", side_effect=OSError("模拟错误")):
                self.window._start_send()
                self.wait_for(lambda: self.window.thread is None)
        self.assertIn("模拟错误", self.window.log_view.toPlainText())
        self.assertTrue(self.window.send_button.isEnabled())

    def test_close_cancels_worker_before_destroying_window(self):
        self.window.show()
        self.window.target_input.setText("模拟目标")
        self.window.message_edit.setPlainText("测试通知")

        def cancellable_send(options, report):
            options.cancel_event.wait(2)
            raise RuntimeError("操作已取消")

        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            with patch.object(gui.core, "execute_send", side_effect=cancellable_send):
                self.window._start_send()
                self.window.close()
                self.wait_for(lambda: self.window.thread is None and not self.window.isVisible())
        self.assertTrue(self.window.close_after_task)
        self.assertIn("操作已取消", self.window.log_view.toPlainText())


if __name__ == "__main__":
    unittest.main()
