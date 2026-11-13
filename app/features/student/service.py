"""启停本机极域学生端进程，需要管理员权限时按需提权。

模拟教师端和学生端同时跑在一台电脑上时，学生端会独占教师端地址的 4705
端口，把学生回包全部收走，所以需要能一键结束它；测试结束后又要能把它重新
拉起来恢复课堂管理。

定位与结束的思路参考 JiYuTrainer：

- 定位：手工指定或设置里记住的路径 → 运行中的真身进程（同目录带
  ``LibTDMaster.dll``）→ 卸载信息里的 ``DisplayIcon`` → 卸载信息里的
  ``InstallLocation`` → 极域服务（如 ``GATESRV.exe``）所在目录 → 常见
  安装目录。
- 识别：映像名带 ``student``，同目录有 ``LibTDMaster.dll`` 才认定为真身，
  其余同名进程只标记、不默认处理。
- 结束：先发 ``WM_CLOSE`` 请它自己退出，再按创建时间校验后强制结束，仍被
  拒绝才通过 UAC 助手提权，最后观察是否有守护服务把它重新拉起。

与 JiYuTrainer 用内核驱动强杀不同，这里只用系统提供的能力：驱动需要签名、
加载失败会蓝屏，测试工具不值得为此扩大权限。
"""

import json
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

from app.features.settings.service import portable_settings
from app.features.student.data import (
    FORCED_TIMEOUT,
    GRACEFUL_TIMEOUT,
    GUARDIAN_MARKERS,
    POLL_INTERVAL,
    RESPAWN_WINDOW,
    START_TIMEOUT,
    STUDENT_DIRECTORIES,
    STUDENT_EXE_SETTINGS_KEY,
    STUDENT_EXECUTABLE_NAMES,
    STUDENT_HELPER_ARGUMENT,
    STUDENT_LIBRARY,
    STUDENT_NAME_MARKER,
    STUDENT_PORT,
    STUDENT_RESULT_ARGUMENT,
    normalize_executable_path,
    registry_paths,
)
from app.system.windows.command import run_windows_command
from app.system.windows.elevation import _is_admin, run_elevated_helper
from app.system.windows.ports import listening_ports
from app.system.windows.process import (
    close_main_windows,
    is_process_alive,
    list_processes,
    process_creation_time,
    process_rows,
    terminate_process,
)

__all__ = [
    "STUDENT_HELPER_ARGUMENT",
    "find_student_executable",
    "find_student_processes",
    "run_student_helper",
    "save_executable",
    "start_student_process",
    "stop_student_processes",
    "student_status",
    "toggle_student_process",
]


def _rows():
    """枚举进程；直接枚举失败时退回 ``tasklist``，两条路都失败才报错。

    Raises:
        RuntimeError: 两种枚举方式都不可用。
    """
    try:
        return list_processes()
    except (OSError, RuntimeError):
        pass
    process = run_windows_command(["tasklist", "/FO", "CSV", "/NH"])
    if process.returncode:
        raise RuntimeError(process.stderr.strip() or "进程列表查询失败")
    return [
        {"pid": int(pid), "name": name, "path": ""}
        for name, pid in process_rows(process.stdout)
    ]


def _is_student_name(name):
    """映像名里带 ``student`` 的都算候选，极域各版本命名不同。"""
    return STUDENT_NAME_MARKER in str(name or "").casefold()


def _is_genuine(path):
    """判断路径是否位于真正的学生端目录：同目录必须有 ``LibTDMaster.dll``。"""
    if not path:
        return False
    with suppress(OSError):
        return (Path(path).parent / STUDENT_LIBRARY).is_file()
    return False


def _describe(row, ports):
    """把一条进程记录补成界面与命令行共用的结构。"""
    path = row.get("path") or ""
    return {
        "pid": row["pid"],
        "name": row.get("name") or STUDENT_EXECUTABLE_NAMES[0],
        "ports": sorted(ports.get(row["pid"], set())),
        "path": path,
        "genuine": _is_genuine(path),
        "creation": row.get("creation") or process_creation_time(row["pid"]),
    }


