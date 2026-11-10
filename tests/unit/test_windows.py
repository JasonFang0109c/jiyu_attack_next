"""按模块组织的离线回归测试。"""

from pathlib import Path
from unittest.mock import patch

import app.features.student.service as student_service
import app.system.windows.command as windows_command
import app.system.windows.elevation as elevation
from tests.fixtures.offline import OfflineCase


class WindowsTests(OfflineCase):
    def test_elevated_helper_uses_module_entry_when_not_frozen(self):
        seen = {}

        def fake(executable, parameters, directory=None, action=""):
            seen["executable"] = executable
            seen["parameters"] = parameters
            seen["directory"] = directory
            seen["action"] = action
            return 1

        with (
            patch.object(elevation, "_run_elevated_process", side_effect=fake),
            patch.object(elevation, "sys") as fake_sys,
        ):
            fake_sys.platform = "win32"
            fake_sys.executable = "python.exe"
            fake_sys.frozen = False
            with self.assertRaises(RuntimeError):
                student_service._run_student_elevated("17600")
        self.assertTrue(seen["parameters"].startswith("-m app"))
        self.assertTrue(seen["parameters"].endswith(".json"))
        self.assertEqual(
            Path(seen["directory"]).name,
            Path(__file__).resolve().parents[2].name,
        )

    def test_windows_output_decoding_supports_utf8_and_gbk(self):
        self.assertEqual(
            windows_command._decode_windows_output("规则已更新".encode("utf-8")),
            "规则已更新",
        )
        self.assertEqual(
            windows_command._decode_windows_output("服务已在运行".encode("gbk")),
            "服务已在运行",
        )
