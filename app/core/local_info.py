"""本机 IP 与端口探测。"""

import csv
import ipaddress
import socket
import subprocess

from .firewall import run_windows_command
from .protocol import get_ip


def validate_listen_ip(value):
    """校验用户填写的发送端 IP，空值表示自动检测。

    Args:
        value: 用户输入，可以为 None。

    Returns:
        str | None: 规范化后的 IPv4 地址，空输入返回 None。

    Raises:
        ValueError: 地址格式无效。
    """
    if value is None or not str(value).strip():
        return None
    try:
        return str(ipaddress.IPv4Address(str(value).strip()))
    except ValueError as error:
        raise ValueError("发送端 IP 格式无效") from error


def _is_usable_local_address(value, target=None):
    try:
        address = ipaddress.IPv4Address(str(value).strip())
    except ValueError:
        return False
    if address.is_unspecified or address.is_loopback or address.is_link_local:
        return bool(target and ipaddress.IPv4Address(target).is_loopback)
    if address.is_multicast or address.is_reserved:
        return False
    # 198.18.0.0/15 是网络基准测试保留网段，Mihomo 等 TUN 虚拟网卡
    # 常把它作为本地地址返回，但目标电脑无法通过该地址回连。
    return address not in ipaddress.IPv4Network("198.18.0.0/15")


def detect_local_ip(target=None):
    """检测目标电脑可以回连的本机 IPv4 地址。

    先探测到目标的默认路由出口地址；TUN/VPN 让出口地址不可用时，再从主机名
    解析结果里挑真实局域网地址，并优先选择与目标同 /16 网段的候选。

    Args:
        target: 目标地址，可以为 None 表示只做通用探测。

    Returns:
        str: 本机 IPv4 地址，全部探测失败时返回 ``127.0.0.1``。
    """
    probes = []
    try:
        hosts = get_ip(target) if target else []
        if hosts:
            probes.append((hosts[0], 9))
    except ValueError:
        pass
    if not probes:
        probes.append(("8.8.8.8", 80))
    route_local = None
    for address, port in probes:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect((address, port))
                local = probe.getsockname()[0]
        except OSError:
            continue
        if local:
            route_local = local
        if _is_usable_local_address(local, address):
            return local

    # TUN/VPN 会改变系统默认路由，socket 的出口地址可能是虚拟网卡地址。
    # 如果出口地址不可用，则从主机名解析出的地址中选择真实局域网地址，
    # 并优先选择与目标地址处于同一 /16 网段的候选。
    candidates = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address and address not in candidates:
                candidates.append(address)
    except OSError:
        pass
    target_host = hosts[0] if hosts else None
    usable = [
        value for value in candidates if _is_usable_local_address(value, target_host)
    ]
    if usable:
        if target_host and not ipaddress.IPv4Address(target_host).is_loopback:
            # 每个候选地址只解析一次 IPv4Address，排序 key 里直接复用解析结果。
            target_prefix = ipaddress.IPv4Address(target_host).packed[:2]
            parsed = [(value, ipaddress.IPv4Address(value)) for value in usable]
            parsed.sort(
                key=lambda item: (
                    0 if item[1].packed[:2] == target_prefix else 1,
                    0 if item[1].is_private else 1,
                    item[0],
                )
            )
            return parsed[0][0]
        return usable[0]
    if route_local:
        return route_local
    return "127.0.0.1"


def local_ip_and_ports():
    """查询本机 IP 与学生端进程当前监听的 UDP 端口。

    Returns:
        tuple[str, list[str]]: 本机 IP 与按端口号升序排列的端口列表。

    Raises:
        RuntimeError: 进程或端口查询失败。
    """
    hostname = socket.gethostname()
    ip = socket.gethostbyname(hostname)
    tasks = run_windows_command(["tasklist", "/FO", "CSV", "/NH"])
    if tasks.returncode:
        raise RuntimeError(
            tasks.stderr.strip() or tasks.stdout.strip() or "进程查询失败"
        )
    pids = {
        row[1]
        for row in csv.reader(tasks.stdout.splitlines())
        if len(row) >= 2 and "student" in row[0].casefold()
    }
    if not pids:
        return ip, []
    connections = run_windows_command(["netstat", "-ano", "-p", "UDP"])
    if connections.returncode:
        raise RuntimeError(connections.stderr.strip() or "监听端口查询失败")
    ports = set()
    for line in connections.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0] == "UDP" and fields[-1] in pids:
            port = fields[1].rsplit(":", 1)[-1]
            if port.isdigit():
                ports.add(port)
    return ip, sorted(ports, key=int)


# 网卡前缀查一次就够用，结果缓存到进程结束；网卡变动后重启程序即可刷新。
_NETWORK_CACHE = None


def _query_ipv4_networks():
    """调用系统命令读取本机 IPv4 地址与前缀长度。

    ``ipconfig`` 的输出随系统语言变化，PowerShell 输出的对象属性名是固定的，
    因此改用它；查询失败时返回空列表，由调用方按 /24 兜底。

    Returns:
        list[tuple[str, int]]: ``(地址, 前缀长度)`` 列表。
    """
    script = (
        "Get-NetIPAddress -AddressFamily IPv4 | "
        "ForEach-Object { $_.IPAddress + '/' + $_.PrefixLength }"
    )
    try:
        process = run_windows_command(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
        )
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return []
    if process.returncode:
        return []
    networks = []
    for line in process.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            interface = ipaddress.ip_interface(text)
        except ValueError:
            continue
        networks.append((str(interface.ip), interface.network.prefixlen))
    return networks


def local_networks():
    """返回本机 IPv4 地址与其所在网段的前缀长度。

    宣告时要用本网段广播和网段首个可用地址去补齐组播覆盖不到的目标，需要先
    知道本机地址属于哪个网段。取不到网卡信息时按 /24 兜底，学校机房的网段
    基本都是 /24。

    Returns:
        list[tuple[str, int]]: ``(地址, 前缀长度)`` 列表。
    """
    global _NETWORK_CACHE
    if _NETWORK_CACHE is None:
        # 回环、链路本地与 TUN 虚拟网卡的地址发不出有用的广播，留着只会让
        # 宣告多跑几遍无用报文，这里只保留真正能到达局域网的网卡。
        networks = [
            (address, prefix)
            for address, prefix in _query_ipv4_networks()
            if _is_usable_local_address(address)
        ]
        if not networks:
            address = detect_local_ip()
            networks = [(address, 24)] if address else []
        _NETWORK_CACHE = networks
    return list(_NETWORK_CACHE)
