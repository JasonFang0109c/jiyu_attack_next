import sys
from pathlib import Path
from threading import Event

from PySide6.QtCore import QCoreApplication, QEvent, QLocale, Qt, QTimer, Slot
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import QApplication, QFileDialog
from qfluentwidgets import (CaptionLabel, FluentIcon as FIF, FluentTranslator, HyperlinkButton,
                            FluentWindow, InfoBar, InfoBarPosition, MessageBox,
                            NavigationItemPosition, Theme, setTheme, setThemeColor)

from cli import main as core
from .models import ConnectionState, DeviceAliasStore, LogStore
from .pages import (AboutPage, AliasPage, CommandPage, DevicePage, FirewallPage,
                    LocalPage, LogPage, MessagePage, SettingsPage)
from .workers import SendWorker, TaskWorker


APP_NAME = "JiYu Attack Next"
CATEGORIES = {"message": "文本消息", "command": "远程命令", "device": "设备操作",
              "local": "本机信息", "firewall": "防火墙"}


def configure_application(application):
    application.setFont(QFont("Microsoft YaHei UI", 10))
    locale = QLocale(QLocale.Chinese, QLocale.China)
    QLocale.setDefault(locale)
    application.fluent_translator = FluentTranslator(locale)
    application.installTranslator(application.fluent_translator)
    setTheme(Theme.LIGHT)
    setThemeColor(QColor("#0067c0"))


def app_icon():
    resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return QIcon(str(resource_root / "assets" / "app.svg"))


