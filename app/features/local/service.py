"""本机信息与端口占用查询。"""

import socket

from app.system.net.local import _is_usable_local_address, detect_local_ip
from app.system.windows.command import run_windows_command
from app.system.windows.process import netstat_rows, process_rows


def local_ip_and_ports():
    """查询本机 IP 与学生端进程当前监听的 UDP 端口。

    Returns:
        tuple[str, list[str]]: 本机 IP 与按端口号升序排列的端口列表。

    Raises:
        RuntimeError: 进程或端口查询失败。
    """
    hostname = socket.gethostname()
    ip = socket.gethostbyname(hostname)
    # 主机名可能解析到 TUN 网卡的 198.18.0.0/15 地址，学生端无法用这种
    # 地址回连，此时改用出口探测拿到的真实局域网地址。
    if not _is_usable_local_address(ip):
        ip = detect_local_ip()
    tasks = run_windows_command(["tasklist", "/FO", "CSV", "/NH"])
    if tasks.returncode:
        raise RuntimeError(
            tasks.stderr.strip() or tasks.stdout.strip() or "进程查询失败"
        )
    pids = {
        pid for name, pid in process_rows(tasks.stdout) if "student" in name.casefold()
    }
    if not pids:
        return ip, []
    connections = run_windows_command(["netstat", "-ano", "-p", "UDP"])
    if connections.returncode:
        raise RuntimeError(connections.stderr.strip() or "监听端口查询失败")
    ports = set()
    for address, pid in netstat_rows(connections.stdout):
        if pid not in pids:
            continue
        port = address.rsplit(":", 1)[-1]
        if port.isdigit():
            ports.add(port)
    return ip, sorted(ports, key=int)


def udp_port_owners(port, exclude_pids=()):
    """列出本机占用指定 UDP 端口的其他进程。

    学生端的回包只会送到教师端地址的 4705 端口，本机若同时跑着学生端客户端，
    它对同一地址的独占绑定会抢先收走回包，表现为“宣告发出去了但没人登录”。

    Args:
        port: 要检查的 UDP 端口。
        exclude_pids: 需要忽略的进程号，通常是本进程。

    Returns:
        list[dict]: 每项含 ``address``、``pid``、``name``，按进程号升序。

    Raises:
        RuntimeError: 端口或进程查询失败。
    """
    connections = run_windows_command(["netstat", "-ano", "-p", "UDP"])
    if connections.returncode:
        raise RuntimeError(connections.stderr.strip() or "监听端口查询失败")
    ignored = {str(pid) for pid in exclude_pids}
    owners = {}
    for address, pid in netstat_rows(connections.stdout):
        if address.rsplit(":", 1)[-1] != str(port) or pid in ignored:
            continue
        owners.setdefault(pid, []).append(address)
    if not owners:
        return []
    names = _process_names(tuple(owners))
    return [
        {
            "address": ",".join(sorted(addresses)),
            "pid": int(pid),
            "name": names.get(pid, "未知进程"),
        }
        for pid, addresses in sorted(owners.items(), key=lambda item: int(item[0]))
    ]


def _process_names(pids):
    """把进程号映射成映像名，查询失败时返回空字典。"""
    tasks = run_windows_command(["tasklist", "/FO", "CSV", "/NH"])
    if tasks.returncode:
        return {}
    wanted = {str(pid) for pid in pids}
    names = {}
    for row in process_rows(tasks.stdout):
        if row[1] in wanted:
            names[row[1]] = row[0]
    return names
