"""发送功能的数据类型。"""

from dataclasses import dataclass
from threading import Event
from typing import Optional


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
