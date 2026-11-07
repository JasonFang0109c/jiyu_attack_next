"""全员缩略图窗口：把一轮收集到的学生缩略图排成网格。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CaptionLabel, SimpleCardWidget, StrongBodyLabel, TitleLabel

THUMBNAIL_WIDTH = 320
THUMBNAIL_HEIGHT = 180
COLUMNS = 3
WINDOW_SIZE = (1120, 720)


class PreviewGridWindow(QWidget):
    """按网格展示每台学生机的最新缩略图。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("全员缩略图")
        self.resize(*WINDOW_SIZE)
        self._cards = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(TitleLabel("全员缩略图", self))
        self.summary = CaptionLabel("暂无数据", self)
        layout.addWidget(self.summary)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget(self._scroll)
        self._grid = QGridLayout(container)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(container)
        layout.addWidget(self._scroll, 1)

    def set_records(self, records):
        """重建网格。

        Args:
            records: 学生记录列表，用 ``address``、``info`` 与 ``preview`` 渲染。
        """
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        items = list(records or [])
        received = 0
        for index, record in enumerate(items):
            card = self._build_card(record)
            if record.get("preview"):
                received += 1
            self._grid.addWidget(card, index // COLUMNS, index % COLUMNS)
            self._cards.append(card)
        self.summary.setText(
            "共 %d 台学生机，收到缩略图 %d 台" % (len(items), received)
        )

    def _build_card(self, record):
        """按单条学生记录拼一张缩略图卡片。"""
        card = SimpleCardWidget(self._scroll)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        address = record.get("address") or "未知地址"
        layout.addWidget(StrongBodyLabel(address, card))
        info = record.get("info") or {}
        detail = " / ".join(
            part
            for part in (info.get("name"), info.get("user"), info.get("os"))
            if part
        )
        layout.addWidget(CaptionLabel(detail or "未上报系统信息", card))

        image = QLabel(card)
        image.setFixedSize(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setFrameShape(QFrame.Shape.StyledPanel)
        data = record.get("preview")
        pixmap = QPixmap()
        if data and pixmap.loadFromData(data):
            image.setPixmap(
                pixmap.scaled(
                    THUMBNAIL_WIDTH,
                    THUMBNAIL_HEIGHT,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            image.setText("未收到缩略图" if not data else "缩略图无法解析")
        layout.addWidget(image)
        return card
