"""文件传送的命令行参数与结果输出。"""

from pathlib import Path

from app.features.files.service import format_size, transfer_file
from app.features.send.cli import add_port, add_target
from app.shared.logs import cli as cli_log


def register(commands, defaults):
    """注册功能子命令并沿用统一参数默认值。"""
    file_command = commands.add_parser(
        "file", help="文件传送：把文件或文件夹送到目标桌面"
    )
    file_command.set_defaults(**dict(defaults))
    add_target(file_command)
    add_port(file_command)
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


def add_flat_arguments(parser, message_options):
    """注册本功能兼容的扁平参数。"""
    message_options.add_argument(
        "--file",
        type=str,
        nargs="+",
        metavar="PATH",
        help="传送一个或多个文件、文件夹到目标电脑桌面，文件夹按原结构递归",
    )
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


def run_file_transfer(arguments):
    """执行文件传送并输出传送结果。"""
    log = cli_log.LOG
    # argparse 给出的是列表；直接调用时允许传单个路径，统一成列表再下发。
    paths = arguments.file
    if isinstance(paths, (str, Path)):
        paths = [str(paths)]
    else:
        paths = [str(path) for path in paths]
    log.info("开始文件传送", "文件传送", "目标：%s" % arguments.ip)
    log.debug(
        "文件传送参数",
        "文件传送",
        "路径：%s；端口：%s；发送端：%s；超时：%s 秒"
        % (paths, arguments.p, arguments.file_ip or "自动检测", arguments.file_timeout),
    )
    result = transfer_file(
        arguments.ip,
        arguments.p,
        paths[0],
        listen_ip=arguments.file_ip,
        timeout=arguments.file_timeout,
        report=print,
        paths=paths,
    )
    log.debug(
        "文件传送完成",
        "文件传送",
        "文件：%s；数量：%s；大小：%d 字节；监听端口：%s"
        % (
            result.get("files"),
            result.get("file_count"),
            result["size"],
            result["port"] if result.get("port") is not None else "未启动",
        ),
    )
    if len(result["targets"]) == 1:
        print("文件已传送：%s（%s）" % (result["name"], format_size(result["size"])))
    else:
        print(
            "文件已传送到 %d 个目标桌面：%s（%s）"
            % (len(result["targets"]), result["name"], format_size(result["size"]))
        )
    log.info("文件已传送", "文件传送", "目标：%s" % "、".join(result["transferred"]))
    return 0
