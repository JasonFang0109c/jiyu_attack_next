"""课堂助手密码读取的离线回归测试：Knock1 解密与注册表回退顺序。"""

import unittest
from unittest.mock import patch

import app.features.classroom.passwords as passwords
from app.features.classroom.data import (
    KNOCK_XOR_FIRST,
    KNOCK_XOR_SECOND,
    PASSWORD_KNOCK_SENTINEL,
)
from tests.fixtures.offline import OfflineCase


def _encrypt_knock(text, offset=8):
    """按解密算法的逆过程构造一份 ``Knock1`` 测试数据。"""
    plain = bytearray(offset + len(text.encode("utf-16-le")))
    plain[0] = offset
    plain[offset:] = text.encode("utf-16-le")
    for index in range(len(plain) // 4):
        start = index * 4
        value = int.from_bytes(plain[start : start + 4], "little")
        value ^= KNOCK_XOR_SECOND
        value ^= KNOCK_XOR_FIRST
        plain[start : start + 4] = value.to_bytes(4, "little")
    return bytes(plain)


class ClassroomPasswordTests(OfflineCase):
    def test_decrypt_knock_round_trip(self):
        self.assertEqual(
            passwords.decrypt_knock(_encrypt_knock("Passw0rd")), "Passw0rd"
        )
        self.assertEqual(
            passwords.decrypt_knock(_encrypt_knock("abc", offset=4)), "abc"
        )

    def test_decrypt_knock_stops_at_nul_and_truncates(self):
        text = "0123456789" * 4
        self.assertEqual(passwords.decrypt_knock(_encrypt_knock(text)), text[:32])

    def test_decrypt_knock_rejects_bad_data(self):
        with self.assertRaisesRegex(ValueError, "长度不足"):
            passwords.decrypt_knock(b"\x00\x01\x02")
        with self.assertRaisesRegex(ValueError, "偏移超出"):
            passwords.decrypt_knock(_encrypt_knock("", offset=200))

    def test_plain_password_strips_prefix(self):
        with patch.object(passwords, "_read_value", return_value="ABCDEFsecret"):
            self.assertEqual(passwords._read_plain_password(), "secret")

    def test_plain_password_sentinel_switches_to_knock(self):
        with patch.object(
            passwords, "_read_value", return_value=PASSWORD_KNOCK_SENTINEL
        ):
            self.assertIsNone(passwords._read_plain_password())

    def test_read_password_plain(self):
        with patch.object(passwords, "_read_plain_password", return_value="hunter2"):
            result = passwords.read_password()
        self.assertEqual(
            result, {"password": "hunter2", "source": "plain", "error": ""}
        )

    def test_read_password_falls_back_to_knock(self):
        with (
            patch.object(passwords, "_read_plain_password", return_value=None),
            patch.object(
                passwords, "_read_value", return_value=_encrypt_knock("knock-pass")
            ),
        ):
            result = passwords.read_password()
        self.assertEqual(result["password"], "knock-pass")
        self.assertEqual(result["source"], "knock")
        self.assertEqual(result["error"], "")

    def test_read_password_reports_missing_values(self):
        with (
            patch.object(
                passwords, "_read_plain_password", side_effect=OSError("missing")
            ),
            patch.object(passwords, "_read_value", side_effect=OSError("missing")),
        ):
            result = passwords.read_password()
        self.assertEqual(result["password"], "")
        self.assertIn("读取失败", result["error"])


if __name__ == "__main__":
    unittest.main()
