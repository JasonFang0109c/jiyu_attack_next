"""StudentService 的界面协调逻辑。"""

from functools import partial

import app.features.student.service as student_service
from app.gui.workers.tasks import ProbeWorker, TaskWorker


class StudentService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window

    def refresh_student_processes(self, purpose="refresh"):
        """刷新学生端状态。

        Args:
            purpose: ``refresh`` 手动刷新（显示忙碌与结果提示）、``poll``
                定时轮询（静默）或 ``toggle`` / ``stop`` / ``start`` 动作前的
                状态确认；非手动刷新不闪忙碌状态，避免每两秒切一次按钮。
        """
        window = self.window
        page = window.pages["studentproc"]
        if purpose == "refresh":
            page.set_busy(True)
            page.set_working("正在读取学生端状态…")
        window._probe_student_processes(purpose)

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
    def _signature(processes):
        """用于比较两次查询是否真的发生了变化。"""
        return [
            (item["pid"], tuple(item.get("ports") or ()), item.get("path", ""))
            for item in processes or []
        ]

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
        if purpose == "poll":
            if self._signature(processes) == self._signature(page.processes):
                return
            page.set_snapshot(snapshot)
            window.logs.debug(
                "解除限制",
                "学生端状态变化",
                "当前进程：%s"
                % ("、".join(str(item["pid"]) for item in processes) or "无"),
            )
            return
        page.set_snapshot(snapshot)
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
            return
        page.set_busy(False)
        window.logs.info("解除限制", "已刷新学生端状态", "共 %d 个" % len(processes))
        if not processes:
            window._notify("未发现学生端", "本机没有正在运行的学生端进程", "信息")

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
        window.pages["studentproc"].set_working("正在确认学生端状态…")
        window._probe_student_processes("toggle")

    def _start(self):
        """最终确认后启动本机学生端，必要时走 UAC 提权。"""
        window = self.window
        page = window.pages["studentproc"]
        if page.processes:
            window._notify("学生端已在运行", "先结束再启动", "警告")
            page.set_busy(False)
            return
        path = page.exe_path()
        shown = path or page.manual_path() or page.saved_path or "自动查找安装位置"
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
            TaskWorker(student_service.start_student_process, path),
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

    # ---- 程序位置 ---------------------------------------------------------

    def choose_student_executable(self):
        """用文件对话框挑选 StudentMain.exe，选中后记住并回填。"""
        from PySide6.QtWidgets import QFileDialog

        window = self.window
        page = window.pages["studentproc"]
        start = page.manual_path() or page.saved_path or "C:\\Program Files"
        filename, _ = QFileDialog.getOpenFileName(
            window,
            "选择学生端主程序",
            start,
            "学生端主程序 (StudentMain*.exe Student.exe);;可执行文件 (*.exe)",
        )
        if not filename:
            return
        student_service.save_executable(filename)
        page.set_exe_text(filename)
        window.logs.info("解除限制", "已记住学生端程序位置", "程序：%s" % filename)
        self.refresh_student_processes("poll")

    def locate_student_executable(self):
        """按记住的路径、运行中的进程、注册表与常见目录查找程序位置。"""
        window = self.window
        page = window.pages["studentproc"]
        try:
            found = student_service.find_student_executable()
        except RuntimeError as error:
            window.logs.warning(
                "解除限制", "没有找到学生端安装位置", "原因：%s" % error
            )
            window._notify("没有找到学生端", str(error), "警告")
            return
        student_service.save_executable(found)
        page.set_exe_text(found)
        window.logs.info("解除限制", "已定位学生端程序位置", "程序：%s" % found)
        window._notify("已找到学生端", found, "成功")
        self.refresh_student_processes("poll")

    def forget_student_executable(self):
        """清除记住的路径，之后按自动查找处理。"""
        window = self.window
        page = window.pages["studentproc"]
        student_service.save_executable("")
        page.set_exe_text("")
        page.saved_path = ""
        window.logs.info("解除限制", "已清除记住的学生端路径")
        window._notify("已清除记忆", "下次启动会重新自动查找程序位置", "信息")

    def copy_student_path(self):
        """复制优先显示的路径到剪贴板。"""
        window = self.window
        page = window.pages["studentproc"]
        text = page.path_for_copy()
        if not text:
            window._notify("没有可复制的路径", "先定位或选择 StudentMain.exe", "警告")
            return
        if page.copy_text(text):
            window.logs.info("解除限制", "已复制学生端路径", "路径：%s" % text)
            window._notify("已复制路径", text, "成功")

    def copy_student_port(self):
        """复制 4705 端口号，方便填到远程页面。"""
        window = self.window
        page = window.pages["studentproc"]
        if page.copy_text(str(student_service.STUDENT_PORT)):
            window.logs.info("解除限制", "已复制学生端端口")
            window._notify("已复制端口", str(student_service.STUDENT_PORT), "成功")

    def copy_row_path(self, path):
        """双击进程行时复制那一行的程序路径。"""
        window = self.window
        page = window.pages["studentproc"]
        if page.copy_text(path):
            window.logs.info("解除限制", "已复制学生端路径", "路径：%s" % path)
            window._notify("已复制路径", path, "成功")
