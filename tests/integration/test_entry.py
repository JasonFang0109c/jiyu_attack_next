"""命令行入口、控制台恢复与打包入口的离线回归。"""

import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import __version__
from app.__main__ import main
from app.features.send.cli import print_delivery
from app.start.console import _show_cli_console
from app.system.net.data import Delivery, DeliveryState, SendOutcome


class EntryTests(unittest.TestCase):
    def test_package_cli_help_works(self):
        project_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", "-m", "app", "-h"],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("restriction", "remote", "local"):
            self.assertIn(name, result.stdout)

    def test_group_help_lists_message_options(self):
        project_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                "-m",
                "app",
                "remote",
                "message",
                "-h",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("-msg", result.stdout)
        self.assertIn("--msg-file", result.stdout)

    def test_cli_entry_does_not_import_qt(self):
        project_root = Path(__file__).resolve().parents[2]
        program = """import sys
import app
from app.start import cli, parser
assert not any(name.startswith(('PySide6', 'qfluentwidgets')) for name in sys.modules)
for arguments in (['-h'], ['--version'], ['remote', 'message', '-h']):
    try:
        cli.main(arguments)
    except SystemExit as error:
        assert error.code == 0, error.code
    else:
        raise AssertionError('Expected help/version exit')
    assert not any(name.startswith(('PySide6', 'qfluentwidgets')) for name in sys.modules)
"""
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", "-c", program],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_gui_package_entry_dispatches_to_gui(self):
        # 启动分流只需要入口契约，避免为测试这个分支初始化 Qt。
        with (
            patch("app.start.service._show_cli_console") as show,
            patch.dict(sys.modules, {"app.start.gui": SimpleNamespace(main=lambda: 7)}),
        ):
            self.assertEqual(main([]), 7)
        show.assert_not_called()

    def test_cli_arguments_dispatch_to_cli(self):
        arguments = ["-ip", "10.49.151.29", "-msg", "Hello"]
        with (
            patch("app.start.service._show_cli_console") as show,
            patch("app.start.cli.main", return_value=3) as run_cli,
        ):
            self.assertEqual(main(arguments), 3)
        show.assert_called_once_with()
        run_cli.assert_called_once_with(arguments)

    def test_cli_console_keeps_streams_that_already_exist(self):
        with (
            patch("app.start.console.sys.stdout", new=io.StringIO()),
            patch("app.start.console.sys.stderr", new=io.StringIO()),
            patch("app.start.console._rebind_inherited_streams") as rebind,
        ):
            _show_cli_console()
        rebind.assert_not_called()

    def test_console_helper_never_allocates_a_window(self):
        source = Path(__file__).resolve().parents[2] / "app" / "start" / "console.py"
        self.assertNotIn("AllocConsole", source.read_text(encoding="utf-8"))

    def test_hidden_helpers_dispatch_without_console(self):
        for arguments in (
            ["--firewall-helper", "block", "--firewall-result", "result.json"],
            ["--student-helper", "--student-result", "result.json"],
        ):
            with (
                self.subTest(arguments=arguments),
                patch("app.start.service._show_cli_console") as show,
                patch("app.start.cli.main", return_value=0) as run_cli,
            ):
                self.assertEqual(main(arguments), 0)
            show.assert_not_called()
            run_cli.assert_called_once_with(arguments)

    def test_frozen_entry_runs_as_main_without_package_context(self):
        project_root = Path(__file__).resolve().parents[2]
        program = """import runpy, sys
sys.argv = ['JiYuAttackNext.exe', '--version']
runpy.run_path('app/__main__.py', run_name='__main__')
"""
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", "-c", program],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(__version__, result.stdout)

    def test_unified_entry_runs_cli_without_importing_qt(self):
        project_root = Path(__file__).resolve().parents[2]
        program = """import sys
from app.__main__ import main
assert 'app.start.gui' not in sys.modules
assert not any(name.startswith(('PySide6', 'qfluentwidgets')) for name in sys.modules)
for arguments in (['-h'], ['--version']):
    try:
        main(arguments)
    except SystemExit as error:
        assert error.code == 0, error.code
    else:
        raise AssertionError('Expected help/version exit')
    assert 'app.start.gui' not in sys.modules
    assert not any(name.startswith(('PySide6', 'qfluentwidgets')) for name in sys.modules)
"""
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", "-c", program],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("remote", result.stdout)


class DeliveryReportTests(unittest.TestCase):
    def test_delivery_report_marks_status_per_target(self):
        outcome = SendOutcome(
            sent=3,
            deliveries=(
                Delivery("10.0.0.1", 2, DeliveryState.DELIVERED),
                Delivery("10.0.0.2", 1, DeliveryState.REJECTED, "端口未响应"),
            ),
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            print_delivery(outcome)
        output = buffer.getvalue()
        self.assertIn("[成功] 10.0.0.1：已送达（2 个报文）", output)
        self.assertIn("[-] [失败] 10.0.0.2：失败：目标端口未响应", output)
        self.assertIn("共 2 个目标：成功 1，失败 1", output)


if __name__ == "__main__":
    unittest.main()
