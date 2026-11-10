"""运行日志的等级、值对象与历史格式解析。"""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.shared.logs.levels import DEFAULT_LEVEL, SELECTABLE_LEVELS


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


LOG_LEVEL_RANK = {level: index for index, level in enumerate(LogLevel)}

LOG_LEVELS = tuple(LogLevel(name) for name in SELECTABLE_LEVELS)

DEFAULT_LOG_LEVEL = LogLevel(DEFAULT_LEVEL)

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
