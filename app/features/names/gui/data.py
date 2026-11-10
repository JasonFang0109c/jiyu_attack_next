"""把设备备注服务的变更接入 Qt 信号。"""

from PySide6.QtCore import QObject, Signal

from app.features.names.service import DeviceAliasService


class DeviceAliasStore(QObject):
    """保留页面使用的备注 API，并由纯 Python 服务维护数据。"""

    changed = Signal()
    renamed = Signal(str, str)
    removed = Signal(str)
    SETTINGS_KEY = DeviceAliasService.SETTINGS_KEY
    MAX_NAME_LENGTH = DeviceAliasService.MAX_NAME_LENGTH

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self._service = DeviceAliasService(
            settings, self.changed.emit, self.renamed.emit, self.removed.emit
        )

    @property
    def load_error(self):
        """返回备注读取错误。"""
        return self._service.load_error

    @load_error.setter
    def load_error(self, value):
        self._service.load_error = value

    def _load(self):
        return self._service._load()

    @classmethod
    def _normalize_name(cls, name):
        return DeviceAliasService._normalize_name(name)

    @staticmethod
    def _normalize_address(address):
        return DeviceAliasService._normalize_address(address)

    def items(self):
        return self._service.items()

    def _find_name(self, name):
        return self._service._find_name(name)

    def match(self, target):
        return self._service.match(target)

    def resolve(self, target):
        return self._service.resolve(target)

    def format_target(self, target):
        return self._service.format_target(target)

    def _save(self, aliases):
        return self._service._save(aliases)

    def add(self, name, address):
        return self._service.add(name, address)

    def update(self, original_name, name, address):
        return self._service.update(original_name, name, address)

    def remove(self, name):
        return self._service.remove(name)

    def clear(self, persist=True):
        return self._service.clear(persist)
