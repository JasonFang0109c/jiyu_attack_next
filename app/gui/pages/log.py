"""运行日志页：筛选、勾选、导出与删除运行日志。"""

from PySide6.QtCore import QSignalBlocker, Qt, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QTableWidgetItem
from qfluentwidgets import CaptionLabel, ComboBox, FluentIcon as FIF, SearchLineEdit

from ..components import SectionCard, page_heading, tool_button
from ..models import LOG_LEVELS
from .common import LogHeaderView, LogTableWidget, Page, table_widget


class LogPage(Page):
    """展示运行日志，支持按关键字、功能与级别筛选。

    Attributes:
        store: 日志存储，页面通过信号与其保持同步。
    """

    exportSelectedRequested = Signal(object)
    deleteSelectedRequested = Signal(object)
    cancelRequested = Signal()

    def __init__(self, store, parent=None):
        super().__init__("logs", parent)
        self.store = store
        # 行号与 uid 双向映射，配合缓存的可搜索文本，
        # 刷新统计时不必再逐个单元格取文本。
        self._row_by_uid = {}
        self._uid_by_row = []
        self._meta_by_uid = {}
        # 勾选与可见集合按 uid 记录，删除或淘汰行时不会错位。
        self._checked_uids = set()
        self._visible_uids = set()
        self._query = ""
        self._category = "全部功能"
        self._level = "全部级别"
        # 回填历史日志时先挂起筛选，最后统一计算一次可见行。
        self._suspend_filter = False
        page_heading(self.vbox, "运行日志")
        toolbar = QHBoxLayout()
        self.search = SearchLineEdit(self)
        self.search.setPlaceholderText("搜索日志")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        self.category = ComboBox(self)
        self.category.addItems(
            [
                "全部功能",
                "应用",
                "文本消息",
                "远程命令",
                "设备操作",
                "文件传送",
                "本机信息",
                "防火墙",
                "运行日志",
            ]
        )
        self.category.currentIndexChanged.connect(self.apply_filter)
        self.category.setMinimumWidth(130)
        self.level_filter = ComboBox(self)
        self.level_filter.addItems(["全部级别"] + [str(level) for level in LOG_LEVELS])
        self.level_filter.currentIndexChanged.connect(self.apply_filter)
        self.level_filter.setMinimumWidth(120)
        self.cancel_button = tool_button(
            FIF.CANCEL, "取消当前发送", self, self.cancelRequested.emit
        )
        self.cancel_button.setEnabled(False)
        self.export_button = tool_button(
            FIF.SAVE, "导出选中日志", self, self._export_selected
        )
        self.delete_button = tool_button(
            FIF.DELETE, "删除选中日志", self, self._delete_selected
        )
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.category)
        toolbar.addWidget(self.level_filter)
        for button in [self.cancel_button, self.export_button, self.delete_button]:
            toolbar.addWidget(button)

        self.content_card = SectionCard(self, spacing=10)
        self.content_card.body.addLayout(toolbar)
        self.table = table_widget(
            ["", "时间", "级别", "功能", "内容", "线程", "输出位置"],
            self.content_card,
            LogTableWidget,
        )
        self.table.setHorizontalHeader(LogHeaderView(Qt.Horizontal, self.table))
        header = self.table.horizontalHeader()
        self.select_all_checkbox = header.select_all_checkbox
        self.select_all_checkbox.toggled.connect(self._toggle_visible_rows)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(40)
        for column, width in (
            (0, 42),
            (1, 190),
            (2, 112),
            (3, 96),
            (4, 220),
            (5, 145),
            (6, 165),
        ):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            self.table.setColumnWidth(column, width)
        self.table.itemChanged.connect(self._item_changed)
        self.table.itemClicked.connect(self._item_clicked)
        self.table.horizontalScrollBar().valueChanged.connect(
            self._position_header_checkbox
        )
        self.content_card.body.addWidget(self.table, 1)
        self.count_label = CaptionLabel("0 条记录", self.content_card)
        self.content_card.body.addWidget(self.count_label)
        self.vbox.addWidget(self.content_card, 1)
        store.added.connect(self._append_entry)
        store.removed.connect(self._remove_entries)
        store.cleared.connect(self._clear_entries)
        store.levelChanged.connect(self._level_changed)
        self._suspend_filter = True
        try:
            for entry in self.store.entries:
                self._append_entry(entry)
        finally:
            self._suspend_filter = False
        self.apply_filter()
        self._position_header_checkbox()

    @Slot(object)
    def _append_entry(self, entry):
        if self.table.rowCount() >= self.store.entries.maxlen:
            self._drop_row(0)
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
        self._uid_by_row.append(entry.uid)
        self.table.setRowHeight(row, 38)
        # 筛选字段预先算好，后续刷新只做字符串比较。
        self._meta_by_uid[entry.uid] = (
            entry.category,
            str(entry.level),
            self._entry_search_text(entry),
        )
        if self._suspend_filter:
            return
        matched = self._refresh_row(row, entry.uid)
        self._update_selection_controls()
        if matched:
            self.table.scrollToBottom()

    @staticmethod
    def _entry_search_text(entry):
        """拼接参与搜索的字段，避免刷新筛选时再读单元格文本。"""
        return " ".join(
            [
                entry.time,
                str(entry.level),
                entry.category,
                entry.message,
                "%s (%d)" % (entry.thread_name, entry.thread_id),
                "%s:%d" % (entry.logger_name, entry.line_number),
            ]
        ).casefold()

    def _rebuild_row_map(self):
        """按当前表格顺序重建 uid 与行号的映射。"""
        self._uid_by_row = []
        self._row_by_uid = {}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            uid = int(item.data(Qt.UserRole))
            self._uid_by_row.append(uid)
            self._row_by_uid[uid] = row
        known = set(self._uid_by_row)
        self._checked_uids &= known
        self._visible_uids &= known

    def _drop_row(self, row):
        """删除一行并同步行号映射，避免整表重建。"""
        uid = self._uid_by_row[row]
        self.table.removeRow(row)
        del self._uid_by_row[row]
        self._row_by_uid.pop(uid, None)
        self._meta_by_uid.pop(uid, None)
        self._checked_uids.discard(uid)
        self._visible_uids.discard(uid)
        # 被删行之后的记录整体前移一行。
        for index in range(row, len(self._uid_by_row)):
            self._row_by_uid[self._uid_by_row[index]] = index

    @Slot(str)
    def _level_changed(self, _level):
        self.apply_filter()

    def _matches(self, uid):
        """判断一条记录是否满足当前的关键字、功能与级别条件。"""
        category, level, text = self._meta_by_uid.get(uid, ("", "", ""))
        return (
            (self._category == "全部功能" or category == self._category)
            and (self._level == "全部级别" or level == self._level)
            and (not self._query or self._query in text)
        )

    def _refresh_row(self, row, uid):
        """按当前筛选条件更新一行的可见性，返回该行是否可见。"""
        matched = self._matches(uid)
        if matched:
            self._visible_uids.add(uid)
        else:
            self._visible_uids.discard(uid)
        self.table.setRowHidden(row, not matched)
        return matched

    def _entry_checked(self, uid):
        return uid in self._checked_uids

    def selected_entries(self):
        """按日志顺序返回勾选的记录。"""
        return [
            entry for entry in self.store.entries if entry.uid in self._checked_uids
        ]

    def selected_uids(self):
        """按日志顺序返回勾选记录的 uid。"""
        return [
            entry.uid for entry in self.store.entries if entry.uid in self._checked_uids
        ]

    def _update_selection_controls(self):
        visible_count = len(self._visible_uids)
        selected_count = len(self._checked_uids)
        all_checked = visible_count > 0 and self._visible_uids <= self._checked_uids
        with QSignalBlocker(self.select_all_checkbox):
            self.select_all_checkbox.setChecked(all_checked)
        self.select_all_checkbox.setEnabled(visible_count > 0)
        for button in (self.export_button, self.delete_button):
            button.setEnabled(selected_count > 0)
        self.count_label.setText(
            "%d / %d 条记录 | 运行等级 %s | 已选 %d 条"
            % (
                visible_count,
                self.table.rowCount(),
                str(self.store.minimum_level),
                selected_count,
            )
        )

    @Slot(bool)
    def _toggle_visible_rows(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        targets = list(self._visible_uids) if checked else list(self._uid_by_row)
        self.table.blockSignals(True)
        try:
            for uid in targets:
                row = self._row_by_uid.get(uid)
                if row is None:
                    continue
                item = self.table.item(row, 0)
                if item is not None:
                    item.setCheckState(state)
        finally:
            self.table.blockSignals(False)
        if checked:
            self._checked_uids |= self._visible_uids
        else:
            self._checked_uids.clear()
        self._update_selection_controls()

    def _position_header_checkbox(self, *_):
        self.table.horizontalHeader().position_checkbox()

    def _item_changed(self, item):
        if item.column() != 0:
            return
        row = item.row()
        if 0 <= row < len(self._uid_by_row):
            uid = self._uid_by_row[row]
            if item.checkState() == Qt.Checked:
                self._checked_uids.add(uid)
            else:
                self._checked_uids.discard(uid)
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
                if self._uid_by_row[row] in removed_uids:
                    self.table.removeRow(row)
                    del self._uid_by_row[row]
        finally:
            self.table.blockSignals(False)
        for uid in removed_uids:
            self._row_by_uid.pop(uid, None)
            self._meta_by_uid.pop(uid, None)
            self._checked_uids.discard(uid)
            self._visible_uids.discard(uid)
        self._rebuild_row_map()
        self.apply_filter()

    def _clear_entries(self):
        self.table.setRowCount(0)
        self._row_by_uid.clear()
        self._uid_by_row = []
        self._meta_by_uid.clear()
        self._checked_uids.clear()
        self._visible_uids.clear()
        self.apply_filter()

    def apply_filter(self, *_):
        """按关键字、功能与级别刷新可见行，最后同步勾选统计。"""
        self._query = self.search.text().casefold().strip()
        self._category = self.category.currentText()
        self._level = self.level_filter.currentText()
        table = self.table
        # 逐行 setRowHidden 会触发大量重排，先关闭更新再一次性刷新。
        table.setUpdatesEnabled(False)
        try:
            for row, uid in enumerate(self._uid_by_row):
                matched = self._matches(uid)
                if matched:
                    self._visible_uids.add(uid)
                else:
                    self._visible_uids.discard(uid)
                if table.isRowHidden(row) == matched:
                    table.setRowHidden(row, not matched)
        finally:
            table.setUpdatesEnabled(True)
        self._update_selection_controls()

    def export_text(self, entries=None):
        """把指定记录转成导出文本，None 表示导出全部记录。

        Args:
            entries: 待导出的日志记录列表。

        Returns:
            str: 可直接写入文件的文本。
        """
        source = self.store.entries if entries is None else entries
        return self.store.export_text(source)
