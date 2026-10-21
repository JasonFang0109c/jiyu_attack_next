"""Fluent 界面共用的连接参数、页面标题与任务栏。"""

from PySide6.QtCore import QSignalBlocker, Qt, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, ComboBox, Dialog, DoubleSpinBox,
                            FluentIcon, IndeterminateProgressRing, LineEdit,
                            PrimaryPushButton, PushButton, SpinBox, SubtitleLabel,
                            ToolButton, ToolTipFilter, ToolTipPosition)

from cli import main as core


def tool_button(icon, text, parent, callback):
    button = ToolButton(icon, parent)
    button.setToolTip(text)
    button.setAccessibleName(text)
    button.setFixedSize(34, 34)
    button.installEventFilter(ToolTipFilter(button, showDelay=300, position=ToolTipPosition.TOP))
    button.clicked.connect(lambda checked=False: callback())
    return button


def page_heading(layout, title, action=None):
    row = QHBoxLayout()
    row.setSpacing(12)
    row.addWidget(SubtitleLabel(title))
    row.addStretch()
    if action is not None:
        row.addWidget(action)
    layout.addLayout(row)


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


class TargetControls(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        heading.addWidget(BodyLabel("目标设备", self))
        heading.addStretch()
        self.target_count = CaptionLabel("0 个目标", self)
        heading.addWidget(self.target_count)
        layout.addLayout(heading)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.target_input = LineEdit(self)
        self.target_input.setPlaceholderText("IPv4、末段范围或 /24 网段")
        self.target_input.setClearButtonEnabled(True)
        # 窄窗口下允许目标框收缩，避免覆盖右侧的选择设备按钮。
        self.target_input.setMinimumWidth(160)
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
        labels = {"target": "目标地址", "port": "UDP 端口",
                  "loops": "发送轮数", "interval": "间隔（秒）"}
        for name, field in self.fields.items():
            column = QVBoxLayout()
            column.setSpacing(6)
            column.addWidget(CaptionLabel(labels[name], self))
            if name == "target":
                target_row = QHBoxLayout()
                target_row.setSpacing(8)
                target_row.addWidget(field, 1)
                target_row.addWidget(self.device_button)
                column.addLayout(target_row)
            else:
                column.addWidget(field)
            row.addLayout(column, 1 if name == "target" else 0)
            if name == "target":
                field.setText(state.values[name])
                field.textChanged.connect(lambda value: state.set_value("target", value))
            else:
                field.setValue(state.values[name])
                field.valueChanged.connect(lambda value, key=name: state.set_value(key, value))
        layout.addLayout(row)
        self.alias_hint = CaptionLabel("", self)
        self.alias_hint.hide()
        layout.addWidget(self.alias_hint)
        self.target_input.textChanged.connect(lambda value: self._update_alias_hint(value))
        state.changed.connect(self._on_changed)
        state.aliases.changed.connect(self._aliases_changed)
        self._update_count()
        self.interval_input.setEnabled(state.values["loops"] > 1)

    @Slot()
    def _aliases_changed(self):
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
        with QSignalBlocker(field):
            if name == "target":
                if field.text() != value:
                    field.setText(value)
                field.setError(False)
                self._update_count()
            elif field.value() != value:
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
        try:
            count = len(core.get_ip(self.state.resolve_target(text))) if text else 0
            self.target_count.setText("%d 个目标" % count)
        except ValueError:
            self.target_count.setText("地址未完成")


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
