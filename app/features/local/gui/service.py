"""LocalService 的界面协调逻辑。"""

import time

from PySide6.QtWidgets import QApplication

import app.features.local.service as local_service
from app.gui.window.data import LOCAL_IP_PLACEHOLDERS
from app.gui.workers.tasks import TaskWorker


def probe_local(report=None):
    """查询本机 IP 与 Student 监听端口，供后台线程调用。"""
    if report:
        report("正在读取本机 IP 与 Student 监听端口")
    return local_service.local_ip_and_ports()


class LocalService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window

    def start_local_probe(self):
        """查询本机 IP 与 Student 端监听端口。"""
        window = self.window
        if not window._claim_task("本机信息", "本机查询"):
            return
        window.logs.info("本机信息", "开始查询本机 IP 与监听端口")
        window._begin_task(
            "local",
            TaskWorker(probe_local),
            window._probe_finished,
            window._local_failed,
        )

    def _probe_finished(self, result):
        window = self.window
        ip, ports = result
        window.pages["local"].set_result(ip, ports)
        message = "查询完成，发现 %d 个监听端口" % len(ports)
        window.pages["local"].footer.set_status(message)
        window.logs.info(
            "本机信息",
            "本机 IP：%s；监听端口：%s" % (ip, ", ".join(ports) or "未发现"),
            "IP：%s；端口数：%d；耗时：%.3f 秒"
            % (ip, len(ports), time.monotonic() - window.active_started_at),
        )

    def copy_local_ip(self):
        """把本机 IP 复制到剪贴板。"""
        window = self.window
        ip = window.pages["local"].ip_label.text()
        if ip in LOCAL_IP_PLACEHOLDERS:
            # 标签上还是占位文案，复制过去没有意义。
            window._notify("尚未查询", "先查询本机信息再复制", "警告")
            return
        QApplication.clipboard().setText(ip)
        window.logs.info("本机信息", "本机 IP 已复制", "IP：%s" % ip)
        window._notify("已复制", "本机 IP 已复制到剪贴板", "成功")
