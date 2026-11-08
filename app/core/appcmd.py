"""极域应用命令、学生信息请求与教师端宣告报文。

报文格式来自对极域学生端的静态分析与实际抓包：应用命令走 ``COMD``/``LCMD``
单播到学生机的 4705 端口，学生信息与黑屏指令走 ``MESS`` 发到会话组播端点，
教师端则通过 ``OONC``/``NANC``/``CANC`` 在 4705 组播上宣告自己的存在。

本模块只负责拼装与解析字节，不碰套接字，便于单独测试。
"""

import ipaddress
import struct
import uuid

MULTICAST_ADDRESS = "224.50.50.42"
DEFAULT_PORT = 4705
SESSION_MULTICAST_PREFIX = "225.2"
SESSION_BASE_PORT = 5000
SESSION_PORT_STRIDE = 0x200
SESSION_CHANNELS = 32

TEACHER_GUID = uuid.UUID("{F96A6D19-5B29-46B9-AB95-8A143ECDDC26}")

OONC_MAGIC = 0x434E4F4F
NANC_MAGIC = 0x434E414E
CANC_MAGIC = 0x434E4143
WACA_MAGIC = 0x41434157
MESS_MAGIC = 0x5353454D
LOGI_MAGIC = 0x49474F4C
COM_MAGIC = 0x434F4D44
LCMD_MAGIC = 0x4C434D44
COM_VERSION = 0x00010000
LPNT_MAGIC = 0x544E504C
SRNT_MAGIC = 0x544E5253
TRMC_MAGIC = 0x434D5254
TRNT_MAGIC = 0x544E5254
DENT_MAGIC = 0x544E4544
LANT_MAGIC = 0x544E414C
KACA_MAGIC = 0x4143414B
ANNO_MAGIC = 0x4F4E4E41
UMSP_SELECT_MAGIC = 0x4F434853
UMSP_DATA_MAGIC = 0x43504B54
DESKTOP_H264_MAGIC = 0x46524848
DESKTOP_JPEG_MAGIC = 0x46524A48
DESKTOP_HMRF_MAGIC = 0x46524D48
INPUT_MAGIC = 0x2321347C
DESKTOP_CHANNEL = 10

APP_CATEGORY = 0x200
APP_COMMAND_CODE = 0x80000010
INFO_REQUEST_CODE = 0x100000
INFO_REPORT_CATEGORY = 0x800000
MESS_CHAT_TYPE = 0x800
TCP_COMM_PORT = 4806

CMD_CLOSE_APPS = 0x02
CMD_RENAME = 0x05
CMD_BLACKSCREEN = 0x06
CMD_LOCK_SCREEN = 0x0A
CMD_SET_PASSWORD = 0x0B
CMD_RUN = 0x0F
CMD_TERMINATE = 0x12
CMD_REBOOT = 0x13
CMD_SHUTDOWN = 0x14
CMD_EXIT_STUDENT = 0x15
CMD_OPEN_URL = 0x18
CMD_FORCE = 0x10000000

REPORT_ALL = 0
REPORT_WINDOWS = 1
REPORT_PROCESSES = 2
REPORT_CLOSE_WINDOW = 3
REPORT_KILL_PROCESS = 4

REPORT_KINDS = {
    REPORT_ALL: "全部",
    REPORT_WINDOWS: "窗口",
    REPORT_PROCESSES: "进程",
}

# 学生端按包头里的长度从 body+0xC 复制负载，会把末尾 4 字节当保留字段吃掉，
# 所以每个应用命令的 body 后面都要多补 4 个 0。
TRUNCATION_PADDING = b"\x00" * 4
# 远控鼠标动作对应学生端的窗口消息，键是小写动作名。
MOUSE_MESSAGES = {
    "move": 0x0200,
    "leftdown": 0x0201,
    "leftup": 0x0202,
    "rightdown": 0x0204,
    "rightup": 0x0205,
    "middledown": 0x0207,
    "middleup": 0x0208,
    "wheel": 0x020A,
}

# LPNT 的策略体固定 20 字节：版本、启用标志、宽、高、刷新秒数。
_LPNT_POLICY_LENGTH = 20
# 缩略图分片、桌面记录与远控输入各自的固定头长度。
_PREVIEW_HEADER_LENGTH = 48
_DESKTOP_HEADER_LENGTH = 64
_INPUT_LENGTH = 20
_MCMD_LENGTH = 53
_LPNT_GUID = bytes.fromhex("aa3a8dbe2b906645908ea29526218540")

_BLACKSCREEN_PADDING = b"\xa0\x05\x20"
_STUDENT_INFO_LENGTH = 0x2E0
_ID_NAME_MIN_LENGTH = 6