def _candidates(rows):
    """从进程快照里挑出学生端候选。

    只认映像名带 ``student`` 或名字正是已知主程序之一的进程。极域安装目录
    下还有 ``DispcapHelper.exe``、``GATESRV.exe`` 这类同目录程序，按“同目录
    有 LibTDMaster.dll”收下会把它们误当成学生端，结束它们并不能腾出 4705。
    """
    known = {name.casefold() for name in STUDENT_EXECUTABLE_NAMES}
    picked = []
    for row in rows:
        name = str(row.get("name") or "").casefold()
        if _is_student_name(name) or name in known:
            picked.append(row)
    return picked


def find_student_processes():
    """列出本机正在运行的学生端进程。

    Returns:
        list[dict]: 每项含 ``pid``、``name``、按端口号升序的 ``ports``、
        ``path``（读不到时为空字符串）、``genuine``（同目录有
        ``LibTDMaster.dll`` 时为 True）与 ``creation``（创建时间，用于校验
        进程号复用）。

    Raises:
        RuntimeError: 进程列表查询失败。
    """
    rows = _candidates(_rows())
    if not rows:
        return []
    ports = listening_ports([row["pid"] for row in rows])
    return [_describe(row, ports) for row in rows]


def _saved_executable():
    """读取设置里记住的学生端路径，读取失败时返回空字符串。"""
    with suppress(OSError, ValueError):
        return normalize_executable_path(
            portable_settings().value(STUDENT_EXE_SETTINGS_KEY, "")
        )
    return ""


def save_executable(path):
    """把路径写进设置，下次启动直接复用。"""
    settings = portable_settings()
    settings.set_value(STUDENT_EXE_SETTINGS_KEY, str(path or ""))
    settings.sync()
    return settings.status() == 0


def student_status(exe_path=None):
    """一次调用拿到页面需要的全部状态，避免界面分多次查询。

    进程快照、端口与记住的路径都在这里读，后台线程只需调一次。

    Args:
        exe_path: 手工路径；None 表示读设置里记住的路径。

    Returns:
        dict: ``processes`` 为进程列表；``exe_path`` 为记住的或从运行中
        进程取到的路径，都没有时为空字符串；``saved_path`` 为设置里记住
        的路径；``port`` 为极域默认端口；``port_owner`` 为占用该端口的
        学生端进程号（没有时为 0）。
    """
    processes = find_student_processes()
    saved = normalize_executable_path(
        exe_path if exe_path is not None else _saved_executable()
    )
    owner = 0
    for item in processes:
        if STUDENT_PORT in item["ports"]:
            owner = item["pid"]
            break
    return {
        "processes": processes,
        "exe_path": saved
        or next((item["path"] for item in processes if item["path"]), ""),
        "saved_path": saved,
        "port": STUDENT_PORT,
        "port_owner": owner,
    }


def _wait_gone(pid, timeout, creation=None):
    """在超时时间内轮询等待进程消失，返回是否已经不在。"""
    deadline = time.monotonic() + timeout
    while True:
        if not is_process_alive(pid, creation):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_INTERVAL)


def _terminate(entry, report=None):
    """结束单个学生端进程：先请它自己退出，再强制结束。

    极域学生端没有窗口也不处理关闭消息，``taskkill`` 不加 ``/F`` 同样返回
    成功，但进程其实还在跑，所以每一步都要以“进程是否真的消失”为准。

    Args:
        entry: ``find_student_processes`` 返回的记录，用其中的进程号与创建时间。
        report: 可选的进度回调。

    Returns:
        dict: 执行结果，字段与 ``terminate_process`` 一致并带 ``pid``。
    """
    pid = entry["pid"]
    creation = entry.get("creation")
    close_main_windows(pid)
    if _wait_gone(pid, GRACEFUL_TIMEOUT, creation):
        return {
            "pid": pid,
            "code": 0,
            "output": "进程已自行退出",
            "success": True,
            "forced": False,
            "gone": True,
        }
    if report:
        report("PID %d 未响应关闭请求，正在强制结束…" % pid)
    outcome = terminate_process(pid, creation, FORCED_TIMEOUT)
    outcome["pid"] = pid
    return outcome


