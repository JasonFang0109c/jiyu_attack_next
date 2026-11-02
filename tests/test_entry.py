"""命令行入口的测试：帮助输出、参数分发与打包后的入口行为。"""

from pathlib import Path
import io
import subprocess
import sys
import unittest
from unittest.mock import patch

from app.__main__ import _show_cli_console, main


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
        self.assertIn("-msg", result.stdout)
        self.assertIn("--msg-file", result.stdout)


if __name__ == "__main__":
    unittest.main()
