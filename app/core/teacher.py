"""教师端会话：组播宣告、登录握手与学生信息收集。

学生端只在收到教师端宣告或登录应答后才会继续通信，因此这里把「发宣告、等
握手、回会话应答、拉取学生信息」串成一个可取消的流程。套接字只在本模块创建，
报文拼装全部交给 :mod:`app.core.appcmd`。
"""

import ipaddress
import socket
import struct
import time
from contextlib import suppress
from threading import Lock
from time import monotonic, sleep

from . import appcmd
from .local_info import detect_local_ip, local_networks

# 组播回环要关掉，否则本机会收到自己发出的宣告，把监听结果撑成多个条目。
_MULTICAST_TTL = 32
_RECEIVE_BUFFER = 65535
# 收包超时决定取消响应速度，取值太小会让空闲时占满 CPU。
_POLL_TIMEOUT = 0.2
# 登录后等学生端把信息回传的时间，太短会拿不到 type 5。
_INFO_WAIT = 1.2
# 宣告后等目标登录的时间。聊天这类单播 MESS 必须有登录会话才生效。
_LOGIN_WAIT = 1.5


def _multicast_socket(port, group=None, local_ip=None):
    """创建可收发组播的 UDP 套接字。

    Args:
        port: 绑定端口。
        group: 要加入的组播地址，为空时只做普通发送。
        local_ip: 组播出口地址，为空时交给系统选择。

    Returns:
        socket.socket: 已绑定的套接字。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, _MULTICAST_TTL)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)
    if local_ip:
        sock.setsockopt(
            socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip)
        )
    sock.bind(("", port))
    if group:
        membership = socket.inet_aton(group) + socket.inet_aton("0.0.0.0")
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    sock.settimeout(_POLL_TIMEOUT)
    return sock


def announce_targets(local_ip, group, port, peers=None):
    """列出宣告要发往的目标，返回 ``(地址, 端口)`` 列表。

    组播在虚拟交换机和部分无线网络上会被过滤，只发组播时一台学生机都发现
    不到，所以除了组播地址再补两路：本网段广播，以及网段首个可用地址
    （VMware 的宿主虚拟网卡默认就落在网段第一个地址上）。``peers`` 用于手工
    指定跨网段的定向目标。

    Args:
        local_ip: 本机宣告地址，会从目标里剔除。
        group: 组播地址。
        port: 目标 UDP 端口。
        peers: 额外定向发送的地址，可以为 None。

    Returns:
        list[tuple[str, int]]: 去重后的目标列表。
    """
    targets = []
    seen = set()

    def add(host):
        if not host or host == local_ip or host in seen:
            return
        seen.add(host)
        targets.append((host, port))

    add(group)
    for address, prefix in local_networks():
        try:
            network = ipaddress.ip_network("%s/%d" % (address, prefix), strict=False)
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        # 前缀大于 30 时网段里没有广播可用，公网地址也不该被扫。
        if network.prefixlen > 30 or not parsed.is_private:
            continue
        add(str(network.broadcast_address))
        add(str(network.network_address + 1))
    for peer in peers or ():
        add(str(peer).strip())
    return targets


class TeacherSession:
    """一次教师端会话，负责宣告、握手应答与信息收集。

    Attributes:
        channel: 频道号，决定会话组播端点与学生端归属。
        teacher_name: 学生端显示的教师名。
        port: 学生端监听的 UDP 端口。
        local_ip: 本机宣告地址。
        students: 已登录学生，键为地址，值为收集到的信息。
    """

    def __init__(self, channel=1, teacher_name="1", port=4705, local_ip=None):
        self.channel = channel
        self.teacher_name = teacher_name
        self.port = port
        self.local_ip = local_ip or detect_local_ip()
        self.session_address, self.session_port = appcmd.session_endpoint(channel)
        self.students = {}
        self._lock = Lock()
        self._main = None
        self._session = None
        self._sequence = 0
        self._previews = appcmd.PreviewAssembler()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_exception):
        self.close()

    def open(self):
        """打开主通道与会话通道的组播套接字。"""
        if self._main is not None:
            return
        self._main = _multicast_socket(
            self.port, appcmd.MULTICAST_ADDRESS, self.local_ip
        )
        self._session = _multicast_socket(
            self.session_port, self.session_address, self.local_ip
        )

    def close(self):
        """关闭两个套接字，重复调用无副作用。"""
        for name in ("_main", "_session"):
            sock = getattr(self, name)
            if sock is not None:
                try:
                    sock.close()
                finally:
                    setattr(self, name, None)

    def announce(
        self, rounds=1, interval=1.0, report=None, cancel_event=None, peers=None
    ):
        """发送在线宣告，学生端据此发现自己并登录。

        Args:
            rounds: 发送轮数，0 表示一直发到取消。
            interval: 相邻两轮的间隔秒数。
            report: 进度回调。
            cancel_event: 取消信号。
            peers: 额外定向发送的地址，用于组播与广播都到不了的跨网段目标。

        Returns:
            int: 实际发送的报文数量。
        """
        self.open()
        targets = announce_targets(
            self.local_ip, appcmd.MULTICAST_ADDRESS, self.port, peers
        )
        sent = 0
        round_index = 0
        while rounds <= 0 or round_index < rounds:
            if cancel_event is not None and cancel_event.is_set():
                break
            self._sequence += 1
            packets = [
                appcmd.oonc_packet(self.local_ip, self._sequence),
                appcmd.nanc_packet(self.local_ip, self.channel, self.teacher_name),
                appcmd.canc_packet(self.local_ip, self.channel, self.teacher_name),
            ]
            for packet in packets:
                for target in targets:
                    self._main.sendto(packet, target)
                    sent += 1
            round_index += 1
            if report:
                report("第 %d 轮宣告已发送" % round_index)
            if rounds <= 0 or round_index < rounds:
                if cancel_event is not None:
                    if cancel_event.wait(interval):
                        break
                else:
                    sleep(interval)
        if report:
            report("宣告结束，共发送 %d 个报文" % sent)
        return sent

    @staticmethod
    def _blank_student(host):
        """返回一条空白学生记录，字段固定便于界面直接读取。"""
        return {
            "address": host,
            "info": {},
            "processes": [],
            "windows": [],
            "preview": None,
        }

    def _register(self, host, report=None):
        """登记学生并回会话应答，返回是否为新登录。"""
        with self._lock:
            if host in self.students:
                return False
            self.students[host] = self._blank_student(host)
        for packet in appcmd.session_replies(host):
            self._session.sendto(packet, (host, self.session_port))
            sleep(0.05)
        for packet in appcmd.thumbnail_packets():
            self._session.sendto(packet, (host, self.port))
        self._session.sendto(appcmd.dmoc_packet(self.local_ip), (host, self.port))
        if report:
            report("学生已登录：%s" % host)
        return True

    def listen(self, duration=10.0, report=None, cancel_event=None):
        """监听登录与信息上报，返回超时前收到的学生地址列表。

        Args:
            duration: 监听时长，0 表示一直监听到取消。
            report: 进度回调。
            cancel_event: 取消信号。

        Returns:
            list[str]: 本次监听中登录的学生地址。
        """
        self.open()
        deadline = None if duration <= 0 else monotonic() + duration
        found = []
        while deadline is None or monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                break
            for sock in (self._session, self._main):
                try:
                    data, address = sock.recvfrom(_RECEIVE_BUFFER)
                except socket.timeout:
                    continue
                except OSError:
                    break
                host = address[0]
                if appcmd.looks_like_login(data):
                    if self._register(host, report) and host not in found:
                        found.append(host)
                    continue
                self._serve(data, host)
                self._absorb(data, host)
        if report:
            report("监听结束，本次发现 %d 台学生机" % len(found))
        return found

    def _serve(self, data, host):
        """处理学生端主动发起的心跳、缩略图与重传请求。

        这些报文都需要教师端回包，否则学生端不会继续上报缩略图，所以在
        ``listen`` 的收包循环里一并处理。

        Args:
            data: 收到的报文。
            host: 发送方地址。
        """
        if len(data) < 4:
            return
        magic = struct.unpack("<I", data[:4])[0]
        if magic == appcmd.KACA_MAGIC:
            self._main.sendto(
                appcmd.waca_packet(self.local_ip, self.channel), (host, self.port)
            )
        elif magic == appcmd.TRMC_MAGIC:
            for packet in appcmd.thumbnail_packets():
                self._main.sendto(packet, (host, self.port))
            self._main.sendto(appcmd.dmoc_packet(self.local_ip), (host, self.port))
        elif magic == appcmd.DENT_MAGIC:
            self._answer_retransmit(data, host)
        elif magic == appcmd.LANT_MAGIC:
            self._store_preview(data, host)

    def _answer_retransmit(self, data, host):
        """按缺失分片回答 ``SRNT``，让学生端只补发缺的部分。"""
        try:
            frame = appcmd.dent_frame_sequence(data)
        except ValueError:
            return
        missing = self._previews.missing_parts(frame)
        packet = appcmd.srnt_packet(frame, complete=not missing, missing_parts=missing)
        self._main.sendto(packet, (host, self.port))

    def _store_preview(self, data, host):
        """把收齐的缩略图写进学生记录，并对重传请求及时应答。"""
        try:
            image = self._previews.feed(data)
        except ValueError:
            return
        if image is None:
            return
        with self._lock:
            student = self.students.get(host)
            if student is not None:
                student["preview"] = image

    def _absorb(self, data, host):
        """把收到的信息上报并入对应学生记录。"""
        try:
            message = appcmd.parse_message(data)
        except ValueError:
            return
        with self._lock:
            student = self.students.setdefault(host, self._blank_student(host))
            kind = message.get("kind")
            if kind == "info":
                student["info"] = message["info"]
            elif kind in {"processes", "windows"}:
                key = kind
                if message["first"]:
                    student[key] = []
                known = {entry[0] for entry in student[key]}
                student[key].extend(
                    entry for entry in message["entries"] if entry[0] not in known
                )

    def request_preview(self, host):
        """向学生端下发缩略图策略，让它开始推送画面缩略图。

        Args:
            host: 学生地址。
        """
        for packet in appcmd.thumbnail_packets():
            self._main.sendto(packet, (host, self.port))

    def request_info(self, host, report=appcmd.REPORT_ALL, wait=_INFO_WAIT):
        """向学生请求信息上报并等一会儿，让回复有时间回来。

        Args:
            host: 学生地址。
            report: 上报类型，0 全部、1 窗口、2 进程。
            wait: 等待回复的秒数。
        """
        self._session.sendto(
            appcmd.mess_packet(host, appcmd.info_request_payload(report)),
            (host, self.session_port),
        )
        deadline = monotonic() + max(0.0, wait)
        while monotonic() < deadline:
            try:
                data, address = self._session.recvfrom(_RECEIVE_BUFFER)
            except socket.timeout:
                continue
            except OSError:
                return
            self._absorb(data, address[0])

    def send_command(self, host, payload, report=None, label=""):
        """把应用命令单播给学生，返回发送的字节数。"""
        packet = appcmd.comd_packet(payload)
        sent = self._session.sendto(packet, (host, self.port)) if self._session else 0
        if report:
            report("%s → %s（%d 字节）" % (label or "应用命令", host, sent))
        return sent

    def send_mess(self, host, payload, report=None, label=""):
        """把 MESS 负载单播给学生。"""
        packet = appcmd.mess_packet(host, payload)
        sent = (
            self._session.sendto(packet, (host, self.session_port))
            if self._session
            else 0
        )
        if report:
            report("%s → %s（%d 字节）" % (label or "MESS", host, sent))
        return sent

    def chat(self, host, text, report=None):
        """向已登录的学生发一条会话聊天消息。

        Args:
            host: 学生地址。
            text: 聊天文本。
            report: 进度回调。

        Returns:
            int: 发送的字节数。
        """
        return self.send_mess(host, appcmd.chat_payload(text), report, "聊天消息")

    def close_window(self, host, window, report=None):
        """按窗口句柄关闭学生机上的应用（MESS 0x100000 type 3）。

        走的是 ``WM_CLOSE``，学生端只关窗口不杀进程，和按进程号强杀不同。

        Args:
            host: 学生地址。
            window: 窗口句柄。
            report: 进度回调。

        Returns:
            int: 发送的字节数。
        """
        payload = appcmd.kill_payload(window=window, force=False)
        return self.send_mess(host, payload, report, "关闭应用窗口")

    def blackscreen(self, host, lock_input=True, timeout=10, text=""):
        """黑屏并锁键鼠：MESS 发到会话组播，同时补一条 COMD 给学生单播。"""
        self._session.sendto(
            appcmd.mess_packet(
                host, appcmd.blackscreen_mess_payload(lock_input, timeout, text)
            ),
            (self.session_address, self.session_port),
        )
        if lock_input:
            self.send_command(host, appcmd.blackscreen_payload(lock_input, timeout))

    def unlock(self, host):
        """解除黑屏与键鼠锁。"""
        self._session.sendto(
            appcmd.mess_packet(host, appcmd.unlock_payload()),
            (self.session_address, self.session_port),
        )


def send_app_command(
    host, payload, port=4705, local_ip=None, label="应用命令", report=None
):
    """不需要会话时的一条应用命令，直接用临时套接字发出。

    Args:
        host: 学生地址。
        payload: :mod:`app.core.appcmd` 生成的负载。
        port: 学生端 UDP 端口。
        local_ip: 组播出口地址，可省略。
        label: 日志里显示的动作名。
        report: 进度回调。

    Returns:
        int: 发送的字节数。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if local_ip:
            sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip)
            )
        sent = sock.sendto(appcmd.comd_packet(payload), (host, port))
    finally:
        sock.close()
    if report:
        report("%s → %s（%d 字节）" % (label, host, sent))
    return sent


