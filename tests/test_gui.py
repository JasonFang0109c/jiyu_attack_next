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
from qfluentwidgets import FluentWindow, Theme, qconfig

from app.gui import app as gui


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        gui.configure_application(cls.application)

    def setUp(self):
        gui.setTheme(Theme.LIGHT)
        guard = patch.object(socket, "socket", side_effect=AssertionError("禁止真实网络通信"))
        guard.start()
        self.addCleanup(guard.stop)
        self.window = gui.MainWindow()
        self.message = self.window.pages["message"]
        self.command = self.window.pages["command"]
        self.device = self.window.pages["device"]
        self.state = self.window.connection_state
        notify = patch.object(self.window, "_notify")
        self.notify = notify.start()
        self.addCleanup(notify.stop)
        confirm = patch.object(self.window, "_confirm", return_value=True)
        self.confirm = confirm.start()
        self.addCleanup(confirm.stop)
        self.addCleanup(self.dispose_window)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), "界面任务未在预期时间内结束")

    def dispose_window(self):
        self.window.close()
        if self.window.thread is not None:
            self.wait_for(lambda: self.window.thread is None and not self.window.isVisible())
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.application.processEvents()

    def test_fluent_window_has_seven_function_pages(self):
        self.assertIsInstance(self.window, FluentWindow)
        self.assertEqual(self.window.windowTitle(), gui.APP_NAME)
        self.assertFalse(self.window.windowIcon().isNull())
        self.assertEqual(self.window.stackedWidget.count(), 7)
        self.assertEqual(self.window.current_page(), "message")
        self.assertEqual(self.state.values["target"], "")
        self.assertEqual(self.state.values["port"], 4705)
        self.assertIn("0 / 163", self.command.statistics.text())

    def test_sidebar_routes_preserve_drafts(self):
        self.message.editor.setPlainText("测试通知")
        self.command.editor.setPlainText("whoami")
        for key in self.window.pages:
            self.window.show_page(key)
            self.assertEqual(self.window.current_page(), key)
        self.assertEqual(self.message.editor.toPlainText(), "测试通知")
        self.assertEqual(self.command.editor.toPlainText(), "whoami")

    def test_connection_fields_are_shared_between_pages(self):
        self.command.targets.target_input.setText("模拟目标")
        self.message.targets.port_input.setValue(8800)
        self.device.targets.loop_input.setValue(3)
        self.command.targets.interval_input.setValue(0.5)
        for page in self.window.network_pages:
            self.assertEqual(page.targets.target_input.text(), "模拟目标")
            self.assertEqual(page.targets.port_input.value(), 8800)
            self.assertEqual(page.targets.loop_input.value(), 3)
            self.assertEqual(page.targets.interval_input.value(), 0.5)
            self.assertTrue(page.targets.interval_input.isEnabled())

    def test_interval_is_disabled_for_single_round(self):
        self.assertFalse(self.message.targets.interval_input.isEnabled())
        self.state.set_value("loops", 2)
        self.assertTrue(self.message.targets.interval_input.isEnabled())
        self.state.set_value("loops", 1)
        self.assertFalse(self.message.targets.interval_input.isEnabled())

    def test_message_and_command_statistics(self):
        self.message.editor.setPlainText("a" * 449)
        self.assertIn("2 条报文", self.message.statistics.text())
        self.command.editor.setPlainText("中文")
        self.assertIn("2 / 163", self.command.statistics.text())

    def test_each_page_only_sends_its_own_payload(self):
        self.message.editor.setPlainText("通知")
        self.command.editor.setPlainText("whoami")
        self.device.shutdown.setChecked(True)
        message = self.window._options_for_page("message")
        command = self.window._options_for_page("command")
        device = self.window._options_for_page("device")
        self.assertEqual((message.message, message.command, message.extra), ("通知", "", ""))
        self.assertEqual((command.message, command.command, command.extra), ("", "whoami", ""))
        self.assertEqual((device.message, device.command, device.extra), ("", "", "s"))
        self.assertFalse(self.device.reboot.isChecked())

    def test_target_preview_is_local_parsing_only(self):
        with patch.object(gui.core, "get_ip", return_value=["模拟目标甲", "模拟目标乙"]):
            self.state.set_value("target", "模拟范围")
        self.assertEqual(self.device.preview.rowCount(), 2)
        self.assertEqual(self.device.preview.item(1, 0).text(), "模拟目标乙")
        self.assertEqual(self.device.preview.item(1, 1).text(), "4705")

    def test_footer_and_numeric_text_fit_at_minimum_size(self):
        self.window.resize(960, 640)
        self.window.show()
        self.application.processEvents()
        for page in self.window.task_pages:
            self.window.show_page(page.objectName())
            self.application.processEvents()
            for button in [page.footer.send_button, page.footer.cancel_button]:
                if button.isHidden():
                    continue
                point = button.mapTo(self.window, button.rect().center())
                self.assertTrue(self.window.rect().contains(point))
        self.window.show_page("message")
        self.application.processEvents()
        for spin in [self.message.targets.port_input, self.message.targets.loop_input,
                     self.message.targets.interval_input]:
            self.assertGreater(spin.lineEdit().width(), 30)
        self.message.targets.port_input.setValue(65535)
        self.message.targets.loop_input.setValue(10000)
        self.application.processEvents()
        self.assertGreater(self.message.targets.port_input.lineEdit().width(), 30)
        self.assertEqual(self.message.targets.port_input.lineEdit().text(), "65535")

    def test_invalid_target_does_not_start_worker(self):
        self.message.footer.send_button.click()
        self.assertIsNone(self.window.thread)
        self.assertTrue(self.message.targets.target_input.isError())
        self.assertIn("目标地址", self.message.footer.status.text())

    def test_oversized_command_is_rejected_before_worker(self):
        self.state.set_value("target", "模拟目标")
        self.command.editor.setPlainText("a" * 164)
        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            self.window.start_send("command")
        self.assertIsNone(self.window.thread)
        self.assertIn("超过报文容量", self.command.footer.status.text())

    def test_worker_completes_and_reenables_controls(self):
        self.state.set_value("target", "模拟目标")
        self.message.editor.setPlainText("测试通知")

        def fake_send(options, report):
            report("模拟发送完成")
            return 2

        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            with patch.object(gui.core, "execute_send", side_effect=fake_send) as runner:
                self.message.footer.send_button.click()
                self.assertFalse(self.command.footer.send_button.isEnabled())
                self.wait_for(lambda: self.window.thread is None)
                runner.assert_called_once()
                self.assertEqual(runner.call_args.args[0].command, "")
        self.assertTrue(self.message.footer.send_button.isEnabled())
        self.assertFalse(self.message.footer.cancel_button.isEnabled())
        self.assertIn("已发送 2 个报文", self.message.footer.status.text())
        self.assertEqual(self.window.logs.entries[-1].level, "成功")

    def test_worker_failure_is_reported_and_logged(self):
        self.state.set_value("target", "模拟目标")
        self.command.editor.setPlainText("whoami")
        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            with patch.object(gui.core, "execute_send", side_effect=OSError("模拟错误")):
                self.window.start_send("command")
                self.wait_for(lambda: self.window.thread is None)
        self.assertIn("模拟错误", self.command.footer.status.text())
        self.assertEqual(self.window.logs.entries[-1].category, "远程命令")
        self.assertEqual(self.window.logs.entries[-1].level, "错误")
        self.assertTrue(self.command.footer.send_button.isEnabled())

    def test_device_action_can_be_cancelled_in_confirmation(self):
        self.state.set_value("target", "模拟目标")
        self.confirm.return_value = False
        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            self.window.start_send("device")
        self.assertIsNone(self.window.thread)
        self.confirm.assert_called_once()

    def test_local_query_uses_background_task(self):
        with patch.object(gui, "probe_local", return_value=("模拟本机", ["4705"])) as probe:
            self.window.start_local_probe()
            self.wait_for(lambda: self.window.thread is None)
        probe.assert_called_once()
        self.assertEqual(self.window.pages["local"].ip_label.text(), "模拟本机")
        self.assertEqual(self.window.pages["local"].port_table.rowCount(), 1)

    def test_firewall_result_preserves_failure_status(self):
        result = [("模拟规则", 1, "", "模拟失败")]
        with patch.object(gui, "apply_firewall", return_value=result) as apply:
            self.window.start_firewall()
            self.wait_for(lambda: self.window.thread is None)
        apply.assert_called_once()
        page = self.window.pages["firewall"]
        self.assertIn("失败", page.footer.status.text())
        self.assertEqual(page.result_table.item(0, 1).text(), "失败")

    def test_firewall_result_keeps_multiline_utf8_output_readable(self):
        page = self.window.pages["firewall"]
        page.set_result([
            {
                "command": "netsh advfirewall firewall set rule name=StudentMain.exe new action=block",
                "code": 0,
                "stdout": "已更新 6 规则。\n确定。",
                "stderr": "",
                "success": True,
                "detail": "",
            }
        ])
        self.assertEqual(page.result_table.item(0, 0).text(), "更新目标规则")
        self.assertEqual(page.result_table.item(0, 1).text(), "成功")
        self.assertEqual(page.result_table.item(0, 2).text(), "已更新 6 规则。\n确定。")
    def test_log_search_filter_export_and_clear(self):
        store = self.window.logs
        store.clear()
        store.add("文本消息", "第一条记录")
        store.add("远程命令", "第二条记录", "错误")
        page = self.window.pages["logs"]
        page.search.setText("第二条")
        self.assertTrue(page.table.isRowHidden(0))
        self.assertFalse(page.table.isRowHidden(1))
        self.assertEqual(len(page.export_text().splitlines()), 2)
        page.category.setCurrentIndex(2)
        self.assertTrue(page.table.isRowHidden(1))
        store.clear()
        self.assertEqual(page.table.rowCount(), 0)

    def test_settings_reset_preserves_drafts(self):
        self.message.editor.setPlainText("保留的草稿")
        self.state.set_value("port", 8800)
        self.window.pages["settings"].reset_button.click()
        self.assertEqual(self.state.values["port"], 4705)
        self.assertEqual(self.message.editor.toPlainText(), "保留的草稿")

    def test_reset_connection_parameters_can_be_undone(self):
        original = {"target": "模拟目标", "port": 8800, "loops": 2, "interval": 0.5}
        for name, value in original.items():
            self.state.set_value(name, value)
        self.window.pages["settings"].reset_button.click()
        self.assertEqual(self.state.values, self.state.DEFAULTS)
        self.assertTrue(self.window.pages["settings"].reset_undo.isVisibleTo(self.window.pages["settings"]))
        self.window.pages["settings"].reset_undo.click()
        self.assertEqual(self.state.values, original)
        self.assertFalse(self.window.pages["settings"].reset_undo.isVisibleTo(self.window.pages["settings"]))

    def test_theme_control_switches_to_dark(self):
        self.window.pages["settings"].theme_box.setCurrentIndex(1)
        self.assertEqual(qconfig.theme, Theme.DARK)

    def test_close_cancels_worker_before_destroying_window(self):
        self.window.show()
        self.state.set_value("target", "模拟目标")
        self.message.editor.setPlainText("测试通知")

        def cancellable_send(options, report):
            options.cancel_event.wait(2)
            raise RuntimeError("操作已取消")

        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            with patch.object(gui.core, "execute_send", side_effect=cancellable_send):
                self.window.start_send("message")
                self.window.close()
                self.wait_for(lambda: self.window.thread is None and not self.window.isVisible())
        self.assertTrue(self.window.close_after_task)
        self.assertEqual(self.window.logs.entries[-1].message, "操作已取消")


if __name__ == "__main__":
    unittest.main()
