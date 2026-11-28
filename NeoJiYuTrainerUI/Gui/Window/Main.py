"""主窗口组合根：页面接线、Qt 事件与跨功能退出协调。"""

import contextlib
import os
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QSystemTrayIcon
from qfluentwidgets import (
    FluentWindow,
)

from NeoJiYuTrainer.Features.Settings.Data import (
    CLOSE_BEHAVIOR_QUIT,
    CLOSE_BEHAVIOR_TRAY,
    DEFAULT_CLOSE_BEHAVIOR,
    DEFAULT_HOTKEY_FAKE_FULL,
    DEFAULT_HOTKEY_SHOW_HIDE,
    DEFAULT_WINDOW_MATERIAL,
    HOTKEY_FAKE_FULL_SETTINGS_KEY,
    HOTKEY_SHOW_HIDE_SETTINGS_KEY,
    MATERIAL_SOLID,
)
from NeoJiYuTrainer.Features.Settings.Service import portable_settings
from NeoJiYuTrainer.Features.Uninstall.Service import install_root, run_uninstall
from NeoJiYuTrainer.Shared.Paths import portable_data_dir, portable_log_path
from NeoJiYuTrainer.System.Windows.Driver import DriverSession
from NeoJiYuTrainerUI.Features.About.Gui.Page import AboutPage
from NeoJiYuTrainerUI.Features.Classroom.Gui.Page import ClassroomPage
from NeoJiYuTrainerUI.Features.Classroom.Gui.Service import ClassroomService
from NeoJiYuTrainerUI.Features.Command.Gui.Page import CommandPage
from NeoJiYuTrainerUI.Features.Device.Gui.Page import DevicePage
from NeoJiYuTrainerUI.Features.Files.Gui.Page import FilePage
from NeoJiYuTrainerUI.Features.Files.Gui.Service import FileService
from NeoJiYuTrainerUI.Features.Firewall.Gui.Page import FirewallPage
from NeoJiYuTrainerUI.Features.Firewall.Gui.Service import FirewallService
from NeoJiYuTrainerUI.Features.Home.Gui.Page import HomePage
from NeoJiYuTrainerUI.Features.Local.Gui.Page import LocalPage
from NeoJiYuTrainerUI.Features.Local.Gui.Service import LocalService
from NeoJiYuTrainerUI.Features.Logs.Gui.Data import LogStore
from NeoJiYuTrainerUI.Features.Logs.Gui.Page import LogPage
from NeoJiYuTrainerUI.Features.Logs.Gui.Service import LogService
from NeoJiYuTrainerUI.Features.Message.Gui.Page import MessagePage
from NeoJiYuTrainerUI.Features.Message.Gui.Service import MessageService
from NeoJiYuTrainerUI.Features.Names.Gui.Data import DeviceAliasStore
from NeoJiYuTrainerUI.Features.Names.Gui.Page import AliasPage
from NeoJiYuTrainerUI.Features.Settings.Gui.Page import SettingsPage
from NeoJiYuTrainerUI.Features.Shell.Gui.Page import ShellPage
from NeoJiYuTrainerUI.Features.Student.Gui.Page import StudentProcessPage
from NeoJiYuTrainerUI.Features.Student.Gui.Service import StudentService
from NeoJiYuTrainerUI.Gui.Data import ConnectionState
from NeoJiYuTrainerUI.Gui.Hotkey import HotkeyManager
from NeoJiYuTrainerUI.Gui.Menu.Service import NavigationService
from NeoJiYuTrainerUI.Gui.Resources import app_icon
from NeoJiYuTrainerUI.Gui.Service import GuiService
from NeoJiYuTrainerUI.Gui.Theme import (
    WINDOW_BACKGROUND_DARK,
    WINDOW_BACKGROUND_LIGHT,
    window_background,
)
from NeoJiYuTrainerUI.Gui.Widgets.Page import TabbedPage
from NeoJiYuTrainerUI.Gui.Window.Data import (
    APP_NAME,
    CAPTION_BUTTON_MARGIN,
    STUDENT_POLL_INTERVAL,
    TAB_GROUPS,
)
from NeoJiYuTrainerUI.Gui.Window.Service import WindowService
from NeoJiYuTrainerUI.Gui.Window.Tray import TrayService
from NeoJiYuTrainerUI.Gui.Workers.Service import TaskService


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
        self._task_service = TaskService(self)
        self._student_service = StudentService(self)
        self._tray_service = TrayService(self)
        self._window_service = WindowService(self)
        self._navigation_service = NavigationService(self)
        self._file_service = FileService(self)
        self._message_service = MessageService(self)
        self._local_service = LocalService(self)
        self._firewall_service = FirewallService(self)
        self._log_service = LogService(self)
        self._gui_service = GuiService(self)
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
        self._navigation_closed = False
        self._navigation_refresh_timer = QTimer(self)
        self._navigation_refresh_timer.setSingleShot(True)
        self._navigation_refresh_timer.timeout.connect(self._refresh_navigation)
        self._task_dispatch_timer = QTimer(self)
        self._task_dispatch_timer.setSingleShot(True)
        self._task_dispatch_timer.timeout.connect(self._dispatch_after_task)
        # 学生端可能被课堂软件自己拉起或结束，页面可见时按节奏轮询状态。
        self._studentproc_timer = QTimer(self)
        self._studentproc_timer.setInterval(STUDENT_POLL_INTERVAL)
        self._studentproc_timer.timeout.connect(self._poll_student_processes)
        # 进程枚举会拉起子进程，只在后台线程里跑，界面线程只取结果。
        self._student_probe_thread = None
        self._student_probe_queued = None
        self._first_close_dialog_open = False
        self.tray_icon = None
        self.tray_menu = None
        self.connection_state = ConnectionState(alias_store, parent=self)
        self.alias_store = self.connection_state.aliases
        self.alias_store.changed.connect(self._aliases_changed)
        self.logs = LogStore(self, log_path=portable_log_path(self.data_dir))
        self._configure_file_logging()
        self.setWindowTitle(APP_NAME)
        # 组件库把三个窗口按钮顶对齐在 48 像素标题栏里，补上等分留白才居中。
        self.titleBar.buttonLayout.setContentsMargins(
            0, CAPTION_BUTTON_MARGIN, 0, CAPTION_BUTTON_MARGIN
        )
        self.setWindowIcon(app_icon())
        self._setup_tray()
        self.blur_enabled = False
        self.window_material = self._load_window_material()
        self.apply_window_material(self.window_material)
        self.theme_accent = self._load_theme_accent()
        self.system_accent_color = QColor()
        self.setCustomBackgroundColor(WINDOW_BACKGROUND_LIGHT, WINDOW_BACKGROUND_DARK)
        self.setMinimumSize(960, 640)
        self.resize(1180, 1000)
        self._restore_window_geometry()
        self.stackedWidget.setAnimationEnabled(False)
        self._classroom_service = ClassroomService(self)
        self.show_hide_hotkey = self._load_hotkey(
            HOTKEY_SHOW_HIDE_SETTINGS_KEY, DEFAULT_HOTKEY_SHOW_HIDE
        )
        self.fake_full_hotkey = self._load_hotkey(
            HOTKEY_FAKE_FULL_SETTINGS_KEY, DEFAULT_HOTKEY_FAKE_FULL
        )
        self._hotkeys = HotkeyManager(self)
        self._driver_session = None
        self.pages = {
            "home": HomePage(self),
            "message": MessagePage(self.connection_state, self),
            "shell": ShellPage(self.connection_state, self.logs, self),
            "command": CommandPage(self.connection_state, self),
            "device": DevicePage(self.connection_state, self),
            "file": FilePage(self.connection_state, self),
            "aliases": AliasPage(self.connection_state, self, logs=self.logs),
            "local": LocalPage(self),
            "firewall": FirewallPage(self),
            "classroom": ClassroomPage(self),
            "studentproc": StudentProcessPage(self),
            "logs": LogPage(self.logs, self),
            "settings": SettingsPage(
                self.logs,
                self.close_behavior,
                self.window_material,
                self.theme_accent,
                self.show_hide_hotkey,
                self.fake_full_hotkey,
                self,
            ),
            "about": AboutPage(self),
        }
        # 组内页面收进导航容器，侧边栏只保留一级入口。
        for host_key, _icon, title, children in TAB_GROUPS:
            host = TabbedPage(host_key, title, self)
            for child_key, child_icon, child_title in children:
                host.add_tab(self.pages[child_key], child_title, child_icon)
            self.pages[host_key] = host
        self._classroom_service.attach(self.pages["classroom"])
        # 网络页都带目标输入区与底栏，忙碌状态由主窗口统一开关。
        self.network_pages = [
            self.pages[key] for key in ("message", "command", "device")
        ]
        self.task_pages = [
            *self.network_pages,
            self.pages["file"],
            self.pages["local"],
            self.pages["firewall"],
        ]
        self._build_navigation()
        self._connect_actions()
        self._register_hotkeys()
        self.apply_theme_accent(self.theme_accent)
        self._tune_scroll_bars()
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
        return self._window_service._load_close_behavior()

    def _load_hotkey(self, key, default):
        """读取热键配置，空串表示用户主动禁用。"""
        value = self.settings.value(key, default)
        return str(value) if value is not None else default

    def _register_hotkeys(self):
        """重新注册两个全局热键；失败只记日志，不阻塞启动。"""
        self._hotkeys.unregister_all()
        self._hotkeys.install()
        failed = []
        if self.show_hide_hotkey and not self._hotkeys.register(
            self.show_hide_hotkey, self._toggle_window_visibility
        ):
            failed.append(self.show_hide_hotkey)
        if self.fake_full_hotkey and not self._hotkeys.register(
            self.fake_full_hotkey, self._toggle_fake_full
        ):
            failed.append(self.fake_full_hotkey)
        if failed:
            self.logs.warning("热键", "注册失败：" + "、".join(failed))

    def _toggle_window_visibility(self):
        """全局热键：显示或隐藏主窗口。"""
        if self.isVisible() and not self.isMinimized():
            self._hide_to_tray()
        else:
            self.show_from_tray()

    def _toggle_fake_full(self):
        """全局热键：切换课堂假全屏。"""
        self._classroom_service.set_fake_full(not self._classroom_service._fake_full)

    def _set_hotkey(self, kind, text):
        """保存并立即应用热键设置。"""
        text = str(text or "").strip()
        if kind == "show_hide":
            self.show_hide_hotkey = text
            self.settings.set_value(HOTKEY_SHOW_HIDE_SETTINGS_KEY, text)
        elif kind == "fake_full":
            self.fake_full_hotkey = text
            self.settings.set_value(HOTKEY_FAKE_FULL_SETTINGS_KEY, text)
        else:
            return
        self.settings.sync()
        self._register_hotkeys()
        self.pages["settings"].set_hotkeys(self.show_hide_hotkey, self.fake_full_hotkey)

    def _driver_action(self, action, pid=0):
        """处理设置页的内核驱动操作。"""
        try:
            if action == "start":
                if not os.path.exists(str(self._driver_path())):
                    raise OSError("驱动文件不存在，请先构建原生组件")
                self._driver_session = DriverSession()
                self._driver_session.install()
                self._driver_session.open()
                self._driver_session.protect(os.getpid())
                status = self._driver_session.status()
                self.pages["settings"].set_driver_status(
                    "已启用，保护 %d 个进程，回调=%s"
                    % (status.protected_count, status.callback_active),
                    True,
                )
            elif action == "stop":
                if self._driver_session is not None:
                    with contextlib.suppress(OSError):
                        self._driver_session.unprotect(os.getpid())
                    self._driver_session.close()
                    self._driver_session.uninstall()
                    self._driver_session = None
                self.pages["settings"].set_driver_status(
                    "已停止并卸载驱动服务。", False
                )
            elif action == "kill" and pid > 0:
                if self._driver_session is None:
                    self._driver_session = DriverSession()
                    self._driver_session.open()
                self._driver_session.kill(int(pid))
                self.logs.info("驱动", "已强杀进程", "PID：%d" % int(pid))
        except (OSError, ValueError) as error:
            self.logs.error("驱动", "操作失败", str(error))
            self._notify("驱动操作失败", str(error))

    def _driver_path(self):
        from NeoJiYuTrainer.System.Windows.Driver import default_driver_path

        return default_driver_path()

    def _uninstall_application(self, keep_user_data):
        """确认后执行卸载并退出。"""
        if install_root() is None:
            self._notify("卸载", "源码运行时没有安装目录，已跳过卸载。")
            return
        message = "将删除快捷方式和应用文件"
        if keep_user_data:
            message += "，保留 data"
        else:
            message += "，并删除 data"
        message += "。是否继续？"
        if not self._confirm("卸载应用", message, "卸载"):
            return
        result = run_uninstall(keep_user_data=bool(keep_user_data), remove_driver=True)
        self.logs.info("应用", "已执行卸载", str(result))
        self._notify("卸载", "卸载操作已完成，应用即将退出。")
        QTimer.singleShot(800, self.close)

    def _load_first_close_prompt_shown(self):
        return self._window_service._load_first_close_prompt_shown()

    def _load_window_material(self):
        return self._window_service._load_window_material()

    def _normalBackgroundColor(self):
        """返回窗口常态底色，材质开启时必须是全透明。

        库的 ``_normalBackgroundColor`` 只在它自己的云母开关打开时返回透明，
        而这里改走 ``windowEffect`` 直接施加材质，开关始终是关的。若沿用库的
        实现，窗口获得焦点、鼠标移入移出都会把底色动画回不透明色，材质随之
        被完全盖住，表现就是“设置了却没生效、切换后也不生效”。
        """
        if getattr(self, "window_material", None) in (None, MATERIAL_SOLID):
            return window_background()
        return QColor(0, 0, 0, 0)

    def apply_window_material(self, material):
        return self._window_service.apply_window_material(material)

    def _load_theme_accent(self):
        return self._window_service._load_theme_accent()

    def apply_theme_accent(self, accent):
        return self._window_service.apply_theme_accent(accent)

    def set_theme_accent(self, accent):
        return self._window_service.set_theme_accent(accent)

    def refresh_system_accent(self):
        return self._window_service.refresh_system_accent()

    def _refresh_background_effect(self):
        """重新应用材质，系统在窗口显示与主题切换时会把背景重置回云母。"""
        if self.window_material == MATERIAL_SOLID:
            return
        self.apply_window_material(self.window_material)

    def showEvent(self, event):
        """窗口显示后再应用一次模糊，覆盖库在 showEvent 里设下的云母。"""
        super().showEvent(event)
        self._refresh_background_effect()
        # 滚动区要等窗口真正显示才有尺寸，等这一轮事件走完再滚到当前页面。
        self._navigation_refresh_timer.start()

    def changeEvent(self, event):
        """窗口重新获得焦点时跟随系统强调色的变化。"""
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.refresh_system_accent()

    def _refresh_navigation(self):
        """把当前页面所在的可见导航项滚进视口。"""
        if getattr(self, "_navigation_closed", False):
            return
        current = self.stackedWidget.currentWidget()
        if current is not None:
            self._reveal_navigation_item(current.objectName())

    def _onThemeChangedFinished(self):
        """主题切换后重新应用模糊，深浅色决定染色与标题栏明暗。"""
        super()._onThemeChangedFinished()
        self._refresh_background_effect()

    def _restore_window_geometry(self):
        return self._window_service._restore_window_geometry()

    def _clamp_to_screen(self):
        return self._window_service._clamp_to_screen()

    def _center_on_screen(self):
        return self._window_service._center_on_screen()

    def _save_window_geometry(self):
        return self._window_service._save_window_geometry()

    def _save_first_close_prompt_shown(self):
        return self._tray_service._save_first_close_prompt_shown()

    def _setup_tray(self):
        return self._tray_service._setup_tray()

    def _configure_file_logging(self):
        return self._log_service._configure_file_logging()

    def _build_navigation(self):
        return self._navigation_service._build_navigation()

    def _tune_scroll_bars(self):
        return self._navigation_service._tune_scroll_bars()

    def expand_navigation(self):
        return self._navigation_service.expand_navigation()

    def _save_navigation_expanded(self, expanded):
        return self._navigation_service._save_navigation_expanded(expanded)

    def _update_return_button(self, _index=0):
        return self._navigation_service._update_return_button(_index)

    def _on_current_page_changed(self, _index=0):
        return self._navigation_service._on_current_page_changed(_index)

    def _sync_page_polling(self):
        return self._navigation_service._sync_page_polling()

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
        self.pages["studentproc"].toggleRequested.connect(self.toggle_local_student)
        self.pages["studentproc"].copyPortRequested.connect(self.copy_student_port)
        self.pages["studentproc"].rowPathRequested.connect(self.copy_student_row_path)
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
        self.pages["settings"].themeColorRequested.connect(self.set_theme_accent)
        self.pages["settings"].materialRequested.connect(self.set_window_material)
        self.pages["settings"].closeBehaviorRequested.connect(self.set_close_behavior)
        self.pages["settings"].logLevelRequested.connect(self.set_log_level)
        self.pages["settings"].clearDataRequested.connect(self.clear_data)
        self.pages["settings"].hotkeyRequested.connect(self._set_hotkey)
        self.pages["settings"].driverRequested.connect(self._driver_action)
        self.pages["settings"].uninstallRequested.connect(self._uninstall_application)
        self.pages["home"].pageRequested.connect(self._open_home_link)

    def _open_home_link(self, target):
        return self._navigation_service._open_home_link(target)

    def show_page(self, key):
        return self._navigation_service.show_page(key)

    def _navigation_item(self, key):
        return self._navigation_service._navigation_item(key)

    def _reveal_navigation_item(self, key):
        return self._navigation_service._reveal_navigation_item(key)

    def current_page(self):
        return self._navigation_service.current_page()

    def _notify(self, title, message, level="信息"):
        return self._gui_service._notify(title, message, level)

    def _dialog(self, title, content, confirm_text=None):
        return self._gui_service._dialog(title, content, confirm_text)

    def _confirm(self, title, content, confirm_text="确认执行"):
        return self._gui_service._confirm(title, content, confirm_text)

    def _options_for_page(self, kind):
        return self._gui_service._options_for_page(kind)

    def start_send(self, kind):
        return self._gui_service.start_send(kind)

    def _validation_error(self, kind, message, details=""):
        return self._gui_service._validation_error(kind, message, details)

    def choose_transfer_files(self):
        return self._file_service.choose_transfer_files()

    def choose_transfer_folder(self):
        return self._file_service.choose_transfer_folder()

    def _add_transfer_paths(self, paths):
        return self._file_service._add_transfer_paths(paths)

    def delete_transfer_files(self):
        return self._file_service.delete_transfer_files()

    def start_file_transfer(self):
        return self._file_service.start_file_transfer()

    @Slot(object)
    def _file_finished(self, result):
        return self._file_service._file_finished(result)

    def _report_failure(self, category, message, details, titles):
        return self._gui_service._report_failure(category, message, details, titles)

    @Slot(str, str)
    def _file_failed(self, message, details=""):
        return self._file_service._file_failed(message, details)

    def _claim_task(self, category, action):
        return self._task_service._claim_task(category, action)

    def start_local_probe(self):
        return self._local_service.start_local_probe()

    def start_firewall(self):
        return self._firewall_service.start_firewall()

    def refresh_student_processes(self):
        return self._student_service.refresh_student_processes()

    @Slot()
    def _poll_student_processes(self):
        return self._student_service._poll_student_processes()

    def _probe_student_processes(self, purpose):
        return self._student_service._probe_student_processes(purpose)

    @Slot()
    def _student_probe_finished(self):
        return self._student_service._student_probe_finished()

    def _student_processes_ready(self, purpose, processes):
        return self._student_service._student_processes_ready(purpose, processes)

    def _student_processes_failed(self, purpose, message, details):
        return self._student_service._student_processes_failed(
            purpose, message, details
        )

    def toggle_local_student(self):
        return self._student_service.toggle_local_student()

    def start_local_student(self):
        return self._student_service.start_local_student()

    @Slot(object)
    def _start_student_finished(self, results):
        return self._student_service._start_student_finished(results)

    def stop_local_student(self):
        return self._student_service.stop_local_student()

    def _stop_student_finished(self, results):
        return self._student_service._stop_student_finished(results)

    def copy_student_port(self):
        return self._student_service.copy_student_port()

    @Slot(str)
    def copy_student_row_path(self, path):
        return self._student_service.copy_row_path(path)

    def _begin_task(self, kind, worker, finished, failed):
        return self._task_service._begin_task(kind, worker, finished, failed)

    def _set_busy(self, busy):
        return self._task_service._set_busy(busy)

    @Slot(str)
    def _task_progress(self, message):
        return self._task_service._task_progress(message)

    @Slot(object)
    def _send_finished(self, outcome):
        return self._gui_service._send_finished(outcome)

    @Slot(str, str)
    def _send_failed(self, message, details=""):
        return self._gui_service._send_failed(message, details)

    @Slot(object)
    def _probe_finished(self, result):
        return self._local_service._probe_finished(result)

    @Slot(object)
    def _firewall_finished(self, results):
        return self._firewall_service._firewall_finished(results)

    @Slot(str, str)
    def _local_failed(self, message, details=""):
        return self._gui_service._local_failed(message, details)

    def cancel_task(self):
        return self._task_service.cancel_task()

    @Slot()
    def _thread_finished(self):
        return self._task_service._thread_finished()

    def _dispatch_after_task(self):
        return self._task_service._dispatch_after_task()

    def _start_next_task(self):
        return self._task_service._start_next_task()

    def import_message(self):
        return self._message_service.import_message()

    def save_message(self):
        return self._message_service.save_message()

    @Slot(object)
    def export_selected_logs(self, entries):
        return self._log_service.export_selected_logs(entries)

    @Slot(object)
    def delete_selected_logs(self, uids):
        return self._log_service.delete_selected_logs(uids)

    @Slot(str)
    def set_log_level(self, level):
        return self._log_service.set_log_level(level)

    def _save_text(self, filename, text):
        return self._gui_service._save_text(filename, text)

    def copy_local_ip(self):
        return self._local_service.copy_local_ip()

    @Slot(object)
    def set_theme(self, theme):
        return self._window_service.set_theme(theme)

    @Slot(str)
    def set_window_material(self, material):
        return self._window_service.set_window_material(material)

    @Slot(str)
    def set_close_behavior(self, behavior):
        return self._window_service.set_close_behavior(behavior)

    def _tray_activated(self, reason):
        return self._tray_service._tray_activated(reason)

    def show_from_tray(self):
        return self._tray_service.show_from_tray()

    def quit_from_tray(self):
        return self._tray_service.quit_from_tray()

    def _hide_to_tray(self):
        return self._tray_service._hide_to_tray()

    def _ask_first_close_behavior(self):
        return self._tray_service._ask_first_close_behavior()

    def quit_application(self):
        return self._tray_service.quit_application()

    def _remove_tray(self, destroy=True):
        return self._tray_service._remove_tray(destroy)

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
            "将删除 data 文件夹中的设备备注、界面设置和运行日志。\n此操作无法撤销。",
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
        # 设置文件已删除，窗口材质与窗口位置一并回到默认状态。
        self.window_material = DEFAULT_WINDOW_MATERIAL
        self.apply_window_material(self.window_material)
        self.pages["settings"].set_window_material(self.window_material)
        self.resize(1180, 1000)
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
        self._notify("数据已清除", "已删除 data 文件夹并恢复默认设置", "成功")

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
        if (
            not self._quit_requested
            and effective_behavior == CLOSE_BEHAVIOR_TRAY
            and self._hide_to_tray()
        ):
            event.ignore()
            return

        self._quit_requested = True
        self.close_after_task = True
        self._studentproc_timer.stop()
        self._student_probe_queued = None
        self._hotkeys.shutdown()
        if self._driver_session is not None:
            with contextlib.suppress(OSError):
                self._driver_session.unprotect(os.getpid())
            self._driver_session.close()
            self._driver_session = None
        # 课堂助手自带查询/自动看护线程；退出流程可能因任务线程提前 return，
        # 必须在这里先停掉，避免窗口销毁时仍有 QThread 在运行。
        self._classroom_service.stop()
        if self.thread is not None and self.thread.isRunning():
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
        # 查询线程也会回调页面；等 finished 被处理后再释放窗口与日志。
        if self._student_probe_thread is not None:
            event.ignore()
            return
        self.pages["shell"].stop_listen()
        for page in self.task_pages:
            page.footer.ring.stop()
        self.logs.info("应用", "应用退出", "关闭行为：%s" % self.close_behavior)
        self._remove_tray()
        instance = getattr(self, "single_instance", None)
        if instance is not None:
            instance.close()
        self._navigation_closed = True
        self._navigation_refresh_timer.stop()
        self._task_dispatch_timer.stop()
        self._studentproc_timer.stop()
        super().closeEvent(event)
        if not event.isAccepted():
            return
        self._quit_finished = True
        # 窗口从托盘隐藏状态下关闭时 Qt 不认为“最后一个窗口已关闭”，
        # 事件循环会继续空转、进程留在后台，这里显式通知 main() 退出。
        self.quitRequested.emit()
