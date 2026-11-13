"""启停学生端页：列出本机极域学生端，按状态启动或结束，并可直接指定程序位置。"""

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QTableWidgetItem
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    LineEdit,
    PushButton,
    isDarkTheme,
    setFont,
)
from qfluentwidgets import FluentIcon as FIF

from app.features.student.data import STUDENT_PORT
from app.gui.widgets.common import SectionCard, page_heading, tool_button
from app.gui.widgets.page import Page, table_widget

# 进程号、映像名、占用端口与程序路径：端口是被独占的关键信息，
# 路径用来判断这个 StudentMain.exe 是不是极域真身。
PROCESS_COLUMNS = ("进程号", "进程名", "占用端口", "程序路径")

# 同一个按钮的两个状态：标签、图标与提示都跟着变。
START_LABEL = "启动学生端"
START_ICON = FIF.PLAY
START_HINT = "本机没有学生端在运行，点一下启动它，恢复极域课堂管理"
STOP_LABEL = "结束学生端"
STOP_ICON = FIF.CANCEL_MEDIUM
STOP_HINT = "学生端正在运行，点一下结束它，腾出被它独占的 4705 端口"

# 状态行的语气色，沿用 Windows 状态提示的配色，深色主题另取一档。
COLOR_OK = "#107C10"
COLOR_WARNING = "#9D5D00"
COLOR_ERROR = "#C42B1C"
COLOR_NEUTRAL = "#605E5C"
DARK_COLORS = {
    COLOR_OK: "#6CCB5F",
    COLOR_WARNING: "#FCE100",
    COLOR_ERROR: "#FF99A4",
    COLOR_NEUTRAL: "#A0A0A0",
}


def _tone_color(color):
    """按当前主题返回状态色。"""
    return DARK_COLORS.get(color, color) if isDarkTheme() else color


