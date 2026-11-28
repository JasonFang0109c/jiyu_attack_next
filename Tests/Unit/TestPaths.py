"""运行数据目录迁移测试。"""

import shutil
import unittest
from pathlib import Path

import NeoJiYuTrainer.Shared.Paths as paths


class PortableDataDirTests(unittest.TestCase):
    """旧版数据目录改名到 data。"""

    def setUp(self):
        self.root = Path("Build") / "TestData" / "PathsTemp"
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

    def test_portable_data_dir_fixes_lowercase_directory_name(self):
        lowercase = self.root / "data"
        lowercase.mkdir()
        (lowercase / "settings.json").write_text("{}", encoding="utf-8")

        result = paths.portable_data_dir(self.root / "NeoJiYuTrainer.exe")

        entries = {entry.name for entry in self.root.iterdir()}
        self.assertIn(paths.DATA_DIRECTORY_NAME, entries)
        self.assertNotIn("data", entries)
        self.assertEqual(result.name, paths.DATA_DIRECTORY_NAME)
        self.assertTrue((result / "settings.json").is_file())

    def test_log_paths_live_in_log_directory(self):
        data = self.root / paths.DATA_DIRECTORY_NAME
        data.mkdir(parents=True, exist_ok=True)

        runtime = paths.portable_log_path(data)
        cli = paths.portable_cli_log_path(data)

        self.assertEqual(runtime.name, "Runtime.log")
        self.assertEqual(cli.name, "Cli.log")
        self.assertEqual(runtime.parent.name, paths.LOG_DIRECTORY_NAME)
        self.assertEqual(cli.parent.name, paths.LOG_DIRECTORY_NAME)

    def test_migrate_legacy_logs_moves_files_into_log(self):
        data = self.root / paths.DATA_DIRECTORY_NAME
        data.mkdir(parents=True, exist_ok=True)
        (data / "runtime.log").write_text("旧界面日志", encoding="utf-8")
        (data / "cli.log").write_text("旧命令行日志", encoding="utf-8")
        crash = data / "Crash"
        crash.mkdir()
        (crash / "CrashInfo-1.txt").write_text("旧报告", encoding="utf-8")
        (crash / "Fatal.log").write_text("旧硬崩溃", encoding="utf-8")

        paths.migrate_legacy_logs(data)

        log_dir = data / "Log"
        self.assertFalse((data / "runtime.log").exists())
        self.assertFalse(crash.exists())
        self.assertEqual(
            (log_dir / "Runtime.log").read_text(encoding="utf-8"), "旧界面日志"
        )
        self.assertEqual(
            (log_dir / "Cli.log").read_text(encoding="utf-8"), "旧命令行日志"
        )
        self.assertEqual(
            (log_dir / "CrashInfo-1.txt").read_text(encoding="utf-8"), "旧报告"
        )
        self.assertEqual(
            (log_dir / "Fatal.log").read_text(encoding="utf-8"), "旧硬崩溃"
        )

    def test_migrate_legacy_logs_keeps_existing_target(self):
        data = self.root / paths.DATA_DIRECTORY_NAME
        data.mkdir(parents=True, exist_ok=True)
        (data / "runtime.log").write_text("旧界面日志", encoding="utf-8")
        log_dir = data / "Log"
        log_dir.mkdir()
        (log_dir / "Runtime.log").write_text("新界面日志", encoding="utf-8")

        paths.migrate_legacy_logs(data)

        self.assertEqual(
            (log_dir / "Runtime.log").read_text(encoding="utf-8"), "新界面日志"
        )
        self.assertTrue((data / "runtime.log").exists())
