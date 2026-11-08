"""图形界面的离线测试：窗口装配、页面交互、日志与单实例行为。"""

import io
import json
import os
import shutil
import socket
import sys
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen"
)

from PySide6.QtCore import (
    QAbstractAnimation,
    QBuffer,
    QCoreApplication,
    QEvent,
    QPoint,
    QPointF,
    QRect,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QSystemTrayIcon,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    Dialog,
    FluentWindow,
    HyperlinkButton,
    NavigationDisplayMode,
    NavigationItemHeader,
    SmoothScrollArea,
    StrongBodyLabel,
    Theme,
    ToolTip,
    qconfig,
)

from app import core
from app.gui import app as gui
from app.gui import components, models, screen_window, splash, window_effect
from app.gui.navigation import SidebarTreeWidget
from app.gui.pages.common import (
    CompactHeaderCheckBox,
    CompactTreeItemDelegate,
    FileTreeHeader,
)


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        gui.configure_application(cls.application)

    def setUp(self):
        gui.setTheme(Theme.LIGHT)
        guard = patch.object(
            socket, "socket", side_effect=AssertionError("禁止真实网络通信")
        )
        guard.start()
        self.addCleanup(guard.stop)
        # 用测试名而不是 id(self) 命名：CPython 会复用对象地址，id 命名会让
        # 不同测试共用同一临时目录，残留的 runtime.log 干扰后续断言。
        self.temp_root = (
            Path("build") / "jiyu-gui-test" / self._testMethodName.replace("/", "_")
        )
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.temp_root, ignore_errors=True))
        self.data_dir = self.temp_root / "JiYuAttackNextData"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = str(self.data_dir / "settings.json")
        # 正常构建只写 WARNING 及以上，而这些用例验证 INFO 记录的内容与联动，
        # 所以整个用例期间把默认阈值放宽到 INFO。必须在建窗口之前换掉，
        # LogStore 在构造时读取该常量；发版阈值由
        # test_log_level_is_fixed_by_build_variant 单独校验。
        level_patch = patch.object(models, "DEFAULT_LOG_LEVEL", models.LogLevel.INFO)
        self.default_log_level = level_patch.start()
        self.addCleanup(level_patch.stop)
        self.alias_store = gui.DeviceAliasStore(
            settings=models.portable_settings(self.data_dir)
        )
        self.window = gui.MainWindow(
            alias_store=self.alias_store, data_dir=self.data_dir, enable_tray=False
        )
        self.message = self.window.pages["message"]
        self.command = self.window.pages["command"]
        self.device = self.window.pages["device"]
        self.state = self.window.connection_state
        notify = patch.object(self.window, "_notify")
        self.notify = notify.start()
        self.addCleanup(notify.stop)
        confirm = patch.object(self.window, "_confirm", return_value=True)
        self.confirm_patcher = confirm
        self.confirm = confirm.start()
        self.addCleanup(confirm.stop)
        self.addCleanup(self.dispose_window)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), "界面任务未在预期时间内结束")

    def hover(self, widget, position):
        """投递进入与移动事件，模拟鼠标悬停。

        不依赖系统光标位置：QTest.mouseMove 在 Windows 上驱动真实光标，
        光标已在该位置时不产生移动事件；ToolTipFilter 也只在 Enter 事件
        上启动计时，仅发送移动事件不会触发提示。
        """
        self.leave(widget)
        QApplication.sendEvent(widget, QEvent(QEvent.Type.Enter))
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(position),
            widget.mapToGlobal(QPointF(position)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(widget, event)
        QTest.qWait(30)

    def leave(self, widget):
        """投递离开事件，模拟鼠标移出控件。"""
        QApplication.sendEvent(widget, QEvent(QEvent.Type.Leave))
        QTest.qWait(30)

    def dispose_window(self):
        self.window.close()
        if not self.window._quit_finished:
            self.wait_for(lambda: self.window._quit_finished)
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(self.window, QEvent.Type.DeferredDelete)
        self.application.processEvents()

    def dispose_widget(self, widget):
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)

    def test_fluent_window_has_all_function_pages(self):
        self.assertIsInstance(self.window, FluentWindow)
        self.assertEqual(self.window.windowTitle(), gui.APP_NAME)
        self.assertFalse(self.window.windowIcon().isNull())
        # 首页加 10 个功能页：文本消息、文件传送、设备操作、远程命令、设备备注、
        # 应用命令、学生信息、本机信息、防火墙、运行日志，另有设置与关于。
        self.assertEqual(self.window.stackedWidget.count(), 19)
        self.assertEqual(self.window.current_page(), "home")
        self.assertEqual(self.state.values["target"], "")
        self.assertEqual(self.state.values["port"], 4705)
        self.assertEqual(self.window.logs.minimum_level, models.LogLevel.INFO)
        self.assertIn("0 / 163", self.command.statistics.text())

    def test_application_font_stack_matches_component_fonts(self):
        # 组件库控件按 getFont 取字体，QApplication 的字体管不到它们，
        # 两处必须给同一个字体栈，否则中文与西文会混用不同字族。
        families = gui.font_families()
        self.assertTrue(families)
        self.assertEqual(qconfig.get(qconfig.fontFamilies), families)
        self.assertEqual(self.application.font().families(), families)
        self.assertEqual(StrongBodyLabel().font().families(), families)

    def test_idle_status_is_hidden_and_about_page_has_project_info(self):
        self.assertFalse(self.message.footer.status.isVisible())
        self.assertEqual(self.message.footer.status.text(), "")
        about = self.window.pages["about"]
        self.assertEqual(about.objectName(), "about")
        links = [
            button.getUrl().toString() for button in about.findChildren(HyperlinkButton)
        ]
        self.assertIn("https://github.com/JasonFang0109c", links)
        self.assertIn("https://github.com/JasonFang0109c/jiyu_attack_next", links)
        self.assertIn("https://github.com/ht0Ruial/Jiyu_udp_attack", links)
        self.assertNotIn(
            "https://github.com/JasonFang0109c",
            [button.text() for button in about.findChildren(HyperlinkButton)],
        )
        self.assertIn(
            "JasonFang0109c",
            [button.text() for button in about.findChildren(HyperlinkButton)],
        )
        self.assertEqual(about.author_card.objectName(), "aboutInfoCard")
        self.assertEqual(about.author_card.borderRadius, components.CORNER_RADIUS)
        self.assertEqual(about.author_card.detail.text(), "JasonFang0109c")
        hero = about.findChild(QWidget, "aboutHero")
        self.assertIsNotNone(hero)
        self.assertNotIsInstance(hero, components.SectionCard)
        self.assertFalse(hero.findChildren(components.SectionCard))

    def test_about_page_groups_version_and_repository_info(self):
        from app.gui import build_info

        about = self.window.pages["about"]
        # 版本与构建时间合并到“版本信息”，组件版本改名为“组件信息”。
        self.assertEqual(about.version_card.heading.text(), "版本信息")
        self.assertEqual(about.version_card.objectName(), "aboutDetailCard")
        self.assertEqual(about.version_card.borderRadius, components.CORNER_RADIUS)
        self.assertEqual(about.version_value.text(), build_info.version_text())
        self.assertEqual(about.version_value.objectName(), "aboutVersion")
        self.assertEqual(about.build_time_value.text(), "源码运行")
        self.assertEqual(about.build_time_value.objectName(), "aboutBuildTime")
        self.assertEqual(
            [label.text() for label in about.version_card.findChildren(CaptionLabel)][
                ::2
            ],
            ["版本", "构建时间"],
        )
        self.assertEqual(about.component_card.heading.text(), "组件信息")
        self.assertEqual(about.component_card.objectName(), "aboutDetailCard")
        self.assertIn("PySide6", about.component_card.rows)
        self.assertIn("PySide6-Fluent-Widgets", about.component_card.rows)
        self.assertEqual(about.license_card.heading.text(), "许可信息")
        self.assertEqual(
            about.license_card.rows["license"].text(),
            "GNU General Public License v3.0",
        )
        self.assertEqual(
            about.license_card.rows["license"].getUrl().toString(),
            "https://www.gnu.org/licenses/gpl-3.0.html",
        )
        self.assertNotIn(
            "组件版本", [label.text() for label in about.findChildren(BodyLabel)]
        )

    def show_about_page(self):
        """关于页放在 stacked 容器中，未切换过去时几何信息无效。"""
        self.window.show_page("about")
        self.window.show()
        self.application.processEvents()
        return self.window.pages["about"]

    def test_about_detail_rows_share_uniform_height(self):
        about = self.show_about_page()
        cards = (
            about.repository_card,
            about.version_card,
            about.component_card,
            about.license_card,
        )
        row_height = about.repository_card.row_height()
        for card in cards:
            heights = {widget.height() for widget in card.rows.values()}
            self.assertEqual(heights, {row_height}, card.heading.text())
            offsets = [widget.geometry().top() for widget in card.rows.values()]
            self.assertEqual(offsets, sorted(offsets))
        # 行数与行高都一致的卡片，总高应完全相同；仓库信息多一行来源仓库，
        # 高度自然比另外三张多一行。
        two_row = (about.version_card, about.component_card, about.license_card)
        self.assertEqual(len({card.height() for card in two_row}), 1)

    def test_about_links_are_not_clipped(self):
        about = self.show_about_page()
        for card in (
            about.repository_card,
            about.version_card,
            about.component_card,
            about.license_card,
        ):
            for widget in card.rows.values():
                # 下划线位于按钮下缘，高度小于 sizeHint 就会被裁掉。
                self.assertGreaterEqual(
                    widget.height(),
                    widget.sizeHint().height(),
                    widget.text() if hasattr(widget, "text") else "",
                )

    def test_about_heading_sits_further_from_rows_than_rows_do(self):
        about = self.show_about_page()
        card = about.repository_card
        rows = list(card.rows.values())
        heading_bottom = card.heading.geometry().bottom()
        row_gap = rows[1].geometry().top() - rows[0].geometry().bottom()
        heading_gap = rows[0].geometry().top() - heading_bottom
        # 标题与首行的间距应明显大于行间距，形成分组层次。
        self.assertGreater(heading_gap, row_gap)
        self.assertGreaterEqual(heading_gap, row_gap + card.HEADING_GAP - 1)

    def test_about_page_scrolls_when_window_is_short(self):
        about = self.show_about_page()
        scroll = about.findChild(SmoothScrollArea)
        self.assertIsNotNone(scroll)
        self.assertTrue(scroll.widgetResizable())
        # 内容高于视口时可通过滚动查看，而不是压缩布局。
        self.assertGreater(scroll.widget().sizeHint().height(), 0)

    def test_about_hero_subtitle_matches_readme(self):
        about = self.window.pages["about"]
        hero = about.findChild(QWidget, "aboutHero")
        texts = [label.text() for label in hero.findChildren(BodyLabel)]
        for line in (
            "极域课堂 UDP 报文测试工具，覆盖学生端控制与教师端模拟，图形界面与命令行合并为同一个 Windows EXE",
            "基于 PySide6-Fluent-Widgets 构建，打包后无需安装 Python 即可使用 GUI 与 CLI",
            "仅供已获授权的教学环境测试使用",
        ):
            self.assertIn(line, texts)
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
            encoding="utf-8"
        )
        for line in texts:
            self.assertIn(line, readme)

    def test_about_page_merges_repository_links_into_one_card(self):
        about = self.window.pages["about"]
        self.assertEqual(about.repository_card.heading.text(), "仓库信息")
        self.assertEqual(about.repository_card.objectName(), "aboutDetailCard")
        self.assertEqual(
            sorted(about.repository_card.rows), ["origin", "repository", "thirdparty"]
        )
        self.assertEqual(
            about.repository_card.rows["repository"].getUrl().toString(),
            "https://github.com/JasonFang0109c/jiyu_attack_next",
        )
        self.assertEqual(
            about.repository_card.rows["origin"].getUrl().toString(),
            "https://github.com/ht0Ruial/Jiyu_udp_attack",
        )
        self.assertEqual(
            about.repository_card.rows["thirdparty"].getUrl().toString(),
            "https://github.com/yunsjxh/Third-party-JiYu-Teacher-Endpoint",
        )
        self.assertNotIn(
            "GitHub 仓库", [label.text() for label in about.findChildren(BodyLabel)]
        )

    def test_build_time_comes_from_bundle_asset(self):
        from app.gui import build_info

        self.assertEqual(build_info.build_time_text(), "源码运行")
        time_file = self.temp_root / "bundle" / build_info.BUILD_TIME_FILE_NAME
        build_info.write_build_time(time_file)
        with patch.object(gui.sys, "_MEIPASS", str(time_file.parent), create=True):
            self.assertRegex(
                build_info.build_time_text(), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
            )
        with patch.object(
            gui.sys, "_MEIPASS", str(self.temp_root / "missing"), create=True
        ):
            self.assertEqual(build_info.build_time_text(), "源码运行")

    def test_version_comes_from_bundle_asset(self):
        from app import __version__
        from app.gui import build_info

        self.assertEqual(build_info.version_text(), __version__)
        version_file = self.temp_root / "bundle" / build_info.VERSION_FILE_NAME
        build_info.write_version(version_file, "9.9.9")
        with patch.object(gui.sys, "_MEIPASS", str(version_file.parent), create=True):
            self.assertEqual(build_info.version_text(), "9.9.9")

    def test_every_page_uses_rounded_section_cards(self):
        # 首页用整块横幅与入口卡片组织内容，没有分区卡片，单独断言卡片圆角。
        home = self.window.pages["home"]
        self.assertTrue(home.cards)
        self.assertTrue(
            all(
                card.borderRadius == components.CORNER_RADIUS
                for card in home.cards.values()
            )
        )
        for key, page in self.window.pages.items():
            if key == "home":
                continue
            cards = page.findChildren(components.SectionCard)
            self.assertGreaterEqual(len(cards), 1, page.objectName())
            self.assertTrue(
                all(card.borderRadius == components.CORNER_RADIUS for card in cards)
            )

    def test_title_bar_keeps_icon_and_title(self):
        self.assertFalse(self.window.titleBar.iconLabel.isHidden())
        self.assertFalse(self.window.titleBar.titleLabel.isHidden())
        self.assertEqual(self.window.titleBar.titleLabel.text(), gui.APP_NAME)
        self.assertFalse(hasattr(self.window, "global_status"))
        self.window.show()
        self.application.processEvents()
        menu = self.window.navigationInterface.panel.menuButton
        icon = self.window.titleBar.iconLabel
        menu_center = menu.mapTo(self.window, menu.rect().center()).y()
        icon_center = icon.mapTo(self.window, icon.rect().center()).y()
        self.assertLessEqual(abs(menu_center - icon_center), 1)
        gap = (
            icon.mapTo(self.window, icon.rect().topLeft()).x()
            - menu.mapTo(self.window, menu.rect().topRight()).x()
        )
        self.assertGreaterEqual(gap, 5)

    def test_sidebar_routes_preserve_drafts(self):
        self.message.editor.setPlainText("测试通知")
        self.command.editor.setPlainText("whoami")
        for key in self.window.pages:
            self.window.show_page(key)
            self.assertEqual(self.window.current_page(), key)
        self.assertEqual(self.message.editor.toPlainText(), "测试通知")
        self.assertEqual(self.command.editor.toPlainText(), "whoami")

    def test_navigation_groups_pages_in_expected_order(self):
        # 分组顺序固定：远程攻击、教师端模拟、设备备注、本机工具、本机进程。
        panel = self.window.navigationInterface.panel
        top = [
            item.routeKey
            for item in panel.items.values()
            if not item.parentRouteKey
            and item.routeKey not in ("logs", "settings", "about")
        ]
        self.assertEqual(
            top,
            [
                "home",
                "group_remote",
                "group_teacher",
                "aliases",
                "group_local",
                "group_process",
            ],
        )
        self.assertEqual(
            [child.text() for child in panel.widget("group_remote").treeChildren],
            ["文本消息", "文件传送", "设备操作", "远程命令", "反弹终端"],
        )
        self.assertEqual(
            [child.text() for child in panel.widget("group_teacher").treeChildren],
            ["应用命令", "学生信息", "屏幕画面", "远程接管", "聊天消息", "关闭窗口"],
        )
        self.assertEqual(
            [child.text() for child in panel.widget("group_local").treeChildren],
            ["本机信息", "防火墙"],
        )
        self.assertEqual(
            [child.text() for child in panel.widget("group_process").treeChildren],
            ["结束学生端"],
        )

    def test_navigation_groups_have_no_header_text(self):
        # 分组靠缩进表达层级，侧边栏不再出现灰色小字分类标题。
        headers = [
            widget.text()
            for widget in self.window.navigationInterface.panel.findChildren(
                NavigationItemHeader
            )
        ]
        self.assertEqual(headers, [])

    def test_sidebar_starts_collapsed_and_remembers_expanded_state(self):
        # 首次使用保持图标模式；展开后写进设置，下次启动按它恢复。
        panel = self.window.navigationInterface.panel
        self.assertTrue(panel.isCollapsed())
        # 收展请求立即保存，不依赖动画是否完整播放。
        self.window.navigationInterface.expand()
        self.assertFalse(panel.isCollapsed())
        self.assertTrue(
            self.window.settings.value(models.NAVIGATION_EXPANDED_SETTINGS_KEY, False)
        )
        another = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=models.portable_settings(self.data_dir)
            ),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            self.assertFalse(another.navigationInterface.panel.isCollapsed())
        finally:
            another.close()
            another.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            self.application.processEvents()

    def test_switching_to_child_page_expands_its_group(self):
        panel = self.window.navigationInterface.panel
        # 侧边栏首次使用是收起的，先展开才能看到分组里的子项。
        self.window.navigationInterface.expand(useAni=False)
        group = panel.widget("group_teacher")
        group.setExpanded(False, ani=False)
        self.window.show_page("appcmd")
        self.assertTrue(group.isExpanded)
        self.assertEqual(self.window.current_page(), "appcmd")

    def test_selected_children_do_not_leak_into_collapsed_sidebar(self):
        self.window.apply_window_material(gui.MATERIAL_SOLID)
        self.window.show()
        panel = self.window.navigationInterface.panel
        for route in ("message", "appcmd", "firewall"):
            with self.subTest(route=route):
                self.window.expand_navigation()
                self.window.show_page("home")
                self.window._reveal_navigation_item(route)
                self.application.processEvents()
                leaf = panel.widget(route)
                group = leaf.treeParent
                QTest.mouseClick(leaf.itemWidget, Qt.LeftButton)
                panel.collapse()
                for delay in (0, 30):
                    QTest.qWait(delay)
                    self.assertTrue(leaf.isHidden())
                    self.assertEqual(group.height(), 36)
                    self.assertTrue(panel.indicator.isHidden())
                self.wait_for(
                    lambda: panel.expandAni.state() == QAbstractAnimation.State.Stopped
                )
                self.assertEqual(panel.width(), 48)
                self.assertTrue(group.itemWidget._canDrawIndicator())
                # 检查实际绘制的蓝色像素，避免只验父节点尺寸而漏掉选中条残影。
                image = panel.grab().toImage()
                ratio = image.devicePixelRatio()
                origin = group.itemWidget.mapTo(panel, QPoint())
                expected = QRect(origin.x(), origin.y() + 9, 5, 19)
                colored = []
                for y in range(image.height()):
                    for x in range(image.width()):
                        color = image.pixelColor(x, y)
                        if (
                            color.blue() > color.red() + 60
                            and color.green() > color.red() + 20
                        ):
                            point = QPoint(int(x / ratio), int(y / ratio))
                            colored.append(point)
                            self.assertTrue(expected.contains(point), (route, point))
                self.assertTrue(colored, "选中标记应该画在当前父项左侧")
                panel.expand(useAni=False)
                self.application.processEvents()
                self.assertFalse(leaf.isHidden())
                self.assertEqual(self.window.current_page(), route)
                self.assertEqual(group.itemWidget.width(), 190)
                for item in panel.items.values():
                    self.assertEqual(
                        item.widget.expandAni.state(), QAbstractAnimation.State.Stopped
                    )

    def test_sidebar_animation_reverses_and_preserves_window_height(self):
        self.window.show()
        self.application.processEvents()
        panel = self.window.navigationInterface.panel
        self.window.show_page("message")
        for _ in range(3):
            panel.expand()
            QTest.qWait(25)
            panel.collapse()
            self.assertTrue(panel.widget("message").isHidden())
            QTest.qWait(20)
            panel.expand()
            self.window.resize(1200, self.window.height() - 15)
            self.wait_for(
                lambda: panel.expandAni.state() == QAbstractAnimation.State.Stopped
            )
            self.assertFalse(panel.isCollapsed())
            self.assertEqual(panel.width(), 200)
            self.assertEqual(panel.height(), self.window.navigationInterface.height())
            self.assertFalse(panel.widget("message").isHidden())
        panel.collapse()
        self.wait_for(
            lambda: panel.expandAni.state() == QAbstractAnimation.State.Stopped
        )
        self.assertEqual(panel.width(), 48)
        self.assertEqual(self.window.navigationInterface.width(), 48)

    def test_group_state_survives_compact_mode_and_programmatic_navigation(self):
        panel = self.window.navigationInterface.panel
        self.window.expand_navigation()
        teacher = panel.widget("group_teacher")
        teacher.setExpanded(False)
        attack = panel.widget("message").treeParent
        panel.collapse()
        self.wait_for(
            lambda: panel.expandAni.state() == QAbstractAnimation.State.Stopped
        )
        self.assertFalse(teacher.isExpanded)
        self.assertTrue(attack.isExpanded)
        self.window.show_page("appcmd")
        self.assertTrue(teacher.isExpanded)
        self.assertTrue(panel.widget("appcmd").isHidden())
        self.assertEqual(teacher.height(), 36)
        panel.expand(useAni=False)
        self.assertFalse(panel.widget("appcmd").isHidden())
        self.assertTrue(attack.isExpanded)
        self.assertTrue(
            self.window.settings.value("gui/window/navigation_group_teacher", False)
        )

    def test_sidebar_narrow_overlay_returns_to_interface(self):
        self.window.show()
        panel = self.window.navigationInterface.panel
        for width in (960, 1049, 1050, 1200):
            with self.subTest(width=width):
                self.window.resize(width, 760)
                self.application.processEvents()
                panel.expand(useAni=False)
                if width < panel.minimumExpandWidth:
                    self.assertEqual(panel.displayMode, NavigationDisplayMode.MENU)
                    self.assertIs(panel.parent(), self.window)
                    self.assertEqual(self.window.navigationInterface.width(), 48)
                else:
                    self.assertEqual(panel.displayMode, NavigationDisplayMode.EXPAND)
                    self.assertIs(panel.parent(), self.window.navigationInterface)
                panel.collapse()
                self.wait_for(
                    lambda: panel.expandAni.state() == QAbstractAnimation.State.Stopped
                )
                self.assertIs(panel.parent(), self.window.navigationInterface)
                self.assertEqual(panel.width(), 48)
        self.window.resize(1300, 820)
        self.application.processEvents()
        self.assertTrue(panel.isCollapsed())

    def test_sidebar_overlay_can_become_inline_without_collapsing(self):
        self.window.show()
        panel = self.window.navigationInterface.panel
        self.window.resize(960, 760)
        self.application.processEvents()
        panel.expand(useAni=False)
        self.assertEqual(self.window.navigationInterface.width(), 48)
        self.window.resize(1200, 760)
        self.application.processEvents()
        panel.expand(useAni=False)
        self.assertIs(panel.parent(), self.window.navigationInterface)
        self.assertEqual(self.window.navigationInterface.width(), 200)
        self.window.resize(960, 760)
        self.application.processEvents()
        panel.expand(useAni=False)
        self.assertEqual(panel.displayMode, NavigationDisplayMode.MENU)
        self.assertEqual(self.window.navigationInterface.width(), 48)

    def test_compact_sidebar_updates_parent_marker_when_switching_groups(self):
        self.window.show()
        panel = self.window.navigationInterface.panel
        first = panel.widget("message").treeParent
        second = panel.widget("appcmd").treeParent
        self.window.show_page("message")
        self.application.processEvents()
        self.assertTrue(first.itemWidget._canDrawIndicator())
        self.assertFalse(second.itemWidget._canDrawIndicator())
        with (
            patch.object(first.itemWidget, "update") as first_update,
            patch.object(second.itemWidget, "update") as second_update,
        ):
            self.window.show_page("appcmd")
            first_update.assert_called()
            second_update.assert_called()
        self.assertFalse(first.itemWidget._canDrawIndicator())
        self.assertTrue(second.itemWidget._canDrawIndicator())
        self.assertTrue(panel.widget("appcmd").isHidden())

    def test_sidebar_flyout_clone_keeps_leaf_clicks_free_of_geometry_animation(self):
        panel = self.window.navigationInterface.panel
        original = panel.widget("message")
        clone = original.clone()
        self.addCleanup(clone.deleteLater)
        self.assertIsInstance(clone, SidebarTreeWidget)
        clone.setCompacted(False)
        clone._onClicked(True, False)
        self.assertEqual(self.window.current_page(), "message")
        self.assertEqual(clone.expandAni.state(), QAbstractAnimation.State.Stopped)
        self.assertEqual(original.expandAni.state(), QAbstractAnimation.State.Stopped)
        self.assertTrue(original.isHidden())
        self.assertTrue(panel.isCollapsed())

    def test_students_page_lists_discovered_records(self):
        page = self.window.pages["students"]
        page.set_students(
            [{"address": "10.1.1.5", "info": {"name": "机房-01"}, "processes": []}]
        )
        self.assertEqual(page.students.rowCount(), 1)
        page.students.selectRow(0)
        self.assertEqual(page.selected_address(), "10.1.1.5")
        # 画面相关的入口已经搬到独立页面，这一页只剩发现与进程窗口。
        self.assertFalse(hasattr(page, "preview_button"))
        self.assertFalse(hasattr(page, "viewRequested"))

    def test_screen_page_shows_preview_and_placeholder(self):
        page = self.window.pages["screen"]
        self.assertIsInstance(page.preview_label, BodyLabel)
        page.set_preview(self.png_bytes())
        self.assertFalse(page.preview_label.pixmap().isNull())
        page.set_preview(None)
        self.assertIn("暂无缩略图", page.preview_label.text())

    def test_screen_page_opens_window_for_typed_host(self):
        page = self.window.pages["screen"]
        page.host_input.setText("10.1.1.7")
        page.channel_input.setValue(3)
        with patch.object(gui, "ScreenWindow") as window_class:
            page.viewRequested.emit()
        window_class.assert_called_once()
        self.assertEqual(window_class.call_args.args[0], "10.1.1.7")
        self.assertEqual(window_class.call_args.args[2], 3)

    def test_screen_probe_keeps_event_loop_responsive_and_preserves_target(self):
        page = self.window.pages["screen"]
        for reachable, detail in ((True, ""), (False, "模拟超时")):
            with self.subTest(reachable=reachable):
                entered, release = Event(), Event()

                def blocked_probe(
                    host,
                    timeout,
                    _entered=entered,
                    _release=release,
                    _reachable=reachable,
                    _detail=detail,
                ):
                    _entered.set()
                    if not _release.wait(3):
                        raise TimeoutError("测试未及时释放端口检查")
                    return _reachable, _detail

                page.host_input.setText("10.1.1.7")
                with patch.object(core, "probe", side_effect=blocked_probe) as probe:
                    try:
                        self.window.probe_screen_port()
                        self.wait_for(entered.is_set)
                        self.assertFalse(page.probe_button.isEnabled())
                        page.host_input.setText("10.1.1.9")
                        ticks = []
                        QTimer.singleShot(0, lambda target=ticks: target.append(True))
                        self.wait_for(lambda target=ticks: bool(target))
                        self.window.probe_screen_port()
                        self.assertEqual(probe.call_count, 1)
                    finally:
                        release.set()
                        self.wait_for(lambda: self.window.thread is None)
                    probe.assert_called_once_with("10.1.1.7", timeout=gui.PROBE_TIMEOUT)
                self.assertTrue(page.probe_button.isEnabled())
                self.assertIn("10.1.1.7", page.status.text())
                self.assertIn("可连" if reachable else "模拟超时", page.status.text())

    def test_screen_window_reuse_waits_for_cleanup_and_updates_control_port(self):
        entered, release = Event(), Event()
        sessions = []
        order = []

        def make_session(*args, **kwargs):
            session = MagicMock()
            if not sessions:

                def slow_close():
                    entered.set()
                    if not release.wait(5):
                        raise RuntimeError("测试未释放旧屏幕连接")

                session.close.side_effect = slow_close
            sessions.append(session)
            return session

        with (
            patch.object(
                screen_window,
                "start_screen",
                side_effect=lambda *a, **k: order.append("start"),
            ),
            patch.object(
                screen_window,
                "stop_screen",
                side_effect=lambda *a, **k: order.append("stop"),
            ),
            patch.object(screen_window, "ScreenSession", side_effect=make_session),
        ):
            try:
                self.window._open_screen_window("10.1.1.7", 3, False)
                window = self.window._screen_windows[("10.1.1.7", 3)]
                self.wait_for(lambda: window.session is not None)
                self.window._open_screen_window("10.1.1.7", 3, False)
                self.assertEqual(len(sessions), 1)
                window.control = MagicMock()
                old_control = window.control
                self.window.connection_state.values["port"] = 4706
                self.window._open_screen_window("10.1.1.7", 3, False)
                self.assertIs(self.window._screen_windows[("10.1.1.7", 3)], window)
                self.assertEqual(window.port, 4706)
                old_control.close.assert_called_once()
                self.assertIsNone(window.control)
                window.close()
                self.wait_for(entered.is_set)
                self.window._open_screen_window("10.1.1.7", 3, True)
                self.assertIs(self.window._screen_windows[("10.1.1.7", 3)], window)
                self.assertEqual(order, ["start"])
                release.set()
                self.wait_for(
                    lambda: len(sessions) == 2 and window.session is sessions[1]
                )
                self.assertEqual(order[:3], ["start", "stop", "start"])
                window.close()
                self.wait_for(lambda: window.shutdown_complete)
                window.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                self.application.processEvents()
                self.assertNotIn(("10.1.1.7", 3), self.window._screen_windows)
            finally:
                release.set()
                for window in self.window.findChildren(gui.ScreenWindow):
                    window.close()
                    self.wait_for(lambda current=window: current.shutdown_complete)

    def test_control_page_starts_with_takeover(self):
        page = self.window.pages["control"]
        page.host_input.setText("10.1.1.8")
        with patch.object(gui, "ScreenWindow") as window_class:
            page.controlRequested.emit()
        window_class.assert_called_once()
        self.assertEqual(window_class.call_args.args[0], "10.1.1.8")
        window_class.return_value.request_control.assert_called_once_with()

    def test_app_command_log_button_connects_once(self):
        with patch.object(self.window, "show_page") as show_page:
            self.window.pages["appcmd"].footer.viewLogs.emit()
        show_page.assert_called_once_with("logs")

    def test_student_refresh_and_process_workers_accept_their_arguments(self):
        page = self.window.pages["students"]
        record = {"address": "10.1.1.8", "processes": [(4321, "notepad.exe")]}
        with (
            patch.object(page, "selected_record", return_value=record),
            patch.object(page, "selected_address", return_value="10.1.1.8"),
            patch.object(page, "selected_detail_id", return_value=4321),
            patch.object(page, "kill_target", return_value=""),
            patch.object(page, "detail_kind", return_value="processes"),
            patch.object(self.window, "_begin_task") as begin_task,
            patch.object(core, "fetch_students_info", return_value=[]) as fetch,
            patch.object(core, "send_mess_command", return_value=1) as send,
        ):
            for start in (
                self.window.refresh_students,
                self.window.kill_student_process,
            ):
                begin_task.reset_mock()
                start()
                worker = begin_task.call_args.args[1]
                results, errors = [], []
                worker.completed.connect(results.append)
                worker.failed.connect(
                    lambda message, details, target=errors: target.append(message)
                )
                worker.run()
                self.assertEqual(errors, [])
                self.assertEqual(len(results), 1)
            fetch.assert_called_once()
            send.assert_called_once()

    def test_ipv4_assignment_preserves_existing_signal_block(self):
        target = self.message.targets.target_input
        segment = target.segments[0]
        segment.blockSignals(True)
        try:
            target.setText("10.2.3.4")
            self.assertTrue(segment.signalsBlocked())
            self.assertEqual(target.text(), "10.2.3.4")
            self.assertFalse(target.segments[1].signalsBlocked())
        finally:
            segment.blockSignals(False)

    def test_chat_page_requires_message_text(self):
        page = self.window.pages["chat"]
        with self.assertRaises(ValueError):
            page.message()
        page.editor.setPlainText("机房请注意")
        self.assertEqual(page.message(), "机房请注意")
        page.teacher_input.setText("")
        self.assertEqual(page.teacher_name(), "1")

    def test_close_window_page_parses_handles(self):
        page = self.window.pages["closewindow"]
        with self.assertRaises(ValueError):
            page.window_handle()
        page.window_input.setText("0x00120A3C")
        self.assertEqual(page.window_handle(), 0x00120A3C)
        page.window_input.setText("48212800")
        self.assertEqual(page.window_handle(), 48212800)
        page.window_input.setText("0")
        with self.assertRaises(ValueError):
            page.window_handle()

    def test_close_window_page_accepts_title_keywords(self):
        page = self.window.pages["closewindow"]
        page.window_input.setText("记事本")
        self.assertEqual(page.window_target(), ("title", "记事本"))
        page.window_input.setText("0x00120A3C")
        self.assertEqual(page.window_target(), ("handle", 0x00120A3C))
        page.window_input.setText("")
        with self.assertRaises(ValueError):
            page.window_target()

    def test_device_power_uses_app_command(self):
        page = self.window.pages["device"]
        page.shutdown.setChecked(True)
        page.delay_input.setValue(30)
        page.force_input.setChecked(False)
        page.text_input.setText("请保存作业")
        self.assertEqual(
            page.power(),
            {"reboot": False, "delay": 30, "force": False, "text": "请保存作业"},
        )
        with (
            patch.object(self.window, "start_power") as start_power,
            patch.object(self.window, "_begin_task") as begin_task,
        ):
            self.window.start_send("device")
        start_power.assert_called_once_with()
        begin_task.assert_not_called()
        page.logoff.setChecked(True)
        self.assertFalse(page.delay_input.isEnabled())

    def test_black_screen_timer_sends_unlock(self):
        self.window._blackscreen_targets = ["10.1.1.8"]
        self.window._blackscreen_channel = 3
        with patch.object(core, "send_unlocks", return_value=13) as send:
            self.window._auto_unlock_blackscreen()
        self.assertEqual(send.call_args.args[0], ["10.1.1.8"])
        self.assertEqual(send.call_args.kwargs["channel"], 3)
        self.assertEqual(self.window._blackscreen_targets, [])

    def test_student_preview_all_dispatches_worker(self):
        page = self.window.pages["students"]
        page.set_students([{"address": "10.1.1.8", "computer": "PC-01"}])
        self.window.thread = None
        with patch.object(self.window, "_begin_task") as begin_task:
            page.previewAllRequested.emit()
        worker = begin_task.call_args.args[1]
        self.assertIsInstance(worker, gui.TaskWorker)
        self.assertEqual(begin_task.call_args.args[0], "students")
        with patch.object(core, "collect_previews", return_value={}) as collect:
            worker.run()
        collect.assert_called_once()

    def test_students_serve_button_starts_and_stops_session(self):
        page = self.window.pages["students"]
        fake = MagicMock()
        fake.students = {"10.1.1.8": {"address": "10.1.1.8", "info": {"name": "PC-01"}}}
        with patch.object(core, "TeacherSession", return_value=fake) as factory:
            self.window.toggle_serve()
            factory.assert_called_once()
            fake.start.assert_called_once_with()
            self.assertIs(self.window._serve_session, fake)
            self.assertTrue(self.window._serve_timer.isActive())
            # 常驻期间不允许改频道与教师名，否则会和已建立的会话不一致。
            self.assertFalse(page.channel_input.isEnabled())
            self.window.toggle_serve()
        fake.stop.assert_called_once_with()
        self.assertIsNone(self.window._serve_session)
        self.assertFalse(self.window._serve_timer.isActive())
        self.assertTrue(page.channel_input.isEnabled())

    def test_student_process_page_lists_and_gates_stop_button(self):
        page = self.window.pages["studentproc"]
        page.set_processes([])
        self.assertFalse(page.stop_button.isEnabled())
        self.assertIn("没有正在运行", page.status.text())
        page.set_processes(
            [{"pid": 17600, "name": "StudentMain.exe", "ports": [4705, 51767]}]
        )
        self.assertTrue(page.stop_button.isEnabled())
        self.assertEqual(page.table.item(0, 2).text(), "4705、51767")
        # 任务进行中按钮要禁用，避免重复提权。
        page.set_busy(True)
        self.assertFalse(page.stop_button.isEnabled())
        self.assertFalse(page.refresh_button.isEnabled())
        page.set_busy(False)
        self.assertTrue(page.stop_button.isEnabled())

    def test_stop_local_student_dispatches_worker(self):
        page = self.window.pages["studentproc"]
        page.set_processes([{"pid": 17600, "name": "StudentMain.exe", "ports": [4705]}])
        with (
            patch.object(self.window, "_begin_task") as begin_task,
            patch.object(self.window, "thread", None),
            patch.object(
                core,
                "stop_student_processes",
                return_value=[{"pid": 17600, "success": True}],
            ) as stop,
        ):
            self.window.stop_local_student()
            worker = begin_task.call_args.args[1]
            self.assertEqual(begin_task.call_args.args[0], "studentproc")
            worker.run()
        # 后台任务会额外传入进度回调，这里只核对结束的进程号。
        self.assertEqual(stop.call_args.args, ([17600],))

    def test_app_command_page_covers_new_operations(self):
        page = self.window.pages["appcmd"]
        codes = [
            page.operation_box.itemData(index)
            for index in range(page.operation_box.count())
        ]
        self.assertEqual(page.forms.count(), len(codes))
        page.operation_box.setCurrentIndex(codes.index("rename"))
        page.rename_input.setText("2-01")
        delivery = page.delivery()
        self.assertEqual(delivery["name"], "修改显示名")
        self.assertEqual(delivery["channel"], "comd")
        page.lcmd_input.setChecked(True)
        self.assertEqual(page.delivery()["channel"], "lcmd")
        page.operation_box.setCurrentIndex(codes.index("lock"))
        self.assertEqual(page.delivery()["payload"][8:12], bytes([10, 0, 0, 0]))
        page.operation_box.setCurrentIndex(codes.index("unlock-screen"))
        self.assertEqual(page.delivery()["payload"][12:16], bytes(4))
        page.operation_box.setCurrentIndex(codes.index("password"))
        page.password_input.setText("1234")
        self.assertEqual(page.delivery()["payload"][8:12], bytes([11, 0, 0, 0]))
        page.operation_box.setCurrentIndex(codes.index("rename"))
        page.rename_input.setText("   ")
        with self.assertRaises(ValueError):
            page.delivery()

    def test_screen_view_maps_click_into_remote_coordinates(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QPixmap as Pixmap

        from app.gui.screen_window import ScreenView

        class Stub:
            """只为接收转发调用，不需要真实的远控通道。"""

            def __init__(self):
                self.mouse = []

            def send_mouse(self, action, x, y, data=0):
                self.mouse.append((action, x, y, data))

            def send_key(self, event, key_up):
                pass

        stub = Stub()
        view = ScreenView(stub, None)
        view.resize(800, 600)
        pixmap = Pixmap(400, 200)
        pixmap.fill(QColor("#000000"))
        view.setPixmap(pixmap)
        area = view.image_rect()
        # 400x200 的画面按比例放进 800x600，上下各留 100 像素黑边。
        self.assertEqual(area.width(), 800)
        self.assertEqual(area.height(), 400)
        self.assertEqual(area.y(), 100)

        # 中心点应落在坐标范围的正中间附近，取整方式不同会有几十的偏差。
        point = view.normalized(area.center())
        self.assertTrue(32000 <= point[0] <= 33500, point)
        self.assertTrue(32000 <= point[1] <= 33500, point)
        # 落在黑边上的点不产生坐标。
        self.assertIsNone(view.normalized(QPoint(area.center().x(), 10)))

    def test_screen_window_forwards_input_only_after_takeover(self):
        from app.gui.screen_window import ScreenWindow

        window = ScreenWindow("10.1.1.5")
        self.addCleanup(self.dispose_widget, window)
        window.control = None
        window.send_mouse("move", 1, 1)
        self.assertIsNone(window.control)
        control = MagicMock()
        control.port = 55120
        window.control = control
        window.send_mouse("leftdown", 100, 200)
        control.mouse.assert_called_once_with("leftdown", 100, 200, 0)
        self.assertEqual(window.control_button.text(), "接管键鼠")

    def png_bytes(self):
        """生成一张最小的 PNG，用来验证缩略图能真正解析成图片。"""
        image = QImage(8, 8, QImage.Format.Format_RGB32)
        image.fill(QColor("#0f6cbd"))
        buffer = QBuffer()
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(buffer.data())

    def test_home_page_lists_shortcuts_and_function_cards(self):
        home = self.window.pages["home"]
        self.assertEqual(home.objectName(), "home")
        self.assertEqual(
            list(home.shortcuts), ["aliases", "repository", "document", "feedback"]
        )
        # 功能卡片覆盖除首页、设置、关于与快捷入口以外的全部页面，点击即跳转。
        self.assertEqual(
            set(home.cards),
            set(self.window.pages) - {"home", "settings", "about", "aliases"},
        )
        self.assertEqual(home.cards["message"].objectName(), "homeCard_message")
        home.cards["logs"].clicked.emit()
        self.assertEqual(self.window.current_page(), "logs")

    def test_home_shortcut_opens_page_or_external_link(self):
        home = self.window.pages["home"]
        opened = []
        with patch.object(gui, "QDesktopServices") as desktop:
            desktop.openUrl.side_effect = lambda url: opened.append(url.toString())
            home.pageRequested.emit("repository")
            home.pageRequested.emit("file")
        self.assertEqual(opened, [gui.HOME_LINKS["repository"]])
        self.assertEqual(self.window.current_page(), "file")

    def test_dialog_centers_on_parent_and_falls_back_to_screen(self):
        parent = QWidget()
        parent.resize(1180, 780)
        parent.move(400, 200)
        parent.show()
        self.addCleanup(parent.deleteLater)
        QTest.qWait(10)
        dialog = Dialog("标题", "内容", parent)
        dialog.setFixedSize(520, 280)
        components.center_dialog(dialog)
        self.addCleanup(dialog.deleteLater)
        frame = parent.frameGeometry()
        expected = frame.center() - dialog.rect().center()
        self.assertEqual(dialog.pos(), expected)

        # 启动阶段没有主窗口，退回屏幕可用区域居中。
        screen = dialog.screen().availableGeometry()
        loose = Dialog("标题", "内容")
        loose.setFixedSize(560, 300)
        components.center_dialog(loose)
        self.addCleanup(loose.deleteLater)
        self.assertEqual(loose.pos(), screen.center() - loose.rect().center())

    def test_device_alias_can_be_added_edited_used_and_removed(self):
        page = self.window.pages["aliases"]
        self.assertEqual(
            page.info_button.toolTip(),
            "备注名可直接用作目标；支持 IPv4、末段范围和 /24，修改后同步引用。",
        )
        self.assertEqual(page.info_button.size().width(), 28)
        page.name_input.setText("教室 A")
        for edit, text in zip(
            page.address_input.segments, ("192", "168", "1", "10"), strict=True
        ):
            edit.setText(text)
        page.save_button.click()
        self.assertEqual(self.alias_store.match("教室 a"), ("教室 A", "192.168.1.10"))
        self.assertEqual(page.table.item(0, 1).text(), "192.168.1.10")

        page.table.setCurrentCell(0, 0)
        page.use_button.click()
        self.assertEqual(self.state.values["target"], "教室 A")
        self.assertEqual(self.state.resolve_target(), "192.168.1.10")
        self.assertIn("192.168.1.10", self.message.targets.alias_hint.text())

        page.edit_button.click()
        page.name_input.setText("一号机房")
        for edit, text in zip(
            page.address_input.segments, ("192", "168", "1", "11"), strict=True
        ):
            edit.setText(text)
        page.save_button.click()
        self.assertEqual(self.state.values["target"], "一号机房")
        self.assertEqual(
            self.alias_store.match("一号机房"), ("一号机房", "192.168.1.11")
        )
        self.assertEqual(self.message.targets.target_input.text(), "192.168.1.11")
        self.assertEqual(
            [edit.text() for edit in self.message.targets.target_input.segments],
            ["192", "168", "1", "11"],
        )

        page.table.setCurrentCell(0, 0)
        with patch.object(gui.Dialog, "exec", return_value=1):
            page.delete_button.click()
        self.assertIsNone(self.alias_store.match("一号机房"))
        self.assertEqual(self.state.values["target"], "")

    def test_device_alias_supports_ranges_and_is_persisted(self):
        page = self.window.pages["aliases"]
        page.name_input.setText("机房范围")
        for edit, text in zip(
            page.address_input.segments, ("10", "0", "0", "1-10"), strict=True
        ):
            edit.setText(text)
        page.save_button.click()
        self.assertEqual(
            self.alias_store.match("机房范围"), ("机房范围", "10.0.0.1-10")
        )
        self.assertEqual(page.table.item(0, 1).text(), "10.0.0.1-10")

        reloaded = gui.DeviceAliasStore(
            settings=models.portable_settings(self.data_dir)
        )
        self.assertEqual(reloaded.match("机房范围"), ("机房范围", "10.0.0.1-10"))
        self.state.set_value("target", "机房范围")
        options = self.window._options_for_page("message")
        self.assertEqual(options.target, "10.0.0.1-10")
        self.assertEqual(self.message.targets.target_count.text(), "10 个目标")

    def test_alias_address_advances_on_enter_and_enters_four_segments(self):
        page = self.window.pages["aliases"]
        self.window.show()
        self.window.show_page("aliases")
        self.application.processEvents()
        page.name_input.setFocus()
        page.name_input.setText("回车设备")
        QTest.keyClick(page.name_input, Qt.Key_Return)
        self.application.processEvents()
        self.assertTrue(page.address_input.segments[0].hasFocus())
        for index, text in enumerate(("10", "1", "2")):
            page.address_input.segments[index].setText(text)
            QTest.keyClick(page.address_input.segments[index], Qt.Key_Return)
            self.application.processEvents()
        self.assertTrue(page.address_input.segments[3].hasFocus())
        page.address_input.segments[3].setText("20")
        QTest.keyClick(page.address_input.segments[3], Qt.Key_Return)
        self.application.processEvents()
        self.assertEqual(self.alias_store.match("回车设备"), ("回车设备", "10.1.2.20"))

    def test_portable_paths_are_based_on_executable_directory(self):
        executable = Path(self.temp_root) / "portable" / "JiYuAttackNext.exe"
        data_dir = models.portable_data_dir(executable)
        self.assertEqual(
            data_dir, executable.parent.resolve() / models.DATA_DIRECTORY_NAME
        )
        self.assertEqual(
            models.portable_log_path(data_dir), data_dir / models.LOG_FILE_NAME
        )
        self.assertTrue(
            models.portable_settings(data_dir)
            .file_name()
            .endswith(models.SETTINGS_FILE_NAME)
        )

    def test_settings_json_keeps_core_and_gui_groups(self):
        self.alias_store.add("配置分组", "10.0.0.9")
        self.window.set_close_behavior(models.CLOSE_BEHAVIOR_QUIT)
        path = self.data_dir / models.SETTINGS_FILE_NAME
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("// "))
        data = core.config.loads(text)
        self.assertEqual(data["core"]["device_aliases"], {"配置分组": "10.0.0.9"})
        self.assertEqual(
            data["gui"]["window"]["close_behavior"], models.CLOSE_BEHAVIOR_QUIT
        )
        self.assertIn("gui", data)
        self.assertIn("core", data)

    def test_settings_json_accepts_handwritten_comments(self):
        path = self.data_dir / models.SETTINGS_FILE_NAME
        self.alias_store.add("手写注释", "10.0.0.8")
        text = path.read_text(encoding="utf-8")
        edited = text.replace(
            '"core": {',
            "// 手写的分组说明" + chr(10) + '  "core": {',
            1,
        )
        path.write_text(edited, encoding="utf-8")
        reloaded = models.SettingsStore(path)
        self.assertEqual(reloaded.status(), models.STATUS_NO_ERROR)
        self.assertEqual(
            reloaded.value(models.DEVICE_ALIAS_SETTINGS_KEY),
            {"手写注释": "10.0.0.8"},
        )

    def test_dialogs_use_application_icon(self):
        self.assertFalse(self.application.windowIcon().isNull())
        dialog = Dialog("标题", "内容")
        try:
            self.assertFalse(dialog.windowIcon().isNull())
            self.assertEqual(
                dialog.windowIcon().pixmap(16, 16).toImage(),
                self.application.windowIcon().pixmap(16, 16).toImage(),
            )
        finally:
            dialog.deleteLater()

    def test_runtime_logs_are_persisted_and_loaded(self):
        self.window.logs.clear()
        self.window.logs.add("应用", "第一行\n第二行", "成功")
        log_path = self.data_dir / models.LOG_FILE_NAME
        self.assertTrue(log_path.exists())
        text = log_path.read_text(encoding="utf-8")
        self.assertIn(" INFO    ", text)
        self.assertIn("[应用] 第一行", text)
        self.assertIn("    第二行", text)
        reloaded = models.LogStore(log_path=log_path)
        self.assertEqual(reloaded.entries[-1].message, "第一行\n第二行")
        self.assertEqual(reloaded.entries[-1].level, models.LogLevel.INFO)
        self.assertGreater(reloaded.entries[-1].line_number, 0)
        self.assertTrue(reloaded.entries[-1].logger_name.endswith(".GuiTests"))
        self.window.logs.clear()
        self.assertEqual(log_path.read_text(encoding="utf-8"), "")

    def test_target_has_four_ipv4_segments_and_manual_address_still_works(self):
        targets = self.message.targets
        self.assertEqual(targets.device_button.text(), "选择设备")
        self.assertEqual(targets.device_button.parentWidget(), targets)
        self.assertEqual(len(targets.target_input.segments), 4)
        for edit, text in zip(
            targets.target_input.segments, ("192", "168", "1", "20"), strict=True
        ):
            edit.setText(text)
        self.assertEqual(targets.target_input.text(), "192.168.1.20")
        self.assertEqual(self.state.values["target"], "192.168.1.20")
        self.assertEqual(targets.target_count.text(), "1 个目标")

    def test_ipv4_segments_advance_on_enter_and_accept_last_segment_forms(self):
        targets = self.message.targets
        segments = targets.target_input.segments
        self.window.show()
        self.window.show_page("message")
        self.application.processEvents()
        segments[0].setFocus()
        for edit, text in zip(segments[:3], ("10", "49", "151"), strict=True):
            edit.setText(text)
            QTest.keyClick(edit, Qt.Key_Return)
            self.application.processEvents()
        self.assertTrue(segments[3].hasFocus())
        segments[3].setText("1-10")
        self.assertEqual(self.state.values["target"], "10.49.151.1-10")
        self.assertEqual(targets.target_count.text(), "10 个目标")
        segments[3].setText("0/24")
        self.assertEqual(self.state.values["target"], "10.49.151.0/24")
        self.assertEqual(targets.target_count.text(), "254 个目标")
        QTest.keyClick(segments[3], Qt.Key_Return)
        self.application.processEvents()
        self.assertTrue(targets.port_input.hasFocus())

    def test_ipv4_segments_advance_on_dot_key(self):
        targets = self.message.targets
        segments = targets.target_input.segments
        self.window.show()
        self.window.show_page("message")
        self.application.processEvents()
        segments[0].setFocus()
        for edit, text in zip(segments[:3], ("10", "49", "151"), strict=True):
            edit.setText(text)
            QTest.keyClick(edit, Qt.Key_Period)
            self.application.processEvents()
        self.assertTrue(segments[3].hasFocus())
        # 点号只用于跳段，不进入输入框，四段仍是纯数字。
        self.assertEqual([edit.text() for edit in segments[:3]], ["10", "49", "151"])
        segments[3].setText("7")
        self.assertEqual(self.state.values["target"], "10.49.151.7")
        # 回车行为保持不变：最后一段回车进入端口输入框。
        QTest.keyClick(segments[3], Qt.Key_Return)
        self.application.processEvents()
        self.assertTrue(targets.port_input.hasFocus())

    def test_device_picker_lists_aliases_and_selects_target(self):
        self.alias_store.add("教室 A", "192.168.1.10")
        self.alias_store.add("一号机房", "192.168.1.11")
        targets = self.message.targets
        dialog, selector = targets._create_device_dialog()
        try:
            self.assertEqual(selector.count(), 2)
            self.assertEqual(selector.itemData(0), "教室 A")
            self.assertEqual(selector.itemText(1), "一号机房  ·  192.168.1.11")
        finally:
            dialog.deleteLater()
        targets.state.set_value("target", "一号机房")
        self.assertEqual(targets.target_input.text(), "192.168.1.11")
        self.assertEqual(
            [edit.text() for edit in targets.target_input.segments],
            ["192", "168", "1", "11"],
        )
        self.assertIn("192.168.1.11", targets.alias_hint.text())

    def test_device_picker_handles_no_aliases(self):
        targets = self.message.targets
        with patch.object(components.Dialog, "exec", return_value=1) as execute:
            targets.choose_device()
        execute.assert_called_once()
        self.assertEqual(self.state.values["target"], "")

    def test_connection_fields_are_shared_between_pages(self):
        self.command.targets.target_input.setText("10.0.0.8")
        self.message.targets.port_input.setValue(8800)
        self.device.targets.loop_input.setValue(3)
        self.command.targets.interval_input.setValue(0.5)
        for page in self.window.network_pages:
            self.assertEqual(page.targets.target_input.text(), "10.0.0.8")
            self.assertEqual(
                [edit.text() for edit in page.targets.target_input.segments],
                ["10", "0", "0", "8"],
            )
            self.assertEqual(page.targets.port_input.value(), 8800)
            self.assertEqual(page.targets.loop_input.value(), 3)
            self.assertEqual(page.targets.interval_input.value(), 0.5)
            self.assertTrue(page.targets.interval_input.isEnabled())

    def test_interval_is_disabled_for_single_round(self):
        self.assertFalse(self.message.targets.interval_input.isEnabled())
        self.state.set_value("loops", 2)
        self.assertTrue(self.message.targets.interval_input.isEnabled())
        self.state.set_value("loops", 1)
        self.assertFalse(self.message.targets.interval_input.isEnabled())

    def test_message_and_command_statistics(self):
        self.message.editor.setPlainText("a" * 449)
        self.assertIn("2 条报文", self.message.statistics.text())
        self.command.editor.setPlainText("中文")
        self.assertIn("2 / 163", self.command.statistics.text())

    def test_each_page_only_sends_its_own_payload(self):
        self.message.editor.setPlainText("通知")
        self.command.editor.setPlainText("whoami")
        self.device.shutdown.setChecked(True)
        message = self.window._options_for_page("message")
        command = self.window._options_for_page("command")
        device = self.window._options_for_page("device")
        self.assertEqual(
            (message.message, message.command, message.extra), ("通知", "", "")
        )
        self.assertEqual(
            (command.message, command.command, command.extra), ("", "whoami", "")
        )
        self.assertEqual((device.message, device.command, device.extra), ("", "", "s"))
        self.assertFalse(self.device.reboot.isChecked())
        self.device.logoff.setChecked(True)
        self.assertEqual(self.device.action(), "l")
        self.assertEqual(self.device.footer.send_button.text(), "执行注销")
        self.assertEqual(self.window._options_for_page("device").extra, "l")

    def test_target_preview_is_local_parsing_only(self):
        with patch.object(
            gui.core, "get_ip", return_value=["模拟目标甲", "模拟目标乙"]
        ):
            self.state.set_value("target", "模拟范围")
        self.assertEqual(self.device.preview.rowCount(), 2)
        self.assertEqual(self.device.preview.item(1, 0).text(), "模拟目标乙")
        self.assertEqual(self.device.preview.item(1, 1).text(), "4705")

    def test_footer_and_numeric_text_fit_at_minimum_size(self):
        self.window.resize(960, 640)
        self.window.show()
        self.application.processEvents()
        for page in self.window.task_pages:
            self.window.show_page(page.objectName())
            self.application.processEvents()
            for button in [page.footer.send_button, page.footer.cancel_button]:
                if button.isHidden():
                    continue
                point = button.mapTo(self.window, button.rect().center())
                self.assertTrue(self.window.rect().contains(point))
        self.window.show_page("message")
        self.application.processEvents()
        for spin in [
            self.message.targets.port_input,
            self.message.targets.loop_input,
            self.message.targets.interval_input,
        ]:
            self.assertGreater(spin.lineEdit().width(), 30)
        self.message.targets.port_input.setValue(65535)
        self.message.targets.loop_input.setValue(10000)
        self.application.processEvents()
        self.assertGreater(self.message.targets.port_input.lineEdit().width(), 30)
        self.assertEqual(self.message.targets.port_input.lineEdit().text(), "65535")

    def test_target_and_device_picker_do_not_overlap_at_narrow_widths(self):
        self.window.show()
        self.window.show_page("message")
        for width in (1050, 960):
            self.window.resize(width, 640)
            QTest.qWait(300)
            self.application.processEvents()
            targets = self.message.targets
            self.assertLess(
                targets.target_input.geometry().right(),
                targets.device_button.geometry().left(),
                "窗口宽度 %d 时目标地址与选择设备按钮重叠" % width,
            )

    def test_invalid_target_does_not_start_worker(self):
        self.message.footer.send_button.click()
        self.assertIsNone(self.window.thread)
        self.assertTrue(self.message.targets.target_input.segments[-1].isError())
        self.assertIn("目标地址", self.message.footer.status.text())

    def test_oversized_command_is_rejected_before_worker(self):
        self.state.set_value("target", "192.168.1.10")
        self.command.editor.setPlainText("a" * 164)
        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            self.window.start_send("command")
        self.assertIsNone(self.window.thread)
        self.assertIn("超过报文容量", self.command.footer.status.text())

    def test_file_page_selects_file_and_starts_transfer(self):
        page = self.window.pages["file"]
        self.assertEqual(page.objectName(), "file")
        self.assertEqual(page.targets.loop_input.isVisibleTo(page), False)
        source = self.temp_root / "报告.txt"
        source.write_text("测试文件", encoding="utf-8")
        page.set_file(source)
        self.state.set_value("target", "192.168.1.10")
        self.assertEqual(page.selected_items(), [(str(source.resolve()), "报告.txt")])

        def fake_transfer(
            target,
            port,
            path,
            listen_ip,
            timeout,
            cancel_event=None,
            report=None,
            items=None,
        ):
            report("目标正在下载文件：50%")
            report("目标正在下载文件：100%")
            return {
                "name": "报告.txt",
                "size": 8,
                "target": target,
                "listen_ip": listen_ip,
                "file_count": 1,
            }

        with (
            patch.object(gui.core, "get_ip", return_value=["模拟目标"]),
            patch.object(
                gui.core, "transfer_file", side_effect=fake_transfer
            ) as transfer,
        ):
            self.window.start_file_transfer()
            self.wait_for(lambda: self.window.thread is None)
        transfer.assert_called_once()
        self.assertEqual(
            transfer.call_args.kwargs["items"], [(str(source.resolve()), "报告.txt")]
        )
        self.assertEqual(page.progress.value(), 100)
        self.assertIn("文件已传送到目标桌面", page.footer.status.text())
        self.assertEqual(self.window.logs.entries[-1].category, "文件传送")
        self.assertEqual(self.window.logs.entries[-1].level, models.LogLevel.INFO)

    def test_file_transfer_confirmation_is_active_and_responsive(self):
        page = self.window.pages["file"]
        source = self.temp_root / "确认测试.txt"
        source.write_text("确认测试", encoding="utf-8")
        page.set_file(source)
        self.state.set_value("target", "192.168.1.10")
        dialogs = []

        def click_dialog(button_name):
            modal = QApplication.activeModalWidget()
            dialog = modal or next(
                (
                    widget
                    for widget in self.window.findChildren(QDialog)
                    if widget.isVisible()
                ),
                None,
            )
            dialogs.append((dialog, modal is dialog))
            if dialog is not None:
                QTest.mouseClick(getattr(dialog, button_name), Qt.LeftButton)

        self.window.show()
        self.window.activateWindow()
        self.window.raise_()
        QTest.qWait(200)
        self.confirm_patcher.stop()
        try:
            with (
                patch.object(gui.core, "get_ip", return_value=["模拟目标"]),
                patch.object(
                    gui.core,
                    "transfer_file",
                    return_value={
                        "name": source.name,
                        "size": source.stat().st_size,
                        "target": "模拟目标",
                        "listen_ip": "127.0.0.1",
                        "file_count": 1,
                    },
                ) as transfer,
            ):
                QTimer.singleShot(150, lambda: click_dialog("yesButton"))
                self.window.start_file_transfer()
                self.wait_for(lambda: self.window.thread is None)
            transfer.assert_called_once()
            with (
                patch.object(gui.core, "get_ip", return_value=["模拟目标"]),
                patch.object(gui.core, "transfer_file") as cancelled_transfer,
            ):
                QTimer.singleShot(150, lambda: click_dialog("cancelButton"))
                self.window.start_file_transfer()
                self.assertIsNone(self.window.thread)
            cancelled_transfer.assert_not_called()
        finally:
            self.confirm_patcher.start()
        self.assertEqual(len(dialogs), 2)
        for dialog, active in dialogs:
            self.assertIsNotNone(dialog)
            self.assertTrue(active)
            self.assertEqual(dialog.yesButton.text(), "确认执行")
            self.assertEqual(dialog.cancelButton.text(), "取消")
        self.assertIn("文件已传送到目标桌面", page.footer.status.text())

    def test_file_page_shows_tree_with_checkboxes_and_select_all(self):
        page = self.window.pages["file"]
        folder = self.temp_root / "课件"
        (folder / "第二章").mkdir(parents=True)
        (folder / "说明.txt").write_text("说明", encoding="utf-8")
        (folder / "第二章" / "示例.docx").write_text("示例", encoding="utf-8")
        single = self.temp_root / "通知.txt"
        single.write_text("通知", encoding="utf-8")
        page.add_paths([folder, single])
        self.assertEqual(len(page.items), 3)
        self.assertEqual(page.tree.topLevelItemCount(), 2)
        self.assertEqual(
            page.selected_items(),
            [
                (
                    str((folder / "第二章" / "示例.docx").resolve()),
                    "课件/第二章/示例.docx",
                ),
                (str((folder / "说明.txt").resolve()), "课件/说明.txt"),
                (str(single.resolve()), "通知.txt"),
            ],
        )
        self.assertEqual(page.select_all_checkbox.checkState(), Qt.Checked)
        self.assertTrue(page.footer.send_button.isEnabled())
        self.assertTrue(page.delete_button.isEnabled())
        self.assertIn("3 个文件", page.count_label.text())
        self.assertEqual(page.tree.columnCount(), 3)
        self.assertEqual(FileTreeHeader.CHECKBOX_SIZE, 16)
        self.assertEqual(CompactHeaderCheckBox.INDICATOR_SIZE, 16)
        self.assertEqual(CompactTreeItemDelegate.CHECKBOX_SIZE, 16)
        self.assertEqual(page.tree.headerItem().text(0), "名称")
        self.assertEqual(page.select_all_checkbox.size().width(), 16)
        self.assertEqual(page.select_all_checkbox.size().height(), 16)
        self.assertEqual(
            page.select_all_checkbox.objectName(), "fileTreeSelectAllCheckbox"
        )
        self.assertIs(page.info_button.parent(), page)
        self.assertEqual(
            page.info_button.toolTip(),
            "勾选项发送到目标桌面并保留文件夹结构；目标需支持远程命令和 curl。",
        )
        self.assertEqual(page.info_button.size().width(), 28)
        self.assertEqual(page.info_button.size().height(), 28)
        self.assertTrue(
            all(
                Qt.CheckState(item.data(0, Qt.CheckStateRole)) == Qt.Checked
                and item.icon(0).isNull()
                for item in page._file_items()
            )
        )

        page.select_all_checkbox.click()
        self.assertEqual(page.selected_items(), [])
        self.assertFalse(page.footer.send_button.isEnabled())
        self.assertFalse(page.delete_button.isEnabled())
        self.assertEqual(page.delete_button.toolTip(), "删除选中文件")

        page.select_all_checkbox.click()
        self.assertEqual(len(page.selected_items()), 3)

        folder_item = page.tree.topLevelItem(0)
        self.assertEqual(folder_item.text(0), "课件")
        folder_item.setCheckState(0, Qt.Unchecked)
        self.assertEqual(page.selected_items(), [(str(single.resolve()), "通知.txt")])
        self.assertEqual(page.select_all_checkbox.checkState(), Qt.PartiallyChecked)
        self.assertIsNone(folder_item.data(0, Qt.CheckStateRole))
        self.assertFalse(folder_item.icon(0).isNull())
        folder_item.setCheckState(0, Qt.Checked)
        self.assertEqual(len(page.selected_items()), 3)
        self.assertEqual(page.select_all_checkbox.checkState(), Qt.Checked)

    def test_page_info_buttons_show_fluent_tooltip_on_hover(self):
        for key in ("file", "aliases"):
            self.window.show_page(key)
            self.window.show()
            QTest.qWait(80)
            button = self.window.pages[key].info_button
            self.hover(button, button.rect().center())
            QTest.qWait(400)
            visible_tips = [
                widget
                for widget in QApplication.topLevelWidgets()
                if isinstance(widget, ToolTip) and widget.isVisible()
            ]
            self.assertTrue(
                any(tip.text() == button.toolTip() for tip in visible_tips), key
            )
            self.leave(button)

    def test_file_tree_toggles_icon_and_checkbox_on_hover(self):
        page = self.window.pages["file"]
        path = self.temp_root / "hover.txt"
        path.write_text("hover", encoding="utf-8")
        folder = self.temp_root / "hover-folder"
        folder.mkdir()
        (folder / "nested.txt").write_text("nested", encoding="utf-8")
        page.add_paths([path, folder])
        item = next(
            item
            for item in page._file_items()
            if item.data(0, Qt.UserRole)[1] == "hover.txt"
        )
        item.setCheckState(0, Qt.Unchecked)
        self.assertIsNone(item.data(0, Qt.CheckStateRole))
        self.assertFalse(item.icon(0).isNull())

        folder_item = next(
            item
            for item in page._all_visible_items()
            if item.data(0, Qt.UserRole) == ("dir", "hover-folder")
        )
        folder_item.setCheckState(0, Qt.Unchecked)
        self.assertIsNone(folder_item.data(0, Qt.CheckStateRole))
        self.assertFalse(folder_item.icon(0).isNull())

        self.window.show_page("file")
        self.window.show()
        QTest.qWait(200)
        rect = page.tree.visualItemRect(item)
        hover_pos = QPoint(rect.x() + 32, rect.center().y())
        self.hover(page.tree.viewport(), hover_pos)
        self.assertEqual(item.checkState(0), Qt.Unchecked)
        self.assertEqual(item.data(0, Qt.CheckStateRole), Qt.Unchecked.value)
        self.assertTrue(item.icon(0).isNull())

        checkbox_pos = QPoint(rect.x() + 32, rect.center().y())
        QTest.mouseClick(page.tree.viewport(), Qt.LeftButton, pos=checkbox_pos)
        QTest.qWait(150)
        self.assertEqual(item.checkState(0), Qt.Checked)
        self.leave(page.tree.viewport())
        self.assertEqual(item.data(0, Qt.CheckStateRole), Qt.Checked.value)
        self.assertTrue(item.icon(0).isNull())

        item.setCheckState(0, Qt.Unchecked)
        self.leave(page.tree.viewport())
        self.assertIsNone(item.data(0, Qt.CheckStateRole))
        self.assertFalse(item.icon(0).isNull())

        folder_rect = page.tree.visualItemRect(folder_item)
        folder_pos = QPoint(folder_rect.x() + 32, folder_rect.center().y())
        self.hover(page.tree.viewport(), folder_pos)
        self.assertEqual(folder_item.data(0, Qt.CheckStateRole), Qt.Unchecked.value)
        self.assertTrue(folder_item.icon(0).isNull())
        self.leave(page.tree.viewport())
        self.assertIsNone(folder_item.data(0, Qt.CheckStateRole))
        self.assertFalse(folder_item.icon(0).isNull())

        folder_item.setCheckState(0, Qt.Checked)
        self.leave(page.tree.viewport())
        self.assertEqual(folder_item.checkState(0), Qt.Checked)
        self.assertEqual(folder_item.data(0, Qt.CheckStateRole), Qt.Checked.value)
        self.assertTrue(folder_item.icon(0).isNull())

    def test_file_page_deletes_selected_tree_items_only(self):
        page = self.window.pages["file"]
        folder = self.temp_root / "素材"
        folder.mkdir()
        (folder / "a.bin").write_bytes(b"a")
        (folder / "b.bin").write_bytes(b"b")
        single = self.temp_root / "保留.txt"
        single.write_text("保留", encoding="utf-8")
        page.add_paths([folder, single])
        folder_item = page.tree.topLevelItem(0)
        folder_item.setCheckState(0, Qt.Unchecked)
        for index in range(page.tree.topLevelItemCount()):
            item = page.tree.topLevelItem(index)
            if item.text(0) == "保留.txt":
                item.setCheckState(0, Qt.Checked)
        removed = page.remove_selected()
        self.assertEqual([relative for _, relative, _ in removed], ["保留.txt"])
        self.assertEqual(
            [relative for _, relative, _ in page.items], ["素材/a.bin", "素材/b.bin"]
        )
        self.assertTrue((single).exists())
        self.assertTrue(page.has_files())

        page.select_all_checkbox.click()
        removed = page.remove_selected()
        self.assertEqual(len(removed), 2)
        self.assertFalse(page.has_files())
        self.assertFalse(page.tree.isVisibleTo(page))
        self.assertFalse(page.footer.send_button.isEnabled())

    def test_file_transfer_sends_only_checked_files(self):
        page = self.window.pages["file"]
        folder = self.temp_root / "选中测试"
        folder.mkdir()
        (folder / "a.txt").write_text("a", encoding="utf-8")
        (folder / "b.txt").write_text("bb", encoding="utf-8")
        page.add_paths([folder])
        folder_item = page.tree.topLevelItem(0)
        for index in range(folder_item.childCount()):
            child = folder_item.child(index)
            child.setCheckState(
                0, Qt.Checked if child.text(0) == "b.txt" else Qt.Unchecked
            )
        self.state.set_value("target", "192.168.1.10")
        captured = {}

        def fake_transfer(
            target,
            port,
            path,
            listen_ip,
            timeout,
            cancel_event=None,
            report=None,
            items=None,
        ):
            captured["items"] = items
            return {
                "name": "1 个文件",
                "size": 2,
                "target": target,
                "listen_ip": listen_ip,
                "file_count": 1,
            }

        with (
            patch.object(gui.core, "get_ip", return_value=["模拟目标"]),
            patch.object(
                gui.core, "transfer_file", side_effect=fake_transfer
            ) as transfer,
        ):
            self.window.start_file_transfer()
            self.wait_for(lambda: self.window.thread is None)
        transfer.assert_called_once()
        self.assertEqual(
            captured["items"], [(str((folder / "b.txt").resolve()), "选中测试/b.txt")]
        )
        self.assertIn("1 个文件", page.footer.status.text())

    def test_file_transfer_requires_checked_tree_items(self):
        page = self.window.pages["file"]
        self.window.start_file_transfer()
        self.assertIsNone(self.window.thread)
        self.assertIn("请先选择要传送的文件", page.footer.status.text())
        source = self.temp_root / "未勾选.txt"
        source.write_text("未勾选", encoding="utf-8")
        page.set_file(source)
        page.select_all_checkbox.click()
        self.window.start_file_transfer()
        self.assertIsNone(self.window.thread)
        self.assertIn("请勾选要传送的文件或文件夹", page.footer.status.text())

    def test_file_page_requires_file_and_accepts_target_range(self):
        page = self.window.pages["file"]
        self.window.start_file_transfer()
        self.assertIsNone(self.window.thread)
        self.assertIn("请先选择要传送的文件", page.footer.status.text())
        source = self.temp_root / "报告.txt"
        source.write_text("测试文件", encoding="utf-8")
        page.set_file(source)
        self.state.set_value("target", "192.168.1.1-2")

        requested = []

        def fake_transfer(
            target,
            port,
            path,
            listen_ip,
            timeout,
            cancel_event=None,
            report=None,
            items=None,
        ):
            requested.append(target)
            report("目标 1/2（192.168.1.1）正在下载文件：100%")
            return {
                "name": source.name,
                "size": source.stat().st_size,
                "target": target,
                "targets": ["192.168.1.1", "192.168.1.2"],
                "transferred": ["192.168.1.1", "192.168.1.2"],
                "listen_ip": "127.0.0.1",
                "port": None,
                "file_count": 1,
            }

        with patch.object(
            gui.core, "transfer_file", side_effect=fake_transfer
        ) as transfer:
            self.window.start_file_transfer()
            self.wait_for(lambda: self.window.thread is None)
        transfer.assert_called_once()
        self.assertEqual(requested, ["192.168.1.1-2"])
        self.assertIn("2 个目标桌面", page.footer.status.text())
        self.assertEqual(page.progress.value(), 100)
        self.assertEqual(self.window.logs.entries[-1].level, models.LogLevel.INFO)

    def test_worker_completes_and_reenables_controls(self):
        self.state.set_value("target", "192.168.1.10")
        self.message.editor.setPlainText("测试通知")

        def fake_send(options, report):
            report("模拟发送完成")
            return gui.core.SendOutcome(
                sent=2,
                deliveries=(
                    gui.core.Delivery("模拟目标", 2, gui.core.DeliveryState.DELIVERED),
                ),
            )

        with (
            patch.object(gui.core, "get_ip", return_value=["模拟目标"]),
            patch.object(
                gui.core, "execute_send_report", side_effect=fake_send
            ) as runner,
        ):
            self.message.footer.send_button.click()
            self.assertTrue(self.command.footer.send_button.isEnabled())
            self.assertIn("可继续加入队列", self.command.footer.status.text())
            self.wait_for(lambda: self.window.thread is None)
            runner.assert_called_once()
            self.assertEqual(runner.call_args.args[0].command, "")
        self.assertTrue(self.message.footer.send_button.isEnabled())
        self.assertFalse(self.message.footer.cancel_button.isEnabled())
        self.assertIn("已发送 2 个报文", self.message.footer.status.text())
        self.assertEqual(self.window.logs.entries[-1].level, models.LogLevel.INFO)

    def test_worker_reports_failed_targets(self):
        self.state.set_value("target", "192.168.1.10")
        self.message.editor.setPlainText("测试通知")

        def fake_send(options, report):
            return gui.core.SendOutcome(
                sent=1,
                deliveries=(
                    gui.core.Delivery(
                        "192.168.1.10",
                        1,
                        gui.core.DeliveryState.REJECTED,
                        "端口未响应",
                    ),
                ),
            )

        with (
            patch.object(gui.core, "get_ip", return_value=["模拟目标"]),
            patch.object(gui.core, "execute_send_report", side_effect=fake_send),
        ):
            self.message.footer.send_button.click()
            self.wait_for(lambda: self.window.thread is None)
        self.assertIn("失败 1 台", self.message.footer.status.text())
        self.assertEqual(self.window.logs.entries[-1].level, models.LogLevel.WARNING)
        self.assertEqual(self.notify.call_args.args[0], "部分目标失败")

    def test_remote_requests_are_queued_while_task_runs(self):
        self.state.set_value("target", "192.168.1.10")
        self.message.editor.setPlainText("第一条")
        started = Event()
        release = Event()
        calls = []

        def fake_send(options, report):
            calls.append(options.message)
            if len(calls) == 1:
                started.set()
                release.wait(5)
            return gui.core.SendOutcome(
                sent=1,
                deliveries=(
                    gui.core.Delivery("模拟目标", 1, gui.core.DeliveryState.DELIVERED),
                ),
            )

        with (
            patch.object(gui.core, "get_ip", return_value=["模拟目标"]),
            patch.object(gui.core, "execute_send_report", side_effect=fake_send),
        ):
            self.window.start_send("message")
            self.assertTrue(started.wait(2))
            self.message.editor.setPlainText("第二条")
            self.assertTrue(self.message.footer.send_button.isEnabled())
            self.window.start_send("message")
            self.assertEqual(len(self.window._task_queue), 1)
            self.assertIn("已加入队列", self.message.footer.status.text())
            release.set()
            self.wait_for(
                lambda: (
                    self.window.thread is None
                    and not self.window._task_queue
                    and len(calls) == 2
                )
            )
        self.assertEqual(calls, ["第一条", "第二条"])

    def test_cancel_also_drops_queued_remote_requests(self):
        self.state.set_value("target", "192.168.1.10")
        self.message.editor.setPlainText("第一条")
        started = Event()
        release = Event()
        calls = []

        def fake_send(options, report):
            calls.append(options.message)
            started.set()
            release.wait(5)
            return gui.core.SendOutcome(
                sent=1,
                deliveries=(
                    gui.core.Delivery("模拟目标", 1, gui.core.DeliveryState.DELIVERED),
                ),
            )

        with (
            patch.object(gui.core, "get_ip", return_value=["模拟目标"]),
            patch.object(gui.core, "execute_send_report", side_effect=fake_send),
        ):
            self.window.start_send("message")
            self.assertTrue(started.wait(2))
            self.message.editor.setPlainText("第二条")
            self.window.start_send("message")
            self.assertEqual(len(self.window._task_queue), 1)
            self.window.cancel_task()
            self.assertEqual(self.window._task_queue, [])
            release.set()
            self.wait_for(lambda: self.window.thread is None)
        self.assertEqual(calls, ["第一条"])

    def test_worker_failure_is_reported_and_logged(self):
        self.state.set_value("target", "192.168.1.10")
        self.command.editor.setPlainText("whoami")
        with (
            patch.object(gui.core, "get_ip", return_value=["模拟目标"]),
            patch.object(
                gui.core, "execute_send_report", side_effect=OSError("模拟错误")
            ),
        ):
            self.window.start_send("command")
            self.wait_for(lambda: self.window.thread is None)
        self.assertIn("模拟错误", self.command.footer.status.text())
        self.assertEqual(self.window.logs.entries[-1].category, "远程命令")
        self.assertEqual(self.window.logs.entries[-1].level, models.LogLevel.ERROR)
        self.assertIn("OSError", self.window.logs.entries[-1].details)
        self.assertTrue(self.command.footer.send_button.isEnabled())

    def test_device_action_can_be_cancelled_in_confirmation(self):
        self.state.set_value("target", "192.168.1.10")
        self.confirm.return_value = False
        with patch.object(gui.core, "get_ip", return_value=["模拟目标"]):
            self.window.start_send("device")
        self.assertIsNone(self.window.thread)
        self.confirm.assert_called_once()

    def test_local_query_uses_background_task(self):
        with patch.object(
            gui, "probe_local", return_value=("模拟本机", ["4705"])
        ) as probe:
            self.window.start_local_probe()
            self.wait_for(lambda: self.window.thread is None)
        probe.assert_called_once()
        self.assertEqual(self.window.pages["local"].ip_label.text(), "模拟本机")
        self.assertEqual(self.window.pages["local"].port_table.rowCount(), 1)

    def test_apply_firewall_uses_on_demand_elevation(self):
        with patch.object(
            gui.core, "request_firewall_rule", return_value=[]
        ) as request:
            self.assertEqual(gui.apply_firewall("block"), [])
        request.assert_called_once_with("block")

    def test_firewall_result_preserves_failure_status(self):
        result = [("模拟规则", 1, "", "模拟失败")]
        with patch.object(gui, "apply_firewall", return_value=result) as apply:
            self.window.start_firewall()
            self.wait_for(lambda: self.window.thread is None)
        apply.assert_called_once()
        page = self.window.pages["firewall"]
        self.assertIn("失败", page.footer.status.text())
        self.assertEqual(page.result_table.item(0, 1).text(), "失败")

    def test_firewall_result_keeps_multiline_utf8_output_readable(self):
        page = self.window.pages["firewall"]
        page.set_result(
            [
                {
                    "command": "netsh advfirewall firewall set rule name=StudentMain.exe new action=block",
                    "code": 0,
                    "stdout": "已更新 6 规则。\n确定。",
                    "stderr": "",
                    "success": True,
                    "detail": "",
                }
            ]
        )
        self.assertEqual(page.result_table.item(0, 0).text(), "目标规则")
        self.assertEqual(page.result_table.item(0, 1).text(), "成功")
        self.assertEqual(page.result_table.item(0, 2).text(), "已更新 6 规则。\n确定。")

    def test_log_search_filter_export_and_clear(self):
        store = self.window.logs
        store.clear()
        store.add("文本消息", "第一条记录")
        store.add("远程命令", "第二条记录", "错误")
        page = self.window.pages["logs"]
        page.search.setText("第二条")
        self.assertTrue(page.table.isRowHidden(0))
        self.assertFalse(page.table.isRowHidden(1))
        self.assertEqual(len(page.export_text().splitlines()), 2)
        page.category.setCurrentIndex(2)
        self.assertTrue(page.table.isRowHidden(1))
        store.clear()
        self.assertEqual(page.table.rowCount(), 0)

    def test_log_page_controls_are_visible_at_minimum_size(self):
        self.window.resize(960, 640)
        self.window.show()
        QTest.qWait(120)
        page = self.window.pages["logs"]
        self.window.show_page("logs")
        QTest.qWait(120)
        for button in (
            page.select_all_checkbox,
            page.export_button,
            page.delete_button,
            page.level_filter,
        ):
            self.assertTrue(button.isVisible(), button.objectName() or button.text())
        self.assertIs(
            page.select_all_checkbox.parentWidget(),
            page.table.horizontalHeader().viewport(),
        )
        self.assertFalse(hasattr(page, "select_all_button"))
        self.assertFalse(hasattr(page, "runtime_level"))
        self.assertGreaterEqual(page.table.columnWidth(1), 180)
        self.assertGreaterEqual(page.table.columnWidth(2), 100)
        self.window.show_page("settings")
        QTest.qWait(120)
        settings = self.window.pages["settings"]
        # 正常版本可以调低到 INFO，DEBUG 不在可选集合里。
        self.assertTrue(settings.log_level_box.isEnabled())
        self.assertEqual(
            [
                settings.log_level_box.itemText(index)
                for index in range(settings.log_level_box.count())
            ],
            ["INFO", "WARNING", "ERROR"],
        )

    def test_uncaught_exception_is_written_to_runtime_log(self):
        previous_stderr = sys.stderr
        sys.stderr = io.StringIO()
        previous = gui.install_exception_logging(self.window.logs)
        try:
            try:
                raise RuntimeError("模拟未捕获异常")
            except RuntimeError:
                exception_type, exception, tb = sys.exc_info()
                gui.sys.excepthook(exception_type, exception, tb)
        finally:
            gui.sys.excepthook = previous
            sys.stderr = previous_stderr
        entry = self.window.logs.entries[-1]
        self.assertEqual(entry.level, models.LogLevel.ERROR)
        self.assertIn("模拟未捕获异常", entry.message)
        self.assertIn("RuntimeError", entry.details)

    def test_log_level_filter_selection_and_selected_export(self):
        store = self.window.logs
        store.clear()
        store.debug("应用", "调试记录")
        store.info("文本消息", "普通记录")
        store.warning("远程命令", "警告记录")
        store.error("设备操作", "错误记录")
        page = self.window.pages["logs"]
        self.assertEqual(page.table.rowCount(), 3)
        self.assertFalse(page.select_all_checkbox.isChecked())
        self.assertFalse(page.export_button.isEnabled())
        self.assertFalse(page.delete_button.isEnabled())
        self.assertEqual(page.export_button.toolTip(), "导出选中日志")
        self.assertEqual(page.delete_button.toolTip(), "删除选中日志")
        # 只认文案不认序号：可选等级随构建变体变化，序号会跟着漂。
        page.level_filter.setCurrentIndex(page.level_filter.findText("WARNING"))
        self.assertTrue(page.table.isRowHidden(0))
        self.assertFalse(page.table.isRowHidden(1))
        self.assertTrue(page.table.isRowHidden(2))
        page.level_filter.setCurrentIndex(0)
        page.search.clear()
        self.assertEqual(page.selected_uids(), [])
        page.select_all_checkbox.click()
        self.assertTrue(page.select_all_checkbox.isChecked())
        self.assertEqual(len(page.selected_entries()), 3)
        self.assertTrue(page.export_button.isEnabled())
        self.assertTrue(page.delete_button.isEnabled())
        page.table.item(2, 0).setCheckState(Qt.Unchecked)
        self.assertFalse(page.select_all_checkbox.isChecked())
        self.assertEqual(len(page.selected_entries()), 2)
        exported = page.export_text(page.selected_entries())
        self.assertIn("普通记录", exported)
        self.assertIn("警告记录", exported)
        self.assertNotIn("错误记录", exported)
        page.select_all_checkbox.click()
        self.assertTrue(page.select_all_checkbox.isChecked())
        page.select_all_checkbox.click()
        self.assertFalse(page.select_all_checkbox.isChecked())
        self.assertEqual(page.selected_uids(), [])
        self.assertFalse(page.export_button.isEnabled())
        self.assertFalse(page.delete_button.isEnabled())

    def test_select_all_off_clears_rows_hidden_by_filter(self):
        store = self.window.logs
        store.clear()
        store.info("文本消息", "消息记录")
        store.error("远程命令", "命令记录")
        page = self.window.pages["logs"]
        page.category.setCurrentIndex(2)
        page.select_all_checkbox.click()
        self.assertEqual(len(page.selected_entries()), 1)
        page.category.setCurrentIndex(0)
        page.select_all_checkbox.click()
        self.assertEqual(len(page.selected_entries()), 2)
        page.select_all_checkbox.click()
        self.assertEqual(page.selected_uids(), [])

    def test_log_level_options_follow_build_variant(self):
        # 正常版本不提供 DEBUG，默认 WARNING；用例为了验证 INFO 记录放宽了默认值，
        # 这里只看构建变体给出的取值。
        self.assertEqual(core.loglevel.MINIMUM_LEVEL, "WARNING")
        self.assertEqual(
            [str(level) for level in models.LOG_LEVELS], ["INFO", "WARNING", "ERROR"]
        )
        self.assertFalse(core.loglevel.allows("DEBUG"))
        self.assertFalse(core.loglevel.allows("INFO"))
        self.assertTrue(core.loglevel.allows("WARNING"))
        store = models.LogStore(minimum_level="WARNING")
        self.assertIsNone(store.info("应用", "被过滤"))
        self.assertIsNotNone(store.warning("应用", "保留警告"))
        store.set_level("DEBUG")
        # 正常版本里 DEBUG 不在可选集合内，请求按最低可选等级处理。
        self.assertEqual(store.minimum_level, models.LogLevel.INFO)
        store.set_level("ERROR")
        self.assertEqual(store.minimum_level, models.LogLevel.ERROR)

    def test_cancelled_file_selection_is_logged(self):
        store = self.window.logs
        store.clear()
        with patch.object(gui.QFileDialog, "getOpenFileNames", return_value=("", "")):
            self.window.choose_transfer_files()
        self.assertEqual(store.entries[-1].category, "文件传送")
        self.assertEqual(store.entries[-1].level, models.LogLevel.INFO)
        self.assertEqual(store.entries[-1].message, "用户取消了文件选择")

    def test_busy_window_rejects_local_probe_with_warning(self):
        store = self.window.logs
        store.clear()
        # 直接占用线程句柄模拟正在执行的任务，避免真的启动后台线程。
        self.window.thread = object()
        try:
            self.window.start_local_probe()
        finally:
            self.window.thread = None
        self.assertEqual(store.entries[-1].level, models.LogLevel.WARNING)
        self.assertEqual(store.entries[-1].message, "已有任务在运行，本机查询未开始")

    def test_background_worker_records_debug_trace(self):
        store = self.window.logs
        store.clear()
        store._minimum_level = models.LogLevel.DEBUG
        try:
            worker = gui.TaskWorker(
                lambda report=None: 42, logs=store, category="本机信息"
            )
            worker.run()
        finally:
            store._minimum_level = models.LogLevel.INFO
        messages = [entry.message for entry in store.entries]
        self.assertIn("后台任务开始执行", messages)
        self.assertIn("后台任务执行完成", messages)
        self.assertTrue(all(entry.category == "本机信息" for entry in store.entries))

    def test_device_alias_actions_are_logged(self):
        store = self.window.logs
        page = self.window.pages["aliases"]
        store.clear()
        page.name_input.setText("日志备注")
        for index, segment in enumerate(("192", "168", "1", "20")):
            page.address_input.segments[index].setText(segment)
        page.save_button.click()
        self.assertEqual(store.entries[-1].level, models.LogLevel.INFO)
        self.assertEqual(store.entries[-1].message, "已添加备注「日志备注」")
        page.table.setCurrentCell(0, 0)
        with patch.object(gui.Dialog, "exec", return_value=1):
            page.delete_button.click()
        self.assertEqual(store.entries[-1].level, models.LogLevel.INFO)
        self.assertEqual(store.entries[-1].message, "已删除备注「日志备注」")

    def test_delete_selected_logs_removes_rows_and_rewrites_file(self):
        store = self.window.logs
        store.clear()
        first = store.info("应用", "保留记录")
        removed = store.error("应用", "删除记录")
        log_path = self.data_dir / models.LOG_FILE_NAME
        page = self.window.pages["logs"]
        row = page._row_by_uid[removed.uid]
        page.table.item(row, 0).setCheckState(Qt.Checked)
        self.window.delete_selected_logs([removed.uid])
        remaining_uids = [entry.uid for entry in store.entries]
        self.assertIn(first.uid, remaining_uids)
        self.assertNotIn(removed.uid, remaining_uids)
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("保留记录", text)
        self.assertNotIn("[应用] 删除记录", text)

    def test_legacy_json_log_is_loaded_and_migrated_on_next_write(self):
        log_path = self.data_dir / models.LOG_FILE_NAME
        legacy = {
            "time": "2026-01-02 03:04:05",
            "category": "应用",
            "level": "警告",
            "message": "旧格式记录",
        }
        log_path.write_text(
            json.dumps(legacy, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        store = models.LogStore(log_path=log_path)
        self.addCleanup(store.close)
        self.assertEqual(store.entries[0].level, models.LogLevel.WARNING)
        store.info("应用", "新格式记录")
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("WARNING", text)
        self.assertIn("INFO", text)
        self.assertIn("旧格式记录", text)
        reloaded = models.LogStore(log_path=log_path)
        self.addCleanup(reloaded.close)
        self.assertEqual(reloaded.entries[0].level, models.LogLevel.WARNING)

    def test_log_file_keeps_one_handle_and_flushes_each_line(self):
        log_path = self.data_dir / models.LOG_FILE_NAME
        store = models.LogStore(log_path=log_path)
        try:
            store.info("应用", "第一行")
            handle = store._file_handle
            self.assertIsNotNone(handle)
            store.info("应用", "第二行")
            # 同一个句柄跨条复用，且每条写完即可从磁盘读到。
            self.assertIs(store._file_handle, handle)
            self.assertFalse(handle.closed)
            text = log_path.read_text(encoding="utf-8")
            self.assertIn("[应用] 第一行", text)
            self.assertIn("[应用] 第二行", text)
        finally:
            store.close()
        self.assertIsNone(store._file_handle)

    def test_log_page_coalesces_scroll_requests_into_one(self):
        store = self.window.logs
        store.clear()
        page = self.window.pages["logs"]
        page._scroll_timer.stop()
        with patch.object(page.table, "scrollToBottom") as scroll:
            for index in range(30):
                store.info("应用", "滚动记录 %d" % index)
            # 定时器未触发前不会逐条滚动，一批追加只滚一次。
            self.assertEqual(scroll.call_count, 0)
            self.assertTrue(page._scroll_timer.isActive())
            self.application.processEvents()
            self.assertLessEqual(scroll.call_count, 1)

    def test_about_page_reuses_application_icon(self):
        about = self.show_about_page()
        pixmaps = [
            label.pixmap()
            for label in about.findChildren(QLabel)
            if not label.pixmap().isNull()
        ]
        self.assertTrue(pixmaps)
        expected = QApplication.windowIcon().pixmap(96, 96)
        self.assertEqual(pixmaps[0].toImage(), expected.toImage())

    def test_settings_show_close_behavior_above_log_level(self):
        settings_page = self.window.pages["settings"]
        self.assertFalse(hasattr(settings_page, "reset_button"))
        theme_layout = settings_page.theme_card.body
        self.assertEqual(theme_layout.itemAt(0).widget().text(), "界面主题")
        labels = []
        for index in range(1, theme_layout.count()):
            row = theme_layout.itemAt(index).layout()
            if row is not None:
                label = row.itemAt(0).widget()
                if isinstance(label, BodyLabel):
                    labels.append(label.text())
        self.assertEqual(labels, ["颜色模式", "窗口材质"])
        behavior_layout = settings_page.findChild(
            components.SectionCard, "settingsBehaviorCard"
        ).body
        labels = []
        for index in range(behavior_layout.count()):
            row = behavior_layout.itemAt(index).layout()
            if row is not None:
                label = row.itemAt(0).widget()
                if isinstance(label, BodyLabel):
                    labels.append(label.text())
        self.assertEqual(labels, ["关闭时最小化到托盘", "运行日志等级"])
        self.assertTrue(settings_page.close_behavior_switch.label.isHidden())
        self.assertEqual(settings_page.close_behavior_switch.label.text(), "")
        self.assertEqual(settings_page.data_card.objectName(), "settingsDataCard")
        self.assertTrue(settings_page.clear_data_button.isVisibleTo(settings_page))
        self.assertFalse(hasattr(self.window.pages["about"], "clear_data_button"))

    def test_window_material_reflects_support_and_persists(self):
        settings_page = self.window.pages["settings"]
        self.assertEqual(settings_page.theme_card.objectName(), "settingsThemeCard")
        self.assertEqual(
            settings_page.theme_card.borderRadius, components.CORNER_RADIUS
        )
        self.assertEqual(
            settings_page.material_box.itemText(0),
            models.WINDOW_MATERIAL_LABELS[models.MATERIAL_MICA],
        )
        self.assertEqual(settings_page.material_box.itemData(0), models.MATERIAL_MICA)
        self.assertEqual(self.window.window_material, models.DEFAULT_WINDOW_MATERIAL)
        self.assertTrue(settings_page.material_box.isEnabled())
        settings_page.material_box.setCurrentIndex(
            models.WINDOW_MATERIALS.index(models.MATERIAL_SOLID)
        )
        self.assertEqual(self.window.window_material, models.MATERIAL_SOLID)
        reloaded = models.portable_settings(self.data_dir)
        self.assertEqual(
            models.normalize_window_material(
                reloaded.value(models.WINDOW_MATERIAL_SETTINGS_KEY)
            ),
            models.MATERIAL_SOLID,
        )
        settings_page.material_box.setCurrentIndex(
            models.WINDOW_MATERIALS.index(models.MATERIAL_MICA)
        )
        self.assertEqual(self.window.window_material, models.MATERIAL_MICA)

    def test_legacy_blur_switch_maps_to_window_material(self):
        self.assertEqual(
            models.normalize_window_material(None, True), models.MATERIAL_MICA
        )
        self.assertEqual(
            models.normalize_window_material(None, False), models.MATERIAL_SOLID
        )
        self.assertEqual(
            models.normalize_window_material("acrylic", None), models.MATERIAL_ACRYLIC
        )
        self.assertEqual(
            models.normalize_window_material("unknown", None),
            models.DEFAULT_WINDOW_MATERIAL,
        )

    @unittest.skipUnless(sys.platform == "win32", "仅 Windows 提供窗口材质")
    def test_window_effect_applies_material_to_window(self):
        self.assertTrue(window_effect.apply_acrylic(self.window, False))
        window_effect.apply_acrylic(self.window, True)
        self.assertTrue(window_effect.apply_mica(self.window, False))
        self.assertTrue(window_effect.apply_mica(self.window, True))
        window_effect.clear_material(self.window)
        self.assertEqual(window_effect.acrylic_color(False, 0x00), "F5F6F800")
        self.assertEqual(window_effect.acrylic_color(True, 0x00), "20202000")
        self.assertEqual(window_effect.acrylic_color(False, 0x10), "F5F6F810")

    def test_window_effect_ignores_objects_without_dwm(self):
        self.assertFalse(window_effect.apply_acrylic(None, False))
        self.assertFalse(window_effect.apply_mica(None, False))
        window_effect.clear_material(None)

    def test_window_geometry_is_remembered_across_restarts(self):
        self.window.resize(1000, 700)
        self.window.move(120, 90)
        self.window._quit_requested = True
        self.window.close()
        stored = models.portable_settings(self.data_dir).value(
            models.WINDOW_GEOMETRY_SETTINGS_KEY
        )
        self.assertIsNotNone(stored)
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=models.portable_settings(self.data_dir)
            ),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            self.assertEqual(window.size(), QSize(1000, 700))
            self.assertEqual(window.pos(), QPoint(120, 90))
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()

    def test_close_behavior_switch_persists_and_defaults_to_tray(self):
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=models.portable_settings(self.data_dir)
            ),
            data_dir=self.data_dir,
        )
        try:
            settings_page = window.pages["settings"]
            self.assertTrue(settings_page.close_behavior_switch.isChecked())
            self.assertEqual(window.close_behavior, models.CLOSE_BEHAVIOR_TRAY)
            settings_page.close_behavior_switch.setChecked(False)
            self.assertEqual(window.close_behavior, models.CLOSE_BEHAVIOR_QUIT)
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()
        self.assertEqual(
            models.portable_settings(self.data_dir).value(
                models.CLOSE_BEHAVIOR_SETTINGS_KEY
            ),
            models.CLOSE_BEHAVIOR_QUIT,
        )
        reloaded = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=models.portable_settings(self.data_dir)
            ),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            self.assertEqual(reloaded.close_behavior, models.CLOSE_BEHAVIOR_QUIT)
            self.assertFalse(
                reloaded.pages["settings"].close_behavior_switch.isChecked()
            )
        finally:
            reloaded._quit_requested = True
            reloaded.close()
            reloaded.deleteLater()

    def test_clear_data_requires_confirmation_and_removes_portable_folder(self):
        self.alias_store.add("教室 A", "192.168.1.10")
        self.window.logs.info("应用", "清除前日志")
        self.state.set_value("port", 8800)
        settings_page = self.window.pages["settings"]
        self.assertTrue(settings_page.clear_data_button.isEnabled())
        settings_page.clear_data_button.click()
        self.confirm.assert_called_once()
        self.assertFalse(self.data_dir.exists())
        self.assertEqual(self.alias_store.items(), [])
        self.assertEqual(self.state.values, self.state.DEFAULTS)
        self.assertEqual(len(self.window.logs.entries), 1)
        self.assertEqual(self.window.logs.entries[-1].message, "本地数据已清除")
        self.assertIsNone(self.window.logs.log_path)

    def test_clear_data_cancel_keeps_folder(self):
        self.confirm.return_value = False
        self.alias_store.add("教室 A", "192.168.1.10")
        self.window.pages["settings"].clear_data_button.click()
        self.assertTrue(self.data_dir.exists())
        self.assertIsNotNone(self.alias_store.match("教室 A"))

    def test_theme_control_switches_to_dark(self):
        self.window.pages["settings"].theme_box.setCurrentIndex(1)
        self.assertEqual(qconfig.theme, Theme.DARK)

    def test_close_cancels_worker_before_destroying_window(self):
        self.window.show()
        self.state.set_value("target", "192.168.1.10")
        self.message.editor.setPlainText("测试通知")

        def cancellable_send(options, report):
            options.cancel_event.wait(2)
            raise RuntimeError("操作已取消")

        with (
            patch.object(gui.core, "get_ip", return_value=["模拟目标"]),
            patch.object(gui.core, "execute_send_report", side_effect=cancellable_send),
        ):
            self.window.start_send("message")
            self.window.close()
            self.wait_for(
                lambda: self.window.thread is None and not self.window.isVisible()
            )
        self.assertTrue(self.window.close_after_task)
        self.assertTrue(
            any(entry.message == "操作已取消" for entry in self.window.logs.entries)
        )
        self.assertEqual(self.window.logs.entries[-1].message, "应用退出")

    def test_close_without_available_tray_exits_and_stops_listener(self):
        self.window.close_behavior = models.CLOSE_BEHAVIOR_TRAY
        with patch.object(self.window.pages["shell"], "stop_listen") as stop:
            self.assertTrue(self.window.close())
        stop.assert_called_once_with()
        self.assertTrue(self.window._quit_finished)

    def test_close_waits_for_screen_shutdown_before_quit(self):
        from app.gui.screen_window import ScreenWindow

        screen = ScreenWindow("10.1.1.8", parent=self.window)
        connection = MagicMock()
        connection.is_alive.return_value = False
        screen._connection = connection
        screen.destroyed.connect(connection.cancelled.set)
        quitting = []
        self.window.quitRequested.connect(lambda: quitting.append(True))
        self.window.show()
        self.assertFalse(self.window.close())
        self.assertFalse(self.window._quit_finished)
        self.assertEqual(quitting, [])
        self.assertTrue(screen._closed)
        connection.cancelled.set.assert_called_once_with()
        screen._connection_finished(connection, "")
        self.wait_for(lambda: self.window._quit_finished)
        self.assertEqual(quitting, [True])

    def test_close_hides_to_tray_when_tray_mode_is_enabled(self):
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=models.portable_settings(self.data_dir)
            ),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            window.show()
            window.tray_icon = TestTrayIcon(window)
            window.tray_menu = gui.SystemTrayMenu(parent=window)
            window.close_behavior = models.CLOSE_BEHAVIOR_TRAY
            window.close()
            self.assertFalse(window.isVisible())
            self.assertIsNotNone(window.tray_icon)
            self.assertEqual(window.tray_icon.messages, [])
            self.assertEqual(window.logs.entries[-1].message, "窗口已隐藏到系统托盘")
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()

    def test_first_close_can_minimize_to_tray_and_prompts_only_once(self):
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=models.portable_settings(self.data_dir)
            ),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            window.enable_tray = True
            window.show()
            window.tray_icon = TestTrayIcon(window)
            window.tray_menu = gui.SystemTrayMenu(parent=window)
            with patch.object(gui.Dialog, "exec", return_value=1) as execute:
                window.close()
            execute.assert_called_once()
            self.assertFalse(window.isVisible())
            self.assertEqual(window.close_behavior, models.CLOSE_BEHAVIOR_TRAY)
            self.assertTrue(window.first_close_prompt_shown)
            self.assertTrue(
                bool(
                    models.portable_settings(self.data_dir).value(
                        models.FIRST_CLOSE_PROMPT_SETTINGS_KEY, False
                    )
                )
            )

            window.show()
            with patch.object(gui.Dialog, "exec") as second_prompt:
                window.close()
            second_prompt.assert_not_called()
            self.assertFalse(window.isVisible())
            reloaded = gui.MainWindow(
                alias_store=gui.DeviceAliasStore(
                    settings=models.portable_settings(self.data_dir)
                ),
                data_dir=self.data_dir,
                enable_tray=False,
            )
            try:
                self.assertTrue(reloaded.first_close_prompt_shown)
            finally:
                reloaded._quit_requested = True
                reloaded.close()
                reloaded.deleteLater()
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()

    def test_first_close_can_choose_direct_exit(self):
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=models.portable_settings(self.data_dir)
            ),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            window.enable_tray = True
            window.show()
            window.tray_icon = TestTrayIcon(window)
            window.tray_menu = gui.SystemTrayMenu(parent=window)
            with patch.object(gui.Dialog, "exec", return_value=0) as execute:
                window.close()
            execute.assert_called_once()
            self.assertFalse(window.isVisible())
            self.assertEqual(window.close_behavior, models.CLOSE_BEHAVIOR_QUIT)
            self.assertTrue(window.first_close_prompt_shown)
            self.assertIsNone(window.tray_icon)
            self.assertTrue(
                bool(
                    models.portable_settings(self.data_dir).value(
                        models.FIRST_CLOSE_PROMPT_SETTINGS_KEY, False
                    )
                )
            )
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()

    def test_close_quit_mode_exits_and_stops_tray(self):
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=models.portable_settings(self.data_dir)
            ),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            window.show()
            tray = TestTrayIcon(window)
            window.tray_icon = tray
            window.tray_menu = gui.SystemTrayMenu(parent=window)
            window.set_close_behavior(models.CLOSE_BEHAVIOR_QUIT)
            window.close()
            self.assertFalse(window.isVisible())
            self.assertIsNone(window.tray_icon)
            self.assertEqual(window.logs.entries[-1].message, "应用退出")
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()

    def test_tray_menu_shows_window_and_quits(self):
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=models.portable_settings(self.data_dir)
            ),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            tray = TestTrayIcon(window)
            window.tray_icon = tray
            window.tray_menu = gui.SystemTrayMenu(parent=window)
            window.hide()
            window.show_from_tray()
            self.assertTrue(window.isVisible())
            window.hide()
            window.quit_from_tray()
            self.assertFalse(window.isVisible())
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()

    def test_tray_quit_requests_event_loop_exit_when_hidden(self):
        window = gui.MainWindow(
            alias_store=gui.DeviceAliasStore(
                settings=models.portable_settings(self.data_dir)
            ),
            data_dir=self.data_dir,
            enable_tray=False,
        )
        try:
            requests = []
            window.quitRequested.connect(lambda: requests.append(True))
            window.show()
            window.tray_icon = TestTrayIcon(window)
            window.tray_menu = gui.SystemTrayMenu(parent=window)
            window.hide()
            window.quit_from_tray()
            # 隐藏窗口上调用 close() 不会让 Qt 结束事件循环，退出必须由信号驱动。
            self.assertEqual(requests, [True])
            self.assertTrue(window._quit_finished)
            self.assertEqual(window.logs.entries[-1].message, "应用退出")
            # main() 在事件循环结束后还会再调一次，重复清理不应再写日志。
            window.quit_application()
            self.assertEqual(window.logs.entries[-1].message, "应用退出")
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()


