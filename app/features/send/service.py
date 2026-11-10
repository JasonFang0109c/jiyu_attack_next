"""发送参数校验、报文组装与结果汇总。"""

from app.packets.codec import pkg_sendlist, split_message
from app.packets.constants import LOGOFF_COMMAND, basicCMD
from app.system.net.targets import count_targets, get_ip
from app.system.net.udp import send_tracked


def validate_options(options):
    """校验发送参数，不合法时抛出带中文提示的 ValueError。"""
    if not options.target.strip():
        raise ValueError("请填写目标地址")
    try:
        count_targets(options.target.strip())
    except ValueError as error:
        raise ValueError("目标地址格式无效") from error
    if not 1 <= options.port <= 65535:
        raise ValueError("端口必须在 1 到 65535 之间")
    if options.loops < 1:
        raise ValueError("发送轮数必须大于 0")
    if options.interval < 0:
        raise ValueError("发送间隔不能小于 0")
    if options.extra not in {"", "r", "s", "l"}:
        raise ValueError("网络发送仅支持 r、s 或 l 扩展操作")
    if not options.message and not options.command and not options.extra:
        raise ValueError("至少填写消息、命令或选择设备操作")


def prepare_packets(options, report=None):
    """按发送参数组装报文列表，消息超长时拆成多个报文。

    Args:
        options: 发送参数。
        report: 进度回调，接收中文状态文本。

    Returns:
        list[list[int]]: 待发送报文。
    """
    validate_options(options)
    packets = []
    if options.message:
        for chunk in split_message(options.message):
            if options.cancel_event and options.cancel_event.is_set():
                raise RuntimeError("操作已取消")
            packets.append(pkg_sendlist("-msg", chunk))
        if report:
            report("已准备 %d 条消息" % len(packets))
    if options.command:
        packets.append(pkg_sendlist("-c", options.command))
    if options.extra in {"r", "s"}:
        packets.append(basicCMD["-" + options.extra].copy())
    elif options.extra == "l":
        packets.append(pkg_sendlist("-c", LOGOFF_COMMAND))
    return packets


def execute_send_report(options, report=None):
    """按发送参数发送报文，并汇总每个目标的送达判定。

    Args:
        options: 发送参数。
        report: 进度回调，接收中文状态文本。

    Returns:
        SendOutcome: 发送总数与每个目标的送达判定。
    """
    validate_options(options)
    emit = report or (lambda message: None)
    packets = prepare_packets(options, emit)
    target_hosts = get_ip(options.target.strip())
    emit("目标数量：%d，报文数量：%d" % (len(target_hosts), len(packets)))
    outcome = send_tracked(
        packets,
        options.target,
        options.port,
        options.loops,
        options.interval,
        emit,
        options.cancel_event,
    )
    failed = outcome.failed
    if failed:
        emit(
            "本机发送完成，共 %d 个报文；%d/%d 个目标失败：%s"
            % (
                outcome.sent,
                len(failed),
                len(outcome.deliveries),
                "；".join("%s %s" % (item.host, item.state.text) for item in failed),
            )
        )
    else:
        emit(
            "本机发送完成，共 %d 个报文；%d 个目标均未发现异常"
            % (outcome.sent, len(outcome.deliveries))
        )
    return outcome


def execute_send(options, report=None):
    """按发送参数组装并发送报文，返回发送的报文数量。"""
    return execute_send_report(options, report).sent
