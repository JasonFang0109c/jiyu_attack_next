"""界面会话参数、设备备注和运行记录。"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QSettings, Signal

from cli import main as core


DATA_DIRECTORY_NAME = "JiYuAttackNextData"
SETTINGS_FILE_NAME = "settings.ini"
LOG_FILE_NAME = "runtime.log"


def portable_data_dir(executable=None):
    """返回与可执行文件同级的数据目录，源码运行时返回项目根目录。"""
    if executable is not None:
        executable_dir = Path(executable).resolve().parent
    elif getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
    else:
        executable_dir = Path(__file__).resolve().parents[2]
    return executable_dir / DATA_DIRECTORY_NAME


def portable_settings(data_dir=None):
    root = Path(data_dir).resolve() if data_dir is not None else portable_data_dir()
    return QSettings(str(root / SETTINGS_FILE_NAME), QSettings.IniFormat)


def portable_log_path(data_dir=None):
    root = Path(data_dir).resolve() if data_dir is not None else portable_data_dir()
    return root / LOG_FILE_NAME


class DeviceAliasStore(QObject):
    """保存可复用的 IPv4 设备备注。"""

    changed = Signal()
    renamed = Signal(str, str)
    removed = Signal(str)
    SETTINGS_KEY = "device_aliases"
    MAX_NAME_LENGTH = 64

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self._settings = settings if settings is not None else portable_settings()
        self._aliases = {}
        self.load_error = ""
        self._load()

    def _load(self):
        raw = self._settings.value(self.SETTINGS_KEY, "{}")
        try:
            if isinstance(raw, str):
                data = json.loads(raw) if raw else {}
            elif isinstance(raw, dict):
                data = raw
            else:
                raise ValueError("备注数据格式无效")
            if not isinstance(data, dict):
                raise ValueError("备注数据格式无效")
            aliases = {}
            for name, address in data.items():
                aliases[self._normalize_name(name)] = self._normalize_address(address)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            self.load_error = "设备备注读取失败：%s" % error
            return
        self._aliases = aliases

    @classmethod
    def _normalize_name(cls, name):
        if name is None:
            raise ValueError("请填写备注名")
        value = str(name).strip()
        if not value:
            raise ValueError("请填写备注名")
        if len(value) > cls.MAX_NAME_LENGTH:
            raise ValueError("备注名不能超过 %d 个字符" % cls.MAX_NAME_LENGTH)
        if any(character in value for character in ("\x00", "\r", "\n")):
            raise ValueError("备注名不能包含换行或 NUL 字符")
        try:
            core.get_ip(value)
        except ValueError:
            return value
        raise ValueError("备注名不能使用 IP 地址格式")

    @staticmethod
    def _normalize_address(address):
        value = str(address).strip()
        if not value:
            raise ValueError("请填写 IP 地址")
        try:
            hosts = core.get_ip(value)
        except ValueError as error:
            raise ValueError("IP 地址格式错误，请填写单个 IPv4 地址、末段范围或 /24 网段") from error
        return value if "-" in value or "/" in value else hosts[0]

    def names(self):
        return list(self._aliases)

    def items(self):
        return list(self._aliases.items())

    def _find_name(self, name):
        key = str(name).strip().casefold()
        for existing in self._aliases:
            if existing.casefold() == key:
                return existing
        return None

    def match(self, target):
        value = str(target).strip()
        key = value.casefold()
        for name, address in self._aliases.items():
            if name.casefold() == key:
                return name, address
        return None

    def resolve(self, target):
        matched = self.match(target)
        return matched[1] if matched else str(target).strip()

    def format_target(self, target):
        matched = self.match(target)
        if matched:
            return "%s（%s）" % matched
        return str(target).strip()

    def _save(self, aliases):
        if self.load_error:
            raise OSError("%s；为避免覆盖原数据，请先修复或清除该配置项" % self.load_error)
        try:
            settings_path = self._settings.fileName()
            if settings_path:
                Path(settings_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
            self._settings.setValue(
                self.SETTINGS_KEY,
                json.dumps(aliases, ensure_ascii=False, separators=(",", ":")),
            )
            self._settings.sync()
        except OSError as error:
            raise OSError("设备备注保存失败：%s" % error) from error
        if self._settings.status() != QSettings.NoError:
            raise OSError("设备备注保存失败")
        self._aliases = aliases

    def add(self, name, address):
        normalized_name = self._normalize_name(name)
        normalized_address = self._normalize_address(address)
        if self._find_name(normalized_name) is not None:
            raise ValueError("备注名已存在")
        aliases = dict(self._aliases)
        aliases[normalized_name] = normalized_address
        self._save(aliases)
        self.changed.emit()

    def update(self, original_name, name, address):
        existing_name = self._find_name(original_name)
        if existing_name is None:
            raise ValueError("要修改的备注不存在")
        normalized_name = self._normalize_name(name)
        normalized_address = self._normalize_address(address)
        duplicate = self._find_name(normalized_name)
        if duplicate is not None and duplicate.casefold() != existing_name.casefold():
            raise ValueError("备注名已存在")
        aliases = {}
        for alias_name, alias_address in self._aliases.items():
            if alias_name.casefold() == existing_name.casefold():
                aliases[normalized_name] = normalized_address
            else:
                aliases[alias_name] = alias_address
        self._save(aliases)
        if existing_name != normalized_name:
            self.renamed.emit(existing_name, normalized_name)
        self.changed.emit()

    def remove(self, name):
        existing_name = self._find_name(name)
        if existing_name is None:
            raise ValueError("要删除的备注不存在")
        aliases = {
            alias_name: address
            for alias_name, address in self._aliases.items()
            if alias_name.casefold() != existing_name.casefold()
        }
        self._save(aliases)
        self.removed.emit(existing_name)
        self.changed.emit()


class ConnectionState(QObject):
    changed = Signal(str, object)
    DEFAULTS = {"target": "", "port": 4705, "loops": 1, "interval": 22.0}

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

    def resolve_target(self, target=None):
        value = self.values["target"] if target is None else target
        return self.aliases.resolve(value)

    def format_target(self, target=None):
        value = self.values["target"] if target is None else target
        return self.aliases.format_target(value)

    def restore(self, values):
        for name, value in values.items():
            if name in self.DEFAULTS:
                self.set_value(name, value)

    def options(self, **payload):
        values = self.values.copy()
        values["target"] = self.resolve_target(values["target"])
        values.update(payload)
        return core.SendOptions(**values)


@dataclass(frozen=True)
class LogEntry:
    time: str
    category: str
    level: str
    message: str

    def as_text(self):
        return "[%s] [%s] [%s] %s" % (self.time, self.category, self.level, self.message)

    def as_record(self):
        return {
            "time": self.time,
            "category": self.category,
            "level": self.level,
            "message": self.message,
        }

    @classmethod
    def from_record(cls, record):
        if not isinstance(record, dict):
            raise ValueError("日志记录格式无效")
        return cls(
            str(record["time"]),
            str(record["category"]),
            str(record["level"]),
            str(record["message"]),
        )


class LogStore(QObject):
    added = Signal(object)
    cleared = Signal()

    def __init__(self, parent=None, limit=2000, log_path=None):
        super().__init__(parent)
        self.log_path = Path(log_path) if log_path is not None else None
        self.storage_error = ""
        self.entries = deque(maxlen=limit)
        self._load()

    def _load(self):
        if self.log_path is None or not self.log_path.exists():
            return
        try:
            lines = self.log_path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError) as error:
            self.storage_error = "运行日志读取失败：%s" % error
            return
        loaded = deque(maxlen=self.entries.maxlen)
        invalid = 0
        for line in lines:
            if not line.strip():
                continue
            try:
                loaded.append(LogEntry.from_record(json.loads(line)))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                invalid += 1
        self.entries.extend(loaded)
        if invalid:
            self.storage_error = "运行日志中有 %d 行无法读取" % invalid

    def _append_to_file(self, entry):
        if self.log_path is None:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8", newline="\n") as target:
                target.write(json.dumps(entry.as_record(), ensure_ascii=False,
                                        separators=(",", ":")) + "\n")
        except OSError as error:
            self.storage_error = "运行日志保存失败：%s" % error

    def add(self, category, message, level="信息"):
        entry = LogEntry(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            category,
            level,
            str(message),
        )
        self.entries.append(entry)
        self._append_to_file(entry)
        self.added.emit(entry)
        return entry

    def clear(self):
        self.entries.clear()
        if self.log_path is not None:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                self.log_path.write_text("", encoding="utf-8")
            except OSError as error:
                self.storage_error = "运行日志清空失败：%s" % error
        self.cleared.emit()