def send_lcmd_command(
    host, payload, port=4705, local_ip=None, label="轻量命令", report=None
):
    """用不带事务应答的轻量通道发一条应用命令。

    ``LCMD`` 与 ``COMD`` 承载同样的负载，只是少了超时与事务号，适合一次性、
    不需要确认的指令。

    Args:
        host: 学生地址。
        payload: :mod:`app.core.appcmd` 生成的负载。
        port: 学生端 UDP 端口。
        local_ip: 组播出口地址，可省略。
        label: 日志里显示的动作名。
        report: 进度回调。

    Returns:
        int: 发送的字节数。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if local_ip:
            sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip)
            )
        sent = sock.sendto(appcmd.lcmd_packet(payload), (host, port))
    finally:
        sock.close()
    if report:
        report("%s → %s（%d 字节）" % (label, host, sent))
    return sent


def send_mess_command(
    host, payload, channel=1, local_ip=None, label="MESS", report=None
):
    """不需要会话时的一条 MESS 报文，单播到会话端点。

    黑屏这类报文学生端只在会话通道上处理，所以即使只有一个目标也要发到它的
    会话端口。
    """
    _address, port = appcmd.session_endpoint(channel)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if local_ip:
            sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip)
            )
        sent = sock.sendto(appcmd.mess_packet(host, payload), (host, port))
    finally:
        sock.close()
    if report:
        report("%s → %s（%d 字节）" % (label, host, sent))
    return sent


def send_session_broadcast(
    hosts, payload, channel=1, local_ip=None, label="MESS", report=None
):
    """把 MESS 负载发到会话组播端点。

    黑屏与解锁这类指令学生端只在会话组播上处理，单播反而不生效，因此不能
    复用 ``send_mess_command``。组播只决定报文走哪条链路，报文里仍然要写明
    接收学生自己的地址，所以按目标逐个发送。

    Args:
        hosts: 学生地址列表。
        payload: :mod:`app.core.appcmd` 生成的负载。
        channel: 频道号。
        local_ip: 组播出口地址，可省略。
        label: 日志里显示的动作名。
        report: 进度回调。

    Returns:
        int: 发送的字节数合计。

    Raises:
        ValueError: 目标列表为空。
    """
    targets = [address for address in hosts if address]
    if not targets:
        raise ValueError("请先指定目标地址")
    address, port = appcmd.session_endpoint(channel)
    sent = 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, _MULTICAST_TTL)
        if local_ip:
            sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip)
            )
        for host in targets:
            sent += sock.sendto(appcmd.mess_packet(host, payload), (address, port))
    finally:
        sock.close()
    if report:
        report(
            "%s → %s:%d（%d 台，%d 字节）" % (label, address, port, len(targets), sent)
        )
    return sent


def run_app_operation(
    hosts,
    payload,
    channel="comd",
    port=4705,
    session_channel=1,
    local_ip=None,
    report=None,
    cancel_event=None,
    lock_payload=None,
):
    """按通道把一条应用命令发给全部目标。

    三条通道分工不同：``comd`` 单播应用命令，``mess`` 单播会话报文，
    ``session`` 发到会话组播（黑屏与解锁只有这条能生效）。黑屏需要同时锁
    键鼠时，额外用 ``lock_payload`` 给每台学生会补一条应用命令。

    Args:
        hosts: 学生地址列表。
        payload: 主负载。
        channel: 通道代码，``comd``/``lcmd``/``mess``/``session``。
        port: 学生端 UDP 端口。
        session_channel: 会话频道号。
        local_ip: 组播出口地址，可省略。
        report: 进度回调。
        cancel_event: 取消信号。
        lock_payload: 需要逐台补发的应用命令负载，可省略。

    Returns:
        dict: ``{"sent": 字节数合计, "hosts": 目标数}``。

    Raises:
        RuntimeError: 收到取消信号。
    """
    sent = 0
    if channel == "session":
        sent += send_session_broadcast(
            hosts, payload, session_channel, local_ip, "会话报文", report
        )
    else:
        for host in hosts:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("操作已取消")
            if channel == "mess":
                sent += send_mess_command(
                    host, payload, session_channel, local_ip, "会话报文", report
                )
            elif channel == "lcmd":
                sent += send_lcmd_command(
                    host, payload, port, local_ip, "轻量命令", report
                )
            else:
                sent += send_app_command(
                    host, payload, port, local_ip, "应用命令", report
                )
    if lock_payload is not None:
        for host in hosts:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("操作已取消")
            sent += send_app_command(
                host, lock_payload, port, local_ip, "锁定键鼠", report
            )
    if report:
        report("已发送 %d 个字节给 %d 台设备" % (sent, len(hosts)))
    return {"sent": sent, "hosts": len(hosts)}


def send_app_commands(
    hosts, payload, port=4705, local_ip=None, label="应用命令", report=None
):
    """把同一条应用命令发给多个学生，返回累计发送的字节数。

    Args:
        hosts: 学生地址列表。
        payload: :mod:`app.core.appcmd` 生成的负载。
        port: 学生端 UDP 端口。
        local_ip: 组播出口地址，可省略。
        label: 日志里显示的动作名。
        report: 进度回调。

    Returns:
        int: 累计发送的字节数。
    """
    total = 0
    for index, host in enumerate(hosts, 1):
        total += send_app_command(host, payload, port, local_ip, label)
        if report:
            report("%s：已完成第 %d/%d 台" % (label, index, len(hosts)))
    return total


def send_blackscreens(
    hosts, channel=1, lock_input=True, timeout=10, text="", local_ip=None, report=None
):
    """让多台学生黑屏；需要锁键鼠时再逐台补一条应用命令。

    黑屏报文学生端只在会话组播上处理，单播无效；键鼠锁走应用命令通道，
    两条通道缺一不可，所以这里同时发。
    """
    sent = send_session_broadcast(
        hosts,
        appcmd.blackscreen_mess_payload(lock_input, timeout, text),
        channel,
        local_ip,
        "黑屏",
        report,
    )
    if lock_input:
        for host in hosts:
            sent += send_app_command(
                host,
                appcmd.blackscreen_payload(lock_input, timeout),
                local_ip=local_ip,
                label="锁定键鼠",
                report=report,
            )
    return sent


def send_unlocks(hosts, channel=1, local_ip=None, report=None):
    """解除多台学生的黑屏与键鼠锁。"""
    return send_session_broadcast(
        hosts, appcmd.unlock_payload(), channel, local_ip, "解除黑屏", report
    )


def collect_students(
    duration=10.0,
    channel=1,
    teacher_name="1",
    port=4705,
    report=None,
    cancel_event=None,
    peers=None,
    report_kind=appcmd.REPORT_ALL,
):
    """发一轮宣告后监听，返回带信息的学生记录列表。

    Args:
        duration: 监听时长。
        channel: 频道号。
        teacher_name: 学生端显示的教师名。
        port: 学生端 UDP 端口。
        report: 进度回调。
        cancel_event: 取消信号。
        peers: 额外定向宣告的地址，可为 None。
        report_kind: 登录后请求的上报类型，默认全部。

    Returns:
        list[dict]: 每台学生机的地址与已收集到的信息。
    """
    with TeacherSession(channel, teacher_name, port) as session:
        session.announce(
            rounds=1, report=report, cancel_event=cancel_event, peers=peers
        )
        session.listen(duration, report=report, cancel_event=cancel_event)
        for host in list(session.students):
            if cancel_event is not None and cancel_event.is_set():
                break
            session.request_info(host, report_kind)
        return [dict(session.students[host]) for host in session.students]


def fetch_students_info(
    hosts,
    channel=1,
    teacher_name="1",
    port=4705,
    report=None,
    whole_report=appcmd.REPORT_ALL,
):
    """向指定学生请求信息上报，返回收集到的记录。

    Args:
        hosts: 学生地址列表。
        channel: 频道号。
        teacher_name: 学生端显示的教师名。
        port: 学生端 UDP 端口。
        report: 进度回调。
        whole_report: 上报类型，0 全部、1 窗口、2 进程。

    Returns:
        list[dict]: 每台学生机的地址与信息。
    """
    with TeacherSession(channel, teacher_name, port) as session:
        for host in hosts:
            session.request_info(host, whole_report)
        for host in hosts:
            session.students.setdefault(
                host, {"address": host, "info": {}, "processes": [], "windows": []}
            )
        return [dict(session.students[host]) for host in hosts]


def send_to_logged_students(
    payload_for,
    hosts,
    channel=1,
    teacher_name="1",
    port=4705,
    login_wait=_LOGIN_WAIT,
    label="MESS",
    report=None,
    cancel_event=None,
):
    """先宣告等登录，再向目标逐个单播 ``MESS`` 负载。

    聊天消息和按窗口关闭都要求学生已经登录教师会话，无会话时单播过去学生端
    直接丢掉，所以这里必须先宣告并等一会儿登录请求。

    Args:
        payload_for: 接收学生地址、返回负载字节的可调用对象。
        hosts: 目标地址列表。
        channel: 频道号。
        teacher_name: 学生端显示的教师名。
        port: 学生端 UDP 端口。
        login_wait: 等待登录的秒数。
        label: 进度回调里显示的动作名。
        report: 进度回调。
        cancel_event: 取消信号。

    Returns:
        list[str]: 实际发出负载的目标地址。

    Raises:
        ValueError: 目标列表为空，或没有任何目标完成登录。
    """
    targets = [address for address in hosts if address]
    if not targets:
        raise ValueError("请先指定目标地址")
    with TeacherSession(channel, teacher_name, port) as session:
        session.announce(
            rounds=1, peers=targets, report=report, cancel_event=cancel_event
        )
        session.listen(login_wait, report=report, cancel_event=cancel_event)
        logged = [host for host in targets if host in session.students]
        if not logged:
            raise ValueError("目标没有登录教师会话，先确认学生端在线且频道一致")
        for host in logged:
            session.send_mess(host, payload_for(host), report, label)
    return logged


def send_chat(
    hosts,
    text,
    channel=1,
    teacher_name="1",
    port=4705,
    report=None,
    cancel_event=None,
):
    """向已登录的学生发送会话聊天消息，返回实际送达的目标。

    Args:
        hosts: 学生地址列表。
        text: 聊天文本。
        channel: 频道号。
        teacher_name: 学生端显示的教师名。
        port: 学生端 UDP 端口。
        report: 进度回调。
        cancel_event: 取消信号。

    Returns:
        list[str]: 实际发出消息的目标地址。
    """
    payload = appcmd.chat_payload(text)
    return send_to_logged_students(
        lambda _host: payload,
        hosts,
        channel,
        teacher_name,
        port,
        label="聊天消息",
        report=report,
        cancel_event=cancel_event,
    )


def close_window(
    hosts,
    window,
    channel=1,
    teacher_name="1",
    port=4705,
    report=None,
    cancel_event=None,
):
    """按窗口句柄关闭学生机上的应用，返回实际送达的目标。

    Args:
        hosts: 学生地址列表。
        window: 窗口句柄。
        channel: 频道号。
        teacher_name: 学生端显示的教师名。
        port: 学生端 UDP 端口。
        report: 进度回调。
        cancel_event: 取消信号。

    Returns:
        list[str]: 实际发出关闭指令的目标地址。
    """
    payload = appcmd.kill_payload(window=window, force=False)
    return send_to_logged_students(
        lambda _host: payload,
        hosts,
        channel,
        teacher_name,
        port,
        label="关闭应用窗口",
        report=report,
        cancel_event=cancel_event,
    )


def match_entries(entries, keyword):
    """在 ``(编号, 名称)`` 列表里按名称查找。

    先做忽略大小写的精确匹配，没有命中再退化成包含匹配。这一分层与来源项目
    的 ``kill``、``closeapp`` 一致：填完整进程名不会误伤同名子串。

    Args:
        entries: ``(编号, 名称)`` 序列，来自学生信息上报。
        keyword: 进程名或窗口标题关键字。

    Returns:
        list[tuple]: 命中的 ``(编号, 名称)``。
    """
    text = str(keyword or "").strip().casefold()
    if not text:
        return []
    exact = [item for item in entries if str(item[1]).strip().casefold() == text]
    if exact:
        return exact
    return [item for item in entries if text in str(item[1]).casefold()]


def send_payloads_to_logged_students(
    payloads_for,
    hosts,
    channel=1,
    teacher_name="1",
    port=4705,
    login_wait=_LOGIN_WAIT,
    label="MESS",
    report=None,
    cancel_event=None,
):
    """先宣告等登录，再向目标逐个单播多条 ``MESS`` 负载。

    按名称结束进程、按标题关闭窗口会先在本地匹配出多个编号，每个编号都是一
    条独立报文，因此这里允许一台学生对应多条负载。

    Args:
        payloads_for: 接收学生地址、返回负载列表的可调用对象。
        hosts: 目标地址列表。
        channel: 频道号。
        teacher_name: 学生端显示的教师名。
        port: 学生端 UDP 端口。
        login_wait: 等待登录的秒数。
        label: 进度回调里显示的动作名。
        report: 进度回调。
        cancel_event: 取消信号。

    Returns:
        list[tuple[str, int]]: 每台学生的地址与实际发送条数。

    Raises:
        ValueError: 目标列表为空，或没有任何目标完成登录。
    """
    targets = [address for address in hosts if address]
    if not targets:
        raise ValueError("请先指定目标地址")
    sent = []
    with TeacherSession(channel, teacher_name, port) as session:
        session.announce(
            rounds=1, peers=targets, report=report, cancel_event=cancel_event
        )
        session.listen(login_wait, report=report, cancel_event=cancel_event)
        logged = [host for host in targets if host in session.students]
        if not logged:
            raise ValueError("目标没有登录教师会话，先确认学生端在线且频道一致")
        for host in logged:
            payloads = list(payloads_for(host) or [])
            for payload in payloads:
                session.send_mess(host, payload, report, label)
            sent.append((host, len(payloads)))
    return sent


def kill_processes(
    records,
    keyword,
    channel=1,
    teacher_name="1",
    port=4705,
    report=None,
    cancel_event=None,
    force=True,
):
    """按进程名结束学生机进程，返回每台命中的进程。

    Args:
        records: 已收集的学生记录，需带 ``processes`` 列表。
        keyword: 进程名，先精确匹配再包含匹配。
        channel: 频道号。
        teacher_name: 学生端显示的教师名。
        port: 学生端 UDP 端口。
        report: 进度回调。
        cancel_event: 取消信号。
        force: True 强杀，False 先尝试正常关闭。

    Returns:
        dict[str, list[tuple]]: 地址 → 命中的 ``(进程号, 名称)``。

    Raises:
        ValueError: 学生记录里没有匹配的进程，或目标未登录。
    """
    matched = {}
    for record in records or []:
        address = record.get("address")
        hits = match_entries(record.get("processes") or [], keyword)
        if address and hits:
            matched[address] = hits
    if not matched:
        raise ValueError("进程列表里没有匹配“%s”的进程，先刷新学生信息" % keyword)
    payloads = {
        address: [
            appcmd.kill_payload(process_id=identifier, force=force)
            for identifier, _name in hits
        ]
        for address, hits in matched.items()
    }
    send_payloads_to_logged_students(
        lambda host: payloads.get(host, []),
        list(matched),
        channel=channel,
        teacher_name=teacher_name,
        port=port,
        label="结束进程",
        report=report,
        cancel_event=cancel_event,
    )
    return matched


def close_windows(
    records,
    keyword,
    channel=1,
    teacher_name="1",
    port=4705,
    report=None,
    cancel_event=None,
):
    """按窗口标题关键字关闭学生机窗口，返回每台命中的窗口。

    与 :func:`close_window` 的区别是这里先按标题匹配出句柄，可以一次关掉多个
    命中窗口；仍然只发 ``WM_CLOSE``，不结束进程。

    Args:
        records: 已收集的学生记录，需带 ``windows`` 列表。
        keyword: 窗口标题关键字。
        channel: 频道号。
        teacher_name: 学生端显示的教师名。
        port: 学生端 UDP 端口。
        report: 进度回调。
        cancel_event: 取消信号。

    Returns:
        dict[str, list[tuple]]: 地址 → 命中的 ``(句柄, 标题)``。

    Raises:
        ValueError: 学生记录里没有匹配的窗口，或目标未登录。
    """
    matched = {}
    for record in records or []:
        address = record.get("address")
        hits = match_entries(record.get("windows") or [], keyword)
        if address and hits:
            matched[address] = hits
    if not matched:
        raise ValueError("窗口列表里没有标题含“%s”的窗口，先刷新学生信息" % keyword)
    payloads = {
        address: [
            appcmd.kill_payload(window=identifier, force=False)
            for identifier, _title in hits
        ]
        for address, hits in matched.items()
    }
    send_payloads_to_logged_students(
        lambda host: payloads.get(host, []),
        list(matched),
        channel=channel,
        teacher_name=teacher_name,
        port=port,
        label="关闭应用窗口",
        report=report,
        cancel_event=cancel_event,
    )
    return matched


def start_screen(host, channel=1, local_ip=None, report=None):
    """请学生端开始向本机推送桌面画面。

    学生端只有在收到这条 ``feature 8`` 报文后才会去连本机的 TCP 端口，所以
    必须先发报文再建立 :class:`app.core.screen.ScreenSession`。

    Args:
        host: 学生地址。
        channel: 会话频道号。
        local_ip: 教师端地址，写进参数块。
        report: 进度回调。

    Returns:
        int: 发送的字节数。
    """
    _address, port = appcmd.session_endpoint(channel)
    payload = appcmd.screen_start_payload(local_ip or detect_local_ip(), port, port)
    return send_mess_command(host, payload, channel, local_ip, "屏幕传输", report)


def stop_screen(host, channel=1, local_ip=None, report=None):
    """通知学生端停止推送桌面画面。"""
    return send_mess_command(
        host, appcmd.screen_stop_payload(), channel, local_ip, "停止屏幕传输", report
    )


class RemoteControl:
    """常驻的远控通道：先请求接管，再用同一个套接字持续发送输入。

    学生端只认「发出接管请求的那个本地端口」送来的输入，所以套接字必须一直
    留着，不能像普通命令那样发包就关。

    Attributes:
        host: 学生地址。
        local_ip: 教师端地址。
        mode: 0 双方可操作、1 停止、2 仅教师操作并锁定学生输入。
        port: 本机输入端口，构造后由 :meth:`open` 填入实际值。
    """

    # 学生端接管后要过一小会儿才收输入，首包太早会被丢掉。
    READY_DELAY = 0.35
    MOUSE = 1
    KEYBOARD = 16

    def __init__(self, host, local_ip, mode=2, port=0, udp_port=4705):
        self.host = host
        self.local_ip = local_ip
        self.mode = mode
        self.port = port
        self.udp_port = udp_port
        self._sock = None
        self._ready_at = 0.0
        self.inputs = 0

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_exc):
        self.close()

    def open(self):
        """绑定本机端口并发出接管请求。

        Returns:
            int: 本机输入端口。
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.local_ip, self.port))
        self.port = sock.getsockname()[1]
        payload = appcmd.remote_control_payload_for(self.host, self.mode, self.port)
        packet = appcmd.command_transaction_packet(payload, self.local_ip)
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sender.sendto(packet, (self.host, self.udp_port))
        finally:
            sender.close()
        self._sock = sock
        self._ready_at = monotonic() + self.READY_DELAY
        return self.port

    def send(self, kind, payload):
        """发送一条输入报文。

        Args:
            kind: :attr:`MOUSE` 或 :attr:`KEYBOARD`。
            payload: 20 字节输入体。

        Raises:
            RuntimeError: 还未 :meth:`open`。
        """
        if self._sock is None:
            raise RuntimeError("远控尚未开始，请先请求接管")
        delay = self._ready_at - monotonic()
        if delay > 0:
            sleep(delay)
        self._sock.sendto(appcmd.input_packet(kind, payload), (self.host, self.port))
        self.inputs += 1

    def mouse(self, action, x, y, data=0, swapped=0):
        """发送鼠标事件，坐标已归一化到 0..65535。"""
        self.send(self.MOUSE, appcmd.mouse_input_payload(action, x, y, data, swapped))

    def key(self, scan_code, virtual_key, key_up=False, extended=False):
        """发送键盘事件。"""
        self.send(
            self.KEYBOARD,
            appcmd.key_input_payload(scan_code, virtual_key, key_up, extended),
        )

    def close(self, send_stop=True):
        """关闭输入通道，可选通知学生端解除锁定。"""
        sock = self._sock
        self._sock = None
        if sock is not None:
            with suppress(OSError):
                sock.close()
        if send_stop:
            payload = appcmd.remote_control_payload_for(self.host, 1, self.port)
            packet = appcmd.command_transaction_packet(payload, self.local_ip)
            sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                with suppress(OSError):
                    sender.sendto(packet, (self.host, self.udp_port))
            finally:
                sender.close()


