"""Fluent 界面共用的连接参数、页面标题与任务栏。"""

from PySide6.QtCore import QRegularExpression, QSignalBlocker, QSize, Qt, Signal, Slot
from PySide6.QtGui import QIntValidator, QRegularExpressionValidator
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, ComboBox, Dialog, DoubleSpinBox,
                            FluentIcon, IndeterminateProgressRing, LineEdit,
                            PrimaryPushButton, PushButton, SimpleCardWidget, SpinBox,
                            SubtitleLabel, ToolButton, ToolTipFilter, ToolTipPosition)

from cli import main as core


def tool_button(icon, text, parent, callback):
    button = ToolButton(icon, parent)
    button.setToolTip(text)
    button.setAccessibleName(text)
    button.setFixedSize(34, 34)
    button.installEventFilter(ToolTipFilter(button, showDelay=300, position=ToolTipPosition.TOP))
    button.clicked.connect(lambda checked=False: callback())
    return button


def info_button(text, parent):
    """创建带 Fluent 悬停提示的信息图标按钮。"""
    button = ToolButton(FluentIcon.INFO, parent)
    button.setObjectName("pageInfoButton")
    button.setAccessibleName("查看说明")
    button.setAccessibleDescription(text)
    button.setToolTip(text)
    button.setFixedSize(28, 28)
    button.setIconSize(QSize(16, 16))
    button.installEventFilter(ToolTipFilter(button, showDelay=300,
                                            position=ToolTipPosition.TOP))
    return button


def page_heading(layout, title, action=None):
    row = QHBoxLayout()
    row.setSpacing(12)
    row.addWidget(SubtitleLabel(title))
    row.addStretch()
    if action is not None:
        row.addWidget(action)
    layout.addLayout(row)


class SectionCard(SimpleCardWidget):
    """带圆角与内边距的页面功能分区。"""

    def __init__(self, parent=None, spacing=12, margins=(20, 18, 20, 18)):
        super().__init__(parent)
        self.setBorderRadius(12)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(spacing)


