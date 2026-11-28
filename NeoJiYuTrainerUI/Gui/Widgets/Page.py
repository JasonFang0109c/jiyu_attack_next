"""按功能组织的 Fluent 工作页面。"""

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CheckBox,
    Pivot,
    SubtitleLabel,
    TableWidget,
    TreeItemDelegate,
    TreeWidget,
    qconfig,
    setCustomStyleSheet,
    setFont,
)
from qfluentwidgets.components.widgets.check_box import CheckBoxIcon

from NeoJiYuTrainerUI.Gui.Theme import CONTROL_CORNER_RADIUS
from NeoJiYuTrainerUI.Gui.Widgets.Common import (
    SectionCard,
    TargetControls,
    TaskFooter,
    page_heading,
)


class ResizableHeader(QHeaderView):
    """可拖动列宽的表头。

    Qt 只把列边界两侧各两个像素当作拖动区，缩放比例高的屏幕上很难抓准，
    点偏了就会当成点选列。这里把热区放宽到两侧各 6 像素，并在悬停到
    边界时显示左右拖动光标，列宽拖动才和运行日志的表格一样好用。
    """

    GRIP = 6

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setMouseTracking(True)
        # 表头内容画在 viewport 上，光标要两处都设，悬停提示才跟着指针走
        self.viewport().setMouseTracking(True)

    def _grip_at(self, x):
        """返回 ``x`` 附近列边界的横坐标，不在热区内返回 None。"""
        for column in range(self.count()):
            edge = self.sectionViewportPosition(column) + self.sectionSize(column)
            if abs(x - edge) <= self.GRIP:
                return edge
        return None

    def _show_grip_cursor(self, near):
        """在表头与 viewport 上切换拖动光标。"""
        shape = Qt.CursorShape.SplitHCursor if near else Qt.CursorShape.ArrowCursor
        self.setCursor(shape)
        self.viewport().setCursor(shape)

    def mouseMoveEvent(self, event):
        """悬停在列边界时给出拖动光标。"""
        super().mouseMoveEvent(event)
        if not event.buttons():
            self._show_grip_cursor(self._grip_at(event.position().x()) is not None)

    def mousePressEvent(self, event):
        """按在边界附近时把按点对齐到边界，交给基类进入拖动状态。"""
        edge = None
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._grip_at(event.position().x())
        if edge is None:
            super().mousePressEvent(event)
            return
        position = event.position()
        snapped = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(edge, position.y()),
            QPointF(self.viewport().mapToGlobal(QPointF(edge, position.y()).toPoint())),
            event.button(),
            event.buttons(),
            event.modifiers(),
        )
        super().mousePressEvent(snapped)


class SelectAllHeaderView(ResizableHeader):
    """在表头首列内嵌与行复选框一致的全选控件。"""

    CHECKBOX_SIZE = 18

    def __init__(
        self,
        orientation,
        parent=None,
        tooltip="全选当前筛选结果",
        accessible_name="全选当前筛选结果",
    ):
        super().__init__(orientation, parent)
        self.select_all_checkbox = self._create_select_all_checkbox(self.viewport())
        self.select_all_checkbox.setAccessibleName(accessible_name)
        self.select_all_checkbox.setToolTip(tooltip)
        self.select_all_checkbox.setFixedSize(self.CHECKBOX_SIZE, self.CHECKBOX_SIZE)
        self.select_all_checkbox.raise_()
        self._checkbox_visible = True
        # 增删行不会让表头重绘，得直接盯模型的信号。
        model = self._table_model()
        if model is not None:
            for signal in (
                model.rowsInserted,
                model.rowsRemoved,
                model.modelReset,
                model.layoutChanged,
            ):
                signal.connect(self.sync_checkbox_visibility)

    def _create_select_all_checkbox(self, parent):
        return StickySizeCheckBox(parent, self.CHECKBOX_SIZE)

    def _table_model(self):
        """沿父链找到承载本表头的表格模型。"""
        widget = self.parentWidget()
        while widget is not None:
            if isinstance(widget, QAbstractItemView):
                return widget.model()
            widget = widget.parentWidget()
        return None

    def sync_checkbox_visibility(self, *_):
        """表格没有数据行时隐藏全选框。

        空表时表头首列只剩一个没有勾的空框，看上去像画坏的控件；
        有行才需要全选，所以按行数显隐。
        """
        model = self._table_model()
        visible = bool(model is not None and model.rowCount()) and self.count() > 0
        if visible == self._checkbox_visible:
            return
        self._checkbox_visible = visible
        self.select_all_checkbox.setVisible(visible)

    def paintEvent(self, event):
        """重绘表头时顺带同步全选框，模型变化不需要额外信号。"""
        self.sync_checkbox_visibility()
        super().paintEvent(event)

    def position_checkbox(self):
        """把全选框居中放到表头首列。"""
        if not self.isVisible():
            return
        x = (
            self.sectionViewportPosition(0)
            + (self.sectionSize(0) - self.CHECKBOX_SIZE) // 2
        )
        y = (self.height() - self.CHECKBOX_SIZE) // 2
        self.select_all_checkbox.move(x, y)

    def resizeEvent(self, event):
        """尺寸变化后重新定位表头全选框。"""
        super().resizeEvent(event)
        self.position_checkbox()

    def showEvent(self, event):
        super().showEvent(event)
        self.position_checkbox()


