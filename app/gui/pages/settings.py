"""设置页：界面主题、关闭行为、运行日志等级与数据清理。"""

from PySide6.QtCore import QSignalBlocker, Qt, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    FluentIcon as FIF,
    PushButton,
    SwitchButton,
    Theme,
    qconfig,
)

from ..components import SectionCard, page_heading
from ..models import LOG_LEVELS, normalize_log_level
from .common import Page


class SettingsPage(Page):
    """集中放置全局开关，所有改动通过信号交给主窗口处理。"""

    themeRequested = Signal(object)
    closeBehaviorRequested = Signal(str)
    logLevelRequested = Signal(str)
    clearDataRequested = Signal()

    def __init__(self, log_store, close_behavior, parent=None):
        super().__init__("settings", parent)
        self.log_store = log_store
        page_heading(self.vbox, "设置")
        row = QHBoxLayout()
        row.addWidget(BodyLabel("界面主题", self))
        row.addStretch()
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
        row.addWidget(self.theme_box)
        settings_card = SectionCard(self, spacing=18)
        settings_card.body.addLayout(row)

        close_row = QHBoxLayout()
        close_row.addWidget(BodyLabel("关闭时最小化到托盘", self))
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

        log_row = QHBoxLayout()
        log_row.addWidget(BodyLabel("运行日志等级", self))
        log_row.addStretch()
        self.log_level_box = ComboBox(self)
        self.log_level_box.addItems([str(level) for level in LOG_LEVELS])
        self.log_level_box.setCurrentIndex(
            LOG_LEVELS.index(self.log_store.minimum_level)
        )
        self.log_level_box.setMinimumWidth(160)
        self.log_level_box.currentIndexChanged.connect(self._select_log_level)
        log_row.addWidget(self.log_level_box)
        settings_card.body.addLayout(log_row)
        self.vbox.addWidget(settings_card)
        self.log_store.levelChanged.connect(self._log_level_changed)

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

    def _select_close_behavior(self, checked):
        self.closeBehaviorRequested.emit("tray" if checked else "quit")

    def set_close_behavior(self, behavior):
        """按当前配置同步关闭行为开关，期间屏蔽开关自身的信号。

        Args:
            behavior: ``tray`` 表示最小化到托盘，其他值表示直接退出。
        """
        with QSignalBlocker(self.close_behavior_switch):
            self.close_behavior_switch.setChecked(behavior == "tray")

    def _select_log_level(self, index):
        if 0 <= index < len(LOG_LEVELS):
            self.logLevelRequested.emit(str(LOG_LEVELS[index]))

    @Slot(str)
    def _log_level_changed(self, level):
        index = LOG_LEVELS.index(normalize_log_level(level))
        with QSignalBlocker(self.log_level_box):
            self.log_level_box.setCurrentIndex(index)
