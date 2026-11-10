"""校验版本号在包、命令行与打包配置之间保持一致。"""

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from app import __version__ as package_version
from app.shared import build_info, version
from app.start.parser import build_flat_parser

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
        # 版本号由 shared/version.py 单独维护，包入口重新导出。
        self.assertEqual(version.__version__, package_version)

    def test_cli_reports_version(self):
        with self.assertRaises(SystemExit) as raised:
            build_flat_parser().parse_args(["--version"])
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
            version.display_version("0.1.0-nightly.20261029", "1a8ede3"),
            "0.1.0-nightly.20261029-1a8ede3",
        )
        self.assertEqual(
            version.display_version("0.1.0-nightly.20261029-1a8ede3", "1a8ede3"),
            "0.1.0-nightly.20261029-1a8ede3",
        )
        self.assertEqual(version.display_version("0.1.0", ""), "0.1.0")

    def test_runtime_version_uses_bundled_display_version(self):
        # 打包后界面与命令行都读同一份 version.txt，因此都会带上提交哈希。
        target = (
            Path("build") / "test-versioning" / "display" / build_info.VERSION_FILE_NAME
        )
        version.write_version(target, "0.1.0-nightly.20261029-1a8ede3")
        self.addCleanup(lambda: target.unlink(missing_ok=True))
        with patch.object(sys, "_MEIPASS", str(target.parent), create=True):
            self.assertEqual(
                version.runtime_version(), "0.1.0-nightly.20261029-1a8ede3"
            )
            self.assertEqual(
                build_info.version_text(), "0.1.0-nightly.20261029-1a8ede3"
            )

    def test_build_does_not_force_admin_on_startup(self):
        project_root = Path(__file__).resolve().parents[2]
        spec = (project_root / "pack" / "JiYuAttackNext.spec").read_text(
            encoding="utf-8"
        )
        self.assertIn("uac_admin=False", spec)
        self.assertNotIn("uac_admin=True", spec)


class BuildResourceTests(unittest.TestCase):
    def test_source_and_bundle_use_the_same_icon_layout(self):
        from app.shared.resources import resource_path

        project_root = Path(__file__).resolve().parents[2]
        expected = project_root / "app" / "resources" / "icons" / "app.svg"
        with patch.object(sys, "_MEIPASS", None, create=True):
            self.assertEqual(resource_path("icons", "app.svg"), expected)
            self.assertTrue(expected.is_file())
        bundle_root = project_root / "build" / "resource-fixture"
        with patch.object(sys, "_MEIPASS", str(bundle_root), create=True):
            self.assertEqual(
                resource_path("icons", "app.svg"),
                bundle_root / "app" / "resources" / "icons" / "app.svg",
            )

    def test_packaging_uses_the_resource_icon_and_preserves_script_encoding(self):
        project_root = Path(__file__).resolve().parents[2]
        spec = (project_root / "pack" / "JiYuAttackNext.spec").read_text(
            encoding="utf-8"
        )
        self.assertIn('root / "app" / "resources" / "icons" / "app.svg"', spec)
        self.assertIn('"app/resources/icons"', spec)
        script_bytes = (project_root / "pack" / "build.ps1").read_bytes()
        self.assertTrue(script_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", script_bytes.replace(b"\r\n", b""))
        script = script_bytes.decode("utf-8-sig")
        self.assertIn("QIcon('app/resources/icons/app.svg')", script)
        self.assertIn("from app.shared.build_info import write_build_time", script)
        self.assertIn("from app.shared.version import write_version", script)


if __name__ == "__main__":
    unittest.main()
