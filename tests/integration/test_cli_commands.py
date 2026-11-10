"""按模块组织的离线回归测试。"""

import io
import shutil
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import app.packets.constants as constants
import app.shared.logs.cli as cli_log
from app.features.files import cli as files_cli
from app.features.send import cli as send_cli
from app.start import cli
from app.start.parser import build_flat_parser
from tests.fixtures.offline import OfflineCase


class CliCommandsTests(OfflineCase):
    def test_cli_device_actions_reuse_fixed_templates(self):
        parser = build_flat_parser()
        for extra, key in (("r", "-r"), ("s", "-s")):
            with self.subTest(extra=extra):
                arguments = parser.parse_args(["-ip", "192.168.1.10", "-e", extra])
                packets = send_cli.create_send_packets(arguments)
                self.assertEqual(packets, [constants.basicCMD[key]])

        arguments = parser.parse_args(["-ip", "192.168.1.10", "-e", "l"])
        packets = send_cli.create_send_packets(arguments)
        self.assertEqual(self.command_text(packets[0]), constants.LOGOFF_COMMAND)

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
        parser = build_flat_parser()
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
        parser = build_flat_parser()
        args = parser.parse_args(
            ["-ip", "192.168.1.10", "--file", "a.txt", "文件夹", "b.bin"]
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
            patch.object(cli_log, "allows", lambda level: True),
            patch.object(cli, "portable_cli_log_path", return_value=log_path),
            patch.object(files_cli, "transfer_file", return_value=result) as transfer,
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
        parser = build_flat_parser()
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