def session_endpoint(channel):
    """返回频道对应的会话组播地址与端口。

    每个频道占用一段独立的组播地址与端口，学生端登录时会发到该端点。

    Args:
        channel: 频道号，取值 1 到 32。

    Returns:
        tuple[str, int]: 组播地址与端口。

    Raises:
        ValueError: 频道号超出范围。
    """
    if not 1 <= channel <= SESSION_CHANNELS:
        raise ValueError("频道号必须在 1 到 %d 之间" % SESSION_CHANNELS)
    address = "%s.%d.1" % (SESSION_MULTICAST_PREFIX, channel + 1)
    return address, SESSION_BASE_PORT + channel * SESSION_PORT_STRIDE


def _address(value):
    """把地址文本转成 4 字节网络序，非法时抛出 ValueError。"""
    try:
        return ipaddress.IPv4Address(value).packed
    except Exception as error:
        raise ValueError("IP 格式错误：%s" % value) from error


def _name_field(teacher_name, channel):
    """把教师名编码成宣告里的名字字段，并返回频道位。

    学生端从高 16 位读名字长度、低 16 位读频道号，所以两者必须拼在同一个
    32 位字段里。
    """
    encoded = (teacher_name + "\x00").encode("utf-16-le")
    characters = len(encoded) // 2 - 1
    return (characters << 17) | channel, encoded, characters


def oonc_packet(local_ip, sequence=0):
    """构造在线宣告包 ``OONC``。

    Args:
        local_ip: 本机在教室网段的地址。
        sequence: 递增序号，学生端只用来判断宣告是否新鲜。

    Returns:
        bytes: 完整报文。
    """
    return (
        struct.pack("<II", OONC_MAGIC, COM_VERSION)
        + struct.pack("<I", 16)
        + TEACHER_GUID.bytes_le
        + _address(local_ip)
        + struct.pack("<III", 1, 1, sequence & 0xFFFFFFFF)
    )


def nanc_packet(local_ip, channel=1, teacher_name="1"):
    """构造普通频道宣告包 ``NANC``。"""
    field, name, characters = _name_field(teacher_name, channel)
    body = struct.pack("<I", field) + _address(local_ip) + name
    body = body.ljust(11 + characters * 2, b"\x00")
    return (
        struct.pack("<III", NANC_MAGIC, COM_VERSION, len(body))
        + TEACHER_GUID.bytes_le
        + body
    )


def canc_packet(local_ip, channel=1, teacher_name="1"):
    """构造自动连接宣告包 ``CANC``，学生端收到后会自动登录。

    Raises:
        ValueError: 教师名编码后超过 84 字节的负载上限。
    """
    field, name, _characters = _name_field(teacher_name, channel)
    body = (
        struct.pack("<I", field)
        + _address(local_ip)
        + struct.pack("<II", 1 << (channel - 1), 1)
        + name
    )
    if len(body) > 84:
        raise ValueError("教师名编码后超过宣告容量，请缩短名称")
    body = body.ljust(84, b"\x00")
    return (
        struct.pack("<III", CANC_MAGIC, COM_VERSION, len(body))
        + TEACHER_GUID.bytes_le
        + body
    )


def waca_packet(local_ip, channel=1):
    """构造保活包 ``WACA``。"""
    return (
        struct.pack("<III", WACA_MAGIC, COM_VERSION, 8)
        + TEACHER_GUID.bytes_le
        + _address(local_ip)
        + struct.pack("<I", channel)
    )


def mess_packet(host, payload):
    """把负载封装成发往单个学生的 ``MESS`` 报文。"""
    return struct.pack("<III", MESS_MAGIC, 1, 1) + _address(host) + payload


def session_replies(host):
    """返回登录握手要回给学生的两个 ``MESS`` 报文。

    第一个告知会话类型，第二个带上屏幕传输模式与 4806 端口，学生端收到后才
    会把上报信息发回来。
    """
    login_reply = struct.pack("<III", 0x0D, 0x1000, 0) + b"\x00"
    screen_reply = (
        struct.pack("<III", 0x1B, 0x8000, 0)
        + struct.pack("<IH", 1, TCP_COMM_PORT)
        + b"\x00" * 4
        + struct.pack("<I", 0x270034B0)
        + b"\x00"
    )
    return [mess_packet(host, login_reply), mess_packet(host, screen_reply)]


def thumbnail_packets():
    """返回登录后下发的两条缩略图策略包 ``LPNT``。

    两条都是裸 ``LPNT``，不套 ``MESS`` 头，直接发给学生端的 4705 端口。先发
    版本 2 且关闭，再发版本 3 且开启，学生端据此重启缩略图上报。
    """
    head = struct.pack("<III", LPNT_MAGIC, COM_VERSION, _LPNT_POLICY_LENGTH)
    head += bytes.fromhex("aa3a8dbe2b906645908ea29526218540")
    stopped = head + struct.pack("<IIIII", 2, 0, 80, 60, 5)
    started = head + struct.pack("<IIIII", 3, 1, 80, 60, 5)
    return [stopped, started]