def remote_control(
    host, local_ip, mode=2, port=0, udp_port=4705, report=None, cancel_event=None
):
    """请求接管学生端输入，返回可继续发送键鼠事件的通道。

    Args:
        host: 学生地址。
        local_ip: 教师端地址，写进命令事务头。
        mode: 0 双方可操作、1 停止、2 仅教师操作并锁定学生输入。
        port: 本机输入端口，0 表示让系统分配。
        udp_port: 学生端 UDP 端口。
        report: 进度回调。
        cancel_event: 取消信号。

    Returns:
        RemoteControl: 已建立输入通道的对象，用完需 :meth:`RemoteControl.close`。
    """
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("操作已取消")
    control = RemoteControl(host, local_ip, mode, port, udp_port)
    control.open()
    if report:
        report("远控请求 → %s（模式 %d，输入端口 %d）" % (host, mode, control.port))
    return control


def collect_previews(
    hosts,
    duration=8.0,
    channel=1,
    teacher_name="1",
    port=4705,
    local_ip=None,
    report=None,
    cancel_event=None,
):
    """让指定学生持续上报缩略图，返回带 ``preview`` 字节的学生记录。

    学生端只有在收到 ``LPNT`` 策略包后才会推缩略图，所以先宣告再逐个下发策略。

    Args:
        hosts: 学生地址列表。
        duration: 监听时长。
        channel: 频道号。
        teacher_name: 学生端显示的教师名。
        port: 学生端 UDP 端口。
        local_ip: 组播出口地址，可省略。
        report: 进度回调。
        cancel_event: 取消信号。

    Returns:
        list[dict]: 每台学生机的记录，``preview`` 为收齐的原始图片字节。
    """
    targets = [address for address in hosts if address]
    if not targets:
        raise ValueError("请先指定目标地址")
    with TeacherSession(channel, teacher_name, port, local_ip) as session:
        session.announce(rounds=1, report=report, cancel_event=cancel_event)
        for host in targets:
            session.request_preview(host)
        session.listen(duration, report=report, cancel_event=cancel_event)
        records = []
        for host in targets:
            student = session.students.get(host)
            if student is None:
                student = {
                    "address": host,
                    "info": {},
                    "processes": [],
                    "windows": [],
                    "preview": None,
                }
            records.append(dict(student))
        return records


