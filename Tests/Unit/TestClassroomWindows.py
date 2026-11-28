"""课堂助手窗口层的离线回归测试：识别、修复、假全屏与置顶。"""

import unittest

import NeoJiYuTrainer.Features.Classroom.Windows as windows
from Tests.Fixtures.Offline import OfflineCase

KIND_BROADCAST = windows.KIND_BROADCAST
KIND_BLACK = windows.KIND_BLACK
KIND_FULLSCREEN = windows.KIND_FULLSCREEN
SCREEN = (1920, 1080)


class FakeApi:
    """按 ``WindowsApi`` 的接口记录调用，不接触真实桌面。"""

    def __init__(self, screen=SCREEN, raw_windows=()):
        self.screen = screen
        self.raw_windows = [dict(item) for item in raw_windows]
        self.styles = {item["hwnd"]: item.get("style", 0) for item in raw_windows}
        self.exstyles = {item["hwnd"]: item.get("exstyle", 0) for item in raw_windows}
        self.positions = []
        self.shown = []
        self.sizes = []

    def screen_size(self):
        return self.screen

    def enum_windows(self):
        return [dict(item) for item in self.raw_windows]

    def get_style(self, hwnd):
        return self.styles.get(hwnd, 0)

    def set_style(self, hwnd, style):
        self.styles[hwnd] = style

    def get_exstyle(self, hwnd):
        return self.exstyles.get(hwnd, 0)

    def set_exstyle(self, hwnd, exstyle):
        self.exstyles[hwnd] = exstyle

    def set_window_pos(self, hwnd, zone, rect, flags):
        self.positions.append((hwnd, zone, rect, flags))

    def show_window(self, hwnd, command):
        self.shown.append((hwnd, command))

    def send_size(self, hwnd, size):
        self.sizes.append((hwnd, size))


def _raw(
    hwnd, title, pid=100, rect=(0, 0, 1920, 1080), topmost=False, style=0, visible=True
):
    """构造一条 WindowsApi.enum_windows 风格的原始记录。"""
    exstyle = windows.WS_EX_TOPMOST if topmost else 0
    return {
        "hwnd": hwnd,
        "title": title,
        "class_name": "TestWindow",
        "pid": pid,
        "visible": visible,
        "rect": rect,
        "style": style,
        "exstyle": exstyle,
    }


def _window(hwnd=11, kind=KIND_BROADCAST, fullscreen=True, topmost=True, sizable=False):
    """构造一条 collect_windows 风格的窗口记录。"""
    return {
        "hwnd": hwnd,
        "title": "屏幕广播",
        "kind": kind,
        "pid": 100,
        "visible": True,
        "fullscreen": fullscreen,
        "topmost": topmost,
        "sizable": sizable,
    }


