"""命令行解析测试：分组子命令是唯一支持的调用语法。"""

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
            # endstudent 是分组命令别名，不作为正式命令重复列出。
            self.assertEqual([item for item in sub if item in commands], list(commands))

    def test_message_command_keeps_shared_fields(self):
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

    def test_restriction_group_lists_stops_and_starts_student(self):
        parser = cli_parser.build_group_parser()
        stop = parser.parse_args(["restriction", "student"])
        self.assertTrue(stop.endstudent)
        self.assertFalse(stop.start_student)
        self.assertIsNone(stop.pid)
        self.assertFalse(stop.list)
        listing = parser.parse_args(["restriction", "student", "--list"])
        self.assertTrue(listing.list)
        single = parser.parse_args(["restriction", "student", "--pid", "17600"])
        self.assertEqual(single.pid, [17600])
        self.assertIsNone(single.ip)
        started = parser.parse_args(
            ["restriction", "student", "--start", "--exe", "C:/x/StudentMain.exe"]
        )
        self.assertTrue(started.start_student)
        self.assertEqual(started.student_exe, "C:/x/StudentMain.exe")
        self.assertTrue(
            parser.parse_args(["restriction", "endstudent"]).endstudent,
        )

    def test_legacy_flat_syntax_is_rejected(self):
        parser = cli_parser.build_group_parser()
        for arguments in (
            ["-ip", "10.0.0.1", "-msg", "通知"],
            ["--start-student"],
            ["-e", "r"],
        ):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                parser.parse_args(arguments)


if __name__ == "__main__":
    unittest.main()
