import argparse
import os
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

from app.gui import app as gui


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", required=True)
    parser.add_argument("--page", choices=["message", "command", "device", "aliases", "local", "firewall", "logs", "settings", "about"], default="message")
    parser.add_argument("--theme", choices=["light", "dark"], default="light")
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--width", type=int, default=1180)
    parser.add_argument("--height", type=int, default=760)
    args = parser.parse_args()
    Path(args.screenshot).parent.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen")
    app = QApplication(sys.argv)
    gui.configure_application(app)
    if args.theme == "dark":
        gui.setTheme(gui.Theme.DARK)
    settings_dir = tempfile.TemporaryDirectory()
    settings = QSettings(str(Path(settings_dir.name) / "settings.ini"), QSettings.IniFormat)
    alias_store = gui.DeviceAliasStore(settings=settings)
    window = gui.MainWindow(alias_store=alias_store)
    window.resize(args.width, args.height)
    if args.sample:
        window.pages["message"].editor.setPlainText("维护通知\n\n请保存当前工作，准备进行例行维护。\n维护结束后将另行通知。")
        window.pages["command"].editor.setPlainText("cmd.exe /c ipconfig")
        window.alias_store.add("教室 A 讲台", "192.168.1.10")
        window.alias_store.add("一号机房", "192.168.1.11")
        window.connection_state.set_value("target", "教室 A 讲台")
        window.logs.add("应用", "本地界面预览已载入")
    window.show_page(args.page)
    window.show()

    def capture():
        image = window.grab()
        ok = image.save(args.screenshot, "PNG")
        print("截图保存%s：%s (%dx%d)" % (
            "成功" if ok else "失败", args.screenshot, image.width(), image.height()))
        app.exit(0 if ok else 1)

    QTimer.singleShot(450, capture)
    result = app.exec()
    window.close()
    window.deleteLater()
    gui.QCoreApplication.sendPostedEvents(None, gui.QEvent.DeferredDelete)
    app.processEvents()
    settings_dir.cleanup()
    return result


if __name__ == "__main__":
    sys.exit(main())
