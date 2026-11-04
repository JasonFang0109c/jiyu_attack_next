"""窗口材质：调用组件自带的 DWM 效果实现云母与亚克力。

云母（Mica）由系统按桌面壁纸采样，窗口下方压着别的应用时背景不会变化；
亚克力（Acrylic）由 DWM 实时模糊窗口下方的内容，包括其他应用窗口。

两个效果都由 ``PySide6-Fluent-Widgets`` 依赖的 ``qframelesswindow`` 提供，
这里只负责按项目需要拼装调用顺序，不再自己声明 Win32 结构体。亚克力需要
三步配合才能透出下层内容：先 ``DwmEnableBlurBehindWindow`` 打开客户区模糊，
再用 ``DwmExtendFrameIntoClientArea`` 把客户区扩展成玻璃区域，最后用
``setAcrylicEffect`` 写入强调色策略，并清掉先前由云母设下的系统 backdrop，
否则旧的 backdrop 会盖住亚克力。
"""

import sys
from ctypes import byref, c_int

if sys.platform == "win32":
    from qframelesswindow.windows.c_structures import DWMWINDOWATTRIBUTE, MARGINS
else:  # pragma: no cover - 其他系统没有 DWM 结构体
    DWMWINDOWATTRIBUTE = None
    MARGINS = None

TRANSPARENT_MARGINS = 16777215
SYSTEMBACKDROP_NONE = 0
LIGHT_TINT = (0xF5, 0xF6, 0xF8)
DARK_TINT = (0x20, 0x20, 0x20)
ACRYLIC_ALPHA = 0xA0


def acrylic_color(dark_theme, alpha=ACRYLIC_ALPHA):
    """返回组件 ``setAcrylicEffect`` 需要的染色值。

    Args:
        dark_theme: ``True`` 表示深色主题。
        alpha: 染色不透明度，越大越不透明。默认值与库的默认染色一致。

    Returns:
        str: 形如 ``RRGGBBAA`` 的十六进制字符串。
    """
    red, green, blue = DARK_TINT if dark_theme else LIGHT_TINT
    return "%02X%02X%02X%02X" % (red, green, blue, alpha)


def _effect(window):
    """返回窗口自带的 DWM 效果对象与句柄，不可用时返回 ``None``。"""
    if sys.platform != "win32":
        return None
    effect = getattr(window, "windowEffect", None)
    if effect is None:
        return None
    try:
        handle = int(window.winId())
    except (AttributeError, RuntimeError, TypeError):
        return None
    if not handle:
        return None
    return effect, handle


def apply_acrylic(window, dark_theme=False):
    """给窗口启用亚克力实时模糊。

    Args:
        window: 任何带 ``windowEffect`` 的窗口。
        dark_theme: ``True`` 表示深色主题，决定染色与标题栏明暗。

    Returns:
        bool: 系统不是 Windows 或调用失败时为 ``False``。
    """
    target = _effect(window)
    if target is None:
        return False
    effect, handle = target
    try:
        effect.enableBlurBehindWindow(handle)
        margins = MARGINS(TRANSPARENT_MARGINS, TRANSPARENT_MARGINS, 0, 0)
        effect.DwmExtendFrameIntoClientArea(handle, byref(margins))
        effect.setAcrylicEffect(handle, acrylic_color(dark_theme))
        effect.DwmSetWindowAttribute(
            handle,
            DWMWINDOWATTRIBUTE.DWMWA_SYSTEMBACKDROP_TYPE.value,
            byref(c_int(SYSTEMBACKDROP_NONE)),
            4,
        )
    except (OSError, ValueError, AttributeError):
        return False
    return True


def apply_mica(window, dark_theme=False):
    """给窗口启用系统云母。

    Args:
        window: 任何带 ``windowEffect`` 的窗口。
        dark_theme: ``True`` 表示深色主题。

    Returns:
        bool: 系统不是 Windows 或调用失败时为 ``False``。
    """
    target = _effect(window)
    if target is None:
        return False
    effect, handle = target
    try:
        effect.disableBlurBehindWindow(handle)
        effect.setMicaEffect(handle, dark_theme)
    except (OSError, ValueError, AttributeError):
        return False
    return True


def clear_material(window):
    """关闭窗口背景材质，窗口恢复为不透明。

    Args:
        window: 任何带 ``windowEffect`` 的窗口。
    """
    target = _effect(window)
    if target is None:
        return
    effect, handle = target
    try:
        effect.disableBlurBehindWindow(handle)
        effect.removeBackgroundEffect(handle)
        effect.DwmSetWindowAttribute(
            handle,
            DWMWINDOWATTRIBUTE.DWMWA_SYSTEMBACKDROP_TYPE.value,
            byref(c_int(SYSTEMBACKDROP_NONE)),
            4,
        )
        effect.DwmExtendFrameIntoClientArea(handle, byref(MARGINS(0, 0, 0, 0)))
    except (OSError, ValueError, AttributeError):
        pass
