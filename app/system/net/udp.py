"""UDP 发送、轮次等待与网络反馈检查。"""

import select
import socket
from time import monotonic, sleep

from app.system.net.data import Delivery, DeliveryState, SendOutcome
from app.system.net.reachability import ping_hosts
from app.system.net.targets import get_ip


def send(
    send_list,
    target_ip,
    port=4705,
    loops=1,
    interval=22,
    report=None,
    cancel_event=None,
):
    """用 UDP 把报文发送到目标地址。

    Args:
        send_list: 报文字节值列表的序列，每个元素是一条报文。
        target_ip: 目标地址，支持单地址、末段范围与 /24 网段。
        port: 目标 UDP 端口。
        loops: 发送轮数。
        interval: 相邻两轮的间隔秒数。
        report: 进度回调，接收中文状态文本。
        cancel_event: 取消信号，置位后尽快抛出取消异常。

    Returns:
        int: 实际发送的报文数量。
    """
    _check_send_arguments(send_list, port, loops, interval)

    target_host = get_ip(target_ip)
    # 同一批报文要发往多个目标并重复多轮，先统一转成 bytes 再循环，
    # 避免每次发送都重新编码一遍。
    payloads = [bytes(packet) for packet in send_list]
    sent_count = 0
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("操作已取消")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(1.0)
        for _ in _iter_rounds(loops, interval, cancel_event, report):
            for host in target_host:
                for payload in payloads:
                    if cancel_event and cancel_event.is_set():
                        raise RuntimeError("操作已取消")
                    client.sendto(payload, (host, port))
                    sent_count += 1
    return sent_count


def _iter_rounds(loops, interval, cancel_event, report):
    """按轮次产出序号，负责轮末进度与两轮之间的等待。

    单播与多目标发送的轮次节奏完全一样，抽出来避免两处各写一遍。

    Args:
        loops: 发送轮数。
        interval: 相邻两轮的间隔秒数，0 表示不等待。
        cancel_event: 取消信号，等待期间置位会立即抛出取消异常。
        report: 进度回调，可省略。

    Yields:
        int: 从 0 开始的轮次序号。
    """
    for times in range(loops):
        yield times
        if report:
            report("第 %d/%d 轮已发送" % (times + 1, loops))
        if times == loops - 1 or not interval:
            continue
        if cancel_event:
            if cancel_event.wait(interval):
                raise RuntimeError("操作已取消")
        else:
            sleep(interval)


def _check_send_arguments(send_list, port, loops, interval):
    """校验发送参数，供两种发送方式共用。"""
    if len(send_list) == 0:
        raise ValueError("没有可发送的报文")
    if not 1 <= port <= 65535:
        raise ValueError("端口必须在 1 到 65535 之间")
    if loops < 1:
        raise ValueError("发送轮数必须大于 0")
    if interval < 0:
        raise ValueError("发送间隔不能小于 0")


def send_tracked(
    send_list,
    target_ip,
    port=4705,
    loops=1,
    interval=22,
    report=None,
    cancel_event=None,
):
    """发送报文并判定每个目标是否送达。

    每条报文的发送方式与 :func:`send` 相同，区别是给每个目标建立已连接的
    UDP 套接字：目标主机或端口不可达时 Windows 会把 ICMP 反馈转换成套接字
    错误，据此可以分辨“对方没在接收”和“没有异常”。接收端是否执行了报文
    无法从这里确认——协议是单向的，对方不回执。

    Args:
        send_list: 报文字节值列表的序列，每个元素是一条报文。
        target_ip: 目标地址，支持单地址、末段范围与 /24 网段。
        port: 目标 UDP 端口。
        loops: 发送轮数。
        interval: 相邻两轮的间隔秒数。
        report: 进度回调，接收中文状态文本。
        cancel_event: 取消信号，置位后尽快抛出取消异常。

    Returns:
        SendOutcome: 发送总数与每个目标的送达判定。

    Raises:
        ValueError: 参数不合法。
        RuntimeError: 操作被取消。
    """
    _check_send_arguments(send_list, port, loops, interval)
    hosts = get_ip(target_ip)
    payloads = [bytes(packet) for packet in send_list]
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("操作已取消")
    sockets = {}
    sent = dict.fromkeys(hosts, 0)
    states = {}
    try:
        for host in hosts:
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(1.0)
            try:
                client.connect((host, port))
            except OSError as error:
                client.close()
                states[host] = (DeliveryState.UNREACHABLE, str(error))
                continue
            sockets[host] = client
        for _ in _iter_rounds(loops, interval, cancel_event, report):
            for host in hosts:
                client = sockets.get(host)
                if client is None:
                    continue
                for payload in payloads:
                    if cancel_event and cancel_event.is_set():
                        raise RuntimeError("操作已取消")
                    try:
                        client.send(payload)
                        sent[host] += 1
                    except ConnectionResetError:
                        # 10054 是目标端口回送的 ICMP 端口不可达，说明没人接收。
                        states.setdefault(host, (DeliveryState.REJECTED, ""))
                    except OSError as error:
                        states.setdefault(host, (DeliveryState.UNREACHABLE, str(error)))
        _collect_icmp_errors(sockets, states)
        _probe_silent_hosts(hosts, states)
    finally:
        for client in sockets.values():
            client.close()
    deliveries = []
    for host in hosts:
        state, detail = states.get(host, (DeliveryState.DELIVERED, ""))
        deliveries.append(
            Delivery(host=host, sent=sent[host], state=state, detail=detail)
        )
    return SendOutcome(sent=sum(sent.values()), deliveries=tuple(deliveries))


def _collect_icmp_errors(sockets, states, timeout=0.4):
    """短暂等待 ICMP 反馈，把套接字错误归到对应目标。

    Windows 的 ``select`` 一次最多处理 64 个句柄，目标较多时分批等待。
    """
    pending = [host for host in sockets if host not in states]
    if not pending:
        return
    deadline = monotonic() + timeout
    while pending and monotonic() < deadline:
        batch = pending[:60]
        try:
            readable, _, _ = select.select(
                [sockets[host] for host in batch], [], [], 0.05
            )
        except (OSError, TypeError, ValueError):
            return
        for host in batch:
            client = sockets[host]
            if client not in readable:
                continue
            pending.remove(host)
            try:
                client.recv(1)
            except ConnectionResetError:
                states[host] = (DeliveryState.REJECTED, "")
            except OSError as error:
                states[host] = (DeliveryState.UNREACHABLE, str(error))


def _probe_silent_hosts(hosts, states):
    """对没有收到 ICMP 错误的目标再做一次回显探测。

    地址不存在时 ARP 解析失败不会产生任何 ICMP 报文，只看发送反馈会把
    “根本不存在的主机”误判成已送达，所以这里用回显与 ARP 缓存确认主机是否在线。
    """
    pending = [host for host in hosts if host not in states]
    if not pending:
        return
    alive = ping_hosts(pending)
    for host in pending:
        if alive.get(host):
            states[host] = (DeliveryState.DELIVERED, "")
        else:
            states[host] = (
                DeliveryState.NO_RESPONSE,
                "主机可能不存在，或屏蔽了 ICMP 回显",
            )