class ClassroomWindowsTests(OfflineCase):
    def test_broadcast_title_rules_match_upstream(self):
        for title in (
            "屏幕广播",
            "演示窗口",
            "共享屏幕",
            "屏幕演播室窗口",
            "教师广播窗口",
        ):
            with self.subTest(title=title):
                self.assertTrue(windows.is_broadcast_title(title))
                self.assertEqual(windows.classify_title(title), KIND_BROADCAST)
        self.assertEqual(windows.classify_title("BlackScreen Window"), KIND_BLACK)
        self.assertEqual(windows.classify_title("记事本"), "")
        self.assertEqual(windows.classify_title(""), "")
        self.assertEqual(windows.classify_title(None), "")

    def test_fullscreen_geometry(self):
        self.assertTrue(windows.is_fullscreen((0, 0, 1920, 1080), SCREEN))
        self.assertFalse(windows.is_fullscreen((0, 0, 1920, 1079), SCREEN))
        self.assertFalse(windows.is_fullscreen((-8, -8, 1928, 1088), SCREEN))
        self.assertEqual(windows.windowed_rect(SCREEN), (240, 108, 1440, 864))
        self.assertEqual(windows.windowed_rect((1000, 900)), (125, 90, 750, 720))

    def test_collect_windows_filters_pid_and_fullscreen(self):
        api = FakeApi(
            raw_windows=[
                _raw(11, "屏幕广播", topmost=True),
                _raw(12, "BlackScreen Window"),
                _raw(13, "屏幕广播", pid=200),
                _raw(14, "记事本"),
                _raw(15, "记事本", rect=(10, 10, 300, 200)),
            ]
        )
        records = windows.collect_windows(100, True, api=api)
        self.assertEqual([item["hwnd"] for item in records], [11, 12, 14])
        self.assertEqual(
            [item["kind"] for item in records],
            [KIND_BROADCAST, KIND_BLACK, KIND_FULLSCREEN],
        )
        self.assertTrue(records[0]["topmost"])
        self.assertFalse(records[0]["sizable"])
        self.assertTrue(records[0]["fullscreen"])
        self.assertEqual(windows.collect_windows(100, False, api=api)[-1]["hwnd"], 12)
        self.assertEqual(windows.collect_windows(0, True, api=api), [])

    def test_needs_repair(self):
        self.assertTrue(windows.needs_repair(_window(topmost=True, sizable=True)))
        self.assertFalse(
            windows.needs_repair(
                _window(topmost=True, sizable=True, fullscreen=False), allow_top=True
            )
        )
        self.assertTrue(windows.needs_repair(_window(fullscreen=True, topmost=False)))
        self.assertTrue(windows.needs_repair(_window(sizable=False, topmost=False)))
        self.assertFalse(
            windows.needs_repair(_window(fullscreen=False, topmost=False, sizable=True))
        )
        black = _window(kind=KIND_BLACK)
        self.assertTrue(windows.needs_repair(black))
        self.assertFalse(windows.needs_repair(black, hide_black=False))

    def test_repair_broadcast_window_removes_topmost_and_windowed_size(self):
        api = FakeApi()
        api.exstyles[11] = windows.WS_EX_TOPMOST
        api.styles[11] = 0
        self.assertTrue(windows.repair_window(_window(), api=api))
        self.assertFalse(api.exstyles[11] & windows.WS_EX_TOPMOST)
        self.assertTrue(api.styles[11] & windows.WS_OVERLAPPEDWINDOW)
        hwnd, zone, rect, flags = api.positions[-1]
        self.assertEqual(hwnd, 11)
        self.assertEqual(zone, "notopmost")
        self.assertEqual(rect, (240, 108, 1440, 864))
        self.assertTrue(flags & windows.SWP_NOZORDER)

    def test_repair_keeps_topmost_when_allowed(self):
        api = FakeApi()
        api.exstyles[11] = windows.WS_EX_TOPMOST
        windows.repair_window(_window(), allow_top=True, api=api)
        self.assertTrue(api.exstyles[11] & windows.WS_EX_TOPMOST)
        self.assertEqual(api.positions[-1][1], "")

    def test_repair_black_screen_hides_window(self):
        api = FakeApi()
        api.exstyles[12] = windows.WS_EX_APPWINDOW
        black = _window(hwnd=12, kind=KIND_BLACK)
        self.assertTrue(windows.repair_window(black, api=api))
        self.assertFalse(api.exstyles[12] & windows.WS_EX_APPWINDOW)
        self.assertTrue(api.exstyles[12] & windows.WS_EX_NOACTIVATE)
        self.assertEqual(api.positions[-1][2], windows.BLACK_SCREEN_GEOMETRY)
        self.assertEqual(api.shown[-1], (12, windows.SW_HIDE))
        self.assertFalse(windows.repair_window(black, hide_black=False, api=api))

    def test_fake_full_and_restore(self):
        api = FakeApi()
        # 真实的全屏窗口样式里仍带 WS_OVERLAPPEDWINDOW，异或后才会去掉边框。
        api.styles[11] = windows.WS_OVERLAPPEDWINDOW
        windows.fake_full([_window()], api=api)
        self.assertTrue(api.exstyles[11] & windows.WS_EX_TOPMOST)
        self.assertFalse(api.styles[11] & windows.WS_BORDER)
        self.assertEqual(api.positions[-1][1], "topmost")
        self.assertEqual(api.positions[-1][2], (0, 0, 1920, 1080))
        self.assertEqual(api.sizes[-1], (11, (1920, 1080)))

        windows.restore_windowed([_window()], api=api)
        self.assertFalse(api.exstyles[11] & windows.WS_EX_TOPMOST)
        self.assertTrue(api.styles[11] & windows.WS_OVERLAPPEDWINDOW)
        self.assertEqual(api.positions[-1][2], (240, 108, 1440, 864))
        self.assertEqual(api.positions[-1][1], "notopmost")

    def test_set_topmost(self):
        api = FakeApi()
        windows.set_topmost(
            [_window(topmost=False), _window(hwnd=12, kind=KIND_BLACK)], True, api=api
        )
        self.assertTrue(api.exstyles[11] & windows.WS_EX_TOPMOST)
        self.assertEqual([call[0] for call in api.positions], [11])
        self.assertEqual(api.positions[0][1], "topmost")
        windows.set_topmost([_window()], False, api=api)
        self.assertFalse(api.exstyles[11] & windows.WS_EX_TOPMOST)
        self.assertEqual(api.positions[-1][1], "notopmost")


if __name__ == "__main__":
    unittest.main()
