"""IPv4 目标地址解析与数量统计。"""

import ipaddress


def _target_value(ip):
    """校验地址文本并去掉首尾空白。

    Raises:
        ValueError: 地址为空或不是字符串。
    """
    if not isinstance(ip, str) or not ip.strip():
        raise ValueError("请填写目标地址")
    return ip.strip()


def _target_spec(value):
    """把目标地址解析成 ``(首个地址整数, 地址数量)``。

    展开地址与只统计数量共用这一份解析，避免两处规则走偏。

    Raises:
        ValueError: 地址格式不受支持。
    """
    if "-" in value:
        if value.count("-") != 1:
            raise ValueError
        start, end = value.split("-")
        start_address = ipaddress.IPv4Address(start)
        if not end.isdigit():
            raise ValueError
        start_octet = int(start_address) & 0xFF
        end_octet = int(end)
        if not 1 <= start_octet <= end_octet <= 254:
            raise ValueError
        return int(start_address), end_octet - start_octet + 1
    if "/" in value:
        if not value.endswith("/24"):
            raise ValueError
        network = ipaddress.IPv4Network(value, strict=False)
        # /24 的 hosts() 只包含可用主机地址，首地址是网络地址加一。
        return int(network.network_address) + 1, 254
    return int(ipaddress.IPv4Address(value)), 1


def _parse_target(ip):
    """解析目标地址，把格式错误统一成一句中文提示。

    Raises:
        ValueError: 地址为空或格式不受支持。
    """
    value = _target_value(ip)
    try:
        return _target_spec(value)
    except ValueError as error:
        raise ValueError("IP 格式错误，请使用单个地址、末段范围或 /24 网段") from error


def get_ip(ip):
    """把目标地址展开为 IP 列表。

    Args:
        ip: 单个地址、``末段-末段`` 范围或 ``/24`` 网段。

    Returns:
        list[str]: 展开后的 IPv4 地址列表。

    Raises:
        ValueError: 地址为空或格式不受支持。
    """
    start, count = _parse_target(ip)
    return [str(ipaddress.IPv4Address(start + offset)) for offset in range(count)]


def count_targets(ip):
    """只统计地址数量，不逐个构造地址对象。

    界面每次输入变化都要刷新目标数量，为了取 len 而展开 254 个地址会拖慢输入
    响应，因此单独提供计数入口。

    Args:
        ip: 单个地址、``末段-末段`` 范围或 ``/24`` 网段。

    Returns:
        int: 地址数量。

    Raises:
        ValueError: 地址为空或格式不受支持。
    """
    return _parse_target(ip)[1]
