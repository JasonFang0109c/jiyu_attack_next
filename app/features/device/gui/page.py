"""设备操作页：重启、关机、注销目标电脑。"""

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
)
from qfluentwidgets import BodyLabel, RadioButton

import app.system.net.targets as system_net_targets
from app.gui.widgets.page import NetworkPage, table_widget


class DevicePage(NetworkPage):
    """选择设备操作，并预览当前目标会展开成哪些 IP。"""

    def __init__(self, state, parent=None):
        super().__init__("device", "设备操作", state, "执行重启", parent)
        row = QHBoxLayout()
        row.addWidget(BodyLabel("操作", self.content_card))
        self.reboot = RadioButton("重启", self)
        self.shutdown = RadioButton("关机", self)
        self.logoff = RadioButton("注销", self)
        self.group = QButtonGroup(self)
        self.group.addButton(self.reboot)
        self.group.addButton(self.shutdown)
        self.group.addButton(self.logoff)
        self.reboot.setChecked(True)
        for button in (self.reboot, self.shutdown, self.logoff):
            button.toggled.connect(self._update_action)
        row.addSpacing(16)
        row.addWidget(self.reboot)
        row.addSpacing(12)
        row.addWidget(self.shutdown)
        row.addSpacing(12)
        row.addWidget(self.logoff)
        row.addStretch()
        self.body.addLayout(row)

        self.power_hint = BodyLabel(
            "重启与关机会发出固定的重启、关机报文；注销改用远程命令执行 shutdown /l。",
            self.content_card,
        )
        self.body.addWidget(self.power_hint)
        self.preview_title = BodyLabel("目标预览", self.content_card)
        self.body.addWidget(self.preview_title)
        self.preview = table_widget(["目标地址", "UDP 端口"], self)
        self.preview.setSelectionMode(QAbstractItemView.NoSelection)
        self.preview.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.preview.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.preview.setColumnWidth(1, 140)
        self.body.addWidget(self.preview, 1)
        state.changed.connect(self._on_target_changed)
        self.update_preview()

    def _update_action(self):
        """单选切换后同步发送按钮文案。"""
        labels = {"r": "执行重启", "s": "执行关机", "l": "执行注销"}
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
        alias_text = "，备注：%s" % matched[0] if matched else ""
        self.preview_title.setText("目标预览（%d%s）" % (len(hosts), alias_text))

    def action(self):
        """返回当前选中的设备操作代码（r/s/l）。"""
        if self.shutdown.isChecked():
            return "s"
        if self.logoff.isChecked():
            return "l"
        return "r"

    def set_busy(self, busy, cancellable=False, queueable=False):
        """在基类忙碌状态之外锁定三个设备操作按钮。"""
        super().set_busy(busy, cancellable, queueable)
        for button in (self.reboot, self.shutdown, self.logoff):
            button.setEnabled(not busy)
