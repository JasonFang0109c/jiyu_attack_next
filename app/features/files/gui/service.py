"""FileService 的界面协调逻辑。"""

from threading import Event

from PySide6.QtWidgets import QFileDialog

import app.features.files.service as files_service
import app.system.net.targets as system_net_targets
from app.gui.window.data import CATEGORIES
from app.gui.workers.tasks import TaskWorker


class FileService:
    """组织同一职责的界面操作，保留窗口作为 Qt 信号接收者。"""

    def __init__(self, window):
        self.window = window

    def choose_transfer_files(self):
        """选择单个或多个文件加入待传送列表。"""
        window = self.window
        filenames, _ = QFileDialog.getOpenFileNames(
            window, "选择要传送的文件", "", "所有文件 (*)"
        )
        if not filenames:
            window.logs.info(CATEGORIES["file"], "用户取消了文件选择")
            return
        window._add_transfer_paths(filenames)

    def choose_transfer_folder(self):
        """选择文件夹，整个目录会按原结构传送到目标桌面。"""
        window = self.window
        directory = QFileDialog.getExistingDirectory(window, "选择要传送的文件夹")
        if not directory:
            window.logs.info(CATEGORIES["file"], "用户取消了文件夹选择")
            return
        window._add_transfer_paths([directory])

    def _add_transfer_paths(self, paths):
        """把路径展开成文件条目并加入列表，重复项会被忽略。"""
        window = self.window
        page = window.pages["file"]
        try:
            count, size = page.add_paths(paths)
        except (OSError, ValueError) as error:
            window.logs.error(
                CATEGORIES["file"],
                "无法添加待传送文件",
                "路径：%s；异常：%s" % ("；".join(map(str, paths)), error),
            )
            window._notify("无法添加文件", str(error), "错误")
            return
        if not count:
            window.logs.info(
                CATEGORIES["file"],
                "所选文件已在待传送列表中",
                "路径：%s" % "；".join(map(str, paths)),
            )
            window._notify("未添加文件", "所选文件已在待传送列表中", "信息")
            return
        page.footer.set_status(
            "已添加 %d 个文件（%s）" % (count, files_service.format_size(size))
        )
        window.logs.info(
            CATEGORIES["file"],
            "已添加 %d 个待传送文件（%s）" % (count, files_service.format_size(size)),
            "路径：%s；总字节数：%d" % ("；".join(map(str, paths)), size),
        )

    def delete_transfer_files(self):
        """从待传送列表移除选中项，不删除源文件。"""
        window = self.window
        page = window.pages["file"]
        selected = page.selected_entries()
        if not selected:
            window.logs.warning(CATEGORIES["file"], "未勾选待传送条目，无法删除")
            return
        if not window._confirm(
            "删除待传送文件",
            "确定从待传送列表中移除选中的 %d 项（文件或文件夹）？源文件不会被删除。"
            % len(selected),
            "删除",
        ):
            window.logs.info(
                CATEGORIES["file"],
                "用户取消了待传送文件删除",
                "选中项：%d" % len(selected),
            )
            return
        removed = page.remove_selected()
        window.logs.info(
            CATEGORIES["file"],
            "已从待传送列表移除 %d 个文件" % len(removed),
            "条目：%s" % "；".join(relative for _, relative, _ in removed),
        )

    def start_file_transfer(self):
        """校验待传送条目与目标后，把传送任务加入队列。"""
        window = self.window
        page = window.pages["file"]
        selected = page.selected_items()
        if not page.has_files():
            window._validation_error("file", "请先选择要传送的文件")
            return
        if not selected:
            window._validation_error("file", "请勾选要传送的文件或文件夹")
            return
        target = window.connection_state.resolve_target().strip()
        try:
            hosts = system_net_targets.get_ip(target)
        except ValueError as error:
            page.targets.target_input.setError(True)
            window._validation_error("file", str(error))
            return
        try:
            entries = files_service.normalize_transfer_items(selected)
            source = files_service.validate_file_transfer(
                target, window.connection_state.values["port"], str(entries[0][0])
            )
        except ValueError as error:
            window._validation_error("file", str(error))
            return
        total_size = sum(size for _, _, size in entries)
        # 单个文件显示名字，多个文件只报数量，避免对话框被长路径撑开。
        file_label = source.name if len(entries) == 1 else "%d 个文件" % len(entries)
        if not window._confirm(
            "确认传送文件",
            "目标：%s\n目标数量：%d\n文件：%s\n大小：%s\n目标保存位置：当前用户桌面"
            % (target, len(hosts), file_label, files_service.format_size(total_size)),
        ):
            window.logs.info(
                CATEGORIES["file"],
                "用户取消了文件传送确认",
                "目标：%s；文件：%s" % (target, file_label),
            )
            return
        cancel_event = Event()
        window.logs.info(
            CATEGORIES["file"],
            "开始传送：%s → %s（%d 个目标）" % (file_label, target, len(hosts)),
            "文件：%s；文件数：%d；总字节数：%d；目标数：%d；端口：%d；"
            "单目标超时：120 秒"
            % (
                file_label,
                len(entries),
                total_size,
                len(hosts),
                window.connection_state.values["port"],
            ),
        )
        window.logs.debug(
            CATEGORIES["file"],
            "待传送文件清单",
            "；".join(
                "%s (%d 字节)" % (relative, size) for _, relative, size in entries
            ),
        )
        window._begin_task(
            "file",
            TaskWorker(
                files_service.transfer_file,
                target,
                window.connection_state.values["port"],
                str(entries[0][0]),
                None,
                120,
                cancel_event=cancel_event,
                items=[(str(path), relative) for path, relative, _ in entries],
            ),
            window._file_finished,
            window._file_failed,
        )

    def _file_finished(self, result):
        window = self.window
        page = window.pages["file"]
        page.set_progress(100)
        targets = result.get("targets") or [result.get("target", "")]
        file_count = int(result.get("file_count") or 1)
        label = result["name"] if file_count == 1 else "%d 个文件" % file_count
        if len(targets) == 1:
            message = "文件已传送到目标桌面：%s（%s）" % (
                label,
                files_service.format_size(result["size"]),
            )
        else:
            message = "文件已传送到 %d 个目标桌面：%s（%s）" % (
                len(targets),
                label,
                files_service.format_size(result["size"]),
            )
        page.footer.set_status(message)
        window.logs.info(
            CATEGORIES["file"],
            message,
            "目标：%s；目标数量：%d；文件：%s；文件数：%d；字节数：%s"
            % (result["target"], len(targets), label, file_count, result["size"]),
        )
        window._notify("文件传送完成", message, "成功")

    def _file_failed(self, message, details=""):
        window = self.window
        page = window.pages["file"]
        page.reset_progress()
        page.footer.set_status(message)
        window._report_failure(
            CATEGORIES["file"], message, details, ("传送已取消", "文件传送失败")
        )
