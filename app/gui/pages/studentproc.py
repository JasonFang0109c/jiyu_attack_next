"""结束学生端页：列出并结束本机极域学生端进程，结束前按需提权。"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QTableWidgetItem
from qfluentwidgets import BodyLabel, PushButton
from qfluentwidgets import FluentIcon as FIF

from ..components import SectionCard, page_heading
from .common import Page, table_widget

# 进程号、映像名与占用端口三列，端口是学生端收走回包的关键信息。
PROCESS_COLUMNS = ("进程号", "进程名", "占用端口")


class StudentProcessPage(Page):
    """展示本机学生端进程，并提供刷新与结束按钮。

    Attributes:
        processes: 当前列表里展示的进程记录，每项含 pid、name 与 ports。
    """

    refreshRequested = Signal()
    stopRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("studentproc", parent)
        self.processes = []
        page_heading(self.vbox, "结束学生端")
        hint = BodyLabel(
            "本机同时运行极域学生端时，它会独占教师端地址的 4705 端口，"
            "模拟教师端收不到学生的回包。先在这里结束学生端再启动常驻监听。",
            self,
        )
        hint.setWordWrap(True)
        self.vbox.addWidget(hint)

        self.content_card = SectionCard(self)
        row = QHBoxLayout()
        self.status = BodyLabel("尚未查询", self.content_card)
        row.addWidget(self.status)
        row.addStretch()
        self.refresh_button = PushButton(FIF.SYNC, "刷新进程列表", self.content_card)
        self.refresh_button.clicked.connect(lambda: self.refreshRequested.emit())
        row.addWidget(self.refresh_button)
        self.stop_button = PushButton(
            FIF.CANCEL_MEDIUM, "结束学生端", self.content_card
        )
        self.stop_button.clicked.connect(lambda: self.stopRequested.emit())
        self.stop_button.setEnabled(False)
        row.addWidget(self.stop_button)
        self.content_card.body.addLayout(row)
        self.table = table_widget(list(PROCESS_COLUMNS), self.content_card)
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 220)
        self.content_card.body.addWidget(self.table, 1)
        self.vbox.addWidget(self.content_card, 1)

    def set_processes(self, processes):
        """填入进程列表，没有进程时禁用结束按钮。

        Args:
            processes: 每项含 ``pid``、``name`` 与 ``ports`` 的记录列表。
        """
        self.processes = list(processes or [])
        self.table.setRowCount(len(self.processes))
        for row, item in enumerate(self.processes):
            ports = "、".join(str(port) for port in item.get("ports") or []) or "-"
            self.table.setItem(row, 0, QTableWidgetItem(str(item.get("pid", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(item.get("name", "")))
            self.table.setItem(row, 2, QTableWidgetItem(ports))
            self.table.setRowHeight(row, 38)
        self.stop_button.setEnabled(bool(self.processes))
        self.status.setText(
            "共 %d 个学生端进程" % len(self.processes)
            if self.processes
            else "本机没有正在运行的学生端进程"
        )

    def set_busy(self, busy):
        """任务执行期间禁用按钮，避免重复触发。"""
        self.refresh_button.setEnabled(not busy)
        self.stop_button.setEnabled(not busy and bool(self.processes))
