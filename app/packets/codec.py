"""报文编码、消息分片与容量校验。"""

from app.packets.constants import (
    COMMAND_MAX_BYTES,
    COMMAND_OFFSET,
    MESSAGE_MAX_BYTES,
    MESSAGE_OFFSET,
    basicCMD,
)


def format_b4_send(content):
    """把文本编码为 UTF-16LE 字节值列表，供报文字节数组填充。"""
    return list(content.encode("utf-16le"))


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
