"""按功能组织的 Fluent 工作页面。"""
from pathlib import Path


from importlib.metadata import version

from PySide6.QtCore import QSignalBlocker, Qt, Signal, Slot
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QHeaderView,
                               QHBoxLayout, QLabel, QSizePolicy, QTableWidgetItem,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, CheckBox, ComboBox, Dialog,
                            FluentIcon as FIF, HyperlinkButton, LineEdit, PlainTextEdit,
                            PrimaryPushButton, ProgressBar, PushButton, RadioButton,
                            SearchLineEdit, StrongBodyLabel, SwitchButton, TableWidget,
                            Theme, TitleLabel, qconfig, setFont)
from cli import main as core
from .models import LOG_LEVELS, normalize_log_level
from .components import (Ipv4TargetInput, SectionCard, TargetControls, TaskFooter,
                          page_heading, tool_button)


class LogHeaderView(QHeaderView):
    """日志表头首列内嵌与行复选框一致的全选控件。"""

    CHECKBOX_SIZE = 18

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.select_all_checkbox = CheckBox(self.viewport())
        self.select_all_checkbox.setAccessibleName("全选当前筛选结果")
        self.select_all_checkbox.setToolTip("全选当前筛选结果；取消勾选会清空全部选择")
        self.select_all_checkbox.setFixedSize(self.CHECKBOX_SIZE, self.CHECKBOX_SIZE)
        self.select_all_checkbox.raise_()

    def position_checkbox(self):
        if not self.isVisible():
            return
        x = self.sectionViewportPosition(0) + (self.sectionSize(0) - self.CHECKBOX_SIZE) // 2
        y = (self.height() - self.CHECKBOX_SIZE) // 2
        self.select_all_checkbox.move(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_checkbox()

    def showEvent(self, event):
        super().showEvent(event)
        self.position_checkbox()


class LogTableWidget(TableWidget):
    """日志表固定元数据列，内容列按剩余宽度自适应。"""

    FIXED_COLUMNS = (0, 1, 2, 3, 5, 6)
    MIN_CONTENT_WIDTH = 120

    def resizeEvent(self, event):
        super().resizeEvent(event)
        reserved = sum(self.columnWidth(column) for column in self.FIXED_COLUMNS)
        self.setColumnWidth(4, max(self.MIN_CONTENT_WIDTH, self.viewport().width() - reserved))


def table_widget(headers, parent, table_class=TableWidget):
    table = table_class(parent)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setWordWrap(False)
    table.setBorderVisible(True)
    table.setBorderRadius(6)
    table.horizontalHeader().setStretchLastSection(True)
    return table


class Page(QWidget):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self.vbox = QVBoxLayout(self)
        self.vbox.setContentsMargins(28, 24, 28, 24)
        self.vbox.setSpacing(20)


class NetworkPage(Page):
    def __init__(self, name, title, state, button_text, parent=None):
        super().__init__(name, parent)
        page_heading(self.vbox, title)
        self.target_card = SectionCard(self)
        self.targets = TargetControls(state, self.target_card)
        self.target_card.body.addWidget(self.targets)
        self.vbox.addWidget(self.target_card)
        self.content_card = SectionCard(self, spacing=10)
        self.body = self.content_card.body
        self.vbox.addWidget(self.content_card, 1)
        self.footer_card = SectionCard(self, spacing=0, margins=(8, 8, 8, 8))
        self.footer = TaskFooter(button_text, self.footer_card)
        self.footer_card.body.addWidget(self.footer)
        self.vbox.addWidget(self.footer_card)

    def set_busy(self, busy, cancellable=False):
        self.targets.setEnabled(not busy)
        self.footer.set_busy(busy, cancellable)


class MessagePage(NetworkPage):
    def __init__(self, state, parent=None):
        super().__init__("message", "文本消息", state, "发送消息", parent)
        row = QHBoxLayout()
        row.addWidget(BodyLabel("消息正文", self.content_card))
        row.addStretch()
        self.import_button = tool_button(FIF.FOLDER, "导入 UTF-8 文本", self.content_card, self._request_import)
        self.save_button = tool_button(FIF.SAVE, "保存消息正文", self.content_card, self._request_save)
        self.clear_button = tool_button(FIF.DELETE, "清空消息", self.content_card, lambda: self.editor.clear())
        for button in [self.import_button, self.save_button, self.clear_button]:
            row.addWidget(button)
        self.body.addLayout(row)
        self.editor = PlainTextEdit(self)
        self.editor.setPlaceholderText("输入消息内容")
        self.editor.setMinimumHeight(120)
        self.editor.textChanged.connect(self.update_statistics)
        self.body.addWidget(self.editor, 1)
        foot = QHBoxLayout()
        self.statistics = CaptionLabel("0 字符 | 0 条报文", self)
        self.filename = CaptionLabel("", self)
        self.filename.setMaximumWidth(230)
        self.filename.setMinimumWidth(0)
        self.filename.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        foot.addWidget(self.statistics)
        foot.addStretch()
        foot.addWidget(self.filename, 1, Qt.AlignRight)
        self.body.addLayout(foot)

    importRequested = Signal()
    saveRequested = Signal()

    def _request_import(self):
        self.importRequested.emit()

    def _request_save(self):
        self.saveRequested.emit()

    def update_statistics(self):
        text = self.editor.toPlainText()
        try:
            count = sum(1 for _ in core.split_message(text))
            self.statistics.setText("%d 字符 | %d 条报文" % (len(text), count))
            self.statistics.setToolTip("")
        except (ValueError, UnicodeError) as error:
            self.statistics.setText("文本包含不可发送字符")
            self.statistics.setToolTip(str(error))

    def set_busy(self, busy, cancellable=False):
        super().set_busy(busy, cancellable)
        self.editor.setReadOnly(busy)
        for button in [self.import_button, self.clear_button]:
            button.setEnabled(not busy)


class CommandPage(NetworkPage):
    def __init__(self, state, parent=None):
        super().__init__("command", "远程命令", state, "发送命令", parent)
        row = QHBoxLayout()
        row.addWidget(BodyLabel("命令正文", self.content_card))
        row.addStretch()
        self.clear_button = tool_button(FIF.DELETE, "清空命令", self.content_card, lambda: self.editor.clear())
        row.addWidget(self.clear_button)
        self.body.addLayout(row)
        self.editor = PlainTextEdit(self)
        self.editor.setPlaceholderText("cmd.exe /c ...")
        self.editor.setFont(QFont("Consolas", 11))
        self.editor.textChanged.connect(self.update_statistics)
        self.body.addWidget(self.editor, 1)
        self.statistics = CaptionLabel("", self)
        self.body.addWidget(self.statistics)
        self.update_statistics()

    def update_statistics(self):
        try:
            units = len(self.editor.toPlainText().encode("utf-16le")) // 2
        except UnicodeError:
            self.statistics.setText("文本编码无效")
            return
        limit = core.COMMAND_MAX_BYTES // 2
        self.statistics.setText("%d / %d 个 UTF-16 单元" % (units, limit))
        self.statistics.setStyleSheet("color: #c42b1c;" if units > limit else "")

    def set_busy(self, busy, cancellable=False):
        super().set_busy(busy, cancellable)
        self.editor.setReadOnly(busy)
        self.clear_button.setEnabled(not busy)


class DevicePage(NetworkPage):
    def __init__(self, state, parent=None):
        super().__init__("device", "设备操作", state, "执行重启", parent)
        row = QHBoxLayout()
        row.addWidget(BodyLabel("操作", self.content_card))
        self.reboot = RadioButton("重启", self)
        self.shutdown = RadioButton("关机", self)
        self.group = QButtonGroup(self)
        self.group.addButton(self.reboot)
        self.group.addButton(self.shutdown)
        self.reboot.setChecked(True)
        self.reboot.toggled.connect(self._update_action)
        self.shutdown.toggled.connect(self._update_action)
        row.addSpacing(16)
        row.addWidget(self.reboot)
        row.addSpacing(12)
        row.addWidget(self.shutdown)
        row.addStretch()
        self.body.addLayout(row)
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
        self.footer.send_button.setText("执行重启" if self.reboot.isChecked() else "执行关机")

    @Slot(str, object)
    def _on_target_changed(self, name, value):
        if name in {"target", "port"}:
            self.update_preview()

    def update_preview(self):
        target = self.targets.state.values["target"].strip()
        matched = self.targets.state.aliases.match(target)
        try:
            hosts = core.get_ip(self.targets.state.resolve_target(target)) if target else []
        except ValueError:
            hosts = []
        self.preview.setRowCount(len(hosts))
        for row, host in enumerate(hosts):
            self.preview.setItem(row, 0, QTableWidgetItem(host))
            self.preview.setItem(row, 1, QTableWidgetItem(str(self.targets.state.values["port"])))
            self.preview.setRowHeight(row, 36)
        alias_text = "，备注：%s" % matched[0] if matched else ""
        self.preview_title.setText("目标预览（%d%s）" % (len(hosts), alias_text))

    def action(self):
        return "r" if self.reboot.isChecked() else "s"

    def set_busy(self, busy, cancellable=False):
        super().set_busy(busy, cancellable)
        self.reboot.setEnabled(not busy)
        self.shutdown.setEnabled(not busy)


class FilePage(Page):
    chooseRequested = Signal()

    def __init__(self, state, parent=None):
        super().__init__("file", parent)
        page_heading(self.vbox, "文件传送")
        self.target_card = SectionCard(self)
        self.targets = TargetControls(state, self.target_card, show_round_options=False)
        self.target_card.body.addWidget(self.targets)
        self.vbox.addWidget(self.target_card)
        self.content_card = SectionCard(self, spacing=12)
        row = QHBoxLayout()
        row.addWidget(BodyLabel("待传送文件", self.content_card))
        row.addStretch()
        self.choose_button = tool_button(FIF.FOLDER, "选择文件", self.content_card, self.chooseRequested.emit)
        row.addWidget(self.choose_button)
        self.content_card.body.addLayout(row)
        self.file_name = BodyLabel("尚未选择文件", self.content_card)
        self.file_name.setWordWrap(True)
        self.content_card.body.addWidget(self.file_name)
        self.file_detail = CaptionLabel("选择任意本地文件，目标电脑将下载到当前用户桌面。", self.content_card)
        self.file_detail.setWordWrap(True)
        self.content_card.body.addWidget(self.file_detail)
        self.progress = ProgressBar(self.content_card)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.hide()
        self.content_card.body.addWidget(self.progress)
        self.progress_text = CaptionLabel("", self.content_card)
        self.progress_text.hide()
        self.content_card.body.addWidget(self.progress_text)
        hint = CaptionLabel(
            "目标地址支持单个 IPv4、末段范围或 /24 网段，将按目标逐个传送。"
            "目标电脑需要能访问本机 IP 与文件传送端口；传送期间请保持本页任务运行。"
            "目标需允许执行远程命令，并由系统 cmd 下载文件。", self.content_card)
        hint.setWordWrap(True)
        self.content_card.body.addWidget(hint)
        self.content_card.body.addStretch()
        self.vbox.addWidget(self.content_card, 1)
        self.footer_card = SectionCard(self, spacing=0, margins=(8, 8, 8, 8))
        self.footer = TaskFooter("传送文件", self.footer_card, FIF.SEND)
        self.footer_card.body.addWidget(self.footer)
        self.vbox.addWidget(self.footer_card)
        self.path = ""
        self.size = 0

    def set_file(self, path, size):
        self.path = str(path)
        self.size = int(size)
        self.file_name.setText(Path(path).name)
        self.file_name.setToolTip(str(path))
        self.file_detail.setText("%s · %s" % (core.format_size(size), path))

    def set_progress(self, percent):
        self.progress.show()
        self.progress_text.show()
        self.progress.setValue(max(0, min(100, int(percent))))
        self.progress_text.setText("当前目标下载进度：%d%%" % max(0, min(100, int(percent))))

    def reset_progress(self):
        self.progress.setValue(0)
        self.progress.hide()
        self.progress_text.hide()

    def set_busy(self, busy, cancellable=False):
        self.targets.setEnabled(not busy)
        self.choose_button.setEnabled(not busy)
        self.footer.set_busy(busy, cancellable)


class AliasPage(Page):
    def __init__(self, state, parent=None):
        super().__init__("aliases", parent)
        self.state = state
        self.store = state.aliases
        self._editing_name = None
        self.count_label = CaptionLabel("0 条备注", self)
        page_heading(self.vbox, "设备备注", self.count_label)
        hint = CaptionLabel(
            "先为 IPv4 添加备注名，再在任意远程操作的目标地址中直接填写备注名。"
            "修改备注后，已引用的目标会自动同步。", self)
        hint.setWordWrap(True)
        form_card = SectionCard(self, spacing=14)
        form_card.body.addWidget(hint)
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
            self, object_name="aliasAddressInput", field_label="备注 IP 地址")
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
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
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
        self.name_input.returnPressed.connect(lambda: self.address_input.segments[0].setFocus())
        self.address_input.nextFieldRequested.connect(self.save)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(lambda row, column: self.edit_selected())
        self.store.changed.connect(self._refresh_table)
        self._refresh_table()
        if self.store.load_error:
            self._set_status(self.store.load_error, error=True)
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
        self._reset_form()
        self._set_status("")

    def save(self):
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
            return
        self._reset_form()
        self._select_name(name)
        self._set_status(action)

    def edit_selected(self):
        name = self._selected_name()
        if not name:
            return
        matched = self.store.match(name)
        if matched is None:
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

    def use_selected(self):
        name = self._selected_name()
        matched = self.store.match(name) if name else None
        if matched is None:
            return
        self.state.set_value("target", matched[0])
        self._set_status("已将「%s」（%s）设为当前目标" % matched)

    def delete_selected(self):
        name = self._selected_name()
        matched = self.store.match(name) if name else None
        if matched is None:
            return
        dialog = Dialog(
            "删除设备备注",
            "确定删除备注「%s」（%s）？当前目标如果引用该备注，也会被清空。" % matched,
            self,
        )
        dialog.setFixedSize(520, 280)
        dialog.yesButton.setText("删除")
        dialog.cancelButton.setText("取消")
        if not dialog.exec():
            return
        try:
            self.store.remove(matched[0])
        except (OSError, ValueError) as error:
            self._set_status(str(error), error=True)
            return
        if self._editing_name == matched[0]:
            self._reset_form()
        self._set_status("已删除备注「%s」" % matched[0])


