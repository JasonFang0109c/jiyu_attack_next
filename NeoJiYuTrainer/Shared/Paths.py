"""运行数据目录与日志文件位置，命令行与界面共用同一套规则。

数据目录与可执行文件同级，便于把 EXE 与 ``Data`` 一起拷贝；
源码运行时退回项目根目录，避免在 ``NeoJiYuTrainer/`` 里散落运行数据。
"""

import contextlib
import os
import sys
from pathlib import Path

DATA_DIRECTORY_NAME = "Data"
LEGACY_DATA_DIRECTORY_NAMES = (
    "NeoJiYuTrainerData",
    "JiYuAttackNextData",
    "data",
)
LOG_DIRECTORY_NAME = "Log"
LOG_FILE_NAME = "Runtime.log"
CLI_LOG_FILE_NAME = "Cli.log"
FATAL_LOG_NAME = "Fatal.log"
PENDING_LOG_NAME = "Pending.txt"
LEGACY_CRASH_DIRECTORY_NAME = "Crash"
LEGACY_LOG_NAMES = {
    "runtime.log": LOG_FILE_NAME,
    "cli.log": CLI_LOG_FILE_NAME,
    "fatal.log": FATAL_LOG_NAME,
    "pending.txt": PENDING_LOG_NAME,
}


def _migrate_legacy_data_dir(parent):
    """把旧版数据目录原地改名，保留用户的备注、设置与日志。

    Args:
        parent: 数据目录的父目录，通常是 EXE 所在目录或源码仓库根目录。
    """
    target = parent / DATA_DIRECTORY_NAME
    for name in LEGACY_DATA_DIRECTORY_NAMES:
        legacy = parent / name
        if not legacy.is_dir():
            continue
        if _is_same_directory(legacy, target):
            # 只差大小写时两者是同一个目录，NTFS 上必须经临时名才能换掉显示名。
            _rename_case_variant(legacy, target)
            continue
        if target.exists():
            continue
        # 目录被占用或权限不足时保留旧目录，不能让启动因为迁移失败而中断。
        with contextlib.suppress(OSError):
            legacy.rename(target)


def _is_same_directory(left, right):
    """判断两个路径是否指向同一个目录，Windows 下大小写不敏感。"""
    left_path = os.path.normcase(str(left.resolve()))
    right_path = os.path.normcase(str(right.resolve()))
    return left_path == right_path


def _rename_case_variant(source, target):
    """把只差大小写的目录改成目标名，NTFS 上先移到临时名再改名。"""
    if target.resolve().name == target.name:
        return
    temporary = source.with_name(f"{source.name}.migrating")
    with contextlib.suppress(OSError):
        source.rename(temporary)
        temporary.rename(target)


def project_root():
    """返回源码仓库根目录，供源码启动助手与开发工具使用。"""
    return Path(__file__).resolve().parents[2]


def portable_data_dir(executable=None):
    """返回与可执行文件同级的数据目录，源码运行时返回项目根目录。

    Args:
        executable: 可执行文件路径；None 表示按当前运行方式推断。

    Returns:
        Path: ``Data`` 目录的完整路径。
    """
    if executable is not None:
        executable_dir = Path(executable).resolve().parent
    elif getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
    else:
        executable_dir = Path(__file__).resolve().parents[2]
    _migrate_legacy_data_dir(executable_dir)
    return executable_dir / DATA_DIRECTORY_NAME


def log_dir(data_dir=None):
    """返回日志目录 ``Log`` 的完整路径。

    Args:
        data_dir: 数据目录；None 表示由 :func:`portable_data_dir` 推断。

    Returns:
        Path: 日志目录路径。
    """
    root = Path(data_dir).resolve() if data_dir is not None else portable_data_dir()
    return root / LOG_DIRECTORY_NAME


def portable_log_path(data_dir=None):
    """返回界面运行日志 ``Log/Runtime.log`` 的完整路径。

    Args:
        data_dir: 数据目录；None 表示由 :func:`portable_data_dir` 推断。

    Returns:
        Path: 日志文件路径。
    """
    return log_dir(data_dir) / LOG_FILE_NAME


def portable_cli_log_path(data_dir=None):
    """返回命令行运行日志 ``Log/Cli.log`` 的完整路径。

    Args:
        data_dir: 数据目录；None 表示由 :func:`portable_data_dir` 推断。

    Returns:
        Path: 日志文件路径。
    """
    return log_dir(data_dir) / CLI_LOG_FILE_NAME


def migrate_legacy_logs(data_dir=None):
    """把旧位置的日志与崩溃报告移进 ``Log`` 目录。

    旧版把 ``runtime.log``、``cli.log`` 直接放在数据目录，崩溃报告另放
    ``Crash`` 目录；这里统一搬到 ``Log`` 并把文件名改成大驼峰。目录不存在、
    目标已存在或文件被占用时保留原样，迁移失败不阻断启动。

    Args:
        data_dir: 数据目录；None 表示由 :func:`portable_data_dir` 推断。
    """
    root = Path(data_dir).resolve() if data_dir is not None else portable_data_dir()
    target = root / LOG_DIRECTORY_NAME
    with contextlib.suppress(OSError):
        target.mkdir(parents=True, exist_ok=True)

    sources = []
    with contextlib.suppress(OSError):
        sources.extend(item for item in root.iterdir() if item.is_file())
    crash = root / LEGACY_CRASH_DIRECTORY_NAME
    if crash.is_dir():
        with contextlib.suppress(OSError):
            sources.extend(item for item in crash.iterdir() if item.is_file())

    for item in sources:
        name = _migrated_log_name(item.name)
        if name is None:
            continue
        destination = target / name
        if destination.exists():
            continue
        with contextlib.suppress(OSError):
            item.replace(destination)

    with contextlib.suppress(OSError):
        if crash.is_dir() and not any(crash.iterdir()):
            crash.rmdir()


def _migrated_log_name(name):
    """返回旧文件名对应的新文件名，无需迁移时返回 None。"""
    lowered = name.lower()
    mapped = LEGACY_LOG_NAMES.get(lowered)
    if mapped is not None:
        return mapped
    if lowered.startswith("crashinfo-") and lowered.endswith(".txt"):
        return name
    return None
