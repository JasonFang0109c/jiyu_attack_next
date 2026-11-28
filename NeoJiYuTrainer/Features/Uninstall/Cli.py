"""卸载应用的命令行参数与输出。"""

from NeoJiYuTrainer.Features.Uninstall.Service import install_root, run_uninstall


def register(commands, defaults):
    """注册卸载子命令并沿用统一参数默认值。"""
    uninstall = commands.add_parser(
        "uninstall", help="卸载应用：删除快捷方式、数据与驱动服务"
    )
    uninstall.add_argument("--keep-data", action="store_true", help="保留用户数据")
    uninstall.set_defaults(**dict(defaults))


def run_uninstall_command(arguments):
    """执行命令行卸载并打印结果。"""
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
