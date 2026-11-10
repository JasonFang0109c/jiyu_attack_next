"""文件传送页：选择文件或文件夹，预览目录结构并发起传送。"""

from PySide6.QtCore import QSignalBlocker, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QTreeWidgetItem,
)
from qfluentwidgets import BodyLabel, CaptionLabel, ProgressBar
from qfluentwidgets import FluentIcon as FIF

import app.features.files.service as files_service
from app.gui.theme import CONTROL_CORNER_RADIUS
from app.gui.widgets.common import (
    SectionCard,
    TargetControls,
    TaskFooter,
    info_button,
    page_heading,
    tool_button,
)
from app.gui.widgets.page import (
    CompactTreeItemDelegate,
    FileTreeHeader,
    FileTreeWidget,
    Page,
)


class FilePage(Page):
    """以树形结构管理待传送条目，支持按目录勾选与进度展示。"""

    chooseFilesRequested = Signal()
    chooseFolderRequested = Signal()
    deleteRequested = Signal()

    def __init__(self, state, parent=None):
        super().__init__("file", parent)
        self.items = []
        # 总字节数随添加与移除增量维护，刷新统计时不必每次重算整个列表。
        self._total_size = 0
        self._syncing = False
        self._busy = False
        self.info_button = info_button(
            "勾选项发送到目标桌面并保留文件夹结构；目标需支持远程命令和 curl。", self
        )
        page_heading(self.vbox, "文件传送", self.info_button)
        self.target_card = SectionCard(self)
        self.targets = TargetControls(state, self.target_card, show_round_options=False)
        self.target_card.body.addWidget(self.targets)
        self.vbox.addWidget(self.target_card)

        self.content_card = SectionCard(self, spacing=10)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(BodyLabel("待传送文件", self.content_card))
        self.count_label = CaptionLabel("0 个文件", self.content_card)
        row.addWidget(self.count_label)
        row.addStretch()
        self.delete_button = tool_button(
            FIF.DELETE, "删除选中文件", self.content_card, self.deleteRequested.emit
        )
        self.delete_button.setEnabled(False)
        row.addWidget(self.delete_button)
        self.choose_files_button = tool_button(
            FIF.DOCUMENT, "添加文件", self.content_card, self.chooseFilesRequested.emit
        )
        row.addWidget(self.choose_files_button)
        self.choose_folder_button = tool_button(
            FIF.FOLDER, "添加文件夹", self.content_card, self.chooseFolderRequested.emit
        )
        row.addWidget(self.choose_folder_button)
        self.content_card.body.addLayout(row)

        self.empty_label = CaptionLabel(
            "尚未选择文件。可一次添加多个文件或整个文件夹，勾选后点击“传送文件”。",
            self.content_card,
        )
        self.empty_label.setWordWrap(True)
        self.content_card.body.addWidget(self.empty_label)

        self.tree = FileTreeWidget(self.content_card)
        self.tree.setObjectName("transferFileTree")
        self.tree.setColumnCount(3)
        # 先设置边框与圆角，再安装带复选框的自定义表头；顺序颠倒时
        # Fluent 样式刷新会访问未完成布局的表头子控件。
        self.tree.setBorderVisible(True)
        self.tree.setBorderRadius(CONTROL_CORNER_RADIUS)
        header = FileTreeHeader(
            Qt.Horizontal,
            self.tree,
            tooltip="全选待传送文件",
            accessible_name="全选待传送文件",
        )
        self.tree.setHeader(header)
        self.tree.setItemDelegate(CompactTreeItemDelegate(self.tree))
        self.tree.setHeaderLabels(["名称", "大小", "路径"])
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(18)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setWordWrap(False)
        self.select_all_checkbox = header.select_all_checkbox
        # 三态复选框点击会按 未选→部分→全选 循环，这里按点击后的状态统一处理：
        # 未选表示清空选择，其余情况（含部分选中）都视为全选。
        self.select_all_checkbox.clicked.connect(self._header_check_state_changed)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 110)
        self.tree.setColumnWidth(2, 220)
        self.tree.hoverItemChanged.connect(self._hover_item_changed)
        self.tree.itemChanged.connect(self._item_changed)
        self.tree.itemClicked.connect(self._item_clicked)
        self.tree.itemExpanded.connect(lambda item: self._sync_ancestors(item))
        self.tree.itemCollapsed.connect(lambda item: self._sync_ancestors(item))
        self.tree.itemExpanded.connect(lambda item: header.position_checkbox())
        self.tree.itemCollapsed.connect(lambda item: header.position_checkbox())
        self.tree.verticalScrollBar().valueChanged.connect(header.position_checkbox)
        self.tree.horizontalScrollBar().valueChanged.connect(header.position_checkbox)
        self.content_card.body.addWidget(self.tree, 1)

        self.progress = ProgressBar(self.content_card)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.hide()
        self.content_card.body.addWidget(self.progress)
        self.progress_text = CaptionLabel("", self.content_card)
        self.progress_text.hide()
        self.content_card.body.addWidget(self.progress_text)

        self.vbox.addWidget(self.content_card, 1)

        self.footer_card = SectionCard(self, spacing=0, margins=(8, 8, 8, 8))
        self.footer = TaskFooter("传送文件", self.footer_card, FIF.SEND)
        self.footer_card.body.addWidget(self.footer)
        self.vbox.addWidget(self.footer_card)
        self._update_selection_controls()

    def add_paths(self, paths):
        """添加文件或文件夹，并按默认勾选加入待传送列表。"""
        current = list(self.items)
        states = self._check_states()
        existing = {relative.casefold() for _, relative, _ in current}
        added = []
        for path, relative, size in files_service.collect_transfer_items(paths):
            if relative.casefold() in existing:
                continue
            existing.add(relative.casefold())
            current.append((path, relative, size))
            added.append((path, relative, size))
        if not added:
            return 0, 0
        self.items = current
        self._total_size += sum(size for _, _, size in added)
        for _, relative, _ in added:
            states[relative.casefold()] = True
        self._rebuild_tree(states)
        self.empty_label.hide()
        self.tree.show()
        self.footer.set_status("已添加 %d 个文件" % len(added))
        return len(added), sum(size for _, _, size in added)

    def set_file(self, path):
        """添加单个文件，添加后默认勾选。"""
        return self.add_paths([path])

    def has_files(self):
        """返回待传送列表是否非空。"""
        return bool(self.items)

    def selected_items(self):
        """返回勾选的文件 (绝对路径, 目标相对路径) 列表。"""
        selected = []
        for item in self._file_items():
            if item.checkState(0) == Qt.Checked:
                path, relative, _ = item.data(0, Qt.UserRole + 1)
                selected.append((str(path), relative))
        return selected

    def selected_entries(self):
        """返回复选框选中的文件与整目录条目。"""
        entries = []
        for item in self._all_visible_items():
            if item.checkState(0) != Qt.Checked:
                continue
            kind, relative = item.data(0, Qt.UserRole)
            entries.append((kind, relative))
        return entries

    def remove_selected(self):
        """删除复选框选中的文件与文件夹，返回被移除的条目。"""
        targets = self.selected_entries()
        if not targets:
            return []
        directories = {relative for kind, relative in targets if kind == "dir"}
        files = {relative for kind, relative in targets if kind == "file"}

        def matched(relative):
            if relative in files:
                return True
            # 目录匹配只需要看自身与各级父路径，避免为每个文件遍历全部目录。
            candidate = relative
            while True:
                if candidate in directories:
                    return True
                candidate, _, _ = candidate.rpartition("/")
                if not candidate:
                    return False

        removed = []
        remaining = []
        for entry in self.items:
            if matched(entry[1]):
                removed.append(entry)
            else:
                remaining.append(entry)
        if not removed:
            return []
        self.items = remaining
        self._total_size -= sum(size for _, _, size in removed)
        states = self._check_states()
        for _, relative, _ in removed:
            states.pop(relative.casefold(), None)
        self._rebuild_tree(states)
        if not self.items:
            self.tree.hide()
            self.empty_label.show()
        self.footer.set_status("已移除 %d 个文件" % len(removed))
        return removed

    def _check_states(self):
        return {
            relative.casefold(): item.checkState(0) == Qt.Checked
            for item in self._file_items()
            for relative in [item.data(0, Qt.UserRole)[1]]
        }

    def _all_visible_items(self):
        def walk(parent):
            for index in range(parent.childCount()):
                item = parent.child(index)
                yield item
                yield from walk(item)

        yield from walk(self.tree.invisibleRootItem())

    def _file_items(self):
        return [
            item
            for item in self._all_visible_items()
            if item.data(0, Qt.UserRole)[0] == "file"
        ]

    def _rebuild_tree(self, states=None, expand=True):
        expanded = {
            item.data(0, Qt.UserRole)[1]
            for item in self._all_visible_items()
            if item.isExpanded()
        }
        self._syncing = True
        self.tree.blockSignals(True)
        try:
            self._hovered_item = None
            self.tree.reset_hover_item()
            self.tree.clear()
            folders = {}
            for path, relative, size in self.items:
                parts = relative.split("/")
                parent = self.tree.invisibleRootItem()
                for depth, name in enumerate(parts[:-1]):
                    key = "/".join(parts[: depth + 1])
                    folder = folders.get(key)
                    if folder is None:
                        folder = QTreeWidgetItem(parent, [name, "", key])
                        self._set_item_icon(folder, FIF.FOLDER.icon())
                        folder.setFlags(
                            Qt.ItemIsEnabled
                            | Qt.ItemIsSelectable
                            | Qt.ItemIsUserCheckable
                        )
                        folder.setData(0, Qt.UserRole, ("dir", key))
                        folder.setToolTip(0, "全选文件夹：%s" % key)
                        self._set_item_state_role(folder, Qt.Unchecked, hovered=False)
                        folders[key] = folder
                    parent = folder
                file_item = QTreeWidgetItem(
                    parent, [parts[-1], files_service.format_size(size), relative]
                )
                self._set_item_icon(file_item, FIF.DOCUMENT.icon())
                file_item.setFlags(
                    Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
                )
                file_item.setData(0, Qt.UserRole, ("file", relative))
                file_item.setData(0, Qt.UserRole + 1, (path, relative, size))
                file_item.setToolTip(0, str(path))
                checked = (
                    True if states is None else states.get(relative.casefold(), True)
                )
                self._set_item_state_role(
                    file_item, Qt.Checked if checked else Qt.Unchecked, hovered=False
                )
            # 树形展示按“文件夹在前、同类型按名称”排序，更接近资源管理器。
            self._sort_item(self.tree.invisibleRootItem())
            # 先同步最深层文件夹，再向上汇总，避免父文件夹状态过期。
            for folder in reversed(list(folders.values())):
                self._sync_folder_state(folder)
            if expand and not expanded:
                if len(self.items) <= 300:
                    self.tree.expandAll()
                else:
                    for key, folder in folders.items():
                        if "/" not in key:
                            folder.setExpanded(True)
            for key in expanded:
                folder = folders.get(key)
                if folder is not None:
                    folder.setExpanded(True)
        finally:
            self.tree.blockSignals(False)
            self._syncing = False
        self._update_selection_controls()

    def _sort_item(self, parent):
        # 一次性取出全部子项再排序回挂：逐个 takeChild(0) 每次都要搬移剩余子项。
        children = parent.takeChildren()
        children.sort(
            key=lambda item: (
                0 if item.data(0, Qt.UserRole)[0] == "dir" else 1,
                item.text(0).casefold(),
            )
        )
        parent.addChildren(children)
        for child in children:
            if child.childCount():
                self._sort_item(child)

    def _sync_folder_state(self, folder):
        children = [folder.child(index) for index in range(folder.childCount())]
        if not children:
            return Qt.Unchecked
        states = [child.checkState(0) for child in children]
        if all(state == Qt.Checked for state in states):
            state = Qt.Checked
        elif all(state == Qt.Unchecked for state in states):
            state = Qt.Unchecked
        else:
            state = Qt.PartiallyChecked
        self._set_item_state_role(folder, state)
        return state

    def _set_item_state(self, item, state):
        self._set_item_state_role(item, state)
        for index in range(item.childCount()):
            child = item.child(index)
            if child.childCount():
                self._set_item_state(child, state)
            else:
                self._set_item_state_role(child, state)

    def _set_item_icon(self, item, icon):
        item.setData(0, Qt.UserRole + 2, icon)
        item.setIcon(0, icon)

    def _set_item_state_role(self, item, state, hovered=None):
        if hovered is None:
            hovered = item is getattr(self, "_hovered_item", None)
        show_checkbox = hovered or state != Qt.Unchecked
        was_blocked = self.tree.blockSignals(True)
        try:
            if show_checkbox:
                item.setCheckState(0, state)
                item.setIcon(0, QIcon())
            else:
                item.setData(0, Qt.CheckStateRole, None)
                item.setIcon(0, item.data(0, Qt.UserRole + 2) or QIcon())
        finally:
            self.tree.blockSignals(was_blocked)

    def _hover_item_changed(self, item):
        previous = getattr(self, "_hovered_item", None)
        if item is previous:
            return
        if previous is not None:
            self._set_item_state_role(previous, previous.checkState(0), hovered=False)
        self._hovered_item = item
        if item is not None:
            self._set_item_state_role(item, item.checkState(0), hovered=True)

    def _sync_ancestors(self, item):
        parent = item.parent()
        while parent is not None:
            self._sync_folder_state(parent)
            parent = parent.parent()

    def _item_clicked(self, item, column):
        if column != 0:
            self._update_selection_controls()
            return
        # Qt 在点击后才切换复选状态，延后到下一轮事件同步文件夹状态。
        QTimer.singleShot(0, self._update_selection_controls)

    def _item_changed(self, item, column):
        if self._syncing or column != 0:
            return
        kind = item.data(0, Qt.UserRole)[0]
        if kind == "dir":
            self._syncing = True
            try:
                self.tree.blockSignals(True)
                self._set_item_state(item, item.checkState(0))
            finally:
                self.tree.blockSignals(False)
                self._syncing = False
        self._set_item_state_role(item, item.checkState(0))
        self._sync_ancestors(item)
        self._update_selection_controls()

    def _header_check_state_changed(self, _checked=False):
        if self._syncing:
            return
        checked = self.select_all_checkbox.checkState() != Qt.Unchecked
        self._syncing = True
        self.tree.blockSignals(True)
        try:
            for index in range(self.tree.topLevelItemCount()):
                self._set_item_state(
                    self.tree.topLevelItem(index),
                    Qt.Checked if checked else Qt.Unchecked,
                )
        finally:
            self.tree.blockSignals(False)
            self._syncing = False
        self._update_selection_controls()

    def _update_selection_controls(self):
        """按树的当前勾选状态刷新表头复选、按钮可用性与统计文本。"""
        # 一次遍历同时统计文件行、勾选数量与是否存在选中项，避免重复走整棵树。
        file_items = []
        checked = []
        any_selected = False
        for item in self._all_visible_items():
            selected = item.checkState(0) == Qt.Checked
            if selected:
                any_selected = True
            if item.data(0, Qt.UserRole)[0] != "file":
                continue
            file_items.append(item)
            if selected:
                checked.append(item)
        selected_size = sum(item.data(0, Qt.UserRole + 1)[2] for item in checked)
        total_size = self._total_size
        if not file_items:
            header_state = Qt.Unchecked
        elif len(checked) == len(file_items):
            header_state = Qt.Checked
        elif checked:
            header_state = Qt.PartiallyChecked
        else:
            header_state = Qt.Unchecked
        with QSignalBlocker(self.select_all_checkbox):
            self.select_all_checkbox.setCheckState(header_state)
        self.select_all_checkbox.setEnabled(bool(file_items))
        self.delete_button.setEnabled(any_selected)
        self.count_label.setText(
            "%d 个文件，共 %s | 已选 %d 个，%s"
            % (
                len(self.items),
                files_service.format_size(total_size),
                len(checked),
                files_service.format_size(selected_size),
            )
        )
        if not self._busy:
            self.footer.send_button.setEnabled(bool(checked))
        self.tree.header().position_checkbox()

    def set_progress(self, percent):
        """显示并更新当前目标的下载进度条。

        Args:
            percent: 进度百分比，超出 0~100 时按边界截断。
        """
        self.progress.show()
        self.progress_text.show()
        self.progress.setValue(max(0, min(100, int(percent))))
        self.progress_text.setText(
            "当前目标下载进度：%d%%" % max(0, min(100, int(percent)))
        )

    def reset_progress(self):
        """清空并隐藏进度条，任务结束后恢复初始状态。"""
        self.progress.setValue(0)
        self.progress.hide()
        self.progress_text.hide()

    def set_busy(self, busy, cancellable=False, queueable=False):
        """切换忙碌状态：锁定目标输入与文件操作，结束时刷新按钮可用性。"""
        self._busy = bool(busy)
        self.targets.setEnabled(not busy)
        for button in (
            self.choose_files_button,
            self.choose_folder_button,
            self.delete_button,
            self.tree,
        ):
            button.setEnabled(not busy)
        self.footer.set_busy(busy, cancellable, queueable)
        if not busy:
            self._update_selection_controls()
