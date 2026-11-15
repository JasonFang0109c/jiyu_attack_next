"""设备操作页：重启、关机、注销目标电脑。"""

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QTableWidgetItem
from qfluentwidgets import BodyLabel, CaptionLabel, SegmentedWidget
from qfluentwidgets import FluentIcon as FIF

import app.system.net.targets as system_net_targets
from app.gui.widgets.page import NetworkPage, table_widget

# 操作代码、显示名与图标：代码沿用发送层已有的 r/s/l。
DEVICE_ACTIONS = (
    ("r", "重启", FIF.SYNC),
    ("s", "关机", FIF.POWER_BUTTON),
    ("l", "注销", FIF.RETURN),
)

POWER_HINT = "重启与关机会发出固定的重启、关机报文；注销改用远程命令执行 shutdown /l。"


class DevicePage(NetworkPage):
    """选择设备操作，并预览当前目标会展开成哪些 IP。"""

    def __init__(self, state, parent=None):
        super().__init__("device", "设备操作", state, "执行重启", parent)
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(BodyLabel("操作", self.content_card))
        # 分段选择器与 WinUI 的 SelectorBar 一致，三项占一行、当前项高亮，
        # 比三个单选按钮更容易一眼看出现在选的是哪一个。
        self.action_selector = SegmentedWidget(self.content_card)
        for key, text, icon in DEVICE_ACTIONS:
            self.action_selector.addItem(key, text, icon=icon)
        self.action_selector.setFixedHeight(36)
        self.action_selector.setMinimumWidth(300)
        row.addWidget(self.action_selector)
        row.addStretch()
        self.body.addLayout(row)

        self.power_hint = CaptionLabel(POWER_HINT, self.content_card)
        self.power_hint.setWordWrap(True)
        self.body.addWidget(self.power_hint)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(8)
        self.preview_title = BodyLabel("目标预览", self.content_card)
        preview_row.addWidget(self.preview_title)
        self.preview_count = CaptionLabel("", self.content_card)
        preview_row.addWidget(self.preview_count)
        preview_row.addStretch()
        self.body.addLayout(preview_row)

        self.preview = table_widget(["目标地址", "UDP 端口"], self.content_card)
        self.preview.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        # 只给初始宽度，列宽留给用户拖动，和其它表格一致。
        self.preview.setColumnWidth(0, 360)
        self.preview.setColumnWidth(1, 160)
        self.body.addWidget(self.preview, 1)

        state.changed.connect(self._on_target_changed)
        self.action_selector.currentItemChanged.connect(self._update_action)
        self.action_selector.setCurrentItem("r")
        self.update_preview()

    def action(self):
        """返回当前选中的设备操作代码（r/s/l）。"""
        return self.action_selector.currentRouteKey() or "r"

    def set_action(self, key):
        """切换当前操作，供“设为当前目标”一类外部入口复用。"""
        self.action_selector.setCurrentItem(key)

    @Slot(str)
    def _update_action(self, key=None):
        """切换后同步发送按钮文案。"""
        key = key or self.action()
        labels = {"r": "执行重启", "s": "执行关机", "l": "执行注销"}
        self.footer.send_button.setText(labels[key])

    @Slot(str, object)
    def _on_target_changed(self, name, value):
        if name == "target":
            self.update_preview()
        elif name == "port":
            self._update_preview_ports()

    def _update_preview_ports(self):
        """端口变化时只改端口列，避免重建整张预览表。"""
        port = str(self.targets.state.values["port"])
        for row in range(self.preview.rowCount()):
            item = self.preview.item(row, 1)
            if item is not None:
                item.setText(port)

    def update_preview(self):
        """按当前目标重建预览表；地址非法时显示为空。"""
        target = self.targets.state.values["target"].strip()
        matched = self.targets.state.aliases.match(target)
        try:
            hosts = (
                system_net_targets.get_ip(self.targets.state.resolve_target(target))
                if target
                else []
            )
        except ValueError:
            hosts = []
        self.preview.setRowCount(len(hosts))
        for row, host in enumerate(hosts):
            self.preview.setItem(row, 0, QTableWidgetItem(host))
            self.preview.setItem(
                row, 1, QTableWidgetItem(str(self.targets.state.values["port"]))
            )
            self.preview.setRowHeight(row, 36)
        self.preview_title.setText("目标预览")
        alias_text = "备注「%s」" % matched[0] if matched else ""
        parts = ["%d 个目标" % len(hosts)]
        if alias_text:
            parts.append(alias_text)
        self.preview_count.setText("、".join(parts))

    def set_busy(self, busy, cancellable=False, queueable=False):
        """在基类忙碌状态之外锁定操作选择条。"""
        super().set_busy(busy, cancellable, queueable)
        self.action_selector.setEnabled(not busy)
