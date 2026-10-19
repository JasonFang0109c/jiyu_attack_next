from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app.__main__ import main


class EntryTests(unittest.TestCase):
    def run_cli(self, script, directory):
        return subprocess.run(
            [sys.executable, "-X", "utf8", "-B", str(script), "-h"],
            cwd=directory, capture_output=True, text=True, encoding="utf-8", timeout=10)

    def test_cli_launcher_works_outside_project_directory(self):
        script = Path(__file__).resolve().parents[1] / "cli" / "main.py"
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli(script, directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("-msg", result.stdout)
        self.assertIn("--msg-file", result.stdout)

    def test_single_script_can_be_copied_and_run_independently(self):
        project_root = Path(__file__).resolve().parents[1]
        source = project_root / "cli" / "main.py"
        isolation_root = project_root / "build" / "test-isolation"
        isolation_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=isolation_root) as directory:
            standalone = Path(directory) / "standalone.py"
            shutil.copyfile(source, standalone)
            result = self.run_cli(standalone, directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("standalone.py", result.stdout)
        self.assertIn("--msg-file", result.stdout)

    def test_cli_entry_does_not_import_qt(self):
        project_root = Path(__file__).resolve().parents[1]
        program = ("import sys; from cli.main import parser; "
                   "assert not any(name.startswith('PySide6') for name in sys.modules); "
                   "parser.parse_args(['-h'])")
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", "-c", program],
            cwd=project_root, capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_gui_package_entry_dispatches_to_gui(self):
        with patch("app.gui.app.main", return_value=7) as launch:
            self.assertEqual(main(), 7)
        launch.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
