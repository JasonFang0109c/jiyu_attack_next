"""构建变体：正常版本与 debug 版本共用同一份源码。

打包脚本把变体名写进 ``variant.txt`` 打进产物，运行时读它决定日志等级等
行为；源码运行没有这个文件，一律按正常版本处理。
"""

import sys
from pathlib import Path

VARIANT_FILE_NAME = "variant.txt"
RELEASE = "release"
DEBUG = "debug"


def build_variant():
    """返回当前产物的构建变体。

    Returns:
        str: ``debug`` 或 ``release``；读不到标记时按 ``release`` 处理。
    """
    bundle_root = getattr(sys, "_MEIPASS", None)
    if not bundle_root:
        return RELEASE
    try:
        text = (Path(bundle_root) / VARIANT_FILE_NAME).read_text(encoding="utf-8")
    except OSError:
        return RELEASE
    return DEBUG if text.strip().casefold() == DEBUG else RELEASE


VARIANT = build_variant()
IS_DEBUG = VARIANT == DEBUG
