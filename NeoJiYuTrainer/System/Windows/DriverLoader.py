"""JiyuGuard 可选内核驱动的用户态接口。"""

from __future__ import annotations

import ctypes
import struct
import subprocess
import sys
import winreg
from dataclasses import dataclass
from pathlib import Path

from NeoJiYuTrainer.Shared.Resources import resource_path

DEVICE_PATH = r"\\.\JiyuGuard"
SERVICE_NAME = "JiyuGuardDriver"
FILE_DEVICE_UNKNOWN = 0x22
METHOD_BUFFERED = 0
FILE_ANY_ACCESS = 0
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ERROR_SERVICE_ALREADY_RUNNING = 1056
ERROR_SERVICE_DOES_NOT_EXIST = 1060
ERROR_SERVICE_MARKED_FOR_DELETE = 1072
SERVICE_KEY = rf"SYSTEM\CurrentControlSet\Services\{SERVICE_NAME}"


def ctl_code(function: int) -> int:
    """按 Windows CTL_CODE 规则生成控制码。"""
    return (
        (FILE_DEVICE_UNKNOWN << 16)
        | (FILE_ANY_ACCESS << 14)
        | (function << 2)
        | METHOD_BUFFERED
    )


IOCTL_PROTECT = ctl_code(0x800)
IOCTL_UNPROTECT = ctl_code(0x801)
IOCTL_KILL = ctl_code(0x802)
IOCTL_STATUS = ctl_code(0x803)
IOCTL_CLEAR = ctl_code(0x804)


def force_delete_service_key(service_name: str) -> None:
    """递归删除指定服务的注册表键（含子键与全部值）。"""
    path = rf"SYSTEM\CurrentControlSet\Services\{service_name}"

    def delete_tree(current: str) -> None:
        try:
            handle = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                current,
                0,
                winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY,
            )
        except FileNotFoundError:
            return
        with handle:
            while True:
                try:
                    child = winreg.EnumKey(handle, 0)
                except OSError:
                    break
                delete_tree(f"{current}\\{child}")
            while True:
                try:
                    name, _, _ = winreg.EnumValue(handle, 0)
                except OSError:
                    break
                winreg.DeleteValue(handle, name)
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, current)

    try:
        delete_tree(path)
    except OSError as error:
        raise OSError(f"清理驱动服务注册表失败：{error}") from error


@dataclass(frozen=True)
class DriverStatus:
    """驱动运行状态。"""

    version: int
    protected_count: int
    callback_active: bool


def default_driver_path() -> Path:
    """返回随程序分发的驱动文件路径。"""
    return resource_path("Native", "Driver", "JiYuGuardDriver.sys")


def available(sys_path: Path | None = None) -> bool:
    """判断当前平台与驱动文件是否可用。"""
    return sys.platform == "win32" and Path(sys_path or default_driver_path()).is_file()


