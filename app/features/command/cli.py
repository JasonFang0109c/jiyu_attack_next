"""远程命令的参数注册与报文适配。"""

from app.features.send.cli import add_loop, add_port, add_target
from app.packets.codec import pkg_sendlist
from app.packets.elevated import elevated_packets
from app.shared.logs import cli as cli_log


def register(commands, defaults):
    """注册功能子命令并沿用统一参数默认值。"""
    command = commands.add_parser("command", help="远程命令：执行一条命令")
    command.set_defaults(**dict(defaults))
    add_target(command)
    add_port(command)
    command.add_argument(
        "-c", required=True, type=str, help='要执行的命令，例如 "cmd.exe /c ipconfig"'
    )
    command.add_argument(
        "--system",
        action="store_true",
        help="以 SYSTEM 计划任务执行：脚本由本机临时托管，命令不进报文正文",
    )
    add_loop(command)


def create_command_packets(arguments):
    """将远程命令转换为待发送报文。"""
    log = cli_log.LOG
    send_list = []
    if arguments.c:
        log.debug("已加入命令", "命令", "命令字符数：%d" % len(arguments.c))
        if getattr(arguments, "system", False):
            send_list.extend(elevated_packets(arguments.ip, arguments.c))
        else:
            send_list.append(pkg_sendlist("-c", arguments.c))
    return send_list
