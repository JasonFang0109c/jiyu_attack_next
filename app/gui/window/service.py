"""WindowService 的界面协调逻辑。"""

import base64

from PySide6.QtCore import (
    QByteArray,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    isDarkTheme,
    setTheme,
)

from app.features.settings.data import (
    CLOSE_BEHAVIOR_SETTINGS_KEY,
    DEFAULT_CLOSE_BEHAVIOR,
    FIRST_CLOSE_PROMPT_SETTINGS_KEY,
    MATERIAL_ACRYLIC,
    MATERIAL_SOLID,
    MICA_SETTINGS_KEY,
    WINDOW_GEOMETRY_SETTINGS_KEY,
    WINDOW_MATERIAL_LABELS,
    WINDOW_MATERIAL_SETTINGS_KEY,
    WINDOW_MATERIALS,
    normalize_close_behavior,
    normalize_switch,
    normalize_window_material,
    window_material_available,
)
from app.gui.theme import (
    window_background,
)
from app.gui.window_effect import apply_acrylic, apply_mica, clear_material
from app.shared.settings import STATUS_NO_ERROR


class WindowService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window

    def _load_close_behavior(self):
        """读取关闭行为配置，配置损坏时回落默认值并记录原因。"""
        window = self.window
        window._close_behavior_error = ""
        raw = window.settings.value(CLOSE_BEHAVIOR_SETTINGS_KEY, DEFAULT_CLOSE_BEHAVIOR)
        try:
            return normalize_close_behavior(raw)
        except ValueError:
            window._close_behavior_error = "关闭窗口行为配置无效，已恢复默认托盘模式"
            return DEFAULT_CLOSE_BEHAVIOR

    def _load_first_close_prompt_shown(self):
        window = self.window
        value = window.settings.value(FIRST_CLOSE_PROMPT_SETTINGS_KEY, False)
        if isinstance(value, str):
            return value.strip().casefold() in ("1", "true", "yes", "on")
        return bool(value)

    def _load_window_material(self):
        """读取窗口材质，配置缺失时用旧版背景模糊开关换算。"""
        window = self.window
        raw = window.settings.value(WINDOW_MATERIAL_SETTINGS_KEY, None)
        legacy = normalize_switch(window.settings.value(MICA_SETTINGS_KEY, None), None)
        return normalize_window_material(raw, legacy)

    def apply_window_material(self, material):
        """按材质切换窗口背景效果。

        Args:
            material: ``WINDOW_MATERIALS`` 中的材质标识。

        Note:
            云母与亚克力都调用组件自带的 ``windowEffect``：云母走
            ``setMicaEffect``，亚克力走 ``setAcrylicEffect`` 配合窗口玻璃区域。
            纯色则彻底清掉系统效果并把背景刷回不透明色。
        """
        window = self.window
        material = normalize_window_material(material)
        dark_theme = isDarkTheme()
        # 主题切换会启动一段底色动画，动画终点按切换前的材质计算，可能在
        # 这里设好底色之后又把窗口刷回透明，必须先停掉再改色。
        window.backgroundColorAni.stop()
        # 云母与亚克力互斥，先统一关掉库的云母开关，避免系统 backdrop 叠在亚克力上。
        window.blur_enabled = material != MATERIAL_SOLID
        window.setMicaEffectEnabled(False)
        if material == MATERIAL_SOLID:
            clear_material(window)
            # 库关闭材质后不会恢复底色，这里自己刷回不透明，否则窗口全透明。
            window.setBackgroundColor(window_background(dark_theme))
            return
        # 库只在部分系统上把背景刷成透明，自己刷一遍，否则材质被底色盖住。
        window.setBackgroundColor(QColor(0, 0, 0, 0))
        if material == MATERIAL_ACRYLIC:
            apply_acrylic(window, dark_theme)
        else:
            apply_mica(window, dark_theme)

    def _restore_window_geometry(self):
        """恢复上次退出时的窗口位置与大小，越界时夹回当前屏幕。"""
        window = self.window
        raw = window.settings.value(WINDOW_GEOMETRY_SETTINGS_KEY, "")
        if not isinstance(raw, str) or not raw.strip():
            window.logs.debug("应用", "没有可恢复的窗口位置，使用默认大小")
            return
        try:
            stored = QByteArray(base64.b64decode(raw.encode("ascii"), validate=True))
        except (ValueError, UnicodeEncodeError):
            window.logs.warning("设置", "窗口位置记录已损坏，使用默认大小")
            return
        if not window.restoreGeometry(stored):
            window.logs.warning("设置", "窗口位置恢复失败，使用默认大小")
            return
        window._clamp_to_screen()
        window.logs.debug(
            "应用",
            "已恢复窗口位置",
            "位置：%s；大小：%sx%s"
            % (window.pos().toTuple(), window.width(), window.height()),
        )

    def _clamp_to_screen(self):
        """把窗口夹回当前屏幕可用区域，避免显示器变化后窗口跑到屏幕外。"""
        window = self.window
        screen = window.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        bounds = screen.availableGeometry()
        frame = window.frameGeometry()
        left = max(bounds.left(), min(frame.left(), bounds.right() - frame.width() + 1))
        top = max(bounds.top(), min(frame.top(), bounds.bottom() - frame.height() + 1))
        if (left, top) != (frame.left(), frame.top()):
            window.move(left, top)

    def _center_on_screen(self):
        """把窗口放到当前屏幕中央，用于恢复默认布局。"""
        window = self.window
        screen = window.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        bounds = screen.availableGeometry()
        window.move(
            bounds.center().x() - window.width() // 2,
            bounds.center().y() - window.height() // 2,
        )

    def _save_window_geometry(self):
        """把当前窗口位置与大小写入设置文件。"""
        window = self.window
        # 最小化状态下的几何是任务栏图标位置，写进去会让下次启动出现在角落。
        if window.isMinimized():
            return
        window.settings.set_value(
            WINDOW_GEOMETRY_SETTINGS_KEY,
            base64.b64encode(bytes(window.saveGeometry())).decode("ascii"),
        )
        window.settings.sync()
        if window.settings.status() != STATUS_NO_ERROR:
            window.logs.warning(
                "设置",
                "窗口位置保存失败",
                "设置文件：%s；状态：%s"
                % (window.settings.file_name(), window.settings.status()),
            )

    def set_theme(self, theme):
        """切换界面主题；主题不写入配置文件，下次启动仍用浅色。

        Args:
            theme: ``Theme`` 枚举值，来自设置页的下拉框。
        """
        window = self.window
        setTheme(theme, save=False)
        window.logs.info("应用", "界面主题已切换", "主题：%s" % theme)

    def set_window_material(self, material):
        """保存窗口材质并立即生效，写盘失败时回滚到原材质。

        Args:
            material: 设置页下拉框选中的材质标识。
        """
        window = self.window
        target = normalize_window_material(material)
        if target not in WINDOW_MATERIALS:
            return
        if not window_material_available(target):
            window.logs.warning("设置", "当前系统不支持该窗口材质，已忽略改动")
            window.pages["settings"].set_window_material(window.window_material)
            return
        previous = window.window_material
        window.window_material = target
        window.apply_window_material(target)
        window.settings.set_value(WINDOW_MATERIAL_SETTINGS_KEY, target)
        window.settings.sync()
        if window.settings.status() != STATUS_NO_ERROR:
            window.logs.error(
                "设置",
                "窗口材质保存失败",
                "设置文件：%s；状态：%s"
                % (window.settings.file_name(), window.settings.status()),
            )
            window.window_material = previous
            window.apply_window_material(previous)
            window.pages["settings"].set_window_material(previous)
            window._notify("设置保存失败", "无法写入设置文件", "错误")
            return
        window.logs.info(
            "设置",
            "窗口材质已更新",
            "材质：%s" % WINDOW_MATERIAL_LABELS[target],
        )

    def set_close_behavior(self, behavior):
        """保存关闭窗口行为，写盘失败时回滚到原行为。

        Args:
            behavior: 待保存的行为值，非法值会被拒绝并提示用户。
        """
        window = self.window
        try:
            normalized = normalize_close_behavior(behavior)
        except ValueError as error:
            window.logs.error(
                "设置", "关闭窗口行为保存失败", "输入：%s；异常：%s" % (behavior, error)
            )
            window._notify("设置保存失败", str(error), "错误")
            return
        previous = window.close_behavior
        window.close_behavior = normalized
        window.settings.set_value(CLOSE_BEHAVIOR_SETTINGS_KEY, normalized)
        window.settings.sync()
        if window.settings.status() != STATUS_NO_ERROR:
            window.logs.error(
                "设置",
                "关闭窗口行为保存失败",
                "设置文件：%s；状态：%s"
                % (window.settings.file_name(), window.settings.status()),
            )
            window.close_behavior = previous
            window._notify("设置保存失败", "无法写入设置文件", "错误")
            return
        window.logs.info(
            "设置",
            "关闭窗口行为已更新",
            "原行为：%s；新行为：%s" % (previous, normalized),
        )
