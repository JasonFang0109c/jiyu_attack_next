"""用系统 ICMP 接口探测目标主机是否在线。"""

from concurrent.futures import ThreadPoolExecutor
import ctypes
from ctypes import wintypes
import ipaddress
import struct
import sys

# 回显载荷只用于确认往返，内容本身没有含义。
_ECHO_PAYLOAD = b"jiyu-attack-next"
# 局域网内的回显通常几十毫秒返回，超过这个时间视为没有响应。
_ECHO_TIMEOUT_MS = 400
# 同时探测的主机数量，兼顾 /24 网段的速度与系统句柄开销。
_ECHO_WORKERS = 32
_IP_SUCCESS = 0
_INVALID_HANDLE = ctypes.c_void_p(-1).value
# MIB_IPNETROW 的字段：接口索引、物理地址长度、物理地址、地址、类型。
_ARP_ROW_SIZE = 24
_ERROR_INSUFFICIENT_BUFFER = 122


class _IpOptionInformation(ctypes.Structure):
    """IP 选项头，IcmpSendEcho 要求传入可选的 IP_OPTION_INFORMATION。"""

    _fields_ = [
        ("Ttl", ctypes.c_ubyte),
        ("Tos", ctypes.c_ubyte),
        ("Flags", ctypes.c_ubyte),
        ("OptionsSize", ctypes.c_ubyte),
        ("OptionsData", ctypes.c_void_p),
    ]


class _IcmpEchoReply(ctypes.Structure):
    """IcmpSendEcho 的回复结构，Status 为 0 表示收到正常回显。"""

    _fields_ = [
        ("Address", wintypes.ULONG),
        ("Status", wintypes.ULONG),
        ("RoundTripTime", wintypes.ULONG),
        ("DataSize", wintypes.USHORT),
        ("Reserved", wintypes.USHORT),
        ("Data", ctypes.c_void_p),
        ("Options", _IpOptionInformation),
    ]


def _load_icmp_api():
    """加载 iphlpapi 并声明签名；非 Windows 或加载失败时返回 None。"""
    if sys.platform != "win32":
        return None
    try:
        api = ctypes.WinDLL("iphlpapi.dll")
    except OSError:
        return None
    api.IcmpCreateFile.restype = wintypes.HANDLE
    api.IcmpCloseHandle.argtypes = [wintypes.HANDLE]
    api.IcmpSendEcho.restype = wintypes.ULONG
    api.GetIpNetTable.restype = wintypes.ULONG
    api.GetIpNetTable.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.ULONG),
        wintypes.BOOL,
    ]
    api.IcmpSendEcho.argtypes = [
        wintypes.HANDLE,
        wintypes.ULONG,
        ctypes.c_void_p,
        wintypes.WORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    return api


def _echo_once(api, address, timeout_ms):
    """向单个地址发一次回显请求，收到成功回复时返回 True。"""
    handle = api.IcmpCreateFile()
    if not handle or handle == _INVALID_HANDLE:
        return False
    try:
        payload = ctypes.create_string_buffer(_ECHO_PAYLOAD, len(_ECHO_PAYLOAD))
        # 回复缓冲区要容纳 ICMP_ECHO_REPLY 结构、回显头与载荷。
        reply = ctypes.create_string_buffer(ctypes.sizeof(_IcmpEchoReply) + 128)
        count = api.IcmpSendEcho(
            handle,
            address,
            ctypes.byref(payload),
            len(_ECHO_PAYLOAD),
            None,
            ctypes.byref(reply),
            ctypes.sizeof(reply),
            timeout_ms,
        )
        if not count:
            return False
        result = ctypes.cast(reply, ctypes.POINTER(_IcmpEchoReply)).contents
        return result.Status == _IP_SUCCESS
    finally:
        api.IcmpCloseHandle(handle)


def _arp_addresses():
    """读取 ARP 缓存里已解析的地址。

    同网段主机即使屏蔽了 ICMP 也会响应 ARP 并留在缓存里，用它把“在线但不回
    回显”的主机区分出来，避免把正常的机器判成失败。

    Returns:
        set: 已解析地址的网络序整数集合。
    """
    api = _load_icmp_api()
    if api is None:
        return set()
    size = wintypes.ULONG(0)
    if api.GetIpNetTable(None, ctypes.byref(size), True) != _ERROR_INSUFFICIENT_BUFFER:
        return set()
    if not size.value:
        return set()
    buffer = ctypes.create_string_buffer(size.value)
    if api.GetIpNetTable(buffer, ctypes.byref(size), True) != 0:
        return set()
    raw = buffer.raw
    count = struct.unpack_from("<I", raw, 0)[0]
    addresses = set()
    for index in range(count):
        offset = 4 + index * _ARP_ROW_SIZE
        if offset + _ARP_ROW_SIZE > len(raw):
            break
        _interface, length, _physical, address, kind = struct.unpack_from(
            "<II8sII", raw, offset
        )
        # 长度为 0 或类型为无效项时没有可用的物理地址。
        if length and kind != 2:
            addresses.add(address)
    return addresses


def ping_hosts(hosts, timeout_ms=_ECHO_TIMEOUT_MS):
    """并发探测主机是否响应 ICMP 回显。

    只用来区分“主机在，只是没回 UDP 反馈”和“主机根本没有响应”两种情况：
    地址不存在时 ARP 解析失败不会产生任何 ICMP 报文，单靠发送侧无法发现。

    Args:
        hosts: 要探测的地址序列。
        timeout_ms: 单次回显的等待毫秒数。

    Returns:
        dict: 地址到是否响应的映射；无法探测时返回空字典。
    """
    api = _load_icmp_api()
    if api is None:
        return {}
    addresses = {}
    for host in hosts:
        try:
            # IPAddr 按网络字节序存放，转成整数时要按小端解释才能对上。
            addresses[host] = int.from_bytes(
                ipaddress.IPv4Address(host).packed, "little"
            )
        except ValueError:
            continue
    if not addresses:
        return {}
    workers = min(_ECHO_WORKERS, len(addresses))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(
            lambda item: _echo_once(api, item[1], timeout_ms), addresses.items()
        )
    alive = dict(zip(addresses, results))
    if not all(alive.values()):
        resolved = _arp_addresses()
        for host, address in addresses.items():
            if not alive[host] and address in resolved:
                alive[host] = True
    return alive
