"""UDP 发送、文件传送与传输结果。"""

import secrets
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic, sleep
from urllib.parse import urlsplit

from .constants import COMMAND_MAX_BYTES
from .local_info import detect_local_ip, validate_listen_ip
from .protocol import get_ip, pkg_sendlist, prepare_packets, validate_options


def send(
    send_list,
    target_ip,
    port=4705,
    loops=1,
    interval=22,
    report=None,
    cancel_event=None,
):
    """用 UDP 把报文发送到目标地址。

    Args:
        send_list: 报文字节值列表的序列，每个元素是一条报文。
        target_ip: 目标地址，支持单地址、末段范围与 /24 网段。
        port: 目标 UDP 端口。
        loops: 发送轮数。
        interval: 相邻两轮的间隔秒数。
        report: 进度回调，接收中文状态文本。
        cancel_event: 取消信号，置位后尽快抛出取消异常。

    Returns:
        int: 实际发送的报文数量。
    """
    if len(send_list) == 0:
        raise ValueError("没有可发送的报文")
    if not 1 <= port <= 65535:
        raise ValueError("端口必须在 1 到 65535 之间")
    if loops < 1:
        raise ValueError("发送轮数必须大于 0")
    if interval < 0:
        raise ValueError("发送间隔不能小于 0")

    target_host = get_ip(target_ip)
    sent_count = 0
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("操作已取消")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(1.0)
        for times in range(loops):
            for host in target_host:
                for packet_bytes in send_list:
                    if cancel_event and cancel_event.is_set():
                        raise RuntimeError("操作已取消")
                    payload = bytes(packet_bytes)
                    client.sendto(payload, (host, port))
                    sent_count += 1
            if report:
                report("第 %d/%d 轮已发送" % (times + 1, loops))
            if times != loops - 1 and interval:
                if cancel_event:
                    if cancel_event.wait(interval):
                        raise RuntimeError("操作已取消")
                else:
                    sleep(interval)
    return sent_count


def format_size(size):
    """把字节数格式化为带单位的中文界面文本。"""
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return (
                ("%d %s" % (value, unit))
                if unit == "B"
                else ("%.1f %s" % (value, unit))
            )
        value /= 1024


def validate_file_transfer(target, port, file_path):
    """校验单文件传送的目标与源文件，返回规范化后的源文件路径。"""
    if not isinstance(target, str) or not target.strip():
        raise ValueError("请填写目标地址")
    get_ip(target.strip())
    try:
        port = int(port)
    except (TypeError, ValueError) as error:
        raise ValueError("端口必须是整数") from error
    if not 1 <= port <= 65535:
        raise ValueError("端口必须在 1 到 65535 之间")
    if file_path is None or not str(file_path).strip():
        raise ValueError("请选择要传送的文件")
    source = Path(file_path).expanduser()
    try:
        if not source.exists():
            raise ValueError("文件不存在：%s" % source)
        if not source.is_file():
            raise ValueError("请选择文件，而不是文件夹")
        source.stat()
        return source.resolve()
    except OSError as error:
        raise ValueError("无法读取文件：%s" % error) from error


def _bootstrap_desktop_lines(desktop_dir=None):
    if desktop_dir is None:
        return (
            'set "DESKTOP="\r\n'
            'for /f "tokens=2,*" %%A in (\'reg query "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders" /v Desktop 2^>nul\') do set "DESKTOP=%%B"\r\n'
            'call set "DESKTOP=%DESKTOP%"\r\n'
            'if not defined DESKTOP set "DESKTOP=%USERPROFILE%\\Desktop"\r\n'
            'if not exist "%DESKTOP%" set "DESKTOP=%USERPROFILE%\\Desktop"\r\n'
        )
    return 'set "DESKTOP=%s"\r\n' % str(desktop_dir).replace("%", "%%")


