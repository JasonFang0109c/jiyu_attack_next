"""Windows 端口到进程的映射，走 ``iphlpapi`` 而不解析 ``netstat`` 文本。

学生端页面需要按秒轮询“谁在占用 4705”，拉起 ``netstat`` 子进程既慢又
要逐行解析；``GetExtendedUdpTable`` / ``GetExtendedTcpTable`` 一次调用就能
拿到全部表项，进程号与端口都是结构体字段。
"""

import contextlib
import ctypes
import sys
from ctypes import wintypes

AF_INET = 2
UDP_TABLE_OWNER_PID = 1
TCP_TABLE_OWNER_PID_ALL = 5
_NO_ERROR = 0

_IPHLPAPI = None


class _MibUdpRowOwnerPid(ctypes.Structure):
    _fields_ = [
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class _MibTcpRowOwnerPid(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class _MibTcp6RowOwnerPid(ctypes.Structure):
    _fields_ = [
        ("ucLocalAddr", ctypes.c_ubyte * 16),
        ("dwLocalScopeId", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("ucRemoteAddr", ctypes.c_ubyte * 16),
        ("dwRemoteScopeId", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwState", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


# TCP 表里的状态码，只关心 LISTEN（2）。
TCP_STATE_LISTEN = 2
# iphlpapi 用 AF_INET 与 AF_INET6 分开返回 IPv4 与 IPv6 表。
AF_INET6 = 23


def _iphlpapi():
    """加载并缓存 iphlpapi 并声明签名。"""
    global _IPHLPAPI
    if _IPHLPAPI is not None:
        return _IPHLPAPI
    library = ctypes.WinDLL("iphlpapi", use_last_error=True)
    for name in ("GetExtendedUdpTable", "GetExtendedTcpTable"):
        function = getattr(library, name)
        function.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.BOOL,
            wintypes.ULONG,
            ctypes.c_int,
            wintypes.ULONG,
        ]
        function.restype = wintypes.DWORD
    _IPHLPAPI = library
    return library


def _read_rows(function_name, table_class, row_type, family=AF_INET):
    """读出整张表并按 ``row_type`` 解释，返回行结构体列表。

    Raises:
        OSError: 系统调用返回错误。
    """
    library = _iphlpapi()
    function = getattr(library, function_name)
    size = wintypes.DWORD(0)
    function(None, ctypes.byref(size), False, family, table_class, 0)
    if size.value == 0:
        return []
    buffer = ctypes.create_string_buffer(size.value)
    result = function(buffer, ctypes.byref(size), False, family, table_class, 0)
    if result != _NO_ERROR:
        raise OSError(result, "读取端口表失败")
    count = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value
    # 表格头部是一个 DWORD 记录行数，行紧跟其后；C 结构体按 4 字节对齐，
    # 这里直接按数组遍历不会错位。
    rows = ctypes.cast(
        ctypes.byref(buffer, ctypes.sizeof(wintypes.DWORD)),
        ctypes.POINTER(row_type),
    )
    return [rows[index] for index in range(count)]


def _port_of(row):
    """把结构体里的网络字节序端口还原成端口号。"""
    return ((row.dwLocalPort & 0xFF) << 8) | ((row.dwLocalPort >> 8) & 0xFF)


def udp_endpoints():
    """返回本机全部 UDP 端点。

    Returns:
        list[tuple[int, int]]: ``(本地端口, 进程号)``。

    Raises:
        OSError: 非 Windows 平台或系统调用失败。
    """
    if sys.platform != "win32":
        raise OSError("此功能仅支持 Windows")
    return [
        (_port_of(row), int(row.dwOwningPid))
        for row in _read_rows(
            "GetExtendedUdpTable", UDP_TABLE_OWNER_PID, _MibUdpRowOwnerPid
        )
    ]


def tcp_listen_endpoints():
    """返回本机处于监听状态的 TCP 端点，格式同 :func:`udp_endpoints`。

    只保留 ``LISTEN`` 状态：已建立的连接用的是临时端口，放进“占用端口”
    一列只会让页面变吵，真正需要关注的是学生端主动监听的那个。IPv4 与
    IPv6 两张表都要读，极域会同时监听两者。

    Returns:
        list[tuple[int, int]]: ``(本地端口, 进程号)``。

    Raises:
        OSError: 非 Windows 平台或系统调用失败。
    """
    if sys.platform != "win32":
        raise OSError("此功能仅支持 Windows")
    entries = [
        (_port_of(row), int(row.dwOwningPid))
        for row in _read_rows(
            "GetExtendedTcpTable", TCP_TABLE_OWNER_PID_ALL, _MibTcpRowOwnerPid
        )
        if int(row.dwState) == TCP_STATE_LISTEN
    ]
    # IPv6 表失败不该影响 IPv4 的结果，学生端的 IPv4 监听才是关键。
    with contextlib.suppress(OSError):
        entries.extend(
            (_port_of(row), int(row.dwOwningPid))
            for row in _read_rows(
                "GetExtendedTcpTable",
                TCP_TABLE_OWNER_PID_ALL,
                _MibTcp6RowOwnerPid,
                AF_INET6,
            )
            if int(row.dwState) == TCP_STATE_LISTEN
        )
    return entries


def listening_ports(pids):
    """按进程号收集它们监听的 UDP 与 TCP 端口。

    Args:
        pids: 进程号集合。

    Returns:
        dict[int, set[int]]: 进程号到端口集合；读取失败的协议跳过。
    """
    wanted = {int(pid) for pid in pids}
    ports = {}
    for reader in (udp_endpoints, tcp_listen_endpoints):
        try:
            entries = reader()
        except OSError:
            continue
        for port, pid in entries:
            if pid in wanted:
                ports.setdefault(pid, set()).add(port)
    return ports
