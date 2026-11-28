"""课堂防护 DLL 的注入、卸载与策略下发。

DLL 源码在 ``NeoJiYuTrainerHooks``，做五类进程内拦截：屏幕监视、输入控制、
关闭窗口、结束进程与远程命令审批。Python 侧只负责创建策略共享内存、把对应
位数的 DLL 注入学生端并调用导出函数；不安装驱动，也不改动系统全局配置。
"""

import contextlib
import ctypes
import struct
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

PROCESS_CREATE_THREAD = 0x0002
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04
FILE_MAP_WRITE = 0x0002
WAIT_TIMEOUT = 0x00000102
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

POLICY_MAGIC = 0x3150474A
POLICY_VERSION = 1
POLICY_SIZE = 16

GUARD_ANTI_MONITOR = 1 << 0
GUARD_ANTI_CONTROL = 1 << 1
GUARD_BLOCK_CLOSE = 1 << 2
GUARD_BLOCK_TERMINATE = 1 << 3
GUARD_BLOCK_REMOTE = 1 << 4
GUARD_ALL = (
    GUARD_ANTI_MONITOR
    | GUARD_ANTI_CONTROL
    | GUARD_BLOCK_CLOSE
    | GUARD_BLOCK_TERMINATE
    | GUARD_BLOCK_REMOTE
)

REMOTE_MAGIC = 0x3152474A
REMOTE_VERSION = 1
REMOTE_SLOTS = 32
REMOTE_COMMAND_CHARS = 1024
REMOTE_PENDING = 1
REMOTE_ALLOW = 2
REMOTE_DENY = 3
FILE_MAP_ALL_ACCESS = 0x000F001F

_KERNEL32 = None


def _kernel32():
    """延迟加载 kernel32，避免在非 Windows 平台导入时失败。"""
    global _KERNEL32
    if _KERNEL32 is not None:
        return _KERNEL32
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # 64 位句柄必须显式声明返回类型，否则 ctypes 默认按 int 截断。
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CreateRemoteThread.restype = wintypes.HANDLE
    kernel32.CreateRemoteThread.argtypes = (
        wintypes.HANDLE,
        wintypes.LPVOID,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.LPVOID,
    )
    kernel32.VirtualAllocEx.restype = ctypes.c_void_p
    kernel32.VirtualAllocEx.argtypes = (
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_size_t,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    kernel32.VirtualFreeEx.argtypes = (
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_size_t,
        wintypes.DWORD,
    )
    kernel32.WriteProcessMemory.argtypes = (
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    )
    kernel32.GetExitCodeThread.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.UnmapViewOfFile.argtypes = (ctypes.c_void_p,)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    _KERNEL32 = kernel32
    return _KERNEL32


def supported():
    """当前平台是否支持课堂防护。"""
    return sys.platform == "win32"


def policy_name(pid):
    """按目标进程号生成策略共享内存名。"""
    return "Local\\JiyuGuardPolicy_%d" % int(pid)


def pack_policy(flags):
    """把策略位打包成 DLL 读取的 16 字节结构。"""
    return struct.pack("<IIII", POLICY_MAGIC, POLICY_VERSION, int(flags), 0)


def unpack_policy(data):
    """解析策略结构；长度或魔数不符时抛 ``ValueError``。"""
    if len(data) < POLICY_SIZE:
        raise ValueError("策略数据长度不足")
    magic, version, flags, _reserved = struct.unpack("<IIII", data[:POLICY_SIZE])
    if magic != POLICY_MAGIC or version != POLICY_VERSION:
        raise ValueError("策略数据标识无效")
    return flags


class PolicyChannel:
    """保持命名共享内存存活，DLL 每次 Refresh 时重新读取。"""

    def __init__(self, pid):
        if not supported():
            raise RuntimeError("课堂防护只支持 Windows")
        self.name = policy_name(pid)
        kernel32 = _kernel32()
        kernel32.CreateFileMappingW.restype = wintypes.HANDLE
        kernel32.CreateFileMappingW.argtypes = (
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPCWSTR,
        )
        self.handle = kernel32.CreateFileMappingW(
            INVALID_HANDLE_VALUE, None, PAGE_READWRITE, 0, POLICY_SIZE, self.name
        )
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        kernel32.MapViewOfFile.restype = wintypes.LPVOID
        kernel32.MapViewOfFile.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_size_t,
        )
        self.view = kernel32.MapViewOfFile(
            self.handle, FILE_MAP_WRITE, 0, 0, POLICY_SIZE
        )
        if not self.view:
            error = ctypes.get_last_error()
            kernel32.CloseHandle(self.handle)
            raise ctypes.WinError(error)

    def update(self, flags):
        """写入新的策略位。"""
        ctypes.memmove(self.view, pack_policy(flags), POLICY_SIZE)

    def close(self):
        """释放视图与句柄；重复调用无副作用。"""
        kernel32 = _kernel32()
        if getattr(self, "view", None):
            kernel32.UnmapViewOfFile(self.view)
            self.view = None
        if getattr(self, "handle", None):
            kernel32.CloseHandle(self.handle)
            self.handle = None


