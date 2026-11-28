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
LOG_FILE_NAME = "runtime.log"
CLI_LOG_FILE_NAME = "cli.log"


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


def portable_log_path(data_dir=None):
    """返回界面运行日志 ``runtime.log`` 的完整路径。

    Args:
        data_dir: 数据目录；None 表示由 :func:`portable_data_dir` 推断。

    Returns:
        Path: 日志文件路径。
    """
    root = Path(data_dir).resolve() if data_dir is not None else portable_data_dir()
    return root / LOG_FILE_NAME


def portable_cli_log_path(data_dir=None):
    """返回命令行运行日志 ``cli.log`` 的完整路径。

    Args:
        data_dir: 数据目录；None 表示由 :func:`portable_data_dir` 推断。

    Returns:
        Path: 日志文件路径。
    """
    root = Path(data_dir).resolve() if data_dir is not None else portable_data_dir()
    return root / CLI_LOG_FILE_NAME
