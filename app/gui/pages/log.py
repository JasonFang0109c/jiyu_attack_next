"""页面实现。"""

from .common import *
from .common import ASSET_ROOT


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
