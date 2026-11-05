"""首页：仿 Fluent Gallery 的横幅快捷入口与按功能分组的功能卡片。"""

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    IconWidget,
    LargeTitleLabel,
    SimpleCardWidget,
    SmoothScrollArea,
    StrongBodyLabel,
    TitleLabel,
    isDarkTheme,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from ..build_info import version_text
from ..components import CORNER_RADIUS
from .common import Page

REPOSITORY_URL = "https://github.com/JasonFang0109c/jiyu_attack_next"
DOCUMENT_URL = REPOSITORY_URL + "/blob/main/docs/usage/GUI.md"
ISSUE_URL = REPOSITORY_URL + "/issues"


class IconTile(QWidget):
    """功能卡片左侧的圆角色块，图标以白色绘制在色块中央。"""

    SIZE = 48
    RADIUS = 10
    GLYPH_SIZE = 24

    def __init__(self, icon, color, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._color = QColor(color)
        self.setFixedSize(self.SIZE, self.SIZE)

    def paintEvent(self, event):
        """先铺色块再贴图标，避免图标被背景裁掉。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        painter.drawRoundedRect(QRectF(self.rect()), self.RADIUS, self.RADIUS)
        pixmap = self._icon.icon(color=QColor(255, 255, 255)).pixmap(
            QSize(self.GLYPH_SIZE, self.GLYPH_SIZE)
        )
        offset = (self.SIZE - self.GLYPH_SIZE) / 2
        target = QRectF(offset, offset, self.GLYPH_SIZE, self.GLYPH_SIZE)
        painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))


class ShortcutCard(QWidget):
    """横幅上的快捷入口：图标、标题、说明与右下角的外链箭头。"""

    clicked = Signal()

    RADIUS = CORNER_RADIUS
    MINIMUM_WIDTH = 176

    def __init__(self, icon, title, description, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(self.MINIMUM_WIDTH)
        self.setMinimumHeight(160)
        self.setCursor(Qt.PointingHandCursor)
        self._hovered = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        self.icon_widget = IconWidget(icon, self)
        self.icon_widget.setFixedSize(30, 30)
        layout.addWidget(self.icon_widget)
        self.title_label = StrongBodyLabel(title, self)
        layout.addWidget(self.title_label)
        self.description_label = CaptionLabel(description, self)
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)
        layout.addStretch()
        footer = QHBoxLayout()
        footer.addStretch()
        self.arrow = IconWidget(FIF.LINK, self)
        self.arrow.setFixedSize(16, 16)
        footer.addWidget(self.arrow)
        layout.addLayout(footer)
        self._apply_theme_colors()

    def _apply_theme_colors(self):
        """浅色主题下卡片接近白色，图标与文字用深色；深色主题反过来。"""
        if isDarkTheme():
            self.title_label.setStyleSheet("color: white")
            self.description_label.setStyleSheet("color: rgba(255, 255, 255, 200)")
        else:
            self.title_label.setStyleSheet("color: #1a1a1a")
            self.description_label.setStyleSheet("color: rgba(0, 0, 0, 160)")
        self.update()

    def changeEvent(self, event):
        """跟随主题切换重算卡片配色。"""
        if event.type() == QEvent.Type.ThemeChange:
            self._apply_theme_colors()
        super().changeEvent(event)

    def paintEvent(self, event):
        """悬停时略提亮，读起来像浮在横幅上的卡片。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if isDarkTheme():
            border = QColor(255, 255, 255, 90 if self._hovered else 55)
            fill = QColor(255, 255, 255, 55 if self._hovered else 32)
        else:
            border = QColor(255, 255, 255, 150 if self._hovered else 110)
            fill = QColor(255, 255, 255, 225 if self._hovered else 200)
        painter.setPen(border)
        painter.setBrush(fill)
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
            self.RADIUS,
            self.RADIUS,
        )

    def enterEvent(self, event):
        """悬停时加深底色。"""
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """移出后恢复常态。"""
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        """整张卡片都可点击，不必只点某个按钮。"""
        if event.button() == Qt.LeftButton and self.rect().contains(event.position()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class HeroBanner(QWidget):
    """横幅背景：仿 Fluent Gallery 的彩色渐变底，上面浮着快捷卡片。"""

    RADIUS = CORNER_RADIUS

    def __init__(self, parent=None):
        super().__init__(parent)
        # 渐变改成深色系后，白色标题和说明在任何主题下都有足够对比度。
        self.light_colors = (QColor("#7B6BF2"), QColor("#4A3ACB"))
        self.dark_colors = (QColor("#443A8C"), QColor("#211C44"))

    def paintEvent(self, event):
        """圆角裁剪后铺斜向渐变，再叠一条浅色光带。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)
        painter.setClipPath(path)
        start, end = self.dark_colors if isDarkTheme() else self.light_colors
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, start)
        gradient.setColorAt(1.0, end)
        painter.fillRect(rect, gradient)

        band = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
        band.setColorAt(0.0, QColor(255, 255, 255, 0))
        band.setColorAt(0.55, QColor(255, 255, 255, 26))
        band.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(rect, band)


class ActionCard(SimpleCardWidget):
    """功能入口卡片：左侧色块图标，右侧标题与一句话说明。"""

    def __init__(self, icon, color, title, description, parent=None):
        super().__init__(parent)
        self.setBorderRadius(CORNER_RADIUS)
        self.setClickEnabled(True)
        self.setMinimumHeight(88)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(16)
        self.tile = IconTile(icon, color, self)
        layout.addWidget(self.tile, 0, Qt.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title_label = StrongBodyLabel(title, self)
        self.description_label = CaptionLabel(description, self)
        self.description_label.setWordWrap(True)
        text.addWidget(self.title_label)
        text.addWidget(self.description_label)
        layout.addLayout(text, 1)


# 首页的两组入口：远程操作按使用频率排，本机工具按用途排。
SECTIONS = (
    (
        "远程操作",
        (
            (
                "message",
                FIF.MESSAGE,
                "#0F6CBD",
                "文本消息",
                "编辑多行文本，按报文长度自动分条发送",
            ),
            (
                "file",
                FIF.SEND,
                "#038387",
                "文件传送",
                "勾选文件或文件夹，发送到目标学生端桌面",
            ),
            (
                "device",
                FIF.POWER_BUTTON,
                "#C239B3",
                "设备操作",
                "重启、关机或注销，发送前预览目标设备",
            ),
            (
                "command",
                FIF.COMMAND_PROMPT,
                "#CA5010",
                "远程命令",
                "编辑并发送单条远程命令，实时显示缓冲区",
            ),
            (
                "aliases",
                FIF.QUICK_NOTE,
                "#498205",
                "设备备注",
                "给地址起个好记的名字，直接设为当前目标",
            ),
        ),
    ),
    (
        "本机工具",
        (
            (
                "local",
                FIF.IOT,
                "#5D5A58",
                "本机信息",
                "查询本机 IP 与 Student 相关的监听端口",
            ),
            (
                "firewall",
                FIF.CERTIFICATE,
                "#8764B8",
                "防火墙",
                "调整 StudentMain.exe 的防火墙规则并逐项查看结果",
            ),
            (
                "logs",
                FIF.HISTORY,
                "#0B6A0B",
                "运行日志",
                "按功能、级别与关键词筛选，勾选导出或删除",
            ),
        ),
    ),
)


# 横幅上的四个入口：最常用的页面加仓库、文档与反馈。
SHORTCUTS = (
    ("message", FIF.MESSAGE, "快速开始", "编辑消息并发送测试报文"),
    ("repository", FIF.GITHUB, "项目仓库", "查看源码、版本与更新记录"),
    ("document", FIF.DOCUMENT, "使用文档", "图形界面的完整说明"),
    ("feedback", FIF.FEEDBACK, "问题反馈", "提交 issue 描述异常现象"),
)


class HomePage(Page):
    """首页，结构与官方 Gallery 示例一致：大标题、横幅入口、功能卡片分组。"""

    pageRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__("home", parent)
        # 与关于页一致：滚动区域铺满整页，内容超高时整页滚动。
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(0)
        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        bar_width = scroll.verticalScrollBar().sizeHint().width()
        host = QWidget(scroll)
        content = QVBoxLayout(host)
        content.setContentsMargins(28, 24, 28 + bar_width, 24)
        content.setSpacing(16)

        self.banner = HeroBanner(host)
        banner_body = QVBoxLayout(self.banner)
        banner_body.setContentsMargins(28, 26, 28, 26)
        banner_body.setSpacing(6)
        self.title_label = LargeTitleLabel("JiYu Attack Next", self.banner)
        self.title_label.setStyleSheet("color: white")
        banner_body.addWidget(self.title_label)
        self.subtitle_label = CaptionLabel(
            "极域学生端 UDP 控制报文测试工具 · 版本 %s" % version_text(), self.banner
        )
        self.subtitle_label.setStyleSheet("color: rgba(255, 255, 255, 210)")
        banner_body.addWidget(self.subtitle_label)
        banner_body.addSpacing(18)
        shortcuts = QHBoxLayout()
        shortcuts.setSpacing(14)
        self.shortcuts = {}
        for key, icon, title, description in SHORTCUTS:
            card = ShortcutCard(icon, title, description, self.banner)
            card.clicked.connect(lambda page=key: self.emit_page(page))
            shortcuts.addWidget(card, 1)
            self.shortcuts[key] = card
        banner_body.addLayout(shortcuts)
        content.addWidget(self.banner)

        self.cards = {}
        self.section_titles = []
        for section, entries in SECTIONS:
            heading = TitleLabel(section, host)
            self.section_titles.append(heading)
            content.addWidget(heading)
            # 两列排布与官方 Gallery 一致，单卡宽度足够放下说明文字。
            grid = QGridLayout()
            grid.setSpacing(12)
            for index, (key, icon, color, title, description) in enumerate(entries):
                card = ActionCard(icon, color, title, description, host)
                card.setObjectName("homeCard_" + key)
                card.clicked.connect(lambda page=key: self.emit_page(page))
                grid.addWidget(card, index // 2, index % 2)
                self.cards[key] = card
            content.addLayout(grid)
        content.addStretch()
        scroll.setWidget(host)
        # 透明背景要同时作用于滚动区域与内容宿主，否则会留下默认灰底。
        scroll.enableTransparentBackground()
        self.vbox.addWidget(scroll)

    def emit_page(self, key):
        """卡片点击后请求主窗口切换页面。"""
        self.pageRequested.emit(key)
