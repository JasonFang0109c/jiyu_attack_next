"""报文、入口与界面的离线测试。"""

from __future__ import annotations

import atexit
import gc
import sys
import types

from PySide6.QtCore import Property


def _qfluent_classes() -> set[type]:
    """收集 Fluent Widgets 模块仍持有的 Python 类。"""
    classes: set[type] = set()
    pending = list(sys.modules.values())
    visited: set[int] = set()
    while pending:
        value = pending.pop()
        value_id = id(value)
        if value is None or value_id in visited:
            continue
        visited.add(value_id)
        if isinstance(value, type):
            if value.__module__.startswith("qfluentwidgets"):
                classes.add(value)
            continue
        if isinstance(value, types.ModuleType):
            if value.__name__.startswith("qfluentwidgets"):
                pending.extend(vars(value).values())
        elif isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            pending.extend(value)
    return classes


def _release_qfluent_properties() -> None:
    """在测试解释器退出前断开 PySide6 Property 的第三方循环引用。

    PySide6 6.12.0 的 ``Property`` 描述符在模块卸载阶段可能与 Shiboken
    元类形成不可回收循环。这里只处理测试进程中由 Fluent Widgets 创建的
    类定义，不改动产品运行时的第三方类，也不通过过滤告警掩盖资源问题。
    """
    for cls in _qfluent_classes():
        for name, descriptor in tuple(vars(cls).items()):
            if isinstance(descriptor, Property):
                setattr(cls, name, None)
    gc.collect()


atexit.register(_release_qfluent_properties)
