"""离线用例的网络隔离与临时目录夹具。"""

import socket
import unittest
from pathlib import Path
from unittest.mock import patch

import app.packets.constants as constants


class OfflineCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_root = Path("build") / "tests" / cls.__name__
        cls.test_root.mkdir(parents=True, exist_ok=True)
        cls.real_socket = socket.socket
        cls.network_guard = patch.object(
            socket, "socket", side_effect=AssertionError("测试期间禁止创建网络套接字")
        )
        cls.network_guard.start()

    @classmethod
    def tearDownClass(cls):
        cls.network_guard.stop()

    def message_text(self, packet):
        body = bytes(packet[constants.MESSAGE_OFFSET :]).decode("utf-16le")
        return body.split("\x00", 1)[0]

    def command_text(self, packet):
        body = bytes(packet[constants.COMMAND_OFFSET :]).decode("utf-16le")
        return body.split("\x00", 1)[0]

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