def build_items_bootstrap_script(items, urls, desktop_dir=None):
    """生成下载一个或多个文件的 cmd 脚本。

    items 为 (目标相对路径, 字节数) 序列，相对路径以 / 分隔并保留顶层
    文件夹名称；urls 与 items 一一对应。脚本在目标桌面下恢复目录结构。
    """
    items = list(items)
    urls = list(urls)
    if not items:
        raise ValueError("没有要下载的文件")
    if len(items) != len(urls):
        raise ValueError("下载地址数量与文件数量不一致")
    blocks = []
    for (relative, size), url in zip(items, urls):
        relative = str(relative).replace("\\", "/").strip("/")
        parts = [part for part in relative.split("/") if part]
        if not parts:
            raise ValueError("文件相对路径无效：%s" % relative)
        windows_path = "\\".join(part.replace("%", "%%") for part in parts)
        parent_line = ""
        if len(parts) > 1:
            parent = "\\".join(part.replace("%", "%%") for part in parts[:-1])
            parent_line = (
                'if not exist "%DESKTOP%\\' + parent + '" '
                'mkdir "%DESKTOP%\\' + parent + '" >nul 2>nul\r\n'
            )
        blocks.append(
            'set "TARGET=%DESKTOP%\\'
            + windows_path
            + '"\r\n'
            + parent_line
            + 'set "PART=%TARGET%.part"\r\n'
            + 'del /f /q "%PART%" >nul 2>nul\r\n'
            + 'curl.exe -fsSL --noproxy "*" --retry 2 -o "%PART%" "'
            + str(url).replace("%", "%%")
            + '"\r\n'
            + "if errorlevel 1 goto fail\r\n"
            + 'for %%A in ("%PART%") do if not "%%~zA"=="'
            + str(int(size))
            + '" goto fail\r\n'
            + 'move /y "%PART%" "%TARGET%" >nul\r\n'
            + "if errorlevel 1 goto fail\r\n"
        )
    return (
        "@echo off\r\n"
        "chcp 65001>nul\r\n"
        "setlocal DisableDelayedExpansion\r\n"
        + _bootstrap_desktop_lines(desktop_dir)
        + "".join(blocks)
        + "exit /b 0\r\n"
        + ":fail\r\n"
        + 'del /f /q "%TARGET%.part" >nul 2>nul\r\n'
        + "exit /b 1\r\n"
    )


def build_bootstrap_script(file_url, file_name, size, desktop_dir=None):
    """生成单文件下载脚本，等价于只含一个条目的多文件脚本。"""
    return build_items_bootstrap_script([(file_name, size)], [file_url], desktop_dir)


def build_transfer_command(bootstrap_url):
    """生成让目标下载并执行传送脚本的一行 cmd 命令。

    Raises:
        ValueError: 命令超过报文容量。
    """
    command = (
        'cmd /c curl -fsSL --noproxy * -o "%%TEMP%%\\jyt.cmd" "%s" '
        '&&call "%%TEMP%%\\jyt.cmd"&del /f /q "%%TEMP%%\\jyt.cmd"'
    ) % bootstrap_url
    if len(command.encode("utf-16le")) // 2 > COMMAND_MAX_BYTES // 2:
        raise ValueError("文件传送命令超过报文容量")
    return command


def collect_transfer_items(paths):
    """把文件/文件夹选择展开为待传送文件列表。

    返回 (path, relative, size) 序列。relative 以 / 分隔，顶层为所选文件或
    文件夹名称，用于在目标桌面下恢复目录结构。重复选择的同一路径只保留一次。
    """
    if isinstance(paths, (str, Path)):
        paths = [paths]
    items = []
    seen = set()
    for raw in paths:
        if raw is None or not str(raw).strip():
            raise ValueError("请选择要传送的文件")
        path = Path(raw).expanduser()
        try:
            exists = path.exists()
            is_file = path.is_file()
        except OSError as error:
            raise ValueError("无法读取文件：%s" % error) from error
        if not exists:
            raise ValueError("文件不存在：%s" % path)
        if is_file:
            candidates = [(path, path.name)]
        elif path.is_dir():
            candidates = []
            try:
                children = sorted(path.rglob("*"))
            except OSError as error:
                raise ValueError("无法读取文件夹：%s" % error) from error
            for child in children:
                try:
                    if child.is_file():
                        candidates.append(
                            (child, child.relative_to(path.parent).as_posix())
                        )
                except OSError as error:
                    raise ValueError("无法读取文件夹：%s" % error) from error
            if not candidates:
                raise ValueError("文件夹中没有可传送的文件：%s" % path)
        else:
            raise ValueError("不支持的文件类型：%s" % path)
        for candidate, relative in candidates:
            try:
                resolved = candidate.resolve()
                size = candidate.stat().st_size
            except OSError as error:
                raise ValueError("无法读取文件：%s" % error) from error
            key = str(resolved).casefold()
            if key in seen:
                continue
            seen.add(key)
            items.append((resolved, relative, size))
    if not items:
        raise ValueError("请选择要传送的文件")
    return items


def _validate_transfer_request(target, port):
    if not isinstance(target, str) or not target.strip():
        raise ValueError("请填写目标地址")
    get_ip(target.strip())
    try:
        port = int(port)
    except (TypeError, ValueError) as error:
        raise ValueError("端口必须是整数") from error
    if not 1 <= port <= 65535:
        raise ValueError("端口必须在 1 到 65535 之间")
    return port


