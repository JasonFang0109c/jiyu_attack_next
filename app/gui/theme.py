"""界面视觉令牌：圆角、卡片填充与描边统一取 WinUI 3 的主题资源。

数值来自 Windows 11 的 WinUI 3 主题资源，改动时请一并更新
``docs/dev/STYLE.md`` 的对照表：

- 圆角：``ControlCornerRadius`` 4 像素用于控件与内容面，
  ``OverlayCornerRadius`` 8 像素用于对话框、浮出层这类覆盖在内容之上的容器。
- 卡片填充：``CardBackgroundFillColorDefault``，浅色 ``#B3FFFFFF``、
  深色 ``#0DFFFFFF``。
- 卡片描边：``CardStrokeColorDefault``，浅色 ``#0F000000``、
  深色 ``#19000000``。
- 窗口底色：``SolidBackgroundFillColorBase``，浅色 ``#F3F3F3``、
  深色 ``#202020``。
- 状态提示：正常、提醒、错误与中性四种语气色，深浅主题各取一档。
- 强调色：默认蓝色 ``#0067C0``、橙色 ``#F98524``，也可以跟随 Windows
  设置里的强调色；跟随系统时读注册表里的 ``AccentColorMenu``。
"""

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor
from qfluentwidgets import isDarkTheme

from app.features.settings.data import ACCENT_BLUE, ACCENT_ORANGE, ACCENT_SYSTEM

CONTROL_CORNER_RADIUS = 4
OVERLAY_CORNER_RADIUS = 8

CARD_FILL_LIGHT = "#B3FFFFFF"
CARD_FILL_DARK = "#0DFFFFFF"
CARD_STROKE_LIGHT = "#0F000000"
CARD_STROKE_DARK = "#19000000"

WINDOW_BACKGROUND_LIGHT = "#f3f3f3"
WINDOW_BACKGROUND_DARK = "#202020"

# 状态提示的语义色取自 WinUI 的系统色板，深色主题各换一档更亮的同色系。
TONE_COLORS = {
    "ok": ("#107C10", "#6CCB5F"),
    "warning": ("#9D5D00", "#FCE100"),
    "error": ("#C42B1C", "#FF99A4"),
    "neutral": ("#605E5C", "#A0A0A0"),
}

# 滚动条滑块用低透明度的黑白覆盖色，浅色主题压黑、深色主题提白。
SCROLL_HANDLE_LIGHT = (0, 0, 0, 70)
SCROLL_HANDLE_DARK = (255, 255, 255, 60)
SCROLL_GROOVE_LIGHT = (0, 0, 0, 0)
SCROLL_GROOVE_DARK = (255, 255, 255, 0)

# 强调色：蓝色沿用项目原来的默认值，橙色取 WinUI 状态橙的浅色档。
ACCENT_COLORS = {
    ACCENT_BLUE: "#0067c0",
    ACCENT_ORANGE: "#f98524",
}

SYSTEM_ACCENT_FALLBACK = "#0078d4"

# 强调色在注册表里按 ABGR 存放，先读“设置里选的强调色”，再退回 DWM 的窗口色。
SYSTEM_ACCENT_REGISTRY = (
    (
        "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Accent",
        "AccentColorMenu",
    ),
    ("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\DWM", "AccentColor"),
)


def system_accent_color():
    """返回 Windows 设置里的强调色。

    强调色以 ``0xAABBGGRR`` 存在注册表里，按 ABGR 取出 RGB；注册表读不到
    （非 Windows 或键被清理）时退回 Windows 11 的系统默认蓝。

    Returns:
        QColor: 系统强调色。
    """
    for path, name in SYSTEM_ACCENT_REGISTRY:
        store = QSettings(path, QSettings.Format.NativeFormat)
        value = store.value(name)
        if isinstance(value, int) and value & 0xFFFFFF:
            return QColor(value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF)
    return QColor(SYSTEM_ACCENT_FALLBACK)


def accent_color(accent):
    """把设置页选中的主题色换算成颜色。

    Args:
        accent: ``system``、``blue`` 或 ``orange``；未知值按蓝色处理。

    Returns:
        QColor: 该选项对应的强调色。
    """
    if accent == ACCENT_SYSTEM:
        return system_accent_color()
    return QColor(ACCENT_COLORS.get(accent, ACCENT_COLORS[ACCENT_BLUE]))


def card_fill():
    """返回当前主题下的卡片填充色。"""
    return QColor(CARD_FILL_DARK if isDarkTheme() else CARD_FILL_LIGHT)


def card_stroke():
    """返回当前主题下的卡片描边色。"""
    return QColor(CARD_STROKE_DARK if isDarkTheme() else CARD_STROKE_LIGHT)


def window_background(dark=None):
    """返回窗口底色；``None`` 表示跟随当前主题。

    Args:
        dark: 指定深色或浅色，省略时按当前主题判断。

    Returns:
        QColor: 对应主题的窗口底色。
    """
    if dark is None:
        dark = isDarkTheme()
    return QColor(WINDOW_BACKGROUND_DARK if dark else WINDOW_BACKGROUND_LIGHT)


def tone_color(tone):
    """返回状态提示文字的颜色。

    Args:
        tone: ``ok``、``warning``、``error`` 或 ``neutral``。

    Returns:
        QColor: 当前主题下的语义色。
    """
    light, dark = TONE_COLORS[tone]
    return QColor(dark if isDarkTheme() else light)


def scroll_colors():
    """返回滚动条的轨道色与滑块色，顺序为浅色、深色两套。

    Returns:
        tuple: ``(groove_light, groove_dark, handle_light, handle_dark)``，
            每项都是 ``QColor``。
    """
    return (
        QColor(*SCROLL_GROOVE_LIGHT),
        QColor(*SCROLL_GROOVE_DARK),
        QColor(*SCROLL_HANDLE_LIGHT),
        QColor(*SCROLL_HANDLE_DARK),
    )
