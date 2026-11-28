"""全局热键解析测试。"""

import unittest

from NeoJiYuTrainer.System.Windows.Hotkey import MOD_ALT, MOD_CONTROL, parse_hotkey


class HotkeyTests(unittest.TestCase):
    def test_parse_combination(self):
        parsed = parse_hotkey("Ctrl+Alt+H")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.modifiers, MOD_CONTROL | MOD_ALT)
        self.assertEqual(parsed.virtual_key, ord("H"))

    def test_parse_function_key_and_spaces(self):
        parsed = parse_hotkey(" Ctrl + Shift + F12 ")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.virtual_key, 0x7B)

    def test_blank_and_invalid_are_disabled(self):
        self.assertIsNone(parse_hotkey(""))
        self.assertIsNone(parse_hotkey("Ctrl+"))
        self.assertIsNone(parse_hotkey("H"))
        self.assertIsNone(parse_hotkey("Ctrl+Unknown"))


if __name__ == "__main__":
    unittest.main()