class LocalPage(Page):
    copyRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("local", parent)
        page_heading(self.vbox, "本机信息")
        row = QHBoxLayout()
        row.addWidget(BodyLabel("本机 IP", self))
        self.ip_label = BodyLabel("未查询", self)
        setFont(self.ip_label, 18)
        row.addWidget(self.ip_label)
        row.addStretch()
        self.copy_button = tool_button(FIF.COPY, "复制本机 IP", self, self.copyRequested.emit)
        self.copy_button.setEnabled(False)
        row.addWidget(self.copy_button)
        self.content_card = SectionCard(self)
        self.content_card.body.addLayout(row)
        self.content_card.body.addWidget(BodyLabel("Student 监听端口", self.content_card))
        self.port_table = table_widget(["协议", "端口"], self.content_card)
        self.port_table.setColumnWidth(0, 140)
        self.content_card.body.addWidget(self.port_table, 1)
        self.vbox.addWidget(self.content_card, 1)
        self.footer_card = SectionCard(self, spacing=0, margins=(8, 8, 8, 8))
        self.footer = TaskFooter("查询本机", self.footer_card, FIF.SEARCH)
        self.footer.cancel_button.hide()
        self.footer_card.body.addWidget(self.footer)
        self.vbox.addWidget(self.footer_card)

    def set_result(self, ip, ports):
        self.ip_label.setText(ip or "未获取")
        self.copy_button.setEnabled(bool(ip))
        self.port_table.setRowCount(len(ports))
        for row, port in enumerate(ports):
            self.port_table.setItem(row, 0, QTableWidgetItem("UDP"))
            self.port_table.setItem(row, 1, QTableWidgetItem(port))
            self.port_table.setRowHeight(row, 38)


