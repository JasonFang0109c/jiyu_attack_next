"""命令行参数解析与命令分发。"""

import argparse
from multiprocessing import freeze_support
from os import system
from pathlib import Path
import sys
from time import sleep

from ..core import (
    FIREWALL_HELPER_ARGUMENT,
    LOGOFF_COMMAND,
    __version__,
    basicCMD,
    cli_log,
    format_size,
    local_ip_and_ports,
    pkg_sendlist,
    portable_cli_log_path,
    read_message,
    request_firewall_rule,
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
    return parser


parser = build_parser()


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


def run_from_cmd(arguments):
    """校验参数并分发 CLI 请求。"""
    log_arguments(arguments)
    log = cli_log.LOG
    try:
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
