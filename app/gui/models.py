"""界面会话参数、设备备注和运行记录。"""

import inspect
import json
import re
import sys
import threading
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from PySide6.QtCore import QObject, Signal

from .. import core

# 这些名字由本模块转出给界面层，导入后即被其它模块引用。
from ..core import (  # noqa: F401
    DATA_DIRECTORY_NAME,
    LOG_FILE_NAME,
    portable_data_dir,
    portable_log_path,
)
from .settings_store import STATUS_NO_ERROR, SettingsStore

SETTINGS_FILE_NAME = "settings.json"
DEVICE_ALIAS_SETTINGS_KEY = "core/device_aliases"
CLOSE_BEHAVIOR_SETTINGS_KEY = "gui/window/close_behavior"
FIRST_CLOSE_PROMPT_SETTINGS_KEY = "gui/window/first_close_prompt_shown"
WINDOW_GEOMETRY_SETTINGS_KEY = "gui/window/geometry"
WINDOW_MATERIAL_SETTINGS_KEY = "gui/window/material"
# 旧版本只有“背景模糊”开关，保留键名用于把老配置换算成窗口材质。
MICA_SETTINGS_KEY = "gui/window/mica_enabled"
MATERIAL_MICA = "mica"
MATERIAL_ACRYLIC = "acrylic"
MATERIAL_SOLID = "solid"
WINDOW_MATERIALS = (MATERIAL_MICA, MATERIAL_ACRYLIC, MATERIAL_SOLID)
WINDOW_MATERIAL_LABELS = {
    MATERIAL_MICA: "Mica（云母）",
    MATERIAL_ACRYLIC: "Acrylic（亚克力）",
    MATERIAL_SOLID: "纯色（无材质）",
}
DEFAULT_WINDOW_MATERIAL = MATERIAL_MICA
SWITCH_TRUE_VALUES = ("true", "1", "yes", "on")
SWITCH_FALSE_VALUES = ("false", "0", "no", "off")
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


