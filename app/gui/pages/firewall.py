"""防火墙页：阻断或恢复 StudentMain.exe 的联网规则。"""

from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QTableWidgetItem
from qfluentwidgets import BodyLabel, ComboBox, setFont
from qfluentwidgets import FluentIcon as FIF

from ..components import SectionCard, TaskFooter, page_heading
from .common import Page, table_widget


class FirewallPage(Page):
    """选择阻断或恢复，并逐条展示 netsh 的执行结果。"""

    def __init__(self, parent=None):
        super().__init__("firewall", parent)
        page_heading(self.vbox, "防火墙")
        row = QHBoxLayout()
        row.addWidget(BodyLabel("规则", self))
        rule = BodyLabel("StudentMain.exe", self)
        setFont(rule, 16)
        row.addWidget(rule)
        row.addStretch()
        self.action_box = ComboBox(self)
        self.action_box.addItems(["阻断连接", "恢复允许"])
        self.action_box.setMinimumWidth(170)
        row.addWidget(self.action_box)
        self.content_card = SectionCard(self)
        self.content_card.body.addLayout(row)
        self.content_card.body.addWidget(BodyLabel("操作结果", self.content_card))
        self.result_table = table_widget(["操作", "结果", "输出"], self.content_card)
        self.result_table.setColumnWidth(0, 180)
        self.result_table.setColumnWidth(1, 80)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.setWordWrap(True)
        self.result_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.content_card.body.addWidget(self.result_table, 1)
        self.vbox.addWidget(self.content_card, 1)
        self.footer_card = SectionCard(self, spacing=0, margins=(8, 8, 8, 8))
        self.footer = TaskFooter("应用规则", self.footer_card, FIF.CERTIFICATE)
        self.footer.cancel_button.hide()
        self.footer_card.body.addWidget(self.footer)
        self.vbox.addWidget(self.footer_card)

    def action(self):
        """返回下拉框对应的防火墙动作（block/allow）。"""
        return "block" if self.action_box.currentIndex() == 0 else "allow"

    def set_result(self, results):
        """把助手进程返回的执行结果填进结果表。"""
        self.result_table.setRowCount(len(results))
        labels = ["防火墙服务", "启用防火墙", "目标规则"]
        for row, result in enumerate(results):
            text = result["stdout"] or result["stderr"]
            success = result["success"]
            prefixes = [
                "net.exe",
                "netsh advfirewall set",
                "netsh advfirewall firewall",
            ]
            label = next(
                (
                    item
                    for item, prefix in zip(labels, prefixes, strict=True)
                    if result["command"].startswith(prefix)
                ),
                labels[-1],
            )
            for column, value in enumerate(
                [label, "成功" if success else "失败", text]
            ):
                item = QTableWidgetItem(
                    value.replace("\r\n", "\n").replace("\r", "\n").strip()
                )
                item.setToolTip(value)
                self.result_table.setItem(row, column, item)
            self.result_table.setRowHeight(
                row, max(38, self.result_table.sizeHintForRow(row))
            )
