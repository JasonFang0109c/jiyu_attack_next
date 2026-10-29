"""打包构建时间与版本信息。"""

from datetime import datetime
from pathlib import Path
import sys


BUILD_TIME_FILE_NAME = "build_time.txt"
VERSION_FILE_NAME = "version.txt"
UNKNOWN_BUILD_TIME = "源码运行"


def _bundle_file(name):
    """返回打包资源路径；源码运行时返回 None。"""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if not bundle_root:
        return None
    return Path(bundle_root) / name


def _read_bundle_text(name):
    """读取打包资源中的单行文本；缺失或为空时返回 None。"""
    path = _bundle_file(name)
    if path is None:
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def build_time_path():
    """返回构建时间文件路径；源码运行时返回 None。"""
    return _bundle_file(BUILD_TIME_FILE_NAME)


def build_time_text():
    """读取打包时间；无法读取时返回源码运行提示。"""
    return _read_bundle_text(BUILD_TIME_FILE_NAME) or UNKNOWN_BUILD_TIME


def version_text():
    """读取版本号；打包时优先取构建写入的版本，源码运行时取 app.__version__。"""
    bundled = _read_bundle_text(VERSION_FILE_NAME)
    if bundled:
        return bundled
    from app import __version__
    return __version__


def write_build_time(path, moment=None):
    """写入构建时间，供打包脚本生成数据文件。"""
    moment = moment or datetime.now()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(moment.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    return target


def write_version(path, version):
    """写入版本号，供打包脚本生成数据文件。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(version).strip(), encoding="utf-8")
    return target
