"""课堂防护 DLL 的 Python 侧协议与生命周期测试（不加载真实 DLL）。"""

import struct
import sys
import unittest
from unittest.mock import patch

import app.system.windows.guard as guard


class FakeChannel:
    """替代策略共享内存，记录每次写入的防护位。"""

    def __init__(self, pid):
        self.pid = pid
        self.flags = []
        self.closed = False

    def update(self, flags):
        self.flags.append(int(flags))

    def close(self):
        self.closed = True


class FakeProcess:
    """替代远程进程，记录导出调用顺序。"""

    def __init__(self, pid):
        self.pid = pid
        self.calls = []
        self.closed = False
        self.freed = []

    def load_library(self, dll_path):
        self.calls.append(("load", dll_path))
        return 0x1000

    def call_export(self, module, dll_path, name):
        self.calls.append(("call", name))
        if name == "JiyuGuardInstall":
            return 1
        return 1

    def free_library(self, module):
        self.freed.append(module)

    def close(self):
        self.closed = True


class GuardProtocolTests(unittest.TestCase):
    def test_policy_roundtrip(self):
        data = guard.pack_policy(15)
        self.assertEqual(len(data), 16)
        self.assertEqual(struct.unpack("<IIII", data)[:3], (0x3150474A, 1, 15))
        self.assertEqual(guard.unpack_policy(data), 15)

    def test_policy_rejects_bad_data(self):
        with self.assertRaises(ValueError):
            guard.unpack_policy(b"\x00" * 8)
        with self.assertRaises(ValueError):
            guard.unpack_policy(struct.pack("<IIII", 1, 1, 0, 0))

    def test_policy_name_and_supported(self):
        self.assertEqual(guard.policy_name(17600), "Local\\JiyuGuardPolicy_17600")
        self.assertEqual(guard.supported(), sys.platform == "win32")


class GuardSessionTests(unittest.TestCase):
    def _session(self):
        channel = FakeChannel(17600)
        process = FakeProcess(17600)
        session = guard.GuardSession(17600, "C:/app/resources/native/guard_x64.dll")
        return session, channel, process

    def test_start_update_and_stop(self):
        session, channel, process = self._session()
        with (
            patch.object(guard, "PolicyChannel", return_value=channel),
            patch.object(guard, "RemoteProcess", return_value=process),
        ):
            session.start(7)
            self.assertEqual(channel.flags, [7])
            self.assertIn(("call", "JiyuGuardInstall"), process.calls)
            session.update(3)
            self.assertEqual(channel.flags, [7, 3])
            self.assertIn(("call", "JiyuGuardRefresh"), process.calls)
            session.stop()
        self.assertTrue(channel.closed)
        self.assertTrue(process.closed)
        self.assertEqual(process.freed, [0x1000])

    def test_failed_install_rolls_back(self):
        session, channel, process = self._session()
        process.call_export = lambda module, dll_path, name: 0
        with (
            patch.object(guard, "PolicyChannel", return_value=channel),
            patch.object(guard, "RemoteProcess", return_value=process),
            self.assertRaises(RuntimeError),
        ):
            session.start(1)
        self.assertTrue(channel.closed)
        self.assertTrue(process.closed)

    def test_update_before_start_is_rejected(self):
        session = guard.GuardSession(1, "x.dll")
        with self.assertRaises(RuntimeError):
            session.update(1)


if __name__ == "__main__":
    unittest.main()
