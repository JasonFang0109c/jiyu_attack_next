"""报文构造、消息分片与目标地址解析。"""

import ipaddress
import sys
from dataclasses import dataclass
from threading import Event
from typing import Optional

from .constants import (
    COMMAND_MAX_BYTES,
    COMMAND_OFFSET,
    LOGOFF_COMMAND,
    MESSAGE_MAX_BYTES,
    MESSAGE_OFFSET,
    basicCMD,
)


def format_b4_send(content):
    """把文本编码为 UTF-16LE 字节值列表，供报文字节数组填充。"""
    return list(content.encode("utf-16le"))


def read_message(arguments):
    """读取消息文本：优先使用 `--msg`，其次读取 `--msg-file`（`-` 表示标准输入）。"""
    if arguments.msg_file is None:
        return arguments.msg
    if arguments.msg_file == "-":
        return sys.stdin.read()
    with open(arguments.msg_file, encoding="utf-8-sig", newline="") as message_file:
        return message_file.read()


def split_message(content):
    """按报文容量把消息切成若干分片。

    Args:
        content: 待发送的消息文本。

    Yields:
        str: 不超过 ``MESSAGE_MAX_BYTES`` 的分片。

    Raises:
        ValueError: 消息包含 NUL 字符。
    """
    if "\x00" in content:
        raise ValueError("消息不能包含 NUL 字符")
    # 容量以 UTF-16 字节数计算：BMP 字符占 2 字节，增补平面字符（emoji 等）占 4 字节。
    # 逐字符 encode 只为了拿长度，改为按码位判断宽度后再整体切片。
    chunk_start = 0
    byte_count = 0
    for index, character in enumerate(content):
        character_bytes = 4 if ord(character) > 0xFFFF else 2
        if byte_count + character_bytes > MESSAGE_MAX_BYTES:
            yield content[chunk_start:index]
            chunk_start = index
            byte_count = 0
        byte_count += character_bytes
    if chunk_start < len(content):
        yield content[chunk_start:]


def _target_value(ip):
    """校验地址文本并去掉首尾空白。

    Raises:
        ValueError: 地址为空或不是字符串。
    """
    if not isinstance(ip, str) or not ip.strip():
        raise ValueError("请填写目标地址")
    return ip.strip()


def _target_spec(value):
    """把目标地址解析成 ``(首个地址整数, 地址数量)``。

    展开地址与只统计数量共用这一份解析，避免两处规则走偏。

    Raises:
        ValueError: 地址格式不受支持。
    """
    if "-" in value:
        if value.count("-") != 1:
            raise ValueError
        start, end = value.split("-")
        start_address = ipaddress.IPv4Address(start)
        if not end.isdigit():
            raise ValueError
        start_octet = int(start_address) & 0xFF
        end_octet = int(end)
        if not 1 <= start_octet <= end_octet <= 254:
            raise ValueError
        return int(start_address), end_octet - start_octet + 1
    if "/" in value:
        if not value.endswith("/24"):
            raise ValueError
        network = ipaddress.IPv4Network(value, strict=False)
        # /24 的 hosts() 只包含可用主机地址，首地址是网络地址加一。
        return int(network.network_address) + 1, 254
    return int(ipaddress.IPv4Address(value)), 1


def get_ip(ip):
    """把目标地址展开为 IP 列表。

    Args:
        ip: 单个地址、``末段-末段`` 范围或 ``/24`` 网段。

    Returns:
        list[str]: 展开后的 IPv4 地址列表。

    Raises:
        ValueError: 地址为空或格式不受支持。
    """
    value = _target_value(ip)
    try:
        start, count = _target_spec(value)
    except ValueError as error:
        raise ValueError("IP 格式错误，请使用单个地址、末段范围或 /24 网段") from error
    return [str(ipaddress.IPv4Address(start + offset)) for offset in range(count)]


def count_targets(ip):
    """只统计地址数量，不逐个构造地址对象。

    界面每次输入变化都要刷新目标数量，为了取 len 而展开 254 个地址会拖慢输入
    响应，因此单独提供计数入口。

    Args:
        ip: 单个地址、``末段-末段`` 范围或 ``/24`` 网段。

    Returns:
        int: 地址数量。

    Raises:
        ValueError: 地址为空或格式不受支持。
    """
    value = _target_value(ip)
    try:
        return _target_spec(value)[1]
    except ValueError as error:
        raise ValueError("IP 格式错误，请使用单个地址、末段范围或 /24 网段") from error


_SENDLIST_SPECS = {
    "-msg": (MESSAGE_OFFSET, MESSAGE_MAX_BYTES, "消息", "单条消息超过报文容量"),
    "-c": (
        COMMAND_OFFSET,
        COMMAND_MAX_BYTES,
        "命令",
        "命令超过报文容量（最多 %d 个 UTF-16 单元）" % (COMMAND_MAX_BYTES // 2),
    ),
}


def pkg_sendlist(cmdtype, content):
    """把内容填入报文模板，返回可直接发送的字节值列表。

    Args:
        cmdtype: ``"-msg"`` 表示文本消息，``"-c"`` 表示远程命令。
        content: 待填充的文本。

    Returns:
        list[int]: 报文模板副本。

    Raises:
        ValueError: 报文类型未知、内容含 NUL 字符或超过报文容量。
    """
    spec = _SENDLIST_SPECS.get(cmdtype)
    if spec is None:
        raise ValueError("未知的报文类型：%s" % cmdtype)
    offset, capacity, label, overflow = spec
    if "\x00" in content:
        raise ValueError("%s不能包含 NUL 字符" % label)
    arrs = format_b4_send(content)
    if len(arrs) > capacity:
        raise ValueError(overflow)
    result = basicCMD[cmdtype].copy()
    result[offset : offset + len(arrs)] = arrs
    result[offset + len(arrs) : offset + len(arrs) + 2] = [0, 0]
    return result


@dataclass
class SendOptions:
    """一次发送所需的全部参数。

    Attributes:
        target: 目标地址，支持单地址、末段范围与 /24 网段。
        port: 目标 UDP 端口，默认 4705。
        message: 文本消息，超长时自动分条。
        command: 远程命令。
        extra: 设备扩展操作，取 ``r``、``s``、``l`` 之一。
        loops: 发送轮数。
        interval: 相邻两轮的间隔秒数。
        cancel_event: 取消信号，置位后尽快抛出取消异常。
    """

    target: str
    port: int = 4705
    message: str = ""
    command: str = ""
    extra: str = ""
    loops: int = 1
    interval: float = 22
    cancel_event: Optional[Event] = None


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