def dmoc_packet(local_ip):
    """构造教师端控制信息包 ``DMOC``，登录后单播给学生。"""
    body = (
        b"\x20\x4e\x00\x00"
        + _address(local_ip)
        + b"\x35\x00\x00\x00\x35\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x80"
        + bytes.fromhex("e10202331e16e102023421160000a046000020419a99993fa0052000")
        + b"\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x3d\x00"
    )
    return (
        struct.pack("<II", COM_MAGIC, COM_VERSION)
        + struct.pack("<I", len(body))
        + bytes.fromhex("ce90fd383df5844c857fa35183c051f3")
        + body
    )


def anno_packets(local_ip):
    """返回会话通道上的两条 ``ANNO`` 宣告。

    真实教师端每 0.7 秒往会话组播补一次 ``ANNO``：第一条只声明会话类型，
    第二条带上本机地址与两个固定的服务标识。学生端据此判定教师仍然在线。

    Args:
        local_ip: 本机在教室网段的地址。

    Returns:
        list[bytes]: 两条完整报文。
    """
    marker = struct.pack("<I", 0x0D5AD030)
    brief = struct.pack("<II", ANNO_MAGIC, 1)
    detail = (
        struct.pack("<III", ANNO_MAGIC, 1, 1)
        + b"\x00" * 8
        + _address(local_ip)
        + marker
        + b"\x00" * 4
        + marker
        + struct.pack("<I", 1)
        + b"\x00" * 32
    )
    return [brief, detail]


def comd_packet(payload, magic=COM_MAGIC, command_code=APP_COMMAND_CODE, transaction=0):
    """把应用命令负载封装成 ``COMD``/``LCMD`` 报文。"""
    inner = (
        struct.pack("<I", command_code)
        + struct.pack("<I", transaction & 0xFFFFFFFF)
        + struct.pack("<I", len(payload))
        + struct.pack("<I", 0)
        + payload
    )
    return (
        struct.pack("<II", magic, COM_VERSION)
        + struct.pack("<I", len(inner))
        + TEACHER_GUID.bytes_le
        + inner
    )


def lcmd_packet(payload):
    """把应用命令负载封装成轻量 ``LCMD`` 报文。

    ``LCMD`` 与 ``COMD`` 用同一套魔数和 GUID，区别是轻量通道不带
    20000 毫秒超时与事务号，学生端也不回事务应答。

    Args:
        payload: :func:`app_payload` 生成的负载。

    Returns:
        bytes: 完整报文。
    """
    return (
        struct.pack("<II", LCMD_MAGIC, COM_VERSION)
        + struct.pack("<I", len(payload))
        + TEACHER_GUID.bytes_le
        + payload
    )


def app_payload(body):
    """给应用命令体补上类别、标志与截断补偿。"""
    return (
        struct.pack("<I", APP_CATEGORY)
        + struct.pack("<I", 0)
        + body
        + TRUNCATION_PADDING
    )


def run_program_payload(path, arguments="", show=0, fallback=1):
    """远程运行程序（cmdId 0x0F）。

    Args:
        path: 学生机上的绝对路径。
        arguments: 命令行参数。
        show: 0 正常、1 最小化、2 最大化。
        fallback: 启动失败时是否按文件名在系统目录重试。

    Returns:
        bytes: 应用命令负载。
    """
    body = struct.pack("<I", CMD_RUN) + struct.pack("<I", fallback)
    body += path.encode("utf-16-le")[:510].ljust(512, b"\x00")
    body += arguments.encode("utf-16-le")[:318].ljust(320, b"\x00")
    body += struct.pack("<I", show)
    return app_payload(body)


def normalize_url(text):
    """补全省略的协议头，返回可以直接下发的目标。

    只有看起来像域名或主机名的输入才补 ``http://``：已经带 ``://`` 的原样
    返回，本地路径（``C:\\x``、``\\\\host\\share``、``/home/x``）也保持原样，
    否则学生端的 ShellExecuteW 会把路径当成网址去打开。

    Args:
        text: 用户填写的网址或路径。

    Returns:
        str: 规范后的目标。

    Raises:
        ValueError: 输入为空。
    """
    value = str(text or "").strip()
    if not value:
        raise ValueError("请填写网址或路径")
    if "://" in value or looks_like_path(value):
        return value
    return "http://" + value


