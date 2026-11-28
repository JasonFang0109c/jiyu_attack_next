"""以 SYSTEM 计划任务执行远程命令的离线回归测试。"""

import urllib.request
from base64 import b64decode

import NeoJiYuTrainer.Packets.Codec as codec
import NeoJiYuTrainer.Packets.Elevated as elevated
from Tests.Fixtures.Offline import OfflineCase


class ElevatedTests(OfflineCase):
    def test_script_registers_and_runs_system_task(self):
        script = elevated.elevated_script("taskkill /f /im calc.exe")
        self.assertIn("schtasks /Create", script)
        self.assertIn("/RU 'NT AUTHORITY\\SYSTEM'", script)
        self.assertIn("/RL HIGHEST", script)
        self.assertIn("schtasks /Run", script)
        self.assertIn("schtasks /Delete", script)
        # 命令正文不进脚本原文，避免代码页问题。
        self.assertNotIn("taskkill", script)

    def test_script_polls_task_instead_of_blind_sleep(self):
        script = elevated.elevated_script("cmd /c echo hi")
        # 轮询任务状态：命令跑完立刻删任务，不再整段盲等固定秒数。
        self.assertIn("Diagnostics.Stopwatch", script)
        self.assertIn("LastRunTime", script)
        self.assertIn(
            "Start-Sleep -Milliseconds %d" % elevated.TASK_POLL_MILLISECONDS, script
        )
        self.assertNotIn("Start-Sleep -Seconds", script)

    def test_script_carries_command_as_utf16_base64(self):
        command = "cmd /c echo 中文"
        script = elevated.elevated_script(command)
        encoded = script.split("$b='", 1)[1].split("'", 1)[0]
        self.assertEqual(b64decode(encoded).decode("utf-16le"), command)

    def test_script_rejects_nul(self):
        with self.assertRaises(ValueError):
            elevated.elevated_script("a\x00b")

    def test_command_is_one_packet_within_limit(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        command = elevated.elevated_command("127.0.0.1", "whoami")
        self.assertIn("DownloadString", command)
        self.assertIn(elevated.SCRIPT_PATH, command)
        self.assertLessEqual(len(command), 163)
        packets = elevated.elevated_packets("127.0.0.1", "whoami")
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0], codec.pkg_sendlist("-c", command))

    def test_server_serves_script_holding_the_command(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        server = elevated.ElevatedServer("127.0.0.1", "whoami")
        server.start()
        try:
            with urllib.request.urlopen(server.url, timeout=5) as response:
                body = response.read().decode("utf-8")
            self.assertEqual(body, server.script)
            self.assertTrue(server.wait(5))
        finally:
            server.close()
        self.assertTrue(server.closed)

    def test_payload_hint_mentions_system_task(self):
        hint = elevated.payload_hint()
        self.assertIn("SYSTEM", hint)
        self.assertIn("报文 1 条", hint)
