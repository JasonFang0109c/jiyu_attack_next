"""命令行参数解析：按图形界面的分组提供分类子命令，并保留扁平写法。

图形界面的侧边栏分成“解除限制”“远程攻击”“本机工具”三组，每组下面是
具体页面；这里的子命令结构与之一一对应，一个页面就是一条子命令。
"""

import argparse

from ..core import runtime_version

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


def _add_target(parser, required=True):
    """给子命令加上目标地址参数。

    Args:
        parser: 子命令解析器。
        required: 目标地址是否必填。
    """
    parser.add_argument(
        "-ip",
        type=str,
        required=required,
        metavar="ADDRESS",
        help="目标地址，支持单个地址、末段范围（1-50）与 /24 网段",
    )


def _add_port(parser):
    """给子命令加上目标端口参数。"""
    parser.add_argument(
        "-p",
        "--port",
        dest="p",
        type=int,
        default=4705,
        metavar="PORT",
        help="目标 UDP 端口，默认 4705",
    )


def _add_loop(parser):
    """给子命令加上轮数与间隔参数。"""
    parser.add_argument(
        "-l",
        type=int,
        default=1,
        metavar="COUNT",
        help="重复发送的轮数，默认 1",
    )
    parser.add_argument(
        "-t",
        type=int,
        default=22,
        metavar="SECONDS",
        help="两轮之间的间隔秒数，默认 22",
    )


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
    _build_restriction(restriction_commands)

    remote = groups.add_parser("remote", help="远程攻击")
    remote_commands = remote.add_subparsers(
        title="子命令", dest="command", metavar="子命令", required=True
    )
    _build_remote(remote_commands)

    local = groups.add_parser("local", help="本机工具")
    local_commands = local.add_subparsers(
        title="子命令", dest="command", metavar="子命令", required=True
    )
    _build_local(local_commands)

    return parser


def _build_remote(commands):
    """注册远程攻击分组下的子命令。"""
    message = commands.add_parser("message", help="文本消息：发送自动分条的文本")
    message.set_defaults(**_base_defaults())
    _add_target(message)
    _add_port(message)
    message_options = message.add_mutually_exclusive_group(required=True)
    message_options.add_argument(
        "-msg", type=str, help="消息正文，支持多行；超长内容自动分条"
    )
    message_options.add_argument(
        "--msg-file",
        type=str,
        metavar="PATH",
        help="从 UTF-8 文件读取消息；使用 - 从标准输入读取",
    )
    _add_loop(message)

    file_command = commands.add_parser(
        "file", help="文件传送：把文件或文件夹送到目标桌面"
    )
    file_command.set_defaults(**_base_defaults())
    _add_target(file_command)
    _add_port(file_command)
    file_command.add_argument(
        "--file",
        type=str,
        nargs="+",
        required=True,
        metavar="PATH",
        help="一个或多个文件、文件夹，文件夹按原结构递归",
    )
    file_command.add_argument(
        "--file-ip", type=str, metavar="IP", help="发送端 IP，默认自动检测"
    )
    file_command.add_argument(
        "--file-timeout",
        type=int,
        default=120,
        metavar="SECONDS",
        help="等待目标下载文件的秒数，默认 120",
    )

    device = commands.add_parser("device", help="设备操作：重启、关机、注销")
    device.set_defaults(**_base_defaults())
    _add_target(device)
    _add_port(device)
    device_actions = device.add_mutually_exclusive_group(required=True)
    device_actions.add_argument(
        "--reboot",
        dest="e",
        action="store_const",
        const="r",
        help="重启目标电脑",
    )
    device_actions.add_argument(
        "--shutdown",
        dest="e",
        action="store_const",
        const="s",
        help="关闭目标电脑",
    )
    device_actions.add_argument(
        "--logoff",
        dest="e",
        action="store_const",
        const="l",
        help="注销当前用户（走远程命令 shutdown /l）",
    )

    command = commands.add_parser("command", help="远程命令：执行一条命令")
    command.set_defaults(**_base_defaults())
    _add_target(command)
    _add_port(command)
    command.add_argument(
        "-c", required=True, type=str, help='要执行的命令，例如 "cmd.exe /c ipconfig"'
    )
    _add_loop(command)

    shell = commands.add_parser("shell", help="反弹终端：本机监听并让目标连回来")
    shell.set_defaults(**_base_defaults())
    _add_target(shell)
    _add_port(shell)
    shell.set_defaults(shell=True)
    shell.add_argument(
        "--shell-port",
        type=int,
        default=0,
        metavar="PORT",
        help="本机监听端口，默认 0 表示随机",
    )
    shell.add_argument(
        "--shell-ip",
        type=str,
        default="",
        metavar="IP",
        help="写进目标连接命令的本机地址，默认自动探测",
    )