class StudentProcessPage(Page):
    """展示本机学生端进程，按钮按运行状态在启动与结束之间切换。

    Attributes:
        processes: 当前列表里展示的进程记录，每项含 pid、name、ports、
            path、genuine 与 creation。
        port_owner: 占用 4705 的学生端进程号，0 表示没人占用。
        saved_path: 上次记住的程序路径，输入框留空时启动就用它。
    """

    toggleRequested = Signal()
    chooseRequested = Signal()
    locateRequested = Signal()
    forgetRequested = Signal()
    copyPathRequested = Signal()
    copyPortRequested = Signal()
    refreshRequested = Signal()
    # 双击某一行时把这一行的路径交给界面服务复制并写日志。
    rowPathRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__("studentproc", parent)
        self.processes = []
        self.port_owner = 0
        self.saved_path = ""
        page_heading(self.vbox, "启停学生端")
        hint = BodyLabel(
            "本机同时运行极域学生端时，它会独占教师端地址的 4705 端口，"
            "模拟教师端收不到学生的回包；需要恢复极域的课堂管理时又要把它拉起来。"
            "下面的按钮会按当前状态自动决定启动还是结束，必要时弹出管理员授权。",
            self,
        )
        hint.setWordWrap(True)
        self.vbox.addWidget(hint)

        # 状态卡片：一句话说明当前情况，右侧放刷新这类轻量操作。
        status_card = SectionCard(self, spacing=6)
        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.status_icon = BodyLabel("", status_card)
        setFont(self.status_icon, 14)
        status_row.addWidget(self.status_icon)
        self.status = BodyLabel("正在读取学生端状态…", status_card)
        self.status.setWordWrap(True)
        status_row.addWidget(self.status, 1)
        status_row.addWidget(
            tool_button(
                FIF.SYNC, "立即刷新状态", status_card, self.refreshRequested.emit
            )
        )
        status_card.body.addLayout(status_row)
        self.detail = CaptionLabel("", status_card)
        self.detail.setWordWrap(True)
        self.detail.hide()
        status_card.body.addWidget(self.detail)
        self.vbox.addWidget(status_card)

        self.content_card = SectionCard(self)
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.exe_input = LineEdit(self.content_card)
        self.exe_input.setPlaceholderText(
            "StudentMain.exe 的完整路径，留空则自动查找安装位置"
        )
        self.exe_input.setClearButtonEnabled(True)
        self.exe_input.setMinimumWidth(220)
        action_row.addWidget(self.exe_input, 1)
        self.choose_button = PushButton(FIF.FOLDER, "选择程序", self.content_card)
        self.choose_button.setToolTip("从磁盘上挑选 StudentMain.exe，选中后记住")
        self.choose_button.clicked.connect(lambda: self.chooseRequested.emit())
        action_row.addWidget(self.choose_button)
        self.locate_button = PushButton(FIF.SEARCH, "自动定位", self.content_card)
        self.locate_button.setToolTip(
            "按记住的路径、运行中的进程、卸载信息与常见安装目录查找"
        )
        self.locate_button.clicked.connect(lambda: self.locateRequested.emit())
        action_row.addWidget(self.locate_button)
        action_row.addWidget(
            tool_button(
                FIF.COPY,
                "复制程序路径",
                self.content_card,
                lambda: self.copyPathRequested.emit(),
            )
        )
        action_row.addWidget(
            tool_button(
                FIF.DELETE,
                "忘记记住的路径",
                self.content_card,
                lambda: self.forgetRequested.emit(),
            )
        )
        self.content_card.body.addLayout(action_row)

        table_row = QHBoxLayout()
        table_row.setSpacing(8)
        self.port_label = BodyLabel("目标端口 %d" % STUDENT_PORT, self.content_card)
        self.port_label.setToolTip(
            "学生端运行时独占该端口；复制它可以直接填到远程页面的端口框"
        )
        table_row.addWidget(self.port_label)
        table_row.addWidget(
            tool_button(
                FIF.COPY,
                "复制 %d 端口" % STUDENT_PORT,
                self.content_card,
                lambda: self.copyPortRequested.emit(),
            )
        )
        table_row.addStretch()
        self.toggle_button = PushButton(START_ICON, START_LABEL, self.content_card)
        self.toggle_button.setMinimumHeight(34)
        self.toggle_button.setMinimumWidth(128)
        self.toggle_button.setToolTip(START_HINT)
        self.toggle_button.clicked.connect(lambda: self.toggleRequested.emit())
        table_row.addWidget(self.toggle_button)
        self.content_card.body.addLayout(table_row)

        self.table = table_widget(list(PROCESS_COLUMNS), self.content_card)
        self.table.setColumnWidth(0, 96)
        self.table.setColumnWidth(1, 170)
        self.table.setColumnWidth(2, 140)
        self.table.setToolTip("双击一行可以复制它的程序路径")
        self.table.cellDoubleClicked.connect(self._copy_row)
        self.content_card.body.addWidget(self.table, 1)
        self.vbox.addWidget(self.content_card, 1)

    # ---- 数据 -------------------------------------------------------------

    def exe_path(self):
        """返回自己填写的学生端路径，留空时返回 None（交给自动查找）。"""
        text = self.exe_input.text().strip()
        if not text or text == self.saved_path:
            return None
        return text

    def manual_path(self):
        """返回输入框里的原始文本。"""
        return self.exe_input.text().strip()

    def is_running(self):
        """本机是否有学生端在运行，决定按钮当前表示启动还是结束。"""
        return bool(self.processes)

    def has_port_owner(self):
        """是否有学生端正占着 4705。"""
        return bool(self.port_owner)

    # ---- 状态刷新 ---------------------------------------------------------

    def _update_toggle(self, busy=False):
        """按运行状态刷新按钮文案、图标、提示与可用性。"""
        running = self.is_running()
        label = STOP_LABEL if running else START_LABEL
        self.toggle_button.setText(label)
        self.toggle_button.setIcon(STOP_ICON if running else START_ICON)
        self.toggle_button.setToolTip(STOP_HINT if running else START_HINT)
        self.toggle_button.setAccessibleName(label)
        self.toggle_button.setEnabled(not busy)
        # 运行中锁住路径，避免按钮含义随输入框一起变得模糊。
        for widget in (
            self.exe_input,
            self.choose_button,
            self.locate_button,
        ):
            widget.setEnabled(not busy and not running)

    def _set_status(self, text, tone=COLOR_NEUTRAL, icon="", detail=""):
        """更新状态行；``detail`` 为空时隐藏第二行。"""
        self.status_icon.setText(icon)
        self.status.setText(text)
        self.status.setStyleSheet("color: %s;" % _tone_color(tone))
        if detail:
            self.detail.setText(detail)
            self.detail.show()
        else:
            self.detail.hide()

    def set_snapshot(self, snapshot):
        """按一次完整状态快照刷新页面。

        Args:
            snapshot: ``student_status`` 的返回值，含 ``processes``、
                ``exe_path``、``saved_path``、``port`` 与 ``port_owner``；
                也接受旧式的进程列表。
        """
        if isinstance(snapshot, list):
            self.set_processes(snapshot)
            return
        snapshot = snapshot or {}
        self.saved_path = snapshot.get("saved_path") or ""
        # 用户正在输入时不要用设置里的旧值盖掉他刚敲的内容。
        if not self.exe_input.hasFocus() and not self.exe_input.text().strip():
            self.exe_input.setText(self.saved_path)
            self.exe_input.setCursorPosition(0)
        self.set_processes(
            snapshot.get("processes") or [],
            port_owner=snapshot.get("port_owner", 0),
            exe_path=snapshot.get("exe_path") or "",
        )

    def set_processes(self, processes, port_owner=None, exe_path=""):
        """填入进程列表，并让按钮切换到与状态相符的动作。

        Args:
            processes: 每项含 ``pid``、``name``、``ports`` 等字段的记录列表。
            port_owner: 占用 4705 的进程号；None 表示按列表自己判断。
            exe_path: 可执行文件路径，用于状态说明的第二行。
        """
        self.processes = list(processes or [])
        if port_owner is None:
            port_owner = next(
                (
                    item["pid"]
                    for item in self.processes
                    if STUDENT_PORT in (item.get("ports") or [])
                ),
                0,
            )
        self.port_owner = int(port_owner or 0)
        self.table.setRowCount(len(self.processes))
        for row, item in enumerate(self.processes):
            ports = "、".join(str(port) for port in item.get("ports") or []) or "-"
            path = item.get("path") or "不可读（需要管理员权限）"
            if item.get("path") and not item.get("genuine"):
                path += "（同目录没有 LibTDMaster.dll）"
            values = (str(item.get("pid", "")), item.get("name", ""), ports, path)
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                if column == 2 and STUDENT_PORT in (item.get("ports") or []):
                    # 4705 被占用就是本页存在的理由，单独标出来。
                    cell.setForeground(QColor(_tone_color(COLOR_ERROR)))
                self.table.setItem(row, column, cell)
            self.table.setRowHeight(row, 38)
        self._refresh_status(exe_path)

    def _refresh_status(self, exe_path=""):
        """按进程、端口与路径三样事实写状态说明。"""
        count = len(self.processes)
        if not count:
            self._set_status(
                "本机没有正在运行的学生端进程，%d 端口已腾出" % STUDENT_PORT,
                COLOR_OK,
                "✓",
                "点“启动学生端”可以重新把它拉起来，恢复极域课堂管理。",
            )
        else:
            decoys = [item for item in self.processes if not item.get("genuine")]
            if self.port_owner:
                text = "学生端正在运行（PID %d），已独占 %d 端口" % (
                    self.port_owner,
                    STUDENT_PORT,
                )
                tone, icon = COLOR_ERROR, "●"
            else:
                text = "检测到 %d 个学生端进程，但都没有占用 %d" % (
                    count,
                    STUDENT_PORT,
                )
                tone, icon = COLOR_WARNING, "!"
            detail = "共 %d 个学生端进程" % count
            if decoys:
                detail += (
                    "；其中 %d 个目录里没有 LibTDMaster.dll，可能不是极域学生端"
                    % len(decoys)
                )
            path = exe_path or next(
                (item.get("path") for item in self.processes if item.get("path")), ""
            )
            if path:
                detail += "。程序位置：%s" % path
            self._set_status(text, tone, icon, detail)
        self._update_toggle()

    def set_busy(self, busy):
        """任务执行期间禁用按钮，避免重复触发。"""
        self._update_toggle(busy)

    def set_working(self, message):
        """任务进行中的进度文字。"""
        if message:
            self._set_status(message, COLOR_NEUTRAL, "…")

    # ---- 小动作 -----------------------------------------------------------

    def set_exe_text(self, path):
        """把路径写进输入框，供“选择程序”与“自动定位”回填。"""
        self.exe_input.setText(path or "")
        self.exe_input.setCursorPosition(0)

    def copy_text(self, text):
        """把文本复制到剪贴板，返回是否真的复制了。"""
        if not text:
            return False
        QGuiApplication.clipboard().setText(text)
        return True

    def path_for_copy(self):
        """返回优先复制的路径：输入框里的，否则是列表里的第一个。"""
        text = self.manual_path()
        if text:
            return text
        return next(
            (item.get("path") for item in self.processes if item.get("path")), ""
        )

    def _copy_row(self, row, _column):
        """双击进程行时把这一行的程序路径交给界面服务复制。"""
        item = self.table.item(row, 3)
        if item is not None:
            self.table.selectRow(row)
            self.rowPathRequested.emit(item.text().split("（", 1)[0])
