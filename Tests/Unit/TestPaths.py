"""运行数据目录迁移测试。"""

import shutil
import unittest
from pathlib import Path

import NeoJiYuTrainer.Shared.Paths as paths


class PortableDataDirTests(unittest.TestCase):
    """旧版数据目录改名到 data。"""

    def setUp(self):
        self.root = Path("build") / "test-paths-temp"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    def _make_legacy(self, name):
        legacy = self.root / name
        legacy.mkdir()
        (legacy / "settings.json").write_text("{}", encoding="utf-8")
        return legacy

    def test_portable_data_dir_renames_previous_name(self):
        legacy = self._make_legacy("NeoJiYuTrainerData")

        result = paths.portable_data_dir(self.root / "NeoJiYuTrainer.exe")

        self.assertEqual(
            result.resolve(), (self.root / paths.DATA_DIRECTORY_NAME).resolve()
        )
        self.assertTrue(result.is_dir())
        self.assertFalse(legacy.exists())
        self.assertEqual((result / "settings.json").read_text(encoding="utf-8"), "{}")

    def test_portable_data_dir_renames_oldest_name(self):
        legacy = self._make_legacy("JiYuAttackNextData")

        result = paths.portable_data_dir(self.root / "NeoJiYuTrainer.exe")

        self.assertEqual(
            result.resolve(), (self.root / paths.DATA_DIRECTORY_NAME).resolve()
        )
        self.assertFalse(legacy.exists())
        self.assertTrue((result / "settings.json").is_file())

    def test_portable_data_dir_keeps_both_directories_when_target_exists(self):
        legacy = self._make_legacy("NeoJiYuTrainerData")
        target = self.root / paths.DATA_DIRECTORY_NAME
        target.mkdir()
        (target / "new.txt").write_text("new", encoding="utf-8")

        result = paths.portable_data_dir(self.root / "NeoJiYuTrainer.exe")

        self.assertEqual(result.resolve(), target.resolve())
        self.assertTrue((legacy / "settings.json").is_file())
        self.assertTrue((target / "new.txt").is_file())
