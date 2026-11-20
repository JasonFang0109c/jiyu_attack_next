"""蓝屏脚本分片组装的离线回归测试。"""

import base64

import app.packets.blue_screen as blue_screen
import app.packets.codec as codec
import app.packets.constants as constants
from tests.fixtures.offline import OfflineCase


class BlueScreenTests(OfflineCase):
    def test_script_uses_system_scheduled_task(self):
        script = constants.BLUE_SCREEN_SCRIPT
        self.assertIn("taskkill /f /im svchost.exe", script)
        self.assertIn("/RU 'NT AUTHORITY\\SYSTEM'", script)
        self.assertIn("/RL HIGHEST", script)
        self.assertIn("/SC ONCE", script)
        self.assertIn("AddSeconds(30)", script)
        self.assertIn("/ST $s.ToString('HH\\:mm')", script)
        self.assertIn("/SD $s.ToString('MM\\/dd\\/yyyy')", script)
        self.assertIn("schtasks /Run /TN $t", script)
        self.assertIn(constants.BLUE_SCREEN_TASK_NAME, script)

    def test_commands_fit_single_command_channel(self):
        commands = blue_screen.blue_screen_commands()
        self.assertEqual(len(commands), 5)
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
