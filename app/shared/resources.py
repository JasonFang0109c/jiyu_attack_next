"""静态资源定位；源码目录与打包目录使用相同的相对路径。"""

import sys
from pathlib import Path


def resource_path(*parts):
    """返回资源的绝对路径，不创建目录或访问用户运行数据。

    Args:
        parts: 相对于 app/resources 的路径片段。

    Returns:
        Path: 源码或解包目录中的资源路径。
    """
    bundle_root = getattr(sys, "_MEIPASS", None)
    root = (
        Path(bundle_root) / "app" / "resources"
        if bundle_root
        else Path(__file__).resolve().parents[1] / "resources"
    )
    return root.joinpath(*parts)
