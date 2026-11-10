"""Windows 防火墙规则与按需 UAC 提权。"""

import json
import os
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path


def _decode_windows_output(output):
    """解码 Windows 命令行输出，兼容 UTF-8 与系统 ANSI 代码页。"""
    if not output:
        return ""
    # netsh 等系统工具在中文系统上输出 GBK，新版本也可能输出 UTF-8。
    try:
        return output.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return output.decode("mbcs")
    except (UnicodeDecodeError, LookupError):
        return output.decode("utf-8", errors="replace")


def run_windows_command(command):
    """执行无窗口 Windows 命令并解码标准输出。"""
    if sys.platform != "win32":
        raise RuntimeError("此功能仅支持 Windows")
    process = subprocess.run(
        command,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=15,
    )
    process.stdout = _decode_windows_output(process.stdout)
    process.stderr = _decode_windows_output(process.stderr)
    return process


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


def _is_admin():
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run_elevated_process(executable, parameters, directory=None, action="操作"):
    """通过 UAC 启动隐藏的管理员进程并等待其退出。

    Args:
        executable: 要启动的程序。
        parameters: 命令行参数文本。
        directory: 工作目录，None 表示沿用当前目录。
        action: 出现在提示文案里的动作名，用于说明被取消的是什么操作。

    Returns:
        int: 提权进程的退出码。
    """
    import ctypes
    from ctypes import wintypes

    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", wintypes.ULONG),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIcon", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040 | 0x00000100  # NOCLOSEPROCESS | NOASYNC
    info.lpVerb = "runas"
    info.lpFile = executable
    info.lpParameters = parameters
    info.lpDirectory = directory
    info.nShow = 0  # SW_HIDE
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.WinError(ctypes.get_last_error())
        if getattr(error, "winerror", None) == 1223:
            raise RuntimeError("管理员授权已取消，未执行%s" % action)
        raise error
    if not info.hProcess:
        raise RuntimeError("无法启动管理员权限进程")
    try:
        kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return exit_code.value
    finally:
        kernel32.CloseHandle(info.hProcess)


def run_elevated_helper(
    helper_argument, parameters, result_argument, action, temp_prefix, missing_result
):
    """启动提权助手进程，读回它写在临时文件里的结果。

    防火墙与学生端两个助手只差入口参数与结果语义，这段“起进程、等退出、
    读 JSON、清理临时文件”的骨架完全一样。

    Args:
        helper_argument: 助手入口参数，例如 ``"--firewall-helper"``。
        parameters: 传给助手的业务参数。
        result_argument: 结果文件路径参数的开关。
        action: 报错与进度里显示的动作名称。
        temp_prefix: 结果文件前缀，便于分辨是哪个助手留下的。
        missing_result: 读不到结果时的报错模板，``%d`` 处填助手退出码。

    Returns:
        tuple[int, dict]: 助手退出码与它写回的结果内容。

    Raises:
        RuntimeError: 助手没有留下可读的结果文件。
    """
    handle, result_path = tempfile.mkstemp(prefix=temp_prefix, suffix=".json")
    os.close(handle)
    try:
        arguments = [helper_argument, *parameters, result_argument, result_path]
        directory = None
        if not getattr(sys, "frozen", False):
            # 直接运行源码时要先把仓库根目录设为工作目录，用 -m app 走统一入口，
            # 否则助手进程无法解析相对导入，等于什么都没做。
            arguments = ["-m", "app", *arguments]
            directory = str(Path(__file__).resolve().parents[2])
        exit_code = _run_elevated_process(
            sys.executable,
            subprocess.list2cmdline(arguments),
            directory=directory,
            action=action,
        )
        try:
            payload = json.loads(Path(result_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError(missing_result % exit_code) from error
        return exit_code, payload
    finally:
        with suppress(OSError):
            os.unlink(result_path)


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