class UsageNoticeTests(unittest.TestCase):
    """校验启动时的使用须知：未同意不进入主界面。"""

    def test_notice_follows_dialog_answer(self):
        with patch.object(gui, "Dialog") as dialog_class:
            dialog_class.return_value.exec.return_value = 0
            self.assertFalse(gui.confirm_usage_notice())
            dialog_class.return_value.exec.return_value = 1
            self.assertTrue(gui.confirm_usage_notice())
        self.assertIn("授权", gui.USAGE_NOTICE_TEXT)
        self.assertIn("恶意使用", gui.USAGE_NOTICE_TEXT)

    def test_startup_stops_when_notice_is_declined(self):
        with (
            patch.object(gui, "QApplication"),
            patch.object(gui, "configure_application"),
            patch.object(gui, "SingleInstance") as instance_class,
            patch.object(gui, "confirm_usage_notice", return_value=False) as notice,
            patch.object(gui, "MainWindow") as window_class,
        ):
            self.assertEqual(gui.main(), 0)
        notice.assert_called_once_with()
        window_class.assert_not_called()
        instance_class.return_value.close.assert_called_once_with()

    def test_startup_opens_window_after_agreement(self):
        with (
            patch.object(gui, "QApplication"),
            patch.object(gui, "configure_application"),
            patch.object(gui, "SingleInstance"),
            patch.object(gui, "confirm_usage_notice", return_value=True),
            patch.object(gui, "install_exception_logging"),
            patch.object(gui, "MainWindow") as window_class,
        ):
            gui.main()
        window_class.return_value.show.assert_called_once_with()

    def test_startup_shows_splash_before_event_loop(self):
        with (
            patch.object(gui, "QApplication"),
            patch.object(gui, "configure_application"),
            patch.object(gui, "SingleInstance"),
            patch.object(gui, "confirm_usage_notice", return_value=True),
            patch.object(gui, "install_exception_logging"),
            patch.object(gui, "MainWindow"),
            patch.object(gui, "create_splash") as create,
        ):
            gui.main()
        # 遮罩必须围绕主窗口创建并启动，否则界面会在搭建期间露出半成品。
        create.assert_called_once()
        create.return_value.start.assert_called_once_with()


