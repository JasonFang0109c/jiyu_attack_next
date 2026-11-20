"""蓝屏脚本分片组装的离线回归测试。"""

import base64

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

    def test_payload_hint_reports_packet_count(self):
        hint = blue_screen.payload_hint()
        self.assertIn("NtRaiseHardError", hint)
        self.assertIn("%d 条" % len(blue_screen.blue_screen_commands()), hint)

    def test_commands_fit_single_command_channel(self):
        commands = blue_screen.blue_screen_commands()
        limit = constants.COMMAND_MAX_BYTES // 2
        for index, command in enumerate(commands):
            with self.subTest(index=index):
                self.assertLessEqual(len(command), limit)

    def test_first_command_writes_and_last_command_runs(self):
        commands = blue_screen.blue_screen_commands()
        self.assertIn("Set-Content", commands[0])
        self.assertNotIn("Add-Content", commands[0])
        for command in commands[1:-1]:
            self.assertIn("Add-Content", command)
        self.assertIn("iex", commands[-1])
        self.assertIn("FromBase64String", commands[-1])

    def test_chunks_decode_back_to_script(self):
        chunks = []
        for command in blue_screen.blue_screen_commands()[:-1]:
            start = command.index("'") + 1
            chunks.append(command[start:-2])
        decoded = base64.b64decode("".join(chunks)).decode("utf-8")
        self.assertEqual(decoded, constants.BLUE_SCREEN_SCRIPT)

    def test_packets_are_command_packets(self):
        commands = blue_screen.blue_screen_commands()
        expected = [codec.pkg_sendlist("-c", command) for command in commands]
        self.assertEqual(blue_screen.blue_screen_packets(), expected)
