"""卸载服务测试。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.features.uninstall import service


class UninstallTests(unittest.TestCase):
    def test_remove_shortcuts_skips_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            shortcut = Path(directory) / "JiYu Attack Next.lnk"
            shortcut.write_text("x", encoding="utf-8")
            with patch.object(service, "shortcut_paths", return_value=[shortcut]):
                removed = service.remove_shortcuts()
            self.assertEqual(removed, [str(shortcut)])
            self.assertFalse(shortcut.exists())

    def test_remove_data(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "JiYuAttackNextData"
            target.mkdir()
            (target / "settings.json").write_text("{}", encoding="utf-8")
            self.assertTrue(service.remove_data(target))
            self.assertFalse(target.exists())

    def test_run_uninstall_keeps_data_when_requested(self):
        with (
            patch.object(service, "remove_shortcuts", return_value=["a.lnk"]),
            patch.object(service, "remove_driver_service", return_value=""),
            patch.object(service, "install_root", return_value=None),
            patch.object(service, "remove_data") as remove_data,
        ):
            result = service.run_uninstall(keep_user_data=True, remove_driver=True)
        self.assertEqual(result["shortcuts"], ["a.lnk"])
        self.assertFalse(result["data_removed"])
        remove_data.assert_not_called()


if __name__ == "__main__":
    unittest.main()
