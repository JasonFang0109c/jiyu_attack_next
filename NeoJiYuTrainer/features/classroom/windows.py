"""课堂助手的 Windows 窗口访问层。

上游 JiYuTrainer（MIT）在注入的 Hook DLL 里改窗口样式，这里改为在进程内用 ctypes 调
同一组 user32 接口：不注入学生端、不需要驱动。所有系统调用都收在
``WindowsApi`` 里，测试用同接口的假对象替换，不会碰真实桌面。
"""

import ctypes
import sys
from ctypes import wintypes

from NeoJiYuTrainer.features.classroom.data import (
    BLACK_SCREEN_GEOMETRY,
    BLACK_SCREEN_TITLE,
    BROADCAST_TITLE_EXACT,
    BROADCAST_TITLE_KEYWORDS,
    WINDOWED_HEIGHT_RATIO,
    WINDOWED_WIDTH_RATIO,
)

WS_BORDER = 0x00800000
WS_OVERLAPPEDWINDOW = 0x00CF0000

WS_EX_TOPMOST = 0x00000008
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000

GWL_STYLE = -16
GWL_EXSTYLE = -20

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_DRAWFRAME = 0x0020
SWP_SHOWWINDOW = 0x0040

SW_HIDE = 0

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
WM_SIZE = 0x0005

TITLE_BUFFER = 512
CLASS_BUFFER = 256

KIND_BROADCAST = "broadcast"
KIND_BLACK = "black"
KIND_FULLSCREEN = "fullscreen"

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def available():
    """返回当前系统是否支持窗口操作。"""
    return sys.platform == "win32"


