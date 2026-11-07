"""运行日志的并发写入、重写与信号顺序回归。"""

import inspect
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QApplication

from app.gui.models import LogEntry, LogStore


class _ObservedLock:
    def __init__(self, lock, attempted):
        self.lock = lock
        self.attempted = attempted

    def __enter__(self):
        if threading.current_thread().name == "gui-mutation":
            self.attempted.set()
        self.lock.acquire()
        return self

    def __exit__(self, *_exc):
        self.lock.release()


class _GatedHandle:
    def __init__(self, handle, started, release, attempted):
        self.handle = handle
        self.started = started
        self.release = release
        self.attempted = attempted

    def write(self, text):
        self.started.set()
        if not self.release.wait(5):
            raise TimeoutError("日志写入屏障未释放")
        return self.handle.write(text)

    def flush(self):
        self.handle.flush()

    def close(self):
        self.handle.close()
        self.attempted.set()


class _LogObserver(QObject):
    def __init__(self):
        super().__init__()
        self.events = []

    @Slot(object)
    def added(self, entry):
        self.events.append(("added", entry.uid))

    @Slot()
    def cleared(self):
        self.events.append(("cleared", None))


class LogStoreConcurrencyTests(unittest.TestCase):
    """用显式屏障控制句柄关闭和迭代期间的后台写入。"""

    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        Path("build").mkdir(exist_ok=True)
        temporary = TemporaryDirectory(prefix="log-concurrency-", dir="build")
        self.addCleanup(temporary.cleanup)
        self.log_path = Path(temporary.name) / "runtime.log"
        self.store = LogStore(log_path=self.log_path, minimum_level="INFO")
        self.addCleanup(self.store.close)

    def _start(self, function, errors, name):
        def run():
            try:
                function()
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=run, name=name, daemon=True)
        thread.start()
        return thread

    def test_rewrite_waits_for_inflight_append(self):
        for action in ("remove", "clear", "rewrite", "close", "disable"):
            with self.subTest(action=action):
                self.store.clear()
                self.store.log_path = self.log_path
                seed = self.store.warning("测试", "原记录")
                started = threading.Event()
                release = threading.Event()
                attempted = threading.Event()
                # 旧实现没有锁：由 close() 通知已关闭；修复后由锁通知正等待写入。
                lock = getattr(self.store, "_lock", threading.RLock())
                self.store._lock = _ObservedLock(lock, attempted)
                self.store._file_handle = _GatedHandle(
                    self.store._file_handle, started, release, attempted
                )
                errors = []
                writer = self._start(
                    lambda: self.store.warning("测试", "后台记录"),
                    errors,
                    "log-writer",
                )
                mutation = None
                actions = {
                    "remove": lambda seed=seed: self.store.remove_entries([seed.uid]),
                    "clear": self.store.clear,
                    "rewrite": self.store._rewrite_file,
                    "close": self.store.close,
                    "disable": lambda: setattr(self.store, "log_path", None),
                }
                try:
                    self.assertTrue(started.wait(5), "后台写入尚未到达屏障")
                    mutation = self._start(actions[action], errors, "gui-mutation")
                    self.assertTrue(attempted.wait(5), "变更尚未请求同一个句柄")
                finally:
                    release.set()
                    writer.join(5)
                    if mutation is not None:
                        mutation.join(5)
                    self.store._lock = lock
                self.assertFalse(writer.is_alive())
                self.assertIsNotNone(mutation)
                self.assertFalse(mutation.is_alive())
                self.assertEqual(errors, [])
                expected = self.store.export_text()
                self.assertEqual(
                    self.log_path.read_text(encoding="utf-8"),
                    expected + ("\n" if expected else ""),
                )

    def test_export_uses_snapshot_during_concurrent_append(self):
        first = self.store.warning("测试", "第一条")
        self.store.warning("测试", "第二条")
        started = threading.Event()
        release = threading.Event()
        results = []
        errors = []
        as_text = LogEntry.as_text

        def gated_text(entry):
            if (
                entry.uid == first.uid
                and threading.current_thread().name == "log-reader"
            ):
                started.set()
                if not release.wait(5):
                    raise TimeoutError("日志导出屏障未释放")
            return as_text(entry)

        with patch.object(LogEntry, "as_text", gated_text):
            reader = self._start(
                lambda: results.append(self.store.export_text()), errors, "log-reader"
            )
            try:
                self.assertTrue(started.wait(5))
                self.store.warning("测试", "之后追加")
            finally:
                release.set()
                reader.join(5)
        self.assertFalse(reader.is_alive())
        self.assertEqual(errors, [])
        self.assertIn("第一条", results[0])
        self.assertIn("第二条", results[0])
        self.assertNotIn("之后追加", results[0])

    def test_pending_worker_added_is_delivered_before_main_thread_clear(self):
        observer = _LogObserver()
        self.store.added.connect(observer.added)
        self.store.cleared.connect(observer.cleared)
        errors = []
        writer = self._start(
            lambda: self.store.warning("测试", "即将清除"), errors, "log-writer"
        )
        writer.join(5)
        self.assertFalse(writer.is_alive())
        self.assertEqual(errors, [])
        self.store.clear()
        self.application.processEvents()
        self.assertEqual(observer.events, [("added", 1), ("cleared", None)])
        self.assertEqual(list(self.store.entries), [])

    def test_snapshot_remains_stable_after_append_and_remove(self):
        first = self.store.warning("测试", "快照记录")
        snapshot = self.store.snapshot_entries()
        self.store.warning("测试", "随后追加")
        self.store.remove_entries([first.uid])
        self.assertEqual(snapshot, (first,))
        self.assertEqual(self.store.entries.maxlen, 2000)
        self.assertEqual(len(self.store.snapshot_entries()), 1)

    def test_owner_notification_runs_outside_lock_and_keeps_reentrant_order(self):
        events = []
        errors = []
        writers = []

        def on_added(entry):
            events.append(("added", entry.uid))
            if entry.uid == 1:
                writer = self._start(
                    lambda: self.store.warning("测试", "槽内后台追加"),
                    errors,
                    "slot-writer",
                )
                writers.append(writer)
                writer.join(5)
                self.store.clear()

        self.store.added.connect(on_added)
        self.store.cleared.connect(lambda: events.append(("cleared", None)))
        self.store.warning("测试", "触发同步通知")
        self.assertFalse(writers[0].is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(events, [("added", 1), ("added", 2), ("cleared", None)])
        self.application.processEvents()
        self.assertEqual(events, [("added", 1), ("added", 2), ("cleared", None)])

    def test_writer_location_and_thread_metadata_are_preserved(self):
        results = []
        errors = []

        def write():
            line = inspect.currentframe().f_lineno + 1
            entry = self.store.info("测试", "调用位置")
            results.append((line, threading.get_ident(), entry))

        writer = self._start(write, errors, "location-writer")
        writer.join(5)
        self.assertFalse(writer.is_alive())
        self.assertEqual(errors, [])
        line, thread_id, entry = results[0]
        self.assertEqual(entry.line_number, line)
        self.assertEqual(entry.thread_id, thread_id)
        self.assertEqual(entry.thread_name, "location-writer")
        self.assertEqual(entry.logger_name, f"{__name__}.{type(self).__qualname__}")


if __name__ == "__main__":
    unittest.main()
