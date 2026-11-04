"""图形界面主窗口：单实例控制、任务队列、托盘与各页面的信号接线。"""

import base64
import getpass
import hashlib
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path
from threading import Event

from PySide6.QtCore import (
    QByteArray,
    QCoreApplication,
    QEvent,
    QLocale,
    QObject,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QFileDialog, QSystemTrayIcon
from qfluentwidgets import (
    Action,
    Dialog,
    FluentIcon as FIF,
    FluentTranslator,
    FluentWindow,
    InfoBar,
    InfoBarPosition,
    NavigationItemPosition,
    isDarkTheme,
    SystemTrayMenu,
    Theme,
    setTheme,
    setThemeColor,
)

from .. import core
from .build_info import version_text
from .components import center_dialog
from .models import (
    CLOSE_BEHAVIOR_QUIT,
    CLOSE_BEHAVIOR_SETTINGS_KEY,
    CLOSE_BEHAVIOR_TRAY,
    DEFAULT_CLOSE_BEHAVIOR,
    DEFAULT_MICA_ENABLED,
    FIRST_CLOSE_PROMPT_SETTINGS_KEY,
    MICA_SETTINGS_KEY,
    WINDOW_GEOMETRY_SETTINGS_KEY,
    ConnectionState,
    DeviceAliasStore,
    LogLevel,
    LogStore,
    mica_available,
    normalize_close_behavior,
    normalize_log_level,
    normalize_switch,
    portable_data_dir,
    portable_log_path,
    portable_settings,
)
from .pages import (
    AboutPage,
    AliasPage,
    CommandPage,
    DevicePage,
    FilePage,
    FirewallPage,
    LocalPage,
    LogPage,
    MessagePage,
    SettingsPage,
)
from .settings_store import STATUS_NO_ERROR
from .window_effect import apply_acrylic, remove_acrylic
from .workers import SendWorker, TaskWorker

APP_NAME = "JiYu Attack Next"
SINGLE_INSTANCE_KEY = "JiYuAttackNext-single-instance"
# 测试会把模块里的 QApplication 换成替身，这里留住真实类用于启动流程的类型判断。
REAL_APPLICATION = QApplication
USAGE_NOTICE_TITLE = "使用须知"
USAGE_NOTICE_TEXT = (
    "本工具仅面向已获授权的教学环境测试与安全研究，"
    "不得用于任何未授权的目标，也不得用于干扰他人正常使用。\n\n"
    "使用前请确认你已取得目标设备与网络的管理或测试授权；"
    "因违规或恶意使用造成的一切后果由使用者自行承担，"
    "作者与本项目不承担任何责任。\n\n"
    "点击“同意并继续”表示你已阅读并接受上述声明。"
)
CATEGORIES = {
    "message": "文本消息",
    "command": "远程命令",
    "device": "设备操作",
    "file": "文件传送",
    "local": "本机信息",
    "firewall": "防火墙",
}


def single_instance_key():
    """生成当前用户的单实例标识，避免多用户会话互相阻塞。"""
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    digest = hashlib.sha1(user.encode("utf-8", "replace")).hexdigest()[:12]
    return "%s-%s" % (SINGLE_INSTANCE_KEY, digest)


class SingleInstance(QObject):
    """保证同一时间只运行一个 GUI 实例；再次启动会唤醒已有窗口。"""

    activationRequested = Signal()

    def __init__(self, key=None, parent=None):
        super().__init__(parent)
        self.key = key or single_instance_key()
        self.server = None
        self.primary = False
        # 日志存储由主窗口创建后回填；第二次启动拿不到主窗口，此时保持为空。
        self.logs = None

    def _log(self, level, message, details=""):
        """写入单实例相关日志，日志存储尚未就绪时静默跳过。"""
        if self.logs is None:
            return
        getattr(self.logs, level)("应用", message, details)

    def acquire(self):
        """尝试成为主实例，成功返回 True；已有实例时唤醒它并返回 False。"""
        if self.notify_existing():
            self._log(
                "info",
                "已有实例在运行，已请求其恢复主窗口",
                "单实例标识：%s" % self.key,
            )
            return False
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(self.key):
            # 上次异常退出可能遗留同名服务端，清理后重试一次。
            QLocalServer.removeServer(self.key)
            if not server.listen(self.key):
                self._log("error", "单实例服务启动失败", "单实例标识：%s" % self.key)
                return False
        server.newConnection.connect(self._handle_connection)
        self.server = server
        self.primary = True
        self._log("debug", "单实例服务已启动", "单实例标识：%s" % self.key)
        return True

    def notify_existing(self):
        """通知已有实例显示窗口。"""
        socket = QLocalSocket(self)
        socket.connectToServer(self.key)
        if not socket.waitForConnected(500):
            return False
        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        return True

    def _handle_connection(self):
        """接受新连接并发出唤醒信号，让已运行的窗口显示出来。"""
        while self.server is not None and self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            if connection is None:
                break
            connection.readyRead.connect(
                lambda link=connection: self._read_activation(link)
            )
            connection.disconnected.connect(connection.deleteLater)
            if connection.bytesAvailable():
                self._read_activation(connection)
        self._log("debug", "收到第二次启动的唤醒请求")
        self.activationRequested.emit()

    def _read_activation(self, connection):
        try:
            connection.readAll()
        except RuntimeError:
            self._log("warning", "读取唤醒请求失败，连接可能已关闭")
            return

    def close(self):
        """关闭本地服务端并移除同名服务，避免下次启动被残留占用。"""
        if self.server is not None:
            self.server.close()
            QLocalServer.removeServer(self.key)
            self.server.deleteLater()
            self.server = None
            self._log("debug", "单实例服务已关闭", "单实例标识：%s" % self.key)
        self.primary = False


def configure_application(application):
    """设置全局字体、中文区域与默认主题色。"""
    application.setFont(QFont("Microsoft YaHei UI", 10))
    # 应用级图标会让使用须知等在主窗口之前出现的对话框也用同一个任务栏图标。
    application.setWindowIcon(app_icon())
    locale = QLocale(QLocale.Chinese, QLocale.China)
    QLocale.setDefault(locale)
    application.fluent_translator = FluentTranslator(locale)
    application.installTranslator(application.fluent_translator)
    setTheme(Theme.LIGHT, save=False)
    setThemeColor(QColor("#0067c0"), save=False)


def app_icon():
    """返回窗口图标；打包后从 EXE 解压目录读取资源。"""
    resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return QIcon(str(resource_root / "assets" / "app.svg"))


class MainWindow(FluentWindow):
    """主窗口：持有连接状态、日志与全部页面，并串行调度后台任务。

    Attributes:
        connection_state: 目标、端口、轮数与设备备注等共享状态。
        logs: 运行日志存储，同时写入界面与日志文件。
        pages: 页面名到页面实例的映射，键与 ``CATEGORIES`` 保持一致。
        thread: 正在运行的后台线程，空闲时为 None。
        _task_queue: 排队等待执行的任务，元素为 (kind, worker, finished, failed)。
    """

    # 退出清理完成后显式请求结束事件循环：从托盘退出时窗口已隐藏，
    # Qt 的“最后一个窗口关闭”不会触发，只靠关闭窗口会让进程一直空转。
    quitRequested = Signal()

    def __init__(self, alias_store=None, data_dir=None, enable_tray=True):
        super().__init__()
        self.data_dir = (
            Path(data_dir).resolve() if data_dir is not None else portable_data_dir()
        )
        self.settings = portable_settings(self.data_dir)
        if alias_store is None:
            alias_store = DeviceAliasStore(settings=self.settings)
        self.thread = None
        self.worker = None
        self._task_queue = []
        self.active_cancel = None
        self.active_kind = ""
        self.active_started_at = None
        self.close_after_task = False
        self.enable_tray = bool(enable_tray)
        self.close_behavior = self._load_close_behavior()
        if not self.enable_tray:
            self.close_behavior = CLOSE_BEHAVIOR_QUIT
        self._settings_error = getattr(self, "_close_behavior_error", "")
        # 配置文件整体读取失败时也要提示一次，否则用户只会看到设置全部回落到默认值。
        if self.settings.message and not self._settings_error:
            self._settings_error = self.settings.message
        self.first_close_prompt_shown = self._load_first_close_prompt_shown()
        self._quit_requested = False
        self._quit_finished = False
        self._first_close_dialog_open = False
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
        self.blur_enabled = False
        self.mica_enabled = self._load_mica_enabled()
        self.apply_mica(self.mica_enabled)
        self.setCustomBackgroundColor("#f5f6f8", "#202020")
        self.setMinimumSize(960, 640)
        self.resize(1180, 780)
        self._restore_window_geometry()
        self.stackedWidget.setAnimationEnabled(False)
        self.pages = {
            "message": MessagePage(self.connection_state, self),
            "command": CommandPage(self.connection_state, self),
            "device": DevicePage(self.connection_state, self),
            "file": FilePage(self.connection_state, self),
            "aliases": AliasPage(self.connection_state, self, logs=self.logs),
            "local": LocalPage(self),
            "firewall": FirewallPage(self),
            "logs": LogPage(self.logs, self),
            "settings": SettingsPage(
                self.logs, self.close_behavior, self.mica_enabled, self
            ),
            "about": AboutPage(self),
        }
        self.network_pages = [
            self.pages[key] for key in ("message", "command", "device")
        ]
        self.task_pages = self.network_pages + [
            self.pages["file"],
            self.pages["local"],
            self.pages["firewall"],
        ]
        self._build_navigation()
        self._connect_actions()
        self.logs.info(
            "应用",
            "界面已就绪",
            details="数据目录：%s；关闭行为：%s；运行等级：%s；Python：%s；日志格式：规范文本"
            % (
                self.data_dir,
                self.close_behavior,
                self.logs.minimum_level,
                sys.version.split()[0],
            ),
        )
        if self.logs.storage_error:
            self.logs.warning("运行日志", self.logs.storage_error)
            self._notify("运行日志", self.logs.storage_error, "警告")
        if self._settings_error:
            self.logs.warning("设置", self._settings_error)

    def _load_close_behavior(self):
        """读取关闭行为配置，配置损坏时回落默认值并记录原因。"""
        self._close_behavior_error = ""
        raw = self.settings.value(CLOSE_BEHAVIOR_SETTINGS_KEY, DEFAULT_CLOSE_BEHAVIOR)
        try:
            return normalize_close_behavior(raw)
        except ValueError:
            self._close_behavior_error = "关闭窗口行为配置无效，已恢复默认托盘模式"
            return DEFAULT_CLOSE_BEHAVIOR

    def _load_first_close_prompt_shown(self):
        value = self.settings.value(FIRST_CLOSE_PROMPT_SETTINGS_KEY, False)
        if isinstance(value, str):
            return value.strip().casefold() in ("1", "true", "yes", "on")
        return bool(value)

    def _load_mica_enabled(self):
        """读取背景模糊开关，配置缺失或无法识别时使用默认值。"""
        raw = self.settings.value(MICA_SETTINGS_KEY, None)
        return normalize_switch(raw, DEFAULT_MICA_ENABLED)

    def apply_mica(self, enabled):
        """按开关状态启用或关闭窗口背景模糊。

        Args:
            enabled: ``True`` 表示希望启用背景模糊。

        Note:
            实际效果是亚克力实时模糊而不是系统云母：云母只采样桌面壁纸，
            窗口下方压着别的应用时背景不会跟着变；亚克力由 DWM 实时模糊
            窗口下方的全部内容。库的开关名仍是 mica，它同时负责把窗口背景
            刷成透明，两者配合模糊才能透出来。
        """
        enabled = bool(enabled) and mica_available()
        self.blur_enabled = enabled
        self.setMicaEffectEnabled(enabled)
        handle = int(self.winId())
        if not enabled:
            remove_acrylic(handle)
            # 库在非 Windows 11 上会直接返回，背景色要自己恢复，否则窗口全透明。
            self.setBackgroundColor(
                QColor("#202020") if isDarkTheme() else QColor("#f5f6f8")
            )
            return
        # 库只在 Windows 11 上把背景刷成透明，低版本要自己刷，否则亚克力被盖住。
        self.setBackgroundColor(QColor(0, 0, 0, 0))
        apply_acrylic(handle, isDarkTheme())

    def _refresh_background_effect(self):
        """重新应用模糊，系统在窗口显示与主题切换时会把背景重置回云母。"""
        if not self.blur_enabled:
            return
        apply_acrylic(int(self.winId()), isDarkTheme())

    def showEvent(self, event):
        """窗口显示后再应用一次模糊，覆盖库在 showEvent 里设下的云母。"""
        super().showEvent(event)
        self._refresh_background_effect()

    def _onThemeChangedFinished(self):
        """主题切换后重新应用模糊，深浅色决定染色与标题栏明暗。"""
        super()._onThemeChangedFinished()
        self._refresh_background_effect()

    def _restore_window_geometry(self):
        """恢复上次退出时的窗口位置与大小，越界时夹回当前屏幕。"""
        raw = self.settings.value(WINDOW_GEOMETRY_SETTINGS_KEY, "")
        if not isinstance(raw, str) or not raw.strip():
            self.logs.debug("应用", "没有可恢复的窗口位置，使用默认大小")
            return
        try:
            stored = QByteArray(base64.b64decode(raw.encode("ascii"), validate=True))
        except (ValueError, UnicodeEncodeError):
            self.logs.warning("设置", "窗口位置记录已损坏，使用默认大小")
            return
        if not self.restoreGeometry(stored):
            self.logs.warning("设置", "窗口位置恢复失败，使用默认大小")
            return
        self._clamp_to_screen()
        self.logs.debug(
            "应用",
            "已恢复窗口位置",
            "位置：%s；大小：%sx%s"
            % (self.pos().toTuple(), self.width(), self.height()),
        )

    def _clamp_to_screen(self):
        """把窗口夹回当前屏幕可用区域，避免显示器变化后窗口跑到屏幕外。"""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        bounds = screen.availableGeometry()
        frame = self.frameGeometry()
        left = max(bounds.left(), min(frame.left(), bounds.right() - frame.width() + 1))
        top = max(bounds.top(), min(frame.top(), bounds.bottom() - frame.height() + 1))
        if (left, top) != (frame.left(), frame.top()):
            self.move(left, top)

    def _center_on_screen(self):
        """把窗口放到当前屏幕中央，用于恢复默认布局。"""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        bounds = screen.availableGeometry()
        self.move(
            bounds.center().x() - self.width() // 2,
            bounds.center().y() - self.height() // 2,
        )

    def _save_window_geometry(self):
        """把当前窗口位置与大小写入设置文件。"""
        # 最小化状态下的几何是任务栏图标位置，写进去会让下次启动出现在角落。
        if self.isMinimized():
            return
        self.settings.set_value(
            WINDOW_GEOMETRY_SETTINGS_KEY,
            base64.b64encode(bytes(self.saveGeometry())).decode("ascii"),
        )
        self.settings.sync()
        if self.settings.status() != STATUS_NO_ERROR:
            self.logs.warning(
                "设置",
                "窗口位置保存失败",
                "设置文件：%s；状态：%s"
                % (self.settings.file_name(), self.settings.status()),
            )

    def _save_first_close_prompt_shown(self):
        self.first_close_prompt_shown = True
        self.settings.set_value(FIRST_CLOSE_PROMPT_SETTINGS_KEY, True)
        self.settings.sync()
        if self.settings.status() != STATUS_NO_ERROR:
            self.logs.warning(
                "设置",
                "首次关闭提示状态保存失败",
                "设置文件：%s；状态：%s"
                % (self.settings.file_name(), self.settings.status()),
            )

    def _setup_tray(self):
        """创建系统托盘图标与菜单；托盘不可用时关闭窗口即退出。"""
        if not self.enable_tray:
            self.logs.debug("系统托盘", "关闭行为为直接退出，未创建托盘图标")
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.logs.warning("系统托盘", "系统托盘不可用，关闭窗口将直接退出")
            return

        self.tray_icon = QSystemTrayIcon(self.windowIcon(), self)
        self.tray_icon.setToolTip(APP_NAME)
        self.tray_menu = SystemTrayMenu(parent=self)
        self.tray_menu.addActions(
            [
                Action("显示主窗口", triggered=self.show_from_tray),
                Action("退出", triggered=self.quit_from_tray),
            ]
        )
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()
        self.logs.info(
            "系统托盘",
            "系统托盘图标已创建",
            "提示文本：%s；菜单项数：2" % APP_NAME,
        )

    def _configure_file_logging(self):
        """启动时写入本次运行环境，便于从日志复现问题。"""
        self.logs.add(
            "运行日志",
            "日志系统已初始化",
            LogLevel.INFO,
            "日志文件：%s；线程：%s；GUI 版本：%s %s"
            % (
                self.logs.log_path or "未启用",
                threading.current_thread().name,
                APP_NAME,
                version_text(),
            ),
        )

    def _build_navigation(self):
        """按功能分组装配左侧导航，底部放日志、设置与关于。"""
        self.navigationInterface.setExpandWidth(200)
        self.navigationInterface.setMinimumExpandWidth(1050)
        self.navigationInterface.setReturnButtonVisible(False)
        self.navigationInterface.addItemHeader("远程操作")
        self.addSubInterface(self.pages["message"], FIF.MESSAGE, "文本消息")
        self.addSubInterface(self.pages["file"], FIF.SEND, "文件传送")
        self.addSubInterface(self.pages["device"], FIF.POWER_BUTTON, "设备操作")
        self.addSubInterface(self.pages["command"], FIF.COMMAND_PROMPT, "远程命令")
        self.addSubInterface(self.pages["aliases"], FIF.QUICK_NOTE, "设备备注")
        self.navigationInterface.addSeparator()
        self.navigationInterface.addItemHeader("本机工具")
        self.addSubInterface(self.pages["local"], FIF.IOT, "本机信息")
        self.addSubInterface(self.pages["firewall"], FIF.CERTIFICATE, "防火墙")
        self.addSubInterface(
            self.pages["logs"], FIF.HISTORY, "运行日志", NavigationItemPosition.BOTTOM
        )
        self.addSubInterface(
            self.pages["settings"], FIF.SETTING, "设置", NavigationItemPosition.BOTTOM
        )
        self.addSubInterface(
            self.pages["about"], FIF.INFO, "关于", NavigationItemPosition.BOTTOM
        )
        self.navigationInterface.expand(useAni=False)

    def _connect_actions(self):
        """把各页面的按钮与信号接到主窗口的处理方法。"""
        for kind in ("message", "command", "device"):
            self.pages[kind].footer.requested.connect(
                lambda key=kind: self.start_send(key)
            )
        self.pages["file"].footer.requested.connect(self.start_file_transfer)
        self.pages["file"].chooseFilesRequested.connect(self.choose_transfer_files)
        self.pages["file"].chooseFolderRequested.connect(self.choose_transfer_folder)
        self.pages["file"].deleteRequested.connect(self.delete_transfer_files)
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
        self.pages["settings"].micaRequested.connect(self.set_mica_enabled)
        self.pages["settings"].closeBehaviorRequested.connect(self.set_close_behavior)
        self.pages["settings"].logLevelRequested.connect(self.set_log_level)
        self.pages["settings"].clearDataRequested.connect(self.clear_data)

    def show_page(self, key):
        """切换到指定页面。"""
        self.switchTo(self.pages[key])

    def current_page(self):
        """返回当前页面名。"""
        return self.stackedWidget.currentWidget().objectName()

    def _notify(self, title, message, level="信息"):
        """显示提示：窗口隐藏时走托盘气泡，否则用右上角 InfoBar。"""
        # 退出流程中窗口即将销毁，此时再弹 InfoBar 会在关闭动画期间闪现。
        if self.close_after_task:
            return
        if not self.isVisible() and self.tray_icon is not None:
            self.tray_icon.showMessage(
                title, str(message), QSystemTrayIcon.MessageIcon.Information, 4000
            )
            return
        function = {
            "错误": InfoBar.error,
            "成功": InfoBar.success,
            "警告": InfoBar.warning,
        }.get(level, InfoBar.info)
        function(
            title=title,
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=4000,
            parent=self,
        )

    def _confirm(self, title, content, confirm_text="确认执行"):
        """弹出确认对话框，返回用户是否点击了确认按钮。"""
        dialog = Dialog(title, content, self)
        dialog.setFixedSize(520, 280)
        dialog.yesButton.setText(confirm_text)
        dialog.cancelButton.setText("取消")
        center_dialog(dialog)
        return bool(dialog.exec())

    def _options_for_page(self, kind):
        """按页面类型组装发送参数。"""
        if kind == "message":
            return self.connection_state.options(
                message=self.pages[kind].editor.toPlainText()
            )
        if kind == "command":
            return self.connection_state.options(
                command=self.pages[kind].editor.toPlainText()
            )
        if kind == "device":
            return self.connection_state.options(extra=self.pages[kind].action())
        self.logs.warning("应用", "不支持的发送功能", "功能代码：%s" % kind)
        raise ValueError("不支持的发送功能")

    def start_send(self, kind):
        """校验参数、确认设备操作后把发送任务加入队列。"""
        page = self.pages[kind]
        options = self._options_for_page(kind)
        try:
            hosts = core.get_ip(options.target)
        except ValueError as error:
            page.targets.target_input.setError(True)
            page.targets.target_input.setFocus()
            alias_name = self.connection_state.values["target"].strip()
            details = "输入目标：%s；端口：%d；异常：%s" % (
                alias_name or "（空）",
                options.port,
                error,
            )
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
            action = {"r": "重启", "s": "关机", "l": "注销"}[options.extra]
            method = (
                "（远程命令 %s）" % core.LOGOFF_COMMAND if options.extra == "l" else ""
            )
            content = "目标：%s\nUDP 端口：%d\n设备数量：%d\n操作：%s%s" % (
                target_text,
                options.port,
                len(hosts),
                action,
                method,
            )
            if not self._confirm("确认%s" % action, content):
                self.logs.info(
                    CATEGORIES[kind],
                    "用户取消了%s确认" % action,
                    "目标：%s；端口：%d；设备数量：%d"
                    % (target_text, options.port, len(hosts)),
                )
                return
        options.cancel_event = Event()
        if target_input_text.casefold() != options.target.casefold():
            message = "开始发送：%s，解析为 %s，端口 %d，%d 轮" % (
                target_input_text,
                options.target,
                options.port,
                options.loops,
            )
        else:
            message = "开始发送：%s，端口 %d，%d 轮" % (
                target_text,
                options.port,
                options.loops,
            )
        payload = options.message if kind == "message" else options.command
        details = (
            "功能：%s；目标：%s；设备数：%d；端口：%d；轮数：%d；间隔：%s；负载长度：%d"
            % (
                CATEGORIES[kind],
                options.target,
                len(hosts),
                options.port,
                options.loops,
                options.interval,
                len(payload or ""),
            )
        )
        self.logs.info(CATEGORIES[kind], message, details)
        self.logs.debug(CATEGORIES[kind], "发送参数快照", details)
        self._begin_task(
            kind,
            SendWorker(options, core.execute_send_report),
            self._send_finished,
            self._send_failed,
        )

    def _validation_error(self, kind, message, details=""):
        """参数不合法时统一写日志、更新页脚并弹出提示。"""
        self.pages[kind].footer.set_status(message)
        self.logs.warning(
            CATEGORIES[kind],
            message,
            details or "功能：%s；校验未通过" % CATEGORIES[kind],
        )
        self._notify("请检查参数", message, "警告")

    def choose_transfer_files(self):
        """选择单个或多个文件加入待传送列表。"""
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "选择要传送的文件", "", "所有文件 (*)"
        )
        if not filenames:
            self.logs.info(CATEGORIES["file"], "用户取消了文件选择")
            return
        self._add_transfer_paths(filenames)

    def choose_transfer_folder(self):
        """选择文件夹，整个目录会按原结构传送到目标桌面。"""
        directory = QFileDialog.getExistingDirectory(self, "选择要传送的文件夹")
        if not directory:
            self.logs.info(CATEGORIES["file"], "用户取消了文件夹选择")
            return
        self._add_transfer_paths([directory])

    def _add_transfer_paths(self, paths):
        """把路径展开成文件条目并加入列表，重复项会被忽略。"""
        page = self.pages["file"]
        try:
            count, size = page.add_paths(paths)
        except (OSError, ValueError) as error:
            self.logs.error(
                CATEGORIES["file"],
                "无法添加待传送文件",
                "路径：%s；异常：%s" % ("；".join(map(str, paths)), error),
            )
            self._notify("无法添加文件", str(error), "错误")
            return
        if not count:
            self.logs.info(
                CATEGORIES["file"],
                "所选文件已在待传送列表中",
                "路径：%s" % "；".join(map(str, paths)),
            )
            self._notify("未添加文件", "所选文件已在待传送列表中", "信息")
            return
        page.footer.set_status(
            "已添加 %d 个文件（%s）" % (count, core.format_size(size))
        )
        self.logs.info(
            CATEGORIES["file"],
            "已添加 %d 个待传送文件（%s）" % (count, core.format_size(size)),
            "路径：%s；总字节数：%d" % ("；".join(map(str, paths)), size),
        )

    def delete_transfer_files(self):
        """从待传送列表移除选中项，不删除源文件。"""
        page = self.pages["file"]
        selected = page.selected_entries()
        if not selected:
            self.logs.warning(CATEGORIES["file"], "未勾选待传送条目，无法删除")
            return
        if not self._confirm(
            "删除待传送文件",
            "确定从待传送列表中移除选中的 %d 项（文件或文件夹）？源文件不会被删除。"
            % len(selected),
            "删除",
        ):
            self.logs.info(
                CATEGORIES["file"],
                "用户取消了待传送文件删除",
                "选中项：%d" % len(selected),
            )
            return
        removed = page.remove_selected()
        self.logs.info(
            CATEGORIES["file"],
            "已从待传送列表移除 %d 个文件" % len(removed),
            "条目：%s" % "；".join(relative for _, relative, _ in removed),
        )

    def start_file_transfer(self):
        """校验待传送条目与目标后，把传送任务加入队列。"""
        page = self.pages["file"]
        selected = page.selected_items()
        if not page.has_files():
            self._validation_error("file", "请先选择要传送的文件")
            return
        if not selected:
            self._validation_error("file", "请勾选要传送的文件或文件夹")
            return
        target = self.connection_state.resolve_target().strip()
        try:
            hosts = core.get_ip(target)
        except ValueError as error:
            page.targets.target_input.setError(True)
            self._validation_error("file", str(error))
            return
        try:
            entries = core.normalize_transfer_items(selected)
            source = core.validate_file_transfer(
                target, self.connection_state.values["port"], str(entries[0][0])
            )
        except ValueError as error:
            self._validation_error("file", str(error))
            return
        total_size = sum(size for _, _, size in entries)
        if len(entries) == 1:
            file_label = source.name
        else:
            file_label = "%d 个文件" % len(entries)
        if not self._confirm(
            "确认传送文件",
            "目标：%s\n目标数量：%d\n文件：%s\n大小：%s\n目标保存位置：当前用户桌面"
            % (target, len(hosts), file_label, core.format_size(total_size)),
        ):
            self.logs.info(
                CATEGORIES["file"],
                "用户取消了文件传送确认",
                "目标：%s；文件：%s" % (target, file_label),
            )
            return
        cancel_event = Event()
        self.logs.info(
            CATEGORIES["file"],
            "开始传送：%s → %s（%d 个目标）" % (file_label, target, len(hosts)),
            "文件：%s；文件数：%d；总字节数：%d；目标数：%d；端口：%d；"
            "单目标超时：120 秒"
            % (
                file_label,
                len(entries),
                total_size,
                len(hosts),
                self.connection_state.values["port"],
            ),
        )
        self.logs.debug(
            CATEGORIES["file"],
            "待传送文件清单",
            "；".join(
                "%s (%d 字节)" % (relative, size) for _, relative, size in entries
            ),
        )
        self._begin_task(
            "file",
            TaskWorker(
                core.transfer_file,
                target,
                self.connection_state.values["port"],
                str(entries[0][0]),
                None,
                120,
                cancel_event=cancel_event,
                items=[(str(path), relative) for path, relative, _ in entries],
            ),
            self._file_finished,
            self._file_failed,
        )

    @Slot(object)
    def _file_finished(self, result):
        page = self.pages["file"]
        page.set_progress(100)
        targets = result.get("targets") or [result.get("target", "")]
        file_count = int(result.get("file_count") or 1)
        label = result["name"] if file_count == 1 else "%d 个文件" % file_count
        if len(targets) == 1:
            message = "文件已传送到目标桌面：%s（%s）" % (
                label,
                core.format_size(result["size"]),
            )
        else:
            message = "文件已传送到 %d 个目标桌面：%s（%s）" % (
                len(targets),
                label,
                core.format_size(result["size"]),
            )
        page.footer.set_status(message)
        self.logs.info(
            CATEGORIES["file"],
            message,
            "目标：%s；目标数量：%d；文件：%s；文件数：%d；字节数：%s"
            % (result["target"], len(targets), label, file_count, result["size"]),
        )
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
        self._notify(
            "传送已取消" if cancelled else "文件传送失败",
            message,
            "信息" if cancelled else "错误",
        )

    def start_local_probe(self):
        """查询本机 IP 与 Student 端监听端口。"""
        if self.thread is not None:
            self.logs.warning(
                "本机信息",
                "已有任务在运行，本机查询未开始",
                "当前任务：%s" % (self.active_kind or "无"),
            )
            return
        self.logs.info("本机信息", "开始查询本机 IP 与监听端口")
        self._begin_task(
            "local", TaskWorker(probe_local), self._probe_finished, self._local_failed
        )

    def start_firewall(self):
        """确认后修改 StudentMain.exe 的防火墙规则。"""
        if self.thread is not None:
            self.logs.warning(
                "防火墙",
                "已有任务在运行，防火墙操作未开始",
                "当前任务：%s" % (self.active_kind or "无"),
            )
            return
        action = self.pages["firewall"].action()
        action_name = "阻断连接" if action == "block" else "恢复允许"
        if not self._confirm(
            "确认防火墙操作", "在本机对 StudentMain.exe 规则执行“%s”？" % action_name
        ):
            self.logs.info("防火墙", "用户取消了防火墙操作", "操作：%s" % action_name)
            return
        self.logs.info("防火墙", "开始操作：%s" % action_name, "操作代码：%s" % action)
        self._begin_task(
            "firewall",
            TaskWorker(apply_firewall, action),
            self._firewall_finished,
            self._local_failed,
        )

    def _begin_task(self, kind, worker, finished, failed):
        """启动后台任务；已有任务在跑时改为排队，保证同一时间只跑一个。"""
        if self.thread is not None:
            self._task_queue.append((kind, worker, finished, failed))
            position = len(self._task_queue)
            self.pages[kind].footer.set_status(
                "已加入队列，前面还有 %d 个任务" % position
            )
            options = getattr(worker, "options", None)
            target = getattr(options, "target", None)
            details = "待执行任务数：%d" % position
            if target:
                details += "；目标：%s" % target
            self.logs.info(CATEGORIES[kind], "任务已加入队列", details)
            return
        self.active_kind = kind
        self.active_started_at = time.monotonic()
        self.thread = worker
        self.worker = worker
        options = getattr(worker, "options", None)
        cancel_event = getattr(options, "cancel_event", None)
        if cancel_event is None:
            cancel_event = getattr(worker, "kwargs", {}).get("cancel_event")
        self.active_cancel = cancel_event
        if kind == "file":
            self.pages["file"].reset_progress()
        # 线程内日志在此注入：线程对象由各页面创建，统一在启动时补上分类与存储。
        worker.logs = self.logs
        worker.category = CATEGORIES.get(kind, "应用")
        worker.setParent(self)
        worker.progress.connect(self._task_progress, Qt.QueuedConnection)
        worker.completed.connect(finished, Qt.QueuedConnection)
        worker.failed.connect(failed, Qt.QueuedConnection)
        worker.finished.connect(self._thread_finished, Qt.QueuedConnection)
        worker.finished.connect(worker.deleteLater)
        self._set_busy(True)
        worker.start()
        self.logs.debug(
            CATEGORIES[kind],
            "后台任务已启动",
            "线程类：%s；排队任务数：%d"
            % (type(worker).__name__, len(self._task_queue)),
        )

    def _set_busy(self, busy):
        """按忙碌状态统一开关各页面的按钮与输入控件。"""
        for page in self.network_pages:
            page.set_busy(busy, self.active_cancel is not None, queueable=True)
        self.pages["file"].set_busy(
            busy, self.active_cancel is not None, queueable=True
        )
        for key in ("local", "firewall"):
            self.pages[key].footer.set_busy(busy)
        self.pages["firewall"].action_box.setEnabled(not busy)
        self.pages["settings"].clear_data_button.setEnabled(not busy)
        self.pages["logs"].cancel_button.setEnabled(
            busy and self.active_cancel is not None
        )
        for key, page in self.pages.items():
            if key in CATEGORIES and key != self.active_kind:
                page.footer.set_status(
                    "其他任务正在执行，可继续加入队列" if busy else ""
                )
        if busy:
            self.pages[self.active_kind].footer.set_status("执行中，可继续加入队列")
        else:
            self.pages[self.active_kind].footer.finish_status()

    @Slot(str)
    def _task_progress(self, message):
        self.logs.debug(CATEGORIES[self.active_kind], message, "任务函数进度回调")
        self.pages[self.active_kind].footer.set_status(message)
        if self.active_kind == "file" and "文件传送服务已启动" in message:
            self.pages["file"].reset_progress()
        if self.active_kind == "file" and "下载文件：" in message:
            try:
                percent = int(message.rsplit("：", 1)[1].rstrip("%"))
            except ValueError:
                return
            self.pages["file"].set_progress(percent)

    @Slot(object)
    def _send_finished(self, outcome):
        failed = outcome.failed
        total = len(outcome.deliveries)
        if failed:
            message = "已发送 %d 个报文：成功 %d 台，失败 %d 台" % (
                outcome.sent,
                total - len(failed),
                len(failed),
            )
            details = "失败目标：%s" % "；".join(
                "%s（%s）" % (item.host, item.state.text) for item in failed
            )
        else:
            message = "已发送 %d 个报文：%d 台均未发现异常" % (outcome.sent, total)
            details = "成功率按网络反馈判定：没有收到 ICMP 不可达即视为送达。"
        self.pages[self.active_kind].footer.set_status(message)
        details = "%s；耗时：%.3f 秒" % (
            details,
            time.monotonic() - self.active_started_at,
        )
        if failed:
            self.logs.warning(CATEGORIES[self.active_kind], message, details)
        else:
            self.logs.info(CATEGORIES[self.active_kind], message, details)
        self._notify(
            "发送完成" if not failed else "部分目标失败",
            message,
            "成功" if not failed else "错误",
        )

    @Slot(str, str)
    def _send_failed(self, message, details=""):
        cancelled = message == "操作已取消"
        self.pages[self.active_kind].footer.set_status(message)
        details = "耗时：%.3f 秒；%s" % (
            time.monotonic() - self.active_started_at,
            details or "无异常堆栈",
        )
        if cancelled:
            self.logs.info(CATEGORIES[self.active_kind], message, details)
        else:
            self.logs.error(CATEGORIES[self.active_kind], message, details)
        self._notify(
            "发送已取消" if cancelled else "发送失败",
            message,
            "信息" if cancelled else "错误",
        )

    @Slot(object)
    def _probe_finished(self, result):
        ip, ports = result
        self.pages["local"].set_result(ip, ports)
        message = "查询完成，发现 %d 个监听端口" % len(ports)
        self.pages["local"].footer.set_status(message)
        self.logs.info(
            "本机信息",
            "本机 IP：%s；监听端口：%s" % (ip, ", ".join(ports) or "未发现"),
            "IP：%s；端口数：%d；耗时：%.3f 秒"
            % (ip, len(ports), time.monotonic() - self.active_started_at),
        )

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
        self.logs.error(
            CATEGORIES[self.active_kind],
            message,
            "耗时：%.3f 秒；%s"
            % (time.monotonic() - self.active_started_at, details or "无异常堆栈"),
        )
        self._notify("操作失败", message, "错误")

    def cancel_task(self):
        """清空排队任务，并给正在运行的任务置位取消信号。"""
        if self._task_queue:
            queued = len(self._task_queue)
            self._task_queue.clear()
            for key, page in self.pages.items():
                if key in CATEGORIES and key != self.active_kind:
                    page.footer.set_status("排队任务已取消")
            self.logs.warning(
                CATEGORIES.get(self.active_kind, "任务"),
                "已取消全部排队任务",
                "排队任务数：%d" % queued,
            )
        if self.active_cancel and not self.active_cancel.is_set():
            self.active_cancel.set()
            self.pages[self.active_kind].footer.set_status("正在取消")
            for page in self.task_pages:
                page.footer.cancel_button.setEnabled(False)
            self.pages["logs"].cancel_button.setEnabled(False)
            self.logs.warning(
                CATEGORIES[self.active_kind],
                "已请求取消",
                "任务：%s；耗时：%.3f 秒"
                % (
                    CATEGORIES[self.active_kind],
                    time.monotonic() - self.active_started_at,
                ),
            )

    @Slot()
    def _thread_finished(self):
        """线程结束后清理状态，必要时关闭窗口或启动下一个排队任务。"""
        finished_kind = self.active_kind
        self.thread = None
        self.worker = None
        self.active_cancel = None
        self.active_started_at = None
        if self.close_after_task:
            self._task_queue.clear()
            QTimer.singleShot(0, self.close)
        else:
            self._set_busy(False)
        self.active_kind = ""
        if finished_kind:
            self.logs.debug(
                CATEGORIES.get(finished_kind, "应用"),
                "后台线程已结束",
                "任务：%s；排队任务数：%d；关闭延后：%s"
                % (
                    finished_kind,
                    len(self._task_queue),
                    "是" if self.close_after_task else "否",
                ),
            )
        if self._task_queue and not self.close_after_task:
            QTimer.singleShot(0, self._start_next_task)

    def _start_next_task(self):
        """取出队首任务继续执行。"""
        if self.thread is not None or not self._task_queue:
            return
        kind, worker, finished, failed = self._task_queue.pop(0)
        self.logs.debug(
            CATEGORIES[kind],
            "开始执行排队任务",
            "剩余排队任务数：%d" % len(self._task_queue),
        )
        self._begin_task(kind, worker, finished, failed)

    def import_message(self):
        """从 UTF-8 文本文件导入消息正文。"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "导入消息", "", "文本文件 (*.txt *.md);;所有文件 (*)"
        )
        if not filename:
            self.logs.info("应用", "用户取消了消息导入")
            return
        try:
            with open(filename, encoding="utf-8-sig", newline="") as source:
                text = source.read()
            page = self.pages["message"]
            page.editor.setPlainText(text)
            page.filename.setText(
                page.filename.fontMetrics().elidedText(
                    Path(filename).name, Qt.ElideMiddle, 225
                )
            )
            page.filename.setToolTip(filename)
            self.logs.info(
                "应用", "消息文本已导入", "文件：%s；字符数：%d" % (filename, len(text))
            )
        except (OSError, UnicodeError) as error:
            self.logs.error(
                "应用", "导入消息失败", "文件：%s；异常：%s" % (filename, error)
            )
            self._notify("导入失败", str(error), "错误")

    def save_message(self):
        """把当前消息正文另存为 UTF-8 文本。"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存消息", "消息.txt", "文本文件 (*.txt)"
        )
        if filename:
            self._save_text(filename, self.pages["message"].editor.toPlainText())
        else:
            self.logs.info("应用", "用户取消了消息保存")

    @Slot(object)
    def export_selected_logs(self, entries):
        """把选中的日志记录导出为文本文件。"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "导出选中日志", "运行日志-选中.txt", "文本文件 (*.txt)"
        )
        if filename:
            self._save_text(filename, self.pages["logs"].export_text(entries))
        else:
            self.logs.info(
                "运行日志", "用户取消了日志导出", "待导出记录数：%d" % len(entries)
            )

    @Slot(object)
    def delete_selected_logs(self, uids):
        """确认后删除选中日志，并同步重写日志文件。"""
        if not uids:
            self.logs.warning("运行日志", "未勾选日志记录，无法删除")
            return
        if not self._confirm(
            "删除选中日志",
            "确定删除选中的 %d 条运行日志？此操作会同步更新日志文件。" % len(uids),
        ):
            self.logs.info(
                "运行日志", "用户取消了日志删除", "待删除记录数：%d" % len(uids)
            )
            return
        removed = self.logs.remove_entries(uids)
        self.logs.info("运行日志", "已删除选中日志", "删除记录数：%d" % len(removed))

    @Slot(str)
    def set_log_level(self, level):
        """切换运行日志等级，低于该等级的记录不再写入。"""
        previous = self.logs.minimum_level
        normalized = normalize_log_level(level)
        self.logs.set_level(normalized)
        self.logs.warning(
            "运行日志",
            "运行日志等级已调整",
            "原等级：%s；新等级：%s" % (previous, normalized),
        )

    def _save_text(self, filename, text):
        """写出 UTF-8（带 BOM）文本，失败时提示并记录日志。"""
        try:
            Path(filename).write_text(text, encoding="utf-8-sig")
        except OSError as error:
            self.logs.error(
                "应用", "保存文本失败", "文件：%s；异常：%s" % (filename, error)
            )
            self._notify("保存失败", str(error), "错误")
        else:
            self.logs.info(
                "应用", "文本已保存", "文件：%s；字符数：%d" % (filename, len(text))
            )
            self._notify("已保存", Path(filename).name, "成功")

    def copy_local_ip(self):
        """把本机 IP 复制到剪贴板。"""
        ip = self.pages["local"].ip_label.text()
        QApplication.clipboard().setText(ip)
        self.logs.info("本机信息", "本机 IP 已复制", "IP：%s" % ip)
        self._notify("已复制", "本机 IP 已复制到剪贴板", "成功")

    @Slot(object)
    def set_theme(self, theme):
        """切换界面主题；主题不写入配置文件，下次启动仍用浅色。

        Args:
            theme: ``Theme`` 枚举值，来自设置页的下拉框。
        """
        setTheme(theme, save=False)
        self.logs.info("应用", "界面主题已切换", "主题：%s" % theme)

    @Slot(bool)
    def set_mica_enabled(self, enabled):
        """保存背景模糊开关并立即生效，写盘失败时回滚到原状态。

        Args:
            enabled: 设置页开关的目标状态。
        """
        if not mica_available():
            self.logs.warning("设置", "当前系统不支持背景模糊，已忽略开关改动")
            self.pages["settings"].set_mica_enabled(False)
            return
        previous = self.mica_enabled
        self.mica_enabled = bool(enabled)
        self.apply_mica(self.mica_enabled)
        self.settings.set_value(MICA_SETTINGS_KEY, self.mica_enabled)
        self.settings.sync()
        if self.settings.status() != STATUS_NO_ERROR:
            self.logs.error(
                "设置",
                "背景模糊保存失败",
                "设置文件：%s；状态：%s"
                % (self.settings.file_name(), self.settings.status()),
            )
            self.mica_enabled = previous
            self.apply_mica(previous)
            self.pages["settings"].set_mica_enabled(previous)
            self._notify("设置保存失败", "无法写入设置文件", "错误")
            return
        self.logs.info(
            "设置",
            "背景模糊已更新",
            "开关状态：%s" % ("开启" if self.mica_enabled else "关闭"),
        )

    @Slot(str)
    def set_close_behavior(self, behavior):
        """保存关闭窗口行为，写盘失败时回滚到原行为。

        Args:
            behavior: 待保存的行为值，非法值会被拒绝并提示用户。
        """
        try:
            normalized = normalize_close_behavior(behavior)
        except ValueError as error:
            self.logs.error(
                "设置", "关闭窗口行为保存失败", "输入：%s；异常：%s" % (behavior, error)
            )
            self._notify("设置保存失败", str(error), "错误")
            return
        previous = self.close_behavior
        self.close_behavior = normalized
        self.settings.set_value(CLOSE_BEHAVIOR_SETTINGS_KEY, normalized)
        self.settings.sync()
        if self.settings.status() != STATUS_NO_ERROR:
            self.logs.error(
                "设置",
                "关闭窗口行为保存失败",
                "设置文件：%s；状态：%s"
                % (self.settings.file_name(), self.settings.status()),
            )
            self.close_behavior = previous
            self._notify("设置保存失败", "无法写入设置文件", "错误")
            return
        self.logs.info(
            "设置",
            "关闭窗口行为已更新",
            "原行为：%s；新行为：%s" % (previous, normalized),
        )

    def _tray_activated(self, reason):
        """单击或双击托盘图标时恢复主窗口。"""
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_from_tray()

    def show_from_tray(self):
        """从托盘恢复窗口并置顶激活。"""
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
        self.logs.info("系统托盘", "从系统托盘恢复主窗口")

    def quit_from_tray(self):
        """托盘菜单退出：有任务在跑时等任务结束再退出。"""
        self._first_close_dialog_open = False
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.quit_application()
        if self.isVisible():
            self.logs.info(
                "系统托盘",
                "退出请求将在当前任务结束后执行",
                "任务：%s" % (self.active_kind or "无"),
            )

    def _hide_to_tray(self):
        if self.tray_icon is None:
            return False
        self.tray_icon.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.hide()
        self.logs.info("系统托盘", "窗口已隐藏到系统托盘", "关闭行为：保留在系统托盘")
        return True

    def _ask_first_close_behavior(self):
        self._first_close_dialog_open = True
        dialog = Dialog(
            "关闭窗口",
            "是否在关闭窗口时最小化到系统托盘？\n"
            "最小化后后台任务继续运行，可从托盘恢复窗口。",
            self,
        )
        dialog.setFixedSize(520, 280)
        dialog.windowTitleLabel.hide()
        dialog.yesButton.setText("最小化到托盘")
        dialog.cancelButton.setText("直接退出")
        center_dialog(dialog)
        try:
            minimize_to_tray = bool(dialog.exec())
        finally:
            self._first_close_dialog_open = False
        self._save_first_close_prompt_shown()
        behavior = CLOSE_BEHAVIOR_TRAY if minimize_to_tray else CLOSE_BEHAVIOR_QUIT
        self.set_close_behavior(behavior)
        self.pages["settings"].set_close_behavior(behavior)
        self.logs.info("设置", "首次关闭窗口行为已选择", "行为：%s" % behavior)
        return behavior

    def quit_application(self):
        """请求退出应用，不触发关闭到托盘的首次询问。"""
        # 退出清理是一次性的：main() 在事件循环结束后还会再调用一次，
        # 此时重跑清理会重复移除托盘并重复写「应用退出」。
        if self._quit_finished:
            return
        self._quit_requested = True
        self.logs.debug(
            "应用",
            "收到退出请求",
            "任务：%s；排队任务数：%d；窗口可见：%s"
            % (
                self.active_kind or "无",
                len(self._task_queue),
                "是" if self.isVisible() else "否",
            ),
        )
        self.close()

    def _remove_tray(self, destroy=True):
        if self.tray_icon is not None:
            self.tray_icon.hide()
            if destroy:
                self.tray_icon.deleteLater()
            self.tray_icon = None
            self.logs.debug(
                "系统托盘",
                "托盘图标已移除",
                "销毁对象：%s" % ("是" if destroy else "否"),
            )
        if self.tray_menu is not None:
            if destroy:
                self.tray_menu.deleteLater()
            self.tray_menu = None

    @Slot()
    def clear_data(self):
        """确认后删除数据目录并恢复默认设置。

        有任务运行时直接拒绝，避免正在写入的日志与备注文件被删除一半；
        删除失败时还原托盘与日志路径，让本次运行继续可用。
        """
        if self.thread is not None:
            self.logs.warning(
                "关于",
                "有任务正在执行，清除本地数据被拒绝",
                "当前任务：%s" % (self.active_kind or "无"),
            )
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
                if (
                    resolved == Path(resolved.anchor)
                    or resolved == Path.cwd().resolve()
                ):
                    raise OSError("拒绝删除非数据目录路径：%s" % resolved)
                shutil.rmtree(resolved)
        except OSError as error:
            self.logs.log_path = log_path
            if self.enable_tray and QSystemTrayIcon.isSystemTrayAvailable():
                self._setup_tray()
            self.logs.error(
                "关于", "清除本地数据失败", "目录：%s；异常：%s" % (target, error)
            )
            self._notify("清除数据失败", str(error), "错误")
            return
        # 删除成功后本次运行不再写入旧日志文件，避免重新创建数据目录。
        self.logs.log_path = None
        self.alias_store.clear(persist=False)
        self.connection_state.reset()
        self.logs.clear(persist=False)
        self.settings = portable_settings(self.data_dir)
        self.close_behavior = DEFAULT_CLOSE_BEHAVIOR
        self.first_close_prompt_shown = False
        # 设置文件已删除，背景模糊与窗口位置一并回到默认状态。
        self.mica_enabled = DEFAULT_MICA_ENABLED
        self.apply_mica(self.mica_enabled)
        self.pages["settings"].set_mica_enabled(self.mica_enabled)
        self.resize(1180, 780)
        self._center_on_screen()
        self.pages["settings"].set_close_behavior(DEFAULT_CLOSE_BEHAVIOR)
        if self.enable_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self._setup_tray()
        self.logs.info(
            "关于",
            "本地数据已清除",
            "目录：%s；关闭行为已恢复默认托盘模式；本次运行文件日志暂停"
            % self.data_dir,
        )
        self._notify(
            "数据已清除", "已删除 JiYuAttackNextData 文件夹并恢复默认设置", "成功"
        )

    def _aliases_changed(self):
        """设备备注变化后记录数量，页面通过信号自行刷新。"""
        self.logs.info(
            "应用", "设备备注已更新", "当前备注数：%d" % len(self.alias_store.items())
        )

    def closeEvent(self, event):
        """按关闭行为决定隐藏到托盘还是退出；有任务时先取消再退出。"""
        # 隐藏到托盘的分支会提前 return，所以几何必须在函数开头就写盘。
        self._save_window_geometry()
        selected_behavior = None
        if (
            not self._quit_requested
            and self.tray_icon is not None
            and self.enable_tray
            and not self.first_close_prompt_shown
            and not self._first_close_dialog_open
        ):
            selected_behavior = self._ask_first_close_behavior()
            if selected_behavior == CLOSE_BEHAVIOR_QUIT:
                self._quit_requested = True

        effective_behavior = selected_behavior or self.close_behavior
        if not self._quit_requested and effective_behavior == CLOSE_BEHAVIOR_TRAY:
            event.ignore()
            self._hide_to_tray()
            return

        if self.thread is not None and self.thread.isRunning():
            self.close_after_task = True
            # 任务可能在设置开始时间之前就被关闭，取不到时按 0 秒记录。
            elapsed = (
                time.monotonic() - self.active_started_at
                if self.active_started_at is not None
                else 0.0
            )
            self.logs.warning(
                "应用",
                "任务运行中，已取消任务并延后退出",
                "任务：%s；已运行：%.3f 秒" % (self.active_kind or "无", elapsed),
            )
            self.cancel_task()
            event.ignore()
            return
        for page in self.task_pages:
            page.footer.ring.stop()
        self.logs.info("应用", "应用退出", "关闭行为：%s" % self.close_behavior)
        self._remove_tray()
        instance = getattr(self, "single_instance", None)
        if instance is not None:
            instance.close()
        super().closeEvent(event)
        if not event.isAccepted():
            return
        self._quit_finished = True
        # 窗口从托盘隐藏状态下关闭时 Qt 不认为“最后一个窗口已关闭”，
        # 事件循环会继续空转、进程留在后台，这里显式通知 main() 退出。
        self.quitRequested.emit()


def probe_local(report=None):
    """查询本机 IP 与 Student 监听端口，供后台线程调用。"""
    if report:
        report("正在读取本机 IP 与 Student 监听端口")
    return core.local_ip_and_ports()


def apply_firewall(action, report=None):
    """按需提权修改防火墙规则，供后台线程调用。"""
    if report:
        report("正在修改 StudentMain.exe 防火墙规则")
    return core.request_firewall_rule(action)


def confirm_usage_notice(parent=None):
    """弹出使用须知，返回用户是否同意继续启动。

    每次启动都会询问：本工具面向授权测试，不保存“已同意”状态，
    避免与设备备注、界面设置混在一起，也让后来的使用者看到声明。

    Args:
        parent: 对话框父窗口；启动阶段主窗口尚未创建，通常为 None。

    Returns:
        bool: 选择“同意并继续”返回 True，选择退出或关闭对话框返回 False。
    """
    dialog = Dialog(USAGE_NOTICE_TITLE, USAGE_NOTICE_TEXT, parent)
    dialog.setFixedSize(560, 300)
    dialog.windowTitleLabel.hide()
    dialog.yesButton.setText("同意并继续")
    dialog.cancelButton.setText("不同意，退出")
    center_dialog(dialog)
    return bool(dialog.exec())


def main():
    """启动图形界面，返回进程退出码。"""
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName("JiYuAttackNext")
    application = QApplication(sys.argv)
    configure_application(application)
    instance = SingleInstance(parent=application)
    if not instance.acquire():
        return 0
    # 单实例判定之后再询问：已被唤醒的第二次启动不该再弹一次声明。
    if not confirm_usage_notice():
        instance.close()
        return 0
    window = MainWindow()
    window.single_instance = instance
    # 单实例服务在主窗口之前创建，这里补上日志通道，唤醒记录才会进入运行日志。
    instance.logs = window.logs
    instance.activationRequested.connect(window.show_from_tray)
    # 关闭清理完成后再退出事件循环：从托盘退出时窗口是隐藏的，
    # 仅靠 Qt 的“最后一个窗口关闭”规则不足以让 exec() 返回。
    window.quitRequested.connect(application.quit)
    install_exception_logging(window.logs)
    window.show()
    window.logs.info(
        "应用",
        "主窗口已显示，进入事件循环",
        "单实例标识：%s；Python：%s" % (instance.key, sys.version.split()[0]),
    )
    result = application.exec()
    window.logs.info("应用", "事件循环已结束", "退出码：%s" % result)
    window.quit_application()
    if window.isVisible():
        window.hide()
    window.logs.close()
    window.deleteLater()
    # 延迟删除事件只在真实应用实例上派发：测试会用替身替换 QApplication，
    # 此前创建过的实例也可能已被销毁，此时静态调用会让 Qt 直接终止进程。
    if isinstance(application, REAL_APPLICATION):
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        application.processEvents()
    instance.close()
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
