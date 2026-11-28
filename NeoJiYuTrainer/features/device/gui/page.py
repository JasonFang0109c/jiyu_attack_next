"""设备操作页：重启、关机、注销或蓝屏目标电脑。"""

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QTableWidgetItem
from qfluentwidgets import BodyLabel, CaptionLabel
from qfluentwidgets import FluentIcon as FIF

import NeoJiYuTrainer.system.net.targets as system_net_targets
from NeoJiYuTrainer.gui.widgets.common import FluentComboBox
from NeoJiYuTrainer.gui.widgets.page import NetworkPage, table_widget

# 操作代码、显示名与图标：代码沿用发送层已有的 r/s/l，蓝屏为 b。
DEVICE_ACTIONS = (
    ("r", "重启", FIF.SYNC),
    ("s", "关机", FIF.POWER_BUTTON),
    ("l", "注销", FIF.RETURN),
    ("b", "蓝屏", FIF.CLOSE),
)


class DevicePage(NetworkPage):
    """选择设备操作，并预览当前目标会展开成哪些 IP。"""

    def __init__(self, state, parent=None):
        super().__init__("device", "设备操作", state, "执行重启", parent)
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(BodyLabel("操作", self.content_card))
        # 三项操作是互斥的单选，下拉框与设置页的选择器同款，占位也比
        # 分段选择器小，页面留出的高度都让给下面的预览表。
        self.action_box = FluentComboBox(self.content_card)
        for key, text, icon in DEVICE_ACTIONS:
            self.action_box.addItem(text, icon=icon, userData=key)
        self.action_box.setMinimumWidth(180)
        row.addWidget(self.action_box)
        row.addStretch()
        self.body.addLayout(row)

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
        self.action_box.currentIndexChanged.connect(self._update_action)
        self.update_preview()

    def action(self):
        """返回当前选中的设备操作代码（r/s/l）。"""
        return self.action_box.currentData() or "r"

    def set_action(self, key):
        """切换当前操作，供“设为当前目标”一类外部入口复用。"""
        index = self.action_box.findData(key)
        if index >= 0:
            self.action_box.setCurrentIndex(index)

    @Slot(int)
    def _update_action(self, index=0):
        """切换后同步发送按钮文案；``index`` 由下拉框信号传入，不参与判断。"""
        labels = {
            "r": "执行重启",
            "s": "执行关机",
            "l": "执行注销",
            "b": "执行蓝屏",
        }
        self.footer.send_button.setText(labels[self.action()])

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
        """在基类忙碌状态之外锁定操作下拉框。"""
        super().set_busy(busy, cancellable, queueable)
        self.action_box.setEnabled(not busy)
