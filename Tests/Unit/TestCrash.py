"""崩溃报告的行为测试。"""

import faulthandler
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from NeoJiYuTrainer.Shared import Crash


class CrashTests(unittest.TestCase):
    """验证报告写入、待提示标记与摘要。"""

    def setUp(self):
        self._root = tempfile.TemporaryDirectory(dir="Build")
        self.addCleanup(self._root.cleanup)
        self.data = Path(self._root.name) / "Data"
        self.data.mkdir(parents=True, exist_ok=True)
        self._hooks = (sys.excepthook, threading.excepthook, sys.unraisablehook)
        self.addCleanup(self._restore_hooks)
        self.captured = []

        def previous(exception_type, exception, tb):
            self.captured.append(exception_type)

        sys.excepthook = previous

    def _restore_hooks(self):
        sys.excepthook, threading.excepthook, sys.unraisablehook = self._hooks
        faulthandler.disable()
        stream = Crash._fatal_stream
        if stream is not None:
            stream.close()
        Crash._fatal_stream = None
        Crash._fatal_dir = None
        Crash._install_dir = None

    def test_install_creates_directory_and_chains_previous_hook(self):
        target = Crash.install(self.data)
        self.assertEqual(target, self.data / "Crash")
        self.assertTrue((target / "Fatal.log").is_file())
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
        self.assertEqual(self.captured, [RuntimeError])
        reports = list(target.glob("CrashInfo-*.txt"))
        self.assertEqual(len(reports), 1)
        text = reports[0].read_text(encoding="utf-8")
        self.assertIn("未捕获异常", text)
        self.assertIn("RuntimeError: boom", text)

    def test_pending_report_round_trip(self):
        Crash.install(self.data)
        try:
            raise ValueError("bad")
        except ValueError:
            sys.excepthook(*sys.exc_info())
        report = Crash.pending_report(self.data)
        self.assertIsNotNone(report)
        self.assertTrue(report.is_file())
        self.assertIn("ValueError", Crash.summary(report))
        Crash.clear_pending(self.data)
        self.assertIsNone(Crash.pending_report(self.data))

    def test_pending_report_ignores_missing_file(self):
        target = Crash.crash_dir(self.data)
        target.mkdir(parents=True, exist_ok=True)
        (target / Crash.PENDING_NAME).write_text(
            str(target / "CrashInfo-gone.txt"), encoding="utf-8"
        )
        self.assertIsNone(Crash.pending_report(self.data))

    def test_write_report_without_install(self):
        report = Crash.write_report(self.data, "手工记录", "细节")
        self.assertEqual(Crash.pending_report(self.data), report)
        self.assertIn("手工记录", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
