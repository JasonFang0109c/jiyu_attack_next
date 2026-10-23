import shutil
import sys
import threading
import time
import traceback
from pathlib import Path
from threading import Event

from PySide6.QtCore import QCoreApplication, QEvent, QLocale, QSettings, Qt, QTimer, Slot
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QSystemTrayIcon
from qfluentwidgets import (Action, CaptionLabel, Dialog, FluentIcon as FIF,
                            FluentTranslator, HyperlinkButton, FluentWindow, InfoBar,
                            InfoBarPosition, NavigationItemPosition, SystemTrayMenu,
                            Theme, setTheme, setThemeColor)

from cli import main as core
from .models import (CLOSE_BEHAVIOR_QUIT, CLOSE_BEHAVIOR_SETTINGS_KEY,
                     CLOSE_BEHAVIOR_TRAY, DATA_DIRECTORY_NAME,
                     DEFAULT_CLOSE_BEHAVIOR, SETTINGS_FILE_NAME, ConnectionState,
                     DeviceAliasStore, LogLevel, LogStore, normalize_close_behavior,
                     normalize_log_level, portable_data_dir, portable_log_path,
                     portable_settings)
from .pages import (AboutPage, AliasPage, CommandPage, DevicePage, FilePage,
                    FirewallPage, LocalPage, LogPage, MessagePage, SettingsPage)
from .workers import SendWorker, TaskWorker


APP_NAME = "JiYu Attack Next"
CATEGORIES = {"message": "文本消息", "command": "远程命令", "device": "设备操作",
              "file": "文件传送", "local": "本机信息", "firewall": "防火墙"}


def configure_application(application):
    application.setFont(QFont("Microsoft YaHei UI", 10))
    locale = QLocale(QLocale.Chinese, QLocale.China)
    QLocale.setDefault(locale)
    application.fluent_translator = FluentTranslator(locale)
    application.installTranslator(application.fluent_translator)
    setTheme(Theme.LIGHT, save=False)
    setThemeColor(QColor("#0067c0"), save=False)


def app_icon():
    resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return QIcon(str(resource_root / "assets" / "app.svg"))


