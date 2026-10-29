from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

from app import __version__ as package_version
from app.gui import build_info
from cli import main as core


SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*)?"
    r"(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?$"
)


class VersionTests(unittest.TestCase):
    def test_package_version_is_semver(self):
        self.assertRegex(package_version, SEMVER_PATTERN)

    def test_cli_version_matches_package_version(self):
        # cli/main.py 需可单独复制运行，因此版本号在本地重复一次。
        self.assertEqual(core.__version__, package_version)

    def test_cli_reports_version(self):
        with self.assertRaises(SystemExit) as raised:
            core.parser.parse_args(["--version"])
        self.assertEqual(raised.exception.code, 0)

    def test_version_text_falls_back_to_package_version(self):
        with patch.object(sys, "_MEIPASS", str(Path("build") / "missing"), create=True):
            self.assertEqual(build_info.version_text(), package_version)

    def test_version_text_prefers_bundled_version(self):
        target = (Path("build") / "test-versioning" / "bundle"
                  / build_info.VERSION_FILE_NAME)
        build_info.write_version(target, "9.9.9")
        self.addCleanup(lambda: target.unlink(missing_ok=True))
        with patch.object(sys, "_MEIPASS", str(target.parent), create=True):
            self.assertEqual(build_info.version_text(), "9.9.9")


if __name__ == "__main__":
    unittest.main()
