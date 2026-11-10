"""页面共享的连接会话状态。"""

from types import MappingProxyType

from PySide6.QtCore import QObject, Signal

import app.features.send.data as send_data
from app.features.names.gui.data import DeviceAliasStore


class ConnectionState(QObject):
    """页面共享的目标地址、端口、轮数与间隔。

    Attributes:
        aliases: 设备备注存储，改备注时会自动同步 target。
        values: 当前输入值，键与 ``DEFAULTS`` 一致。
    """

    changed = Signal(str, object)
    # 只读共享的缺省值，实例里始终先 copy 再修改。
    DEFAULTS = MappingProxyType(
        {"target": "", "port": 4705, "loops": 1, "interval": 22.0}
    )

    def __init__(self, aliases=None, parent=None):
        super().__init__(parent)
        self.aliases = aliases if aliases is not None else DeviceAliasStore(parent=self)
        self.aliases.renamed.connect(self._alias_renamed)
        self.aliases.removed.connect(self._alias_removed)
        self.values = self.DEFAULTS.copy()

    def _alias_renamed(self, old_name, new_name):
        if self.values["target"].strip().casefold() == old_name.casefold():
            self.set_value("target", new_name)

    def _alias_removed(self, name):
        if self.values["target"].strip().casefold() == name.casefold():
            self.set_value("target", "")

    def set_value(self, name, value):
        """写入一个会话参数；值未变化时不发信号。"""
        if name not in self.DEFAULTS:
            raise KeyError(name)
        if self.values[name] != value:
            self.values[name] = value
            self.changed.emit(name, value)

    def reset(self):
        """把所有会话参数恢复默认值。"""
        for name, value in self.DEFAULTS.items():
            self.set_value(name, value)

    def resolve_target(self, target=None):
        """把设备备注名换成真实地址，未命中时原样返回。"""
        value = self.values["target"] if target is None else target
        return self.aliases.resolve(value)

    def format_target(self, target=None):
        """返回带备注名的展示文本，例如“教室 A（192.168.1.20）”。"""
        value = self.values["target"] if target is None else target
        return self.aliases.format_target(value)

    def options(self, **payload):
        """组装发送参数，自动把备注名解析成地址。"""
        values = self.values.copy()
        values["target"] = self.resolve_target(values["target"])
        values.update(payload)
        return send_data.SendOptions(**values)
