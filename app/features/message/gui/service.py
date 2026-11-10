"""MessageService 的界面协调逻辑。"""

from pathlib import Path

from PySide6.QtCore import (
    Qt,
)
from PySide6.QtWidgets import QFileDialog


class MessageService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window

    def import_message(self):
        """从 UTF-8 文本文件导入消息正文。"""
        window = self.window
        filename, _ = QFileDialog.getOpenFileName(
            window, "导入消息", "", "文本文件 (*.txt *.md);;所有文件 (*)"
        )
        if not filename:
            window.logs.info("应用", "用户取消了消息导入")
            return
        try:
            with open(filename, encoding="utf-8-sig", newline="") as source:
                text = source.read()
            page = window.pages["message"]
            page.editor.setPlainText(text)
            page.filename.setText(
                page.filename.fontMetrics().elidedText(
                    Path(filename).name, Qt.ElideMiddle, 225
                )
            )
            page.filename.setToolTip(filename)
            window.logs.info(
                "应用", "消息文本已导入", "文件：%s；字符数：%d" % (filename, len(text))
            )
        except (OSError, UnicodeError) as error:
            window.logs.error(
                "应用", "导入消息失败", "文件：%s；异常：%s" % (filename, error)
            )
            window._notify("导入失败", str(error), "错误")

    def save_message(self):
        """把当前消息正文另存为 UTF-8 文本。"""
        window = self.window
        filename, _ = QFileDialog.getSaveFileName(
            window, "保存消息", "消息.txt", "文本文件 (*.txt)"
        )
        if filename:
            window._save_text(filename, window.pages["message"].editor.toPlainText())
        else:
            window.logs.info("应用", "用户取消了消息保存")