def looks_like_path(value):
    """判断输入是本地路径而不是网址。

    Args:
        value: 用户填写的目标。

    Returns:
        bool: 是路径时为 True。
    """
    if value.startswith(("\\\\", "/", "./", ".\\")):
        return True
    # Windows 盘符路径：C:\dir\a.txt 与 C:/dir/a.txt
    return len(value) > 2 and value[1] == ":" and value[2] in "\\/"


def open_url_payload(url):
    """打开网址或学生机上的文件（cmdId 0x18）。"""
    body = (
        struct.pack("<I", CMD_OPEN_URL)
        + struct.pack("<I", 0)
        + url.encode("utf-16-le")
        + b"\x00\x00"
    )
    return app_payload(body)


def terminate_payload(process_id):
    """终止指定进程（cmdId 0x12）。"""
    return app_payload(
        struct.pack("<I", CMD_TERMINATE) + struct.pack("<I", int(process_id))
    )


def exit_student_payload():
    """让学生端退出（cmdId 0x15）。"""
    return app_payload(struct.pack("<I", CMD_EXIT_STUDENT))


def close_apps_payload():
    """关闭学生机上所有应用（cmdId 0x02）。"""
    return app_payload(struct.pack("<I", CMD_CLOSE_APPS))


def rename_payload(name):
    """修改学生端的显示名（cmdId 0x05）。

    学生端把这个名字显示在教师端列表里，体格式与打开网址一致：命令号、保留
    字段、UTF-16LE 文本加双字节结束符。

    Args:
        name: 新的显示名。

    Returns:
        bytes: 应用命令负载。

    Raises:
        ValueError: 显示名为空。
    """
    value = str(name or "").strip()
    if not value:
        raise ValueError("请填写要显示的计算机名")
    body = (
        struct.pack("<I", CMD_RENAME)
        + struct.pack("<I", 0)
        + value.encode("utf-16-le")
        + b"\x00\x00"
    )
    return app_payload(body)


def lock_screen_payload(locked=True):
    """锁定或解除学生机的屏幕（cmdId 0x0A）。

    Args:
        locked: True 锁定，False 解除。

    Returns:
        bytes: 应用命令负载。
    """
    body = struct.pack("<I", CMD_LOCK_SCREEN) + struct.pack("<I", int(bool(locked)))
    return app_payload(body)


def unlock_password_payload(password):
    """设置学生机锁屏的解锁密码（cmdId 0x0B）。

    Args:
        password: 解锁密码，空字符串表示清除密码。

    Returns:
        bytes: 应用命令负载。
    """
    body = (
        struct.pack("<I", CMD_SET_PASSWORD)
        + struct.pack("<I", 0)
        + str(password or "").encode("utf-16-le")
        + b"\x00\x00"
    )
    return app_payload(body)


def blackscreen_payload(lock_input=True, timeout=10):
    """黑屏并锁定键鼠（cmdId 0x06）。

    学生端只把 ``lock_input=1`` 当作「上锁」，传 0 并不等于解锁，解锁必须发
    ``unlock_payload``。
    """
    body = (
        struct.pack("<I", CMD_BLACKSCREEN)
        + struct.pack("<I", 1 if lock_input else 0)
        + struct.pack("<I", 1)
        + struct.pack("<I", max(0, int(timeout)))
        + struct.pack("<I", 0)
        + b"\x00" * 8
    )
    return app_payload(body)


def power_payload(reboot=False, delay=0, force=True, text=""):
    """关机或重启（cmdId 0x14 / 0x13）。"""
    command = CMD_REBOOT if reboot else CMD_SHUTDOWN
    if force:
        command |= CMD_FORCE
    body = struct.pack("<I", command) + struct.pack("<I", max(0, int(delay)))
    body += b"\x00" * 8
    if text:
        body += text.encode("utf-16-le") + b"\x00\x00"
    return app_payload(body)


def blackscreen_mess_payload(
    lock_input=True, timeout=10, text="", text_color=0x0000FFFF
):
    """构造黑屏指令的 ``MESS`` 负载。

    与真机抓包逐字节一致：前 39 字节为固定头，末尾可选 UTF-16LE 提示文字。
    """
    encoded = (text.encode("utf-16-le") + b"\x00\x00") if text else b""
    total_length = 39 + len(encoded)
    payload = struct.pack("<I", total_length)
    payload += struct.pack("<I", 0x20)
    payload += struct.pack("<I", 0x80000000)
    payload += struct.pack("<I", 1 if lock_input else 0)
    payload += struct.pack("<I", 1)
    payload += struct.pack("<I", max(0, int(timeout)))
    payload += struct.pack("<I", 1 if text else 0)
    payload += struct.pack("<I", text_color)
    payload += struct.pack("<I", 0)
    payload += encoded if text else _BLACKSCREEN_PADDING
    return payload


