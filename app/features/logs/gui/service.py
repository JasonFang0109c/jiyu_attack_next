"""LogService 的界面协调逻辑。"""

import threading

from PySide6.QtWidgets import QFileDialog

from app.features.logs.data import LogLevel, normalize_log_level
from app.gui.window.data import APP_NAME
from app.shared.build_info import version_text


class LogService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window

    def _configure_file_logging(self):
        """启动时写入本次运行环境，便于从日志复现问题。"""
        window = self.window
        window.logs.add(
            "运行日志",
            "日志系统已初始化",
            LogLevel.INFO,
            "日志文件：%s；线程：%s；GUI 版本：%s %s"
            % (
                window.logs.log_path or "未启用",
                threading.current_thread().name,
                APP_NAME,
                version_text(),
            ),
        )

    def export_selected_logs(self, entries):
        """把选中的日志记录导出为文本文件。"""
        window = self.window
        filename, _ = QFileDialog.getSaveFileName(
            window, "导出选中日志", "运行日志-选中.txt", "文本文件 (*.txt)"
        )
        if filename:
            window._save_text(filename, window.pages["logs"].export_text(entries))
        else:
            window.logs.info(
                "运行日志", "用户取消了日志导出", "待导出记录数：%d" % len(entries)
            )

    def delete_selected_logs(self, uids):
        """确认后删除选中日志，并同步重写日志文件。"""
        window = self.window
        if not uids:
            window.logs.warning("运行日志", "未勾选日志记录，无法删除")
            return
        if not window._confirm(
            "删除选中日志",
            "确定删除选中的 %d 条运行日志？此操作会同步更新日志文件。" % len(uids),
        ):
            window.logs.info(
                "运行日志", "用户取消了日志删除", "待删除记录数：%d" % len(uids)
            )
            return
        removed = window.logs.remove_entries(uids)
        window.logs.info("运行日志", "已删除选中日志", "删除记录数：%d" % len(removed))

    def set_log_level(self, level):
        """切换运行日志等级，低于该等级的记录不再写入。"""
        window = self.window
        previous = window.logs.minimum_level
        normalized = normalize_log_level(level)
        window.logs.warning(
            "运行日志",
            "运行日志等级已调整",
            "原等级：%s；新等级：%s" % (previous, normalized),
        )
        window.logs.set_level(normalized)
