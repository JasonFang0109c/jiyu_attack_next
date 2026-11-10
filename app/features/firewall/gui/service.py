"""FirewallService 的界面协调逻辑。"""

import app.features.firewall.service as firewall_service
from app.gui.workers.tasks import TaskWorker


def apply_firewall(action, report=None):
    """按需提权修改防火墙规则，供后台线程调用。"""
    if report:
        report("正在修改 StudentMain.exe 防火墙规则")
    return firewall_service.request_firewall_rule(action)


class FirewallService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window

    def start_firewall(self):
        """确认后修改 StudentMain.exe 的防火墙规则。"""
        window = self.window
        if not window._claim_task("防火墙", "防火墙操作"):
            return
        action = window.pages["firewall"].action()
        action_name = "阻断连接" if action == "block" else "恢复允许"
        if not window._confirm(
            "确认防火墙操作", "在本机对 StudentMain.exe 规则执行“%s”？" % action_name
        ):
            window.logs.info("防火墙", "用户取消了防火墙操作", "操作：%s" % action_name)
            return
        window.logs.info(
            "防火墙", "开始操作：%s" % action_name, "操作代码：%s" % action
        )
        window._begin_task(
            "firewall",
            TaskWorker(apply_firewall, action),
            window._firewall_finished,
            window._local_failed,
        )

    def _firewall_finished(self, results):
        window = self.window
        window.pages["firewall"].set_result(results)
        failed = any(not result["success"] for result in results)
        message = "部分规则操作失败，请查看操作结果" if failed else "防火墙规则已更新"
        window.pages["firewall"].footer.set_status(message)
        for result in results:
            text = "%s\n%s" % (result["command"], result["stdout"] or result["stderr"])
            if result["success"]:
                window.logs.info("防火墙", text, "命令执行成功")
            else:
                window.logs.error("防火墙", text, "命令执行失败")
        window._notify("防火墙", message, "警告" if failed else "成功")
