"""GuiService 的界面协调逻辑。"""

import time
from pathlib import Path
from threading import Event

from PySide6.QtCore import (
    Qt,
)
from PySide6.QtWidgets import QSystemTrayIcon
from qfluentwidgets import (
    InfoBar,
    InfoBarPosition,
)

import app.features.send.service as send_service
import app.packets.codec as packets_codec
import app.packets.constants as packets_constants
import app.system.net.targets as system_net_targets
from app.gui.widgets.common import FluentDialog, center_dialog
from app.gui.window.data import CATEGORIES, TRAY_MESSAGE_ICONS
from app.gui.workers.tasks import SendWorker


class GuiService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window

    def _notify(self, title, message, level="信息"):
        """显示提示：窗口隐藏时走托盘气泡，否则用右上角 InfoBar。"""
        window = self.window
        # 退出流程中窗口即将销毁，此时再弹 InfoBar 会在关闭动画期间闪现。
        if window.close_after_task:
            return
        if not window.isVisible() and window.tray_icon is not None:
            window.tray_icon.showMessage(
                title,
                str(message),
                TRAY_MESSAGE_ICONS.get(level, QSystemTrayIcon.MessageIcon.Information),
                4000,
            )
            return
        function = {
            "错误": InfoBar.error,
            "成功": InfoBar.success,
            "警告": InfoBar.warning,
        }.get(level, InfoBar.info)
        function(
            title=title,
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=4000,
            parent=window,
        )

    def _dialog(self, title, content, confirm_text=None):
        """创建统一尺寸、居中显示的确认对话框。

        Args:
            title: 对话框标题。
            content: 正文说明。
            confirm_text: 确认按钮文案；为空时沿用组件库默认值。

        Returns:
            FluentDialog: 尚未执行的对话框实例。
        """
        window = self.window
        dialog = FluentDialog(title, content, window)
        dialog.setFixedSize(520, 280)
        if confirm_text is not None:
            dialog.yesButton.setText(confirm_text)
        dialog.cancelButton.setText("取消")
        center_dialog(dialog)
        return dialog

    def _confirm(self, title, content, confirm_text="确认执行"):
        """弹出确认对话框，返回用户是否点击了确认按钮。"""
        window = self.window
        return bool(window._dialog(title, content, confirm_text).exec())

    def _options_for_page(self, kind):
        """按页面类型组装发送参数。"""
        window = self.window
        if kind == "device":
            return window.connection_state.options(extra=window.pages[kind].action())
        if kind in ("message", "command"):
            # 两个页面的编辑器同名，字段名与页面键一致，直接按名字取。
            return window.connection_state.options(
                **{kind: window.pages[kind].editor.toPlainText()}
            )
        window.logs.warning("应用", "不支持的发送功能", "功能代码：%s" % kind)
        raise ValueError("不支持的发送功能")

    def start_send(self, kind):
        """校验参数、确认设备操作后把发送任务加入队列。"""
        window = self.window
        page = window.pages[kind]
        options = window._options_for_page(kind)
        try:
            hosts = system_net_targets.get_ip(options.target)
        except ValueError as error:
            page.targets.target_input.setError(True)
            page.targets.target_input.setFocus()
            alias_name = window.connection_state.values["target"].strip()
            details = "输入目标：%s；端口：%d；异常：%s" % (
                alias_name or "（空）",
                options.port,
                error,
            )
            if window.connection_state.aliases.match(alias_name) is None:
                window._validation_error(kind, str(error), details)
            else:
                window._validation_error(kind, "设备备注对应的 IP 无效", details)
            return
        try:
            send_service.validate_options(options)
            if options.command:
                packets_codec.pkg_sendlist("-c", options.command)
        except (ValueError, UnicodeError) as error:
            window._validation_error(kind, str(error), "发送参数校验失败：%s" % error)
            return
        target_text = window.connection_state.format_target()
        target_input_text = window.connection_state.values["target"].strip()
        if kind == "device":
            action = {"r": "重启", "s": "关机", "l": "注销"}[options.extra]
            method = (
                "（远程命令 %s）" % packets_constants.LOGOFF_COMMAND
                if options.extra == "l"
                else ""
            )
            content = "目标：%s\nUDP 端口：%d\n设备数量：%d\n操作：%s%s" % (
                target_text,
                options.port,
                len(hosts),
                action,
                method,
            )
            if not window._confirm("确认%s" % action, content):
                window.logs.info(
                    CATEGORIES[kind],
                    "用户取消了%s确认" % action,
                    "目标：%s；端口：%d；设备数量：%d"
                    % (target_text, options.port, len(hosts)),
                )
                return
        options.cancel_event = Event()
        if target_input_text.casefold() != options.target.casefold():
            message = "开始发送：%s，解析为 %s，端口 %d，%d 轮" % (
                target_input_text,
                options.target,
                options.port,
                options.loops,
            )
        else:
            message = "开始发送：%s，端口 %d，%d 轮" % (
                target_text,
                options.port,
                options.loops,
            )
        payload = options.message if kind == "message" else options.command
        details = (
            "功能：%s；目标：%s；设备数：%d；端口：%d；轮数：%d；间隔：%s；负载长度：%d"
            % (
                CATEGORIES[kind],
                options.target,
                len(hosts),
                options.port,
                options.loops,
                options.interval,
                len(payload or ""),
            )
        )
        window.logs.info(CATEGORIES[kind], message, details)
        window.logs.debug(CATEGORIES[kind], "发送参数快照", details)
        window._begin_task(
            kind,
            SendWorker(options, send_service.execute_send_report),
            window._send_finished,
            window._send_failed,
        )

    def _validation_error(self, kind, message, details=""):
        """参数不合法时统一写日志、更新页脚并弹出提示。"""
        window = self.window
        window.pages[kind].footer.set_status(message)
        window.logs.warning(
            CATEGORIES[kind],
            message,
            details or "功能：%s；校验未通过" % CATEGORIES[kind],
        )
        window._notify("请检查参数", message, "警告")

    def _report_failure(self, category, message, details, titles):
        """失败收尾：取消按 info、其余按 error 记日志，并弹出对应提示。

        Args:
            category: 日志功能分类。
            message: 失败消息，等于 ``操作已取消`` 时按用户取消处理。
            details: 附加说明。
            titles: 提示标题，依次为已取消与失败两种。
        """
        window = self.window
        cancelled = message == "操作已取消"
        if cancelled:
            window.logs.info(category, message, details)
        else:
            window.logs.error(category, message, details)
        window._notify(
            titles[0] if cancelled else titles[1],
            message,
            "信息" if cancelled else "错误",
        )

    def _send_finished(self, outcome):
        window = self.window
        failed = outcome.failed
        total = len(outcome.deliveries)
        if failed:
            message = "已发送 %d 个报文：成功 %d 台，失败 %d 台" % (
                outcome.sent,
                total - len(failed),
                len(failed),
            )
            details = "失败目标：%s" % "；".join(
                "%s（%s）" % (item.host, item.state.text) for item in failed
            )
        else:
            message = "已发送 %d 个报文：%d 台均未发现异常" % (outcome.sent, total)
            details = "成功率按网络反馈判定：没有收到 ICMP 不可达即视为送达。"
        window.pages[window.active_kind].footer.set_status(message)
        details = "%s；耗时：%.3f 秒" % (
            details,
            time.monotonic() - window.active_started_at,
        )
        if failed:
            window.logs.warning(CATEGORIES[window.active_kind], message, details)
        else:
            window.logs.info(CATEGORIES[window.active_kind], message, details)
        window._notify(
            "发送完成" if not failed else "部分目标失败",
            message,
            "成功" if not failed else "错误",
        )

    def _send_failed(self, message, details=""):
        window = self.window
        window.pages[window.active_kind].footer.set_status(message)
        window._report_failure(
            CATEGORIES[window.active_kind],
            message,
            "耗时：%.3f 秒；%s"
            % (time.monotonic() - window.active_started_at, details or "无异常堆栈"),
            ("发送已取消", "发送失败"),
        )

    def _local_failed(self, message, details=""):
        window = self.window
        active = window.pages[window.active_kind]
        if getattr(active, "footer", None) is not None:
            active.footer.set_status(message)
        window._report_failure(
            CATEGORIES[window.active_kind],
            message,
            "耗时：%.3f 秒；%s"
            % (time.monotonic() - window.active_started_at, details or "无异常堆栈"),
            ("操作已取消", "操作失败"),
        )

    def _save_text(self, filename, text):
        """写出 UTF-8（带 BOM）文本，失败时提示并记录日志。"""
        window = self.window
        try:
            Path(filename).write_text(text, encoding="utf-8-sig")
        except OSError as error:
            window.logs.error(
                "应用", "保存文本失败", "文件：%s；异常：%s" % (filename, error)
            )
            window._notify("保存失败", str(error), "错误")
        else:
            window.logs.info(
                "应用", "文本已保存", "文件：%s；字符数：%d" % (filename, len(text))
            )
            window._notify("已保存", Path(filename).name, "成功")
