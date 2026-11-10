"""StudentService 的界面协调逻辑。"""

from functools import partial

import app.features.student.service as student_service
from app.gui.workers.tasks import ProbeWorker, TaskWorker


class StudentService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window

    def refresh_student_processes(self):
        """刷新本机学生端进程列表。"""
        window = self.window
        window.pages["studentproc"].set_busy(True)
        window._probe_student_processes("refresh")

    def _poll_student_processes(self):
        """页面可见时刷新学生端状态，让按钮始终表示当前能做的事。"""
        window = self.window
        if window.thread is not None:
            return
        window._probe_student_processes("poll")

    def _probe_student_processes(self, purpose):
        """在后台线程枚举学生端进程，结束后按用途分发结果。

        Args:
            purpose: ``refresh`` 手动刷新，``poll`` 定时轮询，``toggle`` 启停前确认状态。
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
            student_service.find_student_processes,
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

    def _student_processes_ready(self, purpose, processes):
        """拿到进程列表：轮询只在集合变化时重绘，手动操作要给出反馈。"""
        window = self.window
        if window._quit_requested:
            return
        page = window.pages["studentproc"]
        if purpose == "poll":
            if [item["pid"] for item in processes] == [
                item["pid"] for item in page.processes
            ]:
                return
            page.set_processes(processes)
            window.logs.debug(
                "解除限制",
                "学生端状态变化",
                "当前进程：%s"
                % ("、".join(str(item["pid"]) for item in processes) or "无"),
            )
            return
        page.set_processes(processes)
        if purpose == "toggle":
            if processes:
                window.stop_local_student()
            else:
                window.start_local_student()
            return
        page.set_busy(False)
        window.logs.info(
            "解除限制", "已刷新学生端进程列表", "共 %d 个" % len(processes)
        )
        if not processes:
            window._notify("未发现学生端", "本机没有正在运行的学生端进程", "信息")

    def _student_processes_failed(self, purpose, message, details):
        """查询失败：恢复按钮并记录堆栈，退出过程与轮询不弹提示。"""
        window = self.window
        if window._quit_requested or purpose == "poll":
            return
        page = window.pages["studentproc"]
        page.set_busy(False)
        window.logs.error("解除限制", "查询学生端进程失败", details or message)
        window._notify("查询学生端进程失败", message, "错误")

    def toggle_local_student(self):
        """单按钮入口：按当前状态决定启动还是结束学生端。"""
        window = self.window
        if not window._claim_task("解除限制", "启停学生端"):
            return
        window._probe_student_processes("toggle")

    def start_local_student(self):
        """确认后启动本机学生端，必要时走 UAC 提权。"""
        window = self.window
        if not window._claim_task("解除限制", "启动学生端"):
            return
        page = window.pages["studentproc"]
        if page.processes:
            window._notify("学生端已在运行", "先结束再启动", "警告")
            return
        if not window._confirm(
            "确认启动学生端",
            "将按需以管理员权限启动本机极域学生端，启动后本机会重新受课堂管理。",
        ):
            return
        page.set_busy(True)
        window._begin_task(
            "studentproc",
            TaskWorker(student_service.start_student_process, page.exe_path()),
            window._start_student_finished,
            window._local_failed,
        )

    def _start_student_finished(self, results):
        """启动结束后提示结果并刷新进程列表。"""
        window = self.window
        failed = [item for item in results if not item.get("success")]
        for item in failed:
            window.logs.error(
                "解除限制",
                "启动学生端失败",
                "程序：%s；%s" % (item.get("path", ""), item.get("output", "")),
            )
        if failed:
            window._notify("启动学生端失败", "见运行日志", "错误")
        else:
            path = results[0].get("path", "") if results else ""
            window.logs.info("解除限制", "已启动学生端", "程序：%s" % path)
            window._notify("已启动学生端", path, "成功")
        window.refresh_student_processes()

    def stop_local_student(self):
        """确认后结束本机学生端进程，必要时走 UAC 提权。"""
        window = self.window
        if not window._claim_task("解除限制", "结束学生端"):
            return
        processes = window.pages["studentproc"].processes
        if not processes:
            window._notify(
                "没有可结束的进程", "列表每 2 秒自动刷新，稍等一下再试", "警告"
            )
            return
        names = "、".join(
            "PID %d %s" % (item["pid"], item["name"]) for item in processes
        )
        if not window._confirm(
            "确认结束学生端",
            "结束本机学生端进程（%s）？\n结束时可能弹出管理员授权，请选择“是”。"
            % names,
        ):
            window.logs.info("解除限制", "用户取消了结束学生端", "目标：%s" % names)
            return
        window.logs.info("解除限制", "开始结束学生端进程", "目标：%s" % names)
        window.pages["studentproc"].set_busy(True)
        window._begin_task(
            "studentproc",
            TaskWorker(
                student_service.stop_student_processes,
                [item["pid"] for item in processes],
            ),
            window._stop_student_finished,
            window._local_failed,
        )

    def _stop_student_finished(self, results):
        """处理结束学生端的结果，并刷新列表。"""
        window = self.window
        window.pages["studentproc"].set_busy(False)
        failed = [item for item in results if not item.get("success")]
        if failed:
            detail = "；".join(
                "PID %d %s" % (item["pid"], item["output"]) for item in failed
            )
            window.logs.error("解除限制", "部分学生端进程未能结束", "失败：%s" % detail)
            window._notify("部分进程未能结束", detail, "错误")
        else:
            window.logs.info("解除限制", "已结束学生端进程", "共 %d 个" % len(results))
            window._notify("已结束学生端", "共结束 %d 个进程" % len(results), "成功")
        window.refresh_student_processes()
