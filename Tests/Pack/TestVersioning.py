"""校验版本号在包、命令行与打包配置之间保持一致。"""

import re
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from NeoJiYuTrainer import __version__ as package_version
from NeoJiYuTrainer.Shared import BuildInfo as build_info
from NeoJiYuTrainer.Shared import Version as version
from NeoJiYuTrainer.Start.Parser import build_group_parser

SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*)?"
    r"(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?$"
)


class VersionTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(Path("Build") / "TestData" / "Versioning", ignore_errors=True)

    def test_package_version_is_semver(self):
        self.assertRegex(package_version, SEMVER_PATTERN)

    def test_cli_version_matches_package_version(self):
        # 版本号由 Shared/Version.py 单独维护，包入口重新导出。
        self.assertEqual(version.__version__, package_version)

    def test_cli_reports_version(self):
        with self.assertRaises(SystemExit) as raised:
            build_group_parser().parse_args(["--version"])
        self.assertEqual(raised.exception.code, 0)

    def test_version_text_falls_back_to_package_version(self):
        with patch.object(sys, "_MEIPASS", str(Path("Build") / "missing"), create=True):
            self.assertEqual(build_info.version_text(), package_version)

    def test_version_text_prefers_bundled_version(self):
        target = (
            Path("Build")
            / "TestData"
            / "Versioning"
            / "bundle"
            / build_info.VERSION_FILE_NAME
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
            Path("Build")
            / "TestData"
            / "Versioning"
            / "display"
            / build_info.VERSION_FILE_NAME
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
        spec = (project_root / "Pack" / "NeoJiYuTrainer.spec").read_text(
            encoding="utf-8"
        )
        self.assertIn("uac_admin=False", spec)
        self.assertNotIn("uac_admin=True", spec)


class BuildResourceTests(unittest.TestCase):
    def test_source_and_bundle_use_the_same_icon_layout(self):
        from NeoJiYuTrainer.Shared.Resources import resource_path

        project_root = Path(__file__).resolve().parents[2]
        expected = project_root / "NeoJiYuTrainer" / "Resources" / "Icons" / "App.svg"
        with patch.object(sys, "_MEIPASS", None, create=True):
            self.assertEqual(resource_path("Icons", "App.svg"), expected)
            self.assertTrue(expected.is_file())
        bundle_root = project_root / "Build" / "resource-fixture"
        with patch.object(sys, "_MEIPASS", str(bundle_root), create=True):
            self.assertEqual(
                resource_path("Icons", "App.svg"),
                bundle_root / "NeoJiYuTrainer" / "Resources" / "Icons" / "App.svg",
            )

    def test_packaging_uses_the_resource_icon_and_preserves_script_encoding(self):
        project_root = Path(__file__).resolve().parents[2]
        spec = (project_root / "Pack" / "NeoJiYuTrainer.spec").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'root / "NeoJiYuTrainer" / "Resources" / "Icons" / "App.svg"', spec
        )
        self.assertIn('"NeoJiYuTrainer/Resources/Icons"', spec)
        script_bytes = (project_root / "Pack" / "Build.ps1").read_bytes()
        self.assertTrue(script_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", script_bytes.replace(b"\r\n", b""))
        script = script_bytes.decode("utf-8-sig")
        self.assertIn("QIcon('NeoJiYuTrainer/Resources/Icons/App.svg')", script)
        self.assertIn(
            "from NeoJiYuTrainer.Shared.BuildInfo import write_build_time", script
        )
        self.assertIn("from NeoJiYuTrainer.Shared.Version import write_version", script)


if __name__ == "__main__":
    unittest.main()
