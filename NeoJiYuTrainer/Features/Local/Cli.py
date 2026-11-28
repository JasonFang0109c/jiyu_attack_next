"""本机信息的命令行参数与输出。"""

from NeoJiYuTrainer.Features.Local.Service import local_ip_and_ports
from NeoJiYuTrainer.Shared.Logs import Cli as cli_log


def register(commands, defaults):
    """注册功能子命令并沿用统一参数默认值。"""
    info = commands.add_parser("info", help="本机信息：本机 IP 与学生端端口")
    info.set_defaults(**dict(defaults))
    info.set_defaults(e="g")
    uninstall = commands.add_parser(
        "uninstall", help="卸载应用：删除快捷方式、数据与驱动服务"
    )
    uninstall.add_argument("--keep-data", action="store_true", help="保留 data")
    uninstall.set_defaults(**dict(defaults))
    uninstall.set_defaults(e="g")


def print_uninstall_info(arguments):
    """执行命令行卸载并打印结果。"""
    from NeoJiYuTrainer.Features.Uninstall.Service import install_root, run_uninstall

    if install_root() is None:
        print("源码运行时没有安装目录，已跳过卸载。")
        return 1
    result = run_uninstall(
        keep_user_data=bool(getattr(arguments, "keep_data", False)),
        remove_driver=True,
    )
    print("已删除快捷方式：%d 个" % len(result["shortcuts"]))
    print("用户数据已删除：%s" % ("是" if result["data_removed"] else "否"))
    if result["driver_error"]:
        print("驱动服务：%s" % result["driver_error"])
    print("安装目录清理已安排：%s" % ("是" if result["scheduled"] else "否"))
    return 0


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
