"""远程命令的参数注册与报文适配。"""

from app.features.send.cli import add_loop, add_port, add_target
from app.packets.elevated import elevated_packets
from app.shared.logs import cli as cli_log


def register(commands, defaults):
    """注册功能子命令并沿用统一参数默认值。"""
    command = commands.add_parser("command", help="远程命令：以 SYSTEM 执行一条命令")
    command.set_defaults(**dict(defaults))
    add_target(command)
    add_port(command)
    command.add_argument(
        "-c", required=True, type=str, help='要执行的命令，例如 "cmd.exe /c ipconfig"'
    )
    add_loop(command)


def create_command_packets(arguments):
    """将远程命令转换为待发送报文。

    命令正文不进报文：由本机临时 HTTP 托管的脚本注册 SYSTEM 计划任务执行。
    """
    log = cli_log.LOG
    send_list = []
    if arguments.c:
        log.debug("已加入命令", "命令", "命令字符数：%d" % len(arguments.c))
        send_list.extend(elevated_packets(arguments.ip, arguments.c))
    return send_list
