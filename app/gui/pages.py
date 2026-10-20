"""按功能组织的 Fluent 工作页面。"""
from pathlib import Path


from importlib.metadata import version

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QHeaderView,
                               QHBoxLayout, QLabel, QSizePolicy, QTableWidgetItem,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, ComboBox, FluentIcon as FIF,
                            HyperlinkButton, PlainTextEdit, PushButton, RadioButton, SearchLineEdit,
                            StrongBodyLabel, TableWidget, Theme, TitleLabel, qconfig, setFont)
from cli import main as core
from .components import TargetControls, TaskFooter, page_heading, tool_button


def table_widget(headers, parent):
    table = TableWidget(parent)
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
        self.targets = TargetControls(state, self)
        self.vbox.addWidget(self.targets)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        self.vbox.addLayout(self.body, 1)
        self.footer = TaskFooter(button_text, self)
        self.vbox.addWidget(self.footer)

    def set_busy(self, busy, cancellable=False):
        self.targets.setEnabled(not busy)
        self.footer.set_busy(busy, cancellable)


class MessagePage(NetworkPage):
    def __init__(self, state, parent=None):
        super().__init__("message", "文本消息", state, "发送消息", parent)
        row = QHBoxLayout()
        row.addWidget(BodyLabel("消息正文", self))
        row.addStretch()
        self.import_button = tool_button(FIF.FOLDER, "导入 UTF-8 文本", self, self._request_import)
        self.save_button = tool_button(FIF.SAVE, "保存消息正文", self, self._request_save)
        self.clear_button = tool_button(FIF.DELETE, "清空消息", self, lambda: self.editor.clear())
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
        row.addWidget(BodyLabel("命令正文", self))
        row.addStretch()
        self.clear_button = tool_button(FIF.DELETE, "清空命令", self, lambda: self.editor.clear())
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
        row.addWidget(BodyLabel("操作", self))
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
        self.preview_title = BodyLabel("目标预览", self)
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
        try:
            hosts = core.get_ip(target) if target else []
        except ValueError:
            hosts = []
        self.preview.setRowCount(len(hosts))
        for row, host in enumerate(hosts):
            self.preview.setItem(row, 0, QTableWidgetItem(host))
            self.preview.setItem(row, 1, QTableWidgetItem(str(self.targets.state.values["port"])))
            self.preview.setRowHeight(row, 36)
        self.preview_title.setText("目标预览（%d）" % len(hosts))

    def action(self):
        return "r" if self.reboot.isChecked() else "s"

    def set_busy(self, busy, cancellable=False):
        super().set_busy(busy, cancellable)
        self.reboot.setEnabled(not busy)
        self.shutdown.setEnabled(not busy)


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
        self.vbox.addLayout(row)
        self.vbox.addWidget(BodyLabel("Student 监听端口", self))
        self.port_table = table_widget(["协议", "端口"], self)
        self.port_table.setColumnWidth(0, 140)
        self.vbox.addWidget(self.port_table, 1)
        self.footer = TaskFooter("查询本机", self, FIF.SEARCH)
        self.footer.cancel_button.hide()
        self.vbox.addWidget(self.footer)

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
        self.vbox.addLayout(row)
        self.vbox.addWidget(BodyLabel("操作结果", self))
        self.result_table = table_widget(["操作", "结果", "输出"], self)
        self.result_table.setColumnWidth(0, 180)
        self.result_table.setColumnWidth(1, 80)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.setWordWrap(True)
        self.result_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.vbox.addWidget(self.result_table, 1)
        self.footer = TaskFooter("应用规则", self, FIF.CERTIFICATE)
        self.footer.cancel_button.hide()
        self.vbox.addWidget(self.footer)

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
    exportRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, store, parent=None):
        super().__init__("logs", parent)
        self.store = store
        page_heading(self.vbox, "运行日志")
        toolbar = QHBoxLayout()
        self.search = SearchLineEdit(self)
        self.search.setPlaceholderText("搜索日志")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        self.category = ComboBox(self)
        self.category.addItems(["全部功能", "应用", "文本消息", "远程命令", "设备操作", "本机信息", "防火墙"])
        self.category.currentIndexChanged.connect(self.apply_filter)
        self.category.setMinimumWidth(130)
        self.cancel_button = tool_button(FIF.CANCEL, "取消当前发送", self, self.cancelRequested.emit)
        self.cancel_button.setEnabled(False)
        export_button = tool_button(FIF.SAVE, "导出全部日志", self, self.exportRequested.emit)
        clear_button = tool_button(FIF.DELETE, "清空日志", self, store.clear)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.category)
        for button in [self.cancel_button, export_button, clear_button]:
            toolbar.addWidget(button)
        self.vbox.addLayout(toolbar)
        self.table = table_widget(["时间", "功能", "级别", "内容"], self)
        self.table.setColumnWidth(0, 105)
        self.table.setColumnWidth(1, 105)
        self.table.setColumnWidth(2, 75)
        self.vbox.addWidget(self.table, 1)
        self.count_label = CaptionLabel("0 条记录", self)
        self.vbox.addWidget(self.count_label)
        store.added.connect(self._append_entry)
        store.cleared.connect(self._clear_entries)

    @Slot(object)
    def _append_entry(self, entry):
        if self.table.rowCount() >= self.store.entries.maxlen:
            self.table.removeRow(0)
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, value in enumerate([entry.time, entry.category, entry.level, entry.message]):
            item = QTableWidgetItem(value.replace("\r", "").replace("\n", " "))
            item.setToolTip(value)
            self.table.setItem(row, column, item)
        self.table.setRowHeight(row, 36)
        self.apply_filter()
        self.table.scrollToBottom()

    def _clear_entries(self):
        self.table.setRowCount(0)
        self.apply_filter()

    def apply_filter(self, *_):
        query = self.search.text().casefold().strip()
        category = self.category.currentText()
        visible = 0
        for row in range(self.table.rowCount()):
            values = [self.table.item(row, column).text() for column in range(4)]
            match = (category == "全部功能" or values[1] == category) and query in " ".join(values).casefold()
            self.table.setRowHidden(row, not match)
            visible += int(match)
        self.count_label.setText("%d / %d 条记录" % (visible, self.table.rowCount()))

    def export_text(self):
        return "\n".join(entry.as_text() for entry in self.store.entries)


