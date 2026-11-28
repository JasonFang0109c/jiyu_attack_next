"""课堂助手三个标签页的界面回归测试：状态、表格、密码与设置信号。"""

import os
import socket
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault(
    "QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen"
)

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from NeoJiYuTrainer.Features.Classroom.Data import (
    SETTINGS_ALLOW_TOP,
    SETTINGS_AUTO_REPAIR,
    SETTINGS_GUARD_FLAGS,
    SETTINGS_INTERVAL,
)
from NeoJiYuTrainerUI.Features.Classroom.Gui.Page import (
    ClassroomGuardPage,
    ClassroomPasswordPage,
    ClassroomViews,
    ClassroomWindowPage,
)


def _snapshot(windows_list=(), running=True, supported=True):
    """构造一份页面快照。"""
    return {
        "supported": supported,
        "student_running": running,
        "student_pid": 17600 if running else 0,
        "windows": list(windows_list),
        "options": {
            "auto_repair": True,
            "interval": 3,
            "allow_top": False,
            "include_fullscreen": True,
            "hide_black_screen": True,
        },
    }


def _window(
    title="屏幕广播", kind="broadcast", fullscreen=True, topmost=False, sizable=False
):
    """构造一条窗口记录。"""
    return {
        "hwnd": 11,
        "title": title,
        "kind": kind,
        "pid": 17600,
        "visible": True,
        "fullscreen": fullscreen,
        "topmost": topmost,
        "sizable": sizable,
    }


