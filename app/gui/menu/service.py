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

from app.features.settings.data import (
    DEFAULT_NAVIGATION_EXPANDED,
    NAVIGATION_EXPANDED_SETTINGS_KEY,
    normalize_switch,
)
from app.gui.menu.sidebar import install_sidebar
from app.gui.widgets.common import soften_scroll_bars
from app.gui.window.data import (
    HOME_LINKS,
    NAVIGATION_ALIASES_AFTER,
    NAVIGATION_GROUPS,
    NAVIGATION_MAX_HEIGHT,
)


class NavigationService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window

    def _build_navigation(self):
        """按功能分组装配左侧导航，底部放日志、设置与关于。"""
        window = self.window
        panel = install_sidebar(window.navigationInterface)
        window.navigationInterface.setExpandWidth(200)
        window.navigationInterface.setMinimumExpandWidth(1050)
        window.navigationInterface.setReturnButtonVisible(False)
        window.addSubInterface(window.pages["home"], FIF.HOME, "首页")
        window.navigationInterface.addSeparator(NavigationItemPosition.SCROLL)
        for route, icon, title, children in NAVIGATION_GROUPS:
            window._add_navigation_group(route, icon, title, children)
            if route == NAVIGATION_ALIASES_AFTER:
                # 设备备注是独立入口，位置在远程攻击与本机工具之间。
                window.addSubInterface(
                    window.pages["aliases"],
                    FIF.QUICK_NOTE,
                    "设备备注",
                    NavigationItemPosition.SCROLL,
                )
        window.navigationInterface.addSeparator(NavigationItemPosition.SCROLL)
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

    def _remember_navigation_group(self, route, expanded):
        """保存用户选择的分组状态，显示模式变化不改写它。"""
        window = self.window
        window.settings.set_value("gui/window/navigation_%s" % route, expanded)
        window.settings.sync()

    def _save_navigation_expanded(self, expanded):
        """把侧边栏最后一次收展请求写进设置。"""
        window = self.window
        window.settings.set_value(NAVIGATION_EXPANDED_SETTINGS_KEY, expanded)
        window.settings.sync()

    def _apply_navigation_minimum_height(self):
        """按导航内容设置侧边栏最小高度，但不让它把窗口顶高。

        分组都在可滚动的导航区里，最小高度只算顶部首页那一行与底部按钮，
        内容再多也只是出现滚动条，不会把窗口顶到超出屏幕。
        """
        window = self.window
        # 交给组件库算，否则分隔符与布局间距都要跟着版本自己重数一遍。
        needed = window.navigationInterface.panel.layoutMinHeight()
        window.navigationInterface.setMinimumHeight(min(needed, NAVIGATION_MAX_HEIGHT))

    def _add_navigation_group(self, route, icon, title, children):
        """创建一个只承载子项的分组节点，并按其顺序挂上子页面。"""
        window = self.window
        # 分组本身不是页面，所以不可选中，点击只切换展开状态。
        window.navigationInterface.addItem(
            routeKey=route,
            icon=icon,
            text=title,
            selectable=False,
            position=NavigationItemPosition.SCROLL,
            tooltip=title,
        )
        node = window._navigation_item(route)
        for key, child_icon, child_title in children:
            window.addSubInterface(
                window.pages[key], child_icon, child_title, parent=route
            )
        node.setExpanded(
            normalize_switch(
                window.settings.value("gui/window/navigation_%s" % route, None), True
            )
        )
        node.expansionChanged.connect(
            lambda expanded, route=route: window._remember_navigation_group(
                route, expanded
            )
        )
        window._apply_navigation_minimum_height()
        return node

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
        """切换到指定页面，并展开它所属的父级导航项。"""
        window = self.window
        # 页面可能从首页快捷入口打开，先恢复所属分组，保持导航位置可见。
        page = window.pages[key]
        item = window.navigationInterface.panel.items.get(key)
        parent_key = item.parentRouteKey if item is not None else None
        node = window._navigation_item(parent_key)
        if node is not None and not node.isExpanded:
            node.setExpanded(True, ani=False)
        window.switchTo(page)
        window._reveal_navigation_item(key)
        # 进页先查一次，随后开轮询；离开本页就停，避免后台白白扫进程。
        if key == "studentproc":
            window.refresh_student_processes()
            window._studentproc_timer.start()
        else:
            window._studentproc_timer.stop()

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

        分组都在可滚动的导航区里，页面一多当前项就可能落在可视范围之外，
        侧边栏就看不出现在停在哪一页。
        """
        window = self.window
        panel = window.navigationInterface.panel
        item = window._navigation_item(key)
        if item is None:
            return
        area = panel.scrollArea
        # 图标模式下定位父项，隐藏子项的旧坐标不参与滚动。
        while item.isHidden() and item.treeParent is not None:
            item = item.treeParent
        panel.scrollLayout.activate()
        area.ensureWidgetVisible(item, area.viewport().width(), 12)
        area.horizontalScrollBar().setValue(0)

    def current_page(self):
        """返回当前页面名。"""
        window = self.window
        return window.stackedWidget.currentWidget().objectName()
