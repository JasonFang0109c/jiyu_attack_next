"""校验版本号在包、命令行与打包配置之间保持一致。"""

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from app import __version__ as package_version
from app import core
from app.cli.main import parser
from app.gui import build_info

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
        # 版本号由 core/constants.py 单独维护，包入口重新导出。
        self.assertEqual(core.__version__, package_version)

    def test_cli_reports_version(self):
        with self.assertRaises(SystemExit) as raised:
            parser.parse_args(["--version"])
        self.assertEqual(raised.exception.code, 0)

    def test_version_text_falls_back_to_package_version(self):
        with patch.object(sys, "_MEIPASS", str(Path("build") / "missing"), create=True):
            self.assertEqual(build_info.version_text(), package_version)

    def test_version_text_prefers_bundled_version(self):
        target = (
            Path("build") / "test-versioning" / "bundle" / build_info.VERSION_FILE_NAME
        )
        build_info.write_version(target, "9.9.9")
        self.addCleanup(lambda: target.unlink(missing_ok=True))
        with patch.object(sys, "_MEIPASS", str(target.parent), create=True):
            self.assertEqual(build_info.version_text(), "9.9.9")

    def test_display_version_appends_commit_once(self):
        # 测试版在版本号后拼 7 位提交哈希，重复调用不会叠加。
        self.assertEqual(
            core.display_version("0.1.0-nightly.20261029", "1a8ede3"),
            "0.1.0-nightly.20261029-1a8ede3",
        )
        self.assertEqual(
            core.display_version("0.1.0-nightly.20261029-1a8ede3", "1a8ede3"),
            "0.1.0-nightly.20261029-1a8ede3",
        )
        self.assertEqual(core.display_version("0.1.0", ""), "0.1.0")

    def test_runtime_version_uses_bundled_display_version(self):
        # 打包后界面与命令行都读同一份 version.txt，因此都会带上提交哈希。
        target = (
            Path("build") / "test-versioning" / "display" / build_info.VERSION_FILE_NAME
        )
        core.write_version(target, "0.1.0-nightly.20261029-1a8ede3")
        self.addCleanup(lambda: target.unlink(missing_ok=True))
        with patch.object(sys, "_MEIPASS", str(target.parent), create=True):
            self.assertEqual(core.runtime_version(), "0.1.0-nightly.20261029-1a8ede3")
            self.assertEqual(
                build_info.version_text(), "0.1.0-nightly.20261029-1a8ede3"
            )

    def test_build_does_not_force_admin_on_startup(self):
        project_root = Path(__file__).resolve().parents[1]
        spec = (project_root / "packaging" / "JiYuAttackNext.spec").read_text(
            encoding="utf-8"
        )
        self.assertIn("uac_admin=False", spec)
        self.assertNotIn("uac_admin=True", spec)


if __name__ == "__main__":
    unittest.main()