def _build_local(commands):
    """注册本机工具分组下的子命令。"""
    info = commands.add_parser("info", help="本机信息：本机地址与学生端端口")
    info.set_defaults(**_base_defaults())
    info.set_defaults(e="g")

    firewall = commands.add_parser("firewall", help="防火墙：阻断或恢复学生端连接")
    firewall.set_defaults(**_base_defaults())
    firewall.add_argument(
        "firewall",
        choices=["block", "allow"],
        metavar="ACTION",
        help="block 阻断学生端、allow 恢复允许",
    )


def _build_restriction(commands):
    """注册解除限制分组下的子命令。"""
    student = commands.add_parser(
        "student",
        aliases=("endstudent",),
        help="启停学生端：按当前状态启动或结束本机极域学生端",
        description="启停本机极域学生端。不带选项时按当前状态决定方向："
        "有学生端在运行就结束它、腾出被独占的 4705 端口；没有就启动它、"
        "恢复课堂管理。非管理员时通过 UAC 提权执行。",
        epilog="示例：restriction student 按状态切换；"
        "restriction student --list 只查看；restriction student --start 强制启动。",
    )
    defaults = _base_defaults()
    defaults["endstudent"] = True
    student.set_defaults(**defaults)
    student.add_argument(
        "--list",
        action="store_true",
        help="只列出学生端进程与占用端口，不做任何改动",
    )
    student.add_argument(
        "--start",
        dest="start_student",
        action="store_true",
        help="启动学生端，路径留空时自动查找 StudentMain.exe",
    )
    student.add_argument(
        "--exe",
        dest="student_exe",
        metavar="PATH",
        help="配合 --start：指定学生端主程序的完整路径",
    )
    student.add_argument(
        "--pid",
        type=int,
        action="append",
        metavar="PID",
        help="只结束指定进程号，可重复；不写则按当前状态切换或结束全部",
    )


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
    parser.add_argument("-ip", type=str, help="ip 指定目标IP地址")
    parser.add_argument(
        "-p", type=int, default=4705, help="port 指定监听端口，默认端口为4705"
    )
    message_options = parser.add_mutually_exclusive_group()
    message_options.add_argument(
        "-msg", type=str, help="发送文本消息，支持多行；超长内容自动分条"
    )
    message_options.add_argument(
        "--msg-file",
        type=str,
        metavar="PATH",
        help="从 UTF-8 文件读取消息；使用 - 从标准输入读取",
    )
    message_options.add_argument(
        "--file",
        type=str,
        nargs="+",
        metavar="PATH",
        help="传送一个或多个文件、文件夹到目标电脑桌面，文件夹按原结构递归",
    )
    parser.add_argument(
        "-c", type=str, help='command命令 eg: -c   "cmd.exe /c ipconfig"'
    )
    parser.add_argument("-l", type=int, default=1, help="循环次数，默认为1")
    parser.add_argument("-t", type=int, default=22, help="循环时间间隔，默认是22秒")
    parser.add_argument(
        "--file-ip", type=str, metavar="IP", help="文件传送时发送端 IP，默认自动检测"
    )
    parser.add_argument(
        "--file-timeout",
        type=int,
        default=120,
        metavar="SECONDS",
        help="等待目标下载文件的秒数，默认 120",
    )
    parser.add_argument(
        "-e",
        type=str,
        choices=["r", "s", "l", "g", "break", "continue", "nc"],
        help=(
            "额外选项：r 重启、s 关机、l 注销、g 本机信息、"
            "break 阻断学生端、continue 恢复允许、nc 反弹终端"
        ),
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help="启动反弹终端：本机监听并通过远程命令让目标连回来交互",
    )
    parser.add_argument(
        "--shell-port",
        type=int,
        default=0,
        metavar="PORT",
        help="反弹终端的本机监听端口，默认 0 表示随机",
    )
    parser.add_argument(
        "--shell-ip",
        type=str,
        default="",
        metavar="IP",
        help="反弹终端写进目标连接命令的本机地址，默认自动探测",
    )
    parser.add_argument(
        "--end-student",
        dest="endstudent",
        action="store_true",
        help="结束本机正在运行的极域学生端进程，腾出 4705 端口（需要管理员权限）",
    )
    parser.add_argument(
        "--start-student",
        dest="start_student",
        action="store_true",
        help="启动本机极域学生端，恢复课堂管理（需要管理员权限）",
    )
    parser.add_argument(
        "--student-exe",
        dest="student_exe",
        metavar="PATH",
        help="配合 --start-student：指定学生端主程序的完整路径",
    )
    parser.add_argument(
        "--end-student-pid",
        dest="pid",
        type=int,
        action="append",
        metavar="PID",
        help="配合 --end-student：只结束指定进程号，可重复",
    )
    parser.add_argument(
        "--list-student",
        dest="list",
        action="store_true",
        help="列出本机学生端进程与占用端口，不结束",
    )
    return parser
