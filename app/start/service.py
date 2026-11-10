"""按调用参数选择命令行或图形界面生命周期。"""

import sys

from app.start.console import _show_cli_console


def main(argv=None):
    """按是否带参数分发到命令行或图形界面入口。

    Args:
        argv: 参数列表，None 表示从 ``sys.argv`` 读取。

    Returns:
        int: 对应入口返回的退出码。
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        # 两个提权助手都在后台执行，挂控制台没有意义还会闪窗。
        if arguments[0] not in ("--firewall-helper", "--student-helper"):
            _show_cli_console()
        from app.start.cli import main as run_cli

        return run_cli(arguments)
    from app.start.gui import main as run_gui

    return run_gui()
