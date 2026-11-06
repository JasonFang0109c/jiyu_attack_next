"""设置页：界面主题、窗口材质、关闭行为与数据清理。"""

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    PushButton,
    SwitchButton,
    Theme,
    getFont,
    qconfig,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from ..components import SectionCard, page_heading
from ..models import (
    WINDOW_MATERIAL_LABELS,
    WINDOW_MATERIALS,
    normalize_window_material,
    window_material_available,
)
from .common import Page

# 设置项标签用 13 像素：比卡片标题（BodyLabel 默认 14）小一档，
# 又比关于页的 CaptionLabel（12）大一点，保证中文小字仍清晰。
SETTING_LABEL_PIXELS = 13


def setting_label(text, parent):
    """返回设置行左侧的标签，字号小于卡片标题。"""
    label = BodyLabel(text, parent)
    label.setFont(getFont(SETTING_LABEL_PIXELS))
    return label


class ThemeCard(SectionCard):
    """界面主题卡片：标题行加颜色模式、窗口材质两项设置。

    样式对齐关于页的仓库信息卡片，标题与设置行之间留出固定间距。
    """

    HEADING_GAP = 6

    def __init__(self, parent=None):
        # 行间距比普通卡片大一些，把颜色模式与窗口材质分成两组。
        super().__init__(parent, spacing=16, margins=(18, 12, 18, 12))
        self.setObjectName("settingsThemeCard")
        self.heading = BodyLabel("界面主题", self)
        self.body.addWidget(self.heading)
        self.body.addSpacing(self.HEADING_GAP)


class SettingsPage(Page):
    """集中放置全局开关，所有改动通过信号交给主窗口处理。"""

    themeRequested = Signal(object)
    materialRequested = Signal(str)
    closeBehaviorRequested = Signal(str)
    clearDataRequested = Signal()

    def __init__(self, log_store, close_behavior, window_material, parent=None):
        super().__init__("settings", parent)
        self.log_store = log_store
        page_heading(self.vbox, "设置")

        self.theme_card = ThemeCard(self)
        theme_card = self.theme_card
        theme_row = QHBoxLayout()
        theme_row.addWidget(setting_label("颜色模式", self))
        theme_row.addStretch()
        self.theme_box = ComboBox(self)
        self.theme_box.addItems(["浅色", "深色", "跟随系统"])
        themes = [Theme.LIGHT, Theme.DARK, Theme.AUTO]
        # 配置被手改成未知值时退回“跟随系统”，避免设置页构造失败。
        current = qconfig.themeMode.value
        self.theme_box.setCurrentIndex(
            themes.index(current) if current in themes else 2
        )
        self.theme_box.setMinimumWidth(180)
        self.theme_box.currentIndexChanged.connect(self._select_theme)
        theme_row.addWidget(self.theme_box)
        theme_card.body.addLayout(theme_row)

        material_row = QHBoxLayout()
        material_row.addWidget(setting_label("窗口材质", self))
        material_row.addStretch()
        self.material_box = ComboBox(self)
        for material in WINDOW_MATERIALS:
            self.material_box.addItem(
                WINDOW_MATERIAL_LABELS[material], userData=material
            )
        current_material = normalize_window_material(window_material)
        # 系统不支持时保留选项但置灰，让用户知道该项依赖系统能力。
        self.supported_materials = {
            material: window_material_available(material)
            for material in WINDOW_MATERIALS
        }
        for index, material in enumerate(WINDOW_MATERIALS):
            self.material_box.setItemEnabled(index, self.supported_materials[material])
        self.material_box.setCurrentIndex(WINDOW_MATERIALS.index(current_material))
        self.material_box.setMinimumWidth(180)
        self.material_box.setToolTip(
            "Mica 由系统按桌面壁纸采样；Acrylic 实时模糊窗口下方的内容，包括其他应用窗口"
        )
        self.material_box.currentIndexChanged.connect(self._select_material)
        material_row.addWidget(self.material_box)
        theme_card.body.addLayout(material_row)
        self.vbox.addWidget(theme_card)

        settings_card = SectionCard(self, spacing=16)
        settings_card.setObjectName("settingsBehaviorCard")
        close_row = QHBoxLayout()
        close_row.addWidget(setting_label("关闭时最小化到托盘", self))
        close_row.addStretch()
        self.close_behavior_switch = SwitchButton(self)
        self.close_behavior_switch.setAccessibleName("关闭时最小化到系统托盘")
        self.close_behavior_switch.setToolTip(
            "开启：关闭窗口后保留在系统托盘；关闭：直接退出应用"
        )
        self.close_behavior_switch.setOnText("")
        self.close_behavior_switch.setOffText("")
        self.close_behavior_switch.setSpacing(0)
        self.close_behavior_switch.label.hide()
        self.close_behavior_switch.setChecked(close_behavior == "tray")
        self.close_behavior_switch.checkedChanged.connect(self._select_close_behavior)
        close_row.addWidget(self.close_behavior_switch)
        settings_card.body.addLayout(close_row)

        self.vbox.addWidget(settings_card)

        self.data_card = SectionCard(self, spacing=12, margins=(18, 12, 18, 12))
        data_card = self.data_card
        data_card.setObjectName("settingsDataCard")
        data_row = QHBoxLayout()
        data_copy = QVBoxLayout()
        data_copy.setSpacing(4)
        data_copy.addWidget(BodyLabel("本地数据", data_card))
        data_hint = CaptionLabel(
            "删除设备备注、界面设置与运行日志所在的 JiYuAttackNextData 文件夹。",
            data_card,
        )
        data_hint.setWordWrap(True)
        data_copy.addWidget(data_hint)
        data_row.addLayout(data_copy, 1)
        self.clear_data_button = PushButton("清除数据", data_card)
        self.clear_data_button.setIcon(FIF.DELETE)
        self.clear_data_button.clicked.connect(
            lambda checked=False: self.clearDataRequested.emit()
        )
        data_row.addWidget(self.clear_data_button, 0, Qt.AlignVCenter)
        data_card.body.addLayout(data_row)
        self.vbox.addWidget(data_card)

        self.vbox.addStretch()

    def _select_theme(self, index):
        self.themeRequested.emit([Theme.LIGHT, Theme.DARK, Theme.AUTO][index])

    def _select_material(self, index):
        if 0 <= index < len(WINDOW_MATERIALS):
            self.materialRequested.emit(WINDOW_MATERIALS[index])

    def set_window_material(self, material):
        """按当前配置同步窗口材质下拉框，期间屏蔽下拉框自身的信号。

        Args:
            material: 当前生效的材质标识。
        """
        material = normalize_window_material(material)
        index = WINDOW_MATERIALS.index(material)
        if self.material_box.currentIndex() == index:
            return
        with QSignalBlocker(self.material_box):
            self.material_box.setCurrentIndex(index)

    def _select_close_behavior(self, checked):
        self.closeBehaviorRequested.emit("tray" if checked else "quit")

    def set_close_behavior(self, behavior):
        """按当前配置同步关闭行为开关，期间屏蔽开关自身的信号。

        Args:
            behavior: ``tray`` 表示最小化到托盘，其他值表示直接退出。
        """
        with QSignalBlocker(self.close_behavior_switch):
            self.close_behavior_switch.setChecked(behavior == "tray")
