"""Qt 图标适配；资源根目录由共享路径模块决定。"""

from PySide6.QtGui import QIcon

from app.shared.resources import resource_path


def app_icon():
    """读取源码或打包目录中的项目图标。"""
    return QIcon(str(resource_path("icons", "app.svg")))
