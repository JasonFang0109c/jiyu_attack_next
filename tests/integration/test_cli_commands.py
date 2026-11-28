"""按模块组织的离线回归测试。"""

import io
import shutil
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import NeoJiYuTrainer.packets.constants as constants
import NeoJiYuTrainer.packets.elevated as packets_elevated
import NeoJiYuTrainer.shared.logs.cli as cli_log
from NeoJiYuTrainer.features.command import cli as command_cli
from NeoJiYuTrainer.features.files import cli as files_cli
from NeoJiYuTrainer.features.send import cli as send_cli
from NeoJiYuTrainer.features.shell import cli as shell_cli
from NeoJiYuTrainer.start import cli
from NeoJiYuTrainer.start.parser import build_group_parser
from tests.fixtures.offline import OfflineCase


class CliCommandsTests(OfflineCase):
    def test_shell_success_returns_zero_exit_code(self):
        server = SimpleNamespace(
            address="127.0.0.1",
            port=50000,
            http_port=50001,
            command=lambda: "connect",
            start=lambda: None,
            close=lambda: None,
        )
        arguments = SimpleNamespace(ip="127.0.0.1", p=4705)
        with (
            patch.object(shell_cli, "ShellServer", return_value=server),
            patch.object(shell_cli, "send_command"),
            patch.object(shell_cli, "relay_shell"),
            patch.object(shell_cli.cli_log.LOG, "info"),
            redirect_stdout(io.StringIO()),
        ):
            result = shell_cli.run_shell(arguments)
        self.assertEqual(result, 0)
        self.assertNotIsInstance(result, bool)

    def test_cli_device_actions_reuse_fixed_templates(self):
        parser = build_group_parser()
        for action, key in (("--reboot", "-r"), ("--shutdown", "-s")):
            with self.subTest(action=action):
                arguments = parser.parse_args(
                    ["remote", "device", "-ip", "192.168.1.10", action]
                )
                packets = send_cli.create_send_packets(arguments)
                self.assertEqual(packets, [constants.basicCMD[key]])

        arguments = parser.parse_args(
            ["remote", "device", "-ip", "192.168.1.10", "--logoff"]
        )
        packets = send_cli.create_send_packets(arguments)
        self.assertEqual(self.command_text(packets[0]), constants.LOGOFF_COMMAND)

        # 蓝屏会真起本机 HTTP 服务，先放开网络守卫。
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        arguments = parser.parse_args(
            ["remote", "device", "-ip", "192.168.1.10", "--bluescreen"]
        )
        packets = send_cli.create_send_packets(arguments)
        # 蓝屏只下发一条取回脚本的命令。
        self.assertEqual(len(packets), 1)
        command = self.command_text(packets[0])
        self.assertIn("DownloadString", command)
        self.assertIn(constants.BLUE_SCREEN_PATH, command)

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
            patch.object(files_cli, "transfer_file", return_value=result),
            redirect_stdout(buffer),
        ):
            self.assertEqual(files_cli.run_file_transfer(arguments), 0)
        self.assertIn("2 个目标桌面", buffer.getvalue())

    def test_file_transfer_cli_parser_and_dispatch(self):
        parser = build_group_parser()
        args = parser.parse_args(
            [
                "remote",
                "file",
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
            parser.parse_args(
                [
                    "remote",
                    "file",
                    "-ip",
                    "192.168.1.10",
                    "--file",
                    "report.pdf",
                    "-msg",
                    "通知",
                ]
            )

    def test_file_option_accepts_multiple_paths(self):
        parser = build_group_parser()
        args = parser.parse_args(
            [
                "remote",
                "file",
                "-ip",
                "192.168.1.10",
                "--file",
                "a.txt",
                "文件夹",
                "b.bin",
            ]
        )
        self.assertEqual(args.file, ["a.txt", "文件夹", "b.bin"])

    def test_cli_log_follows_build_variant_level(self):
        # 正常版本只记 WARNING 及以上，DEBUG 与 INFO 都不落盘。
        log_path = self.test_root / "cli-log" / "cli.log"
        shutil.rmtree(log_path.parent, ignore_errors=True)
        log = cli_log.configure(log_path)
        try:
            log.debug("调试细节", "测试", "附加：值")
            log.info("关键节点", "测试")
            log.warning("参数不合法", "测试", "附加：值")
        finally:
            cli_log.close()
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
            patch.object(cli_log, "allows", lambda level: True),
            patch.object(cli, "portable_cli_log_path", return_value=log_path),
            patch.object(send_cli, "send_tracked", return_value=outcome),
            redirect_stdout(buffer),
        ):
            code = cli.main(
                ["remote", "message", "-ip", "192.168.1.10", "-msg", "通知"]
            )
        self.assertEqual(code, 0)
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("命令行启动", text)
        self.assertIn("命令行参数", text)
        self.assertIn("target=192.168.1.10", text)
        self.assertIn("message=已提供", text)
        self.assertNotIn("通知", text)
        self.assertIn("开始发送", text)
        self.assertIn("命令行结束", text)

    def test_command_text_is_not_written_to_cli_log(self):
        secret_command = "cmd.exe /c echo secret-token"
        log_path = self.test_root / "cli-command" / "cli.log"
        outcome = SimpleNamespace(deliveries=[], failed=[])
        with (
            patch.object(cli_log, "allows", lambda level: True),
            patch.object(cli, "portable_cli_log_path", return_value=log_path),
            patch.object(send_cli, "send_tracked", return_value=outcome),
            # 命令改由托管脚本下发，这里只验证日志，不真起服务与等待。
            patch.object(
                command_cli, "elevated_packets", return_value=[constants.basicCMD["-c"]]
            ),
            patch.object(packets_elevated, "wait_for_elevated", return_value=True),
            redirect_stdout(io.StringIO()),
        ):
            code = cli.main(
                ["remote", "command", "-ip", "192.168.1.10", "-c", secret_command]
            )
        self.assertEqual(code, 0)
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("命令字符数", text)
        self.assertNotIn(secret_command, text)

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
            patch.object(cli_log, "allows", lambda level: True),
            patch.object(cli, "portable_cli_log_path", return_value=log_path),
            patch.object(files_cli, "transfer_file", return_value=result) as transfer,
            redirect_stdout(buffer),
        ):
            code = cli.main(
                [
                    "remote",
                    "file",
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
        parser = build_group_parser()
        args = parser.parse_args(
            [
                "remote",
                "message",
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
            ]
        )
        self.assertEqual(args.msg, "通知")
        self.assertEqual(args.l, 2)
        self.assertEqual(args.t, 3)
        with self.assertRaises(SystemExit):
            parser.parse_args(["remote", "device", "-ip", "192.168.1.10", "--unknown"])
