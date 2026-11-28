"""兼容层后端协议，仅依赖 Python 标准库。"""

from typing import Protocol, Sequence, runtime_checkable

from .models import GuardPolicy, OperationResult, StudentSnapshot, Target


@runtime_checkable
class UdpTransport(Protocol):
    """发送 UDP 报文的传输后端。"""

    def send(self, packets: Sequence[bytes], target: Target) -> OperationResult:
        """向目标发送一组报文并返回操作结果。"""
        ...


@runtime_checkable
class StudentController(Protocol):
    """查询或控制学生端进程的后端。"""

    def snapshot(self, exe_path: str | None = None) -> StudentSnapshot:
        """读取学生端进程快照。"""
        ...

    def terminate(self, pid: int) -> OperationResult:
        """结束指定学生端进程。"""
        ...


@runtime_checkable
class WindowController(Protocol):
    """控制指定进程窗口的后端。"""

    def close_process_windows(self, pid: int) -> int:
        """请求关闭指定进程拥有的窗口并返回处理数量。"""
        ...


@runtime_checkable
class GuardBackend(Protocol):
    """应用或移除课堂防护的后端。"""

    def start(self, pid: int, policy: GuardPolicy) -> object:
        """为指定进程启动防护并返回会话句柄。"""
        ...

    def stop(self, session: object) -> OperationResult:
        """停止指定防护会话。"""
        ...


@runtime_checkable
class DriverBackend(Protocol):
    """管理内核驱动的后端。"""

    def remove(self) -> OperationResult:
        """移除驱动并返回操作结果。"""
        ...


@runtime_checkable
class UninstallBackend(Protocol):
    """执行应用卸载的后端。"""

    def run(
        self, keep_user_data: bool = False, remove_driver: bool = True
    ) -> OperationResult:
        """执行卸载并返回操作结果。"""
        ...
