"""界面会话参数、设备备注和运行记录。"""

from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
import inspect
import json
from pathlib import Path
import re
import sys
import threading

from PySide6.QtCore import QObject, QSettings, Signal

from cli import main as core


DATA_DIRECTORY_NAME = "JiYuAttackNextData"
SETTINGS_FILE_NAME = "settings.ini"
LOG_FILE_NAME = "runtime.log"
CLOSE_BEHAVIOR_SETTINGS_KEY = "window/close_behavior"
CLOSE_BEHAVIOR_TRAY = "tray"
CLOSE_BEHAVIOR_QUIT = "quit"
DEFAULT_CLOSE_BEHAVIOR = CLOSE_BEHAVIOR_TRAY
CLOSE_BEHAVIORS = (CLOSE_BEHAVIOR_TRAY, CLOSE_BEHAVIOR_QUIT)
CLOSE_BEHAVIOR_LABELS = {
    CLOSE_BEHAVIOR_TRAY: "保留在系统托盘",
    CLOSE_BEHAVIOR_QUIT: "直接退出",
}


def normalize_close_behavior(value):
    """把设置值转换为受支持的关闭窗口行为。"""
    text = str(value or "").strip()
    aliases = {
        CLOSE_BEHAVIOR_TRAY: CLOSE_BEHAVIOR_TRAY,
        CLOSE_BEHAVIOR_QUIT: CLOSE_BEHAVIOR_QUIT,
        CLOSE_BEHAVIOR_LABELS[CLOSE_BEHAVIOR_TRAY]: CLOSE_BEHAVIOR_TRAY,
        CLOSE_BEHAVIOR_LABELS[CLOSE_BEHAVIOR_QUIT]: CLOSE_BEHAVIOR_QUIT,
    }
    try:
        return aliases[text.casefold()]
    except KeyError as error:
        raise ValueError("关闭窗口行为无效：%s" % text) from error


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

    def clear(self, persist=True):
        """清空全部设备备注；需要时可跳过写入以配合数据目录删除。"""
        previous_names = tuple(self._aliases)
        previous_error = self.load_error
        if persist:
            self.load_error = ""
            try:
                self._save({})
            except OSError:
                self.load_error = previous_error
                raise
        else:
            self._aliases = {}
            self.load_error = ""
        for name in previous_names:
            self.removed.emit(name)
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


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

    @property
    def rank(self):
        return LOG_LEVEL_RANK[self]


LOG_LEVELS = tuple(LogLevel)
LOG_LEVEL_RANK = {level: index for index, level in enumerate(LOG_LEVELS)}
DEFAULT_LOG_LEVEL = LogLevel.INFO
_LEVEL_ALIASES = {
    "DEBUG": LogLevel.DEBUG,
    "调试": LogLevel.DEBUG,
    "INFO": LogLevel.INFO,
    "信息": LogLevel.INFO,
    "成功": LogLevel.INFO,
    "WARN": LogLevel.WARNING,
    "WARNING": LogLevel.WARNING,
    "警告": LogLevel.WARNING,
    "ERROR": LogLevel.ERROR,
    "错误": LogLevel.ERROR,
    "失败": LogLevel.ERROR,
}
_LOG_HEADER_RE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) "
    r"\[(?P<thread_id>\d+)\] \[(?P<thread_name>[^\]]+)\] "
    r"(?P<level>DEBUG|INFO|WARNING|ERROR)\s+"
    r"(?P<logger>[^:\s]+):(?P<line>\d+) - \[(?P<category>[^\]]*)\] "
    r"(?P<message>.*)$"
)


def normalize_log_level(level):
    """把新旧日志等级统一为规范中的 DEBUG|INFO|WARNING|ERROR。"""
    if isinstance(level, LogLevel):
        return level
    value = str(level).strip().upper()
    normalized = _LEVEL_ALIASES.get(value)
    if normalized is None:
        normalized = _LEVEL_ALIASES.get(str(level).strip())
    if normalized is None:
        raise ValueError("未知日志等级：%s" % level)
    return normalized


