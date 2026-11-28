"""通过延迟导入转发到现有服务的兼容入口。"""

from importlib import import_module
from typing import Any


def _forward(module_name: str, function_name: str, *args: Any, **kwargs: Any) -> Any:
    """仅在调用时导入对应服务并转发参数。"""
    module = import_module(module_name)
    return getattr(module, function_name)(*args, **kwargs)


def prepare_packets(*args: Any, **kwargs: Any) -> Any:
    """转发到报文准备服务。"""
    return _forward("app.features.send.service", "prepare_packets", *args, **kwargs)


def execute_send_report(*args: Any, **kwargs: Any) -> Any:
    """转发到发送结果汇总服务。"""
    return _forward("app.features.send.service", "execute_send_report", *args, **kwargs)


def student_status(*args: Any, **kwargs: Any) -> Any:
    """转发到学生端状态服务。"""
    return _forward("app.features.student.service", "student_status", *args, **kwargs)


def start_guard(*args: Any, **kwargs: Any) -> Any:
    """转发到课堂防护启动服务。"""
    return _forward("app.features.classroom.service", "start_guard", *args, **kwargs)


def run_uninstall(*args: Any, **kwargs: Any) -> Any:
    """转发到卸载服务。"""
    return _forward("app.features.uninstall.service", "run_uninstall", *args, **kwargs)
