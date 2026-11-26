"""课堂助手页：修复广播窗口、假全屏、置顶与读取解锁密码。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    PrimaryPushButton,
    PushButton,
    SmoothScrollArea,
    SwitchButton,
    setFont,
)
from qfluentwidgets import FluentIcon as FIF

from app.features.classroom.data import (
    DEFAULT_ALLOW_TOP,
    DEFAULT_AUTO_REPAIR,
    DEFAULT_HIDE_BLACK_SCREEN,
    DEFAULT_INCLUDE_FULLSCREEN,
    INTERVAL_RANGE,
    SETTINGS_ALLOW_TOP,
    SETTINGS_AUTO_REPAIR,
    SETTINGS_HIDE_BLACK_SCREEN,
    SETTINGS_INCLUDE_FULLSCREEN,
    SETTINGS_INTERVAL,
)
from app.gui.theme import tone_color
from app.gui.widgets.common import (
    ReadableSpinBox,
    SectionCard,
    page_heading,
    tool_button,
)
from app.gui.widgets.page import Page, table_widget

WINDOW_COLUMNS = ("窗口", "类型", "进程号", "状态")
KIND_LABELS = {
    "broadcast": "广播",
    "black": "黑屏",
    "fullscreen": "全屏窗口",
}


class ClassroomPage(Page):
    """课堂助手：窗口列表、修复按钮、密码读取与看护设置。

    Attributes:
        windows: 当前展示的课堂窗口记录。
        fake_full_enabled: 假全屏当前是否开启。
        topmost_enabled: 广播窗口是否被本页置顶。
        password: 最近一次读取到的解锁密码，空串表示没读到。
    """

    refreshRequested = Signal()
    repairRequested = Signal()
    fakeFullRequested = Signal(bool)
    topmostRequested = Signal(bool)
    passwordRequested = Signal()
    copyPasswordRequested = Signal(str)
    # 设置项以键值对发出，键取自 data.py 的 SETTINGS_* 常量。
    optionChanged = Signal(str, object)
    # 子页被切换显示时才轮询，隐藏后不再占用后台线程。
    activated = Signal()
    deactivated = Signal()

    def __init__(self, parent=None):
        super().__init__("classroom", parent)
        self.windows = []
        self.fake_full_enabled = False
        self.topmost_enabled = False
        self.password = ""
        self._suspend_options = False

        # 卡片较多，整页滚动；滚动条贴住窗口右缘并与页面顶部贯通。
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(0)
        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("classroomScroll")
        bar_width = scroll.verticalScrollBar().sizeHint().width()
        content_host = QWidget(scroll)
        content_host.setObjectName("classroomContent")
        content = QVBoxLayout(content_host)
        content.setContentsMargins(28, 24, 28 + bar_width, 24)
        content.setSpacing(12)
        page_heading(content, "课堂助手")
        content.addWidget(self._build_status_card(content_host))
        content.addWidget(self._build_window_card(content_host))
        content.addWidget(self._build_password_card(content_host))
        content.addWidget(self._build_option_card(content_host))
        content.addStretch(1)
        scroll.setWidget(content_host)
        self.vbox.addWidget(scroll)

    # ---- 布局 -------------------------------------------------------------

    def _build_status_card(self, parent):
        """状态卡片：一句话说明学生端与课堂窗口的当前情况。"""
        card = SectionCard(parent, spacing=6)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.status_icon = BodyLabel("", card)
        setFont(self.status_icon, 14)
        row.addWidget(self.status_icon)
        self.status = BodyLabel("正在读取课堂窗口…", card)
        self.status.setWordWrap(True)
        row.addWidget(self.status, 1)
        card.body.addLayout(row)
        self.detail = CaptionLabel("", card)
        self.detail.setWordWrap(True)
        self.detail.hide()
        card.body.addWidget(self.detail)
        return card

    def _build_window_card(self, parent):
        """窗口卡片：列表、修复按钮与假全屏、置顶开关。"""
        card = SectionCard(parent)
        header = QHBoxLayout()
        title = BodyLabel("课堂窗口", card)
        setFont(title, 16)
        header.addWidget(title)
        header.addStretch()
        self.refresh_button = tool_button(
            FIF.SYNC,
            "重新扫描课堂窗口",
            card,
            lambda: self.refreshRequested.emit(),
        )
        header.addWidget(self.refresh_button)
        card.body.addLayout(header)

        self.table = table_widget(list(WINDOW_COLUMNS), card)
        self.table.setColumnWidth(0, 240)
        self.table.setColumnWidth(1, 96)
        self.table.setColumnWidth(2, 96)
        self.table.setMinimumHeight(170)
        card.body.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.repair_button = PrimaryPushButton(FIF.VIEW, "立即修复", card)
        self.repair_button.setMinimumHeight(34)
        self.repair_button.setToolTip("把广播窗口恢复成可移动、可缩放的普通窗口")
        self.repair_button.clicked.connect(lambda: self.repairRequested.emit())
        buttons.addWidget(self.repair_button)

        self.fake_full_button = PushButton(FIF.FULL_SCREEN, "开启假全屏", card)
        self.fake_full_button.setMinimumHeight(34)
        self.fake_full_button.setToolTip("临时铺满屏幕但不进入真正的全屏模式")
        self.fake_full_button.clicked.connect(
            lambda: self.fakeFullRequested.emit(not self.fake_full_enabled)
        )
        buttons.addWidget(self.fake_full_button)

        self.topmost_button = PushButton(FIF.PIN, "窗口置顶", card)
        self.topmost_button.setMinimumHeight(34)
        self.topmost_button.setToolTip("让广播窗口保持在其他窗口之上")
        self.topmost_button.clicked.connect(
            lambda: self.topmostRequested.emit(not self.topmost_enabled)
        )
        buttons.addWidget(self.topmost_button)
        buttons.addStretch()
        card.body.addLayout(buttons)

        note = CaptionLabel(
            "修复只改窗口样式：不注入学生端、不需要驱动。"
            "反监视与防控制依赖上游原生 Hook 组件，当前版本未包含。",
            card,
        )
        note.setWordWrap(True)
        card.body.addWidget(note)
        return card

    def _build_password_card(self, parent):
        """密码卡片：读取并复制极域解锁密码。"""
        card = SectionCard(parent)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(BodyLabel("解锁密码", card))
        self.password_label = BodyLabel("未读取", card)
        setFont(self.password_label, 16)
        row.addWidget(self.password_label)
        row.addStretch()
        self.read_password_button = PushButton(FIF.FINGERPRINT, "读取", card)
        self.read_password_button.setMinimumHeight(34)
        self.read_password_button.clicked.connect(lambda: self.passwordRequested.emit())
        row.addWidget(self.read_password_button)
        self.copy_password_button = tool_button(
            FIF.COPY,
            "复制解锁密码",
            card,
            self._request_password_copy,
        )
        self.copy_password_button.setEnabled(False)
        row.addWidget(self.copy_password_button)
        card.body.addLayout(row)

        self.password_detail = CaptionLabel(
            "密码来自本机注册表，只读不改；读不到时会尝试解 Knock1。", card
        )
        self.password_detail.setWordWrap(True)
        card.body.addWidget(self.password_detail)
        return card

    def _build_option_card(self, parent):
        """看护设置卡片：自动看护、轮询间隔与三条窗口处理规则。"""
        card = SectionCard(parent)
        title = BodyLabel("自动看护", card)
        setFont(title, 16)
        card.body.addWidget(title)

        self.auto_switch = SwitchButton(card)
        self.auto_switch.setOnText("已开启")
        self.auto_switch.setOffText("已关闭")
        self.auto_switch.setChecked(DEFAULT_AUTO_REPAIR)
        self.auto_switch.checkedChanged.connect(
            lambda checked: self._emit_option(SETTINGS_AUTO_REPAIR, checked)
        )
        self._option_row(
            card,
            "在后台定时修复广播窗口",
            self.auto_switch,
        )

        self.interval_box = ReadableSpinBox(card)
        low, high = INTERVAL_RANGE
        self.interval_box.setRange(low, high)
        self.interval_box.setSuffix(" 秒")
        self.interval_box.setFixedWidth(150)
        self.interval_box.valueChanged.connect(
            lambda value: self._emit_option(SETTINGS_INTERVAL, value)
        )
        self._option_row(card, "检查间隔", self.interval_box)

        self.allow_top_switch = SwitchButton(card)
        self.allow_top_switch.setChecked(DEFAULT_ALLOW_TOP)
        self.allow_top_switch.checkedChanged.connect(
            lambda checked: self._emit_option(SETTINGS_ALLOW_TOP, checked)
        )
        self._option_row(
            card,
            "允许广播窗口保持置顶",
            self.allow_top_switch,
        )

        self.include_fullscreen_switch = SwitchButton(card)
        self.include_fullscreen_switch.setChecked(DEFAULT_INCLUDE_FULLSCREEN)
        self.include_fullscreen_switch.checkedChanged.connect(
            lambda checked: self._emit_option(SETTINGS_INCLUDE_FULLSCREEN, checked)
        )
        self._option_row(
            card,
            "把铺满屏幕的其它窗口一起处理",
            self.include_fullscreen_switch,
        )

        self.hide_black_switch = SwitchButton(card)
        self.hide_black_switch.setChecked(DEFAULT_HIDE_BLACK_SCREEN)
        self.hide_black_switch.checkedChanged.connect(
            lambda checked: self._emit_option(SETTINGS_HIDE_BLACK_SCREEN, checked)
        )
        self._option_row(card, "隐藏黑屏窗口", self.hide_black_switch)
        return card

    @staticmethod
    def _option_row(card, text, control):
        """在卡片里加一行“说明 + 控件”。"""
        row = QHBoxLayout()
        row.setSpacing(12)
        label = BodyLabel(text, card)
        label.setWordWrap(True)
        row.addWidget(label, 1)
        control.setParent(card)
        row.addWidget(control)
        card.body.addLayout(row)

    # ---- 状态刷新 ---------------------------------------------------------

    def _set_status(self, text, tone="neutral", icon="", detail=""):
        """更新状态行；``detail`` 为空时隐藏第二行。"""
        self.status_icon.setText(icon)
        self.status.setText(text)
        self.status.setStyleSheet("color: %s;" % tone_color(tone).name())
        if detail:
            self.detail.setText(detail)
            self.detail.show()
        else:
            self.detail.hide()

    def set_snapshot(self, snapshot):
        """按一次完整状态快照刷新页面。

        Args:
            snapshot: ``classroom.service.snapshot`` 的返回值。
        """
        options = snapshot.get("options") or {}
        if options:
            self.set_options(options)
        self.windows = snapshot.get("windows") or []
        self._fill_table()
        self._refresh_status(snapshot)

    def _fill_table(self):
        """把窗口记录写进表格，状态列组合出全屏、置顶与待修复。"""
        self.table.setRowCount(len(self.windows))
        for row, window in enumerate(self.windows):
            if window["kind"] == "black":
                state = "已隐藏" if not window["visible"] else "待隐藏"
            else:
                parts = []
                if window["fullscreen"]:
                    parts.append("全屏")
                if window["topmost"]:
                    parts.append("置顶")
                if window["sizable"]:
                    parts.append("窗口化")
                state = "、".join(parts) or "待修复"
            values = (
                window["title"],
                KIND_LABELS.get(window["kind"], window["kind"]),
                str(window["pid"]),
                state,
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 3 and state in ("待修复", "待隐藏", "全屏"):
                    cell.setForeground(tone_color("warning"))
                self.table.setItem(row, column, cell)
            self.table.setRowHeight(row, 38)

    def _refresh_status(self, snapshot):
        """按系统支持、学生端与窗口数量写状态说明。"""
        if not snapshot.get("supported", True):
            self._set_status(
                "当前系统不支持窗口操作",
                "error",
                "!",
                "课堂助手只处理 Windows 桌面窗口。",
            )
            return
        pid = snapshot.get("student_pid") or 0
        if not snapshot.get("student_running"):
            self._set_status(
                "本机没有正在运行的学生端",
                "warning",
                "!",
                "在“启停学生端”里启动学生端后，课堂窗口才会出现。",
            )
            return
        count = len(self.windows)
        if count:
            self._set_status(
                "学生端运行中（PID %d），发现 %d 个课堂窗口" % (pid, count),
                "ok",
                "●",
                "点“立即修复”恢复窗口，或开启自动看护让它在后台处理。",
            )
        else:
            self._set_status(
                "学生端运行中（PID %d），暂时没有广播窗口" % pid,
                "neutral",
                "○",
                "教师开始广播或屏幕演示后会出现在这里。",
            )

    def set_options(self, options):
        """把设置值填进控件，不触发保存。"""
        self._suspend_options = True
        try:
            self.auto_switch.setChecked(bool(options.get("auto_repair")))
            self.interval_box.setValue(int(options.get("interval", 3)))
            self.allow_top_switch.setChecked(bool(options.get("allow_top")))
            self.include_fullscreen_switch.setChecked(
                bool(options.get("include_fullscreen"))
            )
            self.hide_black_switch.setChecked(bool(options.get("hide_black_screen")))
        finally:
            self._suspend_options = False

    def set_password(self, result):
        """显示读取到的密码或失败原因。"""
        password = result.get("password") or ""
        error = result.get("error") or ""
        self.password = password
        if password:
            self.password_label.setText(password)
            self.password_label.setStyleSheet("color: %s;" % tone_color("ok").name())
            source = "注册表明文" if result.get("source") == "plain" else "Knock1 解密"
            self.password_detail.setText("来源：%s；只读，不修改注册表。" % source)
            self.copy_password_button.setEnabled(True)
        else:
            self.password_label.setText("未读取")
            self.password_label.setStyleSheet(
                "color: %s;" % tone_color("warning").name()
            )
            self.password_detail.setText(error or "点“读取”从本机注册表取密码。")
            self.copy_password_button.setEnabled(False)

    def set_fake_full(self, enabled):
        """刷新假全屏按钮文案与图标。"""
        self.fake_full_enabled = bool(enabled)
        if enabled:
            self.fake_full_button.setText("还原窗口")
            self.fake_full_button.setIcon(FIF.BACK_TO_WINDOW)
        else:
            self.fake_full_button.setText("开启假全屏")
            self.fake_full_button.setIcon(FIF.FULL_SCREEN)

    def set_topmost(self, enabled):
        """刷新置顶按钮文案与图标。"""
        self.topmost_enabled = bool(enabled)
        if enabled:
            self.topmost_button.setText("取消置顶")
            self.topmost_button.setIcon(FIF.UNPIN)
        else:
            self.topmost_button.setText("窗口置顶")
            self.topmost_button.setIcon(FIF.PIN)

    def set_busy(self, busy):
        """任务执行期间禁用按钮，避免重复触发。"""
        for button in (
            self.repair_button,
            self.fake_full_button,
            self.topmost_button,
            self.read_password_button,
            self.refresh_button,
        ):
            button.setEnabled(not busy)

    def _request_password_copy(self):
        """有密码时把复制请求发给界面服务。"""
        if self.password:
            self.copyPasswordRequested.emit(self.password)

    def _emit_option(self, key, value):
        """把控件变化转成设置信号；填充设置时忽略。"""
        if self._suspend_options:
            return
        self.optionChanged.emit(key, value)

    # ---- 可见性 -----------------------------------------------------------

    def showEvent(self, event):
        """页面显示时通知服务开始轮询。"""
        super().showEvent(event)
        self.activated.emit()

    def hideEvent(self, event):
        """页面隐藏时停止轮询。"""
        self.deactivated.emit()
        super().hideEvent(event)