class FirewallPage(Page):
    def __init__(self, parent=None):
        super().__init__("firewall", parent)
        page_heading(self.vbox, "防火墙")
        row = QHBoxLayout()
        row.addWidget(BodyLabel("规则", self))
        rule = BodyLabel("StudentMain.exe", self)
        setFont(rule, 16)
        row.addWidget(rule)
        row.addStretch()
        self.action_box = ComboBox(self)
        self.action_box.addItems(["阻断连接", "恢复允许"])
        self.action_box.setMinimumWidth(170)
        row.addWidget(self.action_box)
        self.content_card = SectionCard(self)
        self.content_card.body.addLayout(row)
        self.content_card.body.addWidget(BodyLabel("操作结果", self.content_card))
        self.result_table = table_widget(["操作", "结果", "输出"], self.content_card)
        self.result_table.setColumnWidth(0, 180)
        self.result_table.setColumnWidth(1, 80)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.setWordWrap(True)
        self.result_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.content_card.body.addWidget(self.result_table, 1)
        self.vbox.addWidget(self.content_card, 1)
        self.footer_card = SectionCard(self, spacing=0, margins=(8, 8, 8, 8))
        self.footer = TaskFooter("应用规则", self.footer_card, FIF.CERTIFICATE)
        self.footer.cancel_button.hide()
        self.footer_card.body.addWidget(self.footer)
        self.vbox.addWidget(self.footer_card)

    def action(self):
        return "block" if self.action_box.currentIndex() == 0 else "allow"

    def set_result(self, results):
        self.result_table.setRowCount(len(results))
        labels = ["防火墙服务", "启用防火墙", "目标规则"]
        for row, result in enumerate(results):
            if isinstance(result, dict):
                code = result["code"]
                text = result["stdout"] or result["stderr"]
                success = result["success"]
                prefixes = ["net.exe", "netsh advfirewall set", "netsh advfirewall firewall"]
                label = next(
                    (item for item, prefix in zip(labels, prefixes) if result["command"].startswith(prefix)),
                    labels[-1],
                )
            else:
                _, code, stdout, stderr = result
                text = stdout or stderr
                success = code == 0
                label = labels[row] if len(results) > 1 else labels[-1]
            for column, value in enumerate([label, "成功" if success else "失败", text]):
                item = QTableWidgetItem(value.replace("\r\n", "\n").replace("\r", "\n").strip())
                item.setToolTip(value)
                self.result_table.setItem(row, column, item)
            self.result_table.setRowHeight(row, max(38, self.result_table.sizeHintForRow(row)))
            self.result_table.setRowHeight(row, max(38, self.result_table.rowHeight(row)))


