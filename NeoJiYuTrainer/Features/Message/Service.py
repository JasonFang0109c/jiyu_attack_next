"""消息输入读取。"""

import sys


def read_message(arguments):
    """读取消息文本：优先使用 `--msg`，其次读取 `--msg-file`（`-` 表示标准输入）。"""
    if arguments.msg_file is None:
        return arguments.msg
    if arguments.msg_file == "-":
        return sys.stdin.read()
    with open(arguments.msg_file, encoding="utf-8-sig", newline="") as message_file:
        return message_file.read()
