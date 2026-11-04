"""本机信息页：显示本机 IP 与 Student 端监听的 UDP 端口。"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QTableWidgetItem
from qfluentwidgets import BodyLabel, setFont
from qfluentwidgets import FluentIcon as FIF

from ..components import SectionCard, TaskFooter, page_heading, tool_button
from .common import Page, table_widget


class LocalPage(Page):
    """展示查询结果，并允许一键复制本机 IP。"""

    copyRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("local", parent)
        page_heading(self.vbox, "本机信息")
        row = QHBoxLayout()
        row.addWidget(BodyLabel("本机 IP", self))
        self.ip_label = BodyLabel("未查询", self)
        setFont(self.ip_label, 18)
        row.addWidget(self.ip_label)
        row.addStretch()
        self.copy_button = tool_button(
            FIF.COPY, "复制本机 IP", self, self.copyRequested.emit
        )
        self.copy_button.setEnabled(False)
        row.addWidget(self.copy_button)
        self.content_card = SectionCard(self)
        self.content_card.body.addLayout(row)
        self.content_card.body.addWidget(
            BodyLabel("Student 监听端口", self.content_card)
        )
        self.port_table = table_widget(["协议", "端口"], self.content_card)
        self.port_table.setColumnWidth(0, 140)
        self.content_card.body.addWidget(self.port_table, 1)
        self.vbox.addWidget(self.content_card, 1)
        self.footer_card = SectionCard(self, spacing=0, margins=(8, 8, 8, 8))
        self.footer = TaskFooter("查询本机", self.footer_card, FIF.SEARCH)
        self.footer.cancel_button.hide()
        self.footer_card.body.addWidget(self.footer)
        self.vbox.addWidget(self.footer_card)

    def set_result(self, ip, ports):
        """填入查询到的本机 IP 与监听端口。"""
        self.ip_label.setText(ip or "未获取")
        self.copy_button.setEnabled(bool(ip))
        self.port_table.setRowCount(len(ports))
        for row, port in enumerate(ports):
            self.port_table.setItem(row, 0, QTableWidgetItem("UDP"))
            self.port_table.setItem(row, 1, QTableWidgetItem(port))
            self.port_table.setRowHeight(row, 38)