class _FileTransferRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format, *args):
        return

    def do_GET(self):
        transfer = self.server.transfer
        segments = [part for part in urlsplit(self.path).path.split("/") if part]
        if len(segments) >= 2 and segments[0] == "b" and segments[1] == transfer.token:
            transfer.mark_requested("script")
            body = transfer.bootstrap_script.encode("utf-8-sig")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if len(segments) >= 2 and segments[0] == "f" and segments[1] == transfer.token:
            index = 0
            if len(segments) >= 3:
                try:
                    index = int(segments[2])
                except ValueError:
                    self.send_error(404)
                    return
            transfer.mark_requested("file")
            self._send_file(transfer, index)
            return
        self.send_error(404)

    def _send_file(self, transfer, index=0):
        if not 0 <= index < len(transfer.sources):
            self.send_error(404)
            return
        source = transfer.sources[index][0]
        total = transfer.completed_before(index)
        try:
            size = source.stat().st_size
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", "attachment")
        self.end_headers()
        sent = 0
        try:
            with source.open("rb") as stream:
                while True:
                    chunk = stream.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    sent += len(chunk)
                    transfer.report_progress(total + sent, None)
        except OSError as error:
            transfer.fail("目标下载中断：%s" % error)
            return
        if sent == size:
            transfer.complete_file(index)
        else:
            transfer.fail("文件传输不完整")


class FileTransferServer:
    """临时 HTTP 文件服务：目标电脑通过它下载脚本与待传送文件。

    Attributes:
        items: (路径, 目标相对路径, 字节数) 列表。
        total_size: 全部待传送文件的总字节数。
        desktop_dir: 目标桌面目录，None 表示由脚本自行查询注册表。
        requested: 目标首次访问服务时置位，用于判断命令是否送达。
        downloaded: 传送结束（成功或失败）时置位。
        error: 传送失败原因，空字符串表示成功。
        progress: 进度回调，接收中文状态文本。
    """

    def __init__(self, source, bind_host="0.0.0.0", port=0, items=None):
        self.token = secrets.token_urlsafe(12)
        self.items = [
            (Path(path), relative, int(size)) for path, relative, size in (items or [])
        ]
        if not self.items:
            self.items = [(Path(source), Path(source).name, 0)]
        self.source = self.items[0][0]
        self.sources = [(path, relative) for path, relative, _ in self.items]
        self.total_size = sum(size for _, _, size in self.items)
        # 各文件在总进度中的起始偏移，避免每次请求都重新累加前面的文件大小。
        self._offsets = [0]
        for _, _, size in self.items:
            self._offsets.append(self._offsets[-1] + size)
        self.desktop_dir = None
        self.bootstrap_script = ""
        self.downloaded = Event()
        self.requested = Event()
        self.request_stage = ""
        self.advertised_host = ""
        self.failure_hint = ""
        self.error = ""
        self.progress = None
        self._progress_value = -1
        self._lock = Lock()
        self._served = set()
        self.httpd = ThreadingHTTPServer((bind_host, port), _FileTransferRequestHandler)
        self.httpd.transfer = self
        self.httpd.daemon_threads = True
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def port(self):
        return self.httpd.server_address[1]

    def start(self):
        self.thread.start()

    def stop(self):
        if self.thread.is_alive():
            self.httpd.shutdown()
            self.thread.join(timeout=2)
        self.httpd.server_close()

    def bootstrap_url(self, host):
        return "http://%s:%d/b/%s" % (host, self.port, self.token)

    def file_url(self, host, index=0):
        if index:
            return "http://%s:%d/f/%s/%d" % (host, self.port, self.token, index)
        return "http://%s:%d/f/%s" % (host, self.port, self.token)

    def completed_before(self, index):
        """返回第 index 个文件之前的累计字节数。"""
        return self._offsets[index]

    def mark_requested(self, stage):
        """记录目标已访问文件服务，并标记访问到哪个阶段。"""
        with self._lock:
            if stage == "file" or not self.request_stage:
                self.request_stage = stage
        self.requested.set()

    def report_progress(self, sent, total=None):
        """按 5% 粒度上报下载进度，重复进度直接丢弃。"""
        if self.progress is None:
            return
        total = self.total_size if total is None else total
        percent = 100 if total == 0 else min(100, int(sent * 100 / total))
        percent = 100 if percent == 100 else percent // 5 * 5
        # 分块下载会频繁回调，先按 5% 粒度粗筛，命中变化再进锁确认。
        if percent == self._progress_value:
            return
        with self._lock:
            if percent == self._progress_value:
                return
            self._progress_value = percent
        try:
            self.progress("目标正在下载文件：%d%%" % percent)
        except Exception:
            pass

    def complete_file(self, index=0):
        """记录一个文件下载完成，全部完成后置位 downloaded。"""
        with self._lock:
            self._served.add(index)
            finished = len(self._served) >= len(self.items)
        if finished:
            self.report_progress(self.total_size)
            self.downloaded.set()

    def complete(self):
        """标记传送成功结束。"""
        self.downloaded.set()

    def fail(self, message):
        """记录失败原因并结束等待，先到的原因保留。"""
        with self._lock:
            if not self.error:
                self.error = message
        self.downloaded.set()

    def timeout_reason(self):
        """按目标访问到的阶段给出针对性的超时提示。"""
        if self.request_stage == "file":
            return "目标已开始下载但未完成，请检查目标网络稳定性与磁盘空间后重试"
        if self.request_stage == "script":
            return (
                "目标已获取传送脚本但未下载文件，请确认目标系统 curl 可用，"
                "且目标能访问 %s:%d" % (self.advertised_host or "发送端 IP", self.port)
            )
        return (
            "目标未访问文件服务，请确认目标能访问发送端 IP %s 和临时端口 %d，"
            "本机防火墙已放行，且目标允许执行远程命令"
            % (self.advertised_host or "自动检测地址", self.port)
        )

    def wait(self, timeout=120, cancel_event=None):
        """等待目标完成下载，超时或取消时抛出带原因的异常。"""
        try:
            timeout = float(timeout)
        except (TypeError, ValueError) as error:
            raise ValueError("等待时间必须是数字") from error
        if timeout <= 0:
            raise ValueError("等待时间必须大于 0")
        deadline = monotonic() + timeout
        while not self.downloaded.is_set():
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("操作已取消")
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise RuntimeError("等待目标下载超时：%s" % self.timeout_reason())
            self.downloaded.wait(min(0.2, remaining))
        if self.error:
            raise RuntimeError(self.error)

    def bootstrap_script_for(self, host):
        """生成指向本服务的下载脚本。"""
        urls = [
            self.file_url(host, index) if index else self.file_url(host)
            for index in range(len(self.items))
        ]
        return build_items_bootstrap_script(
            [(relative, size) for _, relative, size in self.items],
            urls,
            self.desktop_dir,
        )