class MainWindow(FluentWindow):
    def __init__(self, alias_store=None):
        super().__init__()
        self.thread = None
        self.worker = None
        self.active_cancel = None
        self.active_kind = ""
        self.close_after_task = False
        self._reset_undo = None
        self._reset_undo_timer = None
        self.connection_state = ConnectionState(alias_store, parent=self)
        self.alias_store = self.connection_state.aliases
        self.logs = LogStore(self)
        self.setWindowTitle(APP_NAME)
        self.titleBar.hBoxLayout.setContentsMargins(6, 0, 0, 0)
        self.setWindowIcon(app_icon())
        self.setMicaEffectEnabled(False)
        self.setCustomBackgroundColor("#f5f6f8", "#202020")
        self.setMinimumSize(960, 640)
        self.resize(1180, 780)
        self.stackedWidget.setAnimationEnabled(False)
        self.pages = {
            "message": MessagePage(self.connection_state, self),
            "command": CommandPage(self.connection_state, self),
            "device": DevicePage(self.connection_state, self),
            "aliases": AliasPage(self.connection_state, self),
            "local": LocalPage(self),
            "firewall": FirewallPage(self),
            "logs": LogPage(self.logs, self),
            "settings": SettingsPage(self),
            "about": AboutPage(self),
        }
        self.network_pages = [self.pages[key] for key in ("message", "command", "device")]
        self.task_pages = self.network_pages + [self.pages["local"], self.pages["firewall"]]
        self._build_navigation()
        self._connect_actions()
        self.logs.add("应用", "界面已就绪")

    def _build_navigation(self):
        self.navigationInterface.setExpandWidth(200)
        self.navigationInterface.setMinimumExpandWidth(1050)
        self.navigationInterface.setReturnButtonVisible(False)
        self.navigationInterface.addItemHeader("远程操作")
        self.addSubInterface(self.pages["message"], FIF.MESSAGE, "文本消息")
        self.addSubInterface(self.pages["command"], FIF.COMMAND_PROMPT, "远程命令")
        self.addSubInterface(self.pages["device"], FIF.POWER_BUTTON, "设备操作")
        self.addSubInterface(self.pages["aliases"], FIF.QUICK_NOTE, "设备备注")
        self.navigationInterface.addSeparator()
        self.navigationInterface.addItemHeader("本机工具")
        self.addSubInterface(self.pages["local"], FIF.IOT, "本机信息")
        self.addSubInterface(self.pages["firewall"], FIF.CERTIFICATE, "防火墙")
        self.addSubInterface(self.pages["logs"], FIF.HISTORY, "运行日志", NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.pages["settings"], FIF.SETTING, "设置", NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.pages["about"], FIF.INFO, "关于", NavigationItemPosition.BOTTOM)
        self.navigationInterface.expand(useAni=False)

    def _connect_actions(self):
        for kind in ("message", "command", "device"):
            self.pages[kind].footer.requested.connect(lambda key=kind: self.start_send(key))
        self.pages["local"].footer.requested.connect(self.start_local_probe)
        self.pages["local"].copyRequested.connect(self.copy_local_ip)
        self.pages["firewall"].footer.requested.connect(self.start_firewall)
        for page in self.task_pages:
            page.footer.cancelled.connect(self.cancel_task)
            page.footer.viewLogs.connect(lambda: self.show_page("logs"))
        message = self.pages["message"]
        message.importRequested.connect(self.import_message)
        message.saveRequested.connect(self.save_message)
        self.pages["logs"].exportRequested.connect(self.export_logs)
        self.pages["logs"].cancelRequested.connect(self.cancel_task)
        self.pages["settings"].themeRequested.connect(self.set_theme)
        self.pages["settings"].resetRequested.connect(self.reset_connection_parameters)

    def show_page(self, key):
        self.switchTo(self.pages[key])

    def _restore_after_reset(self, values):
        self._cancel_reset_timer()
        self.connection_state.restore(values)
        self._notify("已撤销", "连接参数已恢复为修改前的值", "信息")

    def _cancel_reset_timer(self):
        timer = getattr(self, "_reset_undo_timer", None)
        if timer is not None:
            timer.stop()
        pending = getattr(self, "_reset_undo", None)
        if pending is not None:
            pending.hide()
            self.pages["settings"].hide_reset_undo()
        self._reset_undo = None
        self._reset_undo_timer = None

    def reset_connection_parameters(self):
        current = self.connection_state.snapshot()
        if current == self.connection_state.DEFAULTS:
            self.connection_state.reset()
            self._notify("参数已是默认值", "目标地址为空，端口 4705，1 轮，间隔 22 秒", "信息")
            return
        self._cancel_reset_timer()
        self.connection_state.reset()
        self._reset_undo = self.pages["settings"].show_reset_undo(
            lambda: self._restore_after_reset(current))
        self._reset_undo_timer = QTimer(self)
        self._reset_undo_timer.setSingleShot(True)
        self._reset_undo_timer.timeout.connect(self._cancel_reset_timer)
        self._reset_undo_timer.start(8000)

    def current_page(self):
        return self.stackedWidget.currentWidget().objectName()

    def _notify(self, title, message, level="信息"):
        if self.close_after_task:
            return
        function = {"错误": InfoBar.error, "成功": InfoBar.success, "警告": InfoBar.warning}.get(level, InfoBar.info)
        function(title=title, content=message, orient=Qt.Horizontal, isClosable=True,
                 position=InfoBarPosition.TOP_RIGHT, duration=4000, parent=self)

    def _confirm(self, title, content):
        dialog = MessageBox(title, content, self)
        dialog.yesButton.setText("确认执行")
        dialog.cancelButton.setText("取消")
        return bool(dialog.exec())

    def _options_for_page(self, kind):
        if kind == "message":
            return self.connection_state.options(message=self.pages[kind].editor.toPlainText())
        if kind == "command":
            return self.connection_state.options(command=self.pages[kind].editor.toPlainText())
        if kind == "device":
            return self.connection_state.options(extra=self.pages[kind].action())
        raise ValueError("不支持的发送功能")

    def start_send(self, kind):
        if self.thread is not None:
            return
        page = self.pages[kind]
        options = self._options_for_page(kind)
        try:
            hosts = core.get_ip(options.target)
        except ValueError as error:
            page.targets.target_input.setError(True)
            page.targets.target_input.setFocus()
            alias_name = self.connection_state.values["target"].strip()
            if self.connection_state.aliases.match(alias_name) is None:
                self._validation_error(kind, str(error))
            else:
                self._validation_error(kind, "设备备注对应的 IP 无效")
            return
        try:
            core.validate_options(options)
            if options.command:
                core.pkg_sendlist("-c", options.command)
        except (ValueError, UnicodeError) as error:
            self._validation_error(kind, str(error))
            return
        target_text = self.connection_state.format_target()
        target_input_text = self.connection_state.values["target"].strip()
        if kind == "device":
            action = "重启" if options.extra == "r" else "关机"
            content = "目标：%s\nUDP 端口：%d\n设备数量：%d\n操作：%s" % (
                target_text, options.port, len(hosts), action)
            if not self._confirm("确认%s" % action, content):
                return
        options.cancel_event = Event()
        self.active_cancel = options.cancel_event
        if target_input_text.casefold() != options.target.casefold():
            message = "开始发送：%s，解析为 %s，端口 %d，%d 轮" % (
                target_input_text, options.target, options.port, options.loops)
        else:
            message = "开始发送：%s，端口 %d，%d 轮" % (
                target_text, options.port, options.loops)
        self.logs.add(CATEGORIES[kind], message)
        self._begin_task(kind, SendWorker(options, core.execute_send), self._send_finished, self._send_failed)

    def _validation_error(self, kind, message):
        self.pages[kind].footer.set_status(message)
        self.logs.add(CATEGORIES[kind], message, "警告")
        self._notify("请检查参数", message, "警告")

    def start_local_probe(self):
        if self.thread is not None:
            return
        self.logs.add("本机信息", "开始查询")
        self._begin_task("local", TaskWorker(probe_local), self._probe_finished, self._local_failed)

    def start_firewall(self):
        if self.thread is not None:
            return
        action = self.pages["firewall"].action()
        action_name = "阻断连接" if action == "block" else "恢复允许"
        if not self._confirm("确认防火墙操作", "在本机对 StudentMain.exe 规则执行“%s”？" % action_name):
            return
        self.logs.add("防火墙", "开始操作：%s" % action_name)
        self._begin_task("firewall", TaskWorker(apply_firewall, action), self._firewall_finished, self._local_failed)

    def _begin_task(self, kind, worker, finished, failed):
        self.active_kind = kind
        self.thread = worker
        self.worker = worker
        worker.setParent(self)
        worker.progress.connect(self._task_progress, Qt.QueuedConnection)
        worker.completed.connect(finished, Qt.QueuedConnection)
        worker.failed.connect(failed, Qt.QueuedConnection)
        worker.finished.connect(self._thread_finished, Qt.QueuedConnection)
        worker.finished.connect(worker.deleteLater)
        self._set_busy(True)
        worker.start()

    def _set_busy(self, busy):
        for page in self.network_pages:
            page.set_busy(busy, self.active_cancel is not None)
        for key in ("local", "firewall"):
            self.pages[key].footer.set_busy(busy)
        self.pages["firewall"].action_box.setEnabled(not busy)
        self.pages["settings"].reset_button.setEnabled(not busy)
        self.pages["logs"].cancel_button.setEnabled(busy and self.active_cancel is not None)
        for key, page in self.pages.items():
            if key in CATEGORIES and key != self.active_kind:
                page.footer.set_status("其他任务正在执行" if busy else "")
        if busy:
            self.pages[self.active_kind].footer.set_status("执行中")
        else:
            self.pages[self.active_kind].footer.finish_status()

    @Slot(str)
    def _task_progress(self, message):
        self.logs.add(CATEGORIES[self.active_kind], message)
        self.pages[self.active_kind].footer.set_status(message)

    @Slot(int)
    def _send_finished(self, count):
        message = "本机已发送 %d 个报文" % count
        self.pages[self.active_kind].footer.set_status(message)
        self.logs.add(CATEGORIES[self.active_kind], message, "成功")
        self._notify("发送完成", message, "成功")

    @Slot(str)
    def _send_failed(self, message):
        level = "信息" if message == "操作已取消" else "错误"
        self.pages[self.active_kind].footer.set_status(message)
        self.logs.add(CATEGORIES[self.active_kind], message, level)
        self._notify("发送已取消" if level == "信息" else "发送失败", message, level)

    @Slot(object)
    def _probe_finished(self, result):
        ip, ports = result
        self.pages["local"].set_result(ip, ports)
        message = "查询完成，发现 %d 个监听端口" % len(ports)
        self.pages["local"].footer.set_status(message)
        self.logs.add("本机信息", "本机 IP：%s；监听端口：%s" % (ip, ", ".join(ports) or "未发现"), "成功")

    @Slot(object)
    def _firewall_finished(self, results):
        self.pages["firewall"].set_result(results)
        failed = any(
            not result["success"] if isinstance(result, dict) else result[1] != 0
            for result in results
        )
        message = "部分规则操作失败，请查看操作结果" if failed else "防火墙规则已更新"
        self.pages["firewall"].footer.set_status(message)
        for result in results:
            if isinstance(result, dict):
                command = result["command"]
                output = result["stdout"] or result["stderr"]
                success = result["success"]
            else:
                command, code, stdout, stderr = result
                output = stdout or stderr
                success = code == 0
            self.logs.add("防火墙", "%s\n%s" % (command, output), "成功" if success else "错误")
        self._notify("防火墙", message, "警告" if failed else "成功")

    @Slot(str)
    def _local_failed(self, message):
        self.pages[self.active_kind].footer.set_status(message)
        self.logs.add(CATEGORIES[self.active_kind], message, "错误")
        self._notify("操作失败", message, "错误")

    def cancel_task(self):
        if self.active_cancel and not self.active_cancel.is_set():
            self.active_cancel.set()
            self.pages[self.active_kind].footer.set_status("正在取消")
            for page in self.network_pages:
                page.footer.cancel_button.setEnabled(False)
            self.pages["logs"].cancel_button.setEnabled(False)
            self.logs.add(CATEGORIES[self.active_kind], "已请求取消")

    @Slot()
    def _thread_finished(self):
        self.thread = None
        self.worker = None
        self.active_cancel = None
        if self.close_after_task:
            QTimer.singleShot(0, self.close)
        else:
            self._set_busy(False)
        self.active_kind = ""

    def import_message(self):
        filename, _ = QFileDialog.getOpenFileName(self, "导入消息", "", "文本文件 (*.txt *.md);;所有文件 (*)")
        if not filename:
            return
        try:
            with open(filename, encoding="utf-8-sig", newline="") as source:
                text = source.read()
            page = self.pages["message"]
            page.editor.setPlainText(text)
            page.filename.setText(page.filename.fontMetrics().elidedText(Path(filename).name, Qt.ElideMiddle, 225))
            page.filename.setToolTip(filename)
        except (OSError, UnicodeError) as error:
            self._notify("导入失败", str(error), "错误")

    def save_message(self):
        filename, _ = QFileDialog.getSaveFileName(self, "保存消息", "消息.txt", "文本文件 (*.txt)")
        if filename:
            self._save_text(filename, self.pages["message"].editor.toPlainText())

    def export_logs(self):
        filename, _ = QFileDialog.getSaveFileName(self, "导出日志", "运行日志.txt", "文本文件 (*.txt)")
        if filename:
            self._save_text(filename, self.pages["logs"].export_text())

    def _save_text(self, filename, text):
        try:
            Path(filename).write_text(text, encoding="utf-8-sig")
        except OSError as error:
            self._notify("保存失败", str(error), "错误")
        else:
            self._notify("已保存", Path(filename).name, "成功")

    def copy_local_ip(self):
        QApplication.clipboard().setText(self.pages["local"].ip_label.text())
        self._notify("已复制", "本机 IP 已复制到剪贴板", "成功")

    @Slot(object)
    def set_theme(self, theme):
        setTheme(theme)

    def closeEvent(self, event):
        if self.thread is not None and self.thread.isRunning():
            self.close_after_task = True
            self.cancel_task()
            event.ignore()
            return
        for page in self.task_pages:
            page.footer.ring.stop()
        self._cancel_reset_timer()
        super().closeEvent(event)


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
    application = QApplication(sys.argv)
    configure_application(application)
    window = MainWindow()
    window.show()
    result = application.exec()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    application.processEvents()
    return result


if __name__ == "__main__":
    sys.exit(main())
