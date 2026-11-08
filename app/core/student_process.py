"""结束本机极域学生端进程，需要管理员权限时按需提权。

模拟教师端和学生端同时跑在一台电脑上时，学生端会独占教师端地址的 4705
端口，把学生回包全部收走，所以需要能一键结束它。结束进程必须管理员权限，
这里复用防火墙模块的 UAC 助手：非管理员时用 ``runas`` 启动隐藏子进程，结果
通过临时 JSON 文件回传。
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
    """在提权后的助手进程里结束学生端，并把结果写成 JSON 回传给主进程。

    Args:
        arguments: 形如 ``[进程号列表, STUDENT_RESULT_ARGUMENT, 结果文件路径]``。

    Returns:
        int: 0 表示全部结束成功，1 表示有进程结束失败，2 表示参数不合法。
    """
    if len(arguments) != 3 or arguments[1] != STUDENT_RESULT_ARGUMENT:
        return 2
    pids, result_path = arguments[0], arguments[2]
    try:
        targets = [int(value) for value in pids.split(",") if value.strip()]
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