def normalize_log_time(value):
    """统一历史日志时间为带毫秒的本地时间文本。"""
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text
    return parsed.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


@dataclass(frozen=True)
class LogEntry:
    time: str
    category: str
    level: LogLevel
    message: str
    thread_id: int = 0
    thread_name: str = "MainThread"
    logger_name: str = "app.gui"
    line_number: int = 0
    details: str = ""
    uid: int = 0

    def as_text(self):
        lines = self.message.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        text = "%s [%d] [%s] %-7s %s:%d - [%s] %s" % (
            self.time,
            self.thread_id,
            self.thread_name,
            str(self.level),
            self.logger_name,
            self.line_number,
            self.category,
            lines[0],
        )
        continuation = ["    " + line for line in lines[1:]]
        if self.details:
            detail_lines = self.details.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            continuation.extend("    " + line for line in detail_lines)
        if continuation:
            text += "\n" + "\n".join(continuation)
        return text

    def as_record(self):
        return {
            "time": self.time,
            "category": self.category,
            "level": str(self.level),
            "message": self.message,
            "thread_id": self.thread_id,
            "thread_name": self.thread_name,
            "logger_name": self.logger_name,
            "line_number": self.line_number,
            "details": self.details,
        }

    @classmethod
    def from_record(cls, record):
        if not isinstance(record, dict):
            raise ValueError("日志记录格式无效")
        return cls(
            normalize_log_time(record["time"]),
            str(record["category"]),
            normalize_log_level(record["level"]),
            str(record["message"]),
            int(record.get("thread_id") or 0),
            str(record.get("thread_name") or "MainThread"),
            str(record.get("logger_name") or record.get("source") or "app.gui"),
            int(record.get("line_number") or record.get("line") or 0),
            str(record.get("details") or ""),
        )

    @classmethod
    def from_text(cls, block):
        lines = block.splitlines()
        if not lines:
            raise ValueError("日志记录为空")
        match = _LOG_HEADER_RE.match(lines[0])
        if match is None:
            raise ValueError("日志记录格式无效")
        message_lines = [match.group("message")]
        for line in lines[1:]:
            message_lines.append(line[4:] if line.startswith("    ") else line)
        return cls(
            match.group("time"),
            match.group("category"),
            normalize_log_level(match.group("level")),
            "\n".join(message_lines),
            int(match.group("thread_id")),
            match.group("thread_name"),
            match.group("logger"),
            int(match.group("line")),
        )