class _SpinEditorGeometry:
    # 当前 Qt 版本会将 Fluent 步进框的编辑区域压缩为 1px。
    def _restore_editor(self):
        if not hasattr(self, "upButton"):
            return
        editor = self.lineEdit()
        if editor is not None and editor.width() <= 1:
            editor.setGeometry(11, 1, max(1, self.width() - 91), self.height() - 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._restore_editor()

    def showEvent(self, event):
        super().showEvent(event)
        self._restore_editor()

    def changeEvent(self, event):
        super().changeEvent(event)
        self._restore_editor()


class ReadableSpinBox(_SpinEditorGeometry, SpinBox):
    pass


class ReadableDoubleSpinBox(_SpinEditorGeometry, DoubleSpinBox):
    pass


class Ipv4TargetInput(QWidget):
    """四段式 IPv4 目标输入框。"""

    textChanged = Signal(str)
    nextFieldRequested = Signal()

    SEGMENT_WIDTHS = (64, 64, 64, 148)
    PLACEHOLDERS = ("192", "168", "1", "20、1-10、0/24")

    def __init__(self, parent=None, object_name="targetAddressInput", field_label="目标地址"):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.segments = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        last_validator = QRegularExpressionValidator(
            QRegularExpression(r"[0-9]{0,3}(?:-[0-9]{0,3}|/[0-9]{0,2})?"), self
        )
        for index, width in enumerate(self.SEGMENT_WIDTHS):
            if index:
                dot = BodyLabel(".", self)
                dot.setAlignment(Qt.AlignCenter)
                dot.setFixedWidth(4)
                layout.addWidget(dot)
            edit = LineEdit(self)
            edit.setObjectName("%sSegment%d" % (object_name, index + 1))
            edit.setAccessibleName("%s第 %d 段" % (field_label, index + 1))
            edit.setAlignment(Qt.AlignCenter)
            edit.setFixedWidth(width)
            edit.setMaxLength(3 if index < 3 else 8)
            edit.setPlaceholderText(self.PLACEHOLDERS[index])
            if index < 3:
                edit.setValidator(QIntValidator(0, 255, edit))
                edit.setToolTip("IPv4 第 %d 段（0–255）" % (index + 1))
            else:
                edit.setValidator(last_validator)
                edit.setToolTip("最后一段 IPv4、末段范围或 /24 网段")
            edit.textChanged.connect(self._segments_changed)
            edit.returnPressed.connect(lambda key=index: self._advance(key))
            layout.addWidget(edit)
            self.segments.append(edit)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setMinimumWidth(sum(self.SEGMENT_WIDTHS) + 42)

    def text(self):
        return ".".join(edit.text() for edit in self.segments)

    def setText(self, value):
        value = str(value or "").strip()
        if not value:
            parts = ("", "", "", "")
        elif "." in value:
            raw_parts = value.split(".", 3)
            parts = tuple((raw_parts + [""] * 4)[:4])
        elif value.isdigit() or "-" in value or "/" in value:
            parts = (value, "", "", "")
        else:
            parts = ("", "", "", "")
        changed = False
        for edit, part in zip(self.segments, parts):
            if edit.text() == part:
                continue
            edit.blockSignals(True)
            edit.setText(part)
            edit.blockSignals(False)
            changed = True
        if changed:
            self.textChanged.emit(self.text())

    def clear(self):
        self.setText("")

    def is_complete(self):
        return all(edit.text().strip() for edit in self.segments)

    def setError(self, is_error):
        for edit in self.segments:
            edit.setError(bool(is_error))

    @Slot(str)
    def _segments_changed(self, value):
        self.textChanged.emit(self.text())

    def _advance(self, index):
        if index < len(self.segments) - 1:
            target = self.segments[index + 1]
            target.setFocus()
            target.selectAll()
        else:
            self.nextFieldRequested.emit()


class TargetControls(QWidget):
    def __init__(self, state, parent=None, show_round_options=True):
        super().__init__(parent)
        self.state = state
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        heading.addWidget(BodyLabel("目标设备", self))
        heading.addStretch()
        self.target_count = CaptionLabel("0 个目标", self)
        heading.addWidget(self.target_count)
        layout.addLayout(heading)

        self.target_input = Ipv4TargetInput(self)
        self.device_button = PushButton("选择设备", self)
        self.device_button.setIcon(FluentIcon.PEOPLE)
        self.device_button.setMinimumWidth(106)
        self.device_button.setToolTip("从设备备注中选择目标")
        self.device_button.clicked.connect(self.choose_device)
        self.port_input = ReadableSpinBox(self)
        self.port_input.setRange(1, 65535)
        self.port_input.setFixedWidth(152)
        self.loop_input = ReadableSpinBox(self)
        self.loop_input.setRange(1, 10000)
        self.loop_input.setFixedWidth(136)
        self.interval_input = ReadableDoubleSpinBox(self)
        self.interval_input.setRange(0, 86400)
        self.interval_input.setDecimals(1)
        self.interval_input.setFixedWidth(160)
        self.fields = {"target": self.target_input, "port": self.port_input,
                       "loops": self.loop_input, "interval": self.interval_input}
        self.port_input.setValue(state.values["port"])
        self.loop_input.setValue(state.values["loops"])
        self.interval_input.setValue(state.values["interval"])
        if not show_round_options:
            self.loop_input.hide()
            self.interval_input.hide()
        self.target_input.setText(state.resolve_target(state.values["target"]))

        target_column = QVBoxLayout()
        target_column.setSpacing(6)
        target_column.addWidget(CaptionLabel("目标地址", self))
        target_row = QHBoxLayout()
        target_row.setSpacing(8)
        target_row.addWidget(self.target_input)
        target_row.addWidget(self.device_button)
        target_row.addStretch()
        target_column.addLayout(target_row)
        layout.addLayout(target_column)

        options_row = QHBoxLayout()
        options_row.setSpacing(12)
        labels = {"port": "UDP 端口", "loops": "发送轮数", "interval": "间隔（秒）"}
        option_names = ("port", "loops", "interval") if show_round_options else ("port",)
        for name in option_names:
            field = self.fields[name]
            column = QVBoxLayout()
            column.setSpacing(6)
            column.addWidget(CaptionLabel(labels[name], self))
            column.addWidget(field)
            options_row.addLayout(column)
        options_row.addStretch()
        layout.addLayout(options_row)

        self.alias_hint = CaptionLabel("", self)
        self.alias_hint.hide()
        layout.addWidget(self.alias_hint)

        self.target_input.textChanged.connect(lambda value: state.set_value("target", value))
        self.port_input.valueChanged.connect(lambda value: state.set_value("port", value))
        self.loop_input.valueChanged.connect(lambda value: state.set_value("loops", value))
        self.interval_input.valueChanged.connect(lambda value: state.set_value("interval", value))
        self.target_input.nextFieldRequested.connect(self._focus_options)
        state.changed.connect(self._on_changed)
        state.aliases.changed.connect(self._aliases_changed)
        self._set_tab_order()
        self._update_count()
        self.interval_input.setEnabled(state.values["loops"] > 1)

    def _set_tab_order(self):
        segments = self.target_input.segments
        for current, following in zip(segments, segments[1:]):
            QWidget.setTabOrder(current, following)
        QWidget.setTabOrder(segments[-1], self.device_button)
        QWidget.setTabOrder(self.device_button, self.port_input)
        QWidget.setTabOrder(self.port_input, self.loop_input)
        QWidget.setTabOrder(self.loop_input, self.interval_input)

    def _focus_options(self):
        self.port_input.setFocus()
        self.port_input.selectAll()

    @Slot()
    def _aliases_changed(self):
        matched = self.state.aliases.match(self.state.values["target"])
        if matched is not None:
            with QSignalBlocker(self.target_input):
                if self.target_input.text() != matched[1]:
                    self.target_input.setText(matched[1])
        self._update_count()

    def choose_device(self):
        if not self.state.aliases.items():
            self._show_empty_alias_dialog()
            return
        dialog, selector = self._create_device_dialog()
        if dialog.exec():
            name = selector.currentData()
            if name:
                self.state.set_value("target", name)

    def _show_empty_alias_dialog(self):
        dialog = Dialog("选择设备", "还没有设备备注，请先在“设备备注”页面添加。", self)
        dialog.cancelButton.hide()
        dialog.yesButton.setText("知道了")
        dialog.setFixedSize(360, 196)
        dialog.exec()

    def _create_device_dialog(self):
        dialog = Dialog("选择设备", "选择一个设备备注作为当前目标：", self)
        dialog.setFixedSize(420, 236)
        selector = ComboBox(dialog)
        selector.setMinimumWidth(340)
        for name, address in self.state.aliases.items():
            selector.addItem("%s  ·  %s" % (name, address), userData=name)
        current = self.state.aliases.match(self.state.values["target"])
        if current is not None:
            index = selector.findData(current[0])
            if index >= 0:
                selector.setCurrentIndex(index)
        dialog.textLayout.addWidget(selector)
        dialog.yesButton.setText("选择")
        dialog.cancelButton.setText("取消")
        return dialog, selector

    @Slot(str, object)
    def _on_changed(self, name, value):
        field = self.fields[name]
        if name == "target":
            display = self.state.resolve_target(value) if str(value).strip() else ""
            with QSignalBlocker(field):
                if field.text() != display:
                    field.setText(display)
                field.setError(False)
                self._update_count()
        else:
            with QSignalBlocker(field):
                if field.value() != value:
                    field.setValue(value)
        self.interval_input.setEnabled(self.state.values["loops"] > 1)

    def _update_alias_hint(self, text):
        matched = self.state.aliases.match(text)
        if matched:
            self.alias_hint.setText("备注「%s」→ %s" % matched)
            self.alias_hint.show()
        else:
            self.alias_hint.hide()

    def _update_count(self):
        text = self.state.values["target"].strip()
        self._update_alias_hint(text)
        if not text:
            self.target_count.setText("0 个目标")
            self.target_input.setError(False)
            return
        try:
            count = len(core.get_ip(self.state.resolve_target(text)))
        except ValueError:
            self.target_count.setText("地址未完成")
            self.target_input.setError(self.target_input.is_complete())
        else:
            self.target_count.setText("%d 个目标" % count)
            self.target_input.setError(False)


class TaskFooter(QWidget):
    requested = Signal()
    cancelled = Signal()
    viewLogs = Signal()

    def __init__(self, button_text, parent=None, icon=FluentIcon.SEND):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)
        self.ring = IndeterminateProgressRing(self, start=False)
        self.ring.setFixedSize(18, 18)
        self.ring.setStrokeWidth(2)
        self.ring.hide()
        self.status = CaptionLabel("", self)
        self.status.hide()
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.status.setMinimumWidth(0)
        self.status.setWordWrap(True)
        self.log_button = tool_button(FluentIcon.HISTORY, "查看运行日志", self, self.viewLogs.emit)
        self.log_button.setVisible(False)
        self.cancel_button = PushButton("取消", self)
        self.cancel_button.setIcon(FluentIcon.CANCEL)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setMinimumWidth(92)
        self.send_button = PrimaryPushButton(button_text, self)
        self.send_button.setIcon(icon)
        self.send_button.setMinimumWidth(130)
        self.send_button.setMinimumHeight(36)
        self.cancel_button.clicked.connect(lambda checked=False: self.cancelled.emit())
        self.send_button.clicked.connect(lambda checked=False: self.requested.emit())
        layout.addWidget(self.ring)
        layout.addWidget(self.status, 1)
        layout.addWidget(self.log_button)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.send_button)

    def set_busy(self, busy, cancellable=False):
        self.send_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy and cancellable)
        self.ring.setVisible(busy)
        if busy:
            self.ring.start()
        else:
            self.ring.stop()

    def set_status(self, text=""):
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def finish_status(self):
        self.status.hide()