def unlock_payload():
    """构造解除黑屏与键鼠锁的 ``MESS`` 负载。"""
    return (
        struct.pack("<I", 0x0D)
        + struct.pack("<I", 0x20)
        + struct.pack("<I", 0x90000000)
        + b"\x01"
    )


def info_request_payload(report=REPORT_ALL):
    """构造学生信息上报请求的 ``MESS`` 负载。"""
    return (
        struct.pack("<I", 16)
        + struct.pack("<I", INFO_REQUEST_CODE)
        + struct.pack("<I", 0)
        + struct.pack("<I", report)
    )


def kill_payload(process_id=None, window=None, force=True):
    """构造结束进程或关闭应用窗口的 ``MESS`` 负载。

    Args:
        process_id: 进程号，按进程结束。
        window: 窗口句柄，按窗口结束应用。
        force: 为真时强杀，否则先发 ``WM_CLOSE``。

    Raises:
        ValueError: 进程号与窗口句柄都没给。
    """
    if process_id is None and window is None:
        raise ValueError("需要进程号或窗口句柄")
    report = REPORT_KILL_PROCESS if process_id is not None else REPORT_CLOSE_WINDOW
    return (
        struct.pack("<I", 24)
        + struct.pack("<I", INFO_REQUEST_CODE)
        + struct.pack("<I", 0)
        + struct.pack("<I", report)
        + struct.pack("<I", window or 0)
        + struct.pack("<I", process_id or 0)
        + struct.pack("<I", 1 if force else 0)
    )


