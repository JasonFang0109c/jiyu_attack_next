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
"""

from PySide6.QtGui import QColor
from qfluentwidgets import isDarkTheme

CONTROL_CORNER_RADIUS = 4
OVERLAY_CORNER_RADIUS = 8

CARD_FILL_LIGHT = "#B3FFFFFF"
CARD_FILL_DARK = "#0DFFFFFF"
CARD_STROKE_LIGHT = "#0F000000"
CARD_STROKE_DARK = "#19000000"

WINDOW_BACKGROUND_LIGHT = "#f3f3f3"
WINDOW_BACKGROUND_DARK = "#202020"


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
