import sys
from datetime import datetime
from pathlib import Path
from threading import Event

from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer, Slot
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDoubleSpinBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
    QStackedWidget, QStatusBar, QStyle, QTabWidget, QToolButton,
    QVBoxLayout, QWidget,
)

from cli import main as core
from .workers import SendWorker, TaskWorker


APP_NAME = "JiYu Attack Next"


def configure_application(app):
    app.setStyle("Fusion")
    app.setPalette(app.style().standardPalette())
    app.setFont(QFont("Microsoft YaHei UI", 10))


def app_icon():
    resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return QIcon(str(resource_root / "assets" / "app.svg"))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.thread = None
        self.worker = None
        self.active_cancel = None
        self.close_after_task = False
        self.local_buttons = []
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1180, 760)
        self.setMinimumSize(900, 620)
        self._build_ui()
        self._apply_styles()
        self._update_command_stats()
        self._append_log("就绪")

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 18, 20, 10)
        layout.setSpacing(18)
        header = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(app_icon().pixmap(40, 40))
        mark.setFixedSize(40, 40)
        title = QLabel(APP_NAME)
        title.setObjectName("pageTitle")
        header.addWidget(mark)
        header.addSpacing(8)
        header.addWidget(title)
        header.addStretch()
        subtitle = QLabel("极域 UDP 测试")
        subtitle.setObjectName("mutedText")
        header.addWidget(subtitle)
        layout.addLayout(header)
        body = QHBoxLayout()
        body.setSpacing(20)
        body.addWidget(self._build_navigation())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_send_page())
        self.stack.addWidget(self._build_local_page())
        body.addWidget(self.stack, 1)
        layout.addLayout(body, 1)
        status = QStatusBar()
        status.setSizeGripEnabled(False)
        status.showMessage("就绪")
        self.setStatusBar(status)

    def _standard_icon(self, name):
        return self.style().standardIcon(name)

    def _tool_button(self, icon, tooltip, callback):
        button = QToolButton()
        button.setIcon(self._standard_icon(icon))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(32, 32)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    def _build_navigation(self):
        nav = QWidget()
        nav.setFixedWidth(150)
        layout = QVBoxLayout(nav)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(8)
        self.nav_send = QPushButton("发送测试")
        self.nav_send.setIcon(self._standard_icon(QStyle.SP_FileDialogDetailedView))
        self.nav_local = QPushButton("本机工具")
        self.nav_local.setIcon(self._standard_icon(QStyle.SP_ComputerIcon))
        for button in (self.nav_send, self.nav_local):
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(42)
            layout.addWidget(button)
        self.nav_send.setChecked(True)
        self.nav_send.clicked.connect(lambda: self._switch_page(0))
        self.nav_local.clicked.connect(lambda: self._switch_page(1))
        layout.addStretch()
        version = QLabel("v1.0")
        version.setObjectName("mutedText")
        layout.addWidget(version)
        return nav

    def _switch_page(self, index):
        self.stack.setCurrentIndex(index)
        self.nav_send.setChecked(index == 0)
        self.nav_local.setChecked(index == 1)

    def _build_send_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self._build_target_section())
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        editors = QTabWidget()
        editors.setMinimumWidth(320)
        editors.addTab(self._build_message_section(), "文本消息")
        editors.addTab(self._build_command_section(), "远程命令")
        splitter.addWidget(editors)
        splitter.addWidget(self._build_console_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([510, 350])
        layout.addWidget(splitter, 1)
        layout.addWidget(self._build_options_section())
        self.send_fields = [self.target_input, self.port_input, self.loop_input,
                            self.interval_input, self.message_edit, self.command_edit,
                            self.reboot_check, self.shutdown_check, self.load_button]
        return page

    def _build_target_section(self):
        band = QWidget()
        band.setObjectName("targetBand")
        row = QHBoxLayout(band)
        row.setContentsMargins(0, 0, 0, 14)
        row.setSpacing(12)
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("目标 IPv4 地址 / 末段范围 / 24 位网段")
        self.target_input.setClearButtonEnabled(True)
        self.target_input.setToolTip("支持单个地址、末段范围和 /24 网段")
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(4705)
        self.loop_input = QSpinBox()
        self.loop_input.setRange(1, 10000)
        self.loop_input.setValue(1)
        self.interval_input = QDoubleSpinBox()
        self.interval_input.setRange(0, 86400)
        self.interval_input.setDecimals(1)
        self.interval_input.setValue(22)
        self.interval_input.setSuffix(" 秒")
        self.interval_input.setToolTip("相邻两轮之间的等待时间")
        for label, field in [("目标地址", self.target_input), ("UDP 端口", self.port_input),
                             ("发送轮数", self.loop_input), ("轮次间隔", self.interval_input)]:
            column = QVBoxLayout()
            column.setSpacing(6)
            name = QLabel(label)
            name.setObjectName("fieldLabel")
            column.addWidget(name)
            column.addWidget(field)
            if field is not self.target_input:
                field.setFixedWidth(105)
            row.addLayout(column, 1 if field is self.target_input else 0)
        return band

    def _build_message_section(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 12, 10, 8)
        layout.setSpacing(10)
        toolbar = QHBoxLayout()
        self.message_file = QLabel("消息正文")
        self.message_file.setObjectName("fieldLabel")
        toolbar.addWidget(self.message_file, 1)
        self.load_button = self._tool_button(
            QStyle.SP_DialogOpenButton, "从 UTF-8 文件导入", self._load_message_file)
        toolbar.addWidget(self.load_button)
        layout.addLayout(toolbar)
        self.message_edit = QPlainTextEdit()
        self.message_edit.setPlaceholderText("输入消息")
        self.message_edit.setMinimumHeight(120)
        self.message_edit.textChanged.connect(self._update_message_stats)
        layout.addWidget(self.message_edit, 1)
        self.message_stats = QLabel("0 字符 | 0 条报文")
        self.message_stats.setObjectName("mutedText")
        layout.addWidget(self.message_stats)
        return page

    def _build_command_section(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 12, 10, 8)
        heading = QLabel("命令正文")
        heading.setObjectName("fieldLabel")
        layout.addWidget(heading)
        self.command_edit = QPlainTextEdit()
        self.command_edit.setPlaceholderText("cmd.exe /c ...")
        self.command_edit.textChanged.connect(self._update_command_stats)
        layout.addWidget(self.command_edit, 1)
        self.command_stats = QLabel()
        self.command_stats.setObjectName("mutedText")
        layout.addWidget(self.command_stats)
        return page

    def _build_options_section(self):
        footer = QFrame()
        footer.setObjectName("footer")
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)
        actions = QHBoxLayout()
        actions.addWidget(QLabel("设备操作"))
        actions.addSpacing(10)
        self.reboot_check = QCheckBox("重启")
        self.shutdown_check = QCheckBox("关机")
        self.reboot_check.toggled.connect(
            lambda checked: self._sync_device_actions(checked, self.reboot_check))
        self.shutdown_check.toggled.connect(
            lambda checked: self._sync_device_actions(checked, self.shutdown_check))
        actions.addWidget(self.reboot_check)
        actions.addSpacing(12)
        actions.addWidget(self.shutdown_check)
        actions.addStretch()
        layout.addLayout(actions)
        buttons = QHBoxLayout()
        self.task_summary = QLabel("就绪")
        self.task_summary.setObjectName("mutedText")
        buttons.addWidget(self.task_summary, 1)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setIcon(self._standard_icon(QStyle.SP_MediaStop))
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_task)
        self.send_button = QPushButton("开始发送")
        self.send_button.setObjectName("primaryButton")
        self.send_button.setIcon(self._standard_icon(QStyle.SP_MediaPlay))
        self.send_button.clicked.connect(self._start_send)
        for button in (self.cancel_button, self.send_button):
            button.setMinimumSize(112, 40)
            button.setCursor(Qt.PointingHandCursor)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.send_button)
        layout.addLayout(buttons)
        return footer

    def _build_console_panel(self):
        frame = QFrame()
        frame.setObjectName("consolePanel")
        frame.setMinimumWidth(225)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 12)
        toolbar = QHBoxLayout()
        title = QLabel("运行日志")
        title.setObjectName("consoleTitle")
        self.task_badge = QLabel("空闲")
        self.task_badge.setObjectName("taskBadge")
        toolbar.addWidget(title)
        toolbar.addWidget(self.task_badge)
        toolbar.addStretch()
        toolbar.addWidget(self._tool_button(QStyle.SP_DialogSaveButton, "保存日志", self._save_log))
        toolbar.addWidget(self._tool_button(QStyle.SP_TrashIcon, "清空日志", self._clear_log))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("logView")
        self.log_view.setMaximumBlockCount(2000)
        layout.addLayout(toolbar)
        layout.addWidget(self.log_view, 1)
        return frame

    def _section(self, title):
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        return section, layout

    def _build_local_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        columns = QHBoxLayout()
        columns.setSpacing(20)
        info, info_layout = self._section("本机信息")
        self.local_result = QPlainTextEdit()
        self.local_result.setReadOnly(True)
        self.local_result.setPlaceholderText("尚未查询")
        info_layout.addWidget(self.local_result, 1)
        query = QPushButton("查询本机")
        query.setIcon(self._standard_icon(QStyle.SP_BrowserReload))
        query.clicked.connect(self._start_local_probe)
        info_layout.addWidget(query)
        firewall, firewall_layout = self._section("StudentMain.exe 防火墙规则")
        self.firewall_result = QPlainTextEdit()
        self.firewall_result.setReadOnly(True)
        self.firewall_result.setPlaceholderText("暂无操作记录")
        firewall_layout.addWidget(self.firewall_result, 1)
        row = QHBoxLayout()
        for title, action in [("阻断连接", "block"), ("恢复允许", "allow")]:
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, value=action: self._run_firewall(value))
            self.local_buttons.append(button)
            row.addWidget(button)
        firewall_layout.addLayout(row)
        self.local_buttons.append(query)
        for button in self.local_buttons:
            button.setMinimumHeight(38)
            button.setCursor(Qt.PointingHandCursor)
        columns.addWidget(info, 1)
        columns.addWidget(firewall, 1)
        layout.addLayout(columns, 1)
        heading = QLabel("本机工具日志")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        self.local_log = QPlainTextEdit()
        self.local_log.setReadOnly(True)
        self.local_log.setMaximumBlockCount(1000)
        layout.addWidget(self.local_log, 1)
        return page

    def _apply_styles(self):
        self.setStyleSheet("""
            QWidget#root { background: #f7f8fa; color: #252a32; }
            QLabel { color: #252a32; }
            QLabel#pageTitle { font-size: 22px; font-weight: 700; }
            QLabel#mutedText { color: #717681; font-size: 12px; }
            QLabel#fieldLabel { color: #555b65; font-size: 12px; }
            QLabel#sectionTitle { font-size: 14px; font-weight: 600; }
            QPushButton { border: 1px solid #d4d7dc; background: white; color: #303640;
                          padding: 7px 12px; border-radius: 5px; }
            QPushButton:hover { background: #edf0f3; }
            QPushButton:disabled { color: #9a9ea6; background: #f0f1f3; }
            QPushButton#navButton { text-align: left; border: none; background: transparent; }
            QPushButton#navButton:checked { background: #e1efec; color: #14645f; font-weight: 600; }
            QPushButton#primaryButton { background: #156b64; color: white; border: 1px solid #156b64; }
            QPushButton#primaryButton:hover { background: #105950; }
            QPushButton#primaryButton:disabled { background: #a1b6b0; border-color: #a1b6b0; }
            QToolButton { border: none; border-radius: 4px; background: transparent; }
            QToolButton:hover { background: #dce2e7; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
                color: #252a32; background: white; border: 1px solid #d4d7dc;
                border-radius: 4px; padding: 7px; selection-background-color: #b9dbd5; }
            QLineEdit, QSpinBox, QDoubleSpinBox { min-height: 23px; }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {
                border-color: #156b64; }
            QLineEdit:disabled, QPlainTextEdit:disabled { background: #f0f1f3; color: #7f858d; }
            QTabWidget::pane { border: 1px solid #d4d7dc; background: white; }
            QTabBar::tab { background: #edf0f3; color: #666d77; padding: 10px 18px;
                          border: 1px solid #d4d7dc; border-right: none; }
            QTabBar::tab:selected { color: #14645f; background: white; }
            QFrame#footer { border-top: 1px solid #d4d7dc; }
            QFrame#consolePanel { background: #22262d; border-radius: 5px; }
            QFrame#consolePanel QLabel { color: #e0e4e8; }
            QFrame#consolePanel QLabel#taskBadge { color: #b1cbbf; font-size: 11px; }
            QFrame#consolePanel QToolButton:hover { background: #3a414b; }
            QPlainTextEdit#logView { color: #d3d8de; background: #22262d; border: none;
                                    font-family: "Consolas", "Microsoft YaHei UI"; font-size: 12px; }
            QSplitter::handle { background: transparent; width: 12px; }
            QCheckBox { color: #555b65; spacing: 8px; }
            QStatusBar { background: #f7f8fa; color: #717681; border-top: 1px solid #e0e2e6; }
        """)

    @Slot(str)
    def _append_log(self, message):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText("[%s] %s" % (stamp, message))
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def _clear_log(self):
        self.log_view.clear()

    def _save_log(self):
        filename, _ = QFileDialog.getSaveFileName(self, "保存日志", "运行日志.txt", "文本文件 (*.txt)")
        if filename:
            try:
                Path(filename).write_text(self.log_view.toPlainText(), encoding="utf-8")
            except OSError as error:
                QMessageBox.warning(self, "保存失败", str(error))

    def _update_message_stats(self):
        text = self.message_edit.toPlainText()
        try:
            count = sum(1 for _ in core.split_message(text))
            self.message_stats.setText("%d 字符 | %d 条报文" % (len(text), count))
            self.message_stats.setToolTip("")
        except (ValueError, UnicodeError) as error:
            self.message_stats.setText("文本包含不可发送字符")
            self.message_stats.setToolTip(str(error))

    def _update_command_stats(self):
        text = self.command_edit.toPlainText()
        try:
            units = len(text.encode("utf-16le")) // 2
        except UnicodeError:
            self.command_stats.setText("文本编码无效")
            return
        self.command_stats.setText("%d / %d 个 UTF-16 单元" % (units, core.COMMAND_MAX_BYTES // 2))
        self.command_stats.setStyleSheet("color: %s;" % (
            "#aa3d36" if units > core.COMMAND_MAX_BYTES // 2 else "#717681"))

    def _load_message_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "导入消息文件", "", "文本文件 (*.txt *.md);;所有文件 (*)")
        if filename:
            try:
                with open(filename, encoding="utf-8-sig", newline="") as source:
                    text = source.read()
                self.message_edit.setPlainText(text)
                self.message_file.setText(Path(filename).name)
                self.message_file.setToolTip(filename)
            except (OSError, UnicodeError) as error:
                QMessageBox.warning(self, "导入失败", str(error))

    def _sync_device_actions(self, checked, changed_checkbox):
        if checked:
            other = self.shutdown_check if changed_checkbox is self.reboot_check else self.reboot_check
            other.setChecked(False)

    def _collect_options(self):
        extra = "r" if self.reboot_check.isChecked() else (
            "s" if self.shutdown_check.isChecked() else "")
        return core.SendOptions(
            target=self.target_input.text().strip(), port=self.port_input.value(),
            message=self.message_edit.toPlainText(), command=self.command_edit.toPlainText(),
            extra=extra, loops=self.loop_input.value(), interval=self.interval_input.value())

    def _start_send(self):
        if self.thread is not None:
            return
        options = self._collect_options()
        try:
            core.validate_options(options)
        except ValueError as error:
            self.statusBar().showMessage(str(error))
            self._append_log(str(error))
            return
        options.cancel_event = Event()
        self.active_cancel = options.cancel_event
        self._append_log("开始发送：%s，端口 %d" % (options.target, options.port))
        self._set_busy(True, "发送中")
        self._run_in_thread(SendWorker(options, core.execute_send), self._send_finished, self._send_failed)

    def _start_local_probe(self):
        if self.thread is not None:
            return
        self._append_local_log("正在查询本机信息")
        self._set_busy(True, "查询中")
        self._run_in_thread(TaskWorker(probe_local), self._probe_finished, self._probe_failed, local=True)

    def _run_firewall(self, action):
        if self.thread is not None:
            return
        action_name = "阻断连接" if action == "block" else "恢复允许"
        if QMessageBox.question(self, "确认防火墙操作", "是否在本机执行“%s”？" % action_name,
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._append_local_log("开始操作：%s" % action_name)
        self._set_busy(True, "处理中")
        self._run_in_thread(TaskWorker(apply_firewall, action), self._firewall_finished,
                            self._probe_failed, local=True)

    def _run_in_thread(self, worker, finished, failed, local=False):
        self.thread = worker
        self.worker = worker
        worker.setParent(self)
        worker.progress.connect(self._append_local_log if local else self._append_log, Qt.QueuedConnection)
        worker.completed.connect(finished, Qt.QueuedConnection)
        worker.failed.connect(failed, Qt.QueuedConnection)
        self.thread.finished.connect(self._thread_finished, Qt.QueuedConnection)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @Slot(int)
    def _send_finished(self, count):
        self._append_log("本机已发送 %d 个报文" % count)
        self.statusBar().showMessage("发送完成，未接收目标执行回执")

    @Slot(str)
    def _send_failed(self, message):
        self._append_log(message)
        self.statusBar().showMessage(message)

    @Slot(object)
    def _probe_finished(self, result):
        ip, ports = result
        text = "本机 IP：%s\n\n监听端口：\n%s" % (ip, "\n".join(ports) if ports else "未发现匹配端口")
        self.local_result.setPlainText(text)
        self._append_local_log(text)
        self.statusBar().showMessage("本机查询完成")

    @Slot(str)
    def _probe_failed(self, message):
        self._append_local_log(message)
        self.statusBar().showMessage(message)

    @Slot(object)
    def _firewall_finished(self, result):
        lines = []
        for command, code, stdout, stderr in result:
            lines.extend([command, "成功" if code == 0 else "失败（退出码 %d）" % code])
            if stdout:
                lines.append(stdout)
            if stderr:
                lines.append(stderr)
            lines.append("")
        text = "\n".join(lines).strip()
        self.firewall_result.setPlainText(text)
        self._append_local_log(text)
        failed = any(item[1] != 0 for item in result)
        self.statusBar().showMessage("部分规则操作失败" if failed else "防火墙操作完成")

    @Slot(str)
    def _append_local_log(self, message):
        self.local_log.appendPlainText("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message))

    def _set_busy(self, busy, badge):
        self.send_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy and self.active_cancel is not None)
        for field in self.send_fields + self.local_buttons:
            field.setEnabled(not busy)
        self.task_badge.setText(badge if busy else "空闲")
        self.task_summary.setText(badge if busy else "就绪")

    def _cancel_task(self):
        if self.active_cancel:
            self.active_cancel.set()
            self.cancel_button.setEnabled(False)
            self._append_log("正在取消")

    @Slot()
    def _thread_finished(self):
        self.thread = None
        self.worker = None
        self.active_cancel = None
        if self.close_after_task:
            QTimer.singleShot(0, self.close)
        else:
            self._set_busy(False, "空闲")

    def closeEvent(self, event):
        if self.thread is not None and self.thread.isRunning():
            self.close_after_task = True
            self._cancel_task()
            self.statusBar().showMessage("正在结束当前任务后关闭窗口")
            event.ignore()
            return
        event.accept()


def probe_local(report=None):
    if report:
        report("正在读取本机 IP 与 Student 监听端口")
    return core.local_ip_and_ports()


def apply_firewall(action, report=None):
    if report:
        report("正在修改 StudentMain.exe 防火墙规则")
    return core.set_firewall_rule(action)


def main():
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName("jiyu_attack_next")
    app = QApplication(sys.argv)
    configure_application(app)
    window = MainWindow()
    window.show()
    result = app.exec()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    return result


if __name__ == "__main__":
    sys.exit(main())
