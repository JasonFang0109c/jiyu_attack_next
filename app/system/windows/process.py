"""Windows 进程与端口命令输出解析。"""

import csv


def process_rows(text):
    """把 ``tasklist /FO CSV`` 的输出解析成 ``(映像名, 进程号)``。

    字段不足或进程号不是数字的行会被跳过，两者都保持原始字符串。

    Args:
        text: 命令的标准输出。

    Returns:
        list[tuple[str, str]]: 映像名与进程号。
    """
    rows = []
    for row in csv.reader(text.splitlines()):
        if len(row) >= 2 and row[1].isdigit():
            rows.append((row[0], row[1]))
    return rows


def netstat_rows(text, protocol="UDP"):
    """把 ``netstat -ano -p`` 的输出解析成 ``(本地地址, 进程号)``。

    Args:
        text: 命令的标准输出。
        protocol: 只取该协议的行，例如 ``UDP`` 或 ``TCP``。

    Returns:
        list[tuple[str, str]]: 本地地址与进程号。
    """
    rows = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0] == protocol:
            rows.append((fields[1], fields[-1]))
    return rows
