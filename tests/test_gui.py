import os
import json
import io
import shutil
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen")

from PySide6.QtCore import (QCoreApplication, QEvent, QPoint, QPointF, QSettings, Qt,
                            QTimer)
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QSystemTrayIcon, QWidget
from qfluentwidgets import BodyLabel, FluentWindow, Theme, ToolTip, qconfig

from app.gui import app as gui, pages as gui_pages
from app.gui import components, models


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
        # 用测试名而不是 id(self) 命名：CPython 会复用对象地址，id 命名会让
        # 不同测试共用同一临时目录，残留的 runtime.log 干扰后续断言。
        self.temp_root = (Path("build") / "jiyu-gui-test"
                          / self._testMethodName.replace("/", "_"))
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.temp_root, ignore_errors=True))
        self.data_dir = self.temp_root / "JiYuAttackNextData"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = str(self.data_dir / "settings.ini")
        self.alias_store = gui.DeviceAliasStore(settings=QSettings(self.settings_path, QSettings.IniFormat))
        self.window = gui.MainWindow(
            alias_store=self.alias_store, data_dir=self.data_dir, enable_tray=False)
        self.message = self.window.pages["message"]
        self.command = self.window.pages["command"]
        self.device = self.window.pages["device"]
        self.state = self.window.connection_state
        notify = patch.object(self.window, "_notify")
        self.notify = notify.start()
        self.addCleanup(notify.stop)
        confirm = patch.object(self.window, "_confirm", return_value=True)
        self.confirm_patcher = confirm
        self.confirm = confirm.start()
        self.addCleanup(confirm.stop)
        self.addCleanup(self.dispose_window)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), "界面任务未在预期时间内结束")

    def hover(self, widget, position):
        """投递进入与移动事件，模拟鼠标悬停。

        不依赖系统光标位置：QTest.mouseMove 在 Windows 上驱动真实光标，
        光标已在该位置时不产生移动事件；ToolTipFilter 也只在 Enter 事件
        上启动计时，仅发送移动事件不会触发提示。
        """
        self.leave(widget)
        QApplication.sendEvent(widget, QEvent(QEvent.Type.Enter))
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(position),
                            widget.mapToGlobal(QPointF(position)),
                            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget, event)
        QTest.qWait(30)

    def leave(self, widget):
        """投递离开事件，模拟鼠标移出控件。"""
        QApplication.sendEvent(widget, QEvent(QEvent.Type.Leave))
        QTest.qWait(30)

    def dispose_window(self):
        self.window.close()
        if self.window.thread is not None:
            self.wait_for(lambda: self.window.thread is None and not self.window.isVisible())
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.application.processEvents()

    def test_fluent_window_has_ten_function_pages(self):
        self.assertIsInstance(self.window, FluentWindow)
        self.assertEqual(self.window.windowTitle(), gui.APP_NAME)
        self.assertFalse(self.window.windowIcon().isNull())
        self.assertEqual(self.window.stackedWidget.count(), 10)
        self.assertEqual(self.window.current_page(), "message")
        self.assertEqual(self.state.values["target"], "")
        self.assertEqual(self.state.values["port"], 4705)
        self.assertEqual(self.window.logs.minimum_level, models.LogLevel.INFO)
        self.assertIn("0 / 163", self.command.statistics.text())

    def test_idle_status_is_hidden_and_about_page_has_project_info(self):
        self.assertFalse(self.message.footer.status.isVisible())
        self.assertEqual(self.message.footer.status.text(), "")
        about = self.window.pages["about"]
        self.assertEqual(about.objectName(), "about")
        links = [button.getUrl().toString() for button in about.findChildren(gui.HyperlinkButton)]
        self.assertIn("https://github.com/JasonFang0109c", links)
        self.assertIn("https://github.com/JasonFang0109c/jiyu_attack_next", links)
        self.assertIn("https://github.com/ht0Ruial/Jiyu_udp_attack", links)
        self.assertNotIn("https://github.com/JasonFang0109c", [
            button.text() for button in about.findChildren(gui.HyperlinkButton)
        ])
        self.assertIn("JasonFang0109c", [
            button.text() for button in about.findChildren(gui.HyperlinkButton)
        ])
        for key in ("author", "repository", "upstream"):
            self.assertEqual(about.cards[key].objectName(), "aboutInfoCard")
            self.assertEqual(about.cards[key].borderRadius, 12)
        self.assertEqual(about.cards["repository"].detail.text(),
                         "https://github.com/JasonFang0109c/jiyu_attack_next")
        hero = about.findChild(QWidget, "aboutHero")
        self.assertIsNotNone(hero)
        self.assertNotIsInstance(hero, components.SectionCard)
        self.assertFalse(hero.findChildren(components.SectionCard))
        self.assertEqual(about.build_time_value.text(), "源码运行")
        self.assertIn("构建时间", [label.text() for label in about.findChildren(BodyLabel)])
        self.assertEqual(about.build_time_value.objectName(), "aboutBuildTime")
        from app.gui import build_info
        self.assertEqual(about.version_value.text(), build_info.version_text())
        self.assertIn("版本", [label.text() for label in about.findChildren(BodyLabel)])
        self.assertEqual(about.version_value.objectName(), "aboutVersion")

    def test_build_time_comes_from_bundle_asset(self):
        from app.gui import build_info
        self.assertEqual(build_info.build_time_text(), "源码运行")
        time_file = self.temp_root / "bundle" / build_info.BUILD_TIME_FILE_NAME
        build_info.write_build_time(time_file)
        with patch.object(gui.sys, "_MEIPASS", str(time_file.parent), create=True):
            self.assertRegex(build_info.build_time_text(), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        with patch.object(gui.sys, "_MEIPASS", str(self.temp_root / "missing"), create=True):
            self.assertEqual(build_info.build_time_text(), "源码运行")

    def test_version_comes_from_bundle_asset(self):
        from app.gui import build_info
        from app import __version__
        self.assertEqual(build_info.version_text(), __version__)
        version_file = self.temp_root / "bundle" / build_info.VERSION_FILE_NAME
        build_info.write_version(version_file, "9.9.9")
        with patch.object(gui.sys, "_MEIPASS", str(version_file.parent), create=True):
            self.assertEqual(build_info.version_text(), "9.9.9")

    def test_every_page_uses_rounded_section_cards(self):
        for page in self.window.pages.values():
            cards = page.findChildren(components.SectionCard)
            self.assertGreaterEqual(len(cards), 1, page.objectName())
            self.assertTrue(all(card.borderRadius == 12 for card in cards))

    def test_title_bar_keeps_icon_and_title(self):
        self.assertFalse(self.window.titleBar.iconLabel.isHidden())
        self.assertFalse(self.window.titleBar.titleLabel.isHidden())
        self.assertEqual(self.window.titleBar.titleLabel.text(), gui.APP_NAME)
        self.assertFalse(hasattr(self.window, "global_status"))
        self.window.show()
        self.application.processEvents()
        menu = self.window.navigationInterface.panel.menuButton
        icon = self.window.titleBar.iconLabel
        menu_center = menu.mapTo(self.window, menu.rect().center()).y()
        icon_center = icon.mapTo(self.window, icon.rect().center()).y()
        self.assertLessEqual(abs(menu_center - icon_center), 1)
        gap = icon.mapTo(self.window, icon.rect().topLeft()).x() - menu.mapTo(self.window, menu.rect().topRight()).x()
        self.assertGreaterEqual(gap, 5)

    def test_sidebar_routes_preserve_drafts(self):
        self.message.editor.setPlainText("测试通知")
        self.command.editor.setPlainText("whoami")
        for key in self.window.pages:
            self.window.show_page(key)
            self.assertEqual(self.window.current_page(), key)
        self.assertEqual(self.message.editor.toPlainText(), "测试通知")
        self.assertEqual(self.command.editor.toPlainText(), "whoami")

    def test_device_alias_can_be_added_edited_used_and_removed(self):
        page = self.window.pages["aliases"]
        self.assertEqual(page.info_button.toolTip(),
                         "备注名可直接用作目标；支持 IPv4、末段范围和 /24，"
                         "修改后同步引用。")
        self.assertEqual(page.info_button.size().width(), 28)
        page.name_input.setText("教室 A")
        for edit, text in zip(page.address_input.segments, ("192", "168", "1", "10")):
            edit.setText(text)
        page.save_button.click()
        self.assertEqual(self.alias_store.match("教室 a"), ("教室 A", "192.168.1.10"))
        self.assertEqual(page.table.item(0, 1).text(), "192.168.1.10")

        page.table.setCurrentCell(0, 0)
        page.use_button.click()
        self.assertEqual(self.state.values["target"], "教室 A")
        self.assertEqual(self.state.resolve_target(), "192.168.1.10")
        self.assertIn("192.168.1.10", self.message.targets.alias_hint.text())

        page.edit_button.click()
        page.name_input.setText("一号机房")
        for edit, text in zip(page.address_input.segments, ("192", "168", "1", "11")):
            edit.setText(text)
        page.save_button.click()
        self.assertEqual(self.state.values["target"], "一号机房")
        self.assertEqual(self.alias_store.match("一号机房"), ("一号机房", "192.168.1.11"))
        self.assertEqual(self.message.targets.target_input.text(), "192.168.1.11")
        self.assertEqual([edit.text() for edit in self.message.targets.target_input.segments],
                         ["192", "168", "1", "11"])

        page.table.setCurrentCell(0, 0)
        with patch.object(gui.Dialog, "exec", return_value=1):
            page.delete_button.click()
        self.assertIsNone(self.alias_store.match("一号机房"))
        self.assertEqual(self.state.values["target"], "")

    def test_device_alias_supports_ranges_and_is_persisted(self):
        page = self.window.pages["aliases"]
        page.name_input.setText("机房范围")
        for edit, text in zip(page.address_input.segments, ("10", "0", "0", "1-10")):
            edit.setText(text)
        page.save_button.click()
        self.assertEqual(self.alias_store.match("机房范围"), ("机房范围", "10.0.0.1-10"))
        self.assertEqual(page.table.item(0, 1).text(), "10.0.0.1-10")

        reloaded = gui.DeviceAliasStore(settings=QSettings(self.settings_path, QSettings.IniFormat))
        self.assertEqual(reloaded.match("机房范围"), ("机房范围", "10.0.0.1-10"))
        self.state.set_value("target", "机房范围")
        options = self.window._options_for_page("message")
        self.assertEqual(options.target, "10.0.0.1-10")
        self.assertEqual(self.message.targets.target_count.text(), "10 个目标")

    def test_alias_address_advances_on_enter_and_enters_four_segments(self):
        page = self.window.pages["aliases"]
        self.window.show()
        self.window.show_page("aliases")
        self.application.processEvents()
        page.name_input.setFocus()
        page.name_input.setText("回车设备")
        QTest.keyClick(page.name_input, Qt.Key_Return)
        self.application.processEvents()
        self.assertTrue(page.address_input.segments[0].hasFocus())
        for index, text in enumerate(("10", "1", "2")):
            page.address_input.segments[index].setText(text)
            QTest.keyClick(page.address_input.segments[index], Qt.Key_Return)
            self.application.processEvents()
        self.assertTrue(page.address_input.segments[3].hasFocus())
        page.address_input.segments[3].setText("20")
        QTest.keyClick(page.address_input.segments[3], Qt.Key_Return)
        self.application.processEvents()
        self.assertEqual(self.alias_store.match("回车设备"), ("回车设备", "10.1.2.20"))

    def test_portable_paths_are_based_on_executable_directory(self):
        executable = Path(self.temp_root) / "portable" / "JiYuAttackNext.exe"
        data_dir = models.portable_data_dir(executable)
        self.assertEqual(data_dir, executable.parent.resolve() / models.DATA_DIRECTORY_NAME)
        self.assertEqual(models.portable_log_path(data_dir), data_dir / models.LOG_FILE_NAME)
        self.assertTrue(models.portable_settings(data_dir).fileName().endswith(models.SETTINGS_FILE_NAME))

    def test_runtime_logs_are_persisted_and_loaded(self):
        self.window.logs.clear()
        self.window.logs.add("应用", "第一行\n第二行", "成功")
        log_path = self.data_dir / models.LOG_FILE_NAME
        self.assertTrue(log_path.exists())
        text = log_path.read_text(encoding="utf-8")
        self.assertIn(" INFO    ", text)
        self.assertIn("[应用] 第一行", text)
        self.assertIn("    第二行", text)
        reloaded = models.LogStore(log_path=log_path)
        self.assertEqual(reloaded.entries[-1].message, "第一行\n第二行")
        self.assertEqual(reloaded.entries[-1].level, models.LogLevel.INFO)
        self.assertGreater(reloaded.entries[-1].line_number, 0)
        self.assertTrue(reloaded.entries[-1].logger_name.endswith(".GuiTests"))
        self.window.logs.clear()
        self.assertEqual(log_path.read_text(encoding="utf-8"), "")

    def test_target_has_four_ipv4_segments_and_manual_address_still_works(self):
        targets = self.message.targets
        self.assertEqual(targets.device_button.text(), "选择设备")
        self.assertEqual(targets.device_button.parentWidget(), targets)
        self.assertEqual(len(targets.target_input.segments), 4)
        for edit, text in zip(targets.target_input.segments, ("192", "168", "1", "20")):
            edit.setText(text)
        self.assertEqual(targets.target_input.text(), "192.168.1.20")
        self.assertEqual(self.state.values["target"], "192.168.1.20")
        self.assertEqual(targets.target_count.text(), "1 个目标")

    def test_ipv4_segments_advance_on_enter_and_accept_last_segment_forms(self):
        targets = self.message.targets
        segments = targets.target_input.segments
        self.window.show()
        self.window.show_page("message")
        self.application.processEvents()
        segments[0].setFocus()
        for edit, text in zip(segments[:3], ("10", "49", "151")):
            edit.setText(text)
            QTest.keyClick(edit, Qt.Key_Return)
            self.application.processEvents()
        self.assertTrue(segments[3].hasFocus())
        segments[3].setText("1-10")
        self.assertEqual(self.state.values["target"], "10.49.151.1-10")
        self.assertEqual(targets.target_count.text(), "10 个目标")
        segments[3].setText("0/24")
        self.assertEqual(self.state.values["target"], "10.49.151.0/24")
        self.assertEqual(targets.target_count.text(), "254 个目标")
        QTest.keyClick(segments[3], Qt.Key_Return)
        self.application.processEvents()
        self.assertTrue(targets.port_input.hasFocus())

    def test_device_picker_lists_aliases_and_selects_target(self):
        self.alias_store.add("教室 A", "192.168.1.10")
        self.alias_store.add("一号机房", "192.168.1.11")
        targets = self.message.targets
        dialog, selector = targets._create_device_dialog()
        try:
            self.assertEqual(selector.count(), 2)
            self.assertEqual(selector.itemData(0), "教室 A")
            self.assertEqual(selector.itemText(1), "一号机房  ·  192.168.1.11")
        finally:
            dialog.deleteLater()
        targets.state.set_value("target", "一号机房")
        self.assertEqual(targets.target_input.text(), "192.168.1.11")
        self.assertEqual([edit.text() for edit in targets.target_input.segments],
                         ["192", "168", "1", "11"])
        self.assertIn("192.168.1.11", targets.alias_hint.text())

    def test_device_picker_handles_no_aliases(self):
        targets = self.message.targets
        with patch.object(components.Dialog, "exec", return_value=1) as execute:
            targets.choose_device()
        execute.assert_called_once()
        self.assertEqual(self.state.values["target"], "")

    def test_connection_fields_are_shared_between_pages(self):
        self.command.targets.target_input.setText("10.0.0.8")
        self.message.targets.port_input.setValue(8800)
        self.device.targets.loop_input.setValue(3)
        self.command.targets.interval_input.setValue(0.5)
        for page in self.window.network_pages:
            self.assertEqual(page.targets.target_input.text(), "10.0.0.8")
            self.assertEqual([edit.text() for edit in page.targets.target_input.segments],
                             ["10", "0", "0", "8"])
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

    def test_target_and_device_picker_do_not_overlap_at_narrow_widths(self):
        self.window.show()
        self.window.show_page("message")
        for width in (1050, 960):
            self.window.resize(width, 640)
            QTest.qWait(300)
            self.application.processEvents()
            targets = self.message.targets
            self.assertLess(
                targets.target_input.geometry().right(),
                targets.device_button.geometry().left(),
                "窗口宽度 %d 时目标地址与选择设备按钮重叠" % width,
            )

    def test_invalid_target_does_not_start_worker(self):
        self.message.footer.send_button.click()
        self.assertIsNone(self.window.thread)
        self.assertTrue(self.message.targets.target_input.segments[-1].isError())
        self.assertIn("目标地址", self.message.footer.status.text())

    def test_oversized_command_is_rejected_before_worker(self):
        self.state.set_value("target", "模拟目标")
        self.command.editor.setPlainText("a" * 164)
        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            self.window.start_send("command")
        self.assertIsNone(self.window.thread)
        self.assertIn("超过报文容量", self.command.footer.status.text())

    def test_file_page_selects_file_and_starts_transfer(self):
        page = self.window.pages["file"]
        self.assertEqual(page.objectName(), "file")
        self.assertEqual(page.targets.loop_input.isVisibleTo(page), False)
        source = self.temp_root / "报告.txt"
        source.write_text("测试文件", encoding="utf-8")
        page.set_file(source, source.stat().st_size)
        self.state.set_value("target", "模拟目标")
        self.assertEqual(page.selected_items(), [(str(source.resolve()), "报告.txt")])

        def fake_transfer(target, port, path, listen_ip, timeout, cancel_event=None,
                          report=None, items=None):
            report("目标正在下载文件：50%")
            report("目标正在下载文件：100%")
            return {"name": "报告.txt", "size": 8, "target": target,
                    "listen_ip": listen_ip, "file_count": 1}

        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            with patch.object(gui.core, "transfer_file", side_effect=fake_transfer) as transfer:
                self.window.start_file_transfer()
                self.wait_for(lambda: self.window.thread is None)
        transfer.assert_called_once()
        self.assertEqual(transfer.call_args.kwargs["items"],
                         [(str(source.resolve()), "报告.txt")])
        self.assertEqual(page.progress.value(), 100)
        self.assertIn("文件已传送到目标桌面", page.footer.status.text())
        self.assertEqual(self.window.logs.entries[-1].category, "文件传送")
        self.assertEqual(self.window.logs.entries[-1].level, models.LogLevel.INFO)

    def test_file_transfer_confirmation_is_active_and_responsive(self):
        page = self.window.pages["file"]
        source = self.temp_root / "确认测试.txt"
        source.write_text("确认测试", encoding="utf-8")
        page.set_file(source, source.stat().st_size)
        self.state.set_value("target", "模拟目标")
        dialogs = []

        def click_dialog(button_name):
            modal = QApplication.activeModalWidget()
            dialog = modal or next(
                (widget for widget in self.window.findChildren(QDialog) if widget.isVisible()),
                None,
            )
            dialogs.append((dialog, modal is dialog))
            if dialog is not None:
                QTest.mouseClick(getattr(dialog, button_name), Qt.LeftButton)

        self.window.show()
        self.window.activateWindow()
        self.window.raise_()
        QTest.qWait(200)
        self.confirm_patcher.stop()
        try:
            with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
                with patch.object(gui.core, "transfer_file", return_value={
                        "name": source.name, "size": source.stat().st_size,
                        "target": "模拟目标", "listen_ip": "127.0.0.1",
                        "file_count": 1}) as transfer:
                    QTimer.singleShot(150, lambda: click_dialog("yesButton"))
                    self.window.start_file_transfer()
                    self.wait_for(lambda: self.window.thread is None)
            transfer.assert_called_once()
            with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
                with patch.object(gui.core, "transfer_file") as cancelled_transfer:
                    QTimer.singleShot(150, lambda: click_dialog("cancelButton"))
                    self.window.start_file_transfer()
                    self.assertIsNone(self.window.thread)
            cancelled_transfer.assert_not_called()
        finally:
            self.confirm_patcher.start()
        self.assertEqual(len(dialogs), 2)
        for dialog, active in dialogs:
            self.assertIsNotNone(dialog)
            self.assertTrue(active)
            self.assertEqual(dialog.yesButton.text(), "确认执行")
            self.assertEqual(dialog.cancelButton.text(), "取消")
        self.assertIn("文件已传送到目标桌面", page.footer.status.text())

    def test_file_page_shows_tree_with_checkboxes_and_select_all(self):
        page = self.window.pages["file"]
        folder = self.temp_root / "课件"
        (folder / "第二章").mkdir(parents=True)
        (folder / "说明.txt").write_text("说明", encoding="utf-8")
        (folder / "第二章" / "示例.docx").write_text("示例", encoding="utf-8")
        single = self.temp_root / "通知.txt"
        single.write_text("通知", encoding="utf-8")
        page.add_paths([folder, single])
        self.assertEqual(len(page.items), 3)
        self.assertEqual(page.tree.topLevelItemCount(), 2)
        self.assertEqual(page.selected_items(), [
            (str((folder / "第二章" / "示例.docx").resolve()), "课件/第二章/示例.docx"),
            (str((folder / "说明.txt").resolve()), "课件/说明.txt"),
            (str(single.resolve()), "通知.txt"),
        ])
        self.assertEqual(page.select_all_checkbox.checkState(), Qt.Checked)
        self.assertTrue(page.footer.send_button.isEnabled())
        self.assertTrue(page.delete_button.isEnabled())
        self.assertIn("3 个文件", page.count_label.text())
        self.assertEqual(page.tree.columnCount(), 3)
        self.assertEqual(gui_pages.FileTreeHeader.CHECKBOX_SIZE, 16)
        self.assertEqual(gui_pages.CompactHeaderCheckBox.INDICATOR_SIZE, 16)
        self.assertEqual(gui_pages.CompactTreeItemDelegate.CHECKBOX_SIZE, 16)
        self.assertEqual(page.tree.headerItem().text(0), "名称")
        self.assertEqual(page.select_all_checkbox.size().width(), 16)
        self.assertEqual(page.select_all_checkbox.size().height(), 16)
        self.assertEqual(page.select_all_checkbox.objectName(),
                         "fileTreeSelectAllCheckbox")
        self.assertIs(page.info_button.parent(), page)
        self.assertEqual(page.info_button.toolTip(),
                         "勾选项发送到目标桌面并保留文件夹结构；"
                         "目标需支持远程命令和 curl。")
        self.assertEqual(page.info_button.size().width(), 28)
        self.assertEqual(page.info_button.size().height(), 28)
        self.assertTrue(all(Qt.CheckState(item.data(0, Qt.CheckStateRole)) == Qt.Checked
                            and item.icon(0).isNull()
                            for item in page._file_items()))

        page.select_all_checkbox.click()
        self.assertEqual(page.selected_items(), [])
        self.assertFalse(page.footer.send_button.isEnabled())
        self.assertFalse(page.delete_button.isEnabled())
        self.assertEqual(page.delete_button.toolTip(), "删除选中文件")

        page.select_all_checkbox.click()
        self.assertEqual(len(page.selected_items()), 3)

        folder_item = page.tree.topLevelItem(0)
        self.assertEqual(folder_item.text(0), "课件")
        folder_item.setCheckState(0, Qt.Unchecked)
        self.assertEqual(page.selected_items(), [(str(single.resolve()), "通知.txt")])
        self.assertEqual(page.select_all_checkbox.checkState(), Qt.PartiallyChecked)
        self.assertIsNone(folder_item.data(0, Qt.CheckStateRole))
        self.assertFalse(folder_item.icon(0).isNull())
        folder_item.setCheckState(0, Qt.Checked)
        self.assertEqual(len(page.selected_items()), 3)
        self.assertEqual(page.select_all_checkbox.checkState(), Qt.Checked)

    def test_page_info_buttons_show_fluent_tooltip_on_hover(self):
        for key in ("file", "aliases"):
            self.window.show_page(key)
            self.window.show()
            QTest.qWait(80)
            button = self.window.pages[key].info_button
            self.hover(button, button.rect().center())
            QTest.qWait(400)
            visible_tips = [widget for widget in QApplication.topLevelWidgets()
                            if isinstance(widget, ToolTip) and widget.isVisible()]
            self.assertTrue(any(tip.text() == button.toolTip() for tip in visible_tips), key)
            self.leave(button)

    def test_file_tree_toggles_icon_and_checkbox_on_hover(self):
        page = self.window.pages["file"]
        path = self.temp_root / "hover.txt"
        path.write_text("hover", encoding="utf-8")
        folder = self.temp_root / "hover-folder"
        folder.mkdir()
        (folder / "nested.txt").write_text("nested", encoding="utf-8")
        page.add_paths([path, folder])
        item = next(item for item in page._file_items()
                    if item.data(0, Qt.UserRole)[1] == "hover.txt")
        item.setCheckState(0, Qt.Unchecked)
        self.assertIsNone(item.data(0, Qt.CheckStateRole))
        self.assertFalse(item.icon(0).isNull())

        folder_item = next(item for item in page._all_visible_items()
                           if item.data(0, Qt.UserRole) == ("dir", "hover-folder"))
        folder_item.setCheckState(0, Qt.Unchecked)
        self.assertIsNone(folder_item.data(0, Qt.CheckStateRole))
        self.assertFalse(folder_item.icon(0).isNull())

        self.window.show_page("file")
        self.window.show()
        QTest.qWait(200)
        rect = page.tree.visualItemRect(item)
        hover_pos = QPoint(rect.x() + 32, rect.center().y())
        self.hover(page.tree.viewport(), hover_pos)
        self.assertEqual(item.checkState(0), Qt.Unchecked)
        self.assertEqual(item.data(0, Qt.CheckStateRole), Qt.Unchecked.value)
        self.assertTrue(item.icon(0).isNull())

        checkbox_pos = QPoint(rect.x() + 32, rect.center().y())
        QTest.mouseClick(page.tree.viewport(), Qt.LeftButton, pos=checkbox_pos)
        QTest.qWait(150)
        self.assertEqual(item.checkState(0), Qt.Checked)
        self.leave(page.tree.viewport())
        self.assertEqual(item.data(0, Qt.CheckStateRole), Qt.Checked.value)
        self.assertTrue(item.icon(0).isNull())

        item.setCheckState(0, Qt.Unchecked)
        self.leave(page.tree.viewport())
        self.assertIsNone(item.data(0, Qt.CheckStateRole))
        self.assertFalse(item.icon(0).isNull())

        folder_rect = page.tree.visualItemRect(folder_item)
        folder_pos = QPoint(folder_rect.x() + 32, folder_rect.center().y())
        self.hover(page.tree.viewport(), folder_pos)
        self.assertEqual(folder_item.data(0, Qt.CheckStateRole), Qt.Unchecked.value)
        self.assertTrue(folder_item.icon(0).isNull())
        self.leave(page.tree.viewport())
        self.assertIsNone(folder_item.data(0, Qt.CheckStateRole))
        self.assertFalse(folder_item.icon(0).isNull())

        folder_item.setCheckState(0, Qt.Checked)
        self.leave(page.tree.viewport())
        self.assertEqual(folder_item.checkState(0), Qt.Checked)
        self.assertEqual(folder_item.data(0, Qt.CheckStateRole), Qt.Checked.value)
        self.assertTrue(folder_item.icon(0).isNull())

    def test_file_page_deletes_selected_tree_items_only(self):
        page = self.window.pages["file"]
        folder = self.temp_root / "素材"
        folder.mkdir()
        (folder / "a.bin").write_bytes(b"a")
        (folder / "b.bin").write_bytes(b"b")
        single = self.temp_root / "保留.txt"
        single.write_text("保留", encoding="utf-8")
        page.add_paths([folder, single])
        folder_item = page.tree.topLevelItem(0)
        folder_item.setCheckState(0, Qt.Unchecked)
        for index in range(page.tree.topLevelItemCount()):
            item = page.tree.topLevelItem(index)
            if item.text(0) == "保留.txt":
                item.setCheckState(0, Qt.Checked)
        removed = page.remove_selected()
        self.assertEqual([relative for _, relative, _ in removed], ["保留.txt"])
        self.assertEqual([relative for _, relative, _ in page.items],
                         ["素材/a.bin", "素材/b.bin"])
        self.assertTrue((single).exists())
        self.assertTrue(page.has_files())

        page.select_all_checkbox.click()
        removed = page.remove_selected()
        self.assertEqual(len(removed), 2)
        self.assertFalse(page.has_files())
        self.assertFalse(page.tree.isVisibleTo(page))
        self.assertFalse(page.footer.send_button.isEnabled())

    def test_file_transfer_sends_only_checked_files(self):
        page = self.window.pages["file"]
        folder = self.temp_root / "选中测试"
        folder.mkdir()
        (folder / "a.txt").write_text("a", encoding="utf-8")
        (folder / "b.txt").write_text("bb", encoding="utf-8")
        page.add_paths([folder])
        folder_item = page.tree.topLevelItem(0)
        for index in range(folder_item.childCount()):
            child = folder_item.child(index)
            child.setCheckState(0, Qt.Checked if child.text(0) == "b.txt" else Qt.Unchecked)
        self.state.set_value("target", "模拟目标")
        captured = {}

        def fake_transfer(target, port, path, listen_ip, timeout, cancel_event=None,
                          report=None, items=None):
            captured["items"] = items
            return {"name": "1 个文件", "size": 2, "target": target,
                    "listen_ip": listen_ip, "file_count": 1}

        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            with patch.object(gui.core, "transfer_file", side_effect=fake_transfer) as transfer:
                self.window.start_file_transfer()
                self.wait_for(lambda: self.window.thread is None)
        transfer.assert_called_once()
        self.assertEqual(captured["items"],
                         [(str((folder / "b.txt").resolve()), "选中测试/b.txt")])
        self.assertIn("1 个文件", page.footer.status.text())

    def test_file_transfer_requires_checked_tree_items(self):
        page = self.window.pages["file"]
        self.window.start_file_transfer()
        self.assertIsNone(self.window.thread)
        self.assertIn("请先选择要传送的文件", page.footer.status.text())
        source = self.temp_root / "未勾选.txt"
        source.write_text("未勾选", encoding="utf-8")
        page.set_file(source)
        page.select_all_checkbox.click()
        self.window.start_file_transfer()
        self.assertIsNone(self.window.thread)
        self.assertIn("请勾选要传送的文件或文件夹", page.footer.status.text())

    def test_file_page_requires_file_and_accepts_target_range(self):
        page = self.window.pages["file"]
        self.window.start_file_transfer()
        self.assertIsNone(self.window.thread)
        self.assertIn("请先选择要传送的文件", page.footer.status.text())
        source = self.temp_root / "报告.txt"
        source.write_text("测试文件", encoding="utf-8")
        page.set_file(source, source.stat().st_size)
        self.state.set_value("target", "192.168.1.1-2")

        requested = []

        def fake_transfer(target, port, path, listen_ip, timeout, cancel_event=None,
                          report=None, items=None):
            requested.append(target)
            report("目标 1/2（192.168.1.1）正在下载文件：100%")
            return {
                "name": source.name,
                "size": source.stat().st_size,
                "target": target,
                "targets": ["192.168.1.1", "192.168.1.2"],
                "transferred": ["192.168.1.1", "192.168.1.2"],
                "listen_ip": "127.0.0.1",
                "port": None,
                "file_count": 1,
            }

        with patch.object(gui.core, "transfer_file", side_effect=fake_transfer) as transfer:
            self.window.start_file_transfer()
            self.wait_for(lambda: self.window.thread is None)
        transfer.assert_called_once()
        self.assertEqual(requested, ["192.168.1.1-2"])
        self.assertIn("2 个目标桌面", page.footer.status.text())
        self.assertEqual(page.progress.value(), 100)
        self.assertEqual(self.window.logs.entries[-1].level, models.LogLevel.INFO)

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
        self.assertEqual(self.window.logs.entries[-1].level, models.LogLevel.INFO)

    def test_worker_failure_is_reported_and_logged(self):
        self.state.set_value("target", "模拟目标")
        self.command.editor.setPlainText("whoami")
        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            with patch.object(gui.core, "execute_send", side_effect=OSError("模拟错误")):
                self.window.start_send("command")
                self.wait_for(lambda: self.window.thread is None)
        self.assertIn("模拟错误", self.command.footer.status.text())
        self.assertEqual(self.window.logs.entries[-1].category, "远程命令")
        self.assertEqual(self.window.logs.entries[-1].level, models.LogLevel.ERROR)
        self.assertIn("OSError", self.window.logs.entries[-1].details)
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
        self.assertEqual(page.result_table.item(0, 0).text(), "目标规则")
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

    def test_log_page_controls_are_visible_at_minimum_size(self):
        self.window.resize(960, 640)
        self.window.show()
        QTest.qWait(120)
        page = self.window.pages["logs"]
        self.window.show_page("logs")
        QTest.qWait(120)
        for button in (page.select_all_checkbox, page.export_button,
                       page.delete_button, page.level_filter):
            self.assertTrue(button.isVisible(), button.objectName() or button.text())
        self.assertIs(page.select_all_checkbox.parentWidget(),
                      page.table.horizontalHeader().viewport())
        self.assertFalse(hasattr(page, "select_all_button"))
        self.assertFalse(hasattr(page, "runtime_level"))
        self.assertGreaterEqual(page.table.columnWidth(1), 180)
        self.assertGreaterEqual(page.table.columnWidth(2), 100)
        self.window.show_page("settings")
        QTest.qWait(120)
        settings = self.window.pages["settings"]
        self.assertTrue(settings.log_level_box.isVisible())
        hints = [label.text() for label in settings.findChildren(gui.CaptionLabel)]
        self.assertNotIn("选择本次运行写入的最低日志等级，低于该等级的记录不会出现在日志页和日志文件中。", hints)

    def test_uncaught_exception_is_written_to_runtime_log(self):
        previous_stderr = sys.stderr
        sys.stderr = io.StringIO()
        previous = gui.install_exception_logging(self.window.logs)
        try:
            try:
                raise RuntimeError("模拟未捕获异常")
            except RuntimeError:
                exception_type, exception, tb = sys.exc_info()
                gui.sys.excepthook(exception_type, exception, tb)
        finally:
            gui.sys.excepthook = previous
            sys.stderr = previous_stderr
        entry = self.window.logs.entries[-1]
        self.assertEqual(entry.level, models.LogLevel.ERROR)
        self.assertIn("模拟未捕获异常", entry.message)
        self.assertIn("RuntimeError", entry.details)

    def test_log_level_filter_selection_and_selected_export(self):
        store = self.window.logs
        store.clear()
        store.debug("应用", "调试记录")
        store.info("文本消息", "普通记录")
        store.warning("远程命令", "警告记录")
        store.error("设备操作", "错误记录")
        page = self.window.pages["logs"]
        self.assertEqual(page.table.rowCount(), 3)
        self.assertFalse(page.select_all_checkbox.isChecked())
        self.assertFalse(page.export_button.isEnabled())
        self.assertFalse(page.delete_button.isEnabled())
        self.assertEqual(page.export_button.toolTip(), "导出选中日志")
        self.assertEqual(page.delete_button.toolTip(), "删除选中日志")
        page.level_filter.setCurrentIndex(3)
        self.assertTrue(page.table.isRowHidden(0))
        self.assertFalse(page.table.isRowHidden(1))
        self.assertTrue(page.table.isRowHidden(2))
        page.level_filter.setCurrentIndex(0)
        page.search.clear()
        self.assertEqual(page.selected_uids(), [])
        page.select_all_checkbox.click()
        self.assertTrue(page.select_all_checkbox.isChecked())
        self.assertEqual(len(page.selected_entries()), 3)
        self.assertTrue(page.export_button.isEnabled())
        self.assertTrue(page.delete_button.isEnabled())
        page.table.item(2, 0).setCheckState(Qt.Unchecked)
        self.assertFalse(page.select_all_checkbox.isChecked())
        self.assertEqual(len(page.selected_entries()), 2)
        exported = page.export_text(page.selected_entries())
        self.assertIn("普通记录", exported)
        self.assertIn("警告记录", exported)
        self.assertNotIn("错误记录", exported)
        page.select_all_checkbox.click()
        self.assertTrue(page.select_all_checkbox.isChecked())
        page.select_all_checkbox.click()
        self.assertFalse(page.select_all_checkbox.isChecked())
        self.assertEqual(page.selected_uids(), [])
        self.assertFalse(page.export_button.isEnabled())
        self.assertFalse(page.delete_button.isEnabled())

    def test_select_all_off_clears_rows_hidden_by_filter(self):
        store = self.window.logs
        store.clear()
        store.info("文本消息", "消息记录")
        store.error("远程命令", "命令记录")
        page = self.window.pages["logs"]
        page.category.setCurrentIndex(2)
        page.select_all_checkbox.click()
        self.assertEqual(len(page.selected_entries()), 1)
        page.category.setCurrentIndex(0)
        page.select_all_checkbox.click()
        self.assertEqual(len(page.selected_entries()), 2)
        page.select_all_checkbox.click()
        self.assertEqual(page.selected_uids(), [])

    def test_runtime_log_level_filters_new_entries_and_syncs_page(self):
        store = self.window.logs
        store.clear()
        settings_page = self.window.pages["settings"]
        settings_page.log_level_box.setCurrentIndex(2)
        self.assertEqual(store.minimum_level, models.LogLevel.WARNING)
        self.assertIsNone(store.info("应用", "被过滤"))
        store.warning("应用", "保留警告")
        self.assertEqual(settings_page.log_level_box.currentText(), "WARNING")
        self.assertEqual(store.entries[-1].message, "保留警告")
        self.assertTrue(self.window.pages["logs"].table.rowCount() >= 1)

    def test_settings_log_level_syncs_when_store_changes(self):
        settings_page = self.window.pages["settings"]
        self.window.logs.set_level(models.LogLevel.DEBUG)
        self.assertEqual(settings_page.log_level_box.currentText(), "DEBUG")
        self.window.logs.set_level(models.LogLevel.INFO)

    def test_delete_selected_logs_removes_rows_and_rewrites_file(self):
        store = self.window.logs
        store.clear()
        first = store.info("应用", "保留记录")
        removed = store.error("应用", "删除记录")
        log_path = self.data_dir / models.LOG_FILE_NAME
        page = self.window.pages["logs"]
        row = page._row_by_uid[removed.uid]
        page.table.item(row, 0).setCheckState(Qt.Checked)
        self.window.delete_selected_logs([removed.uid])
        remaining_uids = [entry.uid for entry in store.entries]
        self.assertIn(first.uid, remaining_uids)
        self.assertNotIn(removed.uid, remaining_uids)
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("保留记录", text)
        self.assertNotIn("[应用] 删除记录", text)

    def test_legacy_json_log_is_loaded_and_migrated_on_next_write(self):
        log_path = self.data_dir / models.LOG_FILE_NAME
        legacy = {
            "time": "2026-01-02 03:04:05",
            "category": "应用",
            "level": "警告",
            "message": "旧格式记录",
        }
        log_path.write_text(json.dumps(legacy, ensure_ascii=False) + "\n", encoding="utf-8")
        store = models.LogStore(log_path=log_path)
        self.assertEqual(store.entries[0].level, models.LogLevel.WARNING)
        store.info("应用", "新格式记录")
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("WARNING", text)
        self.assertIn("INFO", text)
        self.assertIn("旧格式记录", text)
        self.assertEqual(models.LogStore(log_path=log_path).entries[0].level,
                         models.LogLevel.WARNING)

    def test_settings_show_close_behavior_above_log_level(self):
        settings_page = self.window.pages["settings"]
        self.assertFalse(hasattr(settings_page, "reset_button"))
        layout = settings_page.findChild(components.SectionCard).body
        rows = [layout.itemAt(index).layout() for index in range(layout.count())]
        labels = []
        for row in rows:
            if row is not None:
                label = row.itemAt(0).widget()
                if isinstance(label, BodyLabel):
                    labels.append(label.text())
        self.assertEqual(labels, ["界面主题", "关闭时最小化到托盘", "运行日志等级"])
        self.assertTrue(settings_page.close_behavior_switch.label.isHidden())
        self.assertEqual(settings_page.close_behavior_switch.label.text(), "")
        self.assertEqual(settings_page.data_card.objectName(), "settingsDataCard")
        self.assertTrue(settings_page.clear_data_button.isVisibleTo(settings_page))
        self.assertFalse(hasattr(self.window.pages["about"], "clear_data_button"))

    def test_close_behavior_switch_persists_and_defaults_to_tray(self):
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=QSettings(self.settings_path, QSettings.IniFormat)),
            data_dir=self.data_dir,
        )
        try:
            settings_page = window.pages["settings"]
            self.assertTrue(settings_page.close_behavior_switch.isChecked())
            self.assertEqual(window.close_behavior, models.CLOSE_BEHAVIOR_TRAY)
            settings_page.close_behavior_switch.setChecked(False)
            self.assertEqual(window.close_behavior, models.CLOSE_BEHAVIOR_QUIT)
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()
        self.assertEqual(
            QSettings(self.settings_path, QSettings.IniFormat).value(
                models.CLOSE_BEHAVIOR_SETTINGS_KEY),
            models.CLOSE_BEHAVIOR_QUIT,
        )
        reloaded = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=QSettings(self.settings_path, QSettings.IniFormat)),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            self.assertEqual(reloaded.close_behavior, models.CLOSE_BEHAVIOR_QUIT)
            self.assertFalse(reloaded.pages["settings"].close_behavior_switch.isChecked())
        finally:
            reloaded._quit_requested = True
            reloaded.close()
            reloaded.deleteLater()

    def test_clear_data_requires_confirmation_and_removes_portable_folder(self):
        self.alias_store.add("教室 A", "192.168.1.10")
        self.window.logs.info("应用", "清除前日志")
        self.state.set_value("port", 8800)
        settings_page = self.window.pages["settings"]
        self.assertTrue(settings_page.clear_data_button.isEnabled())
        settings_page.clear_data_button.click()
        self.confirm.assert_called_once()
        self.assertFalse(self.data_dir.exists())
        self.assertEqual(self.alias_store.items(), [])
        self.assertEqual(self.state.values, self.state.DEFAULTS)
        self.assertEqual(len(self.window.logs.entries), 1)
        self.assertEqual(self.window.logs.entries[-1].message, "本地数据已清除")
        self.assertIsNone(self.window.logs.log_path)

    def test_clear_data_cancel_keeps_folder(self):
        self.confirm.return_value = False
        self.alias_store.add("教室 A", "192.168.1.10")
        self.window.pages["settings"].clear_data_button.click()
        self.assertTrue(self.data_dir.exists())
        self.assertIsNotNone(self.alias_store.match("教室 A"))

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
        self.assertTrue(any(entry.message == "操作已取消"
                            for entry in self.window.logs.entries))
        self.assertEqual(self.window.logs.entries[-1].message, "应用退出")

    def test_close_hides_to_tray_when_tray_mode_is_enabled(self):
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=QSettings(self.settings_path, QSettings.IniFormat)),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            window.show()
            window.tray_icon = TestTrayIcon(window)
            window.tray_menu = gui.SystemTrayMenu(parent=window)
            window.close_behavior = models.CLOSE_BEHAVIOR_TRAY
            window.close()
            self.assertFalse(window.isVisible())
            self.assertIsNotNone(window.tray_icon)
            self.assertEqual(window.tray_icon.messages, [])
            self.assertEqual(window.logs.entries[-1].message, "窗口已隐藏到系统托盘")
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()

    def test_first_close_can_minimize_to_tray_and_prompts_only_once(self):
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=QSettings(self.settings_path, QSettings.IniFormat)),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            window.enable_tray = True
            window.show()
            window.tray_icon = TestTrayIcon(window)
            window.tray_menu = gui.SystemTrayMenu(parent=window)
            with patch.object(gui.Dialog, "exec", return_value=1) as execute:
                window.close()
            execute.assert_called_once()
            self.assertFalse(window.isVisible())
            self.assertEqual(window.close_behavior, models.CLOSE_BEHAVIOR_TRAY)
            self.assertTrue(window.first_close_prompt_shown)
            self.assertTrue(QSettings(self.settings_path, QSettings.IniFormat).value(
                models.FIRST_CLOSE_PROMPT_SETTINGS_KEY, False, type=bool))

            window.show()
            with patch.object(gui.Dialog, "exec") as second_prompt:
                window.close()
            second_prompt.assert_not_called()
            self.assertFalse(window.isVisible())
            reloaded = gui.MainWindow(
                alias_store=gui.DeviceAliasStore(
                    settings=QSettings(self.settings_path, QSettings.IniFormat)),
                data_dir=self.data_dir,
                enable_tray=False,
            )
            try:
                self.assertTrue(reloaded.first_close_prompt_shown)
            finally:
                reloaded._quit_requested = True
                reloaded.close()
                reloaded.deleteLater()
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()

    def test_first_close_can_choose_direct_exit(self):
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=QSettings(self.settings_path, QSettings.IniFormat)),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            window.enable_tray = True
            window.show()
            window.tray_icon = TestTrayIcon(window)
            window.tray_menu = gui.SystemTrayMenu(parent=window)
            with patch.object(gui.Dialog, "exec", return_value=0) as execute:
                window.close()
            execute.assert_called_once()
            self.assertFalse(window.isVisible())
            self.assertEqual(window.close_behavior, models.CLOSE_BEHAVIOR_QUIT)
            self.assertTrue(window.first_close_prompt_shown)
            self.assertIsNone(window.tray_icon)
            self.assertTrue(QSettings(self.settings_path, QSettings.IniFormat).value(
                models.FIRST_CLOSE_PROMPT_SETTINGS_KEY, False, type=bool))
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()

    def test_close_quit_mode_exits_and_stops_tray(self):
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=QSettings(self.settings_path, QSettings.IniFormat)),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            window.show()
            tray = TestTrayIcon(window)
            window.tray_icon = tray
            window.tray_menu = gui.SystemTrayMenu(parent=window)
            window.set_close_behavior(models.CLOSE_BEHAVIOR_QUIT)
            window.close()
            self.assertFalse(window.isVisible())
            self.assertIsNone(window.tray_icon)
            self.assertEqual(window.logs.entries[-1].message, "应用退出")
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()

    def test_tray_menu_shows_window_and_quits(self):
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=QSettings(self.settings_path, QSettings.IniFormat)),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            tray = TestTrayIcon(window)
            window.tray_icon = tray
            window.tray_menu = gui.SystemTrayMenu(parent=window)
            window.hide()
            window.show_from_tray()
            self.assertTrue(window.isVisible())
            window.hide()
            window.quit_from_tray()
            self.assertFalse(window.isVisible())
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()


class SingleInstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen")
        cls.application = QApplication.instance() or QApplication([])

    def test_second_instance_notifies_primary(self):
        key = "JiYuAttackNext-test-%d" % id(self)
        primary = gui.SingleInstance(key)
        secondary = gui.SingleInstance(key)
        try:
            self.assertTrue(primary.acquire())
            activations = []
            primary.activationRequested.connect(lambda: activations.append(True))
            self.assertFalse(secondary.acquire())
            deadline = time.monotonic() + 3
            while not activations and time.monotonic() < deadline:
                QTest.qWait(10)
            self.assertEqual(activations, [True])
        finally:
            primary.close()
            secondary.close()

    def test_single_instance_key_is_user_specific(self):
        self.assertIn(gui.SINGLE_INSTANCE_KEY, gui.single_instance_key())


class TestTrayIcon(QSystemTrayIcon):
    """不依赖真实 Windows 通知区域的测试托盘图标。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.messages = []
        self.hideCount = 0

    def show(self):
        pass

    def hide(self):
        self.hideCount += 1

    def showMessage(self, *args, **kwargs):
        self.messages.append((args, kwargs))


if __name__ == "__main__":
    unittest.main()
