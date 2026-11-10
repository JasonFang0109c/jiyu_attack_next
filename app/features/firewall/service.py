"""防火墙规则业务与提权助手入口。"""

import json
import sys
from pathlib import Path

from app.system.windows.command import run_windows_command
from app.system.windows.elevation import _is_admin, run_elevated_helper


def _firewall_result(command, process, *, success=False, note=""):
    stdout = process.stdout.strip()
    stderr = process.stderr.strip()
    if note:  # noqa: SIM108  (两路输出来源不同，拆开写更清楚)
        output = note + ("\n" + stdout if stdout else "")
    else:
        output = stdout or stderr
    return {
        "command": command,
        "code": process.returncode,
        "stdout": output,
        "stderr": stderr if note and stdout else "",
        "success": success,
        "detail": note,
    }


def _firewall_rule_command(action):
    """构造修改 StudentMain.exe 规则的 netsh 命令。"""
    return [
        "netsh",
        "advfirewall",
        "firewall",
        "set",
        "rule",
        "name=StudentMain.exe",
        "new",
        "action=" + action,
    ]


def _service_already_running(process):
    """判断 net start 的失败输出是否表示服务本来就在运行。"""
    # 服务已运行时 net start 以 2182 退出，中文系统还会附带“已经启动”的提示。
    return "2182" in process.stderr or "已经启动" in process.stderr


def set_firewall_rule(action):
    """把 StudentMain.exe 的入站规则改为阻断或允许。

    阻断前会先启动防火墙服务并打开所有配置文件的防火墙，避免只改规则
    却因为服务停止而仍然放行。

    Args:
        action: 操作类型，"block" 或 "allow"。

    Returns:
        list[dict]: 每条 netsh 命令的执行结果，含命令文本、退出码与中文说明。

    Raises:
        ValueError: action 不是 "block" 或 "allow"。
    """
    if action not in {"block", "allow"}:
        raise ValueError("不支持的防火墙操作")
    rule_note = "已将 StudentMain.exe 规则更新为%s。" % (
        "阻断" if action == "block" else "允许"
    )
    rule_failure = (
        "无法更新 StudentMain.exe 规则，请确认该规则存在且程序已获得管理员权限。"
    )
    # 每步带成功与失败的说明；rescue_note 用于把“服务本来就在运行”算作成功。
    steps = []
    if action == "block":
        steps.append(
            (
                ["net.exe", "start", "MpsSvc"],
                "防火墙服务已启动。",
                "无法启动防火墙服务，请确认程序已获得管理员权限。",
                "防火墙服务原本已在运行。",
            )
        )
        steps.append(
            (
                ["netsh", "advfirewall", "set", "allprofiles", "state", "on"],
                "Windows 防火墙已启用，目标规则已更新为阻断。",
                "无法启用 Windows 防火墙，请确认程序已获得管理员权限。",
                None,
            )
        )
    steps.append((_firewall_rule_command(action), rule_note, rule_failure, None))
    results = []
    for command, success_note, failure_note, rescue_note in steps:
        process = run_windows_command(command)
        success = process.returncode == 0
        note = success_note if success else failure_note
        if not success and rescue_note and _service_already_running(process):
            success = True
            note = rescue_note
        results.append(
            _firewall_result(" ".join(command), process, success=success, note=note)
        )
    return results


FIREWALL_HELPER_ARGUMENT = "--firewall-helper"


FIREWALL_RESULT_ARGUMENT = "--firewall-result"


def _run_firewall_elevated(action):
    exit_code, payload = run_elevated_helper(
        FIREWALL_HELPER_ARGUMENT,
        [action],
        FIREWALL_RESULT_ARGUMENT,
        "防火墙操作",
        "jiyu-firewall-",
        "管理员权限进程未返回防火墙结果（助手退出码 %d）",
    )
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    if exit_code:
        raise RuntimeError("防火墙操作失败（退出码 %d）" % exit_code)
    results = payload.get("results")
    if not isinstance(results, list):
        raise RuntimeError("管理员权限进程返回的防火墙结果无效")
    return results


def request_firewall_rule(action):
    """当前进程不是管理员时，通过 UAC 启动隐藏助手完成操作。"""
    if sys.platform == "win32" and not _is_admin():
        return _run_firewall_elevated(action)
    return set_firewall_rule(action)


def run_firewall_helper(arguments):
    """在提权后的助手进程里执行规则修改，并把结果写成 JSON 回传给主进程。

    Args:
        arguments: 形如 ``[动作, FIREWALL_RESULT_ARGUMENT, 结果文件路径]``。

    Returns:
        int: 0 表示规则修改成功，1 表示执行或写结果失败，2 表示参数不合法。
    """
    if len(arguments) != 3 or arguments[1] != FIREWALL_RESULT_ARGUMENT:
        return 2
    action, result_path = arguments[0], arguments[2]
    try:
        payload = {"results": set_firewall_rule(action)}
        exit_code = 0
    except Exception as error:
        payload = {"error": str(error) or error.__class__.__name__}
        exit_code = 1
    try:
        Path(result_path).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        return 1
    return exit_code
