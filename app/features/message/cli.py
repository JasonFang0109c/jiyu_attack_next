"""文本消息的命令行参数与报文适配。"""

from app.features.message.service import read_message
from app.features.send.cli import add_loop, add_port, add_target
from app.packets.codec import pkg_sendlist, split_message
from app.shared.logs import cli as cli_log


def register(commands, defaults):
    """注册功能子命令并沿用统一参数默认值。"""
    message = commands.add_parser("message", help="文本消息：发送自动分条的文本")
    message.set_defaults(**dict(defaults))
    add_target(message)
    add_port(message)
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
    add_loop(message)


def create_message_packets(arguments):
    """读取消息并按协议容量构造消息报文。"""
    log = cli_log.LOG
    send_list = []
    # 先统一读取消息来源，确保 -msg 与 --msg-file 的处理保持一致。
    message = read_message(arguments)
    if message:
        chunks = list(split_message(message))
        log.debug(
            "已读取消息",
            "消息",
            "字符数：%d，分条：%d" % (len(message), len(chunks)),
        )
        send_list.extend(pkg_sendlist("-msg", chunk) for chunk in chunks)
    return send_list
