"""装配各功能分组子命令。"""

import argparse

from NeoJiYuTrainer.Features.Command import Cli as command_cli
from NeoJiYuTrainer.Features.Device import Cli as device_cli
from NeoJiYuTrainer.Features.Files import Cli as files_cli
from NeoJiYuTrainer.Features.Message import Cli as message_cli
from NeoJiYuTrainer.Features.Shell import Cli as shell_cli
from NeoJiYuTrainer.Features.Student import Cli as student_cli
from NeoJiYuTrainer.Features.Uninstall import Cli as uninstall_cli
from NeoJiYuTrainer.Shared.Version import runtime_version

# 与图形界面侧边栏的分组一一对应。
GROUPS = {
    "classroom": "课堂助手",
    "remote": "远程攻击",
    "app": "应用",
}

# 每个分组下的子命令，同样对应图形界面的页面。
COMMANDS = {
    "classroom": {
        "student": "启停学生端",
    },
    "remote": {
        "message": "文本消息",
        "file": "文件传送",
        "device": "设备操作",
        "command": "远程命令",
        "shell": "反弹终端",
    },
    "app": {
        "uninstall": "卸载应用",
    },
}

GROUP_NAMES = tuple(GROUPS)


def _base_defaults():
    """子命令共用的属性默认值。

    统一提供分发逻辑所需的字段，避免每个功能命令重复补默认值。

    Returns:
        dict: 属性名到默认值的映射。
    """
    return {
        "ip": None,
        "p": 4705,
        "msg": None,
        "msg_file": None,
        "file": None,
        "c": None,
        "l": 1,
        "t": 22,
        "e": None,
        "shell": False,
        "file_ip": None,
        "file_timeout": 120,
        "firewall": None,
        "endstudent": False,
        "start_student": False,
        "student_exe": None,
        "student_path": False,
        "pid": None,
        "list": False,
        "no_guardian": False,
    }


def build_group_parser():
    """创建分类子命令解析器。

    Returns:
        argparse.ArgumentParser: 形如 ``remote message -ip ...`` 的解析器。
    """
    parser = argparse.ArgumentParser(
        prog="NeoJiYuTrainer",
        description="NeoJiYuTrainer：对抗极域电子教室的课堂工具，命令按图形界面的分组组织",
        epilog="分组：classroom 课堂助手、remote 远程攻击、local 本机工具。"
        "每条子命令对应图形界面里的一个页面，例如 remote message 对应“文本消息”。",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=runtime_version(),
        help="显示版本号并退出",
    )
    groups = parser.add_subparsers(
        title="分组", dest="group", metavar="分组", required=True
    )

    classroom = groups.add_parser("classroom", help="课堂助手")
    classroom_commands = classroom.add_subparsers(
        title="子命令", dest="command", metavar="子命令", required=True
    )
    student_cli.register(classroom_commands, _base_defaults())

    remote = groups.add_parser("remote", help="远程攻击")
    remote_commands = remote.add_subparsers(
        title="子命令", dest="command", metavar="子命令", required=True
    )
    message_cli.register(remote_commands, _base_defaults())
    files_cli.register(remote_commands, _base_defaults())
    device_cli.register(remote_commands, _base_defaults())
    command_cli.register(remote_commands, _base_defaults())
    shell_cli.register(remote_commands, _base_defaults())

    app = groups.add_parser("app", help="应用")
    app_commands = app.add_subparsers(
        title="子命令", dest="command", metavar="子命令", required=True
    )
    uninstall_cli.register(app_commands, _base_defaults())

    return parser
