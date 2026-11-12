"""CLI 帮助、参数错误与日志句柄生命周期的离线测试。"""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app.start import cli
from app.start.parser import COMMANDS, GROUP_NAMES


class CliLifecycleTests(unittest.TestCase):
    def setUp(self):
        build = Path("build")
        build.mkdir(exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=build, prefix="audit_cli_log_")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.log_path = self.root / "data" / "cli.log"
        self.log = cli.cli_log.CliLog()
        self.addCleanup(self.log.close)
        self.enterContext(patch.object(cli.cli_log, "LOG", self.log))
        self.enterContext(patch.object(cli.cli_log, "allows", return_value=True))
        self.path_lookup = self.enterContext(
            patch.object(cli, "portable_cli_log_path", return_value=self.log_path)
        )
        self.dispatch = self.enterContext(
            patch.object(cli, "run_from_cmd", return_value=0)
        )
        self.output = self.enterContext(redirect_stdout(io.StringIO()))
        self.enterContext(redirect_stderr(io.StringIO()))

    def test_help_at_every_depth_has_no_log_side_effect(self):
        prefixes = [[], *([group] for group in GROUP_NAMES)]
        prefixes.extend(
            [group, command]
            for group, commands in COMMANDS.items()
            for command in commands
        )
        prefixes.append(["restriction", "endstudent"])
        for prefix in prefixes:
            for flag in ("-h", "--help"):
                with self.subTest(arguments=[*prefix, flag]):
                    with self.assertRaises(SystemExit) as caught:
                        cli.main([*prefix, flag])
                    self.assertEqual(caught.exception.code, 0)
                    self.path_lookup.assert_not_called()
                    self.dispatch.assert_not_called()
                    self.assertFalse(self.log_path.parent.exists())

    def test_version_has_no_log_side_effect(self):
        for flag in ("-V", "--version"):
            with self.subTest(flag=flag), self.assertRaises(SystemExit) as caught:
                cli.main([flag])
            self.assertEqual(caught.exception.code, 0)
        self.path_lookup.assert_not_called()
        self.dispatch.assert_not_called()
        self.assertFalse(self.log_path.parent.exists())

    def test_hidden_helpers_skip_parser_and_log_lifecycle(self):
        for flag, handler in (
            ("--firewall-helper", "run_firewall_helper"),
            ("--student-helper", "run_student_helper"),
        ):
            with (
                self.subTest(flag=flag),
                patch.object(cli, handler, return_value=9) as helper,
                patch.object(cli, "build_group_parser") as select,
                patch.object(cli.cli_log, "close") as close,
            ):
                self.assertEqual(cli.main([flag, "result.json"]), 9)
                helper.assert_called_once_with(["result.json"])
                select.assert_not_called()
                close.assert_not_called()
            self.path_lookup.assert_not_called()
            self.dispatch.assert_not_called()
            self.assertFalse(self.log_path.parent.exists())

    def test_help_text_used_as_value_still_dispatches_and_logs(self):
        self.assertEqual(
            cli.main(["remote", "message", "-ip", "127.0.0.1", "-msg=--help"]), 0
        )
        self.assertEqual(self.dispatch.call_args.args[0].msg, "--help")
        self.path_lookup.assert_called_once_with()
        self.assertTrue(self.log_path.exists())
        self.assertIsNone(self.log._handle)

    def test_parameter_error_is_logged_and_closes_handle(self):
        for arguments in (["local"], ["local", "missing", "--help"]):
            with self.subTest(arguments=arguments):
                with self.assertRaises(SystemExit) as caught:
                    cli.main(arguments)
                self.assertEqual(caught.exception.code, 2)
                self.assertIsNone(self.log._handle)
        self.dispatch.assert_not_called()
        text = self.log_path.read_text(encoding="utf-8")
        self.assertIn("参数解析未通过", text)
        self.assertIn("WARNING", text)

    def test_success_returns_dispatch_status_and_closes_handle(self):
        self.dispatch.return_value = 7
        self.assertEqual(cli.main(["local", "info"]), 7)
        self.assertIsNone(self.log._handle)
        self.assertIn("退出码：7", self.log_path.read_text(encoding="utf-8"))

    def test_dispatch_exception_closes_handle(self):
        self.dispatch.side_effect = RuntimeError("handler failed")
        with self.assertRaisesRegex(RuntimeError, "handler failed"):
            cli.main(["local", "info"])
        self.assertTrue(self.log_path.exists())
        self.assertIsNone(self.log._handle)


class CliDispatchTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(cli.cli_log, "LOG"))
        self.handlers = {
            name: self.enterContext(
                patch.object(getattr(cli, module), name, return_value=17)
            )
            for module, name in (
                ("shell_cli", "run_shell"),
                ("student_cli", "run_student_command"),
                ("firewall_cli", "apply_firewall"),
                ("local_cli", "print_local_info"),
                ("files_cli", "run_file_transfer"),
                ("send_cli", "run_send"),
            )
        }

    def test_each_command_dispatches_to_its_feature(self):
        cases = (
            (["remote", "message", "-msg", "hello"], "run_send", "options"),
            (["remote", "command", "-c", "echo test"], "run_send", "options"),
            (["remote", "device", "--reboot"], "run_send", "options"),
            (
                ["remote", "file", "--file", "fixture.txt"],
                "run_file_transfer",
                "options",
            ),
            (["remote", "shell"], "run_shell", "options"),
            (["restriction", "student", "--list"], "run_student_command", "options"),
            (["local", "info"], "print_local_info", None),
            (["local", "firewall", "block"], "apply_firewall", "block"),
        )
        for arguments, name, argument in cases:
            if arguments[0] == "remote":
                arguments = [*arguments[:2], "-ip", "127.0.0.1", *arguments[2:]]
            with self.subTest(arguments=arguments):
                for handler in self.handlers.values():
                    handler.reset_mock()
                options = cli.build_group_parser().parse_args(arguments)
                self.assertEqual(cli.run_from_cmd(options), 17)
                expected = (options,) if argument == "options" else (argument,)
                if argument is None:
                    expected = ()
                self.handlers[name].assert_called_once_with(*expected)
                for other, handler in self.handlers.items():
                    if other != name:
                        handler.assert_not_called()

    def test_file_conflicts_stop_before_feature_dispatch(self):
        cases = (
            [
                "remote",
                "file",
                "-ip",
                "127.0.0.1",
                "--file",
                "fixture.txt",
                "-c",
                "echo test",
            ],
            [
                "remote",
                "message",
                "-ip",
                "127.0.0.1",
                "-msg",
                "hello",
                "--file-ip",
                "127.0.0.1",
            ],
            [
                "remote",
                "message",
                "-ip",
                "127.0.0.1",
                "-msg",
                "hello",
                "--file-timeout",
                "1",
            ],
        )
        for arguments in cases:
            with self.subTest(arguments=arguments), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    cli.build_group_parser().parse_args(arguments)
                for handler in self.handlers.values():
                    handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
