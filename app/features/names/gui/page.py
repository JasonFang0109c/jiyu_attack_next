"""设备备注页：给常用目标起中文名字，后续直接按名字发送。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CaptionLabel, LineEdit, PrimaryPushButton, PushButton
from qfluentwidgets import FluentIcon as FIF

from app.gui.theme import CONTROL_CORNER_RADIUS
from app.gui.widgets.common import (
    FluentDialog,
    Ipv4TargetInput,
    SectionCard,
    center_dialog,
    info_button,
    page_heading,
)
from app.gui.widgets.page import Page, table_widget


class AliasPage(Page):
    """维护“备注名 → 地址”映射，修改后同步刷新引用该备注的页面。"""

    def __init__(self, state, parent=None, logs=None):
        super().__init__("aliases", parent)
        self.state = state
        self.store = state.aliases
        # 页面可能先于日志存储被单独创建（例如测试），没有存储时日志调用自动跳过。
        self.logs = logs
        self._editing_name = None
        self.count_label = CaptionLabel("0 条备注", self)
        heading_actions = QWidget(self)
        heading_actions_layout = QHBoxLayout(heading_actions)
        heading_actions_layout.setContentsMargins(0, 0, 0, 0)
        heading_actions_layout.setSpacing(8)
        heading_actions_layout.addWidget(self.count_label)
        self.info_button = info_button(
            "备注名可直接用作目标；支持 IPv4、末段范围和 /24，修改后同步引用。",
            heading_actions,
        )
        heading_actions_layout.addWidget(self.info_button)
        page_heading(self.vbox, "设备备注", heading_actions)
        form_card = SectionCard(self, spacing=14)
        form = QHBoxLayout()
        form.setSpacing(12)
        name_column = QVBoxLayout()
        name_column.setSpacing(6)
        name_column.addWidget(CaptionLabel("备注名", self))
        self.name_input = LineEdit(self)
        self.name_input.setPlaceholderText("例如：教室 A 讲台")
        self.name_input.setClearButtonEnabled(True)
        name_column.addWidget(self.name_input)
        address_column = QVBoxLayout()
        address_column.setSpacing(6)
        address_column.addWidget(CaptionLabel("IP 地址", self))
        self.address_input = Ipv4TargetInput(
            self, object_name="aliasAddressInput", field_label="备注 IP 地址"
        )
        self.address_input.setToolTip("支持单个 IPv4、末段范围和 /24 网段")
        address_column.addWidget(self.address_input)
        self.save_button = PrimaryPushButton("添加备注", self)
        self.save_button.setIcon(FIF.ADD)
        self.save_button.setMinimumWidth(112)
        self.cancel_button = PushButton("取消", self)
        self.cancel_button.setIcon(FIF.CANCEL)
        self.cancel_button.setMinimumWidth(84)
        self.cancel_button.hide()
        form.addLayout(name_column, 1)
        form.addLayout(address_column)
        form.addWidget(self.save_button, 0, Qt.AlignBottom)
        form.addWidget(self.cancel_button, 0, Qt.AlignBottom)
        form_card.body.addLayout(form)
        self.vbox.addWidget(form_card)

        self.table_card = SectionCard(self, spacing=0, margins=(0, 0, 0, 0))
        self.table = table_widget(["备注名", "IP 地址"], self.table_card)
        # 表格铺满卡片，圆角与卡片保持一致，避免出现两条错位弧线。
        self.table.setBorderRadius(CONTROL_CORNER_RADIUS)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.table_card.body.addWidget(self.table)
        self.vbox.addWidget(self.table_card, 1)

        action_card = SectionCard(self, spacing=0, margins=(16, 12, 16, 12))
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.status = CaptionLabel("", self)
        self.status.setMinimumWidth(0)
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.status.setWordWrap(True)
        self.status.hide()
        self.use_button = PushButton("设为当前目标", self)
        self.use_button.setIcon(FIF.SEND)
        self.edit_button = PushButton("修改", self)
        self.edit_button.setIcon(FIF.EDIT)
        self.delete_button = PushButton("删除", self)
        self.delete_button.setIcon(FIF.DELETE)
        action_row.addWidget(self.status, 1)
        for button in (self.use_button, self.edit_button, self.delete_button):
            button.setEnabled(False)
            action_row.addWidget(button)
        action_card.body.addLayout(action_row)
        self.vbox.addWidget(action_card)

        self.save_button.clicked.connect(lambda checked=False: self.save())
        self.cancel_button.clicked.connect(lambda checked=False: self.cancel_edit())
        self.use_button.clicked.connect(lambda checked=False: self.use_selected())
        self.edit_button.clicked.connect(lambda checked=False: self.edit_selected())
        self.delete_button.clicked.connect(lambda checked=False: self.delete_selected())
        self.name_input.returnPressed.connect(
            lambda: self.address_input.segments[0].setFocus()
        )
        self.address_input.nextFieldRequested.connect(self.save)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(lambda row, column: self.edit_selected())
        self.store.changed.connect(self._refresh_table)
        self._refresh_table()
        if self.store.load_error:
            self._set_status(self.store.load_error, error=True)
            self._log(
                "warning",
                "设备备注读取失败，已按空列表启动",
                "备注数：%d；异常：%s"
                % (len(self.store.items()), self.store.load_error),
            )
        else:
            self._set_status("备注保存在程序数据目录，重启后仍然可用。")

    def _selected_name(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.text() if item is not None else ""

    def _select_name(self, name):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.text().casefold() == str(name).casefold():
                self.table.setCurrentCell(row, 0)
                return

    def _selection_changed(self):
        selected = bool(self._selected_name())
        for button in (self.use_button, self.edit_button, self.delete_button):
            button.setEnabled(selected)

    def _refresh_table(self):
        selected = self._selected_name()
        items = self.store.items()
        self.table.setRowCount(len(items))
        for row, (name, address) in enumerate(items):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(address))
            self.table.setRowHeight(row, 36)
            if name == selected or name == self._editing_name:
                self.table.setCurrentCell(row, 0)
        self.count_label.setText("%d 条备注" % len(items))
        self._selection_changed()

    def _set_status(self, text, error=False):
        self.status.setText(text)
        self.status.setStyleSheet("color: #c42b1c;" if error else "")
        self.status.setVisible(bool(text))

    def _reset_form(self):
        self._editing_name = None
        self.name_input.clear()
        self.address_input.clear()
        self.name_input.setError(False)
        self.address_input.setError(False)
        self.save_button.setText("添加备注")
        self.save_button.setIcon(FIF.ADD)
        self.cancel_button.hide()

    def cancel_edit(self):
        """退出编辑状态，清空表单与提示。"""
        self._reset_form()
        self._set_status("")

    def _log(self, level, message, details=""):
        """写设备备注相关日志；没有日志存储时直接跳过。"""
        if self.logs is None:
            return
        getattr(self.logs, level)("设备操作", message, details)

    def save(self):
        """添加新备注或保存编辑中的备注，失败时在对应输入框标错。"""
        name = self.name_input.text().strip()
        address = self.address_input.text().strip()
        try:
            if self._editing_name is None:
                self.store.add(name, address)
                action = "已添加备注「%s」" % name
            else:
                original = self._editing_name
                self.store.update(original, name, address)
                action = "已修改备注「%s」" % name
        except (OSError, ValueError) as error:
            message = str(error)
            self.name_input.setError("备注名" in message)
            self.address_input.setError("IP" in message or "地址" in message)
            self._set_status(message, error=True)
            self._log(
                "warning",
                "设备备注保存失败",
                "备注名：%s；地址：%s；异常：%s" % (name or "（空）", address, error),
            )
            return
        self._log(
            "info",
            action,
            "备注名：%s；地址：%s；当前备注数：%d"
            % (name, address, len(self.store.items())),
        )
        self._reset_form()
        self._select_name(name)
        self._set_status(action)

    def edit_selected(self):
        """把选中的备注填入表单并进入编辑状态。"""
        name = self._selected_name()
        if not name:
            self._log("warning", "未选中设备备注，无法修改")
            return
        matched = self.store.match(name)
        if matched is None:
            self._log("warning", "要修改的设备备注不存在", "备注名：%s" % name)
            return
        self._editing_name = matched[0]
        self.name_input.setText(matched[0])
        self.address_input.setText(matched[1])
        self.name_input.setError(False)
        self.address_input.setError(False)
        self.save_button.setText("保存修改")
        self.save_button.setIcon(FIF.SAVE)
        self.cancel_button.show()
        self.name_input.setFocus()
        self.name_input.selectAll()
        self._log("debug", "进入设备备注编辑状态", "备注名：%s；地址：%s" % matched)

    def use_selected(self):
        """把选中备注的地址设为当前发送目标。"""
        name = self._selected_name()
        matched = self.store.match(name) if name else None
        if matched is None:
            self._log("warning", "未选中设备备注，无法设为当前目标")
            return
        self.state.set_value("target", matched[0])
        self._log("info", "设备备注已设为当前目标", "备注名：%s；地址：%s" % matched)
        self._set_status("已将「%s」（%s）设为当前目标" % matched)

    def delete_selected(self):
        """确认后删除选中的备注。"""
        name = self._selected_name()
        matched = self.store.match(name) if name else None
        if matched is None:
            self._log("warning", "未选中设备备注，无法删除")
            return
        dialog = FluentDialog(
            "删除设备备注",
            "确定删除备注「%s」（%s）？当前目标如果引用该备注，也会被清空。" % matched,
            self,
        )
        dialog.setFixedSize(520, 280)
        dialog.yesButton.setText("删除")
        dialog.cancelButton.setText("取消")
        center_dialog(dialog)
        if not dialog.exec():
            self._log("info", "用户取消了设备备注删除", "备注名：%s" % matched[0])
            return
        try:
            self.store.remove(matched[0])
        except (OSError, ValueError) as error:
            self._set_status(str(error), error=True)
            self._log(
                "error",
                "设备备注删除失败",
                "备注名：%s；地址：%s；异常：%s" % (matched[0], matched[1], error),
            )
            return
        if self._editing_name == matched[0]:
            self._reset_form()
        self._log(
            "info",
            "已删除备注「%s」" % matched[0],
            "地址：%s；当前备注数：%d" % (matched[1], len(self.store.items())),
        )
        self._set_status("已删除备注「%s」" % matched[0])
