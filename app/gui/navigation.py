"""侧边导航：分组状态与可见性分离，只有面板宽度参与动画。"""

from PySide6.QtCore import QEasingCurve, QPoint, QRect, QSize, QVariantAnimation, Signal
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    NavigationDisplayMode,
    NavigationItemPosition,
    NavigationPanel,
    NavigationTreeWidget,
)
from qfluentwidgets.components.navigation.navigation_widget import NavigationWidget


class SidebarTreeWidget(NavigationTreeWidget):
    """保留分组选择，同时在图标模式下彻底隐藏后代节点。"""

    expansionChanged = Signal(bool)

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
        height = 36
        for child in self.treeChildren:
            visible = self.isExpanded and not self.isCompacted
            child.setVisible(visible)
            if visible:
                height += child.height() + self.vBoxLayout.spacing()
        width = 40 if self.isCompacted else self.EXPAND_WIDTH
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
        self._expanded = False
        super().__init__(parent)
        # 选中标记由可见条目绘制，避免浮动标记跨布局移动到已隐藏的子项位置。
        self.setIndicatorAnimationEnabled(False)
        # 只动画宽度；窗口高度变化不再被旧的 geometry 动画值覆盖。
        self.expandAni.deleteLater()
        self.expandAni = QVariantAnimation(self)
        self.expandAni.setDuration(150)
        self.expandAni.setEasingCurve(QEasingCurve.OutQuad)
        self.expandAni.valueChanged.connect(self._set_width)
        self.expandAni.finished.connect(self._onExpandAniFinished)

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
            self._parent.setFixedWidth(self.width())
            if self.parent() is not self._parent:
                self.setParent(self._parent)
                self.move(0, 0)
                self.show()
        else:
            self._parent.setFixedWidth(48)
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
        self._animate_width(48)

    def toggle(self):
        """动画中再次操作时直接转向最新请求。"""
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def isCollapsed(self):
        return not self._expanded

    def _animate_width(self, width):
        self.expandAni.setStartValue(self.width())
        self.expandAni.setEndValue(width)
        self.expandAni.start()

    def _set_width(self, width):
        self.resize(int(width), self.height())

    def _onExpandAniFinished(self):
        super()._onExpandAniFinished()
        self._stopIndicatorAnimation()
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
