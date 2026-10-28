"""打包构建时间信息。"""

from datetime import datetime
from pathlib import Path
import sys


BUILD_TIME_FILE_NAME = "build_time.txt"
UNKNOWN_BUILD_TIME = "源码运行"


def build_time_path():
    """返回构建时间文件路径；源码运行时返回 None。"""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if not bundle_root:
        return None
    return Path(bundle_root) / BUILD_TIME_FILE_NAME


def build_time_text():
    """读取打包时间；无法读取时返回源码运行提示。"""
    path = build_time_path()
    if path is None:
        return UNKNOWN_BUILD_TIME
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return UNKNOWN_BUILD_TIME
    if not value:
        return UNKNOWN_BUILD_TIME
    return value


def write_build_time(path, moment=None):
    """写入构建时间，供打包脚本生成数据文件。"""
    moment = moment or datetime.now()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(moment.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    return target
