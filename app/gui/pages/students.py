"""学生信息页：发现学生机，查看系统信息、进程、窗口与屏幕缩略图。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidgetItem,
)
from qfluentwidgets import BodyLabel, ComboBox, PushButton
from qfluentwidgets import FluentIcon as FIF

from ..components import (
    ReadableSpinBox,
    SectionCard,
    TaskFooter,
    page_heading,
    tool_button,
)
from .common import Page, table_widget

INFO_COLUMNS = ["地址", "计算机名", "登录用户", "系统", "CPU", "内存"]
DETAIL_KINDS = (("processes", "进程"), ("windows", "窗口"))


class StudentsPage(Page):
    """展示发现到的学生机，并按需查看进程或窗口。"""

    discoverRequested = Signal()
    refreshRequested = Signal()
    killRequested = Signal()
    previewRequested = Signal()
    viewRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("students", parent)
        page_heading(self.vbox, "学生信息")
        # 这一页扮演教师端，标题下先说清身份，免得和真实教师机混淆。
        self.vbox.addWidget(BodyLabel("教师端模拟：向学生端宣告并发起登录握手。", self))

        config_row = QHBoxLayout()
        config_row.addWidget(BodyLabel("频道", self))
        self.channel_input = ReadableSpinBox(self)
        self.channel_input.setRange(1, 32)
        self.channel_input.setValue(1)
        self.channel_input.setMinimumWidth(110)
        config_row.addWidget(self.channel_input)
        config_row.addSpacing(12)
        config_row.addWidget(BodyLabel("教师名", self))
        self.teacher_input = QLineEdit("1", self)
        self.teacher_input.setPlaceholderText("学生端上显示的教师名")
        self.teacher_input.setMaximumWidth(220)
        config_row.addWidget(self.teacher_input)
        config_row.addStretch()
        self.vbox.addLayout(config_row)

        self.content_card = SectionCard(self)
        self.content_card.body.addWidget(
            BodyLabel(
                "点“发现学生”会以教师端模拟身份发送宣告并监听登录请求，"
                "收到登录后自动应答并拉取系统信息。选中学生后可刷新缩略图；"
                "点“观看屏幕”打开的窗口里再点“接管键鼠”，就能直接操作那台机器。",
                self.content_card,
            )
        )
        self.students = table_widget(INFO_COLUMNS, self.content_card)
        self.students.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.students.setSelectionMode(QAbstractItemView.SingleSelection)
        self.students.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.students.horizontalHeader().setStretchLastSection(True)
        self.content_card.body.addWidget(self.students, 1)

        detail_row = QHBoxLayout()
        detail_row.addWidget(BodyLabel("详细信息", self.content_card))
        self.detail_box = ComboBox(self.content_card)
        for _code, _label in DETAIL_KINDS:
            self.detail_box.addItem(_label)
        self.detail_box.setMinimumWidth(120)
        detail_row.addWidget(self.detail_box)
        detail_row.addStretch()
        self.refresh_button = tool_button(
            FIF.SYNC, "刷新所选学生", self.content_card, self.refreshRequested.emit
        )
        self.kill_button = tool_button(
            FIF.DELETE, "结束所选进程", self.content_card, self.killRequested.emit
        )
        # 这两个是这一页新增的入口，按钮直接写文字，免得只有图标认不出来。
        self.preview_button = PushButton(FIF.CAMERA, "刷新缩略图", self.content_card)
        self.preview_button.clicked.connect(self.previewRequested.emit)
        self.view_button = PushButton(FIF.VIDEO, "观看屏幕", self.content_card)
        self.view_button.clicked.connect(self.viewRequested.emit)
        detail_row.addWidget(self.preview_button)
        detail_row.addWidget(self.view_button)
        detail_row.addSpacing(8)
        detail_row.addWidget(self.refresh_button)
        detail_row.addWidget(self.kill_button)
        self.content_card.body.addLayout(detail_row)

        self.details = table_widget(["编号", "名称"], self.content_card)
        self.details.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.details.setSelectionMode(QAbstractItemView.SingleSelection)
        self.details.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.details.setColumnWidth(0, 120)
        self.details.horizontalHeader().setStretchLastSection(True)
        self.content_card.body.addWidget(self.details, 1)

        # 缩略图由学生端推上来，拿到就是完整 JPEG，这里只负责显示。
        self.preview_label = QLabel("选中学生后可拉取屏幕缩略图", self.content_card)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(160)
        self.preview_label.setScaledContents(False)
        self.content_card.body.addWidget(self.preview_label)
        self.vbox.addWidget(self.content_card, 1)

        self.footer_card = SectionCard(self, spacing=0, margins=(8, 8, 8, 8))
        self.footer = TaskFooter("发现学生", self.footer_card, FIF.PEOPLE)
        self.footer.cancel_button.hide()
        self.footer_card.body.addWidget(self.footer)
        self.vbox.addWidget(self.footer_card)

        self.records = []
        self.students.itemSelectionChanged.connect(self._selection_changed)
        self.detail_box.currentIndexChanged.connect(
            lambda _index: self._refresh_details()
        )

    def set_preview(self, data):
        """显示缩略图字节，没有数据时回到提示文案。

        Args:
            data: JPEG 字节，或 ``None``。
        """
        if not data:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("暂无缩略图，点“刷新缩略图”重新拉取")
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("缩略图数据无法解析")
            return
        self.preview_label.setText("")
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def detail_kind(self):
        """返回当前查看的详情类型（processes/windows）。"""
        return DETAIL_KINDS[self.detail_box.currentIndex()][0]

    def set_students(self, records):
        """填入发现结果，并保留原选中行的地址。"""
        selected = self.selected_address()
        self.records = list(records or [])
        self.students.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            info = record.get("info") or {}
            values = [
                record.get("address", ""),
                info.get("name", ""),
                info.get("user", ""),
                " ".join(
                    part for part in (info.get("os"), info.get("os_version")) if part
                ),
                " ".join(
                    part
                    for part in (info.get("cpu_vendor"), info.get("cpu_model"))
                    if part
                ),
                info.get("memory", ""),
            ]
            for column, value in enumerate(values):
                self.students.setItem(row, column, QTableWidgetItem(value))
            self.students.setRowHeight(row, 36)
        self._refresh_details()
        self._refresh_preview()
        if selected:
            for row, record in enumerate(self.records):
                if record.get("address") == selected:
                    self.students.selectRow(row)
                    break

    def _refresh_preview(self):
        """按当前选中的学生刷新缩略图，顺手开关相关按钮。"""
        record = self.selected_record()
        self.set_preview(record.get("preview") if record else None)
        has_selection = record is not None
        self.preview_button.setEnabled(has_selection)
        self.view_button.setEnabled(has_selection)

    def selected_record(self):
        """返回当前选中的学生记录，未选中时为 None。"""
        rows = self.students.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        if 0 <= index < len(self.records):
            return self.records[index]
        return None

    def selected_address(self):
        """返回当前选中学生的地址，未选中时为空。"""
        record = self.selected_record()
        return record.get("address", "") if record else ""

    def _selection_changed(self):
        self._refresh_details()
        self._refresh_preview()

    def _refresh_details(self):
        """按选中学生与类型重建详情表。"""
        record = self.selected_record()
        entries = []
        if record:
            entries = record.get(self.detail_kind()) or []
        self.details.setRowCount(len(entries))
        for row, (identifier, name) in enumerate(entries):
            self.details.setItem(row, 0, QTableWidgetItem(str(identifier)))
            self.details.setItem(row, 1, QTableWidgetItem(name))
            self.details.setRowHeight(row, 34)
        self.kill_button.setEnabled(bool(entries) and self.detail_kind() == "processes")

    def selected_detail_id(self):
        """返回详情表当前行的编号，未选中时为 None。"""
        rows = self.details.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.details.item(rows[0].row(), 0)
        if item is None or not item.text().isdigit():
            return None
        return int(item.text())
