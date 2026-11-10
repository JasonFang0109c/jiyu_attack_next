"""GUI 应用初始化、单实例、启动确认与事件循环。"""

import getpass
import hashlib
import sys
import traceback

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QLocale,
    QObject,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    FluentTranslator,
    Theme,
    setFontFamilies,
    setTheme,
    setThemeColor,
)

from app.gui.resources import app_icon
from app.gui.splash import create_splash
from app.gui.widgets.common import FluentDialog, center_dialog
from app.gui.window.data import (
    APP_NAME,
)
from app.gui.window.main import MainWindow

SINGLE_INSTANCE_KEY = "JiYuAttackNext-single-instance"

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
        self.existing = False
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
            self.existing = True
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
        """通知已有实例显示窗口。

        套接字用完立刻销毁：它是短连接，跟着 ``SingleInstance`` 活到进程结束
        会在退出阶段留下未处理的网络事件，偶发崩在事件循环里。
        """
        socket = QLocalSocket()
        try:
            socket.connectToServer(self.key)
            if not socket.waitForConnected(500):
                return False
            socket.write(b"show")
            socket.flush()
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
            socket.waitForDisconnected(500)
            return True
        finally:
            socket.deleteLater()

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
        """关闭本地服务端并移除同名服务，避免下次启动被残留占用。

        已接受的连接由服务端持有，关闭前先断开，防止服务端销毁后仍有
        连接信号指向已释放的对象。
        """
        if self.server is not None:
            for connection in self.server.findChildren(QLocalSocket):
                connection.close()
            self.server.close()
            QLocalServer.removeServer(self.key)
            self.server.deleteLater()
            self.server = None
            self._log("debug", "单实例服务已关闭", "单实例标识：%s" % self.key)
        self.primary = False


LATIN_FONT_CANDIDATES = ("Segoe UI Variable Text", "Segoe UI")

CHINESE_FONT = "Microsoft YaHei UI"

CJK_FONT_CANDIDATES = ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC")


def font_families():
    """按系统已装字体给出界面字体栈，缺失的候选会被跳过。"""
    installed = set(QFontDatabase.families())
    families = [name for name in LATIN_FONT_CANDIDATES if name in installed]
    families.extend(name for name in CJK_FONT_CANDIDATES if name in installed)
    return families or [CHINESE_FONT]


def configure_application(application):
    """设置全局字体、中文区域与默认主题色。"""
    families = font_families()
    # 组件库的控件字号由 getFont 统一给出，字体栈必须同步设进去，
    # 否则只有没显式设字体的控件会用上面的 QApplication 字体。
    setFontFamilies(families)
    default_font = QFont()
    default_font.setFamilies(families)
    default_font.setPointSize(10)
    application.setFont(default_font)
    # 应用级图标会让使用须知等在主窗口之前出现的对话框也用同一个任务栏图标。
    application.setWindowIcon(app_icon())
    locale = QLocale(QLocale.Chinese, QLocale.China)
    QLocale.setDefault(locale)
    application.fluent_translator = FluentTranslator(locale)
    application.installTranslator(application.fluent_translator)
    setTheme(Theme.LIGHT, save=False)
    setThemeColor(QColor("#0067c0"), save=False)


def confirm_usage_notice(parent=None):
    """弹出使用须知，返回用户是否同意继续启动。

    每次启动都会询问：本工具面向授权测试，不保存“已同意”状态，
    避免与设备备注、界面设置混在一起，也让后来的使用者看到声明。

    Args:
        parent: 对话框父窗口；启动阶段主窗口尚未创建，通常为 None。

    Returns:
        bool: 选择“同意并继续”返回 True，选择退出或关闭对话框返回 False。
    """
    dialog = FluentDialog(USAGE_NOTICE_TITLE, USAGE_NOTICE_TEXT, parent)
    dialog.setFixedSize(560, 300)
    dialog.windowTitleLabel.hide()
    dialog.yesButton.setText("同意并继续")
    dialog.cancelButton.setText("不同意，退出")
    center_dialog(dialog)
    return bool(dialog.exec())


def main():
    """启动图形界面，返回进程退出码。

    Returns:
        int: 进程退出码。
    """
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName("JiYuAttackNext")
    application = QApplication(sys.argv)
    configure_application(application)
    instance = SingleInstance(parent=application)
    if not instance.acquire():
        # 已有实例在跑属于正常退出；服务端起不来要留下失败退出码。
        return 0 if instance.existing else 1
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
    # 遮罩在窗口显示前创建：它会自动跟随父窗口尺寸并置顶，
    # 界面搭建期间的半成品布局不会露出来。
    splash = create_splash(window)
    window.show()
    if splash is not None:
        splash.start()
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
