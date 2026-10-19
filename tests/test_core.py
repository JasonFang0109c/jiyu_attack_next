import socket
import unittest
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from cli import main as core


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = core
        cls.network_guard = patch.object(
            socket, "socket",
            side_effect=AssertionError("测试期间禁止创建网络套接字"))
        cls.network_guard.start()

    @classmethod
    def tearDownClass(cls):
        cls.network_guard.stop()

    def message_text(self, packet):
        body = bytes(packet[self.core.MESSAGE_OFFSET:]).decode("utf-16le")
        return body.split("\x00", 1)[0]

    def command_text(self, packet):
        body = bytes(packet[self.core.COMMAND_OFFSET:]).decode("utf-16le")
        return body.split("\x00", 1)[0]

    def test_message_chunks(self):
        for text, parts in [
            ("a" * 448, 1),
            ("a" * 449, 2),
            ("中文" * 224, 1),
            ("中文" * 225, 2),
            ("😀" * 224, 1),
            ("😀" * 225, 2),
        ]:
            with self.subTest(text_length=len(text)):
                chunks = list(self.core.split_message(text))
                self.assertEqual(len(chunks), parts)
                self.assertEqual("".join(chunks), text)
                for chunk in chunks:
                    packet = self.core.pkg_sendlist("-msg", chunk)
                    self.assertEqual(len(packet), 954)
                    self.assertEqual(self.message_text(packet), chunk)

    def test_message_keeps_multiline_content(self):
        text = "第一行\n\n第二行\r\n😀\t结束\n" * 100
        chunks = list(self.core.split_message(text))
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), text)

    def test_templates_are_not_mutated(self):
        message_template = self.core.basicCMD["-msg"].copy()
        command_template = self.core.basicCMD["-c"].copy()
        first = self.core.pkg_sendlist("-msg", "第一条")
        second = self.core.pkg_sendlist("-msg", "另一条")
        command = self.core.pkg_sendlist("-c", "cmd.exe /c ipconfig")
        self.assertIsNot(first, second)
        self.assertEqual(self.message_text(first), "第一条")
        self.assertEqual(self.message_text(second), "另一条")
        self.assertEqual(self.command_text(command), "cmd.exe /c ipconfig")
        self.assertEqual(self.core.basicCMD["-msg"], message_template)
        self.assertEqual(self.core.basicCMD["-c"], command_template)

    def test_capacity_errors_are_explicit(self):
        with self.assertRaises(ValueError):
            list(self.core.split_message("a\x00b"))
        with self.assertRaises(ValueError):
            self.core.pkg_sendlist("-msg", "a" * 449)
        command_units = self.core.COMMAND_MAX_BYTES // 2
        with self.assertRaises(ValueError):
            self.core.pkg_sendlist("-c", "a" * (command_units + 1))

    def test_ip_formats(self):
        self.assertEqual(self.core.get_ip("192.168.1.10"), ["192.168.1.10"])
        self.assertEqual(self.core.get_ip("192.168.1.1-3")[:3],
                         ["192.168.1.1", "192.168.1.2", "192.168.1.3"])
        network = self.core.get_ip("192.168.1.0/24")
        self.assertEqual(len(network), 254)
        self.assertEqual(network[0], "192.168.1.1")
        self.assertEqual(network[-1], "192.168.1.254")

    def test_options_validation(self):
        good = self.core.SendOptions("192.168.1.10", message="通知")
        self.core.validate_options(good)
        bad_cases = [
            self.core.SendOptions("", message="通知"),
            self.core.SendOptions("bad-address", message="通知"),
            self.core.SendOptions("192.168.1.10"),
            self.core.SendOptions("192.168.1.10", port=0, message="通知"),
            self.core.SendOptions("192.168.1.10", loops=0, message="通知"),
            self.core.SendOptions("192.168.1.10", interval=-1, message="通知"),
            self.core.SendOptions("192.168.1.10", message="通知", extra="nc"),
        ]
        for options in bad_cases:
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    self.core.validate_options(options)

    def test_packet_preparation(self):
        options = self.core.SendOptions(
            "192.168.1.10", message="a" * 449, command="whoami")
        packets = self.core.prepare_packets(options)
        self.assertEqual(len(packets), 3)
        self.assertEqual(self.message_text(packets[0]) + self.message_text(packets[1]), "a" * 449)
        self.assertEqual(self.command_text(packets[2]), "whoami")

        options.extra = "s"
        packets = self.core.prepare_packets(options)
        self.assertIsNot(packets[-1], self.core.basicCMD["-s"])

    def test_invalid_reverse_range_is_rejected(self):
        for value in ["192.168.1.10-1", "192.168.1.0-10", "192.168.1.1-255"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.core.get_ip(value)

    def test_gui_send_uses_bytes_and_shared_transport(self):
        options = self.core.SendOptions("模拟目标", message="a" * 449,
                                       command="whoami", loops=2, interval=0)
        fake_socket = MagicMock()
        fake_socket.__enter__.return_value = fake_socket
        packets = [bytes(self.core.pkg_sendlist("-msg", chunk))
                   for chunk in self.core.split_message(options.message)]
        packets.append(bytes(self.core.pkg_sendlist("-c", options.command)))
        with patch.object(self.core, "get_ip", return_value=["模拟目标甲", "模拟目标乙"]):
            with patch.object(socket, "socket", return_value=fake_socket):
                count = self.core.execute_send(options)
        self.assertEqual(count, 12)
        self.assertEqual(fake_socket.sendto.call_args_list, [
            call(packet, (host, 4705))
            for _ in range(2) for host in ["模拟目标甲", "模拟目标乙"]
            for packet in packets])
        fake_socket.__exit__.assert_called_once()

    def test_cancellation_before_send_opens_no_socket(self):
        stopped = Event()
        stopped.set()
        options = self.core.SendOptions("模拟目标", message="通知", cancel_event=stopped)
        with patch.object(self.core, "get_ip", return_value=["模拟目标"]):
            with patch.object(socket, "socket") as factory:
                with self.assertRaisesRegex(RuntimeError, "操作已取消"):
                    self.core.execute_send(options)
                factory.assert_not_called()

    def test_cancellation_interrupts_long_interval(self):
        stopped = Event()
        options = self.core.SendOptions("模拟目标", message="通知",
                                       loops=2, interval=3600, cancel_event=stopped)
        fake_socket = MagicMock()
        fake_socket.__enter__.return_value = fake_socket

        def report(message):
            if "轮已发送" in message:
                stopped.set()

        with patch.object(self.core, "get_ip", return_value=["模拟目标"]):
            with patch.object(socket, "socket", return_value=fake_socket):
                with self.assertRaisesRegex(RuntimeError, "操作已取消"):
                    self.core.execute_send(options, report)
        fake_socket.sendto.assert_called_once()
        fake_socket.__exit__.assert_called_once()

    def test_send_error_closes_socket(self):
        fake_socket = MagicMock()
        fake_socket.__enter__.return_value = fake_socket
        fake_socket.sendto.side_effect = OSError("模拟发送失败")
        with patch.object(self.core, "get_ip", return_value=["模拟目标"]):
            with patch.object(socket, "socket", return_value=fake_socket):
                with self.assertRaisesRegex(OSError, "模拟发送失败"):
                    self.core.send([[1, 2, 3]], "模拟目标")
        fake_socket.__exit__.assert_called_once()

    def test_local_ports_match_exact_pids_and_wildcard_addresses(self):
        tasks = SimpleNamespace(returncode=0, stderr="", stdout=
                                '"StudentMain.exe","123"\n"other.exe","5123"\n')
        ports = SimpleNamespace(returncode=0, stderr="", stdout=
                                "UDP 0.0.0.0:4705 *:* 123\n"
                                "UDP [::]:4705 *:* 123\n"
                                "UDP 0.0.0.0:9999 *:* 5123\n")
        with patch.object(self.core, "_windows_command", side_effect=[tasks, ports]):
            with patch.object(socket, "gethostbyname", return_value="模拟本机"):
                ip, result = self.core.local_ip_and_ports()
        self.assertEqual(ip, "模拟本机")
        self.assertEqual(result, ["4705"])

    def test_send_cli_parser_keeps_existing_options(self):
        parser = self.core.build_parser()
        args = parser.parse_args([
            "-ip", "192.168.1.10", "-p", "4705", "-msg", "通知",
            "-l", "2", "-t", "3", "-e", "r"])
        self.assertEqual(args.msg, "通知")
        self.assertEqual(args.l, 2)
        self.assertEqual(args.e, "r")


if __name__ == "__main__":
    unittest.main()