class SettingsPage(Page):
    themeRequested = Signal(object)
    resetRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("settings", parent)
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
        self.vbox.addLayout(row)
        reset_row = QHBoxLayout()
        reset_row.addWidget(BodyLabel("连接参数", self))
        reset_row.addStretch()
        self.reset_hint = CaptionLabel("已恢复默认参数", self)
        self.reset_undo = PushButton("撤销", self)
        self.reset_undo.setIcon(FIF.RETURN)
        self.reset_undo_callback = None
        self.reset_undo.clicked.connect(self._invoke_reset_undo)
        self.reset_hint.hide()
        self.reset_undo.hide()
        reset_row.addWidget(self.reset_hint)
        reset_row.addWidget(self.reset_undo)
        self.reset_button = PushButton("恢复默认参数", self)
        self.reset_button.setIcon(FIF.SYNC)
        self.reset_button.clicked.connect(lambda checked=False: self.resetRequested.emit())
        reset_row.addWidget(self.reset_button)
        self.vbox.addLayout(reset_row)

        self.vbox.addStretch()

    def _select_theme(self, index):
        self.themeRequested.emit([Theme.LIGHT, Theme.DARK, Theme.AUTO][index])

    def show_reset_undo(self, callback):
        self.reset_undo_callback = callback
        self.reset_hint.show()
        self.reset_undo.show()
        return self.reset_undo

    def _invoke_reset_undo(self):
        callback = self.reset_undo_callback
        self.reset_undo_callback = None
        if callback is not None:
            callback()

    def hide_reset_undo(self):
        self.reset_hint.hide()
        self.reset_undo.hide()


class AboutPage(Page):
    def __init__(self, parent=None):
        super().__init__("about", parent)
        page_heading(self.vbox, "关于")
        icon_path = Path(__file__).resolve().parents[2] / "assets" / "app.svg"
        icon = QIcon(str(icon_path)).pixmap(112, 112)
        icon_label = QLabel(self)
        icon_label.setPixmap(icon)
        icon_label.setFixedSize(112, 112)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon_row.addWidget(icon_label)
        icon_row.addStretch()
        self.vbox.addLayout(icon_row)
        title = TitleLabel("JiYu Attack Next", self)
        title.setAlignment(Qt.AlignCenter)
        self.vbox.addWidget(title)
        subtitle = BodyLabel("极域学生端 UDP 控制报文测试工具", self)
        subtitle.setAlignment(Qt.AlignCenter)
        self.vbox.addWidget(subtitle)
        self.vbox.addSpacing(8)
        for label, url, text, icon in [
            ("作者", "https://github.com/JasonFang0109c", "JasonFang0109", FIF.GITHUB),
            ("GitHub", "https://github.com/JasonFang0109c", "https://github.com/JasonFang0109c", FIF.LINK),
            ("上游仓库", "https://github.com/ht0Ruial/Jiyu_udp_attack", "https://github.com/ht0Ruial/Jiyu_udp_attack", FIF.LINK),
        ]:
            row = QHBoxLayout()
            row.addWidget(BodyLabel(label, self))
            button = HyperlinkButton(url, text, self, icon=icon)
            button.setMaximumWidth(button.sizeHint().width())
            row.addWidget(button)
            row.addStretch()
            self.vbox.addLayout(row)
        self.vbox.addSpacing(12)
        self.vbox.addWidget(BodyLabel("组件版本", self))
        for title, package in [("PySide6", "PySide6"), ("Fluent Widgets", "PySide6-Fluent-Widgets")]:
            version_row = QHBoxLayout()
            version_row.addWidget(CaptionLabel(title, self))
            version_row.addStretch()
            version_row.addWidget(CaptionLabel(version(package), self))
            self.vbox.addLayout(version_row)
        self.vbox.addStretch()
