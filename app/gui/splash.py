"""启动遮罩：主窗口首次显示时用项目图标盖住界面，等首帧绘制完再移开。"""

from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QWidget
from qfluentwidgets import BodyLabel, IndeterminateProgressBar, SplashScreen, TitleLabel

from app.shared.build_info import version_text


class AppSplashScreen(SplashScreen):
    """覆盖在主窗口上的启动遮罩。

    遮罩跟随主窗口尺寸变化，内容为项目图标、应用名、版本号与一条不确定
    进度条。它只在启动时短暂出现，主窗口首帧绘制完成后由 ``finish()``
    关闭，避免界面还在搭建时露出半成品布局。

    Attributes:
        title_label: 应用名，位于图标下方。
        version_label: 版本号，位于应用名下方。
        status_label: 状态提示，位于进度条上方。
        progress: 不确定进度条，表示界面还在准备。
    """

    ICON_SIZE = QSize(128, 128)
    # 图标在窗口垂直居中位置再上抬这么多像素，给下方的文字与进度条留空间。
    ICON_LIFT = 68
    GROUP_GAP = 22
    LABEL_GAP = 6
    PROGRESS_WIDTH = 260
    PROGRESS_MARGIN = 52
    STATUS_GAP = 12
    # 遮罩至少停留这么久，否则构造很快时会一闪而过。
    MINIMUM_DURATION = 800

    def __init__(
        self,
        parent,
        icon=None,
        title=None,
        version=None,
        minimum_duration=MINIMUM_DURATION,
    ):
        """创建启动遮罩。

        Args:
            parent: 遮罩覆盖的窗口，通常是主窗口。
            icon: 遮罩中央的图标，默认取项目图标。
            title: 显示的应用名，默认取主窗口的标题常量。
            version: 显示的版本号，默认读取构建信息。
            minimum_duration: 最短停留时间，单位毫秒。
        """
        from app.gui.resources import app_icon
        from app.gui.window.data import APP_NAME

        super().__init__(icon or app_icon(), parent, enableShadow=True)
        self.setIconSize(self.ICON_SIZE)
        # 遮罩是主窗口的一部分，不需要库自带的标题栏与窗口按钮。
        self.titleBar.hide()

        self.title_label = TitleLabel(title or APP_NAME, self)
        self.version_label = BodyLabel(version or version_text(), self)
        self.status_label = BodyLabel("正在准备界面…", self)
        self.progress = IndeterminateProgressBar(self, start=False)
        self.progress.setFixedWidth(self.PROGRESS_WIDTH)

        self._minimum_duration = max(0, int(minimum_duration))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.finish)
        self._finished = False

    def start(self):
        """显示遮罩并开始计时，计时结束后自动关闭。"""
        self._finished = False
        # 遮罩在窗口显示后才启动，此时不会再有父窗口的尺寸变化事件，
        # 需要主动对齐一次，否则遮罩会停在默认的空尺寸上。
        parent = self.parentWidget()
        if parent is not None:
            self.resize(parent.size())
        self.show()
        self.raise_()
        self.progress.start()
        self._timer.start(self._minimum_duration)

    def finish(self):
        """立即关闭遮罩；重复调用无副作用。"""
        if self._finished:
            return
        self._finished = True
        self._timer.stop()
        self.progress.stop()
        self.close()

    def is_finished(self):
        """返回遮罩是否已经结束。"""
        return self._finished

    def resizeEvent(self, event):
        """按窗口尺寸重排图标、文字与进度条。"""
        super().resizeEvent(event)
        icon = self.iconWidget
        top = icon.y() - self.ICON_LIFT
        icon.move(icon.x(), top)

        self.title_label.adjustSize()
        self.version_label.adjustSize()
        self.status_label.adjustSize()

        title_y = top + icon.height() + self.GROUP_GAP
        self.title_label.move((self.width() - self.title_label.width()) // 2, title_y)
        version_y = title_y + self.title_label.height() + self.LABEL_GAP
        self.version_label.move(
            (self.width() - self.version_label.width()) // 2, version_y
        )

        progress_y = self.height() - self.PROGRESS_MARGIN
        self.progress.move((self.width() - self.progress.width()) // 2, progress_y)
        self.status_label.move(
            (self.width() - self.status_label.width()) // 2,
            progress_y - self.status_label.height() - self.STATUS_GAP,
        )


def create_splash(window, **kwargs):
    """在主窗口上创建启动遮罩。

    Args:
        window: 承载遮罩的窗口；非 ``QWidget`` 时说明调用方用的是替身，
            此时不创建遮罩，方便测试整体替换主窗口。
        **kwargs: 传给 ``AppSplashScreen`` 的其余参数。

    Returns:
        AppSplashScreen | None: 创建成功返回遮罩实例，否则返回 ``None``。
    """
    if not isinstance(window, QWidget):
        return None
    return AppSplashScreen(window, **kwargs)
