"""教师端会话：组播宣告、登录握手与学生信息收集。

学生端只在收到教师端宣告或登录应答后才会继续通信，因此这里把「发宣告、等
握手、回会话应答、拉取学生信息」串成一个可取消的流程。套接字只在本模块创建，
报文拼装全部交给 :mod:`app.core.appcmd`。
"""

import socket
from threading import Lock
from time import monotonic, sleep

from . import appcmd
from .local_info import detect_local_ip

# 组播回环要关掉，否则本机会收到自己发出的宣告，把监听结果撑成多个条目。
_MULTICAST_TTL = 32
_RECEIVE_BUFFER = 65535
# 收包超时决定取消响应速度，取值太小会让空闲时占满 CPU。
_POLL_TIMEOUT = 0.2
# 登录后等学生端把信息回传的时间，太短会拿不到 type 5。
_INFO_WAIT = 1.2


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

    def announce(self, rounds=1, interval=1.0, report=None, cancel_event=None):
        """发送在线宣告，学生端据此发现自己并登录。

        Args:
            rounds: 发送轮数，0 表示一直发到取消。
            interval: 相邻两轮的间隔秒数。
            report: 进度回调。
            cancel_event: 取消信号。

        Returns:
            int: 实际发送的报文数量。
        """
        self.open()
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
                self._main.sendto(packet, (appcmd.MULTICAST_ADDRESS, self.port))
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

    def _register(self, host, report=None):
        """登记学生并回会话应答，返回是否为新登录。"""
        with self._lock:
            if host in self.students:
                return False
            self.students[host] = {
                "address": host,
                "info": {},
                "processes": [],
                "windows": [],
            }
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
                self._absorb(data, host)
        if report:
            report("监听结束，本次发现 %d 台学生机" % len(found))
        return found

    def _absorb(self, data, host):
        """把收到的信息上报并入对应学生记录。"""
        try:
            message = appcmd.parse_message(data)
        except ValueError:
            return
        with self._lock:
            student = self.students.setdefault(
                host, {"address": host, "info": {}, "processes": [], "windows": []}
            )
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
        channel: 通道代码，``comd``/``mess``/``session``。
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
):
    """发一轮宣告后监听，返回带信息的学生记录列表。

    Args:
        duration: 监听时长。
        channel: 频道号。
        teacher_name: 学生端显示的教师名。
        port: 学生端 UDP 端口。
        report: 进度回调。
        cancel_event: 取消信号。

    Returns:
        list[dict]: 每台学生机的地址与已收集到的信息。
    """
    with TeacherSession(channel, teacher_name, port) as session:
        session.announce(rounds=1, report=report, cancel_event=cancel_event)
        session.listen(duration, report=report, cancel_event=cancel_event)
        for host in list(session.students):
            if cancel_event is not None and cancel_event.is_set():
                break
            session.request_info(host)
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


__all__ = [
    "TeacherSession",
    "collect_students",
    "fetch_students_info",
    "run_app_operation",
    "send_app_command",
    "send_app_commands",
    "send_blackscreens",
    "send_mess_command",
    "send_session_broadcast",
    "send_unlocks",
]
