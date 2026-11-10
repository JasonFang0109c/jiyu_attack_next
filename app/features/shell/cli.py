"""交互终端的命令行参数与标准输入输出适配。"""

import sys
from queue import Empty, Queue
from threading import Thread
from time import sleep

from app.features.send.cli import add_port, add_target
from app.features.shell.service import ShellServer, send_command
from app.shared.logs import cli as cli_log
from app.system.net.targets import get_ip


def register(commands, defaults):
    """注册功能子命令并沿用统一参数默认值。"""
    shell = commands.add_parser("shell", help="反弹终端：本机监听并让目标连回来")
    shell.set_defaults(**dict(defaults))
    add_target(shell)
    add_port(shell)
    shell.set_defaults(shell=True)
    shell.add_argument(
        "--shell-port",
        type=int,
        default=0,
        metavar="PORT",
        help="本机监听端口，默认 0 表示随机",
    )
    shell.add_argument(
        "--shell-ip",
        type=str,
        default="",
        metavar="IP",
        help="写进目标连接命令的本机地址，默认自动探测",
    )


def add_flat_arguments(parser):
    """注册本功能兼容的扁平参数。"""
    parser.add_argument(
        "--shell",
        action="store_true",
        help="启动反弹终端：本机监听并通过远程命令让目标连回来交互",
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
        help="反弹终端写进目标连接命令的本机地址，默认自动探测",
    )


def run_shell(arguments):
    """启动反弹终端：本机监听、下发连接命令，并把本机终端接到会话上。"""
    log = cli_log.LOG
    host = get_ip(arguments.ip)[0]
    server = ShellServer(
        port=arguments.shell_port, local_ip=arguments.shell_ip or None, target=host
    )
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
