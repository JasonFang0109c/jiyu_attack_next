"""应用命令与教师端会话的离线测试：报文拼接、解析与命令行参数。"""

import socket
import struct
import unittest
from threading import Event
from unittest.mock import patch

from app import core
from app.cli import main as cli


def build_message(host, payload):
    """拼一条完整的 MESS 报文，供解析测试复用。"""
    return (
        struct.pack("<III", core.appcmd.MESS_MAGIC, 1, 1)
        + socket.inet_aton(host)
        + payload
    )


class AppCommandTests(unittest.TestCase):
    """逐字节校验应用命令与会话报文的布局。"""

    def setUp(self):
        self.appcmd = core.appcmd

    def test_session_endpoint_matches_channel_formula(self):
        self.assertEqual(self.appcmd.session_endpoint(1), ("225.2.2.1", 5512))
        self.assertEqual(self.appcmd.session_endpoint(2), ("225.2.3.1", 6024))
        with self.assertRaises(ValueError):
            self.appcmd.session_endpoint(0)
        with self.assertRaises(ValueError):
            self.appcmd.session_endpoint(33)

    def test_announce_packets_carry_magic_length_and_address(self):
        oonc = self.appcmd.oonc_packet("10.0.0.2", sequence=7)
        magic, version, length = struct.unpack("<III", oonc[:12])
        self.assertEqual(magic, self.appcmd.OONC_MAGIC)
        self.assertEqual(version, self.appcmd.COM_VERSION)
        self.assertEqual(length, 16)
        self.assertEqual(oonc[28:32], socket.inet_aton("10.0.0.2"))
        self.assertEqual(struct.unpack("<III", oonc[32:44]), (1, 1, 7))

        nanc = self.appcmd.nanc_packet("10.0.0.2", channel=3, teacher_name="教师")
        magic, _version, length = struct.unpack("<III", nanc[:12])
        self.assertEqual(magic, self.appcmd.NANC_MAGIC)
        self.assertEqual(length, len(nanc) - 28)
        self.assertEqual(nanc[32:36], socket.inet_aton("10.0.0.2"))

    def test_canc_rejects_overlong_teacher_name(self):
        with self.assertRaises(ValueError):
            self.appcmd.canc_packet("10.0.0.2", teacher_name="名" * 40)
        packet = self.appcmd.canc_packet("10.0.0.2", teacher_name="1")
        self.assertEqual(len(packet), 28 + 84)

    def test_run_program_payload_has_fixed_size_fields(self):
        payload = self.appcmd.run_program_payload(
            "C:/Windows/notepad.exe", "-n", show=2
        )
        self.assertEqual(struct.unpack("<I", payload[:4])[0], self.appcmd.APP_CATEGORY)
        self.assertEqual(struct.unpack("<I", payload[4:8])[0], 0)
        self.assertEqual(struct.unpack("<I", payload[8:12])[0], self.appcmd.CMD_RUN)
        self.assertEqual(struct.unpack("<I", payload[12:16])[0], 1)
        self.assertEqual(struct.unpack("<I", payload[-8:-4])[0], 2)
        packet = self.appcmd.comd_packet(payload)
        self.assertEqual(struct.unpack("<I", packet[:4])[0], self.appcmd.COM_MAGIC)
        self.assertEqual(struct.unpack("<I", packet[8:12])[0], len(packet) - 28)

    def test_open_url_payload_appends_terminator_and_padding(self):
        payload = self.appcmd.open_url_payload("http://10.0.0.1")
        self.assertEqual(
            struct.unpack("<I", payload[8:12])[0], self.appcmd.CMD_OPEN_URL
        )
        self.assertTrue(payload.endswith(b"\x00" * 6))
        self.assertIn("http://10.0.0.1".encode("utf-16-le"), payload)

    def test_blackscreen_mess_payload_layout(self):
        payload = self.appcmd.blackscreen_mess_payload(True, 30)
        self.assertEqual(struct.unpack("<I", payload[:4])[0], len(payload))
        self.assertEqual(struct.unpack("<I", payload[4:8])[0], 0x20)
        self.assertEqual(struct.unpack("<I", payload[8:12])[0], 0x80000000)
        self.assertEqual(struct.unpack("<I", payload[12:16])[0], 1)
        self.assertEqual(struct.unpack("<I", payload[20:24])[0], 30)
        self.assertEqual(payload[36:39], b"\xa0\x05\x20")

    def test_blackscreen_payload_uses_case_six(self):
        payload = self.appcmd.blackscreen_payload(True, 15)
        self.assertEqual(
            struct.unpack("<I", payload[8:12])[0], self.appcmd.CMD_BLACKSCREEN
        )
        self.assertEqual(struct.unpack("<I", payload[12:16])[0], 1)
        self.assertEqual(struct.unpack("<I", payload[20:24])[0], 15)

    def test_unlock_payload_clears_blackscreen_flag(self):
        payload = self.appcmd.unlock_payload()
        self.assertEqual(struct.unpack("<I", payload[:4])[0], 0x0D)
        self.assertEqual(struct.unpack("<I", payload[4:8])[0], 0x20)
        self.assertEqual(struct.unpack("<I", payload[8:12])[0], 0x90000000)
        self.assertEqual(payload[12:], b"\x01")

    def test_power_payload_carries_delay_and_text(self):
        payload = self.appcmd.power_payload(reboot=True, delay=5, text="即将重启")
        command = struct.unpack("<I", payload[8:12])[0]
        self.assertEqual(command, self.appcmd.CMD_REBOOT | self.appcmd.CMD_FORCE)
        self.assertEqual(struct.unpack("<I", payload[12:16])[0], 5)
        self.assertIn("即将重启".encode("utf-16-le"), payload)

    def test_kill_payload_requires_identifier(self):
        with self.assertRaises(ValueError):
            self.appcmd.kill_payload()
        by_process = self.appcmd.kill_payload(process_id=4321)
        self.assertEqual(struct.unpack("<I", by_process[12:16])[0], 4)
        self.assertEqual(struct.unpack("<I", by_process[20:24])[0], 4321)
        by_window = self.appcmd.kill_payload(window=99, force=False)
        self.assertEqual(struct.unpack("<I", by_window[12:16])[0], 3)
        self.assertEqual(struct.unpack("<I", by_window[16:20])[0], 99)
        self.assertEqual(struct.unpack("<I", by_window[24:28])[0], 0)

    def test_info_request_payload_carries_report_kind(self):
        payload = self.appcmd.info_request_payload(self.appcmd.REPORT_PROCESSES)
        self.assertEqual(struct.unpack("<I", payload[:4])[0], 16)
        self.assertEqual(
            struct.unpack("<I", payload[4:8])[0], self.appcmd.INFO_REQUEST_CODE
        )
        self.assertEqual(struct.unpack("<I", payload[12:16])[0], 2)

    def test_session_replies_include_tcp_port(self):
        packets = self.appcmd.session_replies("10.0.0.9")
        self.assertEqual(len(packets), 2)
        for packet in packets:
            self.assertEqual(struct.unpack("<I", packet[:4])[0], self.appcmd.MESS_MAGIC)
            self.assertEqual(packet[12:16], socket.inet_aton("10.0.0.9"))
        self.assertEqual(
            struct.unpack("<H", packets[1][32:34])[0], self.appcmd.TCP_COMM_PORT
        )

    def test_thumbnail_packets_use_policy_subtypes(self):
        packets = self.appcmd.thumbnail_packets()
        self.assertEqual(len(packets), 2)
        self.assertEqual(struct.unpack("<I", packets[0][:4])[0], self.appcmd.LPNT_MAGIC)
        self.assertEqual(struct.unpack("<I", packets[0][28:32])[0], 2)
        self.assertEqual(struct.unpack("<I", packets[1][28:32])[0], 3)
        self.assertEqual(len(packets[0]), 48)

    def test_parse_student_info_reads_fixed_offsets(self):
        payload = bytearray(0x2DA + 32)
        struct.pack_into("<I", payload, 0, 5)
        payload[0x10 : 0x10 + 10] = "PC-01".encode("utf-16-le")
        struct.pack_into("<I", payload, 0x50, 20260001)
        payload[0x54:0x5A] = bytes.fromhex("001122334455")
        payload[0x5A : 0x5A + 6] = "学生".encode("utf-16-le")
        payload[0x9A : 0x9A + 20] = "Windows 11".encode("utf-16-le")
        payload[0xDA : 0xDA + 10] = "10.0.22631".encode("utf-16-le")
        payload[0x21A : 0x21A + 8] = "Genuine".encode("utf-16-le")
        payload[0x25A : 0x25A + 10] = "i7-12700".encode("utf-16-le")
        payload[0x2DA : 0x2DA + 16] = "16384 MB".encode("utf-16-le")
        info = self.appcmd.parse_student_info(bytes(payload))
        self.assertEqual(info["name"], "PC-01")
        self.assertEqual(info["student_id"], 20260001)
        self.assertEqual(info["mac"], "00-11-22-33-44-55")
        self.assertEqual(info["user"], "学生")
        self.assertEqual(info["os"], "Windows 11")
        self.assertEqual(info["os_version"], "10.0.22631")
        self.assertEqual(info["cpu_model"], "i7-12700")
        self.assertEqual(info["memory"], "16384 MB")
        with self.assertRaises(ValueError):
            self.appcmd.parse_student_info(b"\x00" * 16)

    def test_parse_id_name_pairs_stops_at_truncation(self):
        data = struct.pack("<I", 101) + "notepad.exe".encode("utf-16-le") + b"\x00\x00"
        data += struct.pack("<I", 202) + "记事本".encode("utf-16-le") + b"\x00\x00"
        self.assertEqual(
            self.appcmd.parse_id_name_pairs(data),
            [(101, "notepad.exe"), (202, "记事本")],
        )
        self.assertEqual(self.appcmd.parse_id_name_pairs(b"\x01\x02"), [])

    def test_parse_message_detects_kinds(self):
        chat = build_message(
            "10.0.0.9",
            struct.pack("<IIII", 0, self.appcmd.MESS_CHAT_TYPE, 0, 0)
            + "你好".encode("utf-16-le"),
        )
        self.assertEqual(self.appcmd.parse_message(chat)["kind"], "chat")
        windows = build_message(
            "10.0.0.9",
            struct.pack("<IIIII", 0, 0x100000, self.appcmd.INFO_REPORT_CATEGORY, 6, 1)
            + struct.pack("<I", 7)
            + "窗口".encode("utf-16-le")
            + b"\x00\x00",
        )
        parsed = self.appcmd.parse_message(windows)
        self.assertEqual(parsed["kind"], "windows")
        self.assertTrue(parsed["first"])
        self.assertEqual(parsed["entries"], [(7, "窗口")])
        with self.assertRaises(ValueError):
            self.appcmd.parse_message(b"\x00\x00")

    def test_looks_like_login_checks_magic(self):
        login = struct.pack("<I", self.appcmd.LOGI_MAGIC) + b"\x00" * 8
        self.assertTrue(self.appcmd.looks_like_login(login))
        self.assertFalse(self.appcmd.looks_like_login(b"\x00\x00\x00\x00"))


