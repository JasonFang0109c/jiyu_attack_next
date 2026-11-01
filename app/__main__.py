"""统一入口：无参数启动图形界面，有参数运行命令行模式。"""

from multiprocessing import freeze_support
import sys


def _show_cli_console():
    """CLI 模式确保控制台窗口可见，双击 GUI 时不显示控制台。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        window = ctypes.windll.kernel32.GetConsoleWindow()
        if window:
            ctypes.windll.user32.ShowWindow(window, 5)
    except Exception:
        pass


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        if arguments[0] != "--firewall-helper":
            _show_cli_console()
        from app.cli.main import main as run_cli

        return run_cli(arguments)
    from app.gui.app import main as run_gui

    return run_gui()


if __name__ == "__main__":
    freeze_support()
    sys.exit(main())
