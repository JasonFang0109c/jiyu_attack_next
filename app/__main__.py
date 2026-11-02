"""统一入口：无参数启动图形界面，有参数运行命令行模式。"""

from multiprocessing import freeze_support
import sys


def _rebind_inherited_streams(kernel32):
    """沿用调用方重定向的标准句柄，句柄指向控制台时返回 False。"""
    import ctypes
    import msvcrt
    import os

    kernel32.GetStdHandle.restype = ctypes.c_void_p
    kernel32.GetFileType.argtypes = [ctypes.c_void_p]
    kernel32.GetFileType.restype = ctypes.c_uint
    console_type = 2
    rebound = False
    for std_id, name in ((-11, "stdout"), (-12, "stderr")):
        if getattr(sys, name) is not None:
            continue
        handle = kernel32.GetStdHandle(std_id)
        # 0 与 INVALID_HANDLE_VALUE 都表示没有可用的标准句柄。
        if not handle or handle == ctypes.c_void_p(-1).value:
            continue
        # 控制台句柄要等挂上父控制台后才能写入，交给后面的分支处理。
        if kernel32.GetFileType(handle) == console_type:
            continue
        descriptor = msvcrt.open_osfhandle(handle, os.O_WRONLY)
        setattr(
            sys,
            name,
            os.fdopen(descriptor, "w", encoding="utf-8", errors="replace", buffering=1),
        )
        rebound = True
    return rebound


def _rebind_console_streams():
    """窗口化子系统下标准流为空，接上控制台后重新打开输出设备。"""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(
                sys,
                name,
                open(
                    "CONOUT$",
                    "w",
                    encoding="utf-8",
                    errors="replace",
                    buffering=1,
                ),
            )


def _show_cli_console():
    """把命令行模式的输出接回调用方的控制台。

    打包产物是窗口化子系统，双击启动不会出现控制台窗口；带参数运行时
    标准流是空的，不加处理会直接丢掉 CLI 输出。这里先沿用调用方重定向
    的句柄，再挂到父进程的控制台，都没有时新建一个控制台。
    """
    if sys.platform != "win32":
        return
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        _rebind_inherited_streams(kernel32)
        if sys.stdout is not None and sys.stderr is not None:
            return
        if not kernel32.AttachConsole(-1) and not kernel32.AllocConsole():
            return
        _rebind_console_streams()
    except Exception:
        # 取不到控制台时不能让命令本身失败：输出丢失比进程崩溃更容易排查。
        pass


def main(argv=None):
    """按是否带参数分发到命令行或图形界面入口。

    Args:
        argv: 参数列表，None 表示从 ``sys.argv`` 读取。

    Returns:
        int: 对应入口返回的退出码。
    """
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
