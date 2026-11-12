"""远程发送的公共参数、组合发送与终端结果输出。"""

from app.shared.logs import cli as cli_log
from app.system.net.udp import send_tracked


def add_target(parser, required=True):
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


def add_port(parser):
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


def add_loop(parser):
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


def create_send_packets(arguments):
    """按分组子命令构造消息、命令或设备操作报文。"""
    # 功能注册复用本模块的目标参数，运行时再取构造器以避免导入环。
    from app.features.command.cli import create_command_packets
    from app.features.device.cli import create_device_packets
    from app.features.message.cli import create_message_packets

    packet_creators = {
        "message": create_message_packets,
        "command": create_command_packets,
        "device": create_device_packets,
    }
    try:
        create_packets = packet_creators[arguments.command]
    except KeyError as error:
        raise ValueError("不支持的远程发送命令：%s" % arguments.command) from error
    return create_packets(arguments)


def print_delivery(outcome):
    """逐个目标输出送达判定，并给出成功与失败的数量。

    判定依据只有网络反馈：收到 ICMP 不可达说明报文没有被接收端收到，
    没有反馈只能说“未发现异常”，无法证明对方执行了命令。
    """
    log = cli_log.LOG
    for item in outcome.deliveries:
        if item.ok:
            print(
                "[成功] %s：%s（%d 个报文）" % (item.host, item.state.text, item.sent)
            )
            log.info(
                "目标送达未发现异常",
                "发送",
                "%s：%s（%d 个报文）" % (item.host, item.state.text, item.sent),
            )
        elif item.detail:
            print("[-] [失败] %s：%s（%s）" % (item.host, item.state.text, item.detail))
            log.error(
                "目标发送失败",
                "发送",
                "%s：%s（%s）" % (item.host, item.state.text, item.detail),
            )
        else:
            print("[-] [失败] %s：%s" % (item.host, item.state.text))
            log.error("目标发送失败", "发送", "%s：%s" % (item.host, item.state.text))
    total = len(outcome.deliveries)
    failed = len(outcome.failed)
    if failed:
        print("共 %d 个目标：成功 %d，失败 %d" % (total, total - failed, failed))
    else:
        print("共 %d 个目标：全部未发现异常" % total)


def run_send(arguments):
    """执行一个远程消息、命令或设备操作子命令。"""
    log = cli_log.LOG
    send_list = create_send_packets(arguments)
    if send_list:
        log.info(
            "开始发送",
            "发送",
            "目标：%s；端口：%d；报文：%d 个；循环：%d 次；间隔：%d 秒"
            % (
                arguments.ip,
                arguments.p,
                len(send_list),
                arguments.l,
                arguments.t,
            ),
        )
        outcome = send_tracked(
            send_list,
            arguments.ip,
            arguments.p,
            arguments.l,
            arguments.t,
            report=print,
        )
        print_delivery(outcome)
    else:
        raise ValueError(
            "请使用 remote message、remote command 或 remote device 子命令"
        )
    return 0
