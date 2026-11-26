"""jiyu_udp_attack 的接口与报文格式回归测试。

本项目整体是 Jiyu_udp_attack 的 Python 重写，课堂助手等新功能不得改变它
已有的命令行入口、服务函数签名与报文布局。这里固定住这些契约，避免后续
整合无意间改到报文或接口。
"""

import inspect
import unittest
from unittest.mock import patch

import app.features.send.data as send_data
import app.features.send.service as send_service
import app.packets.codec as codec
import app.packets.constants as constants
import app.start.parser as parser
from tests.fixtures.offline import OfflineCase


def _decode_text(packet, offset):
    """从报文正文区解出 UTF-16LE 文本，遇到 UTF-16 的 0 字符结束。"""
    payload = bytes(packet[offset:])
    # 按 UTF-16 码元对齐查找结束符，避免把 ASCII 字符的高字节当成结束。
    end = next(
        index
        for index in range(0, len(payload) - 1, 2)
        if payload[index : index + 2] == b"\x00\x00"
    )
    return payload[:end].decode("utf-16-le")


class UdpAttackRegressionTests(OfflineCase):
    def test_service_interface_is_stable(self):
        expected = {
            "validate_options": ["options"],
            "prepare_packets": ["options", "report"],
            "execute_send_report": ["options", "report"],
            "execute_send": ["options", "report"],
        }
        for name, parameters in expected.items():
            with self.subTest(name=name):
                function = getattr(send_service, name)
                self.assertTrue(callable(function))
                self.assertEqual(
                    list(inspect.signature(function).parameters), parameters
                )

    def test_send_options_defaults_are_stable(self):
        options = send_data.SendOptions("10.0.0.5")
        self.assertEqual(options.port, 4705)
        self.assertEqual(options.message, "")
        self.assertEqual(options.command, "")
        self.assertEqual(options.extra, "")
        self.assertEqual(options.loops, 1)
        self.assertEqual(options.interval, 22)
        self.assertIsNone(options.cancel_event)

    def test_message_packet_layout(self):
        packet = codec.pkg_sendlist("-msg", "通知")
        template = constants.basicCMD["-msg"]
        self.assertEqual(len(packet), len(template))
        # 报文头与模板逐字节一致，只有 UTF-16LE 正文区被替换。
        self.assertEqual(
            bytes(packet[: constants.MESSAGE_OFFSET]),
            bytes(template[: constants.MESSAGE_OFFSET]),
        )
        self.assertEqual(_decode_text(packet, constants.MESSAGE_OFFSET), "通知")

    def test_command_packet_layout(self):
        packet = codec.pkg_sendlist("-c", "cmd.exe /c whoami")
        template = constants.basicCMD["-c"]
        self.assertEqual(len(packet), len(template))
        self.assertEqual(
            bytes(packet[: constants.COMMAND_OFFSET]),
            bytes(template[: constants.COMMAND_OFFSET]),
        )
        self.assertEqual(
            _decode_text(packet, constants.COMMAND_OFFSET), "cmd.exe /c whoami"
        )

    def test_device_templates_are_untouched(self):
        for extra in ("r", "s"):
            with self.subTest(extra=extra):
                options = send_data.SendOptions("10.0.0.5", extra=extra)
                packets = send_service.prepare_packets(options)
                self.assertEqual(len(packets), 1)
                self.assertEqual(
                    bytes(packets[0]), bytes(constants.basicCMD["-" + extra])
                )

    def test_logoff_uses_remote_command_packet(self):
        options = send_data.SendOptions("10.0.0.5", extra="l")
        packets = send_service.prepare_packets(options)
        self.assertEqual(len(packets), 1)
        self.assertEqual(
            bytes(packets[0]), bytes(codec.pkg_sendlist("-c", constants.LOGOFF_COMMAND))
        )

    def test_blue_screen_and_command_use_http_payloads(self):
        with patch.object(send_service, "blue_screen_packets") as blue:
            blue.return_value = [constants.basicCMD["-c"]]
            packets = send_service.prepare_packets(
                send_data.SendOptions("10.0.0.5", extra="b")
            )
        blue.assert_called_once()
        self.assertEqual(len(packets), 1)

        with patch.object(send_service, "elevated_packets") as elevated:
            elevated.return_value = [constants.basicCMD["-c"]]
            send_service.prepare_packets(
                send_data.SendOptions("10.0.0.5", command="whoami")
            )
        elevated.assert_called_once()

    def test_cli_remote_commands_still_parse(self):
        argument_parser = parser.build_group_parser()
        cases = [
            (["remote", "message", "-ip", "10.0.0.5", "-msg", "通知"], "message"),
            (["remote", "command", "-ip", "10.0.0.5", "-c", "whoami"], "command"),
            (["remote", "device", "-ip", "10.0.0.5", "--reboot"], "device"),
            (
                ["remote", "file", "-ip", "10.0.0.5", "--file", "a.txt"],
                "file",
            ),
            (["remote", "shell", "-ip", "10.0.0.5"], "shell"),
        ]
        for argv, command in cases:
            with self.subTest(argv=argv):
                args = argument_parser.parse_args(argv)
                self.assertEqual(args.group, "remote")
                self.assertEqual(args.command, command)
                self.assertEqual(args.ip, "10.0.0.5")


if __name__ == "__main__":
    unittest.main()