class LogPage(Page):
    exportSelectedRequested = Signal(object)
    deleteSelectedRequested = Signal(object)
    cancelRequested = Signal()

    def __init__(self, store, parent=None):
        super().__init__("logs", parent)
        self.store = store
        self._row_by_uid = {}
        page_heading(self.vbox, "运行日志")
        toolbar = QHBoxLayout()
        self.search = SearchLineEdit(self)
        self.search.setPlaceholderText("搜索日志")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        self.category = ComboBox(self)
        self.category.addItems(["全部功能", "应用", "文本消息", "远程命令", "设备操作",
                                "文件传送", "本机信息", "防火墙", "运行日志"])
        self.category.currentIndexChanged.connect(self.apply_filter)
        self.category.setMinimumWidth(130)
        self.level_filter = ComboBox(self)
        self.level_filter.addItems(["全部级别"] + [str(level) for level in LOG_LEVELS])
        self.level_filter.currentIndexChanged.connect(self.apply_filter)
        self.level_filter.setMinimumWidth(120)
        self.cancel_button = tool_button(FIF.CANCEL, "取消当前发送", self, self.cancelRequested.emit)
        self.cancel_button.setEnabled(False)
        self.export_button = tool_button(FIF.SAVE, "导出选中日志", self, self._export_selected)
        self.delete_button = tool_button(FIF.DELETE, "删除选中日志", self, self._delete_selected)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.category)
        toolbar.addWidget(self.level_filter)
        for button in [self.cancel_button, self.export_button, self.delete_button]:
            toolbar.addWidget(button)

        self.content_card = SectionCard(self, spacing=10)
        self.content_card.body.addLayout(toolbar)
        self.table = table_widget(["", "时间", "级别", "功能", "内容", "线程", "输出位置"],
                                  self.content_card, LogTableWidget)
        self.table.setHorizontalHeader(LogHeaderView(Qt.Horizontal, self.table))
        header = self.table.horizontalHeader()
        self.select_all_checkbox = header.select_all_checkbox
        self.select_all_checkbox.toggled.connect(self._toggle_visible_rows)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(40)
        for column, width in ((0, 42), (1, 190), (2, 112), (3, 96), (4, 220),
                              (5, 145), (6, 165)):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            self.table.setColumnWidth(column, width)
        self.table.itemChanged.connect(self._item_changed)
        self.table.itemClicked.connect(self._item_clicked)
        self.table.horizontalScrollBar().valueChanged.connect(self._position_header_checkbox)
        self.content_card.body.addWidget(self.table, 1)
        self.count_label = CaptionLabel("0 条记录", self.content_card)
        self.content_card.body.addWidget(self.count_label)
        self.vbox.addWidget(self.content_card, 1)
        store.added.connect(self._append_entry)
        store.removed.connect(self._remove_entries)
        store.cleared.connect(self._clear_entries)
        store.levelChanged.connect(self._level_changed)
        for entry in self.store.entries:
            self._append_entry(entry)
        self.apply_filter()
        self._position_header_checkbox()

    @Slot(object)
    def _append_entry(self, entry):
        if self.table.rowCount() >= self.store.entries.maxlen:
            self.table.removeRow(0)
            self._rebuild_row_map()
        row = self.table.rowCount()
        self.table.blockSignals(True)
        try:
            self.table.insertRow(row)
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            checkbox.setCheckState(Qt.Unchecked)
            checkbox.setData(Qt.UserRole, entry.uid)
            checkbox.setToolTip("选择此条日志")
            self.table.setItem(row, 0, checkbox)
            values = [
                entry.time,
                str(entry.level),
                entry.category,
                entry.message,
                "%s (%d)" % (entry.thread_name, entry.thread_id),
                "%s:%d" % (entry.logger_name, entry.line_number),
            ]
            for column, value in enumerate(values, start=1):
                item = QTableWidgetItem(value.replace("\r", "").replace("\n", " "))
                item.setToolTip(entry.as_text())
                self.table.setItem(row, column, item)
        finally:
            self.table.blockSignals(False)
        self._row_by_uid[entry.uid] = row
        self.table.setRowHeight(row, 38)
        self.apply_filter()
        if not self.table.isRowHidden(row):
            self.table.scrollToBottom()

    def _rebuild_row_map(self):
        self._row_by_uid = {}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                self._row_by_uid[int(item.data(Qt.UserRole))] = row

    @Slot(str)
    def _level_changed(self, _level):
        self.apply_filter()

    def _entry_checked(self, uid):
        row = self._row_by_uid.get(uid)
        if row is None:
            return False
        item = self.table.item(row, 0)
        return item is not None and item.checkState() == Qt.Checked

    def selected_entries(self):
        return [entry for entry in self.store.entries if self._entry_checked(entry.uid)]

    def selected_uids(self):
        return [entry.uid for entry in self.selected_entries()]

    def _visible_rows(self):
        return [row for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)]

    def _update_selection_controls(self):
        selected_count = len(self.selected_uids())
        visible_rows = self._visible_rows()
        all_checked = bool(visible_rows) and all(
            self.table.item(row, 0).checkState() == Qt.Checked for row in visible_rows
        )
        with QSignalBlocker(self.select_all_checkbox):
            self.select_all_checkbox.setChecked(all_checked)
        self.select_all_checkbox.setEnabled(bool(visible_rows))
        for button in (self.export_button, self.delete_button):
            button.setEnabled(selected_count > 0)
        self.count_label.setText(
            "%d / %d 条记录 | 运行等级 %s | 已选 %d 条" % (
                len(visible_rows), self.table.rowCount(),
                str(self.store.minimum_level), selected_count))

    @Slot(bool)
    def _toggle_visible_rows(self, checked):
        rows = self._visible_rows() if checked else range(self.table.rowCount())
        self.table.blockSignals(True)
        try:
            state = Qt.Checked if checked else Qt.Unchecked
            for row in rows:
                item = self.table.item(row, 0)
                if item is not None:
                    item.setCheckState(state)
        finally:
            self.table.blockSignals(False)
        self._update_selection_controls()

    def _position_header_checkbox(self, *_):
        self.table.horizontalHeader().position_checkbox()

    def _item_changed(self, item):
        if item.column() == 0:
            self._update_selection_controls()

    def _item_clicked(self, item):
        if item.column() == 0:
            self._update_selection_controls()

    def _export_selected(self):
        entries = self.selected_entries()
        if entries:
            self.exportSelectedRequested.emit(entries)

    def _delete_selected(self):
        uids = self.selected_uids()
        if uids:
            self.deleteSelectedRequested.emit(uids)

    @Slot(object)
    def _remove_entries(self, removed):
        removed_uids = {entry.uid for entry in removed}
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount() - 1, -1, -1):
                item = self.table.item(row, 0)
                if item is not None and int(item.data(Qt.UserRole)) in removed_uids:
                    self.table.removeRow(row)
        finally:
            self.table.blockSignals(False)
        self._rebuild_row_map()
        self.apply_filter()

    def _clear_entries(self):
        self.table.setRowCount(0)
        self._row_by_uid.clear()
        self.apply_filter()

    def apply_filter(self, *_):
        query = self.search.text().casefold().strip()
        category = self.category.currentText()
        level = self.level_filter.currentText()
        visible = 0
        for row in range(self.table.rowCount()):
            checkbox = self.table.item(row, 0)
            values = [self.table.item(row, column).text() for column in range(1, 7)]
            match = (
                checkbox is not None
                and (category == "全部功能" or values[2] == category)
                and (level == "全部级别" or values[1] == level)
                and query in " ".join(values).casefold()
            )
            self.table.setRowHidden(row, not match)
            visible += int(match)
        self._update_selection_controls()

    def export_text(self, entries=None):
        source = self.store.entries if entries is None else entries
        return self.store.export_text(source)