class ClassroomPageTests(unittest.TestCase):
    """验证三个标签页只做展示与发信号，不直接碰系统窗口。"""

    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        network_guard = patch.object(
            socket, "socket", side_effect=AssertionError("禁止真实网络通信")
        )
        network_guard.start()
        self.addCleanup(network_guard.stop)
        self.window_page = ClassroomWindowPage()
        self.guard_page = ClassroomGuardPage()
        self.password_page = ClassroomPasswordPage()
        self.views = ClassroomViews(
            self.window_page, self.guard_page, self.password_page
        )
        self.page = self.window_page
        self.addCleanup(self.dispose_pages)
        self.emitted = []
        for page in self.views.pages:
            page.optionChanged.connect(
                lambda key, value: self.emitted.append((key, value))
            )

    def dispose_pages(self):
        """释放页面，避免影响其他界面用例。"""
        for page in self.views.pages:
            page.deleteLater()
            QCoreApplication.sendPostedEvents(page, QEvent.Type.DeferredDelete)

    def test_tabs_have_their_own_route_names(self):
        self.assertEqual(
            [page.objectName() for page in self.views.pages],
            ["classroom", "classroomguard", "classroompassword"],
        )
        self.assertEqual(
            [page.TITLE for page in self.views.pages],
            ["课堂窗口", "课堂防护", "解锁密码"],
        )

    def test_set_options_fills_controls_without_saving(self):
        self.views.set_options(
            {
                "auto_repair": False,
                "interval": 5,
                "allow_top": True,
                "include_fullscreen": False,
                "hide_black_screen": False,
                "guard_flags": 5,
            }
        )
        self.assertEqual(self.emitted, [])
        self.assertFalse(self.page.auto_switch.isChecked())
        self.assertEqual(self.page.interval_box.value(), 5)
        self.assertTrue(self.page.allow_top_switch.isChecked())
        self.assertFalse(self.page.include_fullscreen_switch.isChecked())
        self.assertFalse(self.page.hide_black_switch.isChecked())
        # 防护位只落在课堂防护页的开关上。
        self.assertEqual(self.guard_page._guard_flags(), 5)

    def test_option_change_emits_settings_key(self):
        self.page.set_options({"auto_repair": True, "interval": 3})
        self.emitted.clear()
        self.page.auto_switch.setChecked(False)
        self.assertIn((SETTINGS_AUTO_REPAIR, False), self.emitted)
        self.page.interval_box.setValue(6)
        self.assertIn((SETTINGS_INTERVAL, 6), self.emitted)
        self.page.allow_top_switch.setChecked(True)
        self.assertIn((SETTINGS_ALLOW_TOP, True), self.emitted)

    def test_snapshot_with_windows_fills_table(self):
        self.page.set_snapshot(
            _snapshot([_window(), _window("BlackScreen Window", "black")])
        )
        self.assertEqual(self.page.table.rowCount(), 2)
        self.assertEqual(self.page.table.item(0, 0).text(), "屏幕广播")
        self.assertEqual(self.page.table.item(0, 1).text(), "广播")
        self.assertEqual(self.page.table.item(1, 1).text(), "黑屏")
        self.assertIn("发现 2 个课堂窗口", self.page.status.text())
        self.assertIn("17600", self.page.status.text())

    def test_snapshot_without_student(self):
        self.page.set_snapshot(_snapshot([], running=False))
        self.assertEqual(self.page.table.rowCount(), 0)
        self.assertIn("没有正在运行的学生端", self.page.status.text())

    def test_snapshot_on_unsupported_system(self):
        self.page.set_snapshot(_snapshot([], running=False, supported=False))
        self.assertIn("不支持窗口操作", self.page.status.text())

    def test_password_success_and_failure(self):
        self.password_page.set_password(
            {"password": "secret", "source": "knock", "error": ""}
        )
        self.assertEqual(self.password_page.password_label.text(), "secret")
        self.assertTrue(self.password_page.copy_password_button.isEnabled())
        self.assertIn("Knock1", self.password_page.password_detail.text())

        self.password_page.set_password(
            {"password": "", "source": "", "error": "读取失败"}
        )
        self.assertEqual(self.password_page.password_label.text(), "未读取")
        self.assertFalse(self.password_page.copy_password_button.isEnabled())
        self.assertIn("读取失败", self.password_page.password_detail.text())

    def test_copy_request_only_with_password(self):
        copies = []
        self.password_page.copyPasswordRequested.connect(copies.append)
        self.password_page._request_password_copy()
        self.assertEqual(copies, [])
        self.password_page.set_password(
            {"password": "secret", "source": "plain", "error": ""}
        )
        self.password_page._request_password_copy()
        self.assertEqual(copies, ["secret"])

    def test_fake_full_and_topmost_labels(self):
        self.page.set_fake_full(True)
        self.assertEqual(self.page.fake_full_button.text(), "还原窗口")
        self.page.set_fake_full(False)
        self.assertEqual(self.page.fake_full_button.text(), "开启假全屏")
        self.page.set_topmost(True)
        self.assertEqual(self.page.topmost_button.text(), "取消置顶")
        self.page.set_topmost(False)
        self.assertEqual(self.page.topmost_button.text(), "窗口置顶")

    def test_guard_card_emits_flags_and_shows_state(self):
        requests = []
        self.guard_page.guardRequested.connect(requests.append)
        self.guard_page.set_options({"guard_flags": 5})
        self.assertEqual(self.guard_page._guard_flags(), 5)
        self.guard_page.guard_start_button.click()
        self.assertEqual(requests, [5])
        self.emitted.clear()
        self.guard_page._guard_switches[1][1].setChecked(True)
        self.assertIn((SETTINGS_GUARD_FLAGS, 7), self.emitted)
        self.guard_page.set_guard_state(True, 5, 17600)
        self.assertIn("已启用 2 项", self.guard_page.guard_status.text())
        self.assertIn("17600", self.guard_page.guard_status.text())
        self.assertFalse(self.guard_page.guard_start_button.isEnabled())
        self.assertTrue(self.guard_page.guard_stop_button.isEnabled())
        self.guard_page.set_guard_state(False)
        self.assertIn("未启用", self.guard_page.guard_status.text())
        self.assertTrue(self.guard_page.guard_start_button.isEnabled())
        self.assertFalse(self.guard_page.guard_stop_button.isEnabled())

    def test_busy_disables_action_buttons(self):
        self.views.set_busy(True)
        for button in (
            self.page.repair_button,
            self.page.fake_full_button,
            self.page.topmost_button,
            self.page.refresh_button,
            self.password_page.read_password_button,
            self.guard_page.guard_start_button,
            self.guard_page.guard_stop_button,
        ):
            self.assertFalse(button.isEnabled())
        self.views.set_busy(False)
        self.assertTrue(self.page.repair_button.isEnabled())
        self.assertTrue(self.password_page.read_password_button.isEnabled())
        # 防护没启用时只有“启用防护”可点。
        self.assertTrue(self.guard_page.guard_start_button.isEnabled())
        self.assertFalse(self.guard_page.guard_stop_button.isEnabled())

    def test_views_forward_guard_and_password(self):
        self.views.set_guard_state(True, 3, 17600)
        self.assertTrue(self.guard_page.guard_enabled)
        self.assertIn("17600", self.guard_page.guard_status.text())
        self.views.set_password({"password": "123456", "source": "plain", "error": ""})
        self.assertEqual(self.password_page.password_label.text(), "123456")
        self.views.set_snapshot(_snapshot([_window()]))
        self.assertEqual(self.page.table.rowCount(), 1)


if __name__ == "__main__":
    unittest.main()
