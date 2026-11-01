"""命令行参数解析与命令分发。"""

import argparse
import sys
from multiprocessing import freeze_support
from os import system
from time import sleep

from ..core import (
    FIREWALL_HELPER_ARGUMENT,
    LOGOFF_COMMAND,
    __version__,
    basicCMD,
    format_size,
    local_ip_and_ports,
    pkg_sendlist,
    read_message,
    request_firewall_rule,
    run_firewall_helper,
    send,
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
        "--file", type=str, metavar="PATH", help="传送本地文件到目标电脑桌面"
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


def create_send_packets(arguments):
    """根据 CLI 参数构造待发送的报文列表。"""
    send_list = []

    # 先统一读取消息来源，确保 -msg 与 --msg-file 的处理保持一致。
    message = read_message(arguments)
    if message:
        send_list.extend(
            pkg_sendlist("-msg", chunk) for chunk in split_message(message)
        )

    if arguments.c:
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
    if arguments.e == "g":
        try:
            ip, ports = local_ip_and_ports()
            if not ip:
                print("未能获取本机 IP 地址")
                return
            print("\nYour ip addres is:" + ip)
            print("\nYour student client possible ports are:" + ",".join(ports))
        except Exception as error:
            print("[-] %s" % error)
        return

    elif arguments.e == "break":
        results = request_firewall_rule("block")
        sleep(1)
        system("cls")
        failed = any(not item["success"] for item in results)
        print(
            "[-] 部分防火墙设置失败，请检查管理员权限" if failed else "防火墙规则已阻断"
        )
        return

    elif arguments.e == "continue":
        results = request_firewall_rule("allow")
        failed = any(not item["success"] for item in results)
        if failed:
            print("[-] 部分防火墙设置失败，请检查管理员权限")
            return
        print("防火墙规则已恢复")
        return


def run_file_transfer(arguments):
    """执行文件传送并输出传送结果。"""
    result = transfer_file(
        arguments.ip,
        arguments.p,
        arguments.file,
        listen_ip=arguments.file_ip,
        timeout=arguments.file_timeout,
        report=print,
    )
    if len(result["targets"]) == 1:
        print("文件已传送：%s（%s）" % (result["name"], format_size(result["size"])))
    else:
        print(
            "文件已传送到 %d 个目标桌面：%s（%s）"
            % (len(result["targets"]), result["name"], format_size(result["size"]))
        )
    return 0


def run_from_cmd(arguments):
    """校验参数并分发 CLI 请求。"""
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
        send(
            send_list,
            arguments.ip,
            arguments.p,
            arguments.l,
            arguments.t,
            report=print,
        )
    except Exception as e:
        print("[-] %s" % e)
        return 1
    return 0


def main(argv=None):
    """解析参数并执行 CLI 或隐藏的防火墙助手。"""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == [FIREWALL_HELPER_ARGUMENT]:
        return run_firewall_helper(arguments[1:])
    return run_from_cmd(parser.parse_args(arguments))


if __name__ == "__main__":
    freeze_support()
    sys.exit(main())