def chat_payload(text):
    """构造会话聊天消息的 ``MESS`` 负载（payload type ``0x800``）。

    学生端只在登录过教师会话之后才处理这类负载，所以这条消息要单播到会话
    端口。文本按 UTF-16-LE 编码并补一个结尾空字符，长度字段写的是码元数而
    不是字节数，写成字节数时学生端只显示到第一个字。

    Args:
        text: 聊天文本。

    Returns:
        bytes: 去掉 12 字节消息头之后的 ``MESS`` 负载。

    Raises:
        ValueError: 文本为空或包含 NUL 字符。
    """
    if not text:
        raise ValueError("聊天消息不能为空")
    if "\x00" in text:
        raise ValueError("聊天消息不能包含 NUL 字符")
    raw = text.encode("utf-16-le") + b"\x00\x00"
    return (
        struct.pack("<I", 16 + len(raw))
        + struct.pack("<I", MESS_CHAT_TYPE)
        + struct.pack("<I", 0)
        + struct.pack("<I", len(raw) // 2)
        + raw
    )


def _text(payload, offset, length):
    """按 UTF-16LE 读取定长字符串，截到第一个 NUL 为止。"""
    raw = payload[offset : offset + length * 2]
    return raw.decode("utf-16-le", errors="ignore").split("\x00")[0].strip()


def parse_student_info(payload):
    """解析 type 5 学生信息负载。

    Args:
        payload: 去掉 12 字节消息头后的 ``MESS`` 负载起始处。

    Returns:
        dict: 计算机名、学号、MAC、登录用户、系统、CPU 与内存。

    Raises:
        ValueError: 负载长度不足。
    """
    if len(payload) < _STUDENT_INFO_LENGTH:
        raise ValueError("学生信息负载长度不足")
    return {
        "name": _text(payload, 0x10, 32),
        "student_id": struct.unpack("<I", payload[0x50:0x54])[0],
        "mac": "-".join("%02X" % byte for byte in payload[0x54:0x5A]),
        "user": _text(payload, 0x5A, 32),
        "os": _text(payload, 0x9A, 32),
        "os_version": _text(payload, 0xDA, 64),
        "cpu_vendor": _text(payload, 0x21A, 32),
        "cpu_model": _text(payload, 0x25A, 64),
        "memory": _text(payload, 0x2DA, 16),
    }


def parse_id_name_pairs(data):
    """解析 ``{u32 id, wchar 名字}`` 序列，用于进程与窗口列表。

    学生端不给条目数量，只能按「id + 以 NUL 结尾的 UTF-16LE 字符串」逐条读到
    尾部，遇到截断就停下。

    Args:
        data: 条目区字节。

    Returns:
        list[tuple[int, str]]: ``(编号, 名字)`` 列表。
    """
    entries = []
    position, end = 0, len(data)
    while position + _ID_NAME_MIN_LENGTH <= end:
        identifier = struct.unpack("<I", data[position : position + 4])[0]
        start = position + 4
        cursor = start
        while cursor + 2 <= end and data[cursor : cursor + 2] != b"\x00\x00":
            cursor += 2
        name = data[start:cursor].decode("utf-16-le", errors="ignore").strip()
        if name:
            entries.append((identifier, name))
        position = cursor + 2
    return entries


def parse_message(data):
    """解析学生端上报的 ``MESS`` 报文。

    Args:
        data: 收到的完整报文。

    Returns:
        dict: ``kind`` 为 ``chat``、``info``、``processes``、``windows`` 或
        ``unknown``，并带上对应字段。

    Raises:
        ValueError: 报文过短或头部长度不足。
    """
    if len(data) < 12:
        raise ValueError("报文过短")
    magic, _sender, recipients = struct.unpack("<III", data[:12])
    if magic != MESS_MAGIC:
        raise ValueError("不是 MESS 报文")
    header = 12 + 4 * recipients
    if len(data) < header:
        raise ValueError("报文头长度不足")
    payload = data[header:]
    if len(payload) < 12:
        raise ValueError("负载过短")
    message_type = struct.unpack("<I", payload[4:8])[0]
    category = struct.unpack("<I", payload[8:12])[0]
    if message_type == MESS_CHAT_TYPE:
        raw = payload[16:].rstrip(b"\x00")
        if len(raw) % 2:
            raw = raw[:-1]
        return {"kind": "chat", "text": raw.decode("utf-16-le", errors="ignore")}
    subtype = struct.unpack("<I", payload[12:16])[0] if len(payload) >= 16 else 0
    if category != INFO_REPORT_CATEGORY:
        return {"kind": "unknown", "category": category, "subtype": subtype}
    if subtype == 5:
        return {"kind": "info", "info": parse_student_info(payload)}
    if subtype in (6, 7):
        first = (
            struct.unpack("<I", payload[16:20])[0] == 1 if len(payload) >= 20 else False
        )
        entries = parse_id_name_pairs(payload[20:])
        return {
            "kind": "windows" if subtype == 6 else "processes",
            "first": first,
            "entries": entries,
        }
    return {"kind": "unknown", "category": category, "subtype": subtype}


def looks_like_login(data):
    """判断收到的报文是否是学生端登录握手 ``LOGI``。"""
    return len(data) >= 4 and struct.unpack("<I", data[:4])[0] == LOGI_MAGIC


def srnt_packet(frame_sequence, complete=True, missing_parts=None):
    """构造缩略图重传应答 ``SRNT``。

    ``missing_parts`` 为 None 表示整帧都不要了，让学生端从头重发；否则按缺失
    的 1KB 分片编号请求补齐。

    Args:
        frame_sequence: 学生端给的帧序号。
        complete: 帧是否已经完整收到。
        missing_parts: 缺失的分片编号，None 表示请求整帧重发。

    Returns:
        bytes: 完整报文。
    """
    if missing_parts is None:
        body = struct.pack("<III", frame_sequence, 0, 0xFFFFFFFF)
    else:
        parts = tuple(missing_parts)
        body = struct.pack("<III", frame_sequence, int(complete), len(parts))
        if parts:
            body += struct.pack("<%dH" % len(parts), *parts)
    # 学生端的解析实现要求负载至少 14 字节，末尾两位不参与解析。
    body += b"\x00\x00"
    return struct.pack("<III", SRNT_MAGIC, COM_VERSION, len(body)) + _LPNT_GUID + body


def parse_preview_fragment(data):
    """解析 ``LANT`` 缩略图分片。

    Args:
        data: 收到的完整报文。

    Returns:
        dict: 含 ``frame``、``total``、``offset``、``payload``。

    Raises:
        ValueError: 长度不足或字段非法。
    """
    if len(data) < _PREVIEW_HEADER_LENGTH:
        raise ValueError("缩略图分片过短")
    if struct.unpack("<I", data[:4])[0] != LANT_MAGIC:
        raise ValueError("不是缩略图分片")
    frame, total, offset, length = struct.unpack("<IIII", data[32:48])
    if total <= 0 or offset >= total:
        raise ValueError("缩略图分片字段非法")
    fragment = data[48 : 48 + length]
    if not fragment:
        raise ValueError("缩略图分片没有内容")
    # 学生端偶尔会把分片长度写大，按剩余空间截断比直接丢弃更实用。
    return {
        "frame": frame,
        "total": total,
        "offset": offset,
        "payload": fragment[: total - offset],
    }


def dent_frame_sequence(data):
    """取出 ``DENT`` 里的帧序号，用于回答 ``SRNT``。"""
    if len(data) < 40:
        raise ValueError("DENT 报文过短")
    return struct.unpack("<I", data[36:40])[0]


class PreviewAssembler:
    """按帧序号重组缩略图分片。

    学生端把一张 JPEG 切成多个 ``LANT`` 分片发送，同一帧的分片可能乱序或重复，
    这里按偏移写入并按已写入的字节数判断是否收齐。
    """

    def __init__(self, max_frames=4):
        self.max_frames = max_frames
        self._frames = {}

    def feed(self, data):
        """写入一个分片，收齐时返回完整图像字节，否则返回 None。

        Args:
            data: 收到的 ``LANT`` 报文。

        Returns:
            bytes | None: 收齐的完整负载。
        """
        fragment = parse_preview_fragment(data)
        frame = fragment["frame"]
        total = fragment["total"]
        state = self._frames.get(frame)
        if state is None or state["total"] != total:
            state = {
                "total": total,
                "buffer": bytearray(total),
                "seen": bytearray(total),
                "received": 0,
            }
            self._frames[frame] = state
            while len(self._frames) > self.max_frames:
                self._frames.pop(next(iter(self._frames)))
        offset = fragment["offset"]
        payload = fragment["payload"]
        end = offset + len(payload)
        added = len(payload) - sum(state["seen"][offset:end])
        state["buffer"][offset:end] = payload
        state["seen"][offset:end] = b"\x01" * len(payload)
        state["received"] += added
        if state["received"] < total:
            return None
        self._frames.pop(frame, None)
        return bytes(state["buffer"])

    def missing_parts(self, frame):
        """返回某帧尚未收到的分片编号，帧不在重组中时返回 None。"""
        state = self._frames.get(frame)
        if state is None:
            return None
        return [
            index
            for index in range((state["total"] + 1023) // 1024)
            if not state["seen"][index * 1024]
        ]

    def reset(self):
        """丢弃所有未完成的帧。"""
        self._frames.clear()


def screen_start_payload(host, local_port, peer_port):
    """构造开始屏幕传输的 ``MESS`` 负载（feature 8，617 字节）。

    Args:
        host: 学生机地址，同时作为接收端写进参数块。
        local_port: 教师端接收端口。
        peer_port: 学生端发送端口。

    Returns:
        bytes: 617 字节的负载。
    """
    params = bytearray(604)
    struct.pack_into("<I", params, 0, 0)
    params[4:8] = _address(host)
    # 这里填的是教师侧会话端点，不是学生端的 TCP 服务端口。
    struct.pack_into("<H", params, 8, local_port & 0xFFFF)
    params[10:14] = _address(host)
    struct.pack_into("<H", params, 14, peer_port & 0xFFFF)
    struct.pack_into(
        "<IIIIIIII",
        params,
        36,
        1,  # 网络类型
        1,  # 显示控制提示
        20480,  # 最大发送速度
        1,  # 修复模式
        1440,  # 单包上限
        25,  # 帧率上限
        75,  # 采集质量
        1,  # TCP 通信模式
    )
    params[68:72] = _address(host)
    struct.pack_into("<III", params, 72, 5, 12, 16)
    payload = struct.pack("<III", 617, 8, 0x80000000) + bytes(params) + b"\x00"
    if len(payload) != 617:
        raise AssertionError("屏幕传输负载长度错误")
    return payload


def screen_stop_payload():
    """构造停止屏幕传输的 ``MESS`` 负载。"""
    return struct.pack("<III", 13, 0, 0) + b"\x00"


def umsp_hello_payload(channel=10):
    """构造 UMSP 建链包 ``SHCO``，订阅指定频道。"""
    return struct.pack("<IIIII", COM_VERSION, UMSP_SELECT_MAGIC, 8, 1, channel)


def parse_umsp_header(data):
    """解析 UMSP 报文头，返回 (magic, 负载)。

    Raises:
        ValueError: 长度不足 12 字节。
    """
    if len(data) < 12:
        raise ValueError("UMSP 报文过短")
    version, magic, length = struct.unpack("<III", data[:12])
    if version != COM_VERSION:
        raise ValueError("UMSP 版本不匹配：%#x" % version)
    return magic, data[12 : 12 + length]


def parse_desktop_fragment(data):
    """解析 UMSP 里的桌面分片，返回 (帧序号, 偏移, 总长, 分片)。"""
    if len(data) < 12:
        raise ValueError("桌面分片过短")
    frame, offset, total = struct.unpack("<III", data[:12])
    if total <= 0 or offset > total or len(data) - 12 > total - offset:
        raise ValueError("桌面分片字段非法")
    return frame, offset, total, data[12:]


def parse_desktop_record(record):
    """解析一帧完整的桌面记录。

    Args:
        record: 重组后的记录字节。

    Returns:
        dict: ``kind`` 为 ``h264``/``jpeg``/``cursor``/``unknown``，附带尺寸与负载。
    """
    if len(record) < _DESKTOP_HEADER_LENGTH:
        if len(record) >= 16 and record[:4] == b"SPUC":
            _size, timestamp, packed = struct.unpack_from("<III", record, 4)
            return {
                "kind": "cursor",
                "x": packed & 0xFFFF,
                "y": (packed >> 16) & 0xFFFF,
                "timestamp": timestamp,
            }
        return {"kind": "unknown", "payload": record}
    magic, _size, timestamp = struct.unpack("<III", record[:12])
    encoded = struct.unpack("<iiii", record[12:28])
    visible = struct.unpack("<iiii", record[28:44])
    frame_type = struct.unpack("<I", record[44:48])[0]
    payload = record[_DESKTOP_HEADER_LENGTH:]
    width = abs(encoded[2] - encoded[0]) or abs(visible[2] - visible[0])
    height = abs(encoded[3] - encoded[1]) or abs(visible[3] - visible[1])
    result = {
        "width": width,
        "height": height,
        "frame_type": frame_type,
        "timestamp": timestamp,
        "payload": payload,
        "magic": magic,
    }
    if magic == DESKTOP_H264_MAGIC:
        result["kind"] = "h264"
    elif magic == DESKTOP_JPEG_MAGIC:
        start = payload.find(b"\xff\xd8")
        result["kind"] = "jpeg"
        result["payload"] = payload[start:] if start >= 0 else payload
    elif magic == DESKTOP_HMRF_MAGIC:
        result["kind"] = "unknown"
    else:
        result["kind"] = "unknown"
    return result


def remote_control_payload(mode=2, port=0):
    """构造远控请求负载 ``MCMD``。

    Args:
        mode: 0 双方可操作、1 停止、2 仅教师操作并锁定学生输入。
        port: 学生端回传输入的 UDP 端口。
    """
    payload = bytearray(_MCMD_LENGTH)
    struct.pack_into("<III", payload, 0, _MCMD_LENGTH, 8, 0)
    payload[12:16] = b"MCMD"
    struct.pack_into("<I", payload, 16, mode)
    payload[20:24] = _address("0.0.0.0")
    struct.pack_into("<H", payload, 24, port & 0xFFFF)
    return bytes(payload)


def remote_control_payload_for(host, mode=2, port=0):
    """构造带目标地址的 ``MCMD`` 负载。"""
    payload = bytearray(remote_control_payload(mode, port))
    payload[20:24] = _address(host)
    return bytes(payload)


def input_packet(kind, payload):
    """把 20 字节的输入负载封成远控 UDP 报文。

    Args:
        kind: 1 鼠标、16 键盘。
        payload: 20 字节输入负载。

    Returns:
        bytes: 完整报文。
    """
    if len(payload) != _INPUT_LENGTH:
        raise ValueError("输入负载必须是 %d 字节" % _INPUT_LENGTH)
    return struct.pack("<II", INPUT_MAGIC, kind) + payload


def mouse_input_payload(action, x, y, data=0, swapped=0):
    """构造鼠标输入负载，坐标为 0..65535 的归一化值。"""
    try:
        message = MOUSE_MESSAGES[action.lower()]
    except KeyError as error:
        raise ValueError("未知鼠标动作：%s" % action) from error
    if not (0 <= x <= 0xFFFF and 0 <= y <= 0xFFFF):
        raise ValueError("鼠标坐标必须在 0 到 65535 之间")
    return struct.pack("<IIIII", message, x, y, data & 0xFFFFFFFF, swapped & 0xFFFFFFFF)


def key_input_payload(scan_code, virtual_key, key_up=False, extended=False):
    """构造键盘输入负载。"""
    if not (0 <= virtual_key <= 0xFFFF and 0 <= scan_code <= 0xFFFF):
        raise ValueError("键码必须在 0 到 65535 之间")
    flags = (1 if extended else 0) | (0x80 if key_up else 0)
    return struct.pack("<HHI", scan_code, virtual_key, flags) + bytes(12)


def command_transaction_packet(payload, local_ip):
    """把 ``MCMD`` 负载封成 ``COMD`` 命令事务。

    远控请求走的是命令事务而不是应用命令，外层结构与 :func:`comd_packet`
    不同：事务头带 16 字节事务号与发送方地址。

    Args:
        payload: ``MCMD`` 负载。
        local_ip: 教师端地址，写进事务头。

    Returns:
        bytes: 完整报文。

    Raises:
        ValueError: 负载超过 2048 字节。
    """
    if len(payload) > 0x800:
        raise ValueError("命令事务负载不能超过 2048 字节")
    return (
        struct.pack("<III", COM_MAGIC, COM_VERSION, len(payload) + 13)
        + uuid.uuid4().bytes_le
        + struct.pack("<I", 20000)
        + _address(local_ip)
        + struct.pack("<I", len(payload))
        + payload
        + b"\x00"
    )
