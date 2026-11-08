"""启停本机极域学生端进程，需要管理员权限时按需提权。

模拟教师端和学生端同时跑在一台电脑上时，学生端会独占教师端地址的 4705
端口，把学生回包全部收走，所以需要能一键结束它；测试结束后又要能把它重新
拉起来恢复课堂管理。

定位与结束的思路参考 JiYuTrainer：先按运行中的进程取路径，再读卸载信息里的
``DisplayIcon``，最后试常见安装目录；判断一个 ``StudentMain.exe`` 是不是真身，
看它同目录下有没有 ``LibTDMaster.dll``。结束时先请求正常退出，再强制结束，
最后才通过 UAC 助手提权，避免为了关一个进程就弹窗。
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path

from .firewall import _is_admin, _run_elevated_process, run_windows_command

# 提权助手进程的入口参数，由 ``app/__main__.py`` 转发给本模块。
STUDENT_HELPER_ARGUMENT = "--student-helper"

STUDENT_RESULT_ARGUMENT = "--student-result"

# 映像名里带这个片段的都算学生端，极域各版本分别叫 StudentMain.exe 与
# StudentMain64.exe，统一按片段匹配比写死两个名字更稳。
STUDENT_NAME_MARKER = "student"

# 学生端主程序的文件名，各版本与安装方式的差异都在这里列出。
STUDENT_EXECUTABLE_NAMES = (
    "StudentMain.exe",
    "StudentMain64.exe",
    "Student.exe",
)

# 真身标志：极域学生端目录里一定有这个库，别的软件同名进程没有。
STUDENT_LIBRARY = "LibTDMaster.dll"

# 卸载信息里的固定键名，JiYuTrainer 也是先读这里。
STUDENT_UNINSTALL_KEY = "e-Learning Class V6.0"

# 常见安装目录，注册表查不到时按顺序探测。
# 路径用 chr(92) 拼，避免源码里满屏反斜杠转义。
SEP = chr(92)
STUDENT_DIRECTORIES = (
    tuple(
        SEP.join(parts)
        for parts in (
            ["C:", "Program Files", "Mythware", "e-Learning Class"],
            ["C:", "Program Files (x86)", "Mythware", "e-Learning Class"],
            ["C:", "Program Files", "Mythware", "多媒体教学管理系统V6.0 2016 豪华版"],
            [
                "C:",
                "Program Files (x86)",
                "Mythware",
                "多媒体教学管理系统V6.0 2016 豪华版",
            ],
            ["C:", "e-Learning Class"],
            ["C:", "多媒体教学管理系统V6.0 2016 豪华版"],
        )
    )
    + tuple(
        SEP.join(["C:", "Program Files", folder, "e-Learning Class Standard", "1.00"])
        for folder in ("TopDomain", "Mythware", "JiYu")
    )
    + tuple(
        SEP.join(
            ["C:", "Program Files (x86)", folder, "e-Learning Class Standard", "1.00"]
        )
        for folder in ("TopDomain", "Mythware", "JiYu")
    )
)

# 启动后等待学生端进程出现的上限，超时只是提示，不代表启动失败。
START_TIMEOUT = 5.0

# 请求正常退出后等这么久，超时就强制结束；强制结束后的等待时间同理。
GRACEFUL_TIMEOUT = 1.5

FORCED_TIMEOUT = 2.5

# 轮询进程列表的间隔。
POLL_INTERVAL = 0.25


def _process_rows():
    """读取 tasklist 的进程列表，返回 ``(进程号, 映像名)`` 列表。

    Raises:
        RuntimeError: 进程列表查询失败。
    """
    process = run_windows_command(["tasklist", "/FO", "CSV", "/NH"])
    if process.returncode:
        raise RuntimeError(process.stderr.strip() or "进程列表查询失败")
    rows = []
    for line in process.stdout.splitlines():
        fields = [field.strip('"') for field in line.split('","')]
        if len(fields) < 2:
            continue
        name, pid = fields[0].strip('"'), fields[1].strip('"')
        if pid.isdigit():
            rows.append((int(pid), name))
    return rows


def _listening_ports(pids):
    """按进程号收集它们监听的 UDP 与 TCP 端口。"""
    wanted = {str(pid) for pid in pids}
    ports = {}
    for protocol in ("UDP", "TCP"):
        process = run_windows_command(["netstat", "-ano", "-p", protocol])
        if process.returncode:
            continue
        for line in process.stdout.splitlines():
            fields = line.split()
            if len(fields) < 4 or fields[0] != protocol:
                continue
            if fields[-1] not in wanted:
                continue
            port = fields[1].rsplit(":", 1)[-1]
            if port.isdigit():
                ports.setdefault(int(fields[-1]), set()).add(int(port))
    return ports


def _process_paths(pids):
    """按进程号取可执行文件路径，取不到的进程不出现在结果里。

    普通权限读不到 SYSTEM 进程的路径，这时返回空字典，调用方按“路径未知”处理。
    """
    if not pids:
        return {}
    ids = ",".join(str(pid) for pid in pids)
    command = (
        "Get-Process -Id %s -ErrorAction SilentlyContinue | "
        'ForEach-Object { "$($_.Id)|$($_.Path)" }' % ids
    )
    process = run_windows_command(["powershell", "-NoProfile", "-Command", command])
    if process.returncode:
        return {}
    paths = {}
    for line in process.stdout.splitlines():
        pid, _, path = line.strip().partition("|")
        if pid.isdigit() and path.strip():
            paths[int(pid)] = path.strip()
    return paths


def _is_genuine(path):
    """判断路径是否位于真正的学生端目录：同目录必须有 ``LibTDMaster.dll``。"""
    if not path:
        return False
    with suppress(OSError):
        return (Path(path).parent / STUDENT_LIBRARY).is_file()
    return False


def find_student_processes():
    """列出本机正在运行的学生端进程。

    Returns:
        list[dict]: 每项含 ``pid``、``name``、按端口号升序的 ``ports``、
        ``path``（读不到时为空字符串）与 ``genuine``（同目录有
        ``LibTDMaster.dll`` 时为 True）。

    Raises:
        RuntimeError: 进程列表查询失败。
    """
    rows = [
        (pid, name)
        for pid, name in _process_rows()
        if STUDENT_NAME_MARKER in name.casefold()
    ]
    if not rows:
        return []
    pids = [pid for pid, _name in rows]
    ports = _listening_ports(pids)
    paths = _process_paths(pids)
    return [
        {
            "pid": pid,
            "name": name,
            "ports": sorted(ports.get(pid, set())),
            "path": paths.get(pid, ""),
            "genuine": _is_genuine(paths.get(pid, "")),
        }
        for pid, name in rows
    ]


def _pid_alive(pid):
    """用 tasklist 判断指定进程是否还在，避免依赖退出码误判。"""
    process = run_windows_command(["tasklist", "/FI", "PID eq %d" % pid, "/NH"])
    return process.returncode == 0 and str(pid) in process.stdout


def _wait_gone(pid, timeout):
    """在超时时间内轮询等待进程消失，返回是否已经不在。"""
    deadline = time.monotonic() + timeout
    while True:
        if not _pid_alive(pid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_INTERVAL)


def _taskkill(pid, force):
    """用 taskkill 结束进程，先正常请求退出，失败再强制。

    Args:
        pid: 进程号。
        force: True 时直接强制结束。

    Returns:
        dict: 含 ``pid``、``code``、``output``、``success`` 与 ``forced``。
    """
    command = ["taskkill", "/PID", str(pid)]
    if force:
        command.append("/F")
    process = run_windows_command(command)
    output = (process.stdout.strip() or process.stderr.strip()).strip()
    # 128 表示进程已经不在了，按成功处理，免得重复操作时报错。
    success = process.returncode in (0, 128)
    if process.returncode == 128:
        output = "进程已经退出"
    return {
        "pid": pid,
        "code": process.returncode,
        "output": output,
        "success": success,
        "forced": force,
    }


def _terminate(pid):
    """结束单个进程：先请它正常退出，等不到才强制结束。

    极域学生端没有窗口也不处理关闭消息，``taskkill`` 不加 ``/F`` 同样返回
    成功，但进程其实还在跑，所以每一步都要以“进程是否真的消失”为准。
    """
    outcome = _taskkill(pid, force=False)
    if _wait_gone(pid, GRACEFUL_TIMEOUT):
        outcome["gone"] = True
        return outcome
    forced = _taskkill(pid, force=True)
    gone = _wait_gone(pid, FORCED_TIMEOUT)
    forced["gone"] = gone
    forced["success"] = gone
    if not gone:
        reason = forced["output"] or outcome["output"] or "进程仍在运行"
        hint = "进程仍在运行"
        if "拒绝访问" in reason:
            hint = "拒绝访问，需要管理员权限"
        forced["output"] = "%s（%s）" % (reason, hint)
    return forced


def _run_student_elevated(target):
    """通过 UAC 启动助手进程结束或启动学生端，返回助手回传的结果。"""
    handle, result_path = tempfile.mkstemp(prefix="jiyu-student-", suffix=".json")
    os.close(handle)
    try:
        arguments = [
            STUDENT_HELPER_ARGUMENT,
            target,
            STUDENT_RESULT_ARGUMENT,
            result_path,
        ]
        directory = None
        if not getattr(sys, "frozen", False):
            # 源码运行时助手必须走 -m app 统一入口，并把仓库根目录设为工作目录，
            # 否则相对导入失败，助手什么都没干就退出，表现为“没有成功杀掉”。
            arguments = ["-m", "app", *arguments]
            directory = str(Path(__file__).resolve().parents[2])
        exit_code = _run_elevated_process(
            sys.executable,
            subprocess.list2cmdline(arguments),
            directory=directory,
            action="结束或启动学生端",
        )
        try:
            payload = json.loads(Path(result_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError(
                "管理员权限进程未返回结果（助手退出码 %d），可能是授权被取消、"
                "被安全软件拦截或程序路径含中文" % exit_code
            ) from error
        if payload.get("error"):
            raise RuntimeError(payload["error"])
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            raise RuntimeError("管理员权限进程返回的结果无效")
        if exit_code and not any(item.get("success") for item in results):
            raise RuntimeError("管理员权限操作失败（退出码 %d）" % exit_code)
        return results
    finally:
        with suppress(OSError):
            os.unlink(result_path)


def _elevated_stop(pids):
    """提权结束一批进程，返回助手回传的结果。"""
    return _run_student_elevated(",".join(str(pid) for pid in pids))


def _elevated_start(exe_path):
    """提权启动学生端，返回助手回传的结果。"""
    return _run_student_elevated("start=" + str(exe_path))


def stop_student_processes(pids=None, report=None):
    """结束指定进程；不指定时结束本机全部学生端进程。

    每个进程先请求正常退出，失败再强制结束；仍然失败且当前不是管理员时，
    把剩下的进程交给 UAC 助手一次性处理。

    Args:
        pids: 进程号序列，None 表示自动查找学生端。
        report: 可选的进度回调，供后台任务把提示写到界面。

    Returns:
        list[dict]: 每个进程的执行结果，含 ``pid``、``code``、``output``、
        ``success``、``forced``，以及结束后的 ``gone``。

    Raises:
        RuntimeError: 找不到学生端、提权被取消或提权进程未回传结果。
        ValueError: 进程号不合法。
    """
    if pids is None:
        targets = [item["pid"] for item in find_student_processes()]
    else:
        targets = []
        for value in pids:
            if not str(value).strip().isdigit():
                raise ValueError("进程号必须是数字")
            targets.append(int(str(value).strip()))
    if not targets:
        raise RuntimeError("本机没有正在运行的学生端进程")
    if report:
        report("正在结束 %d 个学生端进程…" % len(targets))
    results = []
    for pid in targets:
        outcome = _terminate(pid)
        results.append(outcome)
        if not outcome["success"] and report:
            report("PID %d 结束失败，可能需要管理员权限" % pid)
    pending = [item["pid"] for item in results if not item["success"]]
    can_elevate = sys.platform == "win32"
    if pending and can_elevate and not _is_admin():
        if report:
            report("正在请求管理员权限结束剩余的 %d 个进程…" % len(pending))
        elevated = {item["pid"]: item for item in _elevated_stop(pending)}
        results = [elevated.get(item["pid"], item) for item in results]
    alive = {item["pid"] for item in results if _pid_alive(item["pid"])}
    for item in results:
        item["gone"] = item["pid"] not in alive
        if item["gone"]:
            item["success"] = True
    remaining = find_student_processes()
    # 极域的服务端会看住学生端，结束之后可能立刻被重新拉起，这时必须说清楚，
    # 否则用户只会看到“进程又回来了”，不知道是守护进程干的。
    respawned = [item for item in remaining if item["pid"] not in targets]
    for item in respawned:
        results.append(
            {
                "pid": item["pid"],
                "code": 0,
                "output": "学生端被极域守护服务重新拉起（PID %d），"
                "需要先停止该服务再结束进程" % item["pid"],
                "success": False,
                "forced": False,
                "gone": False,
                "respawned": True,
            }
        )
    return results


def _registry_paths():
    """拼出精确键与通配键的 PowerShell 路径参数，避免源码里写反斜杠转义。"""
    sep = chr(92)
    base = ["SOFTWARE", "Microsoft", "Windows", "CurrentVersion", "Uninstall"]
    exact = [*base, STUDENT_UNINSTALL_KEY]
    wow = ["SOFTWARE", "WOW6432Node", *base[1:], STUDENT_UNINSTALL_KEY]
    wildcard = [*base, "*"]
    wildcard_wow = ["SOFTWARE", "WOW6432Node", *base[1:], "*"]
    return {
        "exact": ["HKLM:" + sep.join(exact), "HKLM:" + sep.join(wow)],
        "wildcard": ["HKLM:" + sep.join(wildcard), "HKLM:" + sep.join(wildcard_wow)],
    }


def _service_directories():
    """从极域相关服务的可执行路径推出安装目录。

    服务端组件（如 ``GATESRV.exe``）和学生端装在同一目录，注册表里查不到时
    用这条线索最可靠；有些机器把学生端装在非系统盘的自定义目录。
    """
    script = (
        "Get-CimInstance Win32_Service | "
        "Where-Object { $_.PathName -match "
        "'Mythware|TopDomain|Student|e-Learning|JiYu' } | "
        "ForEach-Object { $_.PathName }"
    )
    try:
        process = run_windows_command(["powershell", "-NoProfile", "-Command", script])
    except (OSError, RuntimeError):
        return []
    if process.returncode != 0:
        return []
    directories = []
    for line in process.stdout.splitlines():
        text = line.strip().strip('"')
        if not text:
            continue
        quoted = text.startswith('"')
        candidate = (
            text.split('"')[1] if quoted and '"' in text[1:] else text.split()[0]
        )
        parent = Path(candidate.strip('"')).parent
        if str(parent) not in directories:
            directories.append(str(parent))
    return directories


def _clean_icon(value):
    """卸载信息里的 ``DisplayIcon`` 常带引号和图标序号，这里还原成纯路径。"""
    text = str(value or "").strip().strip('"')
    if text.endswith(",0"):
        text = text[:-2]
    return text.strip().strip('"')


def _uninstall_icon():
    """读卸载信息里的 ``DisplayIcon``，找不到时返回空列表。"""
    paths = _registry_paths()["exact"]
    quoted = ",".join("'%s'" % item for item in paths)
    command = (
        "Get-ItemProperty -Path %s -ErrorAction SilentlyContinue | "
        "ForEach-Object { $_.DisplayIcon }" % quoted
    )
    process = run_windows_command(["powershell", "-NoProfile", "-Command", command])
    if process.returncode:
        return []
    return [_clean_icon(line) for line in process.stdout.splitlines() if line.strip()]


def _registered_directories():
    """从卸载信息里找学生端安装目录，找不到时返回空列表。"""
    paths = _registry_paths()["wildcard"]
    quoted = ",".join("'%s'" % item for item in paths)
    command = (
        "Get-ItemProperty -Path %s -ErrorAction SilentlyContinue | "
        "Where-Object { $_.DisplayName -match "
        "'Student|e-Learning|Mythware|TopDomain|极域' } | "
        "ForEach-Object { $_.InstallLocation } | Where-Object { $_ }" % quoted
    )
    process = run_windows_command(["powershell", "-NoProfile", "-Command", command])
    if process.returncode:
        return []
    return [line.strip() for line in process.stdout.splitlines() if line.strip()]


def _executable_in(directory):
    """在一个目录里按已知文件名找主程序，找不到返回 None。"""
    for name in STUDENT_EXECUTABLE_NAMES:
        candidate = Path(directory) / name
        if candidate.is_file():
            # 目录可能来自 netstat 之类的相对来源，统一返回绝对路径。
            return str(candidate.resolve())
    return None


def find_student_executable(explicit=None):
    """定位本机学生端主程序。

    顺序参考 JiYuTrainer：手动指定 → 正在运行的进程 → 卸载信息里的
    ``DisplayIcon`` → 卸载信息里的安装目录 → 极域服务所在目录 → 常见安装
    目录。多个候选时优先同目录带 ``LibTDMaster.dll`` 的真身。

    Args:
        explicit: 手动指定的路径，None 表示自动查找。

    Returns:
        str: 可执行文件的完整路径。

    Raises:
        RuntimeError: 没有找到安装位置。
    """
    if explicit:
        target = Path(str(explicit)).expanduser()
        if target.is_file():
            return str(target.resolve())
        raise RuntimeError("指定的学生端程序不存在：%s" % target)
    running = [item["path"] for item in find_student_processes() if item.get("path")]
    for path in running:
        if _is_genuine(path):
            return path
    candidates = list(running)
    candidates.extend(_uninstall_icon())
    for directory in _registered_directories():
        found = _executable_in(directory)
        if found:
            candidates.append(found)
    for directory in _service_directories():
        found = _executable_in(directory)
        if found:
            candidates.append(found)
    for directory in STUDENT_DIRECTORIES:
        found = _executable_in(directory)
        if found:
            candidates.append(found)
    for path in candidates:
        if Path(path).is_file():
            return path
    raise RuntimeError(
        "没有找到学生端安装位置，可以用 --exe 指定 StudentMain.exe 的完整路径"
    )


def _spawn(exe_path):
    """以独立进程启动学生端，返回启动结果。"""
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    try:
        process = subprocess.Popen(
            [str(exe_path)],
            cwd=str(Path(exe_path).parent),
            creationflags=flags,
            close_fds=True,
        )
    except OSError as error:
        return {
            "path": str(exe_path),
            "pid": 0,
            "code": 1,
            "output": str(error),
            "success": False,
            "forced": False,
        }
    return {
        "path": str(exe_path),
        "pid": process.pid,
        "code": 0,
        "output": "已启动",
        "success": True,
        "forced": False,
    }


def _wait_for_start(before, timeout=START_TIMEOUT):
    """等待学生端进程出现，返回新出现的进程记录，超时返回空字典。"""
    known = {item["pid"] for item in before}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL)
        with suppress(RuntimeError, OSError):
            fresh = [
                item for item in find_student_processes() if item["pid"] not in known
            ]
            if fresh:
                return fresh[0]
    return {}


def start_student_process(exe_path=None, report=None):
    """启动本机学生端，并确认进程真的起来了。

    Args:
        exe_path: 学生端主程序路径，None 表示自动查找。
        report: 可选的进度回调，供后台任务把提示写到界面。

    Returns:
        list[dict]: 启动结果，含 ``path``、``pid``、``code``、``output``、
        ``success`` 与 ``confirmed``。

    Raises:
        RuntimeError: 找不到学生端、已经有实例在跑、提权被取消或提权进程
            没有回传结果。
    """
    before = find_student_processes()
    if before:
        raise RuntimeError("本机已经有学生端在运行，先结束再启动")
    resolved = find_student_executable(exe_path)
    if report:
        report("正在启动学生端：%s" % resolved)
    if sys.platform == "win32" and not _is_admin():
        results = _elevated_start(resolved)
    else:
        results = [_spawn(resolved)]
    started = _wait_for_start(before)
    for item in results:
        item["confirmed"] = bool(started)
        if started:
            item["pid"] = started["pid"]
            item["output"] = "已启动，进程号 %d" % started["pid"]
            item["success"] = True
        elif item.get("success"):
            # 进程已经拉起但列表还没看到，按启动成功但未确认处理。
            item["output"] = "已请求启动，但没有检测到学生端进程"
    if report and started:
        report("学生端已启动，进程号 %d" % started["pid"])
    return results


def toggle_student_process(exe_path=None, report=None):
    """按当前状态启动或结束学生端，供界面的单个按钮与命令行的默认动作使用。

    Args:
        exe_path: 启动时使用的路径，None 表示自动查找。
        report: 可选的进度回调。

    Returns:
        dict: ``action`` 为 ``"start"`` 或 ``"stop"``，``results`` 是核心操作
        的返回值，``processes`` 是操作前的进程列表。
    """
    processes = find_student_processes()
    if processes:
        return {
            "action": "stop",
            "processes": processes,
            "results": stop_student_processes(
                [item["pid"] for item in processes], report=report
            ),
        }
    return {
        "action": "start",
        "processes": processes,
        "results": start_student_process(exe_path, report=report),
    }


def run_student_helper(arguments):
    """在提权后的助手进程里启动或结束学生端，并把结果写成 JSON 回传给主进程。

    Args:
        arguments: 形如 ``[进程号列表, STUDENT_RESULT_ARGUMENT, 结果文件路径]``，
            或 ``["start=程序路径", STUDENT_RESULT_ARGUMENT, 结果文件路径]``。

    Returns:
        int: 0 表示全部成功，1 表示有进程失败，2 表示参数不合法。
    """
    if len(arguments) != 3 or arguments[1] != STUDENT_RESULT_ARGUMENT:
        return 2
    target, result_path = arguments[0], arguments[2]
    if target.startswith("start="):
        results = [_spawn(target[len("start=") :])]
    else:
        try:
            targets = [int(value) for value in target.split(",") if value.strip()]
        except ValueError:
            return 2
        if not targets:
            return 2
        results = [_terminate(pid) for pid in targets]
    try:
        Path(result_path).write_text(
            json.dumps({"results": results}, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        return 1
    return 0 if all(item["success"] for item in results) else 1
