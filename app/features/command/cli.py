"""远程命令的参数注册与报文适配。"""

from app.features.send.cli import add_loop, add_port, add_target
from app.packets.codec import pkg_sendlist
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
    add_loop(command)


def add_flat_arguments(parser):
    """注册本功能兼容的扁平参数。"""
    parser.add_argument(
        "-c",
        type=str,
        metavar="COMMAND",
        help='远程命令，例如 -c "cmd.exe /c ipconfig"',
    )


def create_command_packets(arguments):
    """将远程命令转换为待发送报文。"""
    log = cli_log.LOG
    send_list = []
    if arguments.c:
        log.debug("已加入命令", "命令", "命令：%s" % arguments.c)
        send_list.append(pkg_sendlist("-c", arguments.c))
    return send_list