class WindowsApi:
    """课堂助手用到的 user32 调用，集中声明参数类型避免句柄被截断。"""

    def __init__(self):
        if not available():
            raise OSError("课堂助手只支持 Windows")
        self.user32 = ctypes.windll.user32
        self._declare()

    def _declare(self):
        user32 = self.user32
        user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SendMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        pointer_getter = getattr(user32, "GetWindowLongPtrW", None)
        pointer_setter = getattr(user32, "SetWindowLongPtrW", None)
        if pointer_getter is None or pointer_setter is None:
            pointer_getter = user32.GetWindowLongW
            pointer_setter = user32.SetWindowLongW
        pointer_getter.argtypes = [wintypes.HWND, ctypes.c_int]
        pointer_getter.restype = ctypes.c_ssize_t
        pointer_setter.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        pointer_setter.restype = ctypes.c_ssize_t
        self._get_long = pointer_getter
        self._set_long = pointer_setter

    def screen_size(self):
        """返回主屏尺寸 ``(宽, 高)``。"""
        return (
            int(self.user32.GetSystemMetrics(0)),
            int(self.user32.GetSystemMetrics(1)),
        )

    def enum_windows(self):
        """枚举所有顶层窗口，返回标题、类名、进程与几何等原始数据。"""
        items = []

        @EnumWindowsProc
        def _callback(hwnd, _lparam):
            items.append(self._window_info(hwnd))
            return True

        self.user32.EnumWindows(_callback, 0)
        return items

    def _window_info(self, hwnd):
        """读单个窗口的原始信息；回调里不能抛异常，失败按空值返回。"""
        title = ctypes.create_unicode_buffer(TITLE_BUFFER)
        class_name = ctypes.create_unicode_buffer(CLASS_BUFFER)
        pid = wintypes.DWORD()
        rect = wintypes.RECT()
        self.user32.GetWindowTextW(hwnd, title, TITLE_BUFFER)
        self.user32.GetClassNameW(hwnd, class_name, CLASS_BUFFER)
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return {
            "hwnd": int(hwnd),
            "title": title.value,
            "class_name": class_name.value,
            "pid": int(pid.value),
            "visible": bool(self.user32.IsWindowVisible(hwnd)),
            "rect": (rect.left, rect.top, rect.right, rect.bottom),
            "style": self.get_style(hwnd),
            "exstyle": self.get_exstyle(hwnd),
        }

    def get_style(self, hwnd):
        """读窗口普通样式。"""
        return int(self._get_long(hwnd, GWL_STYLE)) & 0xFFFFFFFF

    def set_style(self, hwnd, style):
        """写窗口普通样式。"""
        self._set_long(hwnd, GWL_STYLE, style)

    def get_exstyle(self, hwnd):
        """读窗口扩展样式。"""
        return int(self._get_long(hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF

    def set_exstyle(self, hwnd, exstyle):
        """写窗口扩展样式。"""
        self._set_long(hwnd, GWL_EXSTYLE, exstyle)

    def set_window_pos(self, hwnd, zone, rect, flags):
        """按 ``zone`` 调整窗口位置与 Z 序。

        Args:
            hwnd: 目标窗口。
            zone: ``topmost``、``notopmost`` 或空串（保持原 Z 序）。
            rect: ``(x, y, 宽, 高)``，``None`` 时配合 NOMOVE/NOSIZE 只改样式。
            flags: SetWindowPos 标志位。
        """
        after = {
            "topmost": HWND_TOPMOST,
            "notopmost": HWND_NOTOPMOST,
        }.get(zone, 0)
        x, y, width, height = rect or (0, 0, 0, 0)
        self.user32.SetWindowPos(hwnd, after, x, y, width, height, flags)

    def show_window(self, hwnd, command):
        """按 ShowWindow 命令显示或隐藏窗口。"""
        self.user32.ShowWindow(hwnd, command)

    def send_size(self, hwnd, size):
        """通知窗口按新尺寸重排客户区，与上游 WM_SIZE 的做法一致。"""
        width, height = size
        lparam = (int(height) << 16) | (int(width) & 0xFFFF)
        self.user32.SendMessageW(hwnd, WM_SIZE, 0, lparam)


_api_singleton = None


def _api(api=None):
    """返回注入的假对象或进程内共享的真实 API。"""
    global _api_singleton
    if api is not None:
        return api
    if _api_singleton is None:
        _api_singleton = WindowsApi()
    return _api_singleton


def is_broadcast_title(title):
    """判断标题是否属于极域广播类窗口，规则与上游一致。"""
    text = str(title or "")
    if text == BROADCAST_TITLE_EXACT:
        return True
    return any(keyword in text for keyword in BROADCAST_TITLE_KEYWORDS)


def classify_title(title):
    """把窗口标题归类为 ``broadcast``、``black`` 或空串。"""
    text = str(title or "").strip()
    if text == BLACK_SCREEN_TITLE:
        return KIND_BLACK
    return KIND_BROADCAST if is_broadcast_title(text) else ""


def is_fullscreen(rect, screen):
    """判断窗口矩形是否正好铺满整块屏幕。"""
    return tuple(rect) == (0, 0, int(screen[0]), int(screen[1]))


def windowed_rect(screen):
    """按上游 3/4 宽、4/5 高把窗口居中摆放，返回 ``(x, y, 宽, 高)``。"""
    width = int(screen[0] * WINDOWED_WIDTH_RATIO)
    height = int(screen[1] * WINDOWED_HEIGHT_RATIO)
    return (
        (int(screen[0]) - width) // 2,
        (int(screen[1]) - height) // 2,
        width,
        height,
    )


def collect_windows(pid, include_fullscreen=True, api=None):
    """收集某个进程的课堂窗口。

    Args:
        pid: 学生端进程号，0 表示本机没有学生端。
        include_fullscreen: 是否把铺满屏幕的其它窗口也算作课堂窗口，
            对应上游 ``AutoIncludeFullWindow``。
        api: 测试注入的假 API。

    Returns:
        窗口记录列表，每项含 hwnd、title、kind、pid、visible、fullscreen、
        topmost 与 sizable。
    """
    if not pid:
        return []
    api = _api(api)
    screen = api.screen_size()
    windows = []
    for raw in api.enum_windows():
        if raw["pid"] != pid:
            continue
        kind = classify_title(raw["title"])
        fullscreen = is_fullscreen(raw["rect"], screen)
        if not kind:
            if not include_fullscreen or not fullscreen:
                continue
            kind = KIND_FULLSCREEN
        windows.append(
            {
                "hwnd": raw["hwnd"],
                "title": raw["title"],
                "kind": kind,
                "pid": raw["pid"],
                "visible": bool(raw["visible"]),
                "fullscreen": fullscreen,
                "topmost": bool(raw["exstyle"] & WS_EX_TOPMOST),
                "sizable": bool(raw["style"] & WS_OVERLAPPEDWINDOW),
            }
        )
    return windows


def needs_repair(window, allow_top=False, hide_black=True):
    """判断一个窗口当前是否需要修复。"""
    if window["kind"] == KIND_BLACK:
        return bool(hide_black and window["visible"])
    return bool(
        (window["topmost"] and not allow_top)
        or not window["sizable"]
        or window["fullscreen"]
    )


def repair_window(window, allow_top=False, hide_black=True, api=None):
    """把单个窗口修复成可移动、可缩放的普通窗口。

    黑屏窗口按上游做法去掉任务栏按钮、缩到角落并隐藏；广播与全屏窗口去掉
    不允许的置顶、补上边框，铺满屏幕的再缩成 3/4 宽、4/5 高居中。

    Returns:
        是否实际改动了窗口。
    """
    api = _api(api)
    hwnd = window["hwnd"]
    if window["kind"] == KIND_BLACK:
        if not hide_black:
            return False
        old_ex = api.get_exstyle(hwnd)
        wanted = old_ex ^ (WS_EX_APPWINDOW | WS_EX_NOACTIVATE)
        if wanted != old_ex:
            api.set_exstyle(hwnd, wanted)
        api.set_window_pos(
            hwnd,
            "",
            BLACK_SCREEN_GEOMETRY,
            SWP_NOZORDER | SWP_DRAWFRAME | SWP_NOACTIVATE,
        )
        api.show_window(hwnd, SW_HIDE)
        return True

    old_style = api.get_style(hwnd)
    old_ex = api.get_exstyle(hwnd)
    zone = ""
    wanted_ex = old_ex
    if window["topmost"] and not allow_top:
        wanted_ex &= ~WS_EX_TOPMOST
        zone = "notopmost"
    wanted_style = old_style | WS_BORDER | WS_OVERLAPPEDWINDOW
    if wanted_ex != old_ex:
        api.set_exstyle(hwnd, wanted_ex)
    if wanted_style != old_style:
        api.set_style(hwnd, wanted_style)
    rect = windowed_rect(api.screen_size()) if window["fullscreen"] else None
    if window["fullscreen"]:
        flags = SWP_NOZORDER | SWP_DRAWFRAME | SWP_NOACTIVATE
    else:
        flags = SWP_NOZORDER | SWP_NOSIZE | SWP_NOMOVE | SWP_DRAWFRAME | SWP_NOACTIVATE
    api.set_window_pos(hwnd, zone, rect, flags)
    return True


def set_topmost(windows, enabled, api=None):
    """批量设置广播窗口的置顶状态，对应上游 ManualTop。"""
    api = _api(api)
    zone = "topmost" if enabled else "notopmost"
    for window in windows:
        if window["kind"] == KIND_BLACK:
            continue
        hwnd = window["hwnd"]
        old_ex = api.get_exstyle(hwnd)
        wanted_ex = old_ex | WS_EX_TOPMOST if enabled else old_ex & ~WS_EX_TOPMOST
        if wanted_ex != old_ex:
            api.set_exstyle(hwnd, wanted_ex)
        api.set_window_pos(
            hwnd,
            zone,
            None,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )


def fake_full(windows, api=None):
    """把广播窗口临时铺满并置顶，对应上游 FakeFull(TRUE)。"""
    api = _api(api)
    screen = api.screen_size()
    for window in windows:
        if window["kind"] == KIND_BLACK:
            continue
        hwnd = window["hwnd"]
        api.set_exstyle(hwnd, api.get_exstyle(hwnd) | WS_EX_TOPMOST)
        api.set_style(
            hwnd,
            api.get_style(hwnd) ^ (WS_BORDER | WS_OVERLAPPEDWINDOW),
        )
        api.set_window_pos(
            hwnd,
            "topmost",
            (0, 0, int(screen[0]), int(screen[1])),
            SWP_SHOWWINDOW,
        )
        api.send_size(hwnd, screen)


def restore_windowed(windows, allow_top=False, hide_black=True, api=None):
    """假全屏关闭后把窗口还原成 3/4 宽、4/5 高的居中窗口。"""
    api = _api(api)
    screen = api.screen_size()
    for window in windows:
        if window["kind"] == KIND_BLACK:
            repair_window(window, allow_top, hide_black, api=api)
            continue
        hwnd = window["hwnd"]
        api.set_style(hwnd, api.get_style(hwnd) | WS_BORDER | WS_OVERLAPPEDWINDOW)
        old_ex = api.get_exstyle(hwnd)
        wanted_ex = old_ex if allow_top else old_ex & ~WS_EX_TOPMOST
        if wanted_ex != old_ex:
            api.set_exstyle(hwnd, wanted_ex)
        api.set_window_pos(
            hwnd,
            "" if allow_top else "notopmost",
            windowed_rect(screen),
            SWP_NOZORDER | SWP_SHOWWINDOW,
        )
