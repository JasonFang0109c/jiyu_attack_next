"""Fluent 界面共用的连接参数、页面标题与任务栏。"""

from itertools import pairwise

from PySide6.QtCore import (
    QEvent,
    QRect,
    QRegularExpression,
    QSignalBlocker,
    QSize,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QIntValidator, QRegularExpressionValidator, QScreen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    Dialog,
    DoubleSpinBox,
    FluentIcon,
    IndeterminateProgressRing,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SimpleCardWidget,
    SpinBox,
    SubtitleLabel,
    ToolButton,
    ToolTipFilter,
    ToolTipPosition,
)

from .. import core


def tool_button(icon, text, parent, callback):
    """创建统一的 34×34 图标按钮，悬停时显示 Fluent 提示。"""
    button = ToolButton(icon, parent)
    button.setToolTip(text)
    button.setAccessibleName(text)
    button.setFixedSize(34, 34)
    button.installEventFilter(
        ToolTipFilter(button, showDelay=300, position=ToolTipPosition.TOP)
    )
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
    button.installEventFilter(
        ToolTipFilter(button, showDelay=300, position=ToolTipPosition.TOP)
    )
    return button


def center_dialog(dialog):
    """把对话框对齐到主窗口中心，并保证完整落在屏幕上。

    ``Dialog`` 是独立的顶层窗口，Qt 只会按屏幕摆放，主窗口移动后弹窗
    就偏离父窗口中心；这里在 ``exec()`` 前按主窗口外框（含标题栏）修正，
    再把结果夹回屏幕可用区域，避免主窗口贴边时弹窗一半跑到屏幕外。
    弹窗的父对象往往是页面里的子控件，``frameGeometry()`` 此时是父控件
    坐标系下的值，所以统一上溯到主窗口再取全局坐标。
    """
    parent = dialog.parentWidget()
    window = parent.window() if parent is not None else None
    area = window.frameGeometry() if isinstance(window, QWidget) else None
    screen = (window.screen() if isinstance(window, QWidget) else None) or (
        dialog.screen()
    )
    # 测试会用替身对象整体替换 Dialog，此时屏幕与窗口几何都不是真实对象。
    if not isinstance(screen, QScreen):
        screen = None
    if not isinstance(area, QRect) or not area.isValid():
        if screen is None:
            return
        area = screen.availableGeometry()
    bounds = screen.availableGeometry() if screen is not None else None
    target = area.center() - dialog.rect().center()
    if bounds is not None:
        target.setX(
            min(
                max(target.x(), bounds.left()),
                bounds.right() - dialog.width() + 1,
            )
        )
        target.setY(
            min(
                max(target.y(), bounds.top()),
                bounds.bottom() - dialog.height() + 1,
            )
        )
    dialog.move(target)


def page_heading(layout, title, action=None):
    """在页面顶部插入“标题 + 右侧操作区”的一行。"""
    row = QHBoxLayout()
    row.setSpacing(12)
    row.addWidget(SubtitleLabel(title))
    row.addStretch()
    if action is not None:
        row.addWidget(action)
    layout.addLayout(row)


# Fluent 2 的形状令牌里，Large 是 8 像素，用于卡片这类大号容器；
# 12 像素属于 X-Large，只留给按钮面板与浮出层，卡片用它会显得过圆。
CORNER_RADIUS = 8


class SectionCard(SimpleCardWidget):
    """带圆角与内边距的页面功能分区。"""

    def __init__(self, parent=None, spacing=12, margins=(20, 18, 20, 18)):
        super().__init__(parent)
        self.setBorderRadius(CORNER_RADIUS)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(spacing)


class _SpinEditorGeometry:
    """修复 Fluent 步进框的编辑区域被压缩的问题。

    当前 Qt 版本下编辑区会被压成 1px 宽，输入内容不可见，这里在尺寸变化、
    显示与主题切换后重新摆正编辑区。
    """

    def _restore_editor(self):
        """编辑区宽度异常时按控件宽度重新布局。"""
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
    """整数步进框，编辑区不会被压成 1px。"""


class ReadableDoubleSpinBox(_SpinEditorGeometry, DoubleSpinBox):
    """浮点步进框，编辑区不会被压成 1px。"""


class Ipv4TargetInput(QWidget):
    """四段式 IPv4 目标输入框。"""

    textChanged = Signal(str)
    nextFieldRequested = Signal()

    SEGMENT_WIDTHS = (64, 64, 64, 148)
    PLACEHOLDERS = ("192", "168", "1", "20、1-10、0/24")

    def __init__(
        self, parent=None, object_name="targetAddressInput", field_label="目标地址"
    ):
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
            # 点号由本控件拦截：段内输入“.”等同于按回车，不会写进数字框。
            edit.installEventFilter(self)
            layout.addWidget(edit)
            self.segments.append(edit)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setMinimumWidth(sum(self.SEGMENT_WIDTHS) + 42)

    def text(self):
        """返回四段拼起来的地址文本。"""
        return ".".join(edit.text() for edit in self.segments)

    def setText(self, value):
        """按输入格式拆成四段填入；单段写法支持范围与 /24 后缀。"""
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
        for edit, part in zip(self.segments, parts, strict=True):
            if edit.text() == part:
                continue
            edit.blockSignals(True)
            edit.setText(part)
            edit.blockSignals(False)
            changed = True
        if changed:
            self.textChanged.emit(self.text())

    def clear(self):
        """清空四段输入。"""
        self.setText("")

    def is_complete(self):
        """四段都填了内容时返回 True。"""
        return all(edit.text().strip() for edit in self.segments)

    def setError(self, is_error):
        """统一设置四段的错误边框状态。"""
        for edit in self.segments:
            edit.setError(bool(is_error))

    @Slot(str)
    def _segments_changed(self, value):
        self.textChanged.emit(self.text())

    def _advance(self, index):
        """回车后跳到下一段，最后一段则请求聚焦到下一个控件。"""
        if index < len(self.segments) - 1:
            target = self.segments[index + 1]
            target.setFocus()
            target.selectAll()
        else:
            self.nextFieldRequested.emit()

    def eventFilter(self, obj, event):
        """拦截段内的点号按键，按回车的方式跳到下一段。"""
        # 小键盘点号与主键盘点号都送 Key_Period；中文输入法可能在
        # InputMethod 事件里给出“。”，这里一并处理。
        if (
            event.type() == QEvent.Type.KeyPress
            and obj in self.segments
            and (event.key() == Qt.Key.Key_Period or event.text() in (".", "。"))
        ):
            self._advance(self.segments.index(obj))
            return True
        return super().eventFilter(obj, event)