class _RemoteHeader(ctypes.Structure):
    """DLL 与桌面端共享的远程命令区头。"""

    _fields_ = [
        ("magic", wintypes.DWORD),
        ("version", wintypes.DWORD),
        ("slots", wintypes.DWORD),
        ("reserved", wintypes.DWORD),
    ]


class _RemoteEntry(ctypes.Structure):
    """单个远程命令槽位；``state`` 为 0/1/2/3 四态。"""

    _fields_ = [
        ("state", wintypes.LONG),
        ("process_id", wintypes.DWORD),
        ("command_length", wintypes.DWORD),
        ("command", wintypes.WCHAR * REMOTE_COMMAND_CHARS),
        ("reserved", wintypes.DWORD),
    ]


REMOTE_HEADER_SIZE = ctypes.sizeof(_RemoteHeader)
REMOTE_ENTRY_SIZE = ctypes.sizeof(_RemoteEntry)
REMOTE_SIZE = REMOTE_HEADER_SIZE + REMOTE_ENTRY_SIZE * REMOTE_SLOTS


@dataclass(frozen=True)
class RemoteCommandRequest:
    """一次待确认的远程命令。"""

    index: int
    process_id: int
    command: str


class RemoteCommandChannel:
    """远程命令共享内存：轮询待确认命令并写回允许/拒绝。"""

    def __init__(self, pid):
        if not supported():
            raise RuntimeError("远程命令监控只支持 Windows")
        self.name = "Local\\JiyuGuardRemote_%d" % int(pid)
        kernel32 = _kernel32()
        kernel32.CreateFileMappingW.restype = wintypes.HANDLE
        kernel32.CreateFileMappingW.argtypes = (
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPCWSTR,
        )
        self.handle = kernel32.CreateFileMappingW(
            INVALID_HANDLE_VALUE, None, PAGE_READWRITE, 0, REMOTE_SIZE, self.name
        )
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        kernel32.MapViewOfFile.restype = wintypes.LPVOID
        kernel32.MapViewOfFile.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_size_t,
        )
        self.view = kernel32.MapViewOfFile(
            self.handle, FILE_MAP_ALL_ACCESS, 0, 0, REMOTE_SIZE
        )
        if not self.view:
            error = ctypes.get_last_error()
            kernel32.CloseHandle(self.handle)
            raise ctypes.WinError(error)
        header = ctypes.cast(self.view, ctypes.POINTER(_RemoteHeader)).contents
        header.magic = REMOTE_MAGIC
        header.version = REMOTE_VERSION
        header.slots = REMOTE_SLOTS
        header.reserved = 0
        self._entries = ctypes.cast(
            self.view + REMOTE_HEADER_SIZE, ctypes.POINTER(_RemoteEntry)
        )

    def poll(self):
        """返回当前所有待确认命令，不修改槽位状态。"""
        requests = []
        for index in range(REMOTE_SLOTS):
            entry = self._entries[index]
            if entry.state != REMOTE_PENDING:
                continue
            length = min(int(entry.command_length), REMOTE_COMMAND_CHARS)
            if length <= 0:
                continue
            command = "".join(entry.command[:length]).rstrip("\0")
            if command:
                requests.append(
                    RemoteCommandRequest(index, int(entry.process_id), command)
                )
        return requests

    def resolve(self, index, allow):
        """写回单个槽位的决定；只处理仍处于待确认状态的槽位。"""
        if not 0 <= int(index) < REMOTE_SLOTS:
            raise ValueError("远程命令槽位越界")
        entry = self._entries[int(index)]
        if entry.state == REMOTE_PENDING:
            entry.state = REMOTE_ALLOW if allow else REMOTE_DENY
            return True
        return False

    def deny_all(self):
        """拒绝所有仍在等待的命令，用于停止防护或退出。"""
        for index in range(REMOTE_SLOTS):
            if self._entries[index].state == REMOTE_PENDING:
                self._entries[index].state = REMOTE_DENY

    def close(self):
        """释放视图与句柄；重复调用无副作用。"""
        kernel32 = _kernel32()
        if getattr(self, "view", None):
            kernel32.UnmapViewOfFile(self.view)
            self.view = None
        if getattr(self, "handle", None):
            kernel32.CloseHandle(self.handle)
            self.handle = None


