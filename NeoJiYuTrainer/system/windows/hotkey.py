"""桌面全局热键的 Win32 常量与文本解析。"""

from __future__ import annotations

from dataclasses import dataclass

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312

_VK_NAMES = {
    "BACKSPACE": 0x08,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "ESC": 0x1B,
    "SPACE": 0x20,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
}
for _index in range(1, 25):
    _VK_NAMES[f"F{_index}"] = 0x6F + _index
for _index in range(10):
    _VK_NAMES[str(_index)] = 0x30 + _index
for _index in range(26):
    _VK_NAMES[chr(ord("A") + _index)] = 0x41 + _index


@dataclass(frozen=True)
class ParsedHotkey:
    """解析后的热键。"""

    modifiers: int
    virtual_key: int


def parse_hotkey(text: str) -> ParsedHotkey | None:
    """把 ``Ctrl+Alt+H`` 解析为 Win32 修饰键与虚拟键。

    无法识别时返回 None，调用方应视为禁用，而不是抛出异常。
    """
    if not text or not text.strip():
        return None
    modifiers = 0
    key_name = ""
    for token in text.replace(" ", "").split("+"):
        upper = token.upper()
        if upper in ("CTRL", "CONTROL"):
            modifiers |= MOD_CONTROL
        elif upper == "ALT":
            modifiers |= MOD_ALT
        elif upper == "SHIFT":
            modifiers |= MOD_SHIFT
        elif upper in ("WIN", "WINDOWS"):
            modifiers |= MOD_WIN
        elif upper:
            key_name = upper
    if modifiers == 0 or key_name not in _VK_NAMES:
        return None
    return ParsedHotkey(modifiers, _VK_NAMES[key_name])
