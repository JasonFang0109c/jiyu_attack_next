"""日志页索引、分类筛选与快照读取的回归测试。"""

import os
import socket
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault(
    "QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen"
)

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication

from app.gui.models import LogStore
from app.gui.pages.log import LogPage


class LogPageTests(unittest.TestCase):
    """验证索引、分类筛选和快照读取保持一致。"""

    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        network_guard = patch.object(
            socket, "socket", side_effect=AssertionError("禁止真实网络通信")
        )
        network_guard.start()
        self.addCleanup(network_guard.stop)
        self.store = LogStore(minimum_level="INFO")
        self.page = LogPage(self.store)
        self.addCleanup(self.dispose_page)

    def dispose_page(self):
        """释放页面与待执行的滚动定时器，避免影响其他界面用例。"""
        page = self.page
        page._scroll_timer.stop()
        page.deleteLater()
        QCoreApplication.sendPostedEvents(page, QEvent.Type.DeferredDelete)
        self.store.close()

    def test_delete_first_or_middle_row_then_select_all(self):
        for removed_index in (0, 1):
            with self.subTest(removed_index=removed_index):
                self.store.clear()
                entries = [
                    self.store.info("应用", "记录 %d" % index) for index in range(4)
                ]
                removed = entries[removed_index]
                self.page.table.item(removed_index, 0).setCheckState(Qt.Checked)
                self.store.remove_entries([removed.uid])
                remaining = [entry for entry in entries if entry is not removed]
                self.assertEqual(self.page.selected_uids(), [])
                self.assertEqual(
                    self.page._row_by_uid,
                    {entry.uid: row for row, entry in enumerate(remaining)},
                )
                self.page.select_all_checkbox.click()
                self.assertEqual(self.page.selected_entries(), remaining)
                self.assertTrue(self.page.select_all_checkbox.isChecked())
                for row, entry in enumerate(remaining):
                    item = self.page.table.item(row, 0)
                    self.assertEqual(item.data(Qt.UserRole), entry.uid)
                    self.assertEqual(item.checkState(), Qt.Checked)
                self.page.select_all_checkbox.click()
                self.assertEqual(self.page.selected_uids(), [])
                self.assertTrue(
                    all(
                        self.page.table.item(row, 0).checkState() == Qt.Unchecked
                        for row in range(self.page.table.rowCount())
                    )
                )

    def test_select_all_after_deletion_respects_filter(self):
        removed = self.store.info("应用", "删除记录")
        first = self.store.info("文本消息", "保留消息一")
        hidden = self.store.info("应用", "隐藏记录")
        last = self.store.info("文本消息", "保留消息二")
        self.page.category.setCurrentIndex(self.page.category.findText("文本消息"))
        self.store.remove_entries([removed.uid])
        self.page.select_all_checkbox.click()
        self.assertEqual(self.page.selected_entries(), [first, last])
        for row, entry in enumerate((first, hidden, last)):
            item = self.page.table.item(row, 0)
            visible = entry.category == "文本消息"
            self.assertEqual(self.page.table.isRowHidden(row), not visible)
            self.assertEqual(item.checkState(), Qt.Checked if visible else Qt.Unchecked)
        self.page.category.setCurrentIndex(0)
        self.page.select_all_checkbox.click()
        self.assertEqual(self.page.selected_entries(), [first, hidden, last])
        self.page.select_all_checkbox.click()
        self.assertEqual(self.page.selected_uids(), [])
        self.assertTrue(
            all(
                self.page.table.item(row, 0).checkState() == Qt.Unchecked
                for row in range(self.page.table.rowCount())
            )
        )

    def test_batch_deletion_keeps_selection_when_new_row_is_appended(self):
        entries = [self.store.info("应用", "记录 %d" % index) for index in range(5)]
        self.page.select_all_checkbox.click()
        self.store.remove_entries([entries[0].uid, entries[2].uid])
        remaining = [entries[1], entries[3], entries[4]]
        self.assertEqual(self.page.selected_entries(), remaining)
        added = self.store.info("应用", "追加记录")
        self.assertFalse(self.page.select_all_checkbox.isChecked())
        self.page.select_all_checkbox.click()
        self.assertEqual(self.page.selected_entries(), [*remaining, added])
        self.page.table.item(0, 0).setCheckState(Qt.Unchecked)
        self.assertEqual(self.page.selected_entries(), [*remaining[1:], added])
        self.assertFalse(self.page.select_all_checkbox.isChecked())
        for row in range(1, self.page.table.rowCount()):
            self.assertEqual(self.page.table.item(row, 0).checkState(), Qt.Checked)

    def test_categories_include_history_and_preserve_active_filter(self):
        historical = self.store.info("反弹终端", "历史记录")
        old_page = self.page
        old_page._scroll_timer.stop()
        old_page.deleteLater()
        QCoreApplication.sendPostedEvents(old_page, QEvent.Type.DeferredDelete)
        self.page = LogPage(self.store)
        self.assertGreaterEqual(self.page.category.findText("反弹终端"), 0)
        self.page.category.setCurrentIndex(self.page.category.findText("反弹终端"))
        first = self.store.info("学生信息", "新分类记录一")
        count = self.page.category.count()
        second = self.store.info("学生信息", "新分类记录二")
        self.assertEqual(self.page.category.count(), count)
        self.assertEqual(self.page.category.currentText(), "反弹终端")
        self.assertEqual(self.page._visible_uids, {historical.uid})
        self.assertFalse(self.page.table.isRowHidden(0))
        self.assertTrue(self.page.table.isRowHidden(1))
        self.assertTrue(self.page.table.isRowHidden(2))
        self.page.category.setCurrentIndex(self.page.category.findText("学生信息"))
        self.assertEqual(self.page._visible_uids, {first.uid, second.uid})
        self.assertTrue(self.page.table.isRowHidden(0))
        self.assertFalse(self.page.table.isRowHidden(1))
        self.assertFalse(self.page.table.isRowHidden(2))

    def test_selection_and_export_use_store_snapshot(self):
        entry = self.store.info("应用", "快照记录")
        self.page.select_all_checkbox.click()
        with patch.object(
            self.store, "snapshot_entries", return_value=[entry]
        ) as snapshot:
            self.assertEqual(self.page.selected_entries(), [entry])
            self.assertEqual(self.page.selected_uids(), [entry.uid])
            self.assertEqual(snapshot.call_count, 2)
        with patch.object(self.store, "export_text", return_value="导出结果") as export:
            self.assertEqual(self.page.export_text(), "导出结果")
            export.assert_called_once_with(None)
            export.reset_mock()
            self.assertEqual(self.page.export_text([entry]), "导出结果")
            export.assert_called_once_with([entry])


if __name__ == "__main__":
    unittest.main()
