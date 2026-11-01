"""本机 IP 与端口探测。"""

import csv
import ipaddress
import socket

from .firewall import _windows_command
from .protocol import get_ip

def validate_listen_ip(value):
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
    if address in ipaddress.IPv4Network("198.18.0.0/15"):
        return False
    return True


def detect_local_ip(target=None):
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
    usable = [value for value in candidates
              if _is_usable_local_address(value, target_host)]
    if usable:
        if target_host and not ipaddress.IPv4Address(target_host).is_loopback:
            target_value = ipaddress.IPv4Address(target_host)
            usable.sort(key=lambda value: (
                0 if ipaddress.IPv4Address(value).packed[:2] == target_value.packed[:2] else 1,
                0 if ipaddress.IPv4Address(value).is_private else 1,
                value,
            ))
        return usable[0]
    if route_local:
        return route_local
    return "127.0.0.1"


def local_ip_and_ports():
    hostname = socket.gethostname()
    ip = socket.gethostbyname(hostname)
    tasks = _windows_command(['tasklist', '/FO', 'CSV', '/NH'])
    if tasks.returncode:
        raise RuntimeError(tasks.stderr.strip() or tasks.stdout.strip() or "进程查询失败")
    pids = {row[1] for row in csv.reader(tasks.stdout.splitlines())
            if len(row) >= 2 and 'student' in row[0].casefold()}
    if not pids:
        return ip, []
    connections = _windows_command(['netstat', '-ano', '-p', 'UDP'])
    if connections.returncode:
        raise RuntimeError(connections.stderr.strip() or "监听端口查询失败")
    ports = set()
    for line in connections.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0] == 'UDP' and fields[-1] in pids:
            port = fields[1].rsplit(':', 1)[-1]
            if port.isdigit():
                ports.add(port)
    return ip, sorted(ports, key=int)
