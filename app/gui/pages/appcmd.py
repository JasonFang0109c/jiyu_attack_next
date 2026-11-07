"""应用命令页：远程运行程序、打开网址、终止进程、黑屏锁键鼠等。"""

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, ComboBox

from ..components import ReadableSpinBox
from .common import NetworkPage, table_widget

# 每个操作对应一组参数，界面按选择切换，避免把无关输入框一次全摆出来。
RUN = "run"
OPEN_URL = "url"
TERMINATE = "terminate"
BLACKSCREEN = "blackscreen"
UNLOCK = "unlock"
EXIT_STUDENT = "exit"
CLOSE_APPS = "close"
RENAME = "rename"
LOCK_SCREEN = "lock"
UNLOCK_SCREEN = "unlock-screen"
PASSWORD = "password"

OPERATIONS = (
    (RUN, "远程运行程序"),
    (OPEN_URL, "打开网址"),
    (TERMINATE, "终止进程"),
    (BLACKSCREEN, "黑屏并锁定键鼠"),
    (UNLOCK, "解除黑屏"),
    (RENAME, "修改显示名"),
    (LOCK_SCREEN, "锁定屏幕"),
    (UNLOCK_SCREEN, "解除锁屏"),
    (PASSWORD, "设置解锁密码"),
    (EXIT_STUDENT, "退出学生端"),
    (CLOSE_APPS, "关闭所有程序"),
)

SHOW_MODES = ("正常窗口", "最小化", "最大化")


