"""Windows 进程枚举、路径读取与结束。

进程枚举与结束直接调用 ``kernel32``，不拉起 ``tasklist`` 或 PowerShell：
学生端页面会定时轮询，子进程开销会让界面每两秒卡一下，也拿不到可靠的
创建时间。创建时间用于识别进程号复用，避免结束一个恰好接管了旧进程号
的无关进程。
"""

import csv
import ctypes
import subprocess
import sys
from contextlib import suppress
from ctypes import wintypes
from pathlib import Path

from app.system.windows.command import run_windows_command

PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_QUERY = 0x0008
SE_PRIVILEGE_ENABLED = 0x0002
WAIT_TIMEOUT = 0x00000102
ERROR_INVALID_PARAMETER = 87
ERROR_ACCESS_DENIED = 5
ERROR_NOT_FOUND = 1168
WM_CLOSE = 0x0010

_KERNEL32 = None
_USER32 = None
_ADVAPI32 = None
_DEBUG_PRIVILEGE = None


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


def _require_windows():
    """非 Windows 平台直接拒绝，避免 ctypes 在导入时失败。"""
    if sys.platform != "win32":
        raise RuntimeError("此功能仅支持 Windows")


class _ProcessEntry(ctypes.Structure):
    """``PROCESSENTRY32W``，只需映像名与进程号两个字段。"""

    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def _kernel32():
    """加载并缓存 kernel32，顺便声明会用到的函数签名。"""
    global _KERNEL32
    if _KERNEL32 is not None:
        return _KERNEL32
    library = ctypes.WinDLL("kernel32", use_last_error=True)
    library.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    library.OpenProcess.restype = wintypes.HANDLE
    library.CloseHandle.argtypes = [wintypes.HANDLE]
    library.CloseHandle.restype = wintypes.BOOL
    library.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    library.TerminateProcess.restype = wintypes.BOOL
    library.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    library.WaitForSingleObject.restype = wintypes.DWORD
    library.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    library.GetProcessTimes.restype = wintypes.BOOL
    library.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    library.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    library.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
    library.Process32FirstW.restype = wintypes.BOOL
    library.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
    library.Process32NextW.restype = wintypes.BOOL
    library.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    library.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _KERNEL32 = library
    return library


class _Luid(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class _LuidAndAttributes(ctypes.Structure):
    _fields_ = [("Luid", _Luid), ("Attributes", wintypes.DWORD)]


class _TokenPrivileges(ctypes.Structure):
    _fields_ = [
        ("PrivilegeCount", wintypes.DWORD),
        ("Privileges", _LuidAndAttributes * 1),
    ]


def _advapi32():
    """加载并缓存 advapi32，用于打开自己的进程令牌。"""
    global _ADVAPI32
    if _ADVAPI32 is not None:
        return _ADVAPI32
    library = ctypes.WinDLL("advapi32", use_last_error=True)
    library.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    library.OpenProcessToken.restype = wintypes.BOOL
    library.LookupPrivilegeValueW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.POINTER(_Luid),
    ]
    library.LookupPrivilegeValueW.restype = wintypes.BOOL
    library.AdjustTokenPrivileges.argtypes = [
        wintypes.HANDLE,
        wintypes.BOOL,
        ctypes.POINTER(_TokenPrivileges),
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    library.AdjustTokenPrivileges.restype = wintypes.BOOL
    _ADVAPI32 = library
    return library


def enable_debug_privilege():
    """尽力打开当前进程的 ``SeDebugPrivilege``，失败时静默返回 False。

    管理员身份下它决定能否打开以 SYSTEM 运行的学生端；普通权限下调用
    不会报错，只是拿不到这项特权。

    Returns:
        bool: 特权已经生效时为 True。
    """
    global _DEBUG_PRIVILEGE
    if _DEBUG_PRIVILEGE is not None:
        return _DEBUG_PRIVILEGE
    _DEBUG_PRIVILEGE = False
    if sys.platform != "win32":
        return False
    kernel32 = _kernel32()
    advapi32 = _advapi32()
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(),
        TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
        ctypes.byref(token),
    ):
        return False
    try:
        privileges = _TokenPrivileges()
        privileges.PrivilegeCount = 1
        if not advapi32.LookupPrivilegeValueW(
            None, "SeDebugPrivilege", ctypes.byref(privileges.Privileges[0].Luid)
        ):
            return False
        privileges.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
        if not advapi32.AdjustTokenPrivileges(
            token, False, ctypes.byref(privileges), 0, None, None
        ):
            return False
        # 调用成功时也可能一个特权都没改，必须看错误码才算真的打开。
        _DEBUG_PRIVILEGE = ctypes.get_last_error() == 0
        return _DEBUG_PRIVILEGE
    finally:
        kernel32.CloseHandle(token)


