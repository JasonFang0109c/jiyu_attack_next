"""Windows 防火墙规则与按需 UAC 提权。"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _decode_windows_output(output):
    """Decode Windows CLI output, which may use UTF-8 or the ANSI code page."""
    if not output:
        return ""
    candidates = []
    for encoding in ("utf-8-sig", "mbcs"):
        try:
            candidates.append((encoding, output.decode(encoding)))
        except UnicodeDecodeError:
            pass
    if not candidates:
        return output.decode("utf-8", errors="replace")
    return candidates[0][1] if candidates[0][0] == "utf-8-sig" else candidates[-1][1]


def _windows_command(command):
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
    if note:
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


def set_firewall_rule(action):
    if action not in {"block", "allow"}:
        raise ValueError("不支持的防火墙操作")
    commands = []
    if action == "block":
        commands.extend(
            [
                ["net.exe", "start", "MpsSvc"],
                ["netsh", "advfirewall", "set", "allprofiles", "state", "on"],
            ]
        )
    commands.append(
        [
            "netsh",
            "advfirewall",
            "firewall",
            "set",
            "rule",
            "name=StudentMain.exe",
            "new",
            "action=" + action,
        ]
    )
    results = []
    for index, command in enumerate(commands):
        process = _windows_command(command)
        command_text = " ".join(command)
        success = process.returncode == 0
        note = ""
        if action == "block" and index == 0:
            if success:
                note = "防火墙服务已启动。"
            elif "2182" in process.stderr or "已经启动" in process.stderr:
                success = True
                note = "防火墙服务原本已在运行。"
            else:
                note = "无法启动防火墙服务，请确认程序已获得管理员权限。"
        elif action == "block" and index == 1:
            if success:
                note = "Windows 防火墙已启用，目标规则已更新为阻断。"
            else:
                note = "无法启用 Windows 防火墙，请确认程序已获得管理员权限。"
        elif action == "block" and index == 2:
            if success:
                note = "已将 StudentMain.exe 规则更新为阻断。"
            else:
                note = "无法更新 StudentMain.exe 规则，请确认该规则存在且程序已获得管理员权限。"
        elif action == "allow":
            if success:
                note = "已将 StudentMain.exe 规则更新为允许。"
            else:
                note = "无法更新 StudentMain.exe 规则，请确认该规则存在且程序已获得管理员权限。"
        results.append(
            _firewall_result(command_text, process, success=success, note=note)
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


def _run_elevated_process(executable, parameters):
    """通过 UAC 启动隐藏的管理员进程并等待其退出。"""
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
    info.nShow = 0  # SW_HIDE
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.WinError(ctypes.get_last_error())
        if getattr(error, "winerror", None) == 1223:
            raise RuntimeError("管理员授权已取消，未执行防火墙操作")
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


def _run_firewall_elevated(action):
    handle, result_path = tempfile.mkstemp(prefix="jiyu-firewall-", suffix=".json")
    os.close(handle)
    try:
        arguments = [
            FIREWALL_HELPER_ARGUMENT,
            action,
            FIREWALL_RESULT_ARGUMENT,
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
            raise RuntimeError("管理员权限进程未返回防火墙结果") from error
        if payload.get("error"):
            raise RuntimeError(payload["error"])
        if exit_code:
            raise RuntimeError("防火墙操作失败（退出码 %d）" % exit_code)
        results = payload.get("results")
        if not isinstance(results, list):
            raise RuntimeError("管理员权限进程返回的防火墙结果无效")
        return results
    finally:
        try:
            os.unlink(result_path)
        except OSError:
            pass


def request_firewall_rule(action):
    """当前进程不是管理员时，通过 UAC 启动隐藏助手完成操作。"""
    if sys.platform == "win32" and not _is_admin():
        return _run_firewall_elevated(action)
    return set_firewall_rule(action)


def run_firewall_helper(arguments):
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