class AppCommandPage(NetworkPage):
    """选择一种应用命令并填写参数，发送到目标设备。"""

    def __init__(self, state, parent=None):
        super().__init__("appcmd", "应用命令", state, "发送命令", parent)
        row = QHBoxLayout()
        row.addWidget(BodyLabel("操作", self.content_card))
        self.operation_box = ComboBox(self)
        for code, label in OPERATIONS:
            self.operation_box.addItem(label, userData=code)
        self.operation_box.setMinimumWidth(200)
        row.addWidget(self.operation_box)
        row.addSpacing(12)
        row.addWidget(BodyLabel("会话频道", self.content_card))
        self.channel_input = ReadableSpinBox(self)
        self.channel_input.setRange(1, 32)
        self.channel_input.setValue(1)
        self.channel_input.setMinimumWidth(110)
        self.channel_input.setToolTip(
            "黑屏与解除黑屏只在会话频道上生效，需与学生端所在频道一致"
        )
        row.addWidget(self.channel_input)
        self.lcmd_input = QCheckBox("走轻量通道 LCMD", self)
        self.lcmd_input.setToolTip(
            "LCMD 不带 20000 毫秒超时与事务号，学生端也不回事务应答；默认走 COMD"
        )
        row.addSpacing(12)
        row.addWidget(self.lcmd_input)
        row.addStretch()
        self.body.addLayout(row)

        self.forms = QStackedWidget(self)
        self.forms.addWidget(self._build_run_form())
        self.forms.addWidget(self._build_url_form())
        self.forms.addWidget(self._build_terminate_form())
        self.forms.addWidget(self._build_blackscreen_form())
        self.forms.addWidget(self._build_empty_form("解除黑屏不需要额外参数"))
        self.forms.addWidget(
            self._build_text_form("显示名", "rename_input", "例如 1-01 号机")
        )
        self.forms.addWidget(self._build_empty_form("锁定屏幕不需要额外参数"))
        self.forms.addWidget(self._build_empty_form("解除锁屏不需要额外参数"))
        self.forms.addWidget(
            self._build_text_form(
                "解锁密码", "password_input", "留空表示清除已设置的解锁密码"
            )
        )
        self.forms.addWidget(self._build_empty_form("退出学生端不需要额外参数"))
        self.forms.addWidget(self._build_empty_form("关闭所有程序不需要额外参数"))
        self.body.addWidget(self.forms)

        self.body.addWidget(BodyLabel("目标预览", self.content_card))
        self.preview = table_widget(["目标地址", "UDP 端口"], self)
        self.preview.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.preview.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.preview.setColumnWidth(1, 140)
        self.body.addWidget(self.preview, 1)

        self.operation_box.currentIndexChanged.connect(self._operation_changed)
        state.changed.connect(self._on_target_changed)
        self.update_preview()
        self._operation_changed(0)

    def _build_run_form(self):
        """远程运行程序的参数：路径、启动参数与窗口状态。"""
        host = QWidget(self)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        path_row = QHBoxLayout()
        path_row.addWidget(BodyLabel("程序路径", host))
        self.run_path = QLineEdit(host)
        self.run_path.setPlaceholderText(r"例如 C:\Windows\System32\notepad.exe")
        path_row.addWidget(self.run_path, 1)
        layout.addLayout(path_row)
        argument_row = QHBoxLayout()
        argument_row.addWidget(BodyLabel("启动参数", host))
        self.run_arguments = QLineEdit(host)
        self.run_arguments.setPlaceholderText("可选，按原样传给目标程序")
        argument_row.addWidget(self.run_arguments, 1)
        layout.addLayout(argument_row)
        show_row = QHBoxLayout()
        show_row.addWidget(BodyLabel("窗口状态", host))
        self.run_show = ComboBox(host)
        self.run_show.addItems(list(SHOW_MODES))
        self.run_show.setMinimumWidth(150)
        show_row.addWidget(self.run_show)
        show_row.addStretch()
        layout.addLayout(show_row)
        return host

    def _build_url_form(self):
        """打开网址只需要一个 URL。"""
        host = QWidget(self)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        row = QHBoxLayout()
        row.addWidget(BodyLabel("网址", host))
        self.url_input = QLineEdit(host)
        self.url_input.setPlaceholderText("https://example.com")
        row.addWidget(self.url_input, 1)
        layout.addLayout(row)
        return host

    def _build_terminate_form(self):
        """终止进程按进程号下发，可选强制结束。"""
        host = QWidget(self)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        row = QHBoxLayout()
        row.addWidget(BodyLabel("进程号", host))
        self.process_input = QLineEdit(host)
        self.process_input.setPlaceholderText("目标电脑上的进程号（PID）")
        row.addWidget(self.process_input, 1)
        self.force_kill = QCheckBox("强制结束", host)
        self.force_kill.setChecked(True)
        row.addWidget(self.force_kill)
        layout.addLayout(row)
        layout.addWidget(
            BodyLabel(
                "进程号可在「学生信息」页的进程列表里查到；按名称结束需要该进程号。",
                host,
            )
        )
        return host

    def _build_blackscreen_form(self):
        """黑屏的参数：是否锁键鼠、倒计时与提示文字。"""
        host = QWidget(self)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        lock_row = QHBoxLayout()
        self.lock_input = QCheckBox("同时锁定键盘与鼠标", host)
        self.lock_input.setChecked(True)
        lock_row.addWidget(self.lock_input)
        lock_row.addStretch()
        layout.addLayout(lock_row)
        timeout_row = QHBoxLayout()
        timeout_row.addWidget(BodyLabel("自动解除秒数", host))
        self.blackout_timeout = ReadableSpinBox(host)
        self.blackout_timeout.setRange(0, 3600)
        self.blackout_timeout.setValue(10)
        self.blackout_timeout.setMinimumWidth(120)
        self.blackout_timeout.setToolTip(
            "0 表示不自动解除：黑屏会一直保持，直到手动发送解除黑屏"
        )
        timeout_row.addWidget(self.blackout_timeout)
        timeout_row.addStretch()
        layout.addLayout(timeout_row)
        text_row = QHBoxLayout()
        text_row.addWidget(BodyLabel("提示文字", host))
        self.blackout_text = QLineEdit(host)
        self.blackout_text.setPlaceholderText("可选，显示在黑屏中间")
        text_row.addWidget(self.blackout_text, 1)
        layout.addLayout(text_row)
        return host

    def _build_text_form(self, label, attribute, placeholder):
        """带一个单行输入的参数表单。"""
        host = QWidget(self)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        row = QHBoxLayout()
        row.addWidget(BodyLabel(label, host))
        field = QLineEdit(host)
        field.setPlaceholderText(placeholder)
        setattr(self, attribute, field)
        row.addWidget(field, 1)
        layout.addLayout(row)
        return host

    def _build_empty_form(self, text):
        """无参数操作的占位说明。"""
        host = QWidget(self)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(BodyLabel(text, host))
        layout.addStretch()
        return host

    def _operation_changed(self, index):
        """切换操作时同步参数表单与按钮文案。"""
        self.forms.setCurrentIndex(index)
        self.footer.send_button.setText(
            "解除黑屏" if self.operation() == UNLOCK else "发送命令"
        )

    @Slot(str, object)
    def _on_target_changed(self, name, _value):
        if name == "target":
            self.update_preview()

    def update_preview(self):
        """按当前目标重建预览表。"""
        from ... import core

        target = self.targets.state.values["target"].strip()
        try:
            hosts = (
                core.get_ip(self.targets.state.resolve_target(target)) if target else []
            )
        except ValueError:
            hosts = []
        port = str(self.targets.state.values["port"])
        self.preview.setRowCount(len(hosts))
        for row, host in enumerate(hosts):
            self.preview.setItem(row, 0, QTableWidgetItem(host))
            self.preview.setItem(row, 1, QTableWidgetItem(port))
            self.preview.setRowHeight(row, 36)

    def operation(self):
        """返回当前选中的操作代码。"""
        return self.operation_box.currentData()

    def payload(self):
        """按当前操作与输入生成应用命令负载。

        Returns:
            tuple: ``(动作名, 负载, 是否走 MESS 通道)``。

        Raises:
            ValueError: 必填参数为空或格式不对。
        """
        from ... import core

        operation = self.operation()
        if operation == RUN:
            path = self.run_path.text().strip()
            if not path:
                raise ValueError("请填写要运行的程序路径")
            return (
                "远程运行程序",
                core.appcmd.run_program_payload(
                    path,
                    self.run_arguments.text().strip(),
                    self.run_show.currentIndex(),
                ),
                False,
            )
        if operation == OPEN_URL:
            url = self.url_input.text().strip()
            if not url:
                raise ValueError("请填写要打开的网址")
            return (
                "打开网址",
                core.appcmd.open_url_payload(core.appcmd.normalize_url(url)),
                False,
            )
        if operation == TERMINATE:
            text = self.process_input.text().strip()
            if not text.isdigit():
                raise ValueError("进程号必须是数字")
            return (
                "终止进程",
                core.appcmd.kill_payload(
                    process_id=int(text), force=self.force_kill.isChecked()
                ),
                True,
            )
        if operation == BLACKSCREEN:
            return (
                "黑屏并锁定键鼠",
                core.appcmd.blackscreen_mess_payload(
                    self.lock_input.isChecked(),
                    self.blackout_timeout.value(),
                    self.blackout_text.text().strip(),
                ),
                True,
            )
        if operation == UNLOCK:
            return "解除黑屏", core.appcmd.unlock_payload(), True
        if operation == RENAME:
            return (
                "修改显示名",
                core.appcmd.rename_payload(self.rename_input.text()),
                False,
            )
        if operation == LOCK_SCREEN:
            return "锁定屏幕", core.appcmd.lock_screen_payload(True), False
        if operation == UNLOCK_SCREEN:
            return "解除锁屏", core.appcmd.lock_screen_payload(False), False
        if operation == PASSWORD:
            return (
                "设置解锁密码",
                core.appcmd.unlock_password_payload(self.password_input.text()),
                False,
            )
        if operation == EXIT_STUDENT:
            return "退出学生端", core.appcmd.exit_student_payload(), False
        return "关闭所有程序", core.appcmd.close_apps_payload(), False

    def delivery(self):
        """返回当前操作该走的通道与补发负载。

        Returns:
            dict: ``channel`` 取 ``comd``/``mess``/``session``；
            ``lock`` 是黑屏时要额外逐台补发的负载，没有则为 ``None``。

        Raises:
            ValueError: 必填参数不合法。
        """
        from ... import core

        name, payload, session = self.payload()
        if name in {"黑屏并锁定键鼠", "解除黑屏"}:
            lock = None
            if name == "黑屏并锁定键鼠" and self.lock_input.isChecked():
                lock = core.appcmd.blackscreen_payload(
                    True, self.blackout_timeout.value()
                )
            return {
                "name": name,
                "payload": payload,
                "channel": "session",
                "lock": lock,
                "timeout": (
                    self.blackout_timeout.value() if name == "黑屏并锁定键鼠" else 0
                ),
            }
        if name == "终止进程":
            # 结束进程走 MESS 的 0x100000 请求，不是应用命令。
            text = self.process_input.text().strip()
            return {
                "name": name,
                "payload": core.appcmd.kill_payload(
                    process_id=int(text), force=self.force_kill.isChecked()
                ),
                "channel": "mess",
                "lock": None,
            }
        return {
            "name": name,
            "payload": payload,
            "channel": "mess"
            if session
            else ("lcmd" if self.lcmd_input.isChecked() else "comd"),
            "lock": None,
        }
