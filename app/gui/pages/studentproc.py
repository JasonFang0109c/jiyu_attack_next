"""启停学生端页：列出本机极域学生端，并用一个按钮按当前状态启动或结束。"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QTableWidgetItem
from qfluentwidgets import BodyLabel, LineEdit, PushButton
from qfluentwidgets import FluentIcon as FIF

from ..components import SectionCard, page_heading
from .common import Page, table_widget

# 进程号、映像名、占用端口与程序路径：端口是被独占的关键信息，
# 路径用来判断这个 StudentMain.exe 是不是极域真身。
PROCESS_COLUMNS = ("进程号", "进程名", "占用端口", "路径")

# 同一个按钮的两个状态：标签、图标与提示都跟着变。
START_LABEL = "启动学生端"
START_ICON = FIF.PLAY
START_HINT = "本机没有学生端在运行，点一下以管理员权限启动它，恢复极域课堂管理"
STOP_LABEL = "结束学生端"
STOP_ICON = FIF.CANCEL_MEDIUM
STOP_HINT = "学生端正在运行，点一下结束它，腾出被它独占的 4705 端口"


class StudentProcessPage(Page):
    """展示本机学生端进程，按钮按运行状态在启动与结束之间切换。

    Attributes:
        processes: 当前列表里展示的进程记录，每项含 pid、name、ports、
            path 与 genuine。
    """

    refreshRequested = Signal()
    toggleRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("studentproc", parent)
        self.processes = []
        page_heading(self.vbox, "启停学生端")
        hint = BodyLabel(
            "本机同时运行极域学生端时，它会独占教师端地址的 4705 端口，"
            "模拟教师端收不到学生的回包；需要恢复极域的课堂管理时又要把它拉起来。"
            "下面的按钮会按当前状态自动决定启动还是结束，必要时弹出管理员授权。",
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
        self.content_card.body.addLayout(row)

        action_row = QHBoxLayout()
        self.exe_input = LineEdit(self.content_card)
        self.exe_input.setPlaceholderText(
            "留空则自动查找 StudentMain.exe，也可以填完整路径"
        )
        self.exe_input.setClearButtonEnabled(True)
        action_row.addWidget(self.exe_input, 1)
        self.toggle_button = PushButton(START_ICON, START_LABEL, self.content_card)
        self.toggle_button.setToolTip(START_HINT)
        self.toggle_button.clicked.connect(lambda: self.toggleRequested.emit())
        action_row.addWidget(self.toggle_button)
        self.content_card.body.addLayout(action_row)

        self.table = table_widget(list(PROCESS_COLUMNS), self.content_card)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 190)
        self.table.setColumnWidth(2, 150)
        self.content_card.body.addWidget(self.table, 1)
        self.vbox.addWidget(self.content_card, 1)

    def exe_path(self):
        """返回手动填写的学生端路径，留空时返回 None。"""
        return self.exe_input.text().strip() or None

    def is_running(self):
        """本机是否有学生端在运行，决定按钮当前表示启动还是结束。"""
        return bool(self.processes)

    def _update_toggle(self, busy=False):
        """按运行状态刷新按钮文案、图标与可用性。"""
        running = self.is_running()
        label = STOP_LABEL if running else START_LABEL
        icon = STOP_ICON if running else START_ICON
        self.toggle_button.setText(label)
        self.toggle_button.setIcon(icon)
        hint = STOP_HINT if running else START_HINT
        self.toggle_button.setToolTip(hint)
        self.toggle_button.setAccessibleName(label)
        self.toggle_button.setEnabled(not busy)
        # 运行中不允许改路径，避免按钮歧义。
        self.exe_input.setEnabled(not busy and not running)

    def set_processes(self, processes):
        """填入进程列表，并让按钮切换到与状态相符的动作。

        Args:
            processes: 每项含 ``pid``、``name``、``ports`` 的记录列表。
        """
        self.processes = list(processes or [])
        self.table.setRowCount(len(self.processes))
        for row, item in enumerate(self.processes):
            ports = "、".join(str(port) for port in item.get("ports") or []) or "-"
            self.table.setItem(row, 0, QTableWidgetItem(str(item.get("pid", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(item.get("name", "")))
            self.table.setItem(row, 2, QTableWidgetItem(ports))
            path = item.get("path") or "不可读（试试点刷新）"
            if item.get("path") and not item.get("genuine"):
                path += "（同目录没有 LibTDMaster.dll）"
            self.table.setItem(row, 3, QTableWidgetItem(path))
            self.table.setRowHeight(row, 38)
        self.status.setText(
            "共 %d 个学生端进程" % len(self.processes)
            if self.processes
            else "本机没有正在运行的学生端进程"
        )
        self._update_toggle()

    def set_busy(self, busy):
        """任务执行期间禁用按钮，避免重复触发。"""
        self.refresh_button.setEnabled(not busy)
        self._update_toggle(busy)
