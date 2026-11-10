"""TaskService 的界面协调逻辑。"""

import time

from PySide6.QtCore import (
    Qt,
)

from app.gui.window.data import CATEGORIES


class TaskService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window

    def _claim_task(self, category, action):
        """确认当前没有任务在跑；已有任务时记一条 warning 并返回 False。"""
        window = self.window
        if window.thread is None:
            return True
        window.logs.warning(
            category,
            "已有任务在运行，%s未开始" % action,
            "当前任务：%s" % (window.active_kind or "无"),
        )
        return False

    def _begin_task(self, kind, worker, finished, failed):
        """启动后台任务；已有任务在跑时改为排队，保证同一时间只跑一个。"""
        window = self.window
        if window.thread is not None:
            window._task_queue.append((kind, worker, finished, failed))
            position = len(window._task_queue)
            queued = window.pages[kind]
            if getattr(queued, "footer", None) is not None:
                queued.footer.set_status("已加入队列，前面还有 %d 个任务" % position)
            options = getattr(worker, "options", None)
            target = getattr(options, "target", None)
            details = "待执行任务数：%d" % position
            if target:
                details += "；目标：%s" % target
            window.logs.info(CATEGORIES[kind], "任务已加入队列", details)
            return
        window.active_kind = kind
        window.active_started_at = time.monotonic()
        window.thread = worker
        window.worker = worker
        options = getattr(worker, "options", None)
        cancel_event = getattr(options, "cancel_event", None)
        if cancel_event is None:
            cancel_event = getattr(worker, "kwargs", {}).get("cancel_event")
        window.active_cancel = cancel_event
        if kind == "file":
            window.pages["file"].reset_progress()
        # 线程内日志在此注入：线程对象由各页面创建，统一在启动时补上分类与存储。
        worker.logs = window.logs
        worker.category = CATEGORIES.get(kind, "应用")
        worker.setParent(window)
        worker.progress.connect(window._task_progress, Qt.QueuedConnection)
        worker.completed.connect(finished, Qt.QueuedConnection)
        worker.failed.connect(failed, Qt.QueuedConnection)
        worker.finished.connect(window._thread_finished, Qt.QueuedConnection)
        worker.finished.connect(worker.deleteLater)
        window._set_busy(True)
        worker.start()
        window.logs.debug(
            CATEGORIES[kind],
            "后台任务已启动",
            "线程类：%s；排队任务数：%d"
            % (type(worker).__name__, len(window._task_queue)),
        )

    def _set_busy(self, busy):
        """按忙碌状态统一开关各页面的按钮与输入控件。"""
        window = self.window
        for page in window.network_pages:
            page.set_busy(busy, window.active_cancel is not None, queueable=True)
        window.pages["file"].set_busy(
            busy, window.active_cancel is not None, queueable=True
        )
        for key in ("local", "firewall"):
            window.pages[key].footer.set_busy(busy)
        window.pages["firewall"].action_box.setEnabled(not busy)
        window.pages["settings"].clear_data_button.setEnabled(not busy)
        window.pages["logs"].cancel_button.setEnabled(
            busy and window.active_cancel is not None
        )
        for key, page in window.pages.items():
            footer = getattr(page, "footer", None)
            if footer is not None and key in CATEGORIES and key != window.active_kind:
                footer.set_status("其他任务正在执行，可继续加入队列" if busy else "")
        active = window.pages[window.active_kind]
        active_footer = getattr(active, "footer", None)
        if active_footer is None:
            active.set_busy(busy)
        elif busy:
            active_footer.set_status("执行中，可继续加入队列")
        else:
            active_footer.finish_status()

    def _task_progress(self, message):
        window = self.window
        window.logs.debug(CATEGORIES[window.active_kind], message, "任务函数进度回调")
        active = window.pages[window.active_kind]
        if getattr(active, "footer", None) is not None:
            active.footer.set_status(message)
        if window.active_kind == "file" and "文件传送服务已启动" in message:
            window.pages["file"].reset_progress()
        if window.active_kind == "file" and "下载文件：" in message:
            try:
                percent = int(message.rsplit("：", 1)[1].rstrip("%"))
            except ValueError:
                return
            window.pages["file"].set_progress(percent)

    def cancel_task(self):
        """清空排队任务，并给正在运行的任务置位取消信号。"""
        window = self.window
        if window._task_queue:
            queued = len(window._task_queue)
            window._task_queue.clear()
            for key, page in window.pages.items():
                footer = getattr(page, "footer", None)
                if (
                    footer is not None
                    and key in CATEGORIES
                    and key != window.active_kind
                ):
                    footer.set_status("排队任务已取消")
            window.logs.warning(
                CATEGORIES.get(window.active_kind, "任务"),
                "已取消全部排队任务",
                "排队任务数：%d" % queued,
            )
        if window.active_cancel and not window.active_cancel.is_set():
            window.active_cancel.set()
            window.pages[window.active_kind].footer.set_status("正在取消")
            for page in window.task_pages:
                page.footer.cancel_button.setEnabled(False)
            window.pages["logs"].cancel_button.setEnabled(False)
            window.logs.warning(
                CATEGORIES[window.active_kind],
                "已请求取消",
                "任务：%s；耗时：%.3f 秒"
                % (
                    CATEGORIES[window.active_kind],
                    time.monotonic() - window.active_started_at,
                ),
            )

    def _thread_finished(self):
        """线程结束后清理状态，必要时关闭窗口或启动下一个排队任务。"""
        window = self.window
        finished_kind = window.active_kind
        window.thread = None
        window.worker = None
        window.active_cancel = None
        window.active_started_at = None
        if window.close_after_task:
            window._task_queue.clear()
            window._task_dispatch_timer.start(0)
        else:
            window._set_busy(False)
        window.active_kind = ""
        if finished_kind:
            window.logs.debug(
                CATEGORIES.get(finished_kind, "应用"),
                "后台线程已结束",
                "任务：%s；排队任务数：%d；关闭延后：%s"
                % (
                    finished_kind,
                    len(window._task_queue),
                    "是" if window.close_after_task else "否",
                ),
            )
        if window._task_queue and not window.close_after_task:
            window._task_dispatch_timer.start(0)

    def _dispatch_after_task(self):
        window = self.window
        if window._navigation_closed:
            return
        if window.close_after_task:
            window.close()
        else:
            window._start_next_task()

    def _start_next_task(self):
        """取出队首任务继续执行。"""
        window = self.window
        if window.thread is not None or not window._task_queue:
            return
        kind, worker, finished, failed = window._task_queue.pop(0)
        window.logs.debug(
            CATEGORIES[kind],
            "开始执行排队任务",
            "剩余排队任务数：%d" % len(window._task_queue),
        )
        window._begin_task(kind, worker, finished, failed)
