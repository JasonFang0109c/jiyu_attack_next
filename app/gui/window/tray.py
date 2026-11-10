"""TrayService 的界面协调逻辑。"""

from PySide6.QtCore import (
    Qt,
)
from PySide6.QtWidgets import QSystemTrayIcon
from qfluentwidgets import (
    Action,
    SystemTrayMenu,
)

from app.features.settings.data import (
    CLOSE_BEHAVIOR_QUIT,
    CLOSE_BEHAVIOR_TRAY,
    FIRST_CLOSE_PROMPT_SETTINGS_KEY,
)
from app.gui.window.data import APP_NAME
from app.shared.settings import STATUS_NO_ERROR


class TrayService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window

    def _setup_tray(self):
        """创建系统托盘图标与菜单；托盘不可用时关闭窗口即退出。"""
        window = self.window
        if not window.enable_tray:
            window.logs.debug("系统托盘", "关闭行为为直接退出，未创建托盘图标")
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            window.logs.warning("系统托盘", "系统托盘不可用，关闭窗口将直接退出")
            return

        window.tray_icon = QSystemTrayIcon(window.windowIcon(), window)
        window.tray_icon.setToolTip(APP_NAME)
        window.tray_menu = SystemTrayMenu(parent=window)
        window.tray_menu.addActions(
            [
                Action("显示主窗口", triggered=window.show_from_tray),
                Action("退出", triggered=window.quit_from_tray),
            ]
        )
        window.tray_icon.setContextMenu(window.tray_menu)
        window.tray_icon.activated.connect(window._tray_activated)
        window.tray_icon.show()
        window.logs.info(
            "系统托盘",
            "系统托盘图标已创建",
            "提示文本：%s；菜单项数：2" % APP_NAME,
        )

    def _tray_activated(self, reason):
        """单击或双击托盘图标时恢复主窗口。"""
        window = self.window
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            window.show_from_tray()

    def show_from_tray(self):
        """从托盘恢复窗口并置顶激活。"""
        window = self.window
        window.show()
        window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
        window.raise_()
        window.activateWindow()
        window.logs.info("系统托盘", "从系统托盘恢复主窗口")
        if window.current_page() == "studentproc":
            window.refresh_student_processes()
            window._studentproc_timer.start()

    def quit_from_tray(self):
        """托盘菜单退出：有任务在跑时等任务结束再退出。"""
        window = self.window
        window._first_close_dialog_open = False
        if window.tray_icon is not None:
            window.tray_icon.hide()
        window.quit_application()
        if window.isVisible():
            window.logs.info(
                "系统托盘",
                "退出请求将在当前任务结束后执行",
                "任务：%s" % (window.active_kind or "无"),
            )

    def _hide_to_tray(self):
        window = self.window
        if window.tray_icon is None:
            return False
        window.tray_icon.show()
        window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
        window.hide()
        # 窗口不可见时页面轮询没有意义，还白白起子进程。
        window._studentproc_timer.stop()
        window.logs.info("系统托盘", "窗口已隐藏到系统托盘", "关闭行为：保留在系统托盘")
        return True

    def _ask_first_close_behavior(self):
        window = self.window
        window._first_close_dialog_open = True
        dialog = window._dialog(
            "关闭窗口",
            "是否在关闭窗口时最小化到系统托盘？\n"
            "最小化后后台任务继续运行，可从托盘恢复窗口。",
            "最小化到托盘",
        )
        dialog.windowTitleLabel.hide()
        dialog.cancelButton.setText("直接退出")
        try:
            minimize_to_tray = bool(dialog.exec())
        finally:
            window._first_close_dialog_open = False
        window._save_first_close_prompt_shown()
        behavior = CLOSE_BEHAVIOR_TRAY if minimize_to_tray else CLOSE_BEHAVIOR_QUIT
        window.set_close_behavior(behavior)
        window.pages["settings"].set_close_behavior(behavior)
        window.logs.info("设置", "首次关闭窗口行为已选择", "行为：%s" % behavior)
        return behavior

    def quit_application(self):
        """请求退出应用，不触发关闭到托盘的首次询问。"""
        window = self.window
        # 退出清理是一次性的：main() 在事件循环结束后还会再调用一次，
        # 此时重跑清理会重复移除托盘并重复写「应用退出」。
        if window._quit_finished:
            return
        window._quit_requested = True
        window.logs.debug(
            "应用",
            "收到退出请求",
            "任务：%s；排队任务数：%d；窗口可见：%s"
            % (
                window.active_kind or "无",
                len(window._task_queue),
                "是" if window.isVisible() else "否",
            ),
        )
        window.close()

    def _remove_tray(self, destroy=True):
        window = self.window
        if window.tray_icon is not None:
            window.tray_icon.hide()
            if destroy:
                window.tray_icon.deleteLater()
            window.tray_icon = None
            window.logs.debug(
                "系统托盘",
                "托盘图标已移除",
                "销毁对象：%s" % ("是" if destroy else "否"),
            )
        if window.tray_menu is not None:
            if destroy:
                window.tray_menu.deleteLater()
            window.tray_menu = None

    def _save_first_close_prompt_shown(self):
        window = self.window
        window.first_close_prompt_shown = True
        window.settings.set_value(FIRST_CLOSE_PROMPT_SETTINGS_KEY, True)
        window.settings.sync()
        if window.settings.status() != STATUS_NO_ERROR:
            window.logs.warning(
                "设置",
                "首次关闭提示状态保存失败",
                "设置文件：%s；状态：%s"
                % (window.settings.file_name(), window.settings.status()),
            )
