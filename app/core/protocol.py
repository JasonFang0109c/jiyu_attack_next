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


def get_ip(ip):
    if not isinstance(ip, str) or not ip.strip():
        raise ValueError("请填写目标地址")
    value = ip.strip()
    try:
        if "-" in value:
            if value.count("-") != 1:
                raise ValueError
            start, end = value.split("-")
            start_address = ipaddress.IPv4Address(start)
            if not end.isdigit():
                raise ValueError
            start_octet = int(str(start_address).split(".")[3])
            end_octet = int(end)
            if not 1 <= start_octet <= end_octet <= 254:
                raise ValueError
            return [
                str(ipaddress.IPv4Address(int(start_address) + offset))
                for offset in range(end_octet - start_octet + 1)
            ]
        if "/" in value:
            if not value.endswith("/24"):
                raise ValueError
            return [
                str(host) for host in ipaddress.IPv4Network(value, strict=False).hosts()
            ]
        return [str(ipaddress.IPv4Address(value))]
    except ValueError as error:
        raise ValueError("IP 格式错误，请使用单个地址、末段范围或 /24 网段") from error


def pkg_sendlist(cmdtype, content):
    arrs = format_b4_send(content)
    if cmdtype == "-msg":
        if "\x00" in content:
            raise ValueError("消息不能包含 NUL 字符")
        if len(arrs) > MESSAGE_MAX_BYTES:
            raise ValueError("单条消息超过报文容量")
        result = basicCMD["-msg"].copy()
        result[MESSAGE_OFFSET : MESSAGE_OFFSET + len(arrs)] = arrs
        result[MESSAGE_OFFSET + len(arrs) : MESSAGE_OFFSET + len(arrs) + 2] = [0, 0]
    elif cmdtype == "-c":
        if "\x00" in content:
            raise ValueError("命令不能包含 NUL 字符")
        if len(arrs) > COMMAND_MAX_BYTES:
            raise ValueError(
                "命令超过报文容量（最多 %d 个 UTF-16 单元）" % (COMMAND_MAX_BYTES // 2)
            )
        result = basicCMD["-c"].copy()
        result[COMMAND_OFFSET : COMMAND_OFFSET + len(arrs)] = arrs
        result[COMMAND_OFFSET + len(arrs) : COMMAND_OFFSET + len(arrs) + 2] = [0, 0]
    return result


@dataclass
class SendOptions:
    target: str
    port: int = 4705
    message: str = ""
    command: str = ""
    extra: str = ""
    loops: int = 1
    interval: float = 22
    cancel_event: Optional[Event] = None


def validate_options(options):
    if not options.target.strip():
        raise ValueError("请填写目标地址")
    try:
        get_ip(options.target.strip())
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
