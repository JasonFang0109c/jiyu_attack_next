"""侧边导航：一级入口、面板宽度动画与标题栏顶部按钮。"""

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QRect,
    QSize,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import (
    NavigationDisplayMode,
    NavigationItemPosition,
    NavigationPanel,
    NavigationTreeWidget,
)
from qfluentwidgets.components.navigation.navigation_widget import NavigationWidget

from NeoJiYuTrainerUI.Gui.Window.Data import (
    SIDEBAR_BUTTON_HEIGHT,
    SIDEBAR_BUTTON_INSET,
    SIDEBAR_BUTTON_TOP,
    SIDEBAR_BUTTON_WIDTH,
    SIDEBAR_COLLAPSED_WIDTH,
    SIDEBAR_HEADER_INSET,
    TITLE_BAR_MARGIN,
)


class SidebarTreeWidget(NavigationTreeWidget):
    """保留分组选择，同时在图标模式下彻底隐藏后代节点。"""

    expansionChanged = Signal(bool)

    # 与组件库的导航项同尺寸：收起时正方形图标块，展开时撑满面板。
    ITEM_HEIGHT = 36
    COMPACT_WIDTH = 40

    def setExpanded(self, isExpanded, ani=False):
        """设置分组状态；树节点即时布局，避免尺寸动画与面板动画竞争。

        ``ani`` 只用于兼容组件库的调用签名，本类始终即时布局。
        """
        changed = self.isExpanded != isExpanded
        self.isExpanded = isExpanded
        self.itemWidget.setExpanded(isExpanded)
        self._layout_tree()
        if changed:
            self.expansionChanged.emit(isExpanded)
            self.expanded.emit()

    def setCompacted(self, isCompacted):
        """切换显示模式，保留逻辑展开状态供下一次展开使用。"""
        NavigationWidget.setCompacted(self, isCompacted)
        self.itemWidget.setCompacted(isCompacted)
        # 后代节点由面板的 _setWidgetCompacted 统一遍历，这里只处理自身。
        self._layout_tree()

    def insertChild(self, index, child):
        super().insertChild(index, child)
        child.setCompacted(self.isCompacted)
        self._layout_tree()

    def setSelected(self, isSelected):
        """隐藏子项改变选择时同步刷新祖先的选中标记。"""
        super().setSelected(isSelected)
        parent = self.treeParent
        while parent is not None:
            parent.itemWidget.update()
            parent = parent.treeParent

    def clone(self):
        """图标模式的弹出菜单也使用同一套节点逻辑。"""
        root = type(self)(self._icon, self.text(), self.isSelectable, self.parent())
        root.nodeDepth = self.nodeDepth
        root.setSelected(self.isSelected)
        root.setTextColor(self.lightTextColor, self.darkTextColor)
        root.setIndicatorColor(
            self.itemWidget.lightIndicatorColor, self.itemWidget.darkIndicatorColor
        )
        root.clicked.connect(self.clicked)
        self.selectedChanged.connect(root.setSelected)
        for child in self.treeChildren:
            root.addChild(child.clone())
        root.setExpanded(self.isExpanded)
        return root

    def _layout_tree(self):
        height = self.ITEM_HEIGHT
        for child in self.treeChildren:
            visible = self.isExpanded and not self.isCompacted
            child.setVisible(visible)
            if visible:
                height += child.height() + self.vBoxLayout.spacing()
        width = self.COMPACT_WIDTH if self.isCompacted else self.EXPAND_WIDTH
        self.setFixedSize(width, height)
        self.vBoxLayout.invalidate()
        self.vBoxLayout.activate()
        self.update()
        if self.treeParent is not None:
            self.treeParent._layout_tree()

    def _onClicked(self, triggerByUser, clickArrow):
        # 叶节点只切换页面；库的默认实现还会给叶节点启动尺寸动画。
        if self.treeChildren and not self.isCompacted:
            self.setExpanded(not self.isExpanded)
        if not clickArrow or self.isCompacted:
            self.clicked.emit(triggerByUser)


