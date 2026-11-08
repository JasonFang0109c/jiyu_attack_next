"""命令行解析的测试：分组子命令与扁平写法共用同一套执行字段。"""

import unittest

from app.cli import parser as cli_parser


class GroupParserTests(unittest.TestCase):
    def test_groups_match_gui_sidebar(self):
        self.assertEqual(
            list(cli_parser.GROUPS),
            ["restriction", "remote", "teacher", "local"],
        )
        self.assertEqual(
            list(cli_parser.COMMANDS["remote"]),
            ["message", "file", "device", "command", "shell"],
        )
        self.assertEqual(
            list(cli_parser.COMMANDS["teacher"]),
            ["appcmd", "students", "screen", "control", "chat", "closewindow"],
        )
        self.assertEqual(list(cli_parser.COMMANDS["local"]), ["info", "firewall"])
        self.assertEqual(list(cli_parser.COMMANDS["restriction"]), ["student"])

    def test_every_command_has_a_parser(self):
        group = cli_parser.build_group_parser()
        choices = group._subparsers._group_actions[0].choices
        for name, commands in cli_parser.COMMANDS.items():
            sub = choices[name]._subparsers._group_actions[0].choices
            # 子命令可能带别名（如 student 的旧名 endstudent），这里只核对正式名。
            self.assertEqual([item for item in sub if item in commands], list(commands))

    def test_message_command_keeps_flat_field_names(self):
        arguments = cli_parser.build_group_parser().parse_args(
            ["remote", "message", "-ip", "10.0.0.1", "-msg", "通知"]
        )
        self.assertEqual(arguments.group, "remote")
        self.assertEqual(arguments.command, "message")
        self.assertEqual(arguments.ip, "10.0.0.1")
        self.assertEqual(arguments.msg, "通知")
        self.assertEqual(arguments.p, 4705)
        self.assertEqual(arguments.l, 1)
        self.assertEqual(arguments.t, 22)

    def test_device_command_maps_flags_to_extra_field(self):
        parser = cli_parser.build_group_parser()
        self.assertEqual(
            parser.parse_args(["remote", "device", "-ip", "10.0.0.1", "--shutdown"]).e,
            "s",
        )
        self.assertEqual(
            parser.parse_args(["remote", "device", "-ip", "10.0.0.1", "--reboot"]).e,
            "r",
        )
        self.assertEqual(
            parser.parse_args(["remote", "device", "-ip", "10.0.0.1", "--logoff"]).e,
            "l",
        )

    def test_appcmd_command_covers_every_gui_operation(self):
        parser = cli_parser.build_group_parser()
        cases = (
            (["--run", "notepad.exe"], "run", "notepad.exe"),
            (["--url", "example.com"], "url", "example.com"),
            (["--kill", "1234"], "kill", "1234"),
            (["--rename", "2-01"], "rename", "2-01"),
            (["--screen-password", "1234"], "screen_password", "1234"),
        )
        for extra, attribute, expected in cases:
            arguments = parser.parse_args(
                ["teacher", "appcmd", "-ip", "10.0.0.1", *extra]
            )
            self.assertEqual(getattr(arguments, attribute), expected)
        flags = ("lock_screen", "unlock_screen", "exit_student", "close_apps")
        for flag in flags:
            arguments = parser.parse_args(
                ["teacher", "appcmd", "-ip", "10.0.0.1", "--" + flag.replace("_", "-")]
            )
            self.assertTrue(getattr(arguments, flag))

    def test_students_command_defaults_and_overrides(self):
        parser = cli_parser.build_group_parser()
        arguments = parser.parse_args(["teacher", "students"])
        self.assertEqual(arguments.students, 8)
        self.assertEqual(arguments.report, 0)
        arguments = parser.parse_args(
            ["teacher", "students", "--seconds", "3", "--report", "2"]
        )
        self.assertEqual(arguments.students, 3)
        self.assertEqual(arguments.report, 2)

    def test_screen_command_actions(self):
        parser = cli_parser.build_group_parser()
        self.assertEqual(
            parser.parse_args(
                ["teacher", "screen", "-ip", "10.0.0.1", "--preview", "4"]
            ).preview,
            4,
        )
        self.assertEqual(
            parser.parse_args(
                ["teacher", "screen", "-ip", "10.0.0.1", "--view", "5"]
            ).view,
            5,
        )
        self.assertTrue(
            parser.parse_args(["teacher", "screen", "-ip", "10.0.0.1", "--probe"]).probe
        )
        self.assertTrue(
            parser.parse_args(
                ["teacher", "screen", "-ip", "10.0.0.1", "--stop"]
            ).view_stop
        )

    def test_control_and_closewindow_positional_fields(self):
        parser = cli_parser.build_group_parser()
        self.assertTrue(
            parser.parse_args(["teacher", "control", "-ip", "10.0.0.1"]).control
        )
        self.assertEqual(
            parser.parse_args(
                ["teacher", "closewindow", "-ip", "10.0.0.1", "记事本"]
            ).kill_window,
            "记事本",
        )
        self.assertEqual(
            parser.parse_args(["teacher", "chat", "-ip", "10.0.0.1", "安静"]).chat,
            "安静",
        )

    def test_local_commands(self):
        parser = cli_parser.build_group_parser()
        self.assertEqual(parser.parse_args(["local", "info"]).e, "g")
        self.assertEqual(
            parser.parse_args(["local", "firewall", "block"]).firewall, "block"
        )
        self.assertEqual(
            parser.parse_args(["local", "firewall", "allow"]).firewall, "allow"
        )

    def test_flat_parser_keeps_legacy_options(self):
        arguments = cli_parser.build_flat_parser().parse_args(
            ["-ip", "10.0.0.1", "-msg", "通知", "-l", "2", "-e", "r"]
        )
        self.assertEqual(arguments.msg, "通知")
        self.assertEqual(arguments.l, 2)
        self.assertEqual(arguments.e, "r")
        # 分类写法才有的字段也要有默认值，分发函数才不用处处判空。
        self.assertIsNone(arguments.firewall)
        self.assertIsNone(arguments.all_preview)

    def test_students_serve_accepts_optional_seconds(self):
        parser = cli_parser.build_group_parser()
        self.assertEqual(parser.parse_args(["teacher", "students", "--serve"]).serve, 0)
        self.assertEqual(
            parser.parse_args(["teacher", "students", "--serve", "5"]).serve, 5
        )
        # 没写 --serve 时保持 False，分发函数据此区分“不常驻”和“常驻到中断”。
        self.assertIs(parser.parse_args(["teacher", "students"]).serve, False)
        flat = cli_parser.build_flat_parser().parse_args(["-ip", "10.0.0.1", "--serve"])
        self.assertEqual(flat.serve, 0)

    def test_restriction_group_lists_stops_and_starts_student(self):
        parser = cli_parser.build_group_parser()
        stop = parser.parse_args(["restriction", "student"])
        self.assertTrue(stop.endstudent)
        self.assertFalse(stop.start_student)
        self.assertIsNone(stop.pid)
        self.assertFalse(stop.list)
        listing = parser.parse_args(["restriction", "student", "--list"])
        self.assertTrue(listing.list)
        # 只结束指定进程时可以不写目标地址，分发直接走本机操作。
        single = parser.parse_args(["restriction", "student", "--pid", "17600"])
        self.assertEqual(single.pid, [17600])
        self.assertIsNone(single.ip)
        started = parser.parse_args(
            ["restriction", "student", "--start", "--exe", "C:/x/StudentMain.exe"]
        )
        self.assertTrue(started.start_student)
        self.assertEqual(started.student_exe, "C:/x/StudentMain.exe")
        # 旧子命令名保留为别名，避免已有脚本失效。
        self.assertTrue(
            parser.parse_args(["restriction", "endstudent"]).endstudent,
        )
        flat = cli_parser.build_flat_parser().parse_args(
            ["--end-student", "--end-student-pid", "17600"]
        )
        self.assertTrue(flat.endstudent)
        self.assertEqual(flat.pid, [17600])
        flat_start = cli_parser.build_flat_parser().parse_args(["--start-student"])
        self.assertTrue(flat_start.start_student)


if __name__ == "__main__":
    unittest.main()