class DriverSession:
    """安装、打开并控制 JiyuGuard 驱动。

    驱动是可选组件，只有用户显式启用时才安装；停止时可选择保留服务，
    便于下次快速启动。所有系统级操作都通过 sc.exe 完成，不写注册表。
    """

    def __init__(self, sys_path: Path | None = None) -> None:
        self.sys_path = Path(sys_path or default_driver_path())
        self.handle: int | None = None

    @staticmethod
    def _run_sc(*args: str) -> tuple[int, str]:
        completed = subprocess.run(
            ["sc.exe", *args],
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="replace",
            check=False,
        )
        return completed.returncode, (completed.stdout or "") + (completed.stderr or "")

    def service_state(self) -> str:
        """返回 stopped/running/absent 之一。"""
        code, output = self._run_sc("query", SERVICE_NAME)
        if code != 0:
            return "absent"
        if "RUNNING" in output.upper():
            return "running"
        return "stopped"

    @staticmethod
    def _force_delete_service_key() -> None:
        """递归删除服务注册表键，用于清理被标记删除的残留服务。"""
        force_delete_service_key(SERVICE_NAME)

    def _create_service(self) -> None:
        """创建内核服务；遇到「标记删除」残留时清理后重试一次。"""
        args = (
            "create",
            SERVICE_NAME,
            "binPath=",
            str(self.sys_path),
            "type=",
            "kernel",
            "start=",
            "demand",
        )
        code, output = self._run_sc(*args)
        if code == 0:
            return
        if str(ERROR_SERVICE_MARKED_FOR_DELETE) in output:
            self._force_delete_service_key()
            code, output = self._run_sc(*args)
            if code == 0:
                return
        if str(1073) in output:  # ERROR_SERVICE_EXISTS：沿用现有服务
            return
        raise OSError(f"创建驱动服务失败：{output.strip()}")

    def install(self) -> None:
        """创建并启动内核服务。"""
        if self.service_state() == "absent":
            self._create_service()
        code, output = self._run_sc("start", SERVICE_NAME)
        if code != 0 and str(ERROR_SERVICE_ALREADY_RUNNING) not in output:
            raise OSError(f"启动驱动服务失败：{output.strip()}")

    def uninstall(self) -> None:
        """停止并删除内核服务。"""
        self._run_sc("stop", SERVICE_NAME)
        code, output = self._run_sc("delete", SERVICE_NAME)
        if code != 0 and str(ERROR_SERVICE_DOES_NOT_EXIST) not in output:
            if str(ERROR_SERVICE_MARKED_FOR_DELETE) in output:
                self._force_delete_service_key()
                return
            raise OSError(f"删除驱动服务失败：{output.strip()}")
        self._force_delete_service_key()

    def _open(self) -> int:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        handle = kernel32.CreateFileW(
            DEVICE_PATH,
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(handle)

    def open(self) -> None:
        """打开设备句柄。"""
        if self.handle is None:
            self.handle = self._open()

    def close(self) -> None:
        """关闭设备句柄。"""
        if self.handle is not None:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle(ctypes.c_void_p(self.handle))
            self.handle = None

    def _ioctl(self, code: int, payload: bytes, out_size: int = 0) -> bytes:
        if self.handle is None:
            self.open()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.DeviceIoControl.restype = ctypes.c_int
        kernel32.DeviceIoControl.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_void_p,
        ]
        in_buffer = ctypes.create_string_buffer(payload, len(payload))
        out_buffer = ctypes.create_string_buffer(max(out_size, 1))
        returned = ctypes.c_uint32()
        ok = kernel32.DeviceIoControl(
            ctypes.c_void_p(self.handle),
            code,
            in_buffer,
            len(payload),
            out_buffer,
            out_size,
            ctypes.byref(returned),
            None,
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        return out_buffer.raw[: returned.value]

    def protect(self, pid: int) -> None:
        """保护指定进程，阻止其它进程结束它。"""
        self._ioctl(IOCTL_PROTECT, struct.pack("<I", int(pid)))

    def unprotect(self, pid: int) -> None:
        """移除进程保护。"""
        self._ioctl(IOCTL_UNPROTECT, struct.pack("<I", int(pid)))

    def kill(self, pid: int, exit_code: int = 1) -> None:
        """从内核直接结束指定进程。"""
        self._ioctl(IOCTL_KILL, struct.pack("<II", int(pid), int(exit_code)))

    def status(self) -> DriverStatus:
        """读取驱动状态。"""
        data = self._ioctl(IOCTL_STATUS, b"", 16)
        version, count, active, _reserved = struct.unpack("<IIII", data)
        return DriverStatus(version, count, bool(active))

    def clear(self) -> None:
        """清空全部受保护 PID。"""
        self._ioctl(IOCTL_CLEAR, b"")


def kernel_kill(pid: int, exit_code: int = 1) -> bool:
    """尝试通过已加载的 JiyuGuard 驱动结束进程。

    驱动是可选组件：没有安装或没有运行时这里只返回 False，不主动安装，
    从而保留“用户显式启用驱动”的边界。调用方先走用户态流程，失败后再调用
    本函数，形成与 JiYuTrainer 相同的“普通结束失败后内核强杀”链。

    Args:
        pid: 目标进程号。
        exit_code: 传给 ``ZwTerminateProcess`` 的退出码。

    Returns:
        bool: 驱动调用成功时为 True。
    """
    session = DriverSession()
    try:
        session.open()
        session.kill(int(pid), int(exit_code))
        return True
    except OSError:
        return False
    finally:
        session.close()
