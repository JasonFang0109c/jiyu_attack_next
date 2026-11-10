"""装配各功能子命令与兼容的扁平命令行语法。"""

import argparse

from app.features.command import cli as command_cli
from app.features.device import cli as device_cli
from app.features.files import cli as files_cli
from app.features.firewall import cli as firewall_cli
from app.features.local import cli as local_cli
from app.features.message import cli as message_cli
from app.features.send import cli as send_cli
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

    分发函数沿用扁平写法的字段名，两条解析路径因此能共用同一套执行代码。

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
        "pid": None,
        "list": False,
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


def build_flat_parser():
    """创建扁平写法解析器。

    兼容来源项目与本程序早期的写法（``-ip ... -msg ...``），保留全部旧参数。

    Returns:
        argparse.ArgumentParser: 扁平参数解析器。
    """
    parser = argparse.ArgumentParser(description="极域课堂 UDP 报文测试工具")
    # 分类写法才有的字段在这里补成默认值，分发函数因此能共用同一套属性名。
    parser.set_defaults(**_base_defaults())
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=runtime_version(),
        help="显示版本号并退出",
    )
    send_cli.add_flat_target(parser)
    message_options = parser.add_mutually_exclusive_group()
    message_cli.add_flat_arguments(message_options)
    files_cli.add_flat_arguments(parser, message_options)
    command_cli.add_flat_arguments(parser)
    send_cli.add_loop(parser)
    # 旧 -e 同时覆盖多个功能，保留在兼容语法装配处。
    parser.add_argument(
        "-e",
        type=str,
        choices=["r", "s", "l", "g", "break", "continue", "nc"],
        help=(
            "额外选项：r 重启、s 关机、l 注销、g 本机信息、"
            "break 阻断学生端、continue 恢复允许、nc 反弹终端"
        ),
    )
    shell_cli.add_flat_arguments(parser)
    student_cli.add_flat_arguments(parser)
    return parser
