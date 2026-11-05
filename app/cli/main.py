"""命令行参数解析与命令分发。"""

import argparse
import sys
from os import system
from pathlib import Path
from time import sleep

from ..core import (
    FIREWALL_HELPER_ARGUMENT,
    LOGOFF_COMMAND,
    __version__,
    appcmd,
    basicCMD,
    cli_log,
    collect_students,
    format_size,
    get_ip,
    local_ip_and_ports,
    pkg_sendlist,
    portable_cli_log_path,
    read_message,
    request_firewall_rule,
    run_app_operation,
    run_firewall_helper,
    send_tracked,
    split_message,
    transfer_file,
)


def build_parser():
    """创建 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(description="极域学生端 UDP 控制报文测试工具")
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=__version__,
        help="显示版本号并退出",
    )
    parser.add_argument("-ip", type=str, help="ip 指定目标IP地址")
    parser.add_argument(
        "-p", type=int, default=4705, help="port 指定监听端口，默认端口为4705"
    )
    message_options = parser.add_mutually_exclusive_group()
    message_options.add_argument(
        "-msg", type=str, help="发送文本消息，支持多行；超长内容自动分条"
    )
    message_options.add_argument(
        "--msg-file",
        type=str,
        metavar="PATH",
        help="从 UTF-8 文件读取消息；使用 - 从标准输入读取",
    )
    message_options.add_argument(
        "--file",
        type=str,
        nargs="+",
        metavar="PATH",
        help="传送一个或多个文件、文件夹到目标电脑桌面，文件夹按原结构递归",
    )
    parser.add_argument(
        "-c", type=str, help='command命令 eg: -c   "cmd.exe /c ipconfig"'
    )
    parser.add_argument("-l", type=int, default=1, help="循环次数，默认为1")
    parser.add_argument("-t", type=int, default=22, help="循环时间间隔，默认是22秒")
    parser.add_argument(
        "--file-ip", type=str, metavar="IP", help="文件传送时发送端 IP，默认自动检测"
    )
    parser.add_argument(
        "--file-timeout",
        type=int,
        default=120,
        metavar="SECONDS",
        help="等待目标下载文件的秒数，默认 120",
    )
    parser.add_argument(
        "-e",
        type=str,
        choices=["r", "s", "l", "g", "break", "continue"],
        help="Extra Options加载额外的选项 eg：-e r；-e l 注销",
    )
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--run",
        metavar="PATH",
        help="在目标电脑上运行指定程序（应用命令 0x0F）",
    )
    action_group.add_argument(
        "--url", metavar="URL", help="在目标电脑上打开网址（应用命令 0x18）"
    )
    action_group.add_argument(
        "--kill", type=int, metavar="PID", help="结束目标电脑上的指定进程（MESS）"
    )
    action_group.add_argument(
        "--blackscreen",
        nargs="?",
        const=10,
        type=int,
        metavar="SECONDS",
        help="黑屏并按 SECONDS 秒自动解除，默认 10 秒",
    )
    action_group.add_argument(
        "--unlock", action="store_true", help="解除目标电脑的黑屏与键鼠锁"
    )
    action_group.add_argument(
        "--exit-student", action="store_true", help="让目标电脑退出学生端"
    )
    action_group.add_argument(
        "--close-apps", action="store_true", help="关闭目标电脑上的所有程序"
    )
    action_group.add_argument(
        "--announce",
        nargs="?",
        const=10,
        type=int,
        metavar="SECONDS",
        help="以教师端模拟身份发送宣告并监听 SECONDS 秒，默认 10 秒",
    )
    action_group.add_argument(
        "--students",
        nargs="?",
        const=8,
        type=int,
        metavar="SECONDS",
        help="发现学生机并拉取信息、进程与窗口，默认监听 8 秒",
    )
    parser.add_argument(
        "--run-args", type=str, default="", metavar="TEXT", help="--run 的启动参数"
    )
    parser.add_argument(
        "--run-show",
        type=int,
        default=0,
        choices=[0, 1, 2],
        metavar="MODE",
        help="--run 的窗口状态：0 正常、1 最小化、2 最大化",
    )
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help="--blackscreen 只黑屏，不锁定键盘与鼠标",
    )
    parser.add_argument(
        "--blackout-text",
        type=str,
        default="",
        metavar="TEXT",
        help="黑屏中间显示的提示",
    )
    parser.add_argument(
        "--channel",
        type=int,
        default=1,
        metavar="N",
        help="教师端模拟的会话频道，默认 1",
    )
    parser.add_argument(
        "--teacher-name",
        type=str,
        default="1",
        metavar="NAME",
        help="学生端显示的教师名",
    )
    return parser


parser = build_parser()


# 只打印帮助或版本号的调用没有任何副作用，也不该在数据目录留下日志文件。
INFORMATIONAL_ARGUMENTS = ("-h", "--help", "-V", "--version")


def is_informational(arguments):
    """判断本次调用是否只是查看帮助或版本号。

    只认单独一个帮助或版本号参数；``-msg "-h"`` 这类把短横线内容当作
    参数值传进来的写法仍按普通发送处理，避免误跳过日志。

    Args:
        arguments: 命令行参数列表。

    Returns:
        bool: 只查帮助或版本号时为 ``True``。
    """
    return len(arguments) == 1 and arguments[0] in INFORMATIONAL_ARGUMENTS


def start_logging():
    """启用命令行日志；等级固定 DEBUG，文件名与界面日志分开。"""
    cli_log.configure(portable_cli_log_path())
    log = cli_log.LOG
    if log.storage_error:
        print("[-] %s" % log.storage_error)
        return log
    log.debug("命令行日志已启用", "命令行", "文件：%s" % log.path)
    return log


def create_send_packets(arguments):
    """根据 CLI 参数构造待发送的报文列表。"""
    log = cli_log.LOG
    send_list = []

    # 先统一读取消息来源，确保 -msg 与 --msg-file 的处理保持一致。
    message = read_message(arguments)
    if message:
        chunks = list(split_message(message))
        log.debug(
            "已读取消息",
            "消息",
            "字符数：%d，分条：%d" % (len(message), len(chunks)),
        )
        send_list.extend(pkg_sendlist("-msg", chunk) for chunk in chunks)

    if arguments.c:
        log.debug("已加入命令", "命令", "命令：%s" % arguments.c)
        send_list.append(pkg_sendlist("-c", arguments.c))

    if arguments.e == "r":
        send_list.append(basicCMD["-r"].copy())

    if arguments.e == "s":
        send_list.append(basicCMD["-s"].copy())

    if arguments.e == "l":
        send_list.append(pkg_sendlist("-c", LOGOFF_COMMAND))

    return send_list


def single_command(arguments):
    """执行查询本机信息或切换本机防火墙规则等单项操作。"""
    log = cli_log.LOG
    if arguments.e == "g":
        try:
            ip, ports = local_ip_and_ports()
            if not ip:
                print("未能获取本机 IP 地址")
                log.warning("未能获取本机 IP 地址", "本机信息")
                return
            print("\\nYour ip addres is:" + ip)
            print("\\nYour student client possible ports are:" + ",".join(ports))
            log.info(
                "已获取本机信息", "本机信息", "IP：%s，端口：%s" % (ip, ",".join(ports))
            )
        except Exception as error:
            print("[-] %s" % error)
            log.error("获取本机信息失败", "本机信息", "异常：%r" % error)
        return

    elif arguments.e == "break":
        results = request_firewall_rule("block")
        sleep(1)
        system("cls")
        failed = any(not item["success"] for item in results)
        print(
            "[-] 部分防火墙设置失败，请检查管理员权限" if failed else "防火墙规则已阻断"
        )
        log_line = "防火墙规则已阻断" if not failed else "部分防火墙设置失败"
        log.add("WARNING" if failed else "INFO", log_line, "防火墙")
        return

    elif arguments.e == "continue":
        results = request_firewall_rule("allow")
        failed = any(not item["success"] for item in results)
        if failed:
            print("[-] 部分防火墙设置失败，请检查管理员权限")
            log.warning("部分防火墙设置失败，请检查管理员权限", "防火墙")
            return
        print("防火墙规则已恢复")
        log.info("防火墙规则已恢复", "防火墙")
        return


def run_file_transfer(arguments):
    """执行文件传送并输出传送结果。"""
    log = cli_log.LOG
    # argparse 给出的是列表；直接调用时允许传单个路径，统一成列表再下发。
    paths = arguments.file
    if isinstance(paths, (str, Path)):
        paths = [str(paths)]
    else:
        paths = [str(path) for path in paths]
    log.info("开始文件传送", "文件传送", "目标：%s" % arguments.ip)
    log.debug(
        "文件传送参数",
        "文件传送",
        "路径：%s；端口：%s；发送端：%s；超时：%s 秒"
        % (paths, arguments.p, arguments.file_ip or "自动检测", arguments.file_timeout),
    )
    result = transfer_file(
        arguments.ip,
        arguments.p,
        paths[0],
        listen_ip=arguments.file_ip,
        timeout=arguments.file_timeout,
        report=print,
        paths=paths,
    )
    log.debug(
        "文件传送完成",
        "文件传送",
        "文件：%s；数量：%s；大小：%d 字节；监听端口：%s"
        % (
            result.get("files"),
            result.get("file_count"),
            result["size"],
            result["port"] if result.get("port") is not None else "未启动",
        ),
    )
    if len(result["targets"]) == 1:
        print("文件已传送：%s（%s）" % (result["name"], format_size(result["size"])))
    else:
        print(
            "文件已传送到 %d 个目标桌面：%s（%s）"
            % (len(result["targets"]), result["name"], format_size(result["size"]))
        )
    log.info("文件已传送", "文件传送", "目标：%s" % "、".join(result["transferred"]))
    return 0


def print_delivery(outcome):
    """逐个目标输出送达判定，并给出成功与失败的数量。

    判定依据只有网络反馈：收到 ICMP 不可达说明报文没有被接收端收到，
    没有反馈只能说“未发现异常”，无法证明对方执行了命令。
    """
    log = cli_log.LOG
    for item in outcome.deliveries:
        if item.ok:
            print(
                "[成功] %s：%s（%d 个报文）" % (item.host, item.state.text, item.sent)
            )
            log.info(
                "目标送达未发现异常",
                "发送",
                "%s：%s（%d 个报文）" % (item.host, item.state.text, item.sent),
            )
        elif item.detail:
            print("[-] [失败] %s：%s（%s）" % (item.host, item.state.text, item.detail))
            log.error(
                "目标发送失败",
                "发送",
                "%s：%s（%s）" % (item.host, item.state.text, item.detail),
            )
        else:
            print("[-] [失败] %s：%s" % (item.host, item.state.text))
            log.error("目标发送失败", "发送", "%s：%s" % (item.host, item.state.text))
    total = len(outcome.deliveries)
    failed = len(outcome.failed)
    if failed:
        print("共 %d 个目标：成功 %d，失败 %d" % (total, total - failed, failed))
    else:
        print("共 %d 个目标：全部未发现异常" % total)


def log_arguments(arguments):
    """把本次参数快照写进日志，便于事后复现。"""
    cli_log.LOG.debug(
        "命令行参数",
        "命令行",
        "ip=%s；port=%s；msg=%s；msg_file=%s；file=%s；c=%s；l=%s；t=%s；e=%s；"
        "file_ip=%s；file_timeout=%s"
        % (
            arguments.ip,
            arguments.p,
            arguments.msg,
            arguments.msg_file,
            arguments.file,
            arguments.c,
            arguments.l,
            arguments.t,
            arguments.e,
            arguments.file_ip,
            arguments.file_timeout,
        ),
    )


def build_action_payload(arguments):
    """按 CLI 动作参数生成应用命令负载与投递通道。

    Returns:
        tuple | None: ``(动作名, 负载, 通道, 补发负载)``；没有动作参数时为
        ``None``。补发负载仅黑屏锁键鼠使用。

    Raises:
        ValueError: 同一调用里给了多个动作参数。
    """
    if arguments.run:
        return (
            "远程运行程序",
            appcmd.run_program_payload(
                arguments.run, arguments.run_args, arguments.run_show
            ),
            "comd",
            None,
        )
    if arguments.url:
        url = arguments.url if "://" in arguments.url else "http://" + arguments.url
        return "打开网址", appcmd.open_url_payload(url), "comd", None
    if arguments.kill is not None:
        return "终止进程", appcmd.kill_payload(process_id=arguments.kill), "mess", None
    if arguments.blackscreen is not None:
        lock = not arguments.no_lock
        return (
            "黑屏并锁定键鼠" if lock else "黑屏",
            appcmd.blackscreen_mess_payload(
                lock, arguments.blackscreen, arguments.blackout_text
            ),
            "session",
            appcmd.blackscreen_payload(lock, arguments.blackscreen) if lock else None,
        )
    if arguments.unlock:
        return "解除黑屏", appcmd.unlock_payload(), "session", None
    if arguments.exit_student:
        return "退出学生端", appcmd.exit_student_payload(), "comd", None
    if arguments.close_apps:
        return "关闭所有程序", appcmd.close_apps_payload(), "comd", None
    return None


def run_action(arguments):
    """执行应用命令、宣告或学生信息查询，返回是否已处理本次调用。"""
    log = cli_log.LOG
    if arguments.announce is not None or arguments.students is not None:
        duration = (
            arguments.announce if arguments.announce is not None else arguments.students
        )
        print("正在以教师端模拟身份发送宣告，监听 %d 秒…" % duration, flush=True)
        records = collect_students(
            duration=duration,
            channel=arguments.channel,
            teacher_name=arguments.teacher_name,
            port=arguments.p,
            report=print,
        )
        if not records:
            print("未发现学生机；请确认与学生端在同一网段，且频道一致")
            log.warning("未发现学生机", "教师端模拟", "监听 %d 秒" % duration)
            return True
        for record in records:
            info = record.get("info") or {}
            print(
                "\n[学生] %s  %s  用户：%s  系统：%s %s  CPU：%s %s  内存：%s"
                % (
                    record.get("address", ""),
                    info.get("name", "未知"),
                    info.get("user", "未知"),
                    info.get("os", ""),
                    info.get("os_version", ""),
                    info.get("cpu_vendor", ""),
                    info.get("cpu_model", ""),
                    info.get("memory", ""),
                )
            )
            for section, label in (("processes", "进程"), ("windows", "窗口")):
                entries = record.get(section) or []
                if not entries:
                    continue
                print("  %s（%d）" % (label, len(entries)))
                for identifier, name in entries:
                    print("    %-10s %s" % (identifier, name))
        log.info("教师端模拟查询完成", "教师端模拟", "学生数：%d" % len(records))
        return True

    action = build_action_payload(arguments)
    if action is None:
        return False
    name, payload, channel, lock = action
    hosts = get_ip(arguments.ip)
    print("开始%s，目标 %d 个" % (name, len(hosts)), flush=True)
    result = run_app_operation(
        hosts,
        payload,
        channel=channel,
        port=arguments.p,
        session_channel=arguments.channel,
        report=print,
        lock_payload=lock,
    )
    print("%s完成：%d 台目标，共发送 %d 字节" % (name, result["hosts"], result["sent"]))
    log.info(
        name, "应用命令", "目标：%d 台；字节：%d" % (result["hosts"], result["sent"])
    )
    return True


def run_from_cmd(arguments):
    """校验参数并分发 CLI 请求。"""
    log_arguments(arguments)
    log = cli_log.LOG
    try:
        if run_action(arguments):
            return
        single_command(arguments)
        if arguments.e in {"g", "break", "continue"}:
            return
        if arguments.file:
            if arguments.e or arguments.msg or arguments.msg_file or arguments.c:
                raise ValueError("文件传送不能与消息、命令或 -e 扩展功能同时使用")
            return run_file_transfer(arguments)
        if arguments.file_ip or arguments.file_timeout != 120:
            raise ValueError("--file-ip 和 --file-timeout 仅用于文件传送")
        send_list = create_send_packets(arguments)
        log.info(
            "开始发送",
            "发送",
            "目标：%s；端口：%d；报文：%d 个；循环：%d 次；间隔：%d 秒"
            % (arguments.ip, arguments.p, len(send_list), arguments.l, arguments.t),
        )
        outcome = send_tracked(
            send_list,
            arguments.ip,
            arguments.p,
            arguments.l,
            arguments.t,
            report=print,
        )
        print_delivery(outcome)
    except Exception as e:
        print("[-] %s" % e)
        log.error("命令执行失败", "命令行", "异常：%s" % e)
        return 1
    return 0


def main(argv=None):
    """解析参数并执行 CLI 或隐藏的防火墙助手。"""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == [FIREWALL_HELPER_ARGUMENT]:
        return run_firewall_helper(arguments[1:])
    if is_informational(arguments):
        # 帮助与版本号走 argparse 自身的退出路径，不创建数据目录与日志文件。
        parser.parse_args(arguments)
        return 0
    start_logging()
    cli_log.LOG.info(
        "命令行启动",
        "命令行",
        "参数：%s" % (" ".join(arguments) if arguments else "无"),
    )
    try:
        code = run_from_cmd(parser.parse_args(arguments))
    except SystemExit as error:
        # --help 与 --version 也用 SystemExit 结束，退出码 0 属于正常结束。
        if error.code in (0, None):
            cli_log.LOG.info("参数解析结束", "命令行", "退出码：%s" % error.code)
        else:
            cli_log.LOG.warning("参数解析未通过", "命令行", "退出码：%s" % error.code)
        cli_log.close()
        raise
    except BaseException:
        cli_log.close()
        raise
    cli_log.LOG.info("命令行结束", "命令行", "退出码：%s" % code)
    cli_log.close()
    return code
