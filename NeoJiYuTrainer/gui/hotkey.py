"""全局热键管理器：用隐藏窗口接收 WM_HOTKEY。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QObject, Signal

from NeoJiYuTrainer.system.windows.hotkey import WM_HOTKEY, parse_hotkey

_WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


_USER32 = ctypes.WinDLL("user32", use_last_error=True)
_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
_KERNEL32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_KERNEL32.GetModuleHandleW.restype = wintypes.HINSTANCE
_USER32.DefWindowProcW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_USER32.DefWindowProcW.restype = ctypes.c_ssize_t
_USER32.CreateWindowExW.restype = wintypes.HWND
_USER32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
_USER32.DestroyWindow.argtypes = [wintypes.HWND]
_USER32.DestroyWindow.restype = wintypes.BOOL
_USER32.RegisterHotKey.argtypes = [
    wintypes.HWND,
    ctypes.c_int,
    wintypes.UINT,
    wintypes.UINT,
]
_USER32.RegisterHotKey.restype = wintypes.BOOL
_USER32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_USER32.UnregisterHotKey.restype = wintypes.BOOL
_USER32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASSW)]
_USER32.RegisterClassW.restype = wintypes.ATOM

_HOTKEY_WINDOWS: dict[int, "HotkeyManager"] = {}
_WINDOW_CLASS_REGISTERED = False
_WINDOW_CLASS_NAME = "NeoJiYuTrainerHotkeyWindow"


def _window_proc(hwnd, message, wparam, lparam):
    """全局隐藏窗口过程：按窗口句柄分发 WM_HOTKEY。"""
    if message == WM_HOTKEY:
        manager = _HOTKEY_WINDOWS.get(int(hwnd))
        if manager is not None:
            manager._dispatch(int(wparam))
            return 0
    return _USER32.DefWindowProcW(hwnd, message, wparam, lparam)


_WINDOW_PROC = _WNDPROC(_window_proc)


class HotkeyManager(QObject):
    """注册全局热键并把 WM_HOTKEY 转成回调。"""

    triggered = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._next_id = 0x4A59
        self._installed = False
        self._failed: list[str] = []
        self._hwnd: int | None = None

    @property
    def failed(self) -> list[str]:
        """返回最近一次注册失败的热键文本。"""
        return list(self._failed)

    def _dispatch(self, hotkey_id: int) -> None:
        callback = self._callbacks.get(hotkey_id)
        if callback is not None:
            callback()

    def _ensure_window(self) -> bool:
        global _WINDOW_CLASS_REGISTERED
        if self._hwnd is not None:
            return True
        if not _WINDOW_CLASS_REGISTERED:
            window_class = _WNDCLASSW()
            window_class.lpfnWndProc = _WINDOW_PROC
            window_class.hInstance = _KERNEL32.GetModuleHandleW(None)
            window_class.lpszClassName = _WINDOW_CLASS_NAME
            _USER32.RegisterClassW(ctypes.byref(window_class))
            _WINDOW_CLASS_REGISTERED = True
        hwnd = _USER32.CreateWindowExW(
            0,
            _WINDOW_CLASS_NAME,
            "",
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            _KERNEL32.GetModuleHandleW(None),
            None,
        )
        if not hwnd:
            return False
        self._hwnd = int(hwnd)
        _HOTKEY_WINDOWS[self._hwnd] = self
        return True

    def install(self) -> None:
        """创建隐藏消息窗口；重复调用无副作用。"""
        if self._installed:
            return
        self._installed = self._ensure_window()

    def register(self, text: str, callback: Callable[[], None]) -> bool:
        """注册一个热键；失败时返回 False。"""
        parsed = parse_hotkey(text)
        if parsed is None:
            return False
        if not self._installed and not self._ensure_window():
            self._failed.append(text)
            return False
        hotkey_id = self._next_id
        if not _USER32.RegisterHotKey(
            self._hwnd, hotkey_id, parsed.modifiers, parsed.virtual_key
        ):
            self._failed.append(text)
            return False
        self._callbacks[hotkey_id] = callback
        self._next_id += 1
        return True

    def unregister_all(self) -> None:
        """注销全部热键。"""
        for hotkey_id in list(self._callbacks):
            _USER32.UnregisterHotKey(self._hwnd, hotkey_id)
        self._callbacks.clear()
        self._failed.clear()

    def shutdown(self) -> None:
        """注销热键并释放隐藏窗口。"""
        self.unregister_all()
        if self._hwnd is not None:
            _HOTKEY_WINDOWS.pop(self._hwnd, None)
            _USER32.DestroyWindow(self._hwnd)
            self._hwnd = None
        self._installed = False
