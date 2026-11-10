"""网络发送结果与送达状态。"""

from dataclasses import dataclass
from enum import StrEnum


class DeliveryState(StrEnum):
    """单个目标的送达判定。

    只能判断报文有没有被网络拒绝。接收端是否执行了报文由对方决定，
    本工具拿不到回执，因此“已送达”表示没收到不可达反馈，而不是执行成功。
    """

    DELIVERED = "delivered"
    REJECTED = "rejected"
    UNREACHABLE = "unreachable"
    NO_RESPONSE = "no_response"

    @property
    def text(self):
        """返回界面与命令行展示用的中文说明。"""
        return {
            DeliveryState.DELIVERED: "已送达",
            DeliveryState.REJECTED: "失败：目标端口未响应",
            DeliveryState.UNREACHABLE: "失败：目标不可达",
            DeliveryState.NO_RESPONSE: "失败：目标未响应",
        }[self]


@dataclass(frozen=True)
class Delivery:
    """一个目标地址的发送结果。

    Attributes:
        host: 目标地址。
        sent: 发往该地址的报文数量。
        state: 送达判定。
        detail: 判定依据或异常文本。
    """

    host: str
    sent: int
    state: DeliveryState
    detail: str = ""

    @property
    def ok(self):
        """该目标是否没有发现异常。"""
        return self.state is DeliveryState.DELIVERED


@dataclass(frozen=True)
class SendOutcome:
    """一次发送的整体结果。

    Attributes:
        sent: 实际发出的报文总数。
        deliveries: 每个目标地址的送达判定，顺序与目标展开顺序一致。
    """

    sent: int
    deliveries: tuple

    @property
    def failed(self):
        """返回判定为失败的目标。"""
        return tuple(item for item in self.deliveries if not item.ok)
