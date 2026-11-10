"""运行日志存储与 Qt 主线程通知适配。"""

import inspect
import json
import threading
from collections import deque
from contextlib import suppress
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.features.logs.data import (
    _LOG_HEADER_RE,
    DEFAULT_LOG_LEVEL,
    LOG_LEVELS,
    LogEntry,
    LogLevel,
    normalize_log_level,
)
from app.shared.logs.levels import FORCED_LEVEL


class LogStore(QObject):
    """运行日志的内存队列与文件同步。

    列表最多保留 ``limit`` 条，超出后丢弃最早记录；文件按时间顺序追加，
    删除或清空时整体重写，保证界面与文件内容一致。
    """

    added = Signal(object)
    removed = Signal(object)
    cleared = Signal()
    levelChanged = Signal(str)
    _notificationReady = Signal()

    def __init__(self, parent=None, limit=2000, log_path=None, minimum_level=None):
        super().__init__(parent)
        self._log_path = None
        self._file_handle = None
        self._lock = threading.RLock()
        # 写盘异常会在持锁期间关闭句柄，文件锁必须允许同一线程重入。
        self._file_lock = threading.RLock()
        self._pending_notifications = deque()
        self._draining_notifications = False
        self._notificationReady.connect(self._drain_notifications)
        self.log_path = log_path
        self.storage_error = ""
        self.entries = deque(maxlen=limit)
        # 调试版本固定记录全部等级，传入的等级与设置文件里的默认值都不作数；
        # 正常版本用默认等级，显式传入只供测试验证更低等级的记录格式。
        if FORCED_LEVEL:
            self._minimum_level = LogLevel(FORCED_LEVEL)
        elif minimum_level is None:
            self._minimum_level = DEFAULT_LOG_LEVEL
        else:
            self._minimum_level = normalize_log_level(minimum_level)
        self._next_uid = 1
        self._load()

    @property
    def minimum_level(self):
        """返回当前写入阈值。"""
        with self._lock:
            return self._minimum_level

    @property
    def log_path(self):
        """日志文件路径；改为 ``None`` 时关闭已打开的文件。"""
        with self._lock:
            return self._log_path

    @log_path.setter
    def log_path(self, value):
        with self._lock:
            self._close_file()
            self._log_path = Path(value) if value is not None else None

    def close(self):
        """关闭日志文件句柄并释放文件占用。"""
        with self._lock:
            self._close_file()

    def _close_file(self):
        """关闭持久写入句柄；下次写日志时按需重新打开。"""
        with self._file_lock:
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

        复用句柄并在每条写入后刷新文件缓冲，减少重复打开文件的开销。
        调用方持有状态锁，使内存追加、文件写入与通知入队保持相同顺序；
        句柄操作另用可重入锁保护，写入失败时释放句柄，供后续追加重试。
        """
        with self._file_lock:
            if self._log_path is None:
                return
            try:
                handle = self._file_handle
                if handle is None:
                    self._log_path.parent.mkdir(parents=True, exist_ok=True)
                    handle = self._log_path.open("a", encoding="utf-8", newline="\n")
                    self._file_handle = handle
                handle.write(entry.as_text() + "\n")
                handle.flush()
            except OSError as error:
                self.storage_error = "运行日志保存失败：%s" % error
                self._close_file()

    def _rewrite_file(self):
        """用当前记录整体覆盖日志文件；先写临时文件再替换，避免写坏原文件。"""
        with self._lock:
            if self._log_path is None:
                return
            # Windows 上被打开的文件无法整体替换，重写前先释放句柄。
            self._close_file()
            temp_path = Path(str(self._log_path) + ".tmp")
            try:
                self._log_path.parent.mkdir(parents=True, exist_ok=True)
                text = "\n".join(entry.as_text() for entry in self.entries)
                content = text + ("\n" if text else "")
                temp_path.write_text(content, encoding="utf-8")
                try:
                    temp_path.replace(self._log_path)
                except OSError:
                    # 别的实例可能仍持有该文件的追加句柄，整体替换会失败；
                    # 退回原地覆盖，追加句柄之后的写入依旧落在文件末尾。
                    self._log_path.write_text(content, encoding="utf-8")
                    temp_path.unlink(missing_ok=True)
            except OSError as error:
                self.storage_error = "运行日志更新失败：%s" % error
                with suppress(OSError):
                    temp_path.unlink(missing_ok=True)

    def _notify_changes(self):
        """请求在对象所属线程排空通知；调用方已在锁内登记变更。"""
        if QThread.currentThread() == self.thread():
            self._drain_notifications()
        else:
            self._notificationReady.emit()

    @Slot()
    def _drain_notifications(self):
        """在对象所属线程排空待发送的日志变更。"""
        if self._draining_notifications:
            return
        self._draining_notifications = True
        try:
            while True:
                with self._lock:
                    if not self._pending_notifications:
                        return
                    kind, payload = self._pending_notifications.popleft()
                if kind == "added":
                    self.added.emit(payload)
                elif kind == "removed":
                    self.removed.emit(payload)
                else:
                    self.cleared.emit()
        finally:
            self._draining_notifications = False

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
        # 低于阈值的记录不会落库，先判等级可以省掉一次调用栈回溯。
        if normalized.rank < self._minimum_level.rank:
            return None
        if logger_name is None:
            logger_name, captured_line = self._caller_location(skip)
            line_number = captured_line
        with self._lock:
            if normalized.rank < self._minimum_level.rank:
                return None
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
            self._pending_notifications.append(("added", entry))
        self._notify_changes()
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
        """修改写入阈值；等级未变化时不发信号。

        调试版本固定记录全部等级，任何改动都不生效；正常版本低于
        ``INFO`` 的请求按 ``INFO`` 处理。
        """
        if FORCED_LEVEL:
            return
        normalized = normalize_log_level(level)
        if normalized.rank < LOG_LEVELS[0].rank:
            normalized = LOG_LEVELS[0]
        with self._lock:
            if normalized == self._minimum_level:
                return
            self._minimum_level = normalized
        self.levelChanged.emit(str(normalized))

    def remove_entries(self, uids):
        """按 uid 删除记录并重写文件，返回实际删除的条目。"""
        selected = {int(uid) for uid in uids}
        with self._lock:
            removed = [entry for entry in self.entries if entry.uid in selected]
            if not removed:
                return []
            self.entries = deque(
                (entry for entry in self.entries if entry.uid not in selected),
                maxlen=self.entries.maxlen,
            )
            self._rewrite_file()
            self._pending_notifications.append(("removed", removed))
        self._notify_changes()
        return removed

    def snapshot_entries(self):
        """在线程安全的快照中返回当前日志记录。"""
        with self._lock:
            return tuple(self.entries)

    def export_text(self, entries=None):
        """导出为文本；不传参数时导出全部记录。"""
        if entries is None or entries is self.entries:
            entries = self.snapshot_entries()
        return "\n".join(entry.as_text() for entry in entries)

    def clear(self, persist=True):
        """清空全部记录，``persist`` 为真时同步清空日志文件。"""
        with self._lock:
            self.entries.clear()
            self.storage_error = ""
            if persist:
                self._rewrite_file()
            self._pending_notifications.append(("cleared", None))
        self._notify_changes()
