"""课堂助手业务层的离线回归测试：设置、进程选择与动作编排。"""

import unittest
from unittest.mock import patch

import app.features.classroom.passwords as passwords
import app.features.classroom.service as classroom
import app.features.classroom.windows as windows
from app.features.classroom.data import (
    DEFAULT_INTERVAL,
    SETTINGS_ALLOW_TOP,
    SETTINGS_AUTO_REPAIR,
    SETTINGS_GUARD_FLAGS,
    SETTINGS_INTERVAL,
)
from tests.fixtures.offline import OfflineCase


def _record(pid=17600, genuine=True):
    """构造一条学生端进程记录。"""
    return {
        "pid": pid,
        "name": "StudentMain.exe",
        "ports": [4705],
        "path": "C:/Program Files/mythware/StudentMain.exe",
        "genuine": genuine,
        "creation": 1,
    }


def _window(hwnd=11, kind=windows.KIND_BROADCAST):
    """构造一条课堂窗口记录。"""
    return {
        "hwnd": hwnd,
        "title": "屏幕广播",
        "kind": kind,
        "pid": 17600,
        "visible": True,
        "fullscreen": True,
        "topmost": True,
        "sizable": False,
    }


class ClassroomServiceTests(OfflineCase):
    def setUp(self):
        self.data_dir = self.test_root / ("service-" + self._testMethodName)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def test_defaults(self):
        self.assertEqual(
            classroom.load_options(self.data_dir),
            {
                "auto_repair": True,
                "interval": DEFAULT_INTERVAL,
                "allow_top": False,
                "include_fullscreen": True,
                "hide_black_screen": True,
                "guard_flags": 0,
            },
        )

    def test_save_and_reload_options(self):
        self.assertTrue(
            classroom.save_option(SETTINGS_AUTO_REPAIR, False, self.data_dir)["ok"]
        )
        classroom.save_option(SETTINGS_INTERVAL, 7, self.data_dir)
        classroom.save_option(SETTINGS_ALLOW_TOP, True, self.data_dir)
        options = classroom.load_options(self.data_dir)
        self.assertFalse(options["auto_repair"])
        self.assertEqual(options["interval"], 7)
        self.assertTrue(options["allow_top"])

    def test_guard_flags_are_masked(self):
        classroom.save_option(SETTINGS_GUARD_FLAGS, 0xFF, self.data_dir)
        self.assertEqual(classroom.load_options(self.data_dir)["guard_flags"], 31)
        classroom.save_option(SETTINGS_GUARD_FLAGS, "bad", self.data_dir)
        self.assertEqual(classroom.load_options(self.data_dir)["guard_flags"], 0)

    def test_interval_is_clamped(self):
        classroom.save_option(SETTINGS_INTERVAL, 99, self.data_dir)
        self.assertEqual(classroom.load_options(self.data_dir)["interval"], 10)
        classroom.save_option(SETTINGS_INTERVAL, 0, self.data_dir)
        self.assertEqual(classroom.load_options(self.data_dir)["interval"], 1)
        classroom.save_option(SETTINGS_INTERVAL, "abc", self.data_dir)
        self.assertEqual(
            classroom.load_options(self.data_dir)["interval"], DEFAULT_INTERVAL
        )

    def test_boolean_values_accept_strings(self):
        self.assertTrue(classroom._as_bool("true", False))
        self.assertTrue(classroom._as_bool("1", False))
        self.assertFalse(classroom._as_bool("off", True))
        self.assertTrue(classroom._as_bool(None, True))

    def test_student_pid_prefers_genuine_process(self):
        self.assertEqual(
            classroom.student_pid([_record(1, False), _record(2, True), _record(3)]), 2
        )
        self.assertEqual(classroom.student_pid([_record(9, False)]), 9)
        self.assertEqual(classroom.student_pid([]), 0)

    def test_snapshot_reports_state(self):
        with (
            patch.object(classroom, "find_student_processes", return_value=[_record()]),
            patch.object(windows, "available", return_value=True),
            patch.object(windows, "collect_windows", return_value=[_window()]),
        ):
            snapshot = classroom.snapshot(self.data_dir)
        self.assertTrue(snapshot["supported"])
        self.assertTrue(snapshot["student_running"])
        self.assertEqual(snapshot["student_pid"], 17600)
        self.assertEqual(snapshot["windows"], [_window()])
        self.assertTrue(snapshot["options"]["auto_repair"])

    def test_repair_counts_only_windows_needing_repair(self):
        targets = [_window(11), _window(12)]
        with (
            patch.object(classroom, "student_pid", return_value=17600),
            patch.object(classroom, "collect", side_effect=[targets, targets]),
            patch.object(windows, "needs_repair", side_effect=[True, False]),
            patch.object(windows, "repair_window") as repair_window,
        ):
            result = classroom.repair(self.data_dir)
        self.assertEqual(result["repaired"], 1)
        self.assertEqual(repair_window.call_count, 1)
        self.assertEqual(result["student_pid"], 17600)

    def test_repair_without_student_does_nothing(self):
        with patch.object(classroom, "student_pid", return_value=0):
            result = classroom.repair(self.data_dir)
        self.assertEqual(result, {"repaired": 0, "windows": [], "student_pid": 0})

    def test_auto_tick_respects_switch(self):
        classroom.save_option(SETTINGS_AUTO_REPAIR, False, self.data_dir)
        with patch.object(classroom, "repair") as repair:
            self.assertEqual(
                classroom.auto_tick(self.data_dir), {"repaired": 0, "enabled": False}
            )
        repair.assert_not_called()

        classroom.save_option(SETTINGS_AUTO_REPAIR, True, self.data_dir)
        with patch.object(
            classroom, "repair", return_value={"repaired": 2, "windows": []}
        ):
            self.assertEqual(
                classroom.auto_tick(self.data_dir),
                {"repaired": 2, "windows": [], "enabled": True},
            )

    def test_fake_full_and_topmost_delegate(self):
        with (
            patch.object(classroom, "student_pid", return_value=1),
            patch.object(classroom, "collect", return_value=[_window()]),
            patch.object(windows, "fake_full") as fake_full,
            patch.object(windows, "restore_windowed") as restore,
        ):
            classroom.toggle_fake_full(True, self.data_dir)
            fake_full.assert_called_once()
            classroom.toggle_fake_full(False, self.data_dir)
            restore.assert_called_once()

        with (
            patch.object(classroom, "student_pid", return_value=1),
            patch.object(classroom, "collect", return_value=[_window()]),
            patch.object(windows, "set_topmost") as set_topmost,
        ):
            result = classroom.set_topmost(True, self.data_dir)
            self.assertTrue(result["topmost"])
        set_topmost.assert_called_once()

    def test_read_password_passthrough(self):
        with patch.object(
            passwords, "read_password", return_value={"password": "x"}
        ) as read:
            self.assertEqual(classroom.read_password(), {"password": "x"})
        read.assert_called_once()

    def test_start_guard_requires_student(self):
        with (
            patch.object(classroom, "student_pid", return_value=0),
            self.assertRaisesRegex(RuntimeError, "学生端未运行"),
        ):
            classroom.start_guard(1)

    def test_start_and_stop_guard_use_session(self):
        class FakeSession:
            def __init__(self, pid, dll_path):
                self.pid = pid
                self.dll_path = dll_path
                self.flags = None
                self.stopped = False

            def start(self, flags):
                self.flags = flags

            def stop(self):
                self.stopped = True

        created = []

        def factory(pid, dll_path):
            session = FakeSession(pid, dll_path)
            created.append(session)
            return session

        with (
            patch.object(classroom, "student_pid", return_value=17600),
            patch.object(classroom, "_guard_dll", return_value="guard_x64.dll"),
            patch.object(classroom.guard, "GuardSession", side_effect=factory),
            patch.object(classroom.guard, "supported", return_value=True),
        ):
            result = classroom.start_guard(0xFF)
            self.assertEqual(result["flags"], 31)
            self.assertEqual(created[0].flags, 31)
            classroom.stop_guard(result["session"])
            self.assertTrue(created[0].stopped)


if __name__ == "__main__":
    unittest.main()