def normalize_transfer_items(items):
    """校验并规范化 (绝对路径, 目标相对路径) 传送条目。"""
    normalized = []
    seen = set()
    for entry in items:
        raw_path, relative = entry[0], entry[1]
        path = Path(raw_path).expanduser()
        try:
            if not path.exists():
                raise ValueError("文件不存在：%s" % path)
            if not path.is_file():
                raise ValueError("请选择文件，而不是文件夹：%s" % path)
            resolved = path.resolve()
            size = path.stat().st_size
        except OSError as error:
            raise ValueError("无法读取文件：%s" % error) from error
        relative = str(relative).replace("\\", "/").strip("/")
        if not relative:
            raise ValueError("文件相对路径无效：%s" % relative)
        key = (str(resolved).casefold(), relative.casefold())
        if key in seen:
            continue
        seen.add(key)
        normalized.append((resolved, relative, size))
    if not normalized:
        raise ValueError("请选择要传送的文件")
    return normalized


def transfer_file(
    target,
    port,
    file_path,
    listen_ip=None,
    timeout=120,
    cancel_event=None,
    report=None,
    desktop_dir=None,
    attempts=3,
    retry_delay=1.5,
    paths=None,
    items=None,
):
    """把文件传送到目标电脑桌面。

    流程：启动临时 HTTP 服务，通过 UDP 下发一行 curl 命令，目标执行后下载
    脚本与文件，最后等待目标回报完成。

    Args:
        target: 目标地址，支持单地址、末段范围与 /24 网段。
        port: 目标 UDP 端口。
        file_path: 单文件路径，``paths`` 与 ``items`` 未提供时使用。
        listen_ip: 发送端 IP，None 表示自动检测。
        timeout: 等待每个目标完成下载的秒数。
        cancel_event: 取消信号。
        report: 进度回调，接收中文状态文本。
        desktop_dir: 目标桌面目录，None 表示由脚本自行查询注册表。
        attempts: UDP 命令重试次数。
        retry_delay: 两次重试之间的间隔秒数。
        paths: 多个文件或文件夹路径。
        items: 已规范化的 (绝对路径, 目标相对路径) 条目。

    Returns:
        dict: 传送结果，包含文件名、大小、目标列表、监听地址与端口等。

    Raises:
        ValueError: 参数不合法或没有可传送的文件。
        RuntimeError: 有目标传送失败或操作被取消。
    """
    emit = report or (lambda message: None)
    port = _validate_transfer_request(target, port)
    if items is not None:
        entries = normalize_transfer_items(items)
    else:
        requested = list(paths) if paths is not None else [file_path]
        entries = collect_transfer_items(requested)
    targets = get_ip(target.strip())
    if int(attempts) < 1:
        raise ValueError("文件传送命令重试次数必须大于 0")
    if float(retry_delay) < 0:
        raise ValueError("文件传送命令重试间隔不能小于 0")
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("操作已取消")
    advertised_ip = validate_listen_ip(listen_ip) or detect_local_ip(target)
    bind_host = "127.0.0.1" if advertised_ip.startswith("127.") else "0.0.0.0"
    total_size = sum(size for _, _, size in entries)
    label = (
        Path(entries[0][0]).name if len(entries) == 1 else "%d 个文件" % len(entries)
    )
    transferred = []
    failures = []
    last_port = None
    for index, host in enumerate(targets, 1):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("操作已取消")
        transfer = FileTransferServer(
            entries[0][0],
            bind_host=bind_host,
            items=[(path, relative, size) for path, relative, size in entries],
        )
        transfer.desktop_dir = desktop_dir
        try:
            transfer.start()
            last_port = transfer.port
            transfer.advertised_host = advertised_ip
            transfer.bootstrap_script = transfer.bootstrap_script_for(advertised_ip)

            def report_target(message, index=index, host=host):
                if message.startswith("目标正在下载文件："):
                    message = "正在下载文件：" + message.split("：", 1)[1]
                emit("目标 %d/%d（%s）%s" % (index, len(targets), host, message))

            transfer.progress = report_target
            command = build_transfer_command(transfer.bootstrap_url(advertised_ip))
            packet = pkg_sendlist("-c", command)
            emit(
                "目标 %d/%d（%s）文件传送服务已启动：%s:%d，文件：%s（%s）"
                % (
                    index,
                    len(targets),
                    host,
                    advertised_ip,
                    transfer.port,
                    label,
                    format_size(total_size),
                )
            )
            # UDP 不保证可靠，单次下发可能丢包导致目标始终不下载。
            for attempt in range(1, attempts + 1):
                if cancel_event and cancel_event.is_set():
                    raise RuntimeError("操作已取消")
                emit(
                    "正在向目标 %d/%d（%s）发送文件传送命令（第 %d/%d 次）"
                    % (index, len(targets), host, attempt, attempts)
                )
                send([packet], host, port, 1, 0, emit, cancel_event)
                if transfer.requested.wait(0 if attempt == attempts else retry_delay):
                    break
            emit("等待目标 %d/%d（%s）下载到桌面" % (index, len(targets), host))
            transfer.wait(timeout, cancel_event)
            transferred.append(host)
            emit(
                "目标 %d/%d（%s）已下载文件：%s（%s）"
                % (index, len(targets), host, label, format_size(total_size))
            )
        except Exception as error:
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("操作已取消") from error
            failures.append((host, str(error)))
            emit("目标 %d/%d（%s）传送失败：%s" % (index, len(targets), host, error))
        finally:
            transfer.stop()
    if failures:
        summary = "；".join("%s（%s）" % (host, reason) for host, reason in failures)
        raise RuntimeError(
            "文件传送完成 %d/%d 个目标，失败目标：%s"
            % (len(transferred), len(targets), summary)
        )
    emit(
        "全部 %d 个目标已下载文件：%s（%s）"
        % (len(targets), label, format_size(total_size))
    )
    result = {
        "name": label,
        "size": total_size,
        "target": target,
        "targets": targets,
        "transferred": transferred,
        "listen_ip": advertised_ip,
        "port": last_port if len(targets) == 1 else None,
        "files": [relative for _, relative, _ in entries],
        "file_count": len(entries),
    }
    if len(entries) == 1:
        result["name"] = Path(entries[0][0]).name
    return result


def execute_send(options, report=None):
    """按发送参数组装并发送报文，返回发送的报文数量。"""
    validate_options(options)
    emit = report or (lambda message: None)
    packets = prepare_packets(options, emit)
    target_hosts = get_ip(options.target.strip())
    emit("目标数量：%d，报文数量：%d" % (len(target_hosts), len(packets)))
    sent_count = send(
        packets,
        options.target,
        options.port,
        options.loops,
        options.interval,
        emit,
        options.cancel_event,
    )
    emit("本机发送完成，共 %d 个报文" % sent_count)
    return sent_count
