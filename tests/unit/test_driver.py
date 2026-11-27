"""JiyuGuard 驱动用户态接口测试。"""

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.system.windows import driver


class DriverProtocolTests(unittest.TestCase):
    def test_ctl_codes_match_windows_layout(self):
        self.assertEqual(driver.IOCTL_PROTECT, 0x00222000)
        self.assertEqual(driver.IOCTL_KILL, 0x00222008)

    def test_available_requires_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jiyu_guard_driver.sys"
            with patch.object(driver.sys, "platform", "win32"):
                self.assertFalse(driver.available(path))
                path.write_bytes(b"MZ")
                self.assertTrue(driver.available(path))

    def test_status_decodes_payload(self):
        session = driver.DriverSession(Path("unused.sys"))
        payload = struct.pack("<IIII", 1, 3, 1, 0)
        with patch.object(session, "_ioctl", return_value=payload):
            status = session.status()
        self.assertEqual(status.version, 1)
        self.assertEqual(status.protected_count, 3)
        self.assertTrue(status.callback_active)

    def test_protect_and_kill_pack_arguments(self):
        session = driver.DriverSession(Path("unused.sys"))
        calls = []
        with patch.object(
            session,
            "_ioctl",
            side_effect=lambda code, data, size=0: calls.append((code, data)),
        ):
            session.protect(123)
            session.kill(456, 7)
        self.assertEqual(calls[0], (driver.IOCTL_PROTECT, struct.pack("<I", 123)))
        self.assertEqual(calls[1], (driver.IOCTL_KILL, struct.pack("<II", 456, 7)))

    def test_kernel_kill_opens_and_closes_session(self):
        fake = unittest.mock.MagicMock()
        with patch.object(driver, "DriverSession", return_value=fake):
            self.assertTrue(driver.kernel_kill(123, 9))
        fake.open.assert_called_once_with()
        fake.kill.assert_called_once_with(123, 9)
        fake.close.assert_called_once_with()

    def test_kernel_kill_returns_false_when_driver_missing(self):
        fake = unittest.mock.MagicMock()
        fake.open.side_effect = OSError("missing")
        with patch.object(driver, "DriverSession", return_value=fake):
            self.assertFalse(driver.kernel_kill(123))
        fake.kill.assert_not_called()
        fake.close.assert_called_once_with()

    def test_install_creates_missing_service(self):
        session = driver.DriverSession(Path("C:/driver.sys"))
        calls = []

        def fake_run(*args):
            calls.append(args)
            return (0, "")

        with (
            patch.object(session, "service_state", return_value="absent"),
            patch.object(session, "_run_sc", side_effect=fake_run),
        ):
            session.install()
        self.assertEqual(calls[0][0], "create")
        self.assertEqual(calls[1], ("start", "JiyuGuardDriver"))


if __name__ == "__main__":
    unittest.main()