class SplashScreenTests(unittest.TestCase):
    """校验启动遮罩：图标、文字、跟随尺寸与关闭时机。"""

    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        gui.configure_application(cls.application)

    def setUp(self):
        gui.setTheme(Theme.LIGHT)
        self.parent = QWidget()
        self.parent.resize(1180, 780)
        self.parent.show()
        self.addCleanup(self.dispose_parent)

    def dispose_parent(self):
        """在本用例内完成父窗口销毁，不把待删除对象留给后续测试。"""
        self.parent.close()
        self.parent.deleteLater()
        QCoreApplication.sendPostedEvents(self.parent, QEvent.Type.DeferredDelete)

    def dispose_splash(self, screen):
        """先停止循环动画与计时器，再完成遮罩的延迟删除。"""
        screen.finish()
        self.assertFalse(screen.progress.isStarted())
        self.assertFalse(screen._timer.isActive())
        screen.deleteLater()
        QCoreApplication.sendPostedEvents(screen, QEvent.Type.DeferredDelete)

    def create(self, **kwargs):
        screen = splash.create_splash(self.parent, **kwargs)
        self.addCleanup(self.dispose_splash, screen)
        return screen

    def test_splash_uses_project_icon_and_hides_title_bar(self):
        screen = self.create()
        screen.start()
        self.application.processEvents()
        # 库自带的标题栏会露出最小化/最大化/关闭按钮，遮罩必须盖掉。
        self.assertFalse(screen.titleBar.isVisible())
        self.assertFalse(screen.icon().isNull())
        self.assertEqual(screen.iconSize(), splash.AppSplashScreen.ICON_SIZE)
        self.assertEqual(screen.title_label.text(), gui.APP_NAME)
        self.assertEqual(screen.version_label.text(), gui.version_text())
        self.assertTrue(screen.isVisible())

    def test_splash_follows_parent_size(self):
        screen = self.create()
        screen.start()
        self.application.processEvents()
        self.assertEqual(screen.size(), self.parent.size())
        self.parent.resize(980, 640)
        self.application.processEvents()
        self.assertEqual(screen.size(), self.parent.size())
        # 图标与文字都必须落在遮罩内，缩小时不能被裁到外面。
        for widget in (
            screen.iconWidget,
            screen.title_label,
            screen.version_label,
            screen.status_label,
            screen.progress,
        ):
            self.assertGreaterEqual(widget.geometry().top(), 0, widget.objectName())
            self.assertLessEqual(widget.geometry().bottom(), screen.height())

    def test_splash_finish_is_idempotent(self):
        screen = self.create(minimum_duration=10_000)
        screen.start()
        self.application.processEvents()
        self.assertFalse(screen.is_finished())
        screen.finish()
        self.assertTrue(screen.is_finished())
        self.assertFalse(screen.isVisible())
        # 再调一次不应抛异常，也不应重复关闭。
        screen.finish()
        self.assertTrue(screen.is_finished())

    def test_splash_closes_after_minimum_duration(self):
        screen = self.create(minimum_duration=10)
        screen.start()
        self.assertTrue(screen._timer.isActive())
        # 直接让定时器到期，等价于等满最短停留时间；真实等待要在事件循环里
        # 空转，进度条的循环动画与嵌套循环叠加会偶发崩在 Qt 内部。
        screen._timer.timeout.emit()
        self.assertTrue(screen.is_finished())
        self.assertFalse(screen.isVisible())

    def test_create_splash_ignores_non_widget(self):
        # 测试会把主窗口整体替换成替身，此时不应尝试创建遮罩。
        self.assertIsNone(splash.create_splash(object()))


class SingleInstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault(
            "QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen"
        )
        cls.application = QApplication.instance() or QApplication([])

    def test_second_instance_notifies_primary(self):
        key = "JiYuAttackNext-test-%d" % id(self)
        primary = gui.SingleInstance(key)
        secondary = gui.SingleInstance(key)
        try:
            self.assertTrue(primary.acquire())
            activations = []
            primary.activationRequested.connect(lambda: activations.append(True))
            self.assertFalse(secondary.acquire())
            deadline = time.monotonic() + 3
            while not activations and time.monotonic() < deadline:
                QTest.qWait(10)
            self.assertEqual(activations, [True])
        finally:
            primary.close()
            secondary.close()
            # 普通 processEvents 不处理 DeferredDelete；在所属 GUI 线程
            # 销毁实例及其子服务，避免网络对象跨用例残留。
            primary.deleteLater()
            secondary.deleteLater()
            QCoreApplication.sendPostedEvents(primary, QEvent.Type.DeferredDelete)
            QCoreApplication.sendPostedEvents(secondary, QEvent.Type.DeferredDelete)
            self.application.processEvents()

    def test_single_instance_key_is_user_specific(self):
        self.assertIn(gui.SINGLE_INSTANCE_KEY, gui.single_instance_key())


class TestTrayIcon(QSystemTrayIcon):
    """不依赖真实 Windows 通知区域的测试托盘图标。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.messages = []
        self.hideCount = 0

    def show(self):
        pass

    def hide(self):
        self.hideCount += 1

    def showMessage(self, *args, **kwargs):
        self.messages.append((args, kwargs))


if __name__ == "__main__":
    unittest.main()
