"""Windows 端口表读取的边界条件测试。"""

import ctypes
import unittest
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import patch

from app.system.windows import ports


class PortTableTests(unittest.TestCase):
    """验证 IP Helper 表大小变化时的重试与错误传播。"""

    def test_read_rows_retries_when_table_grows_between_calls(self):
        calls = 0

        def read_table(buffer, size, ordered, family, table_class, reserved):
            nonlocal calls
            calls += 1
            if buffer is None:
                ctypes.cast(size, ctypes.POINTER(wintypes.DWORD)).contents.value = 4
                return ports._ERROR_INSUFFICIENT_BUFFER
            if calls == 2:
                ctypes.cast(size, ctypes.POINTER(wintypes.DWORD)).contents.value = 8
                return ports._ERROR_INSUFFICIENT_BUFFER
            ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value = 0
            return ports._NO_ERROR

        with patch.object(
            ports,
            "_iphlpapi",
            return_value=SimpleNamespace(GetExtendedUdpTable=read_table),
        ):
            self.assertEqual(
                ports._read_rows(
                    "GetExtendedUdpTable",
                    ports.UDP_TABLE_OWNER_PID,
                    ports._MibUdpRowOwnerPid,
                ),
                [],
            )
        self.assertEqual(calls, 3)

    def test_read_rows_propagates_non_buffer_errors(self):
        def read_table(buffer, size, ordered, family, table_class, reserved):
            ctypes.cast(size, ctypes.POINTER(wintypes.DWORD)).contents.value = 4
            return 5

        with (
            patch.object(
                ports,
                "_iphlpapi",
                return_value=SimpleNamespace(GetExtendedUdpTable=read_table),
            ),
            self.assertRaisesRegex(OSError, "读取端口表失败"),
        ):
            ports._read_rows(
                "GetExtendedUdpTable",
                ports.UDP_TABLE_OWNER_PID,
                ports._MibUdpRowOwnerPid,
            )


if __name__ == "__main__":
    unittest.main()