class MainWindow(FluentWindow):
    def __init__(self, alias_store=None, data_dir=None, enable_tray=True):
        super().__init__()
        self.data_dir = Path(data_dir).resolve() if data_dir is not None else portable_data_dir()
        self.settings = portable_settings(self.data_dir)
        if alias_store is None:
            alias_store = DeviceAliasStore(settings=self.settings)
        self.thread = None
        self.worker = None
        self.active_cancel = None
        self.active_kind = ""
        self.active_started_at = None
        self.close_after_task = False
        self.enable_tray = bool(enable_tray)
        self.close_behavior = self._load_close_behavior()
        if not self.enable_tray:
            self.close_behavior = CLOSE_BEHAVIOR_QUIT
        self._settings_error = getattr(self, "_close_behavior_error", "")
        self._quit_requested = False
        self.tray_icon = None
        self.tray_menu = None
        self.connection_state = ConnectionState(alias_store, parent=self)
        self.alias_store = self.connection_state.aliases
        self.alias_store.changed.connect(self._aliases_changed)
        self.logs = LogStore(self, log_path=portable_log_path(self.data_dir))
        self._configure_file_logging()
        self.setWindowTitle(APP_NAME)
        self.titleBar.hBoxLayout.setContentsMargins(6, 0, 0, 0)
        self.setWindowIcon(app_icon())
        self._setup_tray()
        self.setMicaEffectEnabled(False)
        self.setCustomBackgroundColor("#f5f6f8", "#202020")
        self.setMinimumSize(960, 640)
        self.resize(1180, 780)
        self.stackedWidget.setAnimationEnabled(False)
        self.pages = {
            "message": MessagePage(self.connection_state, self),
            "command": CommandPage(self.connection_state, self),
            "device": DevicePage(self.connection_state, self),
            "file": FilePage(self.connection_state, self),
            "aliases": AliasPage(self.connection_state, self),
            "local": LocalPage(self),
            "firewall": FirewallPage(self),
            "logs": LogPage(self.logs, self),
            "settings": SettingsPage(self.logs, self.close_behavior, self),
            "about": AboutPage(self),
        }
        self.network_pages = [self.pages[key] for key in ("message", "command", "device")]
        self.task_pages = self.network_pages + [self.pages["file"], self.pages["local"],
                                                 self.pages["firewall"]]
        self._build_navigation()
        self._connect_actions()
        self.logs.info(
            "应用",
            "界面已就绪",
            details="数据目录：%s；关闭行为：%s；运行等级：%s；Python：%s；日志格式：规范文本" % (
                self.data_dir, self.close_behavior, self.logs.minimum_level,
                sys.version.split()[0]),
        )
        if self.logs.storage_error:
            self.logs.warning("运行日志", self.logs.storage_error)
            self._notify("运行日志", self.logs.storage_error, "警告")
        if self._settings_error:
            self.logs.warning("设置", self._settings_error)

    def _load_close_behavior(self):
        self._close_behavior_error = ""
        raw = self.settings.value(CLOSE_BEHAVIOR_SETTINGS_KEY, DEFAULT_CLOSE_BEHAVIOR)
        try:
            return normalize_close_behavior(raw)
        except ValueError:
            self._close_behavior_error = "关闭窗口行为配置无效，已恢复默认托盘模式"
            return DEFAULT_CLOSE_BEHAVIOR

    def _setup_tray(self):
        if not self.enable_tray:
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.logs.warning("系统托盘", "系统托盘不可用，关闭窗口将直接退出")
            return

        self.tray_icon = QSystemTrayIcon(self.windowIcon(), self)
        self.tray_icon.setToolTip(APP_NAME)
        self.tray_menu = SystemTrayMenu(parent=self)
        self.tray_menu.addActions([
            Action("显示主窗口", triggered=self.show_from_tray),
            Action("退出", triggered=self.quit_from_tray),
        ])
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _configure_file_logging(self):
        """启动时写入本次运行环境，便于从日志复现问题。"""
        self.logs.add(
            "运行日志",
            "日志系统已初始化",
            LogLevel.INFO,
            "日志文件：%s；线程：%s；GUI 版本：%s" % (
                self.logs.log_path or "未启用", threading.current_thread().name, APP_NAME),
        )

    def _build_navigation(self):
        self.navigationInterface.setExpandWidth(200)
        self.navigationInterface.setMinimumExpandWidth(1050)
        self.navigationInterface.setReturnButtonVisible(False)
        self.navigationInterface.addItemHeader("远程操作")
        self.addSubInterface(self.pages["message"], FIF.MESSAGE, "文本消息")
        self.addSubInterface(self.pages["command"], FIF.COMMAND_PROMPT, "远程命令")
        self.addSubInterface(self.pages["device"], FIF.POWER_BUTTON, "设备操作")
        self.addSubInterface(self.pages["file"], FIF.SEND, "文件传送")
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
        self.pages["file"].footer.requested.connect(self.start_file_transfer)
        self.pages["file"].chooseRequested.connect(self.choose_transfer_file)
        self.pages["local"].footer.requested.connect(self.start_local_probe)
        self.pages["local"].copyRequested.connect(self.copy_local_ip)
        self.pages["firewall"].footer.requested.connect(self.start_firewall)
        for page in self.task_pages:
            page.footer.cancelled.connect(self.cancel_task)
            page.footer.viewLogs.connect(lambda: self.show_page("logs"))
        message = self.pages["message"]
        message.importRequested.connect(self.import_message)
        message.saveRequested.connect(self.save_message)
        self.pages["logs"].exportSelectedRequested.connect(self.export_selected_logs)
        self.pages["logs"].deleteSelectedRequested.connect(self.delete_selected_logs)
        self.pages["logs"].cancelRequested.connect(self.cancel_task)
        self.pages["settings"].themeRequested.connect(self.set_theme)
        self.pages["settings"].closeBehaviorRequested.connect(self.set_close_behavior)
        self.pages["settings"].logLevelRequested.connect(self.set_log_level)
        self.pages["about"].clearDataRequested.connect(self.clear_data)

    def show_page(self, key):
        self.switchTo(self.pages[key])

    def current_page(self):
        return self.stackedWidget.currentWidget().objectName()

    def _notify(self, title, message, level="信息"):
        if self.close_after_task:
            return
        if not self.isVisible() and self.tray_icon is not None:
            self.tray_icon.showMessage(
                title, str(message), QSystemTrayIcon.MessageIcon.Information, 4000)
            return
        function = {"错误": InfoBar.error, "成功": InfoBar.success, "警告": InfoBar.warning}.get(level, InfoBar.info)
        function(title=title, content=message, orient=Qt.Horizontal, isClosable=True,
                 position=InfoBarPosition.TOP_RIGHT, duration=4000, parent=self)

    def _confirm(self, title, content, confirm_text="确认执行"):
        dialog = Dialog(title, content, self)
        dialog.setFixedSize(520, 280)
        dialog.yesButton.setText(confirm_text)
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
            details = "输入目标：%s；端口：%d；异常：%s" % (
                alias_name or "（空）", options.port, error)
            if self.connection_state.aliases.match(alias_name) is None:
                self._validation_error(kind, str(error), details)
            else:
                self._validation_error(kind, "设备备注对应的 IP 无效", details)
            return
        try:
            core.validate_options(options)
            if options.command:
                core.pkg_sendlist("-c", options.command)
        except (ValueError, UnicodeError) as error:
            self._validation_error(kind, str(error), "发送参数校验失败：%s" % error)
            return
        target_text = self.connection_state.format_target()
        target_input_text = self.connection_state.values["target"].strip()
        if kind == "device":
            action = "重启" if options.extra == "r" else "关机"
            content = "目标：%s\nUDP 端口：%d\n设备数量：%d\n操作：%s" % (
                target_text, options.port, len(hosts), action)
            if not self._confirm("确认%s" % action, content):
                self.logs.info(CATEGORIES[kind], "用户取消了%s确认" % action,
                               "目标：%s；端口：%d；设备数量：%d" % (
                                   target_text, options.port, len(hosts)))
                return
        options.cancel_event = Event()
        self.active_cancel = options.cancel_event
        if target_input_text.casefold() != options.target.casefold():
            message = "开始发送：%s，解析为 %s，端口 %d，%d 轮" % (
                target_input_text, options.target, options.port, options.loops)
        else:
            message = "开始发送：%s，端口 %d，%d 轮" % (
                target_text, options.port, options.loops)
        payload = options.message if kind == "message" else options.command
        details = "功能：%s；目标：%s；设备数：%d；端口：%d；轮数：%d；间隔：%s；负载长度：%d" % (
            CATEGORIES[kind], options.target, len(hosts), options.port, options.loops,
            options.interval, len(payload or ""))
        self.logs.info(CATEGORIES[kind], message, details)
        self.logs.debug(CATEGORIES[kind], "发送参数快照", details)
        self._begin_task(kind, SendWorker(options, core.execute_send), self._send_finished, self._send_failed)

    def _validation_error(self, kind, message, details=""):
        self.pages[kind].footer.set_status(message)
        self.logs.warning(CATEGORIES[kind], message,
                          details or "功能：%s；校验未通过" % CATEGORIES[kind])
        self._notify("请检查参数", message, "警告")

    def choose_transfer_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "选择要传送的文件", "", "所有文件 (*)")
        if not filename:
            return
        try:
            size = Path(filename).stat().st_size
        except OSError as error:
            self.logs.error(CATEGORIES["file"], "无法读取待传送文件",
                            "文件：%s；异常：%s" % (filename, error))
            self._notify("无法读取文件", str(error), "错误")
            return
        self.pages["file"].set_file(filename, size)
        self.pages["file"].footer.set_status("已选择：%s" % Path(filename).name)
        self.logs.info(CATEGORIES["file"], "已选择文件：%s（%s）" % (filename, core.format_size(size)),
                       "文件路径：%s；字节数：%d" % (filename, size))

    def start_file_transfer(self):
        if self.thread is not None:
            return
        page = self.pages["file"]
        if not page.path:
            self._validation_error("file", "请先选择要传送的文件")
            return
        target = self.connection_state.resolve_target().strip()
        try:
            hosts = core.get_ip(target)
        except ValueError as error:
            page.targets.target_input.setError(True)
            self._validation_error("file", str(error))
            return
        if len(hosts) != 1:
            self._validation_error("file", "文件传送仅支持单个目标地址")
            return
        try:
            source = core.validate_file_transfer(target, self.connection_state.values["port"], page.path)
        except ValueError as error:
            self._validation_error("file", str(error))
            return
        if not self._confirm(
                "确认传送文件",
                "目标：%s\n文件：%s\n大小：%s\n目标保存位置：当前用户桌面" % (
                    target, source.name, core.format_size(source.stat().st_size))):
            self.logs.info(CATEGORIES["file"], "用户取消了文件传送确认",
                           "目标：%s；文件：%s" % (target, source))
            return
        cancel_event = Event()
        self.active_cancel = cancel_event
        page.reset_progress()
        self.logs.info(CATEGORIES["file"], "开始传送：%s → %s" % (source.name, target),
                       "文件：%s；字节数：%d；端口：%d；超时：120 秒" % (
                           source, source.stat().st_size, self.connection_state.values["port"]))
        self._begin_task(
            "file",
            TaskWorker(core.transfer_file, target, self.connection_state.values["port"],
                       str(source), None, 120, cancel_event=cancel_event),
            self._file_finished, self._file_failed)

    @Slot(object)
    def _file_finished(self, result):
        page = self.pages["file"]
        page.set_progress(100)
        message = "文件已传送到目标桌面：%s（%s）" % (
            result["name"], core.format_size(result["size"]))
        page.footer.set_status(message)
        self.logs.info(CATEGORIES["file"], message, "目标：%s；文件：%s；字节数：%s" % (
            result["target"], result["name"], result["size"]))
        self._notify("文件传送完成", message, "成功")

    @Slot(str, str)
    def _file_failed(self, message, details=""):
        cancelled = message == "操作已取消"
        page = self.pages["file"]
        page.reset_progress()
        page.footer.set_status(message)
        if cancelled:
            self.logs.info(CATEGORIES["file"], message, details)
        else:
            self.logs.error(CATEGORIES["file"], message, details)
        self._notify("传送已取消" if cancelled else "文件传送失败", message,
                     "信息" if cancelled else "错误")

    def start_local_probe(self):
        if self.thread is not None:
            return
        self.logs.info("本机信息", "开始查询本机 IP 与监听端口")
        self._begin_task("local", TaskWorker(probe_local), self._probe_finished, self._local_failed)

    def start_firewall(self):
        if self.thread is not None:
            return
        action = self.pages["firewall"].action()
        action_name = "阻断连接" if action == "block" else "恢复允许"
        if not self._confirm("确认防火墙操作", "在本机对 StudentMain.exe 规则执行“%s”？" % action_name):
            self.logs.info("防火墙", "用户取消了防火墙操作", "操作：%s" % action_name)
            return
        self.logs.info("防火墙", "开始操作：%s" % action_name, "操作代码：%s" % action)
        self._begin_task("firewall", TaskWorker(apply_firewall, action), self._firewall_finished, self._local_failed)

    def _begin_task(self, kind, worker, finished, failed):
        self.active_kind = kind
        self.active_started_at = time.monotonic()
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
        self.pages["file"].set_busy(busy, self.active_cancel is not None)
        for key in ("local", "firewall"):
            self.pages[key].footer.set_busy(busy)
        self.pages["firewall"].action_box.setEnabled(not busy)
        self.pages["about"].clear_data_button.setEnabled(not busy)
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
        self.logs.debug(CATEGORIES[self.active_kind], message, "任务函数进度回调")
        self.pages[self.active_kind].footer.set_status(message)
        if self.active_kind == "file" and "下载文件：" in message:
            try:
                percent = int(message.rsplit("：", 1)[1].rstrip("%"))
            except ValueError:
                return
            self.pages["file"].set_progress(percent)

    @Slot(int)
    def _send_finished(self, count):
        message = "本机已发送 %d 个报文" % count
        self.pages[self.active_kind].footer.set_status(message)
        self.logs.info(CATEGORIES[self.active_kind], message,
                       "已发送报文数：%d；耗时：%.3f 秒" % (count, time.monotonic() - self.active_started_at))
        self._notify("发送完成", message, "成功")

    @Slot(str, str)
    def _send_failed(self, message, details=""):
        cancelled = message == "操作已取消"
        self.pages[self.active_kind].footer.set_status(message)
        details = "耗时：%.3f 秒；%s" % (
            time.monotonic() - self.active_started_at, details or "无异常堆栈")
        if cancelled:
            self.logs.info(CATEGORIES[self.active_kind], message, details)
        else:
            self.logs.error(CATEGORIES[self.active_kind], message, details)
        self._notify("发送已取消" if cancelled else "发送失败", message,
                     "信息" if cancelled else "错误")

    @Slot(object)
    def _probe_finished(self, result):
        ip, ports = result
        self.pages["local"].set_result(ip, ports)
        message = "查询完成，发现 %d 个监听端口" % len(ports)
        self.pages["local"].footer.set_status(message)
        self.logs.info("本机信息", "本机 IP：%s；监听端口：%s" % (ip, ", ".join(ports) or "未发现"),
                       "IP：%s；端口数：%d；耗时：%.3f 秒" % (
                           ip, len(ports), time.monotonic() - self.active_started_at))

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
            message_text = "%s\n%s" % (command, output)
            if success:
                self.logs.info("防火墙", message_text, "命令执行成功")
            else:
                self.logs.error("防火墙", message_text, "命令执行失败")
        self._notify("防火墙", message, "警告" if failed else "成功")

    @Slot(str, str)
    def _local_failed(self, message, details=""):
        self.pages[self.active_kind].footer.set_status(message)
        self.logs.error(CATEGORIES[self.active_kind], message,
                        "耗时：%.3f 秒；%s" % (
                            time.monotonic() - self.active_started_at,
                            details or "无异常堆栈"))
        self._notify("操作失败", message, "错误")

    def cancel_task(self):
        if self.active_cancel and not self.active_cancel.is_set():
            self.active_cancel.set()
            self.pages[self.active_kind].footer.set_status("正在取消")
            for page in self.task_pages:
                page.footer.cancel_button.setEnabled(False)
            self.pages["logs"].cancel_button.setEnabled(False)
            self.logs.warning(CATEGORIES[self.active_kind], "已请求取消",
                              "任务：%s；耗时：%.3f 秒" % (
                                  CATEGORIES[self.active_kind],
                                  time.monotonic() - self.active_started_at))

    @Slot()
    def _thread_finished(self):
        self.thread = None
        self.worker = None
        self.active_cancel = None
        self.active_started_at = None
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
            self.logs.info("应用", "消息文本已导入",
                           "文件：%s；字符数：%d" % (filename, len(text)))
        except (OSError, UnicodeError) as error:
            self.logs.error("应用", "导入消息失败", "文件：%s；异常：%s" % (filename, error))
            self._notify("导入失败", str(error), "错误")

    def save_message(self):
        filename, _ = QFileDialog.getSaveFileName(self, "保存消息", "消息.txt", "文本文件 (*.txt)")
        if filename:
            self._save_text(filename, self.pages["message"].editor.toPlainText())

    @Slot(object)
    def export_selected_logs(self, entries):
        filename, _ = QFileDialog.getSaveFileName(
            self, "导出选中日志", "运行日志-选中.txt", "文本文件 (*.txt)")
        if filename:
            self._save_text(filename, self.pages["logs"].export_text(entries))

    @Slot(object)
    def delete_selected_logs(self, uids):
        if not uids:
            return
        if not self._confirm("删除选中日志", "确定删除选中的 %d 条运行日志？此操作会同步更新日志文件。" % len(uids)):
            self.logs.info("运行日志", "用户取消了日志删除", "待删除记录数：%d" % len(uids))
            return
        removed = self.logs.remove_entries(uids)
        self.logs.info("运行日志", "已删除选中日志", "删除记录数：%d" % len(removed))

    @Slot(str)
    def set_log_level(self, level):
        previous = self.logs.minimum_level
        normalized = normalize_log_level(level)
        self.logs.set_level(normalized)
        self.logs.warning("运行日志", "运行日志等级已调整",
                          "原等级：%s；新等级：%s" % (previous, normalized))

    def _save_text(self, filename, text):
        try:
            Path(filename).write_text(text, encoding="utf-8-sig")
        except OSError as error:
            self.logs.error("应用", "保存文本失败", "文件：%s；异常：%s" % (filename, error))
            self._notify("保存失败", str(error), "错误")
        else:
            self.logs.info("应用", "文本已保存", "文件：%s；字符数：%d" % (filename, len(text)))
            self._notify("已保存", Path(filename).name, "成功")

    def copy_local_ip(self):
        ip = self.pages["local"].ip_label.text()
        QApplication.clipboard().setText(ip)
        self.logs.info("本机信息", "本机 IP 已复制", "IP：%s" % ip)
        self._notify("已复制", "本机 IP 已复制到剪贴板", "成功")

    @Slot(object)
    def set_theme(self, theme):
        setTheme(theme, save=False)
        self.logs.info("应用", "界面主题已切换", "主题：%s" % theme)

    @Slot(str)
    def set_close_behavior(self, behavior):
        try:
            normalized = normalize_close_behavior(behavior)
        except ValueError as error:
            self.logs.error("设置", "关闭窗口行为保存失败", "输入：%s；异常：%s" % (
                behavior, error))
            self._notify("设置保存失败", str(error), "错误")
            return
        previous = self.close_behavior
        self.close_behavior = normalized
        self.settings.setValue(CLOSE_BEHAVIOR_SETTINGS_KEY, normalized)
        self.settings.sync()
        if self.settings.status() != QSettings.NoError:
            self.logs.error("设置", "关闭窗口行为保存失败",
                            "设置文件：%s；状态：%s" % (
                                self.settings.fileName(), self.settings.status()))
            self.close_behavior = previous
            self._notify("设置保存失败", "无法写入设置文件", "错误")
            return
        self.logs.info("设置", "关闭窗口行为已更新",
                       "原行为：%s；新行为：%s" % (previous, normalized))

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_from_tray()

    def show_from_tray(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
        self.logs.info("系统托盘", "从系统托盘恢复主窗口")

    def quit_from_tray(self):
        self._quit_requested = True
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.close()
        if self.isVisible():
            self.logs.info("系统托盘", "退出请求将在当前任务结束后执行",
                           "任务：%s" % (self.active_kind or "无"))

    def _hide_to_tray(self):
        if self.tray_icon is None:
            return False
        self.tray_icon.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.hide()
        self.logs.info("系统托盘", "窗口已隐藏到系统托盘",
                       "关闭行为：保留在系统托盘")
        return True

    def _remove_tray(self, destroy=True):
        if self.tray_icon is not None:
            self.tray_icon.hide()
            if destroy:
                self.tray_icon.deleteLater()
            self.tray_icon = None
        if self.tray_menu is not None:
            if destroy:
                self.tray_menu.deleteLater()
            self.tray_menu = None

    @Slot()
    def clear_data(self):
        if self.thread is not None:
            self._notify("无法清除数据", "请等待当前任务结束后再试", "警告")
            return
        confirmed = self._confirm(
            "清除本地数据",
            "将删除 JiYuAttackNextData 文件夹中的设备备注、界面设置和运行日志。\n"
            "此操作无法撤销。",
            "确认清除",
        )
        if not confirmed:
            self.logs.info("关于", "用户取消了清除本地数据")
            return
        self.logs.info("关于", "开始清除本地数据", "目录：%s" % self.data_dir)
        target = self.data_dir
        log_path = self.logs.log_path
        self.logs.log_path = None
        self._remove_tray(destroy=False)
        self.tray_icon = None
        self.tray_menu = None
        try:
            if target.exists():
                resolved = target.resolve()
                if resolved == Path(resolved.anchor) or resolved == Path.cwd().resolve():
                    raise OSError("拒绝删除非数据目录路径：%s" % resolved)
                shutil.rmtree(resolved)
        except OSError as error:
            self.logs.log_path = log_path
            if self.enable_tray and QSystemTrayIcon.isSystemTrayAvailable():
                self._setup_tray()
            self.logs.error("关于", "清除本地数据失败",
                            "目录：%s；异常：%s" % (target, error))
            self._notify("清除数据失败", str(error), "错误")
            return
        # 删除成功后本次运行不再写入旧日志文件，避免重新创建数据目录。
        self.logs.log_path = None
        self.alias_store.clear(persist=False)
        self.connection_state.reset()
        self.logs.clear(persist=False)
        self.settings = portable_settings(self.data_dir)
        self.close_behavior = DEFAULT_CLOSE_BEHAVIOR
        self.pages["settings"].set_close_behavior(DEFAULT_CLOSE_BEHAVIOR)
        if self.enable_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self._setup_tray()
        self.logs.info("关于", "本地数据已清除",
                       "目录：%s；关闭行为已恢复默认托盘模式；本次运行文件日志暂停" % self.data_dir)
        self._notify("数据已清除", "已删除 JiYuAttackNextData 文件夹并恢复默认设置", "成功")

    def _aliases_changed(self):
        self.logs.info("应用", "设备备注已更新", "当前备注数：%d" % len(self.alias_store.items()))

    def closeEvent(self, event):
        if self.thread is not None and self.thread.isRunning():
            self.close_after_task = True
            self.cancel_task()
            event.ignore()
            return
        if (not self._quit_requested and self.close_behavior == CLOSE_BEHAVIOR_TRAY
                and self.tray_icon is not None):
            event.ignore()
            self._hide_to_tray()
            return
        for page in self.task_pages:
            page.footer.ring.stop()
        self.logs.info("应用", "应用退出",
                       "关闭行为：%s" % self.close_behavior)
        self._remove_tray()
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
    install_exception_logging(window.logs)
    window.show()
    result = application.exec()
    window._quit_requested = True
    window.close()
    if window.isVisible():
        window.hide()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    application.processEvents()
    return result


def install_exception_logging(store):
    """把未捕获异常写入运行日志，保留原始异常钩子行为。"""
    previous_hook = sys.excepthook

    def handle_exception(exception_type, exception, tb):
        try:
            details = "".join(traceback.format_exception(exception_type, exception, tb))
            store.error("应用", "未捕获异常：%s" % exception, details)
        finally:
            previous_hook(exception_type, exception, tb)

    sys.excepthook = handle_exception
    return previous_hook


if __name__ == "__main__":
    sys.exit(main())
