"""打包构建时间与版本信息。"""

from datetime import datetime
from pathlib import Path

from ..core import version as core_version

BUILD_TIME_FILE_NAME = "build_time.txt"
VERSION_FILE_NAME = core_version.VERSION_FILE_NAME
UNKNOWN_BUILD_TIME = "源码运行"


def build_time_text():
    """读取打包时间；无法读取时返回源码运行提示。"""
    return core_version.bundled_text(BUILD_TIME_FILE_NAME) or UNKNOWN_BUILD_TIME


def version_text():
    """读取版本号；打包时优先取构建写入的版本，源码运行时取包版本。"""
    return core_version.runtime_version()


def write_build_time(path, moment=None):
    """写入构建时间，供打包脚本生成数据文件。"""
    moment = moment or datetime.now()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(moment.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    return target


def write_version(path, version):
    """写入版本号，供打包脚本生成数据文件。"""
    return core_version.write_version(path, version)