class TargetControls(QWidget):
    """目标地址、端口、轮数与间隔的组合输入区。

    输入值直接写回共享的 ``ConnectionState``，其它页面通过它的 changed
    信号保持同步；地址未填完整时右侧会显示“地址未完成”。
    """

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
        self.fields = {
            "target": self.target_input,
            "port": self.port_input,
            "loops": self.loop_input,
            "interval": self.interval_input,
        }
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
        option_names = (
            ("port", "loops", "interval") if show_round_options else ("port",)
        )
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

        self.target_input.textChanged.connect(
            lambda value: state.set_value("target", value)
        )
        self.port_input.valueChanged.connect(
            lambda value: state.set_value("port", value)
        )
        self.loop_input.valueChanged.connect(
            lambda value: state.set_value("loops", value)
        )
        self.interval_input.valueChanged.connect(
            lambda value: state.set_value("interval", value)
        )
        self.target_input.nextFieldRequested.connect(self._focus_options)
        state.changed.connect(self._on_changed)
        state.aliases.changed.connect(self._aliases_changed)
        self._set_tab_order()
        self._update_count()
        self.interval_input.setEnabled(state.values["loops"] > 1)

    def _set_tab_order(self):
        """让 Tab 依次经过四段地址、选择设备、端口、轮数与间隔。"""
        segments = self.target_input.segments
        for current, following in pairwise(segments):
            QWidget.setTabOrder(current, following)
        QWidget.setTabOrder(segments[-1], self.device_button)
        QWidget.setTabOrder(self.device_button, self.port_input)
        QWidget.setTabOrder(self.port_input, self.loop_input)
        QWidget.setTabOrder(self.loop_input, self.interval_input)

    def _focus_options(self):
        """地址填完后把焦点交给端口输入框。"""
        self.port_input.setFocus()
        self.port_input.selectAll()

    @Slot()
    def _aliases_changed(self):
        """备注被改名或改地址后，同步刷新输入框里的显示值。"""
        matched = self.state.aliases.match(self.state.values["target"])
        if matched is not None:
            with QSignalBlocker(self.target_input):
                if self.target_input.text() != matched[1]:
                    self.target_input.setText(matched[1])
        self._update_count()

    def choose_device(self):
        """从设备备注里挑一个作为目标；没有备注时给出引导。"""
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
        center_dialog(dialog)
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
        center_dialog(dialog)
        return dialog, selector

    @Slot(str, object)
    def _on_changed(self, name, value):
        """共享状态变化时回写控件，期间屏蔽信号避免循环触发。"""
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
        """命中设备备注时在输入框下方提示对应地址。"""
        matched = self.state.aliases.match(text)
        if matched:
            self.alias_hint.setText("备注「%s」→ %s" % matched)
            self.alias_hint.show()
        else:
            self.alias_hint.hide()

    def _update_count(self):
        """按当前地址重新计算目标数量并提示地址是否可用。"""
        text = self.state.values["target"].strip()
        self._update_alias_hint(text)
        if not text:
            self.target_count.setText("0 个目标")
            self.target_input.setError(False)
            return
        try:
            # 输入过程中只关心数量，不需要把 /24 展开成 254 个地址对象。
            count = core.count_targets(self.state.resolve_target(text))
        except ValueError:
            self.target_count.setText("地址未完成")
            self.target_input.setError(self.target_input.is_complete())
        else:
            self.target_count.setText("%d 个目标" % count)
            self.target_input.setError(False)


class TaskFooter(QWidget):
    """页面底部的任务栏：状态文字、进度环与发送、取消按钮。

    Attributes:
        ring: 不确定进度环，任务运行时显示。
        log_button: 任务结束后出现的“查看运行日志”按钮。
    """

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
        self.log_button = tool_button(
            FluentIcon.HISTORY, "查看运行日志", self, self.viewLogs.emit
        )
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

    def set_busy(self, busy, cancellable=False, queueable=False):
        """按忙碌状态切换按钮可用性与进度环。"""
        self.send_button.setEnabled(not busy or queueable)
        self.cancel_button.setEnabled(busy and cancellable)
        self.ring.setVisible(busy)
        if busy:
            self.ring.start()
        else:
            self.ring.stop()

    def set_status(self, text=""):
        """显示状态文字，空文本时隐藏该行。"""
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def finish_status(self):
        """任务结束后清空状态文字。"""
        self.status.hide()
