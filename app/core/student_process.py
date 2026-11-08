"""启停本机极域学生端进程，需要管理员权限时按需提权。

模拟教师端和学生端同时跑在一台电脑上时，学生端会独占教师端地址的 4705
端口，把学生回包全部收走，所以需要能一键结束它。结束进程必须管理员权限，
这里复用防火墙模块的 UAC 助手：非管理员时用 ``runas`` 启动隐藏子进程，结果
通过临时 JSON 文件回传。

除了结束进程，也可以把学生端重新拉起来：结束之后测试现场要恢复限制，
或者需要学生端在频道里重新上线时都会用到。
"""

import json
import os
import subprocess
import sys
import tempfile
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

# 常见安装目录，注册表查不到时按顺序探测。
# 路径用 chr(92) 拼，避免源码里满屏反斜杠转义。
SEP = chr(92)
STUDENT_DIRECTORIES = tuple(
    SEP.join(["C:", "Program Files", folder, "e-Learning Class Standard", "1.00"])
    for folder in ("TopDomain", "Mythware", "JiYu")
) + tuple(
    SEP.join(["C:", "Program Files (x86)", folder, "e-Learning Class Standard", "1.00"])
    for folder in ("TopDomain", "Mythware", "JiYu")
)


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


def find_student_processes():
    """列出本机正在运行的学生端进程。

    Returns:
        list[dict]: 每项含 ``pid``、``name`` 与按端口号升序的 ``ports``。

    Raises:
        RuntimeError: 进程列表查询失败。
    """
    rows = [
        (pid, name)
        for pid, name in _process_rows()
        if STUDENT_NAME_MARKER in name.casefold()
    ]
    ports = _listening_ports([pid for pid, _name in rows]) if rows else {}
    return [
        {
            "pid": pid,
            "name": name,
            "ports": sorted(ports.get(pid, set())),
        }
        for pid, name in rows
    ]


def _terminate(pid):
    """结束单个进程，返回执行结果。"""
    process = run_windows_command(["taskkill", "/PID", str(pid), "/F"])
    output = (process.stdout.strip() or process.stderr.strip()).strip()
    return {
        "pid": pid,
        "code": process.returncode,
        "output": output,
        "success": process.returncode == 0,
    }


def _terminate_all(pids):
    return [_terminate(pid) for pid in pids]


