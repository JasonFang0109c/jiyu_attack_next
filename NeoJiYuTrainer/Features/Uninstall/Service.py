"""应用卸载：删除快捷方式、数据目录与可选驱动服务。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from NeoJiYuTrainer.Shared.Paths import DATA_DIRECTORY_NAME, portable_data_dir
from NeoJiYuTrainer.System.Windows.DriverLoader import DriverSession

APP_NAME = "NeoJiYuTrainer"


def install_root() -> Path | None:
    """返回冻结后的安装目录；源码运行时返回 None。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def shortcut_paths() -> list[Path]:
    """返回可能存在的桌面与开始菜单快捷方式。"""
    candidates: list[Path] = []
    profile = Path(os.environ.get("USERPROFILE", ""))
    appdata = Path(os.environ.get("APPDATA", ""))
    if profile:
        candidates.append(profile / "Desktop" / f"{APP_NAME}.lnk")
    if appdata:
        candidates.append(
            appdata
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / f"{APP_NAME}.lnk"
        )
    return [path for path in candidates if path.is_file()]


def remove_shortcuts() -> list[str]:
    """删除快捷方式并返回已删除路径。"""
    removed: list[str] = []
    for path in shortcut_paths():
        try:
            path.unlink()
            removed.append(str(path))
        except OSError:
            continue
    return removed


def remove_driver_service() -> str:
    """尝试停止并删除驱动服务，返回错误文本；成功返回空串。"""
    try:
        DriverSession().uninstall()
    except OSError as error:
        return str(error)
    return ""


def remove_data(data_dir: Path | None = None) -> bool:
    """删除运行数据目录。"""
    target = Path(data_dir or portable_data_dir())
    if not target.is_dir():
        return False
    shutil.rmtree(target, ignore_errors=True)
    return not target.exists()


def _schedule_install_dir_cleanup(root: Path, keep_user_data: bool) -> bool:
    """启动退出后清理安装目录；保留用户数据时跳过数据目录。"""
    if not root.is_dir():
        return False
    script = Path(tempfile.gettempdir()) / "NeoJiYuTrainer_uninstall.cmd"
    keep = DATA_DIRECTORY_NAME if keep_user_data else ""
    lines = [
        "@echo off",
        "timeout /t 2 /nobreak >nul",
    ]
    if keep:
        lines.append(
            f'for /d %%D in ("{root}\\*") do if /I not "%%~nxD"=="{keep}" '
            'rmdir /s /q "%%D"'
        )
        lines.append(f'del /f /q "{root}\\*" >nul 2>nul')
    else:
        lines.append(f'rmdir /s /q "{root}"')
    lines.append('del /f /q "%~f0" >nul 2>nul')
    script.write_text("\r\n".join(lines) + "\r\n", encoding="mbcs")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "DETACHED_PROCESS", 0
    )
    subprocess.Popen(
        ["cmd.exe", "/c", str(script)], creationflags=flags, close_fds=True
    )
    return True


def run_uninstall(keep_user_data: bool = False, remove_driver: bool = True) -> dict:
    """执行卸载并返回结果摘要。

    Args:
        keep_user_data: 是否保留 ``data``。
        remove_driver: 是否尝试删除内核驱动服务。

    Returns:
        dict: 已删除快捷方式、数据是否删除、驱动错误与是否已安排清理安装目录。
    """
    removed_shortcuts = remove_shortcuts()
    driver_error = remove_driver_service() if remove_driver else ""
    data_removed = False if keep_user_data else remove_data()
    root = install_root()
    scheduled = bool(root) and _schedule_install_dir_cleanup(root, keep_user_data)
    return {
        "shortcuts": removed_shortcuts,
        "data_removed": data_removed,
        "driver_error": driver_error,
        "scheduled": scheduled,
    }
