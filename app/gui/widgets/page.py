"""按功能组织的 Fluent 工作页面。"""

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QVBoxLayout, QWidget
from qfluentwidgets import CheckBox, TableWidget, TreeItemDelegate, TreeWidget
from qfluentwidgets.components.widgets.check_box import CheckBoxIcon

from app.gui.theme import CONTROL_CORNER_RADIUS
from app.gui.widgets.common import SectionCard, TargetControls, TaskFooter, page_heading


class SelectAllHeaderView(QHeaderView):
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

    def _create_select_all_checkbox(self, parent):
        return CheckBox(parent)

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
        checkbox.setStyleSheet(
            checkbox.styleSheet() + "\nCheckBox#fileTreeSelectAllCheckbox {"
            " min-width: 16px; min-height: 16px; padding: 0; margin: 0; }"
        )
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


class CompactHeaderCheckBox(CheckBox):
    """以与文件行相同的 16px Fluent 样式绘制表头全选框。"""

    INDICATOR_SIZE = 16

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


def table_widget(headers, parent, table_class=TableWidget, *, stretch_last=True):
    """创建统一的只读、按行选择的表格控件。

    Args:
        headers: 表头文本列表。
        parent: 父控件。
        table_class: 表格子类，默认 ``TableWidget``。
        stretch_last: 是否让最后一列自适应剩余宽度。
    """
    table = table_class(parent)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setWordWrap(False)
    table.setBorderVisible(True)
    table.setBorderRadius(CONTROL_CORNER_RADIUS)
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


class NetworkPage(Page):
    """带目标输入区、内容区和任务底栏的网络操作页面。"""

    def __init__(self, name, title, state, button_text, parent=None):
        super().__init__(name, parent)
        page_heading(self.vbox, title)
        self.target_card = SectionCard(self)
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
