"""窗口设置的持久化键、默认值与平台能力规则。"""

import sys

SETTINGS_FILE_NAME = "settings.json"

CLOSE_BEHAVIOR_SETTINGS_KEY = "gui/window/close_behavior"

FIRST_CLOSE_PROMPT_SETTINGS_KEY = "gui/window/first_close_prompt_shown"

WINDOW_GEOMETRY_SETTINGS_KEY = "gui/window/geometry"

NAVIGATION_EXPANDED_SETTINGS_KEY = "gui/window/navigation_expanded"

DEFAULT_NAVIGATION_EXPANDED = False

WINDOW_MATERIAL_SETTINGS_KEY = "gui/window/material"

MICA_SETTINGS_KEY = "gui/window/mica_enabled"

MATERIAL_MICA = "mica"

MATERIAL_ACRYLIC = "acrylic"

MATERIAL_SOLID = "solid"

WINDOW_MATERIALS = (MATERIAL_MICA, MATERIAL_ACRYLIC, MATERIAL_SOLID)

WINDOW_MATERIAL_LABELS = {
    MATERIAL_MICA: "Mica（云母）",
    MATERIAL_ACRYLIC: "Acrylic（亚克力）",
    MATERIAL_SOLID: "纯色（无材质）",
}

DEFAULT_WINDOW_MATERIAL = MATERIAL_MICA

SWITCH_TRUE_VALUES = ("true", "1", "yes", "on")

SWITCH_FALSE_VALUES = ("false", "0", "no", "off")

CLOSE_BEHAVIOR_TRAY = "tray"

CLOSE_BEHAVIOR_QUIT = "quit"

DEFAULT_CLOSE_BEHAVIOR = CLOSE_BEHAVIOR_TRAY

CLOSE_BEHAVIOR_LABELS = {
    CLOSE_BEHAVIOR_TRAY: "保留在系统托盘",
    CLOSE_BEHAVIOR_QUIT: "直接退出",
}


def normalize_close_behavior(value):
    """把设置值转换为受支持的关闭窗口行为。"""
    text = str(value or "").strip()
    aliases = {
        CLOSE_BEHAVIOR_TRAY: CLOSE_BEHAVIOR_TRAY,
        CLOSE_BEHAVIOR_QUIT: CLOSE_BEHAVIOR_QUIT,
        CLOSE_BEHAVIOR_LABELS[CLOSE_BEHAVIOR_TRAY]: CLOSE_BEHAVIOR_TRAY,
        CLOSE_BEHAVIOR_LABELS[CLOSE_BEHAVIOR_QUIT]: CLOSE_BEHAVIOR_QUIT,
    }
    try:
        return aliases[text.casefold()]
    except KeyError as error:
        raise ValueError("关闭窗口行为无效：%s" % text) from error


def normalize_switch(value, default):
    """把设置里的开关值转换为布尔值，无法识别时退回默认值。

    Args:
        value: 从 ``settings.json`` 读出的原始值，可能是布尔、字符串或 ``None``。
        default: 配置缺失或格式非法时使用的默认状态。

    Returns:
        bool: 归一化后的开关状态。
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().casefold()
    if text in SWITCH_TRUE_VALUES:
        return True
    if text in SWITCH_FALSE_VALUES:
        return False
    return default


def _windows_build():
    """返回 Windows 内部版本号，非 Windows 系统返回 0。"""
    if sys.platform != "win32":
        return 0
    try:
        return sys.getwindowsversion().build
    except (AttributeError, ValueError):
        return 0


def mica_available():
    """判断当前系统能否给窗口加上云母材质。

    云母由 DWM 按桌面壁纸采样，只在 Windows 11（build 22000）及以上提供。

    Returns:
        bool: 系统支持云母时为 ``True``。
    """
    return _windows_build() >= 22000


def acrylic_available():
    """判断当前系统能否给窗口加上亚克力材质。

    亚克力由 DWM 实时模糊窗口下方的内容，从 Windows 10 1809（build 17763）
    开始提供，比云母的适用范围更宽。

    Returns:
        bool: 系统支持亚克力时为 ``True``。
    """
    return _windows_build() >= 17763


def window_material_available(material):
    """判断某个窗口材质在当前系统上是否可用。

    Args:
        material: ``WINDOW_MATERIALS`` 中的材质标识。

    Returns:
        bool: 该材质可用时为 ``True``；纯色不依赖系统能力，恒为 ``True``。
    """
    if material == MATERIAL_MICA:
        return mica_available()
    if material == MATERIAL_ACRYLIC:
        return acrylic_available()
    return material == MATERIAL_SOLID


def normalize_window_material(value, legacy_switch=None):
    """把设置值转换为受支持的窗口材质。

    Args:
        value: 从 ``settings.json`` 读出的材质标识或显示名。
        legacy_switch: 旧版“背景模糊”开关状态；只在 ``value`` 缺失时使用，
            ``True`` 视为云母，``False`` 视为纯色。

    Returns:
        str: ``WINDOW_MATERIALS`` 中的材质标识，无法识别时退回默认材质。
    """
    text = str(value or "").strip().casefold()
    for material in WINDOW_MATERIALS:
        if text in (material, WINDOW_MATERIAL_LABELS[material].casefold()):
            return material
    if value is None and legacy_switch is not None:
        return MATERIAL_MICA if legacy_switch else MATERIAL_SOLID
    return DEFAULT_WINDOW_MATERIAL
