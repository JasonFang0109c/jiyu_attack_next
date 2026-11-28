"""StudentService 的界面协调逻辑。"""

from functools import partial

import NeoJiYuTrainer.features.student.service as student_service
from NeoJiYuTrainer.gui.workers.tasks import ProbeWorker, TaskWorker


class StudentService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window
        self._snapshot_signature = None

    def refresh_student_processes(self, purpose="poll"):
        """刷新学生端状态。

        Args:
            purpose: 默认 ``poll`` 静默轮询；``toggle`` / ``stop`` / ``start``
                表示动作前的状态确认。页面不再提供手动刷新入口。
        """
        self.window._probe_student_processes(purpose)

    def _poll_student_processes(self):
        """页面可见时刷新学生端状态，让按钮始终表示当前能做的事。"""
        window = self.window
        if window.thread is not None:
            return
        window._probe_student_processes("poll")

    def _probe_student_processes(self, purpose):
        """在后台线程读取学生端状态，结束后按用途分发结果。

        Args:
            purpose: 见 :meth:`refresh_student_processes`。
        """
        window = self.window
        if window._quit_requested:
            return
        if window._student_probe_thread is not None:
            # 轮询可以丢弃，手动操作要排队，否则点了没反应。
            if purpose != "poll":
                window._student_probe_queued = purpose
            return
        thread = ProbeWorker(
            student_service.student_status,
            logs=window.logs,
            category="解除限制",
        )
        thread.completed.connect(partial(window._student_processes_ready, purpose))
        thread.failed.connect(partial(window._student_processes_failed, purpose))
        thread.finished.connect(window._student_probe_finished)
        thread.finished.connect(thread.deleteLater)
        window._student_probe_thread = thread
        thread.start()

    def _student_probe_finished(self):
        """查询结束后释放引用；退出时丢弃排队请求并继续关闭窗口。"""
        window = self.window
        window._student_probe_thread = None
        purpose, window._student_probe_queued = window._student_probe_queued, None
        if window._quit_requested:
            window._task_dispatch_timer.start(0)
        elif purpose is not None:
            window._probe_student_processes(purpose)

    @staticmethod
    def _signature(snapshot):
        """比较页面实际展示的进程字段与快照状态。"""
        if isinstance(snapshot, dict):
            processes = snapshot.get("processes") or []
            port_owner = snapshot.get("port_owner", 0)
            exe_path = snapshot.get("exe_path") or ""
        else:
            processes = snapshot or []
            port_owner = 0
            exe_path = ""
        return (
            port_owner,
            exe_path,
            tuple(
                (
                    item.get("pid"),
                    item.get("name", ""),
                    tuple(item.get("ports") or ()),
                    item.get("path") or "",
                    bool(item.get("genuine")),
                )
                for item in processes
            ),
        )

    def _student_processes_ready(self, purpose, snapshot):
        """拿到状态：轮询只在集合变化时重绘，动作前先核对再执行。"""
        window = self.window
        if window._quit_requested:
            return
        page = window.pages["studentproc"]
        processes = (
            snapshot.get("processes", [])
            if isinstance(snapshot, dict)
            else list(snapshot or [])
        )
        signature = self._signature(snapshot)
        if purpose == "poll":
            if page.loaded and signature == self._snapshot_signature:
                return
            page.set_snapshot(snapshot)
            self._snapshot_signature = signature
            window.logs.debug(
                "解除限制",
                "学生端状态变化",
                "当前进程：%s"
                % ("、".join(str(item["pid"]) for item in processes) or "无"),
            )
            return
        page.set_snapshot(snapshot)
        self._snapshot_signature = signature
        if purpose == "toggle":
            if processes:
                self._stop(snapshot)
            else:
                self._start()
            return
        if purpose in ("stop", "start"):
            # 动作前的确认查询：以最新状态为准，页面上的列表可能已经过期。
            if purpose == "stop":
                self._stop(snapshot)
            else:
                self._start()

    def _student_processes_failed(self, purpose, message, details):
        """查询失败：恢复按钮并记录堆栈，退出过程与轮询不弹提示。"""
        window = self.window
        if window._quit_requested:
            return
        if purpose == "poll":
            return
        page = window.pages["studentproc"]
        page.set_busy(False)
        window.logs.error("解除限制", "查询学生端状态失败", details or message)
        window._notify("查询学生端状态失败", message, "错误")

    # ---- 动作 -------------------------------------------------------------

    def toggle_local_student(self):
        """单按钮入口：先确认最新状态，再决定启动还是结束。"""
        window = self.window
        if not window._claim_task("解除限制", "启停学生端"):
            return
        window._probe_student_processes("toggle")

    def _start(self):
        """最终确认后启动本机学生端，必要时走 UAC 提权。"""
        window = self.window
        page = window.pages["studentproc"]
        if page.processes:
            window._notify("学生端已在运行", "先结束再启动", "警告")
            page.set_busy(False)
            return
        # 程序位置由核心自动查找（优先用之前记住的路径）。
        shown = "自动查找安装位置"
        if not window._confirm(
            "启动学生端",
            "将按需以管理员权限启动本机极域学生端：\n%s\n\n"
            "启动后本机会重新受课堂管理，过程可能需要几秒。" % shown,
            "启动",
        ):
            window.logs.info("解除限制", "用户取消了启动学生端", "程序：%s" % shown)
            page.set_busy(False)
            return
        window.logs.info("解除限制", "开始启动学生端", "程序：%s" % shown)
        page.set_busy(True)
        window._begin_task(
            "studentproc",
            TaskWorker(student_service.start_student_process),
            window._start_student_finished,
            window._local_failed,
        )

    def _stop(self, snapshot):
        """最终确认后结束快照里的学生端进程，必要时走 UAC 提权。"""
        window = self.window
        page = window.pages["studentproc"]
        processes = (
            list(snapshot.get("processes") or [])
            if isinstance(snapshot, dict)
            else list(snapshot or [])
        )
        if not processes:
            page.set_busy(False)
            window._notify(
                "没有可结束的进程", "列表每 2 秒自动刷新，稍等一下再试", "警告"
            )
            return
        names = "、".join(
            "PID %d %s" % (item["pid"], item["name"]) for item in processes
        )
        port_note = ""
        if any(4705 in (item.get("ports") or []) for item in processes):
            port_note = "\n结束后本机将不再独占 4705 端口，可以正常模拟教师端。"
        if not window._confirm(
            "结束学生端",
            "结束本机学生端进程（%s）？%s\n"
            "结束时可能弹出管理员授权，请选择“是”。" % (names, port_note),
            "结束",
        ):
            window.logs.info("解除限制", "用户取消了结束学生端", "目标：%s" % names)
            page.set_busy(False)
            return
        window.logs.info("解除限制", "开始结束学生端进程", "目标：%s" % names)
        page.set_busy(True)
        window._begin_task(
            "studentproc",
            TaskWorker(
                student_service.stop_student_processes,
                [item["pid"] for item in processes],
            ),
            window._stop_student_finished,
            window._local_failed,
        )

    def stop_local_student(self):
        """先确认最新状态，再结束本机学生端进程。"""
        window = self.window
        if not window._claim_task("解除限制", "结束学生端"):
            return
        window._probe_student_processes("stop")

    def start_local_student(self):
        """先确认最新状态，再启动本机学生端。"""
        window = self.window
        if not window._claim_task("解除限制", "启动学生端"):
            return
        window._probe_student_processes("start")

    def _start_student_finished(self, results):
        """启动结束后提示结果并刷新状态。"""
        window = self.window
        results = results or []
        failed = [item for item in results if not item.get("success")]
        for item in failed:
            window.logs.error(
                "解除限制",
                "启动学生端失败",
                "程序：%s；%s" % (item.get("path", ""), item.get("output", "")),
            )
        if failed:
            window._notify(
                "启动学生端失败", failed[0].get("output") or "见运行日志", "错误"
            )
            window.refresh_student_processes("poll")
            return
        path = results[0].get("path", "") if results else ""
        confirmed = all(item.get("confirmed", True) for item in results)
        if confirmed:
            window.logs.info("解除限制", "已启动学生端", "程序：%s" % path)
            window._notify("已启动学生端", path, "成功")
        else:
            window.logs.warning(
                "解除限制",
                "已请求启动学生端但没有检测到进程",
                "程序：%s；可能被安全软件拦下" % path,
            )
            window._notify(
                "已请求启动学生端", "没有检测到进程，可能被安全软件拦下", "警告"
            )
        window.refresh_student_processes("poll")

    def _stop_student_finished(self, results):
        """处理结束学生端的结果，并刷新状态。"""
        window = self.window
        results = results or []
        window.pages["studentproc"].set_busy(False)
        respawned = [item for item in results if item.get("respawned")]
        failed = [
            item
            for item in results
            if not item.get("success") and not item.get("respawned")
        ]
        stopped = [item for item in results if item.get("success")]
        if respawned:
            detail = respawned[0].get("output", "学生端被守护服务重新拉起")
            window.logs.warning(
                "解除限制",
                "学生端被守护服务重新拉起",
                "新进程：%s" % ", ".join(str(item["pid"]) for item in respawned),
            )
            window._notify("学生端又被拉起来了", detail, "警告")
        if failed:
            detail = "；".join(
                "PID %s %s" % (item["pid"], item.get("output", "")) for item in failed
            )
            window.logs.error("解除限制", "部分学生端进程未能结束", "失败：%s" % detail)
            window._notify("部分进程未能结束", detail, "错误")
        elif stopped and not respawned:
            window.logs.info("解除限制", "已结束学生端进程", "共 %d 个" % len(stopped))
            window._notify(
                "已结束学生端",
                "共结束 %d 个进程，4705 端口已腾出" % len(stopped),
                "成功",
            )
        window.refresh_student_processes("poll")