def view_screen(
    host,
    seconds=15.0,
    tcp_port=appcmd.TCP_COMM_PORT,
    channel=1,
    local_ip=None,
    report=None,
    cancel_event=None,
    on_record=None,
):
    """请求学生端推桌面画面，并在指定时长内持续回调收到的记录。

    Args:
        host: 学生地址。
        seconds: 观看时长。
        tcp_port: 学生端屏幕传输 TCP 端口。
        channel: 会话频道号。
        local_ip: 教师端地址，可省略。
        report: 进度回调。
        cancel_event: 取消信号。
        on_record: 每收到一条完整记录时回调，参数是解析后的记录字典。

    Returns:
        dict: ``{"records": 记录数, "latest": 最后一条记录}``。
    """
    from .screen import ScreenSession

    start_screen(host, channel, local_ip, report)
    time.sleep(0.2)
    counter = {"count": 0}

    def handle(record):
        counter["count"] += 1
        if on_record:
            on_record(record)

    session = ScreenSession(
        host, tcp_port, appcmd.DESKTOP_CHANNEL, on_record=handle, on_log=report
    )
    try:
        session.open()
        deadline = time.monotonic() + max(0.0, float(seconds))
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                break
            time.sleep(0.1)
    finally:
        session.close()
        stop_screen(host, channel, local_ip, report)
    if report:
        report("观看结束：%s，共 %d 条记录" % (host, counter["count"]))
    return {"records": counter["count"], "latest": session.latest}


__all__ = [
    "RemoteControl",
    "TeacherSession",
    "close_windows",
    "collect_previews",
    "collect_students",
    "fetch_students_info",
    "kill_processes",
    "match_entries",
    "remote_control",
    "run_app_operation",
    "send_app_command",
    "send_app_commands",
    "send_blackscreens",
    "send_lcmd_command",
    "send_mess_command",
    "send_payloads_to_logged_students",
    "send_session_broadcast",
    "send_unlocks",
    "start_screen",
    "stop_screen",
    "view_screen",
]
