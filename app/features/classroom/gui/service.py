"""课堂助手界面服务：轮询、后台任务、设置保存与剪贴板。

页面只负责显示与发信号，所有可能拖慢界面的工作都走仓库现有的 QThread
工作类；自动看护即使页面隐藏也按设置继续运行。
"""

from functools import partial

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QCheckBox

import app.features.classroom.service as classroom
import app.system.windows.guard as guard
from app.features.classroom.data import (
    OPTION_NAMES,
    SETTINGS_AUTO_REPAIR,
    SETTINGS_GUARD_FLAGS,
    SETTINGS_INTERVAL,
)
from app.gui.workers.tasks import ProbeWorker, TaskWorker

CATEGORY = "课堂助手"
# 页面可见时每 2 秒刷新一次窗口列表，与启停学生端页的节奏一致。
POLL_INTERVAL = 2000


def _repair_task(data_dir, report=None):
    """后台任务包装：立即修复。``report`` 由 TaskWorker 注入。"""
    return classroom.repair(data_dir)


def _auto_tick_task(data_dir, report=None):
    """后台任务包装：自动看护的一次轮询。"""
    return classroom.auto_tick(data_dir)


def _fake_full_task(enabled, data_dir, report=None):
    """后台任务包装：开关假全屏。"""
    return classroom.toggle_fake_full(enabled, data_dir)


def _topmost_task(enabled, data_dir, report=None):
    """后台任务包装：开关窗口置顶。"""
    return classroom.set_topmost(enabled, data_dir)


def _guard_start_task(flags, data_dir, report=None):
    """后台任务包装：给学生端加载课堂防护。"""
    return classroom.start_guard(flags, data_dir)