class _ModuleEntry32W(ctypes.Structure):
    """``MODULEENTRY32W``：只需模块名与基址。"""

    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.c_void_p),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.WCHAR * 256),
        ("szExePath", wintypes.WCHAR * 260),
    ]


def _module_base(pid, name):
    """从目标进程模块快照里取指定 DLL 的加载基址。"""
    kernel32 = _kernel32()
    kernel32.UnmapViewOfFile.argtypes = (ctypes.c_void_p,)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(
        TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, int(pid)
    )
    if snapshot == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = _ModuleEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        kernel32.Module32FirstW.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(_ModuleEntry32W),
        )
        if not kernel32.Module32FirstW(snapshot, ctypes.byref(entry)):
            raise ctypes.WinError(ctypes.get_last_error())
        wanted = name.lower()
        while True:
            if entry.szModule.lower() == wanted:
                return int(entry.modBaseAddr or 0)
            if not kernel32.Module32NextW(snapshot, ctypes.byref(entry)):
                break
        raise RuntimeError("目标进程未加载 %s" % name)
    finally:
        kernel32.CloseHandle(snapshot)


def is_32bit(pid):
    """返回目标进程是否为 32 位（WOW64）进程。"""
    return _is_wow64(pid)


def _is_wow64(pid):
    """目标进程是否运行在 WOW64（32 位）下。"""
    kernel32 = _kernel32()
    process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not process:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        flag = wintypes.BOOL()
        if not kernel32.IsWow64Process(process, ctypes.byref(flag)):
            raise ctypes.WinError(ctypes.get_last_error())
        return bool(flag.value)
    finally:
        kernel32.CloseHandle(process)


def _u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def export_rva(data, name):
    """从 PE 文件字节里查导出函数 RVA，供跨进程调用使用。"""
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("不是有效的 PE 文件")
    pe_offset = _u32(data, 0x3C)
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError("PE 签名无效")
    coff = pe_offset + 4
    sections = _u16(data, coff + 2)
    optional_size = _u16(data, coff + 16)
    optional = coff + 20
    magic = _u16(data, optional)
    directory = optional + (96 if magic == 0x10B else 112)
    export_address = _u32(data, directory)
    if not export_address:
        raise ValueError("PE 没有导出表")
    section_table = optional + optional_size

    def to_offset(rva):
        for index in range(sections):
            base = section_table + index * 40
            virtual_address = _u32(data, base + 12)
            virtual_size = _u32(data, base + 8)
            raw_pointer = _u32(data, base + 20)
            if virtual_address <= rva < virtual_address + max(virtual_size, 1):
                return raw_pointer + (rva - virtual_address)
        raise ValueError("RVA 不在任何节内")

    export = to_offset(export_address)
    name_count = _u32(data, export + 24)
    names = to_offset(_u32(data, export + 32))
    ordinals = to_offset(_u32(data, export + 36))
    functions = to_offset(_u32(data, export + 28))
    for index in range(name_count):
        name_offset = to_offset(_u32(data, names + index * 4))
        end = data.index(b"\0", name_offset)
        if data[name_offset:end].decode("ascii") == name:
            ordinal = _u16(data, ordinals + index * 2)
            return _u32(data, functions + ordinal * 4)
    raise ValueError("PE 中找不到导出函数 %s" % name)


def _kernel32_export_address(pid, name):
    """取目标进程中 kernel32 指定导出的绝对地址，兼容 32/64 位。"""
    base = _module_base(pid, "kernel32.dll")
    folder = "SysWOW64" if _is_wow64(pid) else "System32"
    path = Path("C:/Windows") / folder / "kernel32.dll"
    return base + export_rva(path.read_bytes(), name)


