"""按模块组织的离线回归测试。"""

import app.packets.codec as codec
import app.packets.constants as constants
from tests.fixtures.offline import OfflineCase


class PacketsTests(OfflineCase):
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
                chunks = list(codec.split_message(text))
                self.assertEqual(len(chunks), parts)
                self.assertEqual("".join(chunks), text)
                for chunk in chunks:
                    packet = codec.pkg_sendlist("-msg", chunk)
                    self.assertEqual(len(packet), 954)
                    self.assertEqual(self.message_text(packet), chunk)

    def test_message_keeps_multiline_content(self):
        text = "第一行\n\n第二行\r\n😀\t结束\n" * 100
        chunks = list(codec.split_message(text))
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), text)

    def test_templates_are_not_mutated(self):
        message_template = constants.basicCMD["-msg"].copy()
        command_template = constants.basicCMD["-c"].copy()
        first = codec.pkg_sendlist("-msg", "第一条")
        second = codec.pkg_sendlist("-msg", "另一条")
        command = codec.pkg_sendlist("-c", "cmd.exe /c ipconfig")
        self.assertIsNot(first, second)
        self.assertEqual(self.message_text(first), "第一条")
        self.assertEqual(self.message_text(second), "另一条")
        self.assertEqual(self.command_text(command), "cmd.exe /c ipconfig")
        self.assertEqual(constants.basicCMD["-msg"], message_template)
        self.assertEqual(constants.basicCMD["-c"], command_template)

    def test_capacity_errors_are_explicit(self):
        with self.assertRaises(ValueError):
            list(codec.split_message("a\x00b"))
        with self.assertRaises(ValueError):
            codec.pkg_sendlist("-msg", "a" * 449)
        command_units = constants.COMMAND_MAX_BYTES // 2
        with self.assertRaises(ValueError):
            codec.pkg_sendlist("-c", "a" * (command_units + 1))
