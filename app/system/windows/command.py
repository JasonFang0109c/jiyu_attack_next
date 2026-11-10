"""无窗口 Windows 命令运行与输出解码。"""

import subprocess
import sys


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
