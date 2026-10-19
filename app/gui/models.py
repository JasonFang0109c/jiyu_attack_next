"""界面会话参数和运行记录。"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from cli import main as core


class ConnectionState(QObject):
    changed = Signal(str, object)
    DEFAULTS = {"target": "", "port": 4705, "loops": 1, "interval": 22.0}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = self.DEFAULTS.copy()

    def set_value(self, name, value):
        if name not in self.DEFAULTS:
            raise KeyError(name)
        if self.values[name] != value:
            self.values[name] = value
            self.changed.emit(name, value)

    def reset(self):
        for name, value in self.DEFAULTS.items():
            self.set_value(name, value)

    def snapshot(self):
        return self.values.copy()

    def restore(self, values):
        for name, value in values.items():
            if name in self.DEFAULTS:
                self.set_value(name, value)

    def options(self, **payload):
        return core.SendOptions(**self.values, **payload)


@dataclass(frozen=True)
class LogEntry:
    time: str
    category: str
    level: str
    message: str

    def as_text(self):
        return "[%s] [%s] [%s] %s" % (self.time, self.category, self.level, self.message)


class LogStore(QObject):
    added = Signal(object)
    cleared = Signal()

    def __init__(self, parent=None, limit=2000):
        super().__init__(parent)
        self.entries = deque(maxlen=limit)

    def add(self, category, message, level="信息"):
        entry = LogEntry(datetime.now().strftime("%H:%M:%S"), category, level, str(message))
        self.entries.append(entry)
        self.added.emit(entry)
        return entry

    def clear(self):
        self.entries.clear()
        self.cleared.emit()
