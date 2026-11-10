"""学生端进程的命令行参数与交互输出。"""

from app.features.student.service import (
    find_student_processes,
    start_student_process,
    stop_student_processes,
)
from app.shared.logs import cli as cli_log


def register(commands, defaults):
    """注册功能子命令并沿用统一参数默认值。"""
    student = commands.add_parser(
        "student",
        aliases=("endstudent",),
        help="启停学生端：按当前状态启动或结束本机极域学生端",
        description="启停本机极域学生端。不带选项时按当前状态决定方向："
        "有学生端在运行就结束它、腾出被独占的 4705 端口；没有就启动它、"
        "恢复课堂管理。非管理员时通过 UAC 提权执行。",
        epilog="示例：restriction student 按状态切换；"
        "restriction student --list 只查看；restriction student --start 强制启动。",
    )
    defaults = dict(defaults)
    defaults["endstudent"] = True
    student.set_defaults(**defaults)
    student.add_argument(
        "--list",
        action="store_true",
        help="只列出学生端进程与占用端口，不做任何改动",
    )
    student.add_argument(
        "--start",
        dest="start_student",
        action="store_true",
        help="启动学生端，路径留空时自动查找 StudentMain.exe",
    )
    student.add_argument(
        "--exe",
        dest="student_exe",
        metavar="PATH",
        help="配合 --start：指定学生端主程序的完整路径",
    )
    student.add_argument(
        "--pid",
        type=int,
        action="append",
        metavar="PID",
        help="只结束指定进程号，可重复；不写则按当前状态切换或结束全部",
    )


def add_flat_arguments(parser):
    """注册本功能兼容的扁平参数。"""
    parser.add_argument(
        "--end-student",
        dest="endstudent",
        action="store_true",
        help="结束本机正在运行的极域学生端进程，腾出 4705 端口（需要管理员权限）",
    )
    parser.add_argument(
        "--start-student",
        dest="start_student",
        action="store_true",
        help="启动本机极域学生端，恢复课堂管理（需要管理员权限）",
    )
    parser.add_argument(
        "--student-exe",
        dest="student_exe",
        metavar="PATH",
        help="配合 --start-student：指定学生端主程序的完整路径",
    )
    parser.add_argument(
        "--end-student-pid",
        dest="pid",
        type=int,
        action="append",
        metavar="PID",
        help="只结束指定进程号，可重复；解析后立即执行，不改变其它进程",
    )
    parser.add_argument(
        "--list-student",
        dest="list",
        action="store_true",
        help="列出本机学生端进程与占用端口，不结束",
    )


def _print_student_list(processes):
    """打印学生端进程列表，返回是否为空。"""
    if not processes:
        print("本机没有正在运行的学生端进程")
        return False
    for item in processes:
        ports = ", ".join(str(port) for port in item["ports"]) or "-"
        tail = ""
        if item.get("path") and not item.get("genuine"):
            tail = "  （目录里没有 LibTDMaster.dll，可能不是极域学生端）"
        print(
            "[*] PID %d  %s  端口 %s  路径 %s%s"
            % (
                item["pid"],
                item["name"],
                ports,
                item.get("path") or "不可读（需要管理员）",
                tail,
            )
        )
    return True


def _start_student(arguments):
    """启动学生端，返回退出码。"""
    log = cli_log.LOG
    results = start_student_process(arguments.student_exe)
    for item in results:
        print(("[+] " if item["success"] else "[-] ") + str(item.get("output", "")))
        if item["success"]:
            print("已启动学生端：%s" % item["path"])
            log.info("已启动学生端", "解除限制", "程序：%s" % item["path"])
        if not item.get("confirmed", True):
            print("[-] 没有检测到学生端进程，可能被安全软件拦下，试试用管理员权限运行")
    failed = [item for item in results if not item["success"]]
    if failed:
        log.error("启动学生端失败", "解除限制", "程序：%s" % failed[0]["path"])
        return 1
    return 0


def _stop_student(pids):
    """结束学生端，返回退出码。"""
    log = cli_log.LOG
    results = stop_student_processes(pids)
    for item in results:
        stage = "强制" if item.get("forced") else "正常"
        print(
            ("[+] " if item["success"] else "[-] ") + "%s：%s" % (stage, item["output"])
        )
    failed = [item for item in results if not item["success"]]
    if failed:
        log.error(
            "结束学生端失败",
            "解除限制",
            "失败进程：%s" % ", ".join(str(item["pid"]) for item in failed),
        )
        return 1
    print("已结束 %d 个学生端进程" % len(results))
    log.info("已结束学生端进程", "解除限制", "共 %d 个" % len(results))
    return 0


def run_student_command(arguments):
    """列出、启动或结束本机学生端。

    与界面上的单按钮一致：什么都不指定时按当前状态决定方向——有进程就结束，
    没有就启动。``--list`` 只列进程，``--start`` 强制启动，``--pid`` 只结束
    指定进程。

    Args:
        arguments: 解析后的参数。

    Returns:
        int: 0 表示成功，1 表示有进程未能启动或结束。
    """
    log = cli_log.LOG
    if arguments.list:
        processes = find_student_processes()
        _print_student_list(processes)
        log.info("已列出学生端进程", "解除限制", "共 %d 个" % len(processes))
        return 0
    if arguments.start_student:
        print("启动学生端：%s" % (arguments.student_exe or "自动查找安装位置"))
        return _start_student(arguments)
    if arguments.pid:
        print("结束指定的 %d 个学生端进程" % len(arguments.pid))
        return _stop_student(arguments.pid)
    # 只有按当前状态决定方向时才需要枚举进程，其余分支不必起子进程。
    processes = find_student_processes()
    if processes:
        print("检测到 %d 个学生端进程，按当前状态执行结束" % len(processes))
        _print_student_list(processes)
        return _stop_student(None)
    print("本机没有学生端进程，按当前状态执行启动")
    return _start_student(arguments)
