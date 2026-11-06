"""首页：仿 Fluent Gallery 的快捷入口与按功能分组的功能卡片。"""

from PySide6.QtCore import Qt, Signal
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
    SubtitleLabel,
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


class ShortcutCard(SimpleCardWidget):
    """顶部的快捷入口：图标、标题、说明与右下角的外链箭头。"""

    MINIMUM_WIDTH = 176
    ICON_SIZE = 40
    # 图标四周的留白取同一个值，上、下、左三边看起来才一样宽。
    PADDING = 26

    def __init__(self, icon, title, description, parent=None):
        super().__init__(parent)
        self.setBorderRadius(CORNER_RADIUS)
        self.setClickEnabled(True)
        self.setMinimumWidth(self.MINIMUM_WIDTH)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self.PADDING, self.PADDING, self.PADDING, self.PADDING
        )
        layout.setSpacing(10)
        self.icon_widget = IconWidget(icon, self)
        self.icon_widget.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        layout.addWidget(self.icon_widget)
        self.title_label = StrongBodyLabel(title, self)
        layout.addWidget(self.title_label)
        self.description_label = CaptionLabel(description, self)
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)
        footer = QHBoxLayout()
        footer.addStretch()
        self.arrow = IconWidget(FIF.LINK, self)
        self.arrow.setFixedSize(16, 16)
        footer.addWidget(self.arrow)
        layout.addLayout(footer)
        # 子控件不接收鼠标事件，点击才能落到整张卡片上。
        for child in (
            self.icon_widget,
            self.title_label,
            self.description_label,
            self.arrow,
        ):
            child.setAttribute(Qt.WA_TransparentForMouseEvents, True)


class ActionCard(SimpleCardWidget):
    """功能入口卡片：左侧纯图标，右侧标题与一句话说明。"""

    ICON_SIZE = 28
    # 图标左右两侧的留白取同一个值，视觉上才会居中在一条竖直的留白里。
    ICON_GAP = 22

    def __init__(self, icon, title, description, parent=None):
        super().__init__(parent)
        self.setBorderRadius(CORNER_RADIUS)
        self.setClickEnabled(True)
        self.setMinimumHeight(84)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(self.ICON_GAP, 14, 18, 14)
        layout.setSpacing(self.ICON_GAP)
        self.icon_widget = IconWidget(icon, self)
        self.icon_widget.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        self.icon_widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.icon_widget, 0, Qt.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title_label = StrongBodyLabel(title, self)
        self.description_label = CaptionLabel(description, self)
        self.description_label.setWordWrap(True)
        text.addWidget(self.title_label)
        text.addWidget(self.description_label)
        layout.addLayout(text, 1)
        for child in (self.title_label, self.description_label):
            child.setAttribute(Qt.WA_TransparentForMouseEvents, True)


# 分组内的入口：远程攻击按使用频率排，本机工具按用途排。
SECTIONS = (
    (
        "远程攻击",
        (
            (
                "message",
                FIF.MESSAGE,
                "文本消息",
                "编辑多行文本，按报文长度自动分条发送",
            ),
            ("file", FIF.SEND, "文件传送", "勾选文件或文件夹，发送到目标学生端桌面"),
            (
                "device",
                FIF.POWER_BUTTON,
                "设备操作",
                "重启、关机或注销，发送前预览目标设备",
            ),
            ("command", FIF.COMMAND_PROMPT, "远程命令", "编辑并发送单条远程命令"),
            (
                "aliases",
                FIF.QUICK_NOTE,
                "设备备注",
                "给地址起个好记的名字并设为当前目标",
            ),
            (
                "shell",
                FIF.SPEED_HIGH,
                "反弹终端",
                "本机监听并让目标主动连回，得到可交互的命令行",
            ),
        ),
    ),
    (
        "教师端模拟",
        (
            (
                "appcmd",
                FIF.ROBOT,
                "应用命令",
                "远程运行程序、打开网址、终止进程与黑屏锁键鼠",
            ),
            (
                "students",
                FIF.PEOPLE,
                "学生信息",
                "以教师端模拟身份发送宣告，收集学生机信息与进程窗口",
            ),
            (
                "screen",
                FIF.VIDEO,
                "屏幕画面",
                "按地址拉取缩略图、打开实时画面并检查远端端口",
            ),
            ("control", FIF.ZOOM, "远程接管", "打开画面并直接把键鼠输入转给学生"),
            ("chat", FIF.CHAT, "聊天消息", "走会话通道发送可回信的聊天内容"),
            (
                "closewindow",
                FIF.CLOSE,
                "关闭窗口",
                "按窗口句柄让目标程序收到关闭消息",
            ),
        ),
    ),
    (
        "本机工具",
        (
            ("local", FIF.IOT, "本机信息", "查询本机 IP 与 Student 相关的监听端口"),
            (
                "firewall",
                FIF.CERTIFICATE,
                "防火墙",
                "调整 StudentMain.exe 的防火墙规则",
            ),
            (
                "logs",
                FIF.HISTORY,
                "运行日志",
                "按功能、级别与关键词筛选，勾选导出或删除",
            ),
        ),
    ),
)

# 顶部的四个入口：最常用的页面加仓库、文档与反馈。
SHORTCUTS = (
    ("message", FIF.MESSAGE, "快速开始", "编辑消息并发送测试报文"),
    ("repository", FIF.GITHUB, "项目仓库", "查看源码、版本与更新记录"),
    ("document", FIF.DOCUMENT, "使用文档", "图形界面的完整说明"),
    ("feedback", FIF.FEEDBACK, "问题反馈", "提交 issue 描述异常现象"),
)


class HomePage(Page):
    """首页，结构与官方 Gallery 示例一致：大标题、快捷入口、功能卡片分组。"""

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

        self.title_label = LargeTitleLabel("JiYu Attack Next", host)
        content.addWidget(self.title_label)
        self.subtitle_label = CaptionLabel(
            "极域学生端 UDP 控制报文测试工具 · 版本 %s" % version_text(), host
        )
        content.addWidget(self.subtitle_label)
        content.addSpacing(8)

        shortcuts = QHBoxLayout()
        shortcuts.setSpacing(12)
        self.shortcuts = {}
        for key, icon, title, description in SHORTCUTS:
            card = ShortcutCard(icon, title, description, host)
            card.setObjectName("homeShortcut_" + key)
            card.clicked.connect(lambda page=key: self.emit_page(page))
            shortcuts.addWidget(card, 1)
            self.shortcuts[key] = card
        content.addLayout(shortcuts)
        content.addSpacing(8)

        self.cards = {}
        for section, entries in SECTIONS:
            # 分组标题与各页顶部的页标题同样使用 SubtitleLabel，
            # 免得首页看起来比功能页的标题层级更高。
            content.addWidget(SubtitleLabel(section, host))
            # 两列排布与官方 Gallery 一致，单卡宽度足够放下说明文字。
            grid = QGridLayout()
            grid.setSpacing(12)
            for index, (key, icon, title, description) in enumerate(entries):
                card = ActionCard(icon, title, description, host)
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