class ClassroomService:
    """组织课堂助手页的轮询、动作与设置持久化。"""

    def __init__(self, window):
        self.window = window
        self.page = None
        self.options = classroom.load_options(window.data_dir)
        self._probe = None
        self._action = None
        self._quit = False
        self._fake_full = False
        self._topmost = False
        self._guard = None
        self._remote_timer = QTimer(window)
        self._remote_timer.setInterval(250)
        self._remote_timer.timeout.connect(self._poll_remote)
        self._remote_dialog_open = False
        self._remote_allow_all = False
        self._poll_timer = QTimer(window)
        self._poll_timer.setInterval(POLL_INTERVAL)
        self._poll_timer.timeout.connect(self._poll)
        self._care_timer = QTimer(window)
        self._care_timer.timeout.connect(self._auto_tick)
        self._apply_care_timer()

    # ---- 装配 -------------------------------------------------------------

    def attach(self, page):
        """接上页面信号并填入已保存的设置。"""
        self.page = page
        page.set_options(self.options)
        page.set_fake_full(False)
        page.set_topmost(False)
        page.set_guard_state(False)
        page.refreshRequested.connect(self.refresh)
        page.repairRequested.connect(self.repair)
        page.fakeFullRequested.connect(self.set_fake_full)
        page.topmostRequested.connect(self.set_topmost)
        page.passwordRequested.connect(self.read_password)
        page.copyPasswordRequested.connect(self.copy_password)
        page.optionChanged.connect(self.set_option)
        page.guardRequested.connect(self.apply_guard)
        page.guardStopRequested.connect(self.stop_guard)
        page.activated.connect(self._start_polling)
        page.deactivated.connect(self._stop_polling)

    def stop(self):
        """窗口关闭前停掉定时器，避免回调打到已销毁的页面。"""
        self._quit = True
        self._poll_timer.stop()
        self._care_timer.stop()
        self._remote_timer.stop()
        if self._guard is not None:
            try:
                self._guard.deny_remote_all()
                classroom.stop_guard(self._guard)
            except Exception as error:
                self.window.logs.warning(CATEGORY, "停止课堂防护失败", str(error))
            self._guard = None
        # 关闭时等待查询/动作线程结束，避免 QThread 在运行中被析构导致进程退出。
        for name in ("_probe", "_action"):
            worker = getattr(self, name)
            if worker is not None and worker.isRunning():
                worker.wait(10000)
            setattr(self, name, None)

    # ---- 轮询 -------------------------------------------------------------

    def _start_polling(self):
        """页面可见：立刻刷新一次，并按固定节奏继续。"""
        if self._quit:
            return
        self._poll_timer.start()
        self.refresh()

    def _stop_polling(self):
        """页面隐藏：停掉列表轮询，自动看护不受影响。"""
        self._poll_timer.stop()

    def _poll(self):
        """定时刷新窗口列表。"""
        self.refresh()

    def refresh(self):
        """后台读取学生端与课堂窗口状态。"""
        if self._quit or self._probe is not None:
            return
        worker = ProbeWorker(
            partial(classroom.snapshot, self.window.data_dir),
            logs=self.window.logs,
            category=CATEGORY,
        )
        worker.setObjectName("classroom-probe")
        worker.completed.connect(self._probe_done)
        worker.failed.connect(self._probe_failed)
        worker.finished.connect(lambda w=worker: self._probe_finished(w))
        worker.finished.connect(worker.deleteLater)
        self._probe = worker
        worker.start()

    def _probe_done(self, snapshot):
        """把快照写进页面；设置以磁盘上的值为准。"""
        if self._quit or self.page is None:
            return
        self.options = snapshot.get("options") or self.options
        self.page.set_snapshot(snapshot)

    def _probe_failed(self, message, details):
        """轮询失败只写日志，避免每 2 秒弹一次提示。"""
        if self._quit:
            return
        self.window.logs.warning(
            CATEGORY, "读取课堂窗口失败", "%s\n%s" % (message, details)
        )

    def _probe_finished(self, worker):
        """查询线程结束后释放引用；先等线程真正停下再丢弃对象。"""
        worker.wait()
        if self._probe is worker:
            self._probe = None

    # ---- 动作 -------------------------------------------------------------

    def _run_action(self, worker):
        """启动一个动作线程；同一时刻只跑一个，避免窗口状态互相覆盖。"""
        if self._quit or self._action is not None or self.page is None:
            return
        self.page.set_busy(True)
        worker.setObjectName("classroom-action")
        worker.completed.connect(self._action_done)
        worker.failed.connect(self._action_failed)
        worker.finished.connect(lambda w=worker: self._action_finished(w))
        worker.finished.connect(worker.deleteLater)
        self._action = worker
        worker.start()

    def repair(self):
        """立即修复所有课堂窗口。"""
        self._run_action(
            TaskWorker(
                _repair_task,
                self.window.data_dir,
                logs=self.window.logs,
                category=CATEGORY,
            )
        )

    def set_fake_full(self, enabled):
        """开启或还原假全屏。"""
        self._run_action(
            TaskWorker(
                _fake_full_task,
                bool(enabled),
                self.window.data_dir,
                logs=self.window.logs,
                category=CATEGORY,
            )
        )

    def set_topmost(self, enabled):
        """设置广播窗口置顶。"""
        self._run_action(
            TaskWorker(
                _topmost_task,
                bool(enabled),
                self.window.data_dir,
                logs=self.window.logs,
                category=CATEGORY,
            )
        )

    def _action_done(self, result):
        """动作完成：更新按钮状态、写日志并刷新列表。"""
        if self._quit or self.page is None:
            return
        if "repaired" in result:
            if result["repaired"]:
                message = "已修复 %d 个课堂窗口" % result["repaired"]
                level = "成功"
            else:
                message = "没有需要修复的课堂窗口"
                level = "信息"
            self.window.logs.info(CATEGORY, "修复课堂窗口", message)
        elif "enabled" in result:
            self._fake_full = bool(result["enabled"])
            self.page.set_fake_full(self._fake_full)
            message = "已开启假全屏" if self._fake_full else "已还原广播窗口"
            level = "成功"
            self.window.logs.info(CATEGORY, message)
        elif "topmost" in result:
            self._topmost = bool(result["topmost"])
            self.page.set_topmost(self._topmost)
            message = "广播窗口已置顶" if self._topmost else "已取消广播窗口置顶"
            level = "成功"
            self.window.logs.info(CATEGORY, message)
        else:
            message = "课堂助手操作完成"
            level = "信息"
        self.page.set_busy(False)
        self.window._notify("课堂助手", message, level)
        self.refresh()

    def _action_failed(self, message, details):
        """动作失败：恢复按钮并提示原因。"""
        if self._quit or self.page is None:
            return
        self.page.set_busy(False)
        self.window.logs.error(
            CATEGORY, "课堂助手操作失败", "%s\n%s" % (message, details)
        )
        self.window._notify("课堂助手", message, "错误")

    def _action_finished(self, worker):
        """动作线程结束后释放引用；先等线程真正停下再丢弃对象。"""
        worker.wait()
        if self._action is worker:
            self._action = None

    def apply_guard(self, flags):
        """启用课堂防护；已启用时只更新策略位。"""
        if self.page is None or self._quit:
            return
        if self._guard is not None:
            try:
                self._guard.update(int(flags))
            except Exception as error:
                self.window.logs.error(CATEGORY, "更新课堂防护失败", str(error))
                self.window._notify("课堂助手", "更新课堂防护失败", "错误")
                return
            self.options["guard_flags"] = int(flags)
            self.page.set_guard_state(True, int(flags))
            self._sync_remote_timer(int(flags))
            self.window._notify("课堂助手", "课堂防护策略已更新", "成功")
            return
        if self._action is not None:
            return
        self.page.set_busy(True)
        worker = TaskWorker(
            _guard_start_task,
            int(flags),
            self.window.data_dir,
            logs=self.window.logs,
            category=CATEGORY,
        )
        worker.setObjectName("classroom-guard")
        worker.completed.connect(self._guard_started)
        worker.failed.connect(self._guard_failed)
        worker.finished.connect(lambda w=worker: self._action_finished(w))
        worker.finished.connect(worker.deleteLater)
        self._action = worker
        worker.start()

    def _guard_started(self, result):
        """防护加载成功：保存会话并更新状态。"""
        if self._quit or self.page is None:
            # 窗口在注入期间关闭时信号仍会到达，必须在这里卸掉已注入的 DLL。
            try:
                classroom.stop_guard(result.get("session"))
            except Exception as error:
                self.window.logs.warning(CATEGORY, "停止课堂防护失败", str(error))
            return
        self._guard = result.get("session")
        self.page.set_busy(False)
        self.page.set_guard_state(True, result.get("flags", 0), result.get("pid", 0))
        self._sync_remote_timer(int(result.get("flags", 0)))
        self.window.logs.info(
            CATEGORY,
            "已启用课堂防护",
            "学生端进程 %s，策略位 %s" % (result.get("pid"), result.get("flags")),
        )
        self.window._notify("课堂助手", "课堂防护已启用", "成功")

    def _guard_failed(self, message, details):
        """防护加载失败：恢复按钮并提示。"""
        if self._quit or self.page is None:
            return
        self.page.set_busy(False)
        self.window.logs.error(
            CATEGORY, "启用课堂防护失败", "%s\n%s" % (message, details)
        )
        self.window._notify("课堂助手", message, "错误")

    def _sync_remote_timer(self, flags):
        """按当前策略位启停远程命令轮询。"""
        if self._guard is not None and int(flags) & guard.GUARD_BLOCK_REMOTE:
            self._remote_timer.start()
        else:
            self._remote_timer.stop()
            self._remote_allow_all = False

    def _poll_remote(self):
        """轮询学生端待确认的远程命令，一次只弹一个对话框。"""
        if self._quit or self._guard is None or self._remote_dialog_open:
            return
        try:
            requests = self._guard.poll_remote()
        except Exception as error:
            self.window.logs.warning(CATEGORY, "读取远程命令请求失败", str(error))
            return
        for request in requests:
            if self._remote_allow_all:
                self._guard.resolve_remote(request.index, True)
                continue
            self._show_remote_dialog(request)
            return

    def _show_remote_dialog(self, request):
        """弹窗询问一条远程命令是否允许执行。"""
        self._remote_dialog_open = True
        try:
            dialog = self.window._dialog(
                "远程命令请求",
                "学生端收到一条远程命令：\n\n%s\n\n是否允许执行？" % request.command,
                "允许执行",
            )
            allow_all = QCheckBox("本次运行期间全部允许", dialog)
            dialog.textLayout.addWidget(allow_all)
            allowed = bool(dialog.exec())
            if self._guard is None:
                return
            self._guard.resolve_remote(request.index, allowed)
            if allowed and allow_all.isChecked():
                self._remote_allow_all = True
            self.window.logs.info(
                CATEGORY,
                "远程命令已允许" if allowed else "远程命令已拒绝",
                request.command,
            )
        except Exception as error:
            self.window.logs.error(CATEGORY, "处理远程命令请求失败", str(error))
            if self._guard is not None:
                self._guard.resolve_remote(request.index, False)
        finally:
            self._remote_dialog_open = False

    def stop_guard(self):
        """停止课堂防护并卸载 DLL。"""
        if self._guard is None:
            return
        session = self._guard
        self._guard = None
        self._remote_timer.stop()
        self._remote_allow_all = False
        try:
            session.deny_remote_all()
            classroom.stop_guard(session)
        except Exception as error:
            self.window.logs.error(CATEGORY, "停止课堂防护失败", str(error))
            self.window._notify("课堂助手", "停止课堂防护失败", "错误")
        else:
            self.window.logs.info(CATEGORY, "已停止课堂防护", "")
            self.window._notify("课堂助手", "课堂防护已停止", "成功")
        if self.page is not None:
            self.page.set_guard_state(False)

    # ---- 密码 -------------------------------------------------------------

    def read_password(self):
        """后台读取注册表里的极域解锁密码。"""
        if self._quit or self._probe is not None or self._action is not None:
            return
        if self.page is None:
            return
        self.page.set_busy(True)
        worker = ProbeWorker(
            classroom.read_password, logs=self.window.logs, category=CATEGORY
        )
        worker.completed.connect(self._password_done)
        worker.failed.connect(self._password_failed)
        worker.finished.connect(lambda w=worker: self._probe_finished(w))
        worker.finished.connect(worker.deleteLater)
        self._probe = worker
        worker.start()

    def _password_done(self, result):
        """展示密码或失败原因。"""
        if self._quit or self.page is None:
            return
        self.page.set_busy(False)
        self.page.set_password(result)
        if result.get("password"):
            self.window.logs.info(
                CATEGORY,
                "已读取解锁密码",
                "来源：%s" % result.get("source"),
            )
        else:
            self.window.logs.warning(
                CATEGORY,
                "没有读到解锁密码",
                result.get("error") or "注册表中没有可用的值",
            )

    def _password_failed(self, message, details):
        """读取异常：恢复按钮并写日志。"""
        if self._quit or self.page is None:
            return
        self.page.set_busy(False)
        self.window.logs.error(
            CATEGORY, "读取解锁密码失败", "%s\n%s" % (message, details)
        )
        self.window._notify("课堂助手", message, "错误")

    def copy_password(self, text):
        """把密码复制到剪贴板。"""
        if not text:
            self.window._notify("尚未读取", "先读取解锁密码再复制", "警告")
            return
        QGuiApplication.clipboard().setText(text)
        self.window.logs.info(CATEGORY, "已复制解锁密码", "内容不写入日志")
        self.window._notify("已复制", "解锁密码已复制到剪贴板", "成功")

    # ---- 设置 -------------------------------------------------------------

    def set_option(self, key, value):
        """保存单项设置；看护相关改动立即生效。"""
        result = classroom.save_option(key, value, self.window.data_dir)
        if not result["ok"]:
            self.window.logs.warning(
                CATEGORY, "课堂助手设置保存失败", result["message"]
            )
            self.window._notify("课堂助手", result["message"], "警告")
            return
        name = OPTION_NAMES.get(key)
        if name:
            self.options[name] = value
        if key in (SETTINGS_AUTO_REPAIR, SETTINGS_INTERVAL):
            self._apply_care_timer()
        if key == SETTINGS_GUARD_FLAGS and self._guard is not None:
            try:
                self._guard.update(int(value))
                self.page.set_guard_state(True, int(value))
                self._sync_remote_timer(int(value))
            except Exception as error:
                self.window.logs.warning(CATEGORY, "课堂防护策略更新失败", str(error))
        if key == SETTINGS_AUTO_REPAIR and value:
            self._auto_tick()

    def _apply_care_timer(self):
        """按设置启动或停掉自动看护定时器。"""
        if self._quit:
            self._care_timer.stop()
            return
        interval = int(self.options.get("interval", 3)) * 1000
        self._care_timer.setInterval(max(interval, 1000))
        if self.options.get("auto_repair"):
            self._care_timer.start()
        else:
            self._care_timer.stop()

    def _auto_tick(self):
        """自动看护的一次轮询；有任务在跑时跳过这一拍。

        后台看护不占用页面忙碌状态，也不弹提示，只在真的修了窗口时写日志。
        """
        if self._quit or self._action is not None or self._probe is not None:
            return
        worker = TaskWorker(
            _auto_tick_task,
            self.window.data_dir,
            logs=self.window.logs,
            category=CATEGORY,
        )
        worker.setObjectName("classroom-auto")
        worker.completed.connect(self._auto_tick_done)
        worker.failed.connect(self._auto_tick_failed)
        worker.finished.connect(lambda w=worker: self._action_finished(w))
        worker.finished.connect(worker.deleteLater)
        self._action = worker
        worker.start()

    def _auto_tick_done(self, result):
        """看护完成：只有真的修复了窗口才记日志并刷新列表。"""
        if self._quit or not result.get("repaired"):
            return
        self.window.logs.info(
            CATEGORY,
            "自动看护修复课堂窗口",
            "本次修复 %d 个" % result["repaired"],
        )
        self.refresh()

    def _auto_tick_failed(self, message, details):
        """看护失败只写日志，避免每个间隔弹一次提示。"""
        if self._quit:
            return
        self.window.logs.warning(
            CATEGORY, "自动看护失败", "%s\n%s" % (message, details)
        )