class SettingsPage(Page):
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
        self.theme_box.setCurrentIndex([Theme.LIGHT, Theme.DARK, Theme.AUTO].index(qconfig.themeMode.value))
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
            "开启：关闭窗口后保留在系统托盘；关闭：直接退出应用")
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
        self.log_level_box.setCurrentIndex(LOG_LEVELS.index(self.log_store.minimum_level))
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
            lambda checked=False: self.clearDataRequested.emit())
        data_row.addWidget(self.clear_data_button, 0, Qt.AlignVCenter)
        data_card.body.addLayout(data_row)
        self.vbox.addWidget(data_card)

        self.vbox.addStretch()

    def _select_theme(self, index):
        self.themeRequested.emit([Theme.LIGHT, Theme.DARK, Theme.AUTO][index])

    def _select_close_behavior(self, checked):
        self.closeBehaviorRequested.emit("tray" if checked else "quit")

    def set_close_behavior(self, behavior):
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


class AboutInfoCard(SectionCard):
    """关于页中每一项独立的信息卡片。"""

    def __init__(self, label, value, parent=None, url=None, icon=None):
        super().__init__(parent, spacing=0, margins=(18, 12, 18, 12))
        self.setObjectName("aboutInfoCard")
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(BodyLabel(label, self))
        row.addStretch()
        if url is None:
            detail = BodyLabel(value, self)
            detail.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(detail)
        else:
            detail = HyperlinkButton(url, value, self, icon=icon)
            detail.setMaximumWidth(detail.sizeHint().width())
            row.addWidget(detail)
        self.body.addLayout(row)
        self.label = label
        self.detail = detail


