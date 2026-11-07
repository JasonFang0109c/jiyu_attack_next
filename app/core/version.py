"""版本号与打包提交后缀的读取。

打包时 `packaging/build.ps1` 把显示版本写入 `version.txt` 并随 EXE 一起打包，
测试版会在基础版本号后拼上提交哈希（如 `0.1.0-1a8ede3`），
正式版不带。源码运行时回落到 `app/core/constants.py` 的 `__version__`。
"""

import sys
from pathlib import Path

from .constants import __version__

VERSION_FILE_NAME = "version.txt"


def bundle_file(name):
    """返回打包资源路径；源码运行时返回 None。

    Args:
        name: 打包根目录下的文件名。

    Returns:
        打包内的绝对路径，或源码运行时的 None。
    """
    root = getattr(sys, "_MEIPASS", None)
    if not root:
        return None
    return Path(root) / name


def bundled_text(name):
    """读取打包资源中的单行文本。

    Args:
        name: 打包根目录下的文件名。

    Returns:
        去掉首尾空白后的文本；文件缺失、为空或读取失败时返回 None。
    """
    path = bundle_file(name)
    if path is None:
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def display_version(version, commit=""):
    """把提交哈希拼到版本号后面。

    Args:
        version: 不含提交哈希的版本号。
        commit: 提交哈希，空字符串表示不拼接。

    Returns:
        需要展示与写入版本资源的版本号；已带同一后缀时原样返回。
    """
    text = str(version).strip()
    suffix = (commit or "").strip()
    if not suffix or text.endswith("-" + suffix):
        return text
    return "%s-%s" % (text, suffix)


def runtime_version():
    """返回当前运行的版本号。

    Returns:
        打包后取 `version.txt` 的内容，源码运行时取包版本。
    """
    return bundled_text(VERSION_FILE_NAME) or __version__


def write_version(path, version):
    """写入显示版本，供打包脚本生成数据文件。

    Args:
        path: 目标文件路径。
        version: 要写入的版本号。

    Returns:
        写入后的文件路径。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(version).strip(), encoding="utf-8")
    return target