LogHeaderView = SelectAllHeaderView


class FileTreeHeader(SelectAllHeaderView):
    """文件树表头：全选复选框与首列行复选框对齐。"""

    CHECKBOX_SIZE = 16

    def _create_select_all_checkbox(self, parent):
        checkbox = CompactHeaderCheckBox(parent)
        checkbox.setObjectName("fileTreeSelectAllCheckbox")
        return checkbox

    def position_checkbox(self):
        """把全选框居中放到表头首列。"""
        if not self.isVisible():
            return
        tree = self.parent()
        offset = 0
        if (
            tree is not None
            and hasattr(tree, "topLevelItem")
            and tree.topLevelItemCount()
        ):
            rect = tree.visualItemRect(tree.topLevelItem(0))
            if rect.isValid():
                offset = rect.x()
        x = self.sectionViewportPosition(0) + offset + 24
        y = (self.height() - self.CHECKBOX_SIZE) // 2
        self.select_all_checkbox.move(x, y)


class StickySizeCheckBox(CheckBox):
    """表头全选框：样式刷新后重新锁定尺寸。

    主题切换会重设 Fluent 复选框样式表，Qt 会顺带清掉由样式表推导出来的
    最小尺寸，控件随即撑到文字宽度；这里在样式变化后补回固定尺寸。
    样式表还给 indicator 留了 1 像素边框与 1 像素左外边距，控件固定成
    方框后 indicator 会溢出控件被裁掉，所以把这层留白一并去掉。
    """

    # indicator 的宽度高度与控件等值、去掉边框后，绘制区域才刚好落在方框内。
    INDICATOR_QSS = (
        "CheckBox { padding: 0px; margin: 0px; spacing: 0px;"
        " min-width: 0px; min-height: 0px; }"
        "CheckBox::indicator { width: %dpx; height: %dpx; border: none;"
        " border-radius: 5px; }"
    )
    # 用来判断紧排样式是否已经追加过，避免重复叠加。
    TIGHT_MARK = "min-width: 0px"

    def __init__(self, parent=None, size=18):
        # 基类构造里就会应用样式表并触发 StyleChange，先备好尺寸再交给基类。
        self._locked_size = size
        super().__init__(parent)
        self._fit_indicator()

    def _fit_indicator(self):
        """让 indicator 正好等于控件尺寸，避免圆角被裁成一半。

        直接改 ``styleSheet`` 会在主题重建时被组件库整份覆盖，所以走它的
        自定义样式接口，跟基础复选框样式一起重组。
        """
        rule = self.INDICATOR_QSS % (self._locked_size, self._locked_size)
        if self.TIGHT_MARK in self.styleSheet():
            return
        setCustomStyleSheet(self, rule, rule)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self.setFixedSize(self._locked_size, self._locked_size)