def _open_process(pid, access):
    """按访问权限打开进程，失败返回 None，错误码留在 last_error。"""
    handle = _kernel32().OpenProcess(access, False, int(pid))
    return handle or None


def process_path(pid):
    """读取进程映像的完整路径，读不到时返回空字符串。

    以 SYSTEM 运行的进程在普通权限下可能被拒绝，调用方把空路径当成
    “路径未知”，不影响按映像名识别。

    Args:
        pid: 进程号。

    Returns:
        str: 可执行文件完整路径，失败时为空字符串。
    """
    _require_windows()
    kernel32 = _kernel32()
    handle = _open_process(pid, PROCESS_QUERY_LIMITED_INFORMATION)
    if handle is None:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            return ""
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def process_creation_time(pid):
    """读取进程创建时间（FILETIME 整数），用于识别进程号复用。

    Args:
        pid: 进程号。

    Returns:
        int | None: 创建时间；进程不存在或无权读取时为 None。
    """
    _require_windows()
    kernel32 = _kernel32()
    handle = _open_process(pid, PROCESS_QUERY_LIMITED_INFORMATION)
    if handle is None:
        return None
    try:
        times = (wintypes.FILETIME * 4)()
        pointers = [ctypes.byref(item) for item in times]
        if not kernel32.GetProcessTimes(handle, *pointers):
            return None
        creation = times[0]
        return (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
    finally:
        kernel32.CloseHandle(handle)


def is_process_alive(pid, creation=None):
    """判断进程是否仍在运行，可按创建时间排除进程号复用。

    以“句柄是否已发出退出信号”为准，而不是比较退出码取 259：进程退出后
    进程号可能立刻被别的程序占用，看句柄状态才不会认错。没有权限打开
    句柄时按“仍在运行”处理，让调用方有机会走管理员权限再确认。

    Args:
        pid: 进程号。
        creation: 之前记录的创建时间；给定时创建时间不同也算已退出。

    Returns:
        bool: 进程仍在运行时为 True。
    """
    if sys.platform != "win32":
        return False
    kernel32 = _kernel32()
    handle = _open_process(pid, SYNCHRONIZE)
    if handle is None:
        error = ctypes.get_last_error()
        # 87 与 1168 都表示进程号不存在；其余（典型是 5 拒绝访问）无法判断，
        # 当成还在运行，交给结束流程在提权后处理。
        return error not in (ERROR_INVALID_PARAMETER, ERROR_NOT_FOUND)
    try:
        if kernel32.WaitForSingleObject(handle, 0) != WAIT_TIMEOUT:
            return False
    finally:
        kernel32.CloseHandle(handle)
    if creation is None:
        return True
    current = process_creation_time(pid)
    if current is None:
        return True
    return int(current) == int(creation)


def close_main_windows(pid):
    """给进程的顶层窗口发送 WM_CLOSE，请它自己退出。

    极域学生端通常没有窗口，这一步往往什么都没做，但它比直接结束温和，
    对有界面的同名程序仍然有效。

    Args:
        pid: 进程号。

    Returns:
        int: 收到关闭消息的窗口数量。
    """
    global _USER32
    _require_windows()
    if _USER32 is None:
        library = ctypes.WinDLL("user32", use_last_error=True)
        library.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        library.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        _USER32 = library
    user32 = _USER32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    targets = []

    def collect(hwnd, _param):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == int(pid):
            targets.append(hwnd)
        return True

    user32.EnumWindows(callback_type(collect), 0)
    for hwnd in targets:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    return len(targets)


def terminate_process(pid, creation=None, timeout=2.5, taskkill=True):
    """结束进程并等待它真正消失。

    Args:
        pid: 进程号。
        creation: 之前记录的创建时间，不一致时放弃结束，防止误杀。
        timeout: 等待进程退出的秒数。
        taskkill: 直接调用系统接口失败时，是否再用 ``taskkill /F`` 兜底。
            原生调用更快也更准（能看到真实错误码），``taskkill`` 只在接口
            调用出现意外错误时兜底。

    Returns:
        dict: 含 ``pid``、``code``、``output``、``success``、``forced``
        与 ``gone``；``code`` 为 0 表示已结束，``5`` 表示拒绝访问。
    """
    _require_windows()
    kernel32 = _kernel32()
    if not is_process_alive(pid, creation):
        return {
            "pid": pid,
            "code": 0,
            "output": "进程已经退出",
            "success": True,
            "forced": False,
            "gone": True,
        }
    enable_debug_privilege()
    handle = _open_process(
        pid, PROCESS_TERMINATE | SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
    )
    if handle is None:
        error = ctypes.get_last_error()
        if error in (ERROR_INVALID_PARAMETER, ERROR_NOT_FOUND):
            return {
                "pid": pid,
                "code": 0,
                "output": "进程已经退出",
                "success": True,
                "forced": False,
                "gone": True,
            }
        if error == ERROR_ACCESS_DENIED:
            output = "拒绝访问，需要管理员权限"
        else:
            output = "无法打开进程（错误码 %d）" % error
            if taskkill:
                output = _taskkill(pid, output)
        return {
            "pid": pid,
            "code": error,
            "output": output,
            "success": False,
            "forced": True,
            "gone": False,
            "elevatable": error == ERROR_ACCESS_DENIED,
        }
    try:
        if not kernel32.TerminateProcess(handle, 1):
            error = ctypes.get_last_error()
            return {
                "pid": pid,
                "code": error,
                "output": "结束进程失败（错误码 %d）" % error,
                "success": False,
                "forced": True,
                "gone": False,
                "elevatable": error == ERROR_ACCESS_DENIED,
            }
        kernel32.WaitForSingleObject(handle, max(0, int(timeout * 1000)))
    finally:
        kernel32.CloseHandle(handle)
    gone = not is_process_alive(pid, creation)
    return {
        "pid": pid,
        "code": 0,
        "output": "已强制结束" if gone else "已请求结束，但进程仍在运行",
        "success": gone,
        "forced": True,
        "gone": gone,
        "elevatable": False,
    }


def _taskkill(pid, fallback):
    """用 ``taskkill /F`` 再试一次，返回可读的结果说明。

    只作为原生接口出意外错误时的兜底，正常路径不会走到这里。

    Args:
        pid: 进程号。
        fallback: 兜底也失败时返回的说明。

    Returns:
        str: 结束成功或失败的中文说明。
    """
    with suppress(OSError, RuntimeError, subprocess.SubprocessError):
        process = run_windows_command(["taskkill", "/PID", str(pid), "/F"])
        if process.returncode in (0, 128):
            return "已强制结束"
        text = (process.stderr or process.stdout).strip()
        if text:
            return text
    return fallback


def list_processes():
    """枚举本机全部进程及其映像路径。

    用 ``CreateToolhelp32Snapshot`` 而不是 ``EnumProcesses``：后者在
    ``kernel32`` 里并不导出，读取映像名也要先用快照拿到列表。

    Returns:
        list[dict]: 每项含 ``pid``、``name`` 与 ``path``，按进程号升序；
        读不到路径时 ``path`` 为空、``name`` 退回快照里的映像名。

    Raises:
        RuntimeError: 非 Windows 平台。
        OSError: 创建进程快照失败。
    """
    _require_windows()
    kernel32 = _kernel32()
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    invalid = ctypes.c_void_p(-1).value
    if not snapshot or int(snapshot) == invalid:
        raise ctypes.WinError(ctypes.get_last_error())
    rows = []
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                pid = int(entry.th32ProcessID)
                if pid > 0:
                    path = process_path(pid)
                    name = Path(path).name if path else entry.szExeFile
                    rows.append({"pid": pid, "name": name, "path": path})
                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)
    rows.sort(key=lambda item: item["pid"])
    return rows


def tasklist_names():
    """用 ``tasklist`` 补一次映像名，供读不到路径的进程识别。

    Returns:
        dict[int, str]: 进程号到映像名的映射，查询失败时为空字典。
    """
    if sys.platform != "win32":
        return {}
    with suppress(OSError, RuntimeError, ValueError):
        process = run_windows_command(["tasklist", "/FO", "CSV", "/NH"])
        if process.returncode:
            return {}
        return {int(pid): name for name, pid in process_rows(process.stdout)}
    return {}
