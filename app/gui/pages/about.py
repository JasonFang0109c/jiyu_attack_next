"""页面实现。"""

from .common import *
from .common import ASSET_ROOT


class AboutInfoCard(SectionCard):
    """关于页中每一项独立的信息卡片。"""

    def __init__(self, label, value, parent=None, url=None, icon=None):
        super().__init__(parent, spacing=0, margins=(18, 12, 18, 12))
        self.setObjectName("aboutInfoCard")
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(BodyLabel(label, self))
        row.addStretch()
        if url is None:
            detail = BodyLabel(value, self)
            detail.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(detail)
        else:
            detail = HyperlinkButton(url, value, self, icon=icon)
            detail.setMaximumWidth(detail.sizeHint().width())
            row.addWidget(detail)
        self.body.addLayout(row)
        self.label = label
        self.detail = detail


class AboutDetailCard(SectionCard):
    """关于页中带标题的多行信息卡片，行样式与组件信息一致。"""

    # 标题与内容行之间额外留白，比行与行之间更大，形成分组层次。
    HEADING_GAP = 6

    def __init__(self, heading, parent=None):
        super().__init__(parent, spacing=8, margins=(18, 12, 18, 12))
        self.setObjectName("aboutDetailCard")
        self.heading = BodyLabel(heading, self)
        self.body.addWidget(self.heading)
        self.body.addSpacing(self.HEADING_GAP)
        self.rows = {}
        self._row_height = None

    def row_height(self):
        """超链接按钮的自然高度；文字行据此对齐。

        用最小高度而非固定高度：固定值会随 DPI 变化裁掉按钮下缘的下划线，
        最小高度只保证等高，不会限制按钮自身绘制。
        """
        if self._row_height is None:
            probe = HyperlinkButton("https://example.invalid", "参考", self)
            self._row_height = probe.sizeHint().height()
            probe.deleteLater()
        return self._row_height

    def add_row(self, key, label, value, url=None, icon=None, tooltip=None):
        """追加一行“名称 + 值”，值可以是纯文本或超链接。"""
        row = QHBoxLayout()
        row.setSpacing(16)
        name = CaptionLabel(label, self)
        name.setMinimumHeight(self.row_height())
        name.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        row.addWidget(name)
        row.addStretch()
        if url is None:
            detail = CaptionLabel(value, self)
            detail.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            detail.setMinimumHeight(self.row_height())
        else:
            detail = HyperlinkButton(url, value, self, icon=icon)
            detail.setMaximumWidth(detail.sizeHint().width())
        if tooltip:
            detail.setToolTip(tooltip)
        row.addWidget(detail)
        self.body.addLayout(row)
        self.rows[key] = detail
        return detail


class AboutPage(Page):
    def __init__(self, parent=None):
        super().__init__("about", parent)
        # 滚动区域铺满整页：滚动条因此贴住窗口右缘并从页面顶部贯通到底部。
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(0)
        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("aboutScroll")
        bar_width = scroll.verticalScrollBar().sizeHint().width()
        content_host = QWidget(scroll)
        content_host.setObjectName("aboutContent")
        content = QVBoxLayout(content_host)
        # 右侧只让出滚动条宽度，卡片与滚动条之间保留页面常规留白。
        content.setContentsMargins(28, 24, 28 + bar_width, 24)
        content.setSpacing(12)
        page_heading(content, "关于")
        content.addSpacing(8)

        hero = QWidget(content_host)
        hero.setObjectName("aboutHero")
        hero_body = QVBoxLayout(hero)
        hero_body.setContentsMargins(20, 18, 20, 18)
        hero_body.setSpacing(10)
        icon_path = ASSET_ROOT / "app.svg"
        icon = QIcon(str(icon_path)).pixmap(96, 96)
        icon_label = QLabel(hero)
        icon_label.setPixmap(icon)
        icon_label.setFixedSize(96, 96)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon_row.addWidget(icon_label)
        icon_row.addStretch()
        hero_body.addLayout(icon_row)
        title = TitleLabel("JiYu Attack Next", hero)
        title.setAlignment(Qt.AlignCenter)
        hero_body.addWidget(title)
        # 与 README 首页说明保持一致。
        for line in (
            "极域学生端 UDP 控制报文测试工具，图形界面与命令行合并为同一个 Windows EXE",
            "基于 PySide6-Fluent-Widgets 构建，打包后无需安装 Python 即可使用 GUI 与 CLI",
            "仅供已获授权的教学环境测试使用",
        ):
            subtitle = BodyLabel(line, hero)
            subtitle.setAlignment(Qt.AlignCenter)
            hero_body.addWidget(subtitle)
        content.addWidget(hero)

        self.author_card = AboutInfoCard(
            "作者",
            "JasonFang0109c",
            content_host,
            url="https://github.com/JasonFang0109c",
            icon=FIF.GITHUB,
        )
        content.addWidget(self.author_card)

        self.repository_card = AboutDetailCard("仓库信息", content_host)
        self.repository_card.add_row(
            "repository",
            "主仓库",
            "https://github.com/JasonFang0109c/jiyu_attack_next",
            url="https://github.com/JasonFang0109c/jiyu_attack_next",
            icon=FIF.GITHUB,
        )
        self.repository_card.add_row(
            "upstream",
            "上游仓库",
            "https://github.com/ht0Ruial/Jiyu_udp_attack",
            url="https://github.com/ht0Ruial/Jiyu_udp_attack",
            icon=FIF.LINK,
        )
        content.addWidget(self.repository_card)

        self.version_card = AboutDetailCard("版本信息", content_host)
        self.version_value = self.version_card.add_row(
            "version",
            "版本",
            version_text(),
            tooltip="版本号遵循语义化版本，nightly 构建可能带预发布后缀",
        )
        self.version_value.setObjectName("aboutVersion")
        self.build_time_value = self.version_card.add_row(
            "build_time",
            "构建时间",
            build_time_text(),
            tooltip="打包 EXE 的时间；源码运行时不会生成构建时间",
        )
        self.build_time_value.setObjectName("aboutBuildTime")
        content.addWidget(self.version_card)

        self.component_card = AboutDetailCard("组件信息", content_host)
        for title_text, package in [
            ("PySide6", "PySide6"),
            ("Fluent Widgets", "PySide6-Fluent-Widgets"),
        ]:
            self.component_card.add_row(package, title_text, version(package))
        content.addWidget(self.component_card)
        content.addStretch()
        scroll.setWidget(content_host)
        # 必须在 setWidget 之后调用：transparent 背景要同时作用于滚动区域
        # 与内容宿主，调用时机不对会漏掉后者，留下默认灰底。
        scroll.enableTransparentBackground()
        self.vbox.addWidget(scroll)
