"""窗口背景材质：用亚克力实时模糊替代表面云母。

Windows 11 的云母（Mica）由系统按桌面壁纸采样，窗口下方的其他应用不会
被计入，所以拖动窗口或切换下层窗口时背景不会变化。亚克力（Acrylic）由
DWM 实时模糊窗口下方的内容，既能透出壁纸，也能透出下层应用窗口。

启用亚克力需要同时做三件事，缺一不可：

1. ``DwmExtendFrameIntoClientArea`` 把客户区扩展成玻璃区域，否则 DWM 会把
   客户区当成不透明，效果完全不可见；
2. ``SetWindowCompositionAttribute`` 设置 ``ACCENT_ENABLE_ACRYLICBLURBEHIND``；
3. 清掉系统 backdrop（``DWMWA_SYSTEMBACKDROP_TYPE = 0``），否则先前由
   ``setMicaEffect`` 设下的 backdrop 会盖住亚克力。
"""

import sys
from ctypes import POINTER, Structure, byref, c_int, c_size_t, c_uint, pointer, sizeof

ACCENT_DISABLED = 0
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
# 亚克力必须带上这组标志位，否则 DWM 会把区域当作纯色处理，效果看不出来。
ACCENT_FLAGS = 0x20 | 0x40 | 0x80 | 0x100
WCA_ACCENT_POLICY = 19
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38
TRANSPARENT_MARGINS = 16777215


class AccentPolicy(Structure):
    """``ACCENT_POLICY`` 结构体。"""

    _fields_ = [
        ("accent_state", c_int),
        ("accent_flags", c_int),
        ("gradient_color", c_uint),
        ("animation_id", c_int),
    ]


class WindowCompositionAttributeData(Structure):
    """``WINDOWCOMPOSITIONATTRIBDATA`` 结构体。"""

    _fields_ = [
        ("attribute", c_int),
        ("data", POINTER(AccentPolicy)),
        # 结构体里是 SIZE_T，64 位上占 8 字节，用 c_uint 会让布局错位。
        ("size_of_data", c_size_t),
    ]


class Margins(Structure):
    """``MARGINS`` 结构体。"""

    _fields_ = [
        ("left", c_int),
        ("right", c_int),
        ("top", c_int),
        ("bottom", c_int),
    ]


def acrylic_tint(dark_theme, alpha=0xA0):
    """返回亚克力的染色值，格式为 ABGR。

    Args:
        dark_theme: ``True`` 表示深色主题。
        alpha: 染色不透明度，越大越不透明，越小越能看清下层内容。默认值
            与库的 ``setAcrylicEffect`` 一致，能透出下层又保证文字可读。

    Returns:
        int: 可直接写入 ``ACCENT_POLICY`` 的 32 位染色值。
    """
    red, green, blue = (0x20, 0x20, 0x20) if dark_theme else (0xF5, 0xF6, 0xF8)
    return (alpha << 24) | (blue << 16) | (green << 8) | red


_API = None


def _api():
    """返回已声明签名的 user32 与 dwmapi 函数，只加载一次。"""
    global _API
    if _API is not None:
        return _API

    from ctypes import WinDLL, c_bool, c_void_p
    from ctypes.wintypes import DWORD

    user32 = WinDLL("user32")
    dwmapi = WinDLL("dwmapi")

    set_composition = user32.SetWindowCompositionAttribute
    set_composition.restype = c_bool
    set_composition.argtypes = [c_int, POINTER(WindowCompositionAttributeData)]

    extend_frame = dwmapi.DwmExtendFrameIntoClientArea
    extend_frame.restype = c_int
    extend_frame.argtypes = [c_int, POINTER(Margins)]

    set_attribute = dwmapi.DwmSetWindowAttribute
    set_attribute.restype = c_int
    set_attribute.argtypes = [c_int, DWORD, c_void_p, DWORD]

    _API = (set_composition, extend_frame, set_attribute)
    return _API


def _set_attribute(set_attribute, handle, attribute, value):
    """写入一个 32 位 DWM 窗口属性。"""
    data = c_int(value)
    set_attribute(handle, attribute, byref(data), sizeof(data))


def _set_accent(handle, state, gradient_color=0):
    """写入强调色策略，``state`` 为 ``ACCENT_DISABLED`` 时表示关闭。"""
    set_composition, _, _ = _api()
    policy = AccentPolicy(state, ACCENT_FLAGS, gradient_color, 0)
    data = WindowCompositionAttributeData(
        WCA_ACCENT_POLICY, pointer(policy), sizeof(policy)
    )
    set_composition(handle, pointer(data))


def apply_acrylic(handle, dark_theme=False):
    """给窗口启用亚克力实时模糊。

    Args:
        handle: 窗口句柄，通常是 ``int(widget.winId())``。
        dark_theme: ``True`` 表示深色主题，决定染色与标题栏明暗。

    Returns:
        bool: 系统不是 Windows 或调用失败时为 ``False``。
    """
    if sys.platform != "win32":
        return False
    handle = int(handle)
    if not handle:
        return False
    try:
        set_composition, extend_frame, set_attribute = _api()
        # 先扩展玻璃区域，否则客户区被当作不透明，效果看不出来。
        margins = Margins(TRANSPARENT_MARGINS, TRANSPARENT_MARGINS, 0, 0)
        extend_frame(handle, byref(margins))
        # 库的 setMicaEffect 会设下系统 backdrop，它会盖住亚克力，这里先清零。
        _set_attribute(set_attribute, handle, DWMWA_SYSTEMBACKDROP_TYPE, 0)
        _set_accent(handle, ACCENT_ENABLE_ACRYLICBLURBEHIND, acrylic_tint(dark_theme))
        _set_attribute(
            set_attribute, handle, DWMWA_USE_IMMERSIVE_DARK_MODE, int(bool(dark_theme))
        )
    except (OSError, ValueError, AttributeError):
        return False
    return True


def remove_acrylic(handle):
    """关闭窗口背景效果，窗口恢复为不透明。"""
    if sys.platform != "win32":
        return
    handle = int(handle)
    if not handle:
        return
    try:
        _, extend_frame, set_attribute = _api()
        _set_accent(handle, ACCENT_DISABLED)
        _set_attribute(set_attribute, handle, DWMWA_SYSTEMBACKDROP_TYPE, 0)
        # 撤销客户区扩展，否则窗口虽然不模糊，内容仍然是半透明的。
        extend_frame(handle, byref(Margins(0, 0, 0, 0)))
    except (OSError, ValueError, AttributeError):
        pass