def normalize_switch(value, default):
    """把设置里的开关值转换为布尔值，无法识别时退回默认值。

    Args:
        value: 从 ``settings.json`` 读出的原始值，可能是布尔、字符串或 ``None``。
        default: 配置缺失或格式非法时使用的默认状态。

    Returns:
        bool: 归一化后的开关状态。
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().casefold()
    if text in SWITCH_TRUE_VALUES:
        return True
    if text in SWITCH_FALSE_VALUES:
        return False
    return default


def _windows_build():
    """返回 Windows 内部版本号，非 Windows 系统返回 0。"""
    if sys.platform != "win32":
        return 0
    try:
        return sys.getwindowsversion().build
    except (AttributeError, ValueError):
        return 0


def mica_available():
    """判断当前系统能否给窗口加上云母材质。

    云母由 DWM 按桌面壁纸采样，只在 Windows 11（build 22000）及以上提供。

    Returns:
        bool: 系统支持云母时为 ``True``。
    """
    return _windows_build() >= 22000


def acrylic_available():
    """判断当前系统能否给窗口加上亚克力材质。

    亚克力由 DWM 实时模糊窗口下方的内容，从 Windows 10 1809（build 17763）
    开始提供，比云母的适用范围更宽。

    Returns:
        bool: 系统支持亚克力时为 ``True``。
    """
    return _windows_build() >= 17763


def window_material_available(material):
    """判断某个窗口材质在当前系统上是否可用。

    Args:
        material: ``WINDOW_MATERIALS`` 中的材质标识。

    Returns:
        bool: 该材质可用时为 ``True``；纯色不依赖系统能力，恒为 ``True``。
    """
    if material == MATERIAL_MICA:
        return mica_available()
    if material == MATERIAL_ACRYLIC:
        return acrylic_available()
    return material == MATERIAL_SOLID


def normalize_window_material(value, legacy_switch=None):
    """把设置值转换为受支持的窗口材质。

    Args:
        value: 从 ``settings.json`` 读出的材质标识或显示名。
        legacy_switch: 旧版“背景模糊”开关状态；只在 ``value`` 缺失时使用，
            ``True`` 视为云母，``False`` 视为纯色。

    Returns:
        str: ``WINDOW_MATERIALS`` 中的材质标识，无法识别时退回默认材质。
    """
    text = str(value or "").strip().casefold()
    for material in WINDOW_MATERIALS:
        if text in (material, WINDOW_MATERIAL_LABELS[material].casefold()):
            return material
    if value is None and legacy_switch is not None:
        return MATERIAL_MICA if legacy_switch else MATERIAL_SOLID
    return DEFAULT_WINDOW_MATERIAL


def portable_settings(data_dir=None):
    """返回便携设置对象，配置文件位于数据目录下的 settings.json。"""
    root = Path(data_dir).resolve() if data_dir is not None else portable_data_dir()
    return SettingsStore(root / SETTINGS_FILE_NAME)


class DeviceAliasStore(QObject):
    """保存可复用的 IPv4 设备备注。"""

    changed = Signal()
    renamed = Signal(str, str)
    removed = Signal(str)
    SETTINGS_KEY = DEVICE_ALIAS_SETTINGS_KEY
    MAX_NAME_LENGTH = 64

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self._settings = settings if settings is not None else portable_settings()
        self._aliases = {}
        self.load_error = ""
        self._load()

    def _load(self):
        """从设置文件读取备注；数据损坏时记录原因并保留空表。"""
        raw = self._settings.value(self.SETTINGS_KEY, {})
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
        """校验备注名：非空、不超长、不含换行或 NUL，且不能是 IP 地址。"""
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
            # 备注名不能与地址混淆，这里只校验格式，不展开地址列表。
            core.count_targets(value)
        except ValueError:
            return value
        raise ValueError("备注名不能使用 IP 地址格式")

    @staticmethod
    def _normalize_address(address):
        """校验地址；单地址规范化为点分形式，范围与 /24 保留原写法。"""
        value = str(address).strip()
        if not value:
            raise ValueError("请填写 IP 地址")
        try:
            hosts = core.get_ip(value)
        except ValueError as error:
            raise ValueError(
                "IP 地址格式错误，请填写单个 IPv4 地址、末段范围或 /24 网段"
            ) from error
        return value if "-" in value or "/" in value else hosts[0]

    def names(self):
        """返回全部备注名，顺序与添加顺序一致。"""
        return list(self._aliases)

    def items(self):
        """返回 (备注名, 地址) 列表，供下拉框与表格使用。"""
        return list(self._aliases.items())

    def _find_name(self, name):
        """按不区分大小写的方式查找已存在的备注名。"""
        key = str(name).strip().casefold()
        for existing in self._aliases:
            if existing.casefold() == key:
                return existing
        return None

    def match(self, target):
        """备注名命中时返回 (备注名, 地址)，否则返回 None。"""
        value = str(target).strip()
        key = value.casefold()
        for name, address in self._aliases.items():
            if name.casefold() == key:
                return name, address
        return None

    def resolve(self, target):
        """把备注名换成地址，未命中时原样返回输入。"""
        matched = self.match(target)
        return matched[1] if matched else str(target).strip()

    def format_target(self, target):
        """返回“备注名（地址）”的展示文本，未命中时原样返回。"""
        matched = self.match(target)
        if matched:
            return "%s（%s）" % matched
        return str(target).strip()

    def _save(self, aliases):
        """写入设置文件；读取阶段出错时拒绝写入，避免覆盖原数据。"""
        if self.load_error:
            raise OSError(
                "%s；为避免覆盖原数据，请先修复或清除该配置项" % self.load_error
            )
        self._settings.set_value(self.SETTINGS_KEY, dict(aliases))
        self._settings.sync()
        if self._settings.status() != STATUS_NO_ERROR:
            raise OSError(
                "设备备注保存失败：%s" % (self._settings.message or "写入失败")
            )
        self._aliases = aliases

    def add(self, name, address):
        """新增一条备注，重名或地址非法时抛出 ValueError。"""
        normalized_name = self._normalize_name(name)
        normalized_address = self._normalize_address(address)
        if self._find_name(normalized_name) is not None:
            raise ValueError("备注名已存在")
        aliases = dict(self._aliases)
        aliases[normalized_name] = normalized_address
        self._save(aliases)
        self.changed.emit()

    def update(self, original_name, name, address):
        """修改备注；改名时额外发出 renamed 信号，供页面同步引用。"""
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
        """删除一条备注，不存在时抛出 ValueError。"""
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

    def restore(self, values):
        """从快照恢复会话参数，未知键会被忽略。"""
        for name, value in values.items():
            if name in self.DEFAULTS:
                self.set_value(name, value)

    def options(self, **payload):
        """组装发送参数，自动把备注名解析成地址。"""
        values = self.values.copy()
        values["target"] = self.resolve_target(values["target"])
        values.update(payload)
        return core.SendOptions(**values)


class LogLevel(StrEnum):
    """运行日志等级，数值越大越严重。

    等级是写入阈值：低于阈值的记录既不进列表也不写文件。
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

    @property
    def rank(self):
        """返回等级序号，用于比较严重程度。"""
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
    """一条运行日志记录。"""

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
        """按日志文件格式输出单条记录，多行内容缩进续行。"""
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
            detail_lines = (
                self.details.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            )
            continuation.extend("    " + line for line in detail_lines)
        if continuation:
            text += "\n" + "\n".join(continuation)
        return text

    @classmethod
    def from_record(cls, record):
        """从旧版 JSONL 记录还原；字段缺失时用默认值补齐。"""
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
        """按规范文本格式解析一段记录，续行按四空格缩进还原。"""
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
    """运行日志的内存队列与文件同步。

    列表最多保留 ``limit`` 条，超出后丢弃最早记录；文件按时间顺序追加，
    删除或清空时整体重写，保证界面与文件内容一致。
    """

    added = Signal(object)
    removed = Signal(object)
    cleared = Signal()
    levelChanged = Signal(str)

    def __init__(
        self, parent=None, limit=2000, log_path=None, minimum_level=DEFAULT_LOG_LEVEL
    ):
        super().__init__(parent)
        self._log_path = None
        self._file_handle = None
        self.log_path = log_path
        self.storage_error = ""
        self.entries = deque(maxlen=limit)
        self._minimum_level = normalize_log_level(minimum_level)
        self._next_uid = 1
        self._load()

    @property
    def minimum_level(self):
        """返回当前写入阈值。"""
        return self._minimum_level

    @property
    def log_path(self):
        """日志文件路径；改为 ``None`` 时关闭已打开的文件。"""
        return self._log_path

    @log_path.setter
    def log_path(self, value):
        self._close_file()
        self._log_path = Path(value) if value is not None else None

    def close(self):
        """释放日志文件句柄；每行都已刷盘，关闭只影响句柄占用。"""
        self._close_file()

    def _close_file(self):
        """关闭持久写入句柄；下次写日志时按需重新打开。"""
        handle = self._file_handle
        self._file_handle = None
        if handle is None:
            return
        with suppress(OSError):
            handle.close()

    def _load(self):
        """读取历史日志；旧版 JSONL 记录会被转换成规范文本。"""
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
            """把暂存的规范文本行解析成一条记录。"""
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
        """沿调用栈上溯，返回“模块.类名”与行号，便于从日志定位代码。"""
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
        """按时间顺序追加一行；写失败只记录状态，不打断任务。

        句柄跨条复用并在每条之后刷盘：重新打开文件比写一行本身贵两个数量级，
        逐条刷盘仍能保证进程异常退出时已写入的记录不会丢。
        """
        if self.log_path is None:
            return
        try:
            handle = self._file_handle
            if handle is None:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                handle = self.log_path.open("a", encoding="utf-8", newline="\n")
                self._file_handle = handle
            handle.write(entry.as_text() + "\n")
            handle.flush()
        except OSError as error:
            self.storage_error = "运行日志保存失败：%s" % error
            self._close_file()

    def _rewrite_file(self):
        """用当前记录整体覆盖日志文件；先写临时文件再替换，避免写坏原文件。"""
        if self.log_path is None:
            return
        # Windows 上被打开的文件无法整体替换，重写前先释放句柄。
        self._close_file()
        temp_path = Path(str(self.log_path) + ".tmp")
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            text = "\n".join(entry.as_text() for entry in self.entries)
            content = text + ("\n" if text else "")
            temp_path.write_text(content, encoding="utf-8")
            try:
                temp_path.replace(self.log_path)
            except OSError:
                # 别的实例可能仍持有该文件的追加句柄，整体替换会失败；
                # 退回原地覆盖，追加句柄之后的写入依旧落在文件末尾。
                self.log_path.write_text(content, encoding="utf-8")
                temp_path.unlink(missing_ok=True)
        except OSError as error:
            self.storage_error = "运行日志更新失败：%s" % error
            with suppress(OSError):
                temp_path.unlink(missing_ok=True)

    def _emit(
        self,
        category,
        message,
        level,
        details="",
        logger_name=None,
        line_number=None,
        skip=3,
    ):
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

    def add(
        self,
        category,
        message,
        level=DEFAULT_LOG_LEVEL,
        details="",
        *,
        logger_name=None,
        line_number=None,
    ):
        """写入一条指定等级的记录。"""
        return self._emit(
            category, message, level, details, logger_name, line_number, skip=3
        )

    def debug(self, category, message, details=""):
        """写入调试记录，用于参数快照与进度细节。"""
        return self._emit(category, message, LogLevel.DEBUG, details, skip=3)

    def info(self, category, message, details=""):
        """写入信息记录，用于启动、关键操作与任务完成。"""
        return self._emit(category, message, LogLevel.INFO, details, skip=3)

    def warning(self, category, message, details=""):
        """写入警告记录，用于可恢复异常与用户取消。"""
        return self._emit(category, message, LogLevel.WARNING, details, skip=3)

    def error(self, category, message, details=""):
        """写入错误记录，用于任务失败与异常。"""
        return self._emit(category, message, LogLevel.ERROR, details, skip=3)

    def set_level(self, level):
        """修改写入阈值；等级未变化时不发信号。"""
        normalized = normalize_log_level(level)
        if normalized == self._minimum_level:
            return
        self._minimum_level = normalized
        self.levelChanged.emit(str(normalized))

    def remove_entries(self, uids):
        """按 uid 删除记录并重写文件，返回实际删除的条目。"""
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
        """导出为文本；不传参数时导出全部记录。"""
        source = self.entries if entries is None else entries
        return "\n".join(entry.as_text() for entry in source)

    def clear(self, persist=True):
        """清空全部记录，``persist`` 为真时同步清空日志文件。"""
        self.entries.clear()
        self.storage_error = ""
        if persist:
            self._rewrite_file()
        self.cleared.emit()