def _run_student_elevated(target):
    """通过 UAC 启动助手进程结束或启动学生端，返回助手回传的结果。

    Args:
        target: 逗号分隔的进程号，或 ``start=程序路径``。

    Returns:
        list[dict]: 助手回传的每个进程的结果。

    Raises:
        RuntimeError: 授权被取消、助手没有回传结果或结果格式不对。
    """
    exit_code, payload = run_elevated_helper(
        STUDENT_HELPER_ARGUMENT,
        [target],
        STUDENT_RESULT_ARGUMENT,
        "结束或启动学生端",
        "jiyu-student-",
        "管理员权限进程未返回结果（助手退出码 %d），可能是授权被取消、"
        "被安全软件拦截或程序路径含中文",
    )
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise RuntimeError("管理员权限进程返回的结果无效")
    if exit_code and not any(item.get("success") for item in results):
        raise RuntimeError("管理员权限操作失败（退出码 %d）" % exit_code)
    return results


def _respawned(known_pids):
    """找出结束后被守护服务重新拉起的进程，返回追加的结果项。"""
    extra = []
    for item in find_student_processes():
        if item["pid"] in known_pids:
            continue
        extra.append(
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
    return extra


def stop_student_processes(pids=None, report=None, guardian=True):
    """结束本机学生端进程；不指定进程号时结束全部学生端。

    普通权限下结束失败时，把剩下的进程交给 UAC 助手一次性处理；助手返回
    后再查一次，以“进程是否真的消失”作为最终结果。

    Args:
        pids: 进程号序列，None 表示自动查找学生端。
        report: 可选的进度回调，供后台任务把提示写到界面。
        guardian: 结束后是否在短窗口内复查是否被守护服务重新拉起。

    Returns:
        list[dict]: 每个进程的执行结果，含 ``pid``、``code``、``output``、
        ``success``、``forced`` 与 ``gone``；被重新拉起的进程额外带
        ``respawned`` 且 ``success`` 为 False。

    Raises:
        RuntimeError: 找不到学生端。
        ValueError: 进程号不合法。
    """
    everything = find_student_processes()
    if pids is None:
        targets = everything
    else:
        wanted = []
        for value in pids:
            if not str(value).strip().isdigit():
                raise ValueError("进程号必须是数字")
            wanted.append(int(str(value).strip()))
        by_pid = {item["pid"]: item for item in everything}
        targets = [by_pid[pid] for pid in wanted if pid in by_pid]
    if not targets:
        raise RuntimeError("本机没有正在运行的学生端进程")
    if report:
        report("正在结束 %d 个学生端进程…" % len(targets))
    results = []
    for entry in targets:
        outcome = _terminate(entry, report)
        results.append(outcome)
        if not outcome["success"] and report:
            report("PID %d 结束失败：%s" % (entry["pid"], outcome["output"]))
    pending = [item for item in results if not item.get("success")]
    can_elevate = sys.platform == "win32"
    if pending and can_elevate and not _is_admin():
        if report:
            report("正在请求管理员权限结束剩余的 %d 个进程…" % len(pending))
        elevated = {
            item["pid"]: item
            for item in _run_student_elevated(
                ",".join(str(item["pid"]) for item in pending)
            )
        }
        results = [elevated.get(item["pid"], item) for item in results]
    # 以最终查询为准：进程消失就算成功，不管上面哪一步报了什么。
    alive = {item["pid"] for item in find_student_processes()}
    for item in results:
        item["gone"] = item["pid"] not in alive
        if item["gone"]:
            item["success"] = True
            item.setdefault("output", "已结束")
    if alive and report:
        report("仍有 %d 个学生端进程未被结束" % len(alive))
    if guardian and not alive:
        with suppress(OSError, RuntimeError):
            time.sleep(RESPAWN_WINDOW)
            results.extend(_respawned({item["pid"] for item in targets}))
    return results


def _registry_list(command):
    """执行一段 PowerShell 并返回非空输出行，失败时返回空列表。"""
    try:
        process = run_windows_command(["powershell", "-NoProfile", "-Command", command])
    except (OSError, RuntimeError):
        return []
    if process.returncode:
        return []
    return [line.strip() for line in process.stdout.splitlines() if line.strip()]


def _clean_icon(value):
    """卸载信息里的 ``DisplayIcon`` 常带引号和图标序号，这里还原成纯路径。"""
    text = str(value or "").strip().strip('"')
    if text.endswith(",0"):
        text = text[:-2]
    return text.strip().strip('"')


def _uninstall_icon():
    """读卸载信息里的 ``DisplayIcon``，找不到时返回空列表。"""
    quoted = ",".join("'%s'" % item for item in registry_paths()["exact"])
    command = (
        "Get-ItemProperty -Path %s -ErrorAction SilentlyContinue | "
        "ForEach-Object { $_.DisplayIcon }" % quoted
    )
    return [_clean_icon(line) for line in _registry_list(command)]


def _registered_directories():
    """从卸载信息里找学生端安装目录，找不到时返回空列表。"""
    quoted = ",".join("'%s'" % item for item in registry_paths()["wildcard"])
    command = (
        "Get-ItemProperty -Path %s -ErrorAction SilentlyContinue | "
        "Where-Object { $_.DisplayName -match "
        "'Student|e-Learning|Mythware|TopDomain|极域' } | "
        "ForEach-Object { $_.InstallLocation } | Where-Object { $_ }" % quoted
    )
    return _registry_list(command)


def _service_directories():
    """从极域相关服务的可执行路径推出安装目录。

    服务端组件（如 ``GATESRV.exe``）和学生端装在同一目录，注册表里查不到时
    用这条线索最可靠；有些机器把学生端装在非系统盘的自定义目录。
    """
    pattern = "|".join(GUARDIAN_MARKERS)
    script = (
        "Get-CimInstance Win32_Service | "
        "Where-Object { $_.PathName -match '%s' } | "
        "ForEach-Object { $_.PathName }" % pattern
    )
    directories = []
    for text in _registry_list(script):
        # PathName 带参数时整段被引号括起，路径本身也可能含空格：
        # 先取第一对引号里的完整路径，没有引号时才按空白截到命令之前。
        if text.startswith('"'):
            end = text.find('"', 1)
            candidate = text[1:end] if end > 0 else text.strip('"')
        else:
            candidate = text.split()[0]
        parent = str(Path(candidate.strip('"')).parent)
        if parent not in directories:
            directories.append(parent)
    return directories


def _executable_in(directory):
    """在一个目录里按已知文件名找主程序，找不到返回 None。"""
    for name in STUDENT_EXECUTABLE_NAMES:
        candidate = Path(directory) / name
        if candidate.is_file():
            # 目录可能来自注册表之类的来源，统一返回绝对路径。
            return str(candidate.resolve())
    return None


def find_student_executable(explicit=None):
    """定位本机学生端主程序。

    顺序参考 JiYuTrainer：手动指定 → 设置里记住的路径 → 正在运行的真身
    进程 → 卸载信息里的 ``DisplayIcon`` → 卸载信息里的安装目录 → 极域服务
    所在目录 → 常见安装目录。多个候选时优先同目录带 ``LibTDMaster.dll``
    的真身。

    Args:
        explicit: 手动指定的路径，None 表示按上面的顺序自动查找。

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
    saved = _saved_executable()
    if saved:
        # 记住的路径即使暂时不在（比如外接盘没插上）也直接沿用用户的意图，
        # 是否真的存在由启动时的 ShellExecute 报错说明。
        return str(Path(saved).resolve())
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
        "没有找到学生端安装位置，可以在页面里选择或输入 StudentMain.exe 的完整路径"
    )


def _shell_execute(path):
    """调用 ``ShellExecuteW`` 打开程序，返回 ``HINSTANCE`` 转换后的错误值。

    学生端依赖正常的工作目录与启动方式，``ShellExecute`` 与在资源管理器里
    双击一致，也避免当前进程退出时把它一起带走。

    Returns:
        int: 0 表示成功，其它值为 ``ShellExecuteW`` 返回的错误码。
    """
    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteW.argtypes = [
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_int,
    ]
    shell32.ShellExecuteW.restype = ctypes.c_void_p
    value = shell32.ShellExecuteW(None, "open", str(path), None, None, 1)
    return int(value or 0)


def _spawn(exe_path):
    """以独立进程启动学生端，返回启动结果。"""
    if sys.platform == "win32":
        error = _shell_execute(exe_path)
        if error == 0:
            return {
                "path": str(exe_path),
                "pid": 0,
                "code": 0,
                "output": "已请求启动",
                "success": True,
                "forced": False,
            }
        return {
            "path": str(exe_path),
            "pid": 0,
            "code": error,
            "output": "启动失败（ShellExecute 错误码 %d）" % error,
            "success": False,
            "forced": False,
        }
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
    """等待学生端进程出现，返回新出现的真身记录，超时返回空字典。

    只认同目录带 ``LibTDMaster.dll`` 或占用 4705 且不在操作前列表里的
    进程，避免把本来就在运行的同名进程当成启动结果。

    Args:
        before: 操作开始前的进程记录列表。
        timeout: 等待秒数。

    Returns:
        dict: 新出现的进程记录，超时为空字典。
    """
    known = {item["pid"] for item in before}
    deadline = time.monotonic() + timeout
    while True:
        for item in find_student_processes():
            if item["pid"] in known:
                continue
            if item["genuine"] or STUDENT_PORT in item["ports"]:
                return item
        if time.monotonic() >= deadline:
            return {}
        time.sleep(POLL_INTERVAL)


def start_student_process(exe_path=None, report=None, remember=True):
    """启动本机学生端，并确认进程真的起来了。

    Args:
        exe_path: 学生端主程序路径，None 表示自动查找。
        report: 可选的进度回调，供后台任务把提示写到界面。
        remember: 是否把用到的路径写进设置，下次直接复用。

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
    # 学生端需要写入自己的安装目录与注册表，非管理员时一贯走提权。
    if sys.platform == "win32" and not _is_admin():
        results = _run_student_elevated("start=" + resolved)
    else:
        results = [_spawn(resolved)]
    started = _wait_for_start(before)
    for item in results:
        item["confirmed"] = bool(started)
        item.setdefault("path", resolved)
        if started:
            item["pid"] = started["pid"]
            item["output"] = "已启动，进程号 %d" % started["pid"]
            item["success"] = True
        elif item.get("success"):
            # 进程已经拉起但列表还没看到，按启动成功但未确认处理。
            item["output"] = "已请求启动，但没有检测到学生端进程"
    ok = any(item.get("success") for item in results)
    if remember and ok:
        save_executable(resolved)
    if report:
        if started:
            report("学生端已启动，进程号 %d" % started["pid"])
        elif not ok:
            report("启动失败，请查看运行日志")
    return results


def toggle_student_process(exe_path=None, report=None):
    """按当前状态启动或结束学生端，供界面的单个按钮与命令行默认动作使用。

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
        arguments: 形如 ``[目标, 结果文件路径]``，目标是逗号分隔的进程号或
            ``start=程序路径``；也兼容 ``[目标, STUDENT_RESULT_ARGUMENT,
            结果文件路径]`` 的三参数写法。

    Returns:
        int: 0 表示全部成功，1 表示有进程失败，2 表示参数不合法。
    """
    if len(arguments) == 3 and arguments[1] == STUDENT_RESULT_ARGUMENT:
        target, result_path = arguments[0], arguments[2]
    elif len(arguments) == 2 and arguments[1] != STUDENT_RESULT_ARGUMENT:
        target, result_path = arguments
    else:
        return 2
    if target.startswith("start="):
        results = [_spawn(target[len("start=") :])]
    else:
        try:
            wanted = [int(value) for value in target.split(",") if value.strip()]
        except ValueError:
            return 2
        if not wanted:
            return 2
        # 逐个结束而不是把整个 target 当成一个进程号：助手只拿到进程号，
        # 按进程号重新取一次进程记录，拿不到创建时间就按进程号直接结束。
        results = []
        for pid in wanted:
            entry = {"pid": pid, "creation": process_creation_time(pid)}
            results.append(_terminate(entry))
    try:
        Path(result_path).write_text(
            json.dumps({"results": results}, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        return 1
    return 0 if all(item.get("success") for item in results) else 1