class AboutPage(Page):
    def __init__(self, parent=None):
        super().__init__("about", parent)
        page_heading(self.vbox, "关于")
        content = QVBoxLayout()
        content.setSpacing(12)

        hero = QWidget(self)
        hero.setObjectName("aboutHero")
        hero_body = QVBoxLayout(hero)
        hero_body.setContentsMargins(20, 18, 20, 18)
        hero_body.setSpacing(8)
        icon_path = Path(__file__).resolve().parents[2] / "assets" / "app.svg"
        icon = QIcon(str(icon_path)).pixmap(96, 96)
        icon_label = QLabel(hero)
        icon_label.setPixmap(icon)
        icon_label.setFixedSize(96, 96)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon_row.addWidget(icon_label)
        icon_row.addStretch()
        hero_body.addLayout(icon_row)
        title = TitleLabel("JiYu Attack Next", hero)
        title.setAlignment(Qt.AlignCenter)
        hero_body.addWidget(title)
        subtitle = BodyLabel("极域学生端 UDP 控制报文测试工具", hero)
        subtitle.setAlignment(Qt.AlignCenter)
        hero_body.addWidget(subtitle)
        content.addWidget(hero)

        self.cards = {}
        for key, label, url, text, icon in [
            ("author", "作者", "https://github.com/JasonFang0109c", "JasonFang0109c", FIF.GITHUB),
            ("repository", "GitHub 仓库", "https://github.com/JasonFang0109c/jiyu_attack_next",
             "https://github.com/JasonFang0109c/jiyu_attack_next", FIF.GITHUB),
            ("upstream", "上游仓库", "https://github.com/ht0Ruial/Jiyu_udp_attack",
             "https://github.com/ht0Ruial/Jiyu_udp_attack", FIF.LINK),
        ]:
            card = AboutInfoCard(label, text, self, url=url, icon=icon)
            self.cards[key] = card
            content.addWidget(card)

        versions = SectionCard(self, spacing=8, margins=(18, 12, 18, 12))
        versions.setObjectName("aboutVersionsCard")
        heading = BodyLabel("组件版本", versions)
        versions.body.addWidget(heading)
        self.versions = {}
        for title_text, package in [("PySide6", "PySide6"),
                                    ("Fluent Widgets", "PySide6-Fluent-Widgets")]:
            version_row = QHBoxLayout()
            version_row.addWidget(CaptionLabel(title_text, versions))
            version_row.addStretch()
            value = CaptionLabel(version(package), versions)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            version_row.addWidget(value)
            versions.body.addLayout(version_row)
            self.versions[title_text] = value
        content.addWidget(versions)
        content.addStretch()
        self.vbox.addLayout(content)