class LogStore(QObject):
    added = Signal(object)
    removed = Signal(object)
    cleared = Signal()
    levelChanged = Signal(str)

    def __init__(self, parent=None, limit=2000, log_path=None, minimum_level=DEFAULT_LOG_LEVEL):
        super().__init__(parent)
        self.log_path = Path(log_path) if log_path is not None else None
        self.storage_error = ""
        self.entries = deque(maxlen=limit)
        self._minimum_level = normalize_log_level(minimum_level)
        self._next_uid = 1
        self._load()

    @property
    def minimum_level(self):
        return self._minimum_level

    def _load(self):
        if self.log_path is None or not self.log_path.exists():
            return
        try:
            lines = self.log_path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError) as error:
            self.storage_error = "运行日志读取失败：%s" % error
            return
        parsed = []
        pending = []
        invalid = 0
        migrated = False

        def flush_pending():
            nonlocal invalid
            if not pending:
                return
            try:
                parsed.append(LogEntry.from_text("\n".join(pending)))
            except (TypeError, ValueError):
                invalid += 1
            pending.clear()

        for line in lines:
            if not line.strip():
                if pending:
                    pending.append("")
                continue
            if line.startswith("{"):
                flush_pending()
                try:
                    parsed.append(LogEntry.from_record(json.loads(line)))
                    migrated = True
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    invalid += 1
            elif _LOG_HEADER_RE.match(line):
                flush_pending()
                pending.append(line)
            elif pending:
                pending.append(line)
            else:
                invalid += 1
        flush_pending()

        for entry in parsed:
            self.entries.append(replace(entry, uid=self._next_uid))
            self._next_uid += 1
        if migrated:
            self._rewrite_file()
        if invalid:
            self.storage_error = "运行日志中有 %d 条记录无法读取" % invalid

    @staticmethod
    def _caller_location(skip):
        frame = inspect.currentframe()
        try:
            for _ in range(skip):
                if frame is None:
                    break
                frame = frame.f_back
            if frame is None:
                return "app.gui", 0
            module = frame.f_globals.get("__name__", "app.gui")
            owner = frame.f_locals.get("self")
            if owner is not None:
                qualname = type(owner).__qualname__
            else:
                qualname = frame.f_code.co_name
            return "%s.%s" % (module, qualname), frame.f_lineno
        finally:
            del frame

    def _append_to_file(self, entry):
        if self.log_path is None:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8", newline="\n") as target:
                target.write(entry.as_text() + "\n")
        except OSError as error:
            self.storage_error = "运行日志保存失败：%s" % error

    def _rewrite_file(self):
        if self.log_path is None:
            return
        temp_path = Path(str(self.log_path) + ".tmp")
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            text = "\n".join(entry.as_text() for entry in self.entries)
            temp_path.write_text(text + ("\n" if text else ""), encoding="utf-8")
            temp_path.replace(self.log_path)
        except OSError as error:
            self.storage_error = "运行日志更新失败：%s" % error
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _emit(self, category, message, level, details="", logger_name=None,
              line_number=None, skip=3):
        normalized = normalize_log_level(level)
        if normalized.rank < self._minimum_level.rank:
            return None
        if logger_name is None:
            logger_name, captured_line = self._caller_location(skip)
            line_number = captured_line
        entry = LogEntry(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            str(category),
            normalized,
            str(message),
            threading.get_ident(),
            threading.current_thread().name,
            str(logger_name or "app.gui"),
            int(line_number or 0),
            str(details or ""),
            self._next_uid,
        )
        self._next_uid += 1
        self.entries.append(entry)
        self._append_to_file(entry)
        self.added.emit(entry)
        return entry

    def add(self, category, message, level=DEFAULT_LOG_LEVEL, details="",
            *, logger_name=None, line_number=None):
        return self._emit(category, message, level, details, logger_name,
                          line_number, skip=3)

    def debug(self, category, message, details=""):
        return self._emit(category, message, LogLevel.DEBUG, details,
                          skip=3)

    def info(self, category, message, details=""):
        return self._emit(category, message, LogLevel.INFO, details,
                          skip=3)

    def warning(self, category, message, details=""):
        return self._emit(category, message, LogLevel.WARNING, details,
                          skip=3)

    def error(self, category, message, details=""):
        return self._emit(category, message, LogLevel.ERROR, details,
                          skip=3)

    def set_level(self, level):
        normalized = normalize_log_level(level)
        if normalized == self._minimum_level:
            return
        self._minimum_level = normalized
        self.levelChanged.emit(str(normalized))

    def remove_entries(self, uids):
        selected = {int(uid) for uid in uids}
        removed = [entry for entry in self.entries if entry.uid in selected]
        if not removed:
            return []
        self.entries = deque(
            (entry for entry in self.entries if entry.uid not in selected),
            maxlen=self.entries.maxlen,
        )
        self._rewrite_file()
        self.removed.emit(removed)
        return removed

    def export_text(self, entries=None):
        source = self.entries if entries is None else entries
        return "\n".join(entry.as_text() for entry in source)

    def clear(self, persist=True):
        self.entries.clear()
        self.storage_error = ""
        if persist:
            self._rewrite_file()
        self.cleared.emit()
