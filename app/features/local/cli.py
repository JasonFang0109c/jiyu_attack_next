"""本机信息的命令行参数与输出。"""

from app.features.local.service import local_ip_and_ports
from app.shared.logs import cli as cli_log


def register(commands, defaults):
    """注册功能子命令并沿用统一参数默认值。"""
    info = commands.add_parser("info", help="本机信息：本机 IP 与学生端端口")
    info.set_defaults(**dict(defaults))
    info.set_defaults(e="g")


def print_local_info():
    """打印本机 IP 与学生端可能占用的端口，返回退出码。"""
    log = cli_log.LOG
    try:
        ip, ports = local_ip_and_ports()
    except Exception as error:
        print("[-] %s" % error)
        log.error("获取本机信息失败", "本机信息", "异常：%r" % error)
        return 1
    if not ip:
        print("未能获取本机 IP 地址")
        log.warning("未能获取本机 IP 地址", "本机信息")
        return 1
    print()
    print("本机 IP 地址：" + ip)
    print("学生端可能占用的端口：" + ",".join(ports))
    log.info("已获取本机信息", "本机信息", "IP：%s，端口：%s" % (ip, ",".join(ports)))
    return 0
