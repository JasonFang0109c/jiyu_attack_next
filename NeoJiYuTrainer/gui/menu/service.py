"""NavigationService 的界面协调逻辑。"""

from PySide6.QtCore import (
    Qt,
    QUrl,
)
from PySide6.QtGui import QDesktopServices
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import (
    NavigationItemPosition,
)

from NeoJiYuTrainer.features.settings.data import (
    DEFAULT_NAVIGATION_EXPANDED,
    NAVIGATION_EXPANDED_SETTINGS_KEY,
    normalize_switch,
)
from NeoJiYuTrainer.gui.menu.sidebar import install_sidebar
from NeoJiYuTrainer.gui.widgets.common import soften_scroll_bars
from NeoJiYuTrainer.gui.widgets.page import TabbedPage
from NeoJiYuTrainer.gui.window.data import (
    HOME_LINKS,
    NAVIGATION_ITEMS,
    PAGE_TABS,
)


class NavigationService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window

    def _build_navigation(self):
        """装配一级导航，底部放日志、设置与关于。"""
        window = self.window
        panel = install_sidebar(window.navigationInterface)
        window.navigationInterface.setExpandWidth(200)
        window.navigationInterface.setMinimumExpandWidth(1050)
        # 首页没有“返回”目标，先隐藏；切到其它页面时再按需显示。
        window.navigationInterface.setReturnButtonVisible(False)
        window.addSubInterface(window.pages["home"], FIF.HOME, "首页")
        window.navigationInterface.addSeparator(NavigationItemPosition.SCROLL)
        for key, icon, title in NAVIGATION_ITEMS:
            window.addSubInterface(
                window.pages[key], icon, title, NavigationItemPosition.SCROLL
            )
        window.addSubInterface(
            window.pages["logs"], FIF.HISTORY, "运行日志", NavigationItemPosition.BOTTOM
        )
        window.addSubInterface(
            window.pages["settings"], FIF.SETTING, "设置", NavigationItemPosition.BOTTOM
        )
        window.addSubInterface(
            window.pages["about"], FIF.INFO, "关于", NavigationItemPosition.BOTTOM
        )
        panel.expandedChanged.connect(window._save_navigation_expanded)
        panel.layoutSettled.connect(window._refresh_navigation)
        window.stackedWidget.currentChanged.connect(window._on_current_page_changed)
        if normalize_switch(
            window.settings.value(NAVIGATION_EXPANDED_SETTINGS_KEY, None),
            DEFAULT_NAVIGATION_EXPANDED,
        ):
            window.expand_navigation()

    def _tune_scroll_bars(self):
        """侧边栏滚动条永不显示，内容区滚动条调细、调淡且滚动时出现。"""
        window = self.window
        panel = window.navigationInterface.panel
        panel.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        panel.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for page in window.pages.values():
            soften_scroll_bars(page)

    def expand_navigation(self):
        """直接展开侧边栏，供启动恢复与截图共用。"""
        window = self.window
        window.navigationInterface.expand(useAni=False)

    def _save_navigation_expanded(self, expanded):
        """把侧边栏最后一次收展请求写进设置。"""
        window = self.window
        window.settings.set_value(NAVIGATION_EXPANDED_SETTINGS_KEY, expanded)
        window.settings.sync()

    def _on_current_page_changed(self, _index=0):
        """页面变化后同步返回按钮与侧边栏轮询。"""
        window = self.window
        window._update_return_button()
        window._sync_page_polling()

    def _sync_page_polling(self):
        """进学生端页先查一次再开轮询，离开就停，避免后台白白扫进程。"""
        window = self.window
        if window.current_page() == "studentproc":
            window.refresh_student_processes()
            window._studentproc_timer.start()
        else:
            window._studentproc_timer.stop()

    def _update_return_button(self, _index=0):
        """非首页显示返回按钮，菜单按钮随之右移；回到首页后还原。"""
        window = self.window
        current = window.stackedWidget.currentWidget()
        window.navigationInterface.setReturnButtonVisible(
            current is not None and current is not window.pages["home"]
        )

    def _open_home_link(self, target):
        """处理首页卡片：页面键直接跳转，其余按外部链接打开。"""
        window = self.window
        if target in window.pages:
            window.show_page(target)
            return
        url = HOME_LINKS.get(target)
        if url is not None:
            QDesktopServices.openUrl(QUrl(url))

    def show_page(self, key):
        """切换到指定页面；组内页面先切到容器页再选中对应标签。"""
        window = self.window
        host_key = PAGE_TABS.get(key)
        if host_key is not None:
            host = window.pages[host_key]
            window.switchTo(host)
            host.set_current(key)
        else:
            window.switchTo(window.pages[key])
        window._reveal_navigation_item(host_key or key)

    def current_page(self):
        """返回当前页面的路由键；停在容器页时返回当前标签的路由。"""
        window = self.window
        current = window.stackedWidget.currentWidget()
        if current is None:
            return ""
        if isinstance(current, TabbedPage):
            return current.current_route()
        return current.objectName()

    def _navigation_item(self, key):
        """按路由取导航控件；路由为空或未注册时返回 None。"""
        window = self.window
        if not key:
            return None
        item = window.navigationInterface.panel.items.get(key)
        # items 存的是路由登记项，导航控件本身挂在它的 widget 上。
        return item.widget if item is not None else None

    def _reveal_navigation_item(self, key):
        """把当前页面对应的导航项滚进可见区域。

        导航项都在可滚动的导航区里，页面一多当前项就可能落在可视范围之外，
        侧边栏就看不出现在停在哪一页。
        """
        window = self.window
        panel = window.navigationInterface.panel
        item = window._navigation_item(key)
        if item is None:
            return
        area = panel.scrollArea
        panel.scrollLayout.activate()
        area.ensureWidgetVisible(item, area.viewport().width(), 12)
        area.horizontalScrollBar().setValue(0)