class TeacherSessionTests(unittest.TestCase):
    """教师端命令分派的离线测试，全程替换套接字发送函数。"""

    def test_run_app_operation_reports_sent_bytes(self):
        with patch.object(core.teacher, "send_app_command", return_value=10) as send:
            result = core.run_app_operation(
                ["10.0.0.1", "10.0.0.2"], b"payload", channel="comd"
            )
        self.assertEqual(result, {"sent": 20, "hosts": 2})
        self.assertEqual(send.call_count, 2)

    def test_run_app_operation_supports_lock_payload(self):
        with (
            patch.object(core.teacher, "send_app_command", return_value=4) as send,
            patch.object(core.teacher, "send_session_broadcast", return_value=6),
        ):
            result = core.run_app_operation(
                ["10.0.0.1"], b"black", channel="session", lock_payload=b"lock"
            )
        self.assertEqual(result["sent"], 10)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[1], b"lock")

    def test_run_app_operation_honours_cancel(self):
        cancel_event = Event()
        cancel_event.set()
        with (
            patch.object(core.teacher, "send_app_command", return_value=1),
            self.assertRaises(RuntimeError),
        ):
            core.run_app_operation(["10.0.0.1"], b"x", cancel_event=cancel_event)

    def test_session_broadcast_requires_targets(self):
        with self.assertRaises(ValueError):
            core.send_session_broadcast([], b"x")


