"""验证原生目录与 JiYuTrainer 上游项目职责对应。"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE_ROOT = ROOT / "pack" / "native"


class NativeLayoutTests(unittest.TestCase):
    def test_native_projects_keep_hooks_and_driver_boundaries(self):
        self.assertTrue((NATIVE_ROOT / "hooks").is_dir())
        self.assertTrue((NATIVE_ROOT / "driver").is_dir())
        self.assertTrue((NATIVE_ROOT / "README.md").is_file())
        self.assertTrue((NATIVE_ROOT / "hooks" / "build.bat").is_file())
        self.assertTrue((NATIVE_ROOT / "driver" / "build.bat").is_file())

    def test_unused_upstream_projects_are_not_copied(self):
        for name in ("ui", "updater", "Debug", "Release"):
            with self.subTest(name=name):
                self.assertFalse((NATIVE_ROOT / name).exists())