def _run_student_elevated(pids):
    """通过 UAC 启动助手进程结束学生端，返回每个进程的结果。"""
    handle, result_path = tempfile.mkstemp(prefix="jiyu-student-", suffix=".json")
    os.close(handle)
    try:
        arguments = [
            STUDENT_HELPER_ARGUMENT,
            ",".join(str(pid) for pid in pids),
            STUDENT_RESULT_ARGUMENT,
            result_path,
        ]
        if not getattr(sys, "frozen", False):
            arguments.insert(0, str(Path(__file__).resolve()))
        exit_code = _run_elevated_process(
            sys.executable, subprocess.list2cmdline(arguments)
        )
        try:
            payload = json.loads(Path(result_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError("管理员权限进程未返回结束进程结果") from error
        if payload.get("error"):
            raise RuntimeError(payload["error"])
        results = payload.get("results")
        if not isinstance(results, list):
            raise RuntimeError("管理员权限进程返回的结果无效")
        if exit_code and not any(item.get("success") for item in results):
            raise RuntimeError("结束学生端失败（退出码 %d）" % exit_code)
        return results
    finally:
        with suppress(OSError):
            os.unlink(result_path)


def stop_student_processes(pids=None, report=None):
    """结束指定进程；不指定时结束本机全部学生端进程。

    Args:
        pids: 进程号序列，None 表示自动查找学生端。
        report: 可选的进度回调，供后台任务把提示写到界面。

    Returns:
        list[dict]: 每个进程的执行结果，含 ``pid``、``code``、``output``、
        ``success``。

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
    if sys.platform == "win32" and not _is_admin():
        return _run_student_elevated(targets)
    return _terminate_all(targets)


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
        results = _terminate_all(targets)
    try:
        Path(result_path).write_text(
            json.dumps({"results": results}, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        return 1
    return 0 if all(item["success"] for item in results) else 1


def _registry_text():
    """拼出卸载信息所在的注册表路径，避免在源码里写反斜杠转义。"""
    sep = chr(92)
    software = sep.join(
        ["SOFTWARE", "Microsoft", "Windows", "CurrentVersion", "Uninstall", "*"]
    )
    wow = sep.join(
        [
            "SOFTWARE",
            "WOW6432Node",
            "Microsoft",
            "Windows",
            "CurrentVersion",
            "Uninstall",
            "*",
        ]
    )
    return "'HKLM:%s','HKLM:%s'" % (software, wow)


def _running_executable():
    """返回正在运行的学生端可执行文件路径，取不到时返回空字符串。"""
    process = run_windows_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-Process -Name 'StudentMain*','Student' -ErrorAction "
            "SilentlyContinue | Where-Object { $_.Path } | Select-Object "
            "-First 1 -ExpandProperty Path)",
        ]
    )
    if process.returncode or not process.stdout.strip():
        return ""
    return process.stdout.strip().splitlines()[0].strip()


def _registered_directories():
    """从卸载信息里找学生端安装目录，找不到时返回空列表。"""
    command = (
        "Get-ItemProperty "
        + _registry_text()
        + " -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match "
        + "'Student|e-Learning|Mythware|TopDomain' } | "
        + "ForEach-Object { $_.InstallLocation } | Where-Object { $_ }"
    )
    process = run_windows_command(["powershell", "-NoProfile", "-Command", command])
    if process.returncode:
        return []
    return [line.strip() for line in process.stdout.splitlines() if line.strip()]


def find_student_executable():
    """定位本机学生端主程序。

    依次尝试正在运行的进程、注册表里的安装目录与几个常见路径。

    Returns:
        str: 可执行文件的完整路径。

    Raises:
        RuntimeError: 没有找到安装位置。
    """
    running = _running_executable()
    if running and Path(running).is_file():
        return running
    candidates = []
    for directory in _registered_directories() + list(STUDENT_DIRECTORIES):
        for name in STUDENT_EXECUTABLE_NAMES:
            candidates.append(Path(directory) / name)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
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
        }
    return {
        "path": str(exe_path),
        "pid": process.pid,
        "code": 0,
        "output": "已启动",
        "success": True,
    }


def _run_start_elevated(exe_path):
    """通过 UAC 启动助手进程拉起学生端，返回启动结果。"""
    handle, result_path = tempfile.mkstemp(prefix="jiyu-student-", suffix=".json")
    os.close(handle)
    try:
        arguments = [
            STUDENT_HELPER_ARGUMENT,
            "start=" + str(exe_path),
            STUDENT_RESULT_ARGUMENT,
            result_path,
        ]
        if not getattr(sys, "frozen", False):
            arguments.insert(0, str(Path(__file__).resolve()))
        exit_code = _run_elevated_process(
            sys.executable, subprocess.list2cmdline(arguments)
        )
        try:
            payload = json.loads(Path(result_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError("管理员权限进程未返回启动学生端结果") from error
        if payload.get("error"):
            raise RuntimeError(payload["error"])
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            raise RuntimeError("管理员权限进程返回的结果无效")
        if exit_code and not any(item.get("success") for item in results):
            raise RuntimeError("启动学生端失败（退出码 %d）" % exit_code)
        return results
    finally:
        with suppress(OSError):
            os.unlink(result_path)


def start_student_process(exe_path=None, report=None):
    """启动本机学生端。

    Args:
        exe_path: 学生端主程序路径，None 表示自动查找。
        report: 可选的进度回调，供后台任务把提示写到界面。

    Returns:
        list[dict]: 启动结果，含 ``path``、``pid``、``code``、``output``、
        ``success``。

    Raises:
        RuntimeError: 找不到学生端、已经有实例在跑、提权被取消或提权进程
            没有回传结果。
    """
    if exe_path:
        target = Path(str(exe_path)).expanduser()
        if not target.is_file():
            raise RuntimeError("指定的学生端程序不存在：%s" % target)
        resolved = str(target.resolve())
    else:
        resolved = find_student_executable()
    if find_student_processes():
        raise RuntimeError("本机已经有学生端在运行，先结束再启动")
    if report:
        report("正在启动学生端…")
    if sys.platform == "win32" and not _is_admin():
        return _run_start_elevated(resolved)
    return [_spawn(resolved)]
