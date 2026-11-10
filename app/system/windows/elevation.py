"""管理员状态与按需 UAC 助手启动。"""

import json
import os
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

from app.shared.paths import project_root


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
            directory = str(project_root())
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
