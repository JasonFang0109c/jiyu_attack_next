"""CLI 帮助、参数错误与日志句柄生命周期的离线测试。"""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app.cli import main as cli
from app.cli.parser import COMMANDS, GROUP_NAMES


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

    def test_help_text_used_as_value_still_dispatches_and_logs(self):
        self.assertEqual(cli.main(["-msg=--help"]), 0)
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


if __name__ == "__main__":
    unittest.main()
