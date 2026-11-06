"""屏幕观看会话：连上学生端的 4806 端口，收桌面分片并还原成帧。

学生端只在收到屏幕传输指令后才会开放 TCP 连接，因此这里只管连接、切包与
分片重组，把还原出来的记录交给调用方。JPEG 帧本身就是完整图片，可以直接
显示；H.264 记录交给 :mod:`app.core.video` 解码成位图再回调出去。
"""

import socket
import struct
import threading
from collections import deque
from contextlib import suppress

from . import appcmd, video

MAX_FRAME_SIZE = 0x241800
MAX_FRAME_COUNT = 4
RECEIVE_SIZE = 65535
# 记住最近交付的帧号，用来忽略重复到达的分片。
DELIVERED_HISTORY = 8


class ScreenSession:
    """一条到学生端的屏幕观看会话。

    Attributes:
        host: 学生地址。
        port: 学生端屏幕传输端口。
        channel: 桌面数据通道号，固定 10。
        latest: 最近一次收到的完整记录，没有则为 None。
    """

    def __init__(
        self,
        host,
        port=appcmd.TCP_COMM_PORT,
        channel=appcmd.DESKTOP_CHANNEL,
        timeout=5.0,
        on_record=None,
        on_log=None,
        on_frame=None,
    ):
        self.host = host
        self.port = port
        self.channel = channel
        self.timeout = timeout
        self.on_record = on_record
        self.on_log = on_log
        # 解出来的位图通过 on_frame 交给界面，参数是 (宽, 高, RGB 字节)。
        self.on_frame = on_frame
        self.latest = None
        self.decoder = video.H264Decoder()
        self._sock = None
        self._thread = None
        self._stop = threading.Event()
        self._frames = {}
        # 已交付的帧号，重复分片会因为缓存被删而重新建帧，这里挡住二次交付。
        self._delivered = deque(maxlen=DELIVERED_HISTORY)
        self._lock = threading.Lock()

    def open(self):
        """建立 TCP 连接并发送 UMSP 选择包。"""
        sock = socket.create_connection((self.host, self.port), self.timeout)
        sock.settimeout(self.timeout)
        try:
            sock.sendall(appcmd.umsp_hello_payload(self.channel))
        except OSError:
            sock.close()
            raise
        self._sock = sock
        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        self._log("已连接 %s:%d，开始接收桌面数据" % (self.host, self.port))
        return self

    def close(self):
        """停止读取并断开连接。"""
        self._stop.set()
        sock, self._sock = self._sock, None
        if sock is not None:
            with suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
            sock.close()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self._frames.clear()
        self._delivered.clear()
        self._log("已断开 %s 的屏幕连接" % self.host)

    def __enter__(self):
        return self.open()

    def __exit__(self, *_exc):
        self.close()

    def send(self, packet):
        """把远控输入包发给学生端。"""
        sock = self._sock
        if sock is None:
            raise RuntimeError("屏幕连接尚未建立")
        return sock.sendall(packet)

    def _log(self, message):
        if self.on_log:
            self.on_log(message)

    def _read_exact(self, sock, size):
        """读满指定字节，连接结束时返回 None。"""
        chunks = []
        remaining = size
        while remaining > 0:
            try:
                chunk = sock.recv(remaining)
            except socket.timeout:
                if self._stop.is_set():
                    return None
                continue
            except OSError:
                return None
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _read_loop(self):
        sock = self._sock
        if sock is None:
            return
        while not self._stop.is_set():
            header = self._read_exact(sock, 12)
            if header is None:
                break
            length = struct.unpack_from("<I", header, 8)[0]
            if length <= 0 or length > MAX_FRAME_SIZE:
                self._log("丢弃长度异常的 UMSP 包：%d" % length)
                break
            body = self._read_exact(sock, length)
            if body is None:
                break
            self._handle_packet(header, body)
        self._stop.set()

    def _handle_packet(self, header, body):
        try:
            magic, payload = appcmd.parse_umsp_header(header + body)
        except ValueError as error:
            self._log(str(error))
            return
        if magic != appcmd.UMSP_DATA_MAGIC:
            return
        if len(payload) < 4:
            return
        channel = struct.unpack_from("<I", payload, 0)[0]
        if channel != self.channel:
            return
        self._handle_fragment(payload[4:])

    def _handle_fragment(self, data):
        """把桌面分片攒成一条完整记录。"""
        if len(data) < 12:
            return
        frame, offset, total = struct.unpack_from("<III", data, 0)
        if not 0 < total <= MAX_FRAME_SIZE:
            return
        fragment = data[12:]
        if not fragment or offset + len(fragment) > total:
            return
        with self._lock:
            if frame in self._delivered:
                return
            entry = self._frames.get(frame)
            if entry is None or entry["total"] != total:
                # 帧号复用但长度变了，说明上一帧已作废，直接重来。
                entry = {"data": bytearray(total), "seen": set(), "total": total}
                self._frames[frame] = entry
            end = min(total, offset + len(fragment))
            entry["data"][offset:end] = fragment[: end - offset]
            entry["seen"].add((offset, end))
            complete = _covered(entry["seen"], total)
            if not complete:
                self._trim()
                return
            record = bytes(entry["data"])
            del self._frames[frame]
            self._delivered.append(frame)
        self._deliver(record)

    def _trim(self):
        """帧缓存只留最近几条，避免丢包时无限增长。"""
        while len(self._frames) > MAX_FRAME_COUNT:
            oldest = min(self._frames)
            del self._frames[oldest]

    def _deliver(self, record):
        try:
            parsed = appcmd.parse_desktop_record(record)
        except ValueError as error:
            self._log(str(error))
            return
        self.latest = parsed
        if self.on_record:
            self.on_record(parsed)
        if parsed.get("kind") == "h264" and self.on_frame:
            self._decode(parsed.get("payload") or b"")

    def _decode(self, data):
        """把 H.264 记录解成位图，解不出来就只记日志。"""
        try:
            frames = self.decoder.decode(data)
        except RuntimeError as error:
            self._log(str(error))
            return
        for width, height, pixels in frames:
            self.on_frame(width, height, pixels)


def _covered(seen, total):
    """判断已收到的区间是否完整覆盖整帧。"""
    position = 0
    for start, end in sorted(seen):
        if start > position:
            return False
        position = max(position, end)
        if position >= total:
            return True
    return position >= total


def fix_thumbnail(data):
    """把学生端缩略图还原成正常方向的 RGB 图片字节。

    学生端发的是自下而上的 DIB，并且只把 Cb/Cr 两个色度通道取反（亮度不
    变），所以要先上下翻转，再分别反相色度通道，最后按 RGB 重新编码。

    Args:
        data: 学生端发来的 JPEG 字节。

    Returns:
        bytes: 修正后的 JPEG 字节。
    """
    try:
        from io import BytesIO

        from PIL import Image, ImageOps
    except ImportError as error:  # pragma: no cover - 依赖缺失时的提示
        raise RuntimeError("缩略图修正需要 Pillow，请安装依赖后再试") from error

    image = Image.open(BytesIO(data))
    image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).convert("YCbCr")
    y, cb, cr = image.split()
    merged = Image.merge("YCbCr", (y, ImageOps.invert(cb), ImageOps.invert(cr)))
    buffer = BytesIO()
    merged.convert("RGB").save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()
