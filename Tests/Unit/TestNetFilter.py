"""极域网络过滤驱动卸载接口测试。"""

import unittest
from unittest.mock import patch

from NeoJiYuTrainer.System.Windows import NetFilter


class NetFilterTests(unittest.TestCase):
    def setUp(self):
        self.open_manager = self.enterContext(
            patch.object(NetFilter.advapi32, "OpenSCManagerW", return_value=100)
        )
        self.open_service = self.enterContext(
            patch.object(NetFilter.advapi32, "OpenServiceW", return_value=200)
        )
        self.control = self.enterContext(
            patch.object(NetFilter.advapi32, "ControlService", return_value=1)
        )
        self.delete = self.enterContext(
            patch.object(NetFilter.advapi32, "DeleteService", return_value=1)
        )
        self.enterContext(
            patch.object(NetFilter.advapi32, "CloseServiceHandle", return_value=1)
        )

    def test_uninstall_stops_deletes_and_cleans_registry(self):
        with patch.object(NetFilter, "force_delete_service_key") as force:
            message = NetFilter.uninstall()
        self.assertIn("已卸载并删除", message)
        self.control.assert_called_once()
        self.delete.assert_called_once_with(200)
        force.assert_called_once_with("TDNetFilter")

    def test_uninstall_reports_missing_service(self):
        self.open_service.return_value = 0
        with (
            patch.object(NetFilter, "force_delete_service_key") as force,
            patch.object(NetFilter.ctypes, "get_last_error", return_value=1060),
        ):
            message = NetFilter.uninstall()
        self.assertIn("没有在这台计算机上找到驱动", message)
        force.assert_not_called()

    def test_uninstall_cleans_registry_when_marked_for_delete(self):
        self.delete.return_value = 0
        with (
            patch.object(NetFilter, "force_delete_service_key") as force,
            patch.object(NetFilter.ctypes, "get_last_error", return_value=1072),
        ):
            message = NetFilter.uninstall()
        self.assertIn("请不要重复操作", message)
        force.assert_called_once_with("TDNetFilter")

    def test_uninstall_raises_when_manager_cannot_open(self):
        self.open_manager.return_value = 0
        with (
            patch.object(NetFilter.ctypes, "get_last_error", return_value=5),
            self.assertRaises(NetFilter.NetFilterError),
        ):
            NetFilter.uninstall()

    def test_uninstall_raises_when_stop_fails(self):
        self.control.return_value = 0
        with (
            patch.object(NetFilter.ctypes, "get_last_error", return_value=31),
            self.assertRaises(NetFilter.NetFilterError),
        ):
            NetFilter.uninstall()


if __name__ == "__main__":
    unittest.main()
