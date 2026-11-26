"""读取极域卸载密码，移植自 JiYuTrainer（MIT）的 ``UnDecryptJiyuKnock``。

新版极域把明文换成了 ``Passwd[123456]`` 标记，真正的密码以注册表二进制
``Knock1`` 保存；这里只做本地读取与解密，不联网、不修改注册表。
"""

import sys

from app.features.classroom.data import (
    KNOCK_KEY_PATHS,
    KNOCK_MAX_LENGTH,
    KNOCK_VALUE_NAME,
    KNOCK_XOR_FIRST,
    KNOCK_XOR_SECOND,
    PASSWORD_KEY_PATHS,
    PASSWORD_KNOCK_SENTINEL,
    PASSWORD_PLAIN_PREFIX_LENGTH,
    PASSWORD_VALUE_NAME,
)


def decrypt_knock(data):
    """按上游算法解开 ``Knock1`` 的二进制密码。

    算法先把整段按小端 DWORD 逐个异或 ``0x50434C45``，再整段异或
    ``0x454C4350``，最后从首字节给出的偏移处按 UTF-16LE 读字符串。

    Args:
        data: 注册表 ``Knock1`` 的原始字节。

    Returns:
        解密后的密码文本，最长 32 个字符。

    Raises:
        ValueError: 数据过短，或首字节偏移之后没有可读内容。
    """
    raw = bytes(data or b"")
    if len(raw) < 8:
        raise ValueError("Knock1 数据长度不足")
    buffer = bytearray(raw)
    count = len(buffer) // 4
    for index in range(count):
        offset = index * 4
        value = int.from_bytes(buffer[offset : offset + 4], "little")
        buffer[offset : offset + 4] = (value ^ KNOCK_XOR_FIRST).to_bytes(4, "little")
    for index in range(count):
        offset = index * 4
        value = int.from_bytes(buffer[offset : offset + 4], "little")
        buffer[offset : offset + 4] = (value ^ KNOCK_XOR_SECOND).to_bytes(4, "little")
    start = buffer[0]
    payload = bytes(buffer[start:])
    if len(payload) < 2:
        raise ValueError("Knock1 偏移超出数据范围")
    text = payload.decode("utf-16-le", "ignore").split("\x00", 1)[0]
    return text[:KNOCK_MAX_LENGTH]


def _read_value(paths, name):
    """按顺序在 HKLM 下找第一个能读到的值，返回其原始内容。"""
    import winreg

    last_error = None
    for path in paths:
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | view
                ) as key:
                    return winreg.QueryValueEx(key, name)[0]
            except OSError as error:
                last_error = error
    if last_error is not None:
        raise last_error
    raise OSError("注册表中没有找到对应项")


def _read_plain_password():
    """读明文密码；新版返回 ``None`` 表示需要解 ``Knock1``。"""
    value = _read_value(PASSWORD_KEY_PATHS, PASSWORD_VALUE_NAME)
    if value == PASSWORD_KNOCK_SENTINEL:
        return None
    # 上游用 substr(6) 去掉值前面的固定前缀。
    return str(value)[PASSWORD_PLAIN_PREFIX_LENGTH:]


def read_password():
    """读取极域解锁/卸载密码。

    Returns:
        dict: ``password`` 密码文本，``source`` 取值 ``plain`` 或 ``knock``，
        ``error`` 为失败原因（成功时为空串）。
    """
    if sys.platform != "win32":
        return {"password": "", "source": "", "error": "课堂助手只支持 Windows"}
    try:
        plain = _read_plain_password()
    except OSError:
        plain = None
    if plain:
        return {"password": plain, "source": "plain", "error": ""}
    try:
        knock = _read_value(KNOCK_KEY_PATHS, KNOCK_VALUE_NAME)
        password = decrypt_knock(knock)
    except (OSError, ValueError) as error:
        return {"password": "", "source": "", "error": "读取失败：%s" % error}
    if not password:
        return {"password": "", "source": "knock", "error": "注册表中的密码为空"}
    return {"password": password, "source": "knock", "error": ""}