class SidebarPanel(NavigationPanel):
    """以最后一次操作为准，从当前宽度平滑切换侧边栏。"""

    expandedChanged = Signal(bool)
    layoutSettled = Signal()

    def __init__(self, parent):
        # 基类构造里就会设置返回按钮的可见性，两个字段要先就位。
        self._expanded = False
        self._tools = None
        self._return_button_visible = False
        # 基类构造期间窗口就会开始派发尺寸事件，待办标记也要先有值。
        self._overlay_reflow_pending = False
        super().__init__(parent)
        self._install_tools()
        # 选中标记由可见条目绘制，避免浮动标记跨布局移动到已隐藏的子项位置。
        self.setIndicatorAnimationEnabled(False)
        # 只动画宽度；窗口高度变化不再被旧的 geometry 动画值覆盖。
        self.expandAni.deleteLater()
        self.expandAni = QVariantAnimation(self)
        self.expandAni.setDuration(150)
        self.expandAni.setEasingCurve(QEasingCurve.OutQuad)
        self.expandAni.valueChanged.connect(self._set_width)
        self.expandAni.finished.connect(self._onExpandAniFinished)

    def showEvent(self, event):
        super().showEvent(event)
        if self._tools is not None:
            self._tools.show()
            self._raise_tools()

    def hideEvent(self, event):
        if self._tools is not None:
            self._tools.hide()
        super().hideEvent(event)

    def _install_tools(self):
        """把返回与菜单按钮并排放在侧边栏左上角。

        两个按钮随返回状态切换槽位：首页隐藏返回按钮，菜单按钮占左槽；子页面显示
        返回按钮，菜单按钮移到右槽。标题栏内容也按同一状态右移，保持菜单与标题
        之间的间距稳定；不要把首页菜单固定在右槽。

        面板顶部的留白用 ``topLayout`` 的上边距给出：组件库会把“顶部”位置的
        导航项插进同一个布局，用间距只会把下面的滚动区一起推下去。
        """
        self._tools = QWidget(self.window())
        self.topLayout.removeWidget(self.returnButton)
        self.topLayout.removeWidget(self.menuButton)
        for button in (self.returnButton, self.menuButton):
            button.setParent(self._tools)
            button.setFixedSize(SIDEBAR_BUTTON_WIDTH, SIDEBAR_BUTTON_HEIGHT)
        self.topLayout.setContentsMargins(4, SIDEBAR_HEADER_INSET, 4, 0)
        self.topLayout.setSpacing(4)
        self._settle_tools()

    def setReturnButtonVisible(self, isVisible):
        """同步返回按钮、菜单按钮与标题栏的槽位。"""
        self._return_button_visible = isVisible
        super().setReturnButtonVisible(isVisible)
        self._settle_tools()

    def _settle_tools(self):
        """按返回按钮状态排布菜单，并同步标题栏的左侧留白。"""
        tools = self._tools
        if tools is None:
            return
        self.returnButton.move(0, 0)
        menu_x = SIDEBAR_BUTTON_WIDTH if self._return_button_visible else 0
        self.menuButton.move(menu_x, 0)
        tools.setGeometry(
            SIDEBAR_BUTTON_INSET,
            SIDEBAR_BUTTON_TOP,
            SIDEBAR_BUTTON_WIDTH * 2,
            SIDEBAR_BUTTON_HEIGHT,
        )
        # FluentTitleBar 左缘固定在 46。菜单占左槽时标题只预留文字间距；子页面
        # 显示返回后，菜单和标题再一起右移一格，避免两者位置失配。
        title_bar = self.window().titleBar
        reserved_width = SIDEBAR_BUTTON_WIDTH if self._return_button_visible else 0
        title_bar.hBoxLayout.setContentsMargins(
            TITLE_BAR_MARGIN + reserved_width, 0, 0, 0
        )
        title_bar.hBoxLayout.activate()
        self._raise_tools()

    def _raise_tools(self):
        """面板或标题栏抬到最上层之后，把按钮重新压回它们上面。"""
        self._tools.raise_()

    def insertItem(
        self,
        index,
        routeKey,
        icon,
        text,
        onClick=None,
        selectable=True,
        position=NavigationItemPosition.TOP,
        tooltip=None,
        parentRouteKey=None,
    ):
        if routeKey in self.items:
            return None
        widget = SidebarTreeWidget(icon, text, selectable, self)
        self.insertWidget(
            index, routeKey, widget, onClick, position, tooltip, parentRouteKey
        )
        return widget

    def expand(self, useAni=True):
        """从当前几何尺寸展开，立即恢复分组的可见性。"""
        self.expandAni.stop()
        changed = not self._expanded
        self._expanded = True
        self._stopIndicatorAnimation()
        self._setWidgetCompacted(False)
        self.expandAni.setProperty("expand", True)
        self.menuButton.setToolTip(self.tr("Close Navigation"))
        # 宽度阈值与窗口缩小时的自动收起阈值一致。
        inline = (
            self.window().width() >= self.minimumExpandWidth
            and not self.isMinimalEnabled
        ) or not self._isCollapsible
        self.displayMode = (
            NavigationDisplayMode.EXPAND if inline else NavigationDisplayMode.MENU
        )
        self.setProperty("menu", not inline)
        self.setStyle(QApplication.style())
        if inline:
            self._attach_to_parent()
        else:
            self._detach_to_window()
        # 浮出的面板是窗口的子控件，新排进最上层后要先让按钮浮回面板之上。
        self._raise_tools()
        self.displayModeChanged.emit(self.displayMode)
        if changed:
            self.expandedChanged.emit(True)
        if useAni:
            self._animate_width(self.expandWidth)
        else:
            self._set_width(self.expandWidth)
            self._onExpandAniFinished()

    def collapse(self):
        """先隐藏后代节点，再收窄面板，避免选中条与子项残影。"""
        if not self._expanded:
            return
        self.expandAni.stop()
        self._expanded = False
        self._stopIndicatorAnimation()
        self._setWidgetCompacted(True)
        self.expandAni.setProperty("expand", False)
        self.menuButton.setToolTip(self.tr("Open Navigation"))
        self.expandedChanged.emit(False)
        self._animate_width(SIDEBAR_COLLAPSED_WIDTH)

    def toggle(self):
        """动画中再次操作时直接转向最新请求。"""
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def isCollapsed(self):
        return not self._expanded

    def eventFilter(self, obj, e):
        """窗口变宽后把浮出的面板收回布局，避免它盖在内容上。"""
        if obj is self.window() and e.type() == QEvent.Resize:
            self._queue_overlay_reflow(QResizeEvent(e).size().width())
        return super().eventFilter(obj, e)

    def _queue_overlay_reflow(self, width):
        """条件满足时排到本轮事件之后再换布局，避免在窗口缩放中重排面板。"""
        if self._overlay_reflow_pending:
            return
        if not self._needs_overlay_reflow(width):
            return
        self._overlay_reflow_pending = True
        QTimer.singleShot(0, self._reflow_overlay)

    def _needs_overlay_reflow(self, width):
        """浮出状态的展开面板遇到变宽的窗口时需要换成贴边展开。"""
        if not self._expanded or self.displayMode != NavigationDisplayMode.MENU:
            return False
        return not self.isMinimalEnabled and width >= self.minimumExpandWidth

    def _reflow_overlay(self):
        """把 MENU 浮出切换成贴边展开。

        组件库只在 ``EXPAND`` 与 ``COMPACT`` 之间自动往返，浮出状态没有对应
        分支：窗口从窄变宽后面板仍是窗口的子控件、保持 200 像素宽压在内容区
        左侧，看上去就是最大化之后界面错乱。宽度够了就原地换成贴边展开，
        这样面板位置与宽度都不变，只是重新参与布局、把内容推到它右侧。
        """
        self._overlay_reflow_pending = False
        if not self._needs_overlay_reflow(self.window().width()):
            return
        self.expand(useAni=False)

    def _attach_to_parent(self):
        """贴边展开：面板回到窗口布局里，宽度由父容器跟着撑开。"""
        self._parent.setFixedWidth(self.width())
        if self.parent() is not self._parent:
            self.setParent(self._parent)
            self.move(0, 0)
            self.show()

    def _detach_to_window(self):
        """浮出展开：面板挂到窗口上盖住内容，先取背景再换父控件。"""
        self._parent.setFixedWidth(SIDEBAR_COLLAPSED_WIDTH)
        if self._canDrawAcrylic():
            self.acrylicBrush.grabImage(
                QRect(
                    self.mapToGlobal(QPoint()),
                    QSize(self.expandWidth, self.height()),
                )
            )
        if self.parent() is self._parent:
            position = self._parent.pos()
            self.setParent(self.window())
            self.move(position)
            self.show()

    def _animate_width(self, width):
        self.expandAni.setStartValue(self.width())
        self.expandAni.setEndValue(width)
        self.expandAni.start()

    def _set_width(self, width):
        self.resize(int(width), self.height())

    def _onExpandAniFinished(self):
        super()._onExpandAniFinished()
        self._stopIndicatorAnimation()
        self._raise_tools()
        self.layout().activate()
        self.scrollLayout.activate()
        self.layoutSettled.emit()


def install_sidebar(interface):
    """在注册页面前替换空面板，保留 FluentWindow 的路由与布局接线。"""
    previous = interface.panel
    previous.removeEventFilter(interface)
    interface.window().removeEventFilter(previous)
    previous.hide()
    previous.deleteLater()
    panel = SidebarPanel(interface)
    interface.panel = panel
    panel.installEventFilter(interface)
    panel.displayModeChanged.connect(interface.displayModeChanged)
    panel.setFixedHeight(interface.height())
    panel.show()
    return panel
