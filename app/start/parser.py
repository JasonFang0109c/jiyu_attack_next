"""装配各功能分组子命令。"""

import argparse

from app.features.command import cli as command_cli
from app.features.device import cli as device_cli
from app.features.files import cli as files_cli
from app.features.firewall import cli as firewall_cli
from app.features.local import cli as local_cli
from app.features.message import cli as message_cli
from app.features.shell import cli as shell_cli
from app.features.student import cli as student_cli
from app.shared.version import runtime_version

# 与图形界面侧边栏的分组一一对应。
GROUPS = {
    "restriction": "解除限制",
    "remote": "远程攻击",
    "local": "本机工具",
}

# 每个分组下的子命令，同样对应图形界面的页面。
COMMANDS = {
    "restriction": {
        "student": "启停学生端",
    },
    "remote": {
        "message": "文本消息",
        "file": "文件传送",
        "device": "设备操作",
        "command": "远程命令",
        "shell": "反弹终端",
    },
    "local": {
        "info": "本机信息",
        "firewall": "防火墙",
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
        "shell_port": 0,
        "shell_ip": "",
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
        prog="JiYuAttackNext",
        description="极域课堂 UDP 报文测试工具：命令按图形界面的分组组织",
        epilog="分组：restriction 解除限制、remote 远程攻击、local 本机工具。"
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

    restriction = groups.add_parser("restriction", help="解除限制")
    restriction_commands = restriction.add_subparsers(
        title="子命令", dest="command", metavar="子命令", required=True
    )
    student_cli.register(restriction_commands, _base_defaults())

    remote = groups.add_parser("remote", help="远程攻击")
    remote_commands = remote.add_subparsers(
        title="子命令", dest="command", metavar="子命令", required=True
    )
    message_cli.register(remote_commands, _base_defaults())
    files_cli.register(remote_commands, _base_defaults())
    device_cli.register(remote_commands, _base_defaults())
    command_cli.register(remote_commands, _base_defaults())
    shell_cli.register(remote_commands, _base_defaults())

    local = groups.add_parser("local", help="本机工具")
    local_commands = local.add_subparsers(
        title="子命令", dest="command", metavar="子命令", required=True
    )
    local_cli.register(local_commands, _base_defaults())
    firewall_cli.register(local_commands, _base_defaults())

    return parser
