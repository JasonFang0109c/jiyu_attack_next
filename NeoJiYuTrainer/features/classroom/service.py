"""课堂助手业务层：识别课堂窗口、按设置批量修复并读取解锁密码。

本模块不依赖 Qt，界面服务与单元测试都直接调用这些函数；所有操作只作用于
``StudentMain.exe`` 自己的顶层窗口，不注入进程、不触碰驱动。
"""

from NeoJiYuTrainer.features.classroom import passwords, windows
from NeoJiYuTrainer.features.classroom.data import (
    DEFAULT_ALLOW_TOP,
    DEFAULT_AUTO_REPAIR,
    DEFAULT_GUARD_FLAGS,
    DEFAULT_HIDE_BLACK_SCREEN,
    DEFAULT_INCLUDE_FULLSCREEN,
    DEFAULT_INTERVAL,
    INTERVAL_RANGE,
    SETTINGS_ALLOW_TOP,
    SETTINGS_AUTO_REPAIR,
    SETTINGS_GUARD_FLAGS,
    SETTINGS_HIDE_BLACK_SCREEN,
    SETTINGS_INCLUDE_FULLSCREEN,
    SETTINGS_INTERVAL,
)
from NeoJiYuTrainer.features.settings.service import portable_settings
from NeoJiYuTrainer.features.student.service import find_student_processes
from NeoJiYuTrainer.shared.resources import resource_path
from NeoJiYuTrainer.shared.settings import STATUS_NO_ERROR
from NeoJiYuTrainer.system.windows import guard

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _as_bool(value, default):
    """把设置文件里的布尔值（可能是字符串）转成 bool。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_VALUES
    return default


def _as_flags(value):
    """把设置里的防护位限制在已定义范围内。"""
    try:
        flags = int(value)
    except (TypeError, ValueError):
        return DEFAULT_GUARD_FLAGS
    return flags & guard.GUARD_ALL


def _as_interval(value):
    """把轮询间隔夹到 1–10 秒，非法值回落到默认值。"""
    try:
        interval = int(value)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL
    low, high = INTERVAL_RANGE
    return min(max(interval, low), high)


def load_options(data_dir=None):
    """读取课堂助手设置。

    Args:
        data_dir: 数据目录，测试可指向临时目录；None 用默认数据目录。

    Returns:
        dict: ``auto_repair``、``interval``、``allow_top``、
        ``include_fullscreen`` 与 ``hide_black_screen``。
    """
    store = portable_settings(data_dir)
    return {
        "auto_repair": _as_bool(
            store.value(SETTINGS_AUTO_REPAIR, DEFAULT_AUTO_REPAIR),
            DEFAULT_AUTO_REPAIR,
        ),
        "interval": _as_interval(store.value(SETTINGS_INTERVAL, DEFAULT_INTERVAL)),
        "allow_top": _as_bool(
            store.value(SETTINGS_ALLOW_TOP, DEFAULT_ALLOW_TOP), DEFAULT_ALLOW_TOP
        ),
        "include_fullscreen": _as_bool(
            store.value(SETTINGS_INCLUDE_FULLSCREEN, DEFAULT_INCLUDE_FULLSCREEN),
            DEFAULT_INCLUDE_FULLSCREEN,
        ),
        "hide_black_screen": _as_bool(
            store.value(SETTINGS_HIDE_BLACK_SCREEN, DEFAULT_HIDE_BLACK_SCREEN),
            DEFAULT_HIDE_BLACK_SCREEN,
        ),
        "guard_flags": _as_flags(
            store.value(SETTINGS_GUARD_FLAGS, DEFAULT_GUARD_FLAGS)
        ),
    }


def save_option(key, value, data_dir=None):
    """写入一项课堂助手设置并立即落盘。

    Returns:
        dict: ``ok`` 是否保存成功，``message`` 为失败原因。
    """
    store = portable_settings(data_dir)
    store.set_value(key, value)
    store.sync()
    return {
        "ok": store.status() == STATUS_NO_ERROR,
        "message": store.message,
    }


def student_pid(processes=None):
    """返回学生端进程号；优先采用同目录带 ``LibTDMaster.dll`` 的真身。"""
    rows = find_student_processes() if processes is None else processes
    if not rows:
        return 0
    genuine = [row for row in rows if row.get("genuine")]
    return int((genuine or rows)[0]["pid"])


def collect(pid, options):
    """按设置收集某进程的课堂窗口。"""
    if not pid or not windows.available():
        return []
    return windows.collect_windows(pid, options["include_fullscreen"])


def snapshot(data_dir=None):
    """一次拿到页面需要的全部状态。

    Returns:
        dict: ``supported`` 当前系统是否支持窗口操作，``student_running``
        是否有学生端进程，``student_pid`` 选中的进程号，``windows`` 窗口
        列表，``options`` 当前设置。
    """
    options = load_options(data_dir)
    processes = find_student_processes()
    pid = student_pid(processes)
    return {
        "supported": windows.available(),
        "student_running": bool(processes),
        "student_pid": pid,
        "windows": collect(pid, options),
        "options": options,
    }


def repair(data_dir=None, options=None):
    """立即修复所有需要处理的课堂窗口。

    Returns:
        dict: ``repaired`` 改动数量，``windows`` 修复后的窗口列表，
        ``student_pid`` 学生端进程号。
    """
    options = options if options is not None else load_options(data_dir)
    pid = student_pid()
    targets = collect(pid, options)
    repaired = 0
    for window in targets:
        if windows.needs_repair(
            window, options["allow_top"], options["hide_black_screen"]
        ):
            windows.repair_window(
                window, options["allow_top"], options["hide_black_screen"]
            )
            repaired += 1
    return {"repaired": repaired, "windows": collect(pid, options), "student_pid": pid}


def auto_tick(data_dir=None):
    """自动看护的一次轮询，关闭看护时直接返回。

    Returns:
        dict: ``repaired`` 改动数量，``enabled`` 看护是否开启。
    """
    options = load_options(data_dir)
    if not options["auto_repair"]:
        return {"repaired": 0, "enabled": False}
    result = repair(options=options)
    result["enabled"] = True
    return result


def toggle_fake_full(enabled, data_dir=None):
    """开关假全屏。

    Args:
        enabled: True 把广播窗口铺满并置顶，False 还原成居中窗口。

    Returns:
        dict: ``enabled`` 目标状态，``windows`` 操作后的窗口列表。
    """
    options = load_options(data_dir)
    pid = student_pid()
    targets = collect(pid, options)
    if enabled:
        windows.fake_full(targets)
    else:
        windows.restore_windowed(
            targets, options["allow_top"], options["hide_black_screen"]
        )
    return {
        "enabled": bool(enabled),
        "windows": collect(pid, options),
        "student_pid": pid,
    }


def set_topmost(enabled, data_dir=None):
    """批量设置广播窗口置顶。"""
    options = load_options(data_dir)
    pid = student_pid()
    targets = collect(pid, options)
    windows.set_topmost(targets, enabled)
    return {"topmost": bool(enabled), "windows": collect(pid, options)}


def read_password():
    """读取极域解锁密码，结果见 ``passwords.read_password``。"""
    return passwords.read_password()


def _guard_dll(pid):
    """按学生端位数选择课堂防护 DLL，并确认资源存在。"""
    name = "guard_x86.dll" if guard.is_32bit(pid) else "guard_x64.dll"
    path = resource_path("native", name)
    if not path.is_file():
        raise RuntimeError(f"缺少课堂防护组件：{name}")
    return path


def start_guard(flags, data_dir=None):
    """向学生端进程注入课堂防护 DLL 并安装钩子。

    Args:
        flags: ``GUARD_ITEMS`` 中各项按位或出的防护位。
        data_dir: 兼容统一服务签名，本函数不读设置。

    Returns:
        dict: ``pid``、``flags`` 与会话对象 ``session``（供停止时使用）。
    """
    if not guard.supported():
        raise RuntimeError("当前系统不支持课堂防护")
    pid = student_pid()
    if not pid:
        raise RuntimeError("学生端未运行，无法启用课堂防护")
    masked = int(flags) & guard.GUARD_ALL
    session = guard.GuardSession(pid, str(_guard_dll(pid)))
    session.start(masked)
    return {"pid": pid, "flags": masked, "session": session}


def stop_guard(session):
    """卸载课堂防护并释放目标进程中的 DLL。"""
    if session is not None:
        session.stop()
