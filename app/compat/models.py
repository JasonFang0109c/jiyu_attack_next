"""兼容层的可序列化数据模型。"""

from dataclasses import dataclass, field
from typing import Any

from .constants import STUDENT_PORT
from .flags import GUARD_ALL


@dataclass(frozen=True, slots=True)
class Target:
    """网络操作目标。

    Attributes:
        host: 去除首尾空白后必须非空的主机名或地址。
        port: 目标端口，范围为 1 到 65535。
    """

    host: str
    port: int

    def __post_init__(self) -> None:
        """校验主机名与端口。"""
        if not isinstance(self.host, str) or not self.host.strip():
            raise ValueError("host must be a non-empty string")
        object.__setattr__(self, "host", self.host.strip())
        if not isinstance(self.port, int) or isinstance(self.port, bool):
            raise ValueError("port must be an integer")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")


@dataclass(frozen=True, slots=True)
class GuardPolicy:
    """归一化后的课堂防护位集合。

    Attributes:
        flags: 仅保留 GUARD_ALL 范围内的位标记。
    """

    flags: int = 0

    def __post_init__(self) -> None:
        """屏蔽防护位集合中的未知标记。"""
        object.__setattr__(self, "flags", int(self.flags) & GUARD_ALL)

    def enabled(self, flag: int | None = None) -> bool:
        """返回整体防护或指定防护位是否启用。"""
        return bool(self.flags) if flag is None else self.has(flag)

    def has(self, flag: int) -> bool:
        """返回指定防护位是否全部包含在策略中。"""
        return bool(flag) and (self.flags & flag) == flag


@dataclass(frozen=True, slots=True)
class StudentSnapshot:
    """学生端进程与路径状态快照。

    Attributes:
        processes: 学生端进程记录的不可变序列。
        port: 学生端监听端口。
        owner: 占用端口的进程标识；没有占用者时为 0。
        executable_path: 当前学生端可执行文件路径。
        saved_path: 设置中保存的可执行文件路径。
    """

    processes: tuple[dict[str, Any], ...] = ()
    port: int = STUDENT_PORT
    owner: int = 0
    executable_path: str = ""
    saved_path: str = ""


@dataclass(frozen=True, slots=True)
class OperationResult:
    """后端操作的统一结果。

    Attributes:
        success: 操作是否成功。
        message: 面向调用方的摘要。
        code: 后端或操作返回码。
        forced: 是否使用强制方式完成。
        gone: 目标对象是否已消失。
        kernel: 是否涉及内核层操作。
        details: 可序列化的额外结果字段。
    """

    success: bool
    message: str = ""
    code: int | str | None = None
    forced: bool = False
    gone: bool = False
    kernel: bool = False
    details: dict[str, Any] = field(default_factory=dict)