class RemoteProcess:
    """最小化的远程进程句柄包装，便于测试替换。"""

    def __init__(self, pid):
        self.pid = int(pid)
        self.handle = _kernel32().OpenProcess(
            PROCESS_CREATE_THREAD
            | PROCESS_VM_OPERATION
            | PROCESS_VM_WRITE
            | PROCESS_VM_READ
            | PROCESS_QUERY_INFORMATION,
            False,
            self.pid,
        )
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        """关闭进程句柄。"""
        if getattr(self, "handle", None):
            _kernel32().CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def _thread(self, address, parameter):
        kernel32 = _kernel32()
        kernel32.CreateRemoteThread.restype = wintypes.HANDLE
        thread = kernel32.CreateRemoteThread(
            self.handle, None, 0, ctypes.c_void_p(address), parameter, 0, None
        )
        if not thread:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if kernel32.WaitForSingleObject(thread, 15000) == WAIT_TIMEOUT:
                raise RuntimeError("远程线程执行超时")
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeThread(thread, ctypes.byref(code)):
                raise ctypes.WinError(ctypes.get_last_error())
            return code.value
        finally:
            kernel32.CloseHandle(thread)

    def load_library(self, dll_path):
        """在目标进程加载 DLL，返回模块句柄。"""
        path = str(Path(dll_path).resolve()).encode("utf-16-le") + b"\0"
        kernel32 = _kernel32()
        kernel32.VirtualAllocEx.restype = ctypes.c_void_p
        address = kernel32.VirtualAllocEx(
            self.handle, None, len(path), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
        )
        if not address:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            written = ctypes.c_size_t()
            if not kernel32.WriteProcessMemory(
                self.handle, address, path, len(path), ctypes.byref(written)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            load_address = _kernel32_export_address(self.pid, "LoadLibraryW")
            if not self._thread(load_address, address):
                raise RuntimeError("目标进程 LoadLibraryW 返回空")
            # 线程退出码只有 32 位，不能承载 x64 模块基址，改查模块快照。
            return _module_base(self.pid, Path(dll_path).name)
        finally:
            kernel32.VirtualFreeEx(self.handle, address, 0, MEM_RELEASE)

    def call_export(self, module, dll_path, name):
        """按模块基址 + 导出 RVA 调用 DLL 导出函数。"""
        rva = export_rva(Path(dll_path).read_bytes(), name)
        return self._thread(module + rva, None)

    def free_library(self, module):
        """在目标进程卸载模块。"""
        address = _kernel32_export_address(self.pid, "FreeLibrary")
        return bool(self._thread(address, module))


class GuardSession:
    """一次课堂防护注入的生命周期：策略共享内存 + DLL 加载/卸载。"""

    def __init__(self, pid, dll_path):
        self.pid = int(pid)
        self.dll_path = str(dll_path)
        self.channel = None
        self.remote = None
        self.process = None
        self.module = 0

    def start(self, flags):
        """创建策略、注入 DLL 并安装钩子；任一步失败都回滚。"""
        self.channel = PolicyChannel(self.pid)
        try:
            self.channel.update(flags)
            if int(flags) & GUARD_BLOCK_REMOTE:
                self.remote = RemoteCommandChannel(self.pid)
            self.process = RemoteProcess(self.pid)
            self.module = self.process.load_library(self.dll_path)
            result = self.process.call_export(
                self.module, self.dll_path, "JiyuGuardInstall"
            )
            if not result:
                raise RuntimeError("课堂防护 DLL 安装钩子失败")
        except Exception:
            self.stop()
            raise
        return self

    def update(self, flags):
        """更新策略位并让 DLL 立即重读。"""
        if self.channel is None or not self.module:
            raise RuntimeError("课堂防护尚未启用")
        if int(flags) & GUARD_BLOCK_REMOTE and self.remote is None:
            self.remote = RemoteCommandChannel(self.pid)
        self.channel.update(flags)
        self.process.call_export(self.module, self.dll_path, "JiyuGuardRefresh")

    def poll_remote(self):
        """返回待确认的远程命令列表。"""
        if self.remote is None:
            return []
        return self.remote.poll()

    def resolve_remote(self, index, allow):
        """写回一条远程命令的允许/拒绝决定。"""
        if self.remote is None:
            return False
        return self.remote.resolve(index, allow)

    def deny_remote_all(self):
        """拒绝所有仍在等待的命令。"""
        if self.remote is not None:
            self.remote.deny_all()

    def stop(self):
        """卸载钩子、释放 DLL 与共享内存；可重复调用。"""
        if self.remote is not None:
            with contextlib.suppress(Exception):
                self.remote.deny_all()
        if self.process is not None and self.module:
            with contextlib.suppress(Exception):
                self.process.call_export(
                    self.module, self.dll_path, "JiyuGuardUninstall"
                )
                self.process.free_library(self.module)
            self.module = 0
        if self.process is not None:
            self.process.close()
            self.process = None
        if self.remote is not None:
            self.remote.close()
            self.remote = None
        if self.channel is not None:
            self.channel.close()
            self.channel = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.stop()