class AppCommandCliTests(unittest.TestCase):
    """应用命令相关命令行参数的解析与负载生成。"""

    def parse(self, *arguments):
        return cli.build_parser().parse_args(["-ip", "10.0.0.1", *arguments])

    def test_action_arguments_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            self.parse("--run", "a.exe", "--url", "http://x")

    def test_run_action_builds_comd_payload(self):
        name, payload, channel, lock = cli.build_action_payload(
            self.parse("--run", "a.exe", "--run-args=-n")
        )
        self.assertEqual(name, "远程运行程序")
        self.assertEqual(channel, "comd")
        self.assertIsNone(lock)
        self.assertEqual(struct.unpack("<I", payload[8:12])[0], core.appcmd.CMD_RUN)

    def test_url_action_adds_scheme(self):
        _name, payload, channel, _lock = cli.build_action_payload(
            self.parse("--url", "example.com")
        )
        self.assertEqual(channel, "comd")
        self.assertIn("http://example.com".encode("utf-16-le"), payload)

    def test_kill_action_uses_mess_channel(self):
        _name, payload, channel, _lock = cli.build_action_payload(
            self.parse("--kill", "42")
        )
        self.assertEqual(channel, "mess")
        self.assertEqual(struct.unpack("<I", payload[12:16])[0], 4)

    def test_blackscreen_action_uses_session_channel_and_lock(self):
        name, payload, channel, lock = cli.build_action_payload(
            self.parse("--blackscreen", "20")
        )
        self.assertEqual(name, "黑屏并锁定键鼠")
        self.assertEqual(channel, "session")
        self.assertIsNotNone(lock)
        self.assertEqual(struct.unpack("<I", payload[20:24])[0], 20)
        _name, _payload, channel, lock = cli.build_action_payload(
            self.parse("--blackscreen", "20", "--no-lock")
        )
        self.assertEqual(channel, "session")
        self.assertIsNone(lock)

    def test_defaults_when_no_action_given(self):
        arguments = self.parse()
        self.assertIsNone(cli.build_action_payload(arguments))
        self.assertEqual(arguments.channel, 1)
        self.assertEqual(arguments.teacher_name, "1")

    def test_announce_and_students_defaults(self):
        self.assertEqual(self.parse("--announce").announce, 10)
        self.assertEqual(self.parse("--students").students, 8)


if __name__ == "__main__":
    unittest.main()
