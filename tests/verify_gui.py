"""渲染图形界面并保存截图，供人工核对布局。"""

import argparse
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.gui import app as gui
from app.gui.models import DATA_DIRECTORY_NAME, portable_settings


def main():
    """打开主窗口并按命令行参数截图，返回进程退出码。

    ``--page`` 选择页面，``--theme`` 选择主题，``--sample`` 预填示例
    数据，``--select-all`` 勾选全部日志，截图保存到 ``--screenshot``。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", required=True)
    parser.add_argument(
        "--page",
        choices=[
            "home",
            "message",
            "command",
            "device",
            "file",
            "aliases",
            "appcmd",
            "students",
            "screen",
            "control",
            "chat",
            "closewindow",
            "shell",
            "local",
            "firewall",
            "studentproc",
            "logs",
            "settings",
            "about",
        ],
        default="home",
    )
    parser.add_argument("--theme", choices=["light", "dark"], default="light")
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--select-all", action="store_true")
    parser.add_argument("--width", type=int, default=1180)
    parser.add_argument("--height", type=int, default=1000)
    args = parser.parse_args()
    Path(args.screenshot).parent.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault(
        "QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen"
    )
    app = QApplication(sys.argv)
    gui.configure_application(app)
    data_root = Path("build") / "verify-gui-data"
    data_dir = data_root / DATA_DIRECTORY_NAME
    data_dir.mkdir(parents=True, exist_ok=True)
    settings = portable_settings(data_dir)
    settings.set_value(gui.FIRST_CLOSE_PROMPT_SETTINGS_KEY, True)
    settings.sync()
    alias_store = gui.DeviceAliasStore(settings=settings)
    window = gui.MainWindow(alias_store=alias_store, data_dir=data_dir)
    # 主窗口构造时会按设置重设主题，暗色要在窗口建好之后再切，截图才是暗色。
    if args.theme == "dark":
        gui.setTheme(gui.Theme.DARK)
    # 截图只能抓到窗口自己画的内容，材质透明区域会留白；
    # 固定成纯色背景，暗色截图的文字才有真实底色可对照。
    window.window_material = gui.MATERIAL_SOLID
    window.apply_window_material(gui.MATERIAL_SOLID)
    window.resize(args.width, args.height)
    if args.sample:
        window.logs.clear()
        window.pages["message"].editor.setPlainText(
            "维护通知\n\n请保存当前工作，准备进行例行维护。\n维护结束后将另行通知。"
        )
        window.pages["command"].editor.setPlainText("cmd.exe /c ipconfig")
        if window.alias_store.match("教室 A 讲台") is None:
            window.alias_store.add("教室 A 讲台", "192.168.1.10")
        if window.alias_store.match("一号机房") is None:
            window.alias_store.add("一号机房", "192.168.1.11")
        window.connection_state.set_value("target", "教室 A 讲台")
        sample_file = data_root / "维护通知.pdf"
        sample_file.write_bytes(b"preview")
        window.pages["file"].set_file(sample_file)
        window.pages["file"].set_progress(65)
        window.logs.add("应用", "本地界面预览已载入")
        window.logs.warning("远程命令", "模拟目标未响应，准备重试")
        window.logs.error("文件传送", "模拟下载失败：连接超时")
    if args.select_all:
        window.pages["logs"].select_all_checkbox.click()
    window.show_page(args.page)
    window.show()

    def capture():
        # 侧边栏的折叠状态跟窗口宽度走，上一次窄窗口运行会把状态留在配置里，
        # 截图前显式展开，画面才是用户默认看到的样子。
        window.expand_navigation()
        app.processEvents()
        image = window.grab()
        ok = image.save(args.screenshot, "PNG")
        print(
            "截图保存%s：%s (%dx%d)"
            % (
                "成功" if ok else "失败",
                args.screenshot,
                image.width(),
                image.height(),
            )
        )
        app.exit(0 if ok else 1)

    QTimer.singleShot(450, capture)
    result = app.exec()
    window.quit_application()
    window.deleteLater()
    gui.QCoreApplication.sendPostedEvents(None, gui.QEvent.DeferredDelete)
    app.processEvents()
    return result


if __name__ == "__main__":
    sys.exit(main())
