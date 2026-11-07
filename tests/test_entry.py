"""命令行入口的测试：帮助输出、参数分发与打包后的入口行为。"""

import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from app import core
from app.__main__ import _show_cli_console, main
from app.cli.main import print_delivery


class EntryTests(unittest.TestCase):
    def test_package_cli_help_works(self):
        project_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", "-m", "app", "-h"],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        # 顶层帮助按图形界面的分组组织，具体参数在子命令的帮助里。
        for name in ("remote", "teacher", "local"):
            self.assertIn(name, result.stdout)

    def test_group_help_lists_message_options(self):
        project_root = Path(__file__).resolve().parents[1]
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
        project_root = Path(__file__).resolve().parents[1]
        program = (
            "import sys; from app.cli.main import parser; "
            "assert not any(name.startswith('PySide6') for name in sys.modules); "
            "parser.parse_args(['-h'])"
        )
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
        with patch("app.gui.app.main", return_value=7) as launch:
            self.assertEqual(main([]), 7)
        launch.assert_called_once_with()

    def test_cli_arguments_dispatch_to_cli(self):
        arguments = ["-ip", "10.49.151.29", "-msg", "Hello"]
        with (
            patch("app.__main__._show_cli_console") as show,
            patch("app.cli.main.main", return_value=3) as run_cli,
        ):
            self.assertEqual(main(arguments), 3)
        show.assert_called_once_with()
        run_cli.assert_called_once_with(arguments)

    def test_cli_console_keeps_streams_that_already_exist(self):
        with (
            patch("app.__main__.sys.stdout", new=io.StringIO()),
            patch("app.__main__.sys.stderr", new=io.StringIO()),
            patch("app.__main__._rebind_inherited_streams") as rebind,
        ):
            _show_cli_console()
        rebind.assert_not_called()

    def test_console_helper_never_allocates_a_window(self):
        source = Path(__file__).resolve().parents[1] / "app" / "__main__.py"
        # 窗口化子系统里 AllocConsole 一定会弹出新窗口，入口不得再使用它。
        self.assertNotIn("AllocConsole", source.read_text(encoding="utf-8"))

    def test_firewall_helper_dispatch_skips_console(self):
        arguments = ["--firewall-helper", "block", "--firewall-result", "result.json"]
        with (
            patch("app.__main__._show_cli_console") as show,
            patch("app.cli.main.main", return_value=0) as run_cli,
        ):
            self.assertEqual(main(arguments), 0)
        show.assert_not_called()
        run_cli.assert_called_once_with(arguments)

    def test_frozen_entry_runs_as_main_without_package_context(self):
        project_root = Path(__file__).resolve().parents[1]
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
        self.assertIn("0.1.0", result.stdout)

    def test_unified_entry_runs_cli_without_importing_qt(self):
        project_root = Path(__file__).resolve().parents[1]
        program = (
            "import sys\n"
            "from app.__main__ import main\n"
            "assert not any(name.startswith('PySide6') for name in sys.modules)\n"
            "try:\n"
            "    main(['-h'])\n"
            "except SystemExit as error:\n"
            "    assert error.code == 0, error.code\n"
        )
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
        self.assertIn("teacher", result.stdout)


if __name__ == "__main__":
    unittest.main()


class DeliveryReportTests(unittest.TestCase):
    def test_delivery_report_marks_status_per_target(self):
        outcome = core.SendOutcome(
            sent=3,
            deliveries=(
                core.Delivery("10.0.0.1", 2, core.DeliveryState.DELIVERED),
                core.Delivery("10.0.0.2", 1, core.DeliveryState.REJECTED, "端口未响应"),
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
