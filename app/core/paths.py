"""运行数据目录与日志文件位置，命令行与界面共用同一套规则。

数据目录与可执行文件同级，便于把 EXE 与 ``JiYuAttackNextData`` 一起拷贝；
源码运行时退回项目根目录，避免在 ``app/`` 里散落运行数据。
"""

import sys
from pathlib import Path

DATA_DIRECTORY_NAME = "JiYuAttackNextData"
LOG_FILE_NAME = "runtime.log"
CLI_LOG_FILE_NAME = "cli.log"


def portable_data_dir(executable=None):
    """返回与可执行文件同级的数据目录，源码运行时返回项目根目录。

    Args:
        executable: 可执行文件路径；None 表示按当前运行方式推断。

    Returns:
        Path: ``JiYuAttackNextData`` 目录的完整路径。
    """
    if executable is not None:
        executable_dir = Path(executable).resolve().parent
    elif getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
    else:
        executable_dir = Path(__file__).resolve().parents[2]
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