class CompactHeaderCheckBox(StickySizeCheckBox):
    """以与文件行相同的 16px Fluent 样式绘制表头全选框。"""

    INDICATOR_SIZE = 16

    def __init__(self, parent=None):
        super().__init__(parent, self.INDICATOR_SIZE)

    def paintEvent(self, event):
        """按文件树行复选框的尺寸绘制表头复选框。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = self.INDICATOR_SIZE
        rect = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
        if not self.isEnabled():
            # 禁用态要连同边框与底色一起压淡，所以必须在绘制之前设置。
            painter.setOpacity(0.8)
        painter.setPen(self._borderColor())
        painter.setBrush(self._backgroundColor())
        radius = 4.5 * size / 19
        painter.drawRoundedRect(rect, radius, radius)
        if self.checkState() == Qt.Checked:
            CheckBoxIcon.ACCEPT.render(painter, rect)
        elif self.checkState() == Qt.PartiallyChecked:
            CheckBoxIcon.PARTIAL_ACCEPT.render(painter, rect)


class CompactTreeItemDelegate(TreeItemDelegate):
    """复用 Fluent 树委托的状态样式，只将选择框略微缩小。"""

    CHECKBOX_SIZE = 16
    DEFAULT_CHECKBOX_SIZE = 19

    def _drawCheckBox(self, painter, option, index):
        scale = self.CHECKBOX_SIZE / self.DEFAULT_CHECKBOX_SIZE
        center_x = option.rect.x() + 23 + self.DEFAULT_CHECKBOX_SIZE / 2
        center_y = option.rect.center().y() + 0.5
        painter.save()
        painter.translate(center_x, center_y)
        painter.scale(scale, scale)
        painter.translate(-center_x, -center_y)
        super()._drawCheckBox(painter, option, index)
        painter.restore()


class FileTreeWidget(TreeWidget):
    """报告鼠标当前悬停的名称列条目，供图标与复选框切换显示。"""

    hoverItemChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_item = None
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def viewportEvent(self, event):
        """只在名称列跟踪悬停项，避免路径列触发复选框切换。"""
        if event.type() == QEvent.Type.MouseMove:
            position = event.position().toPoint()
            item = self.itemAt(position) if self.columnAt(position.x()) == 0 else None
            self._set_hover_item(item)
        elif event.type() == QEvent.Type.Leave:
            self._set_hover_item(None)
        return super().viewportEvent(event)

    def _set_hover_item(self, item):
        # 不去重：重建树之后页面缓存的悬停项可能仍然等于新条目，
        # 这里跳过通知就会让复选框一直不出现。重复通知由页面自己挡住。
        self._hover_item = item
        self.hoverItemChanged.emit(item)

    def reset_hover_item(self):
        """清除悬停项，重建树时避免旧条目继续显示悬停状态。"""
        self._hover_item = None


class LogTableWidget(TableWidget):
    """日志表固定元数据列，内容列按剩余宽度自适应。"""

    FIXED_COLUMNS = (0, 1, 2, 3, 5, 6)
    MIN_CONTENT_WIDTH = 120

    def resizeEvent(self, event):
        """窗口宽度变化时重新计算日志内容列宽。"""
        super().resizeEvent(event)
        reserved = sum(self.columnWidth(column) for column in self.FIXED_COLUMNS)
        self.setColumnWidth(
            4, max(self.MIN_CONTENT_WIDTH, self.viewport().width() - reserved)
        )


def table_widget(
    headers,
    parent,
    table_class=TableWidget,
    *,
    stretch_last=True,
    radius=CONTROL_CORNER_RADIUS,
):
    """创建统一的只读、按行选择的表格控件。

    Args:
        headers: 表头文本列表。
        parent: 父控件。
        table_class: 表格子类，默认 ``TableWidget``。
        stretch_last: 是否让最后一列自适应剩余宽度。
        radius: 表格自身的圆角，铺满卡片时传卡片的圆角值。
    """
    table = table_class(parent)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setWordWrap(False)
    table.setBorderVisible(True)
    table.setBorderRadius(radius)
    table.setHorizontalHeader(ResizableHeader(Qt.Orientation.Horizontal, table))
    table.horizontalHeader().setStretchLastSection(stretch_last)
    return table


class Page(QWidget):
    """所有工作页面的基础布局，统一提供内容边距与垂直布局。"""

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self.vbox = QVBoxLayout(self)
        self.vbox.setContentsMargins(28, 24, 28, 24)
        self.vbox.setSpacing(20)


NAV_ITEM_PIXELS = 14
"""导航项字体的像素大小，与卡片里的 ``BodyLabel`` 一致，比组标题的 20 小一档。"""


class TabbedPage(Page):
    """用顶部导航栏承载多个子页面的容器页。

    侧边栏只保留一个入口，组内的页面通过组标题下方的 ``Pivot`` 切换。
    导航栏左缘与页面内容对齐 28 像素，导航项文字与卡片正文同号（比组标题小
    一档），选中项由组件库在文字下方画出 16×3 的主题色指示条并在切换时滑动
    过去，其余项只有文字。
    子页面原来的页标题会隐藏，避免与导航文字重复。

    Attributes:
        pivot: 组件库的 ``Pivot``，组标题下方的导航栏。
        stack: 子页面容器，索引与导航项一致。
    """

    def __init__(self, name, title, parent=None):
        super().__init__(name, parent)
        # 标题与导航栏各占一行，内容区不再缩在页面边距里面。
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(0)
        title_row = QWidget(self)
        title_layout = QHBoxLayout(title_row)
        # 顶部留白与普通页的 24 像素一致，组标签页的标题才和“启停学生端”对齐。
        title_layout.setContentsMargins(28, 24, 28, 0)
        title_layout.addWidget(SubtitleLabel(title, title_row))
        title_layout.addStretch()
        self.vbox.addWidget(title_row)
        self.pivot = Pivot(self)
        self.pivot.setObjectName("pagePivotNav")
        # 短横沿用组件默认的 16×3，与 WinUI 的 PivotHeaderItem 选中条同规格。
        self.pivot.setIndicatorLength(16)
        nav_row = QWidget(self)
        nav_layout = QHBoxLayout(nav_row)
        # 导航项自带上下各 10 像素内边距，所以这里只补 6 像素：标题到导航文字
        # 16、指示条到卡片 24，正好是 WinUI 间距规范里“控件与标头 8、内容区域
        # 之间 12”的 2:3。
        nav_layout.setContentsMargins(16, 6, 16, 0)
        nav_layout.setSpacing(0)
        # 靠左对齐让导航栏保持自身宽度，否则行内的多余空间会把它撑开。
        nav_layout.addWidget(self.pivot, 0, Qt.AlignLeft)
        self.vbox.addWidget(nav_row)
        self.stack = QStackedWidget(self)
        self.vbox.addWidget(self.stack, 1)
        self.pivot.currentItemChanged.connect(self._follow_pivot)
        # 指示条按当前主题取色，切主题后重绘一次。
        qconfig.themeChanged.connect(self.pivot.update)
        self._routes = []

    def _follow_pivot(self, key):
        """跟随导航项的选择切换子页面。"""
        if key in self._routes:
            self.stack.setCurrentIndex(self._routes.index(key))

    def add_tab(self, widget, text, icon=None):
        """加入一个子页面并隐藏它重复的页标题行。

        Args:
            widget: 子页面，``objectName`` 同时作为导航项的路由键。
            text: 导航项文字。
            icon: 导航项图标，可以是 ``FluentIcon``。

        Returns:
            int: 子页面在容器中的索引。
        """
        heading = widget.findChild(QWidget, "pageHeading")
        if heading is not None:
            heading.hide()
        index = self.stack.addWidget(widget)
        route = widget.objectName()
        # 点击导航项由组件库自己切换选中状态，这里只登记文字与图标。
        self.pivot.addItem(routeKey=route, text=text, icon=icon)
        # 组件默认 18 像素，这里统一压到比组标题小一档。
        setFont(self.pivot.widget(route), NAV_ITEM_PIXELS)
        self._routes.append(route)
        # 首个导航项直接选中，导航栏才会画出指示条。
        if index == 0:
            self.pivot.setCurrentItem(route)
        return index

    def set_current(self, key):
        """切换到指定子页面；键不在本容器时忽略。"""
        if key not in self._routes:
            return
        self.pivot.setCurrentItem(key)
        self._follow_pivot(key)

    def current_route(self):
        """返回当前子页面的路由键。"""
        route = self.pivot.currentRouteKey()
        if route in self._routes:
            return route
        return self.objectName()


class NetworkPage(Page):
    """带目标输入区、内容区和任务底栏的网络操作页面。"""

    def __init__(self, name, title, state, button_text, parent=None):
        super().__init__(name, parent)
        page_heading(self.vbox, title)
        self.target_card = SectionCard(self)
        self.target_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.targets = TargetControls(state, self.target_card)
        self.target_card.body.addWidget(self.targets)
        self.vbox.addWidget(self.target_card)
        self.content_card = SectionCard(self, spacing=10)
        self.body = self.content_card.body
        self.vbox.addWidget(self.content_card, 1)
        self.footer_card = SectionCard(self, spacing=0, margins=(8, 8, 8, 8))
        self.footer = TaskFooter(button_text, self.footer_card)
        self.footer_card.body.addWidget(self.footer)
        self.vbox.addWidget(self.footer_card)

    def set_busy(self, busy, cancellable=False, queueable=False):
        """同步目标输入区与底栏的任务忙碌状态。"""
        self.targets.setEnabled(not busy)
        self.footer.set_busy(busy, cancellable, queueable)
