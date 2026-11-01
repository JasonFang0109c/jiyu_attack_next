"""按功能组织的 Fluent 工作页面。"""

from importlib.metadata import version
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QSignalBlocker,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QFont, QIcon, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTableWidgetItem,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    ComboBox,
    Dialog,
    FluentIcon as FIF,
    HyperlinkButton,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    RadioButton,
    SearchLineEdit,
    SmoothScrollArea,
    StrongBodyLabel,
    SwitchButton,
    TableWidget,
    Theme,
    TitleLabel,
    TreeItemDelegate,
    TreeWidget,
    qconfig,
    setFont,
)
from qfluentwidgets.components.widgets.check_box import CheckBoxIcon

from ... import core
from ..build_info import build_time_text, version_text
from ..models import LOG_LEVELS, normalize_log_level
from ..components import (
    Ipv4TargetInput,
    SectionCard,
    TargetControls,
    TaskFooter,
    info_button,
    page_heading,
    tool_button,
)

ASSET_ROOT = Path(__file__).resolve().parents[3] / "assets"


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
        if not self.isVisible():
            return
        x = (
            self.sectionViewportPosition(0)
            + (self.sectionSize(0) - self.CHECKBOX_SIZE) // 2
        )
        y = (self.height() - self.CHECKBOX_SIZE) // 2
        self.select_all_checkbox.move(x, y)

    def resizeEvent(self, event):
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = self.INDICATOR_SIZE
        rect = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
        painter.setPen(self._borderColor())
        painter.setBrush(self._backgroundColor())
        radius = 4.5 * size / 19
        painter.drawRoundedRect(rect, radius, radius)
        if not self.isEnabled():
            painter.setOpacity(0.8)
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
        if event.type() == QEvent.Type.MouseMove:
            position = event.position().toPoint()
            item = self.itemAt(position) if self.columnAt(position.x()) == 0 else None
            self._set_hover_item(item)
        elif event.type() == QEvent.Type.Leave:
            self._set_hover_item(None)
        return super().viewportEvent(event)

    def _set_hover_item(self, item):
        if item is self._hover_item:
            return
        self._hover_item = item
        self.hoverItemChanged.emit(item)

    def reset_hover_item(self):
        self._hover_item = None


class LogTableWidget(TableWidget):
    """日志表固定元数据列，内容列按剩余宽度自适应。"""

    FIXED_COLUMNS = (0, 1, 2, 3, 5, 6)
    MIN_CONTENT_WIDTH = 120

    def resizeEvent(self, event):
        super().resizeEvent(event)
        reserved = sum(self.columnWidth(column) for column in self.FIXED_COLUMNS)
        self.setColumnWidth(
            4, max(self.MIN_CONTENT_WIDTH, self.viewport().width() - reserved)
        )


def table_widget(headers, parent, table_class=TableWidget):
    table = table_class(parent)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setWordWrap(False)
    table.setBorderVisible(True)
    table.setBorderRadius(6)
    table.horizontalHeader().setStretchLastSection(True)
    return table


class Page(QWidget):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self.vbox = QVBoxLayout(self)
        self.vbox.setContentsMargins(28, 24, 28, 24)
        self.vbox.setSpacing(20)


class NetworkPage(Page):
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
        self.targets.setEnabled(not busy)
        self.footer.set_busy(busy, cancellable, queueable)
