"""命令行解析的测试：分组子命令与扁平写法共用同一套执行字段。"""

import unittest

from app.start import parser as cli_parser


class GroupParserTests(unittest.TestCase):
    def test_groups_match_gui_sidebar(self):
        self.assertEqual(
            list(cli_parser.GROUPS),
            ["restriction", "remote", "local"],
        )
        self.assertEqual(
            list(cli_parser.COMMANDS["remote"]),
            ["message", "file", "device", "command", "shell"],
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
        self.assertFalse(arguments.shell)

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
