"""学生端识别与启停的固定数据、设置键与规范化规则。"""

import sys

# 提权助手进程的入口参数，由 ``app/__main__.py`` 转发给学生端服务。
STUDENT_HELPER_ARGUMENT = "--student-helper"

STUDENT_RESULT_ARGUMENT = "--student-result"

# 映像名里带这个片段的都算学生端；极域各版本分别叫 StudentMain.exe 与
# StudentMain64.exe，按片段匹配比写死两个名字更稳。
STUDENT_NAME_MARKER = "student"

# 学生端主程序的文件名，各版本与安装方式的差异都在这里列出。
STUDENT_EXECUTABLE_NAMES = (
    "StudentMain.exe",
    "StudentMain64.exe",
    "Student.exe",
)

# 真身标志：极域学生端目录里一定有这个库，别的软件同名进程没有。
STUDENT_LIBRARY = "LibTDMaster.dll"

# 卸载信息里的固定键名，JiYuTrainer 也是先读这里。
STUDENT_UNINSTALL_KEY = "e-Learning Class V6.0"

# 极域课堂的默认端口，学生端在运行时会独占本机该 UDP 端口。
STUDENT_PORT = 4705

# 监听 4705 但又不属于学生端的进程名片段，用于过滤本程序自己的绑定。
STUDENT_PORT_MARKERS = ("student", "jiyu", "mythware", "tdmaster")

# 手工指定过的程序路径，启动时优先使用，避免每次都扫注册表与磁盘。
STUDENT_EXE_SETTINGS_KEY = "core/student/exe_path"

# 启动后等待学生端进程出现的上限：ShellExecute 到进程真正建好可能要几秒。
START_TIMEOUT = 8.0

# 结束前给窗口关闭消息的等待时间，极域学生端通常不响应，超时就直接结束。
GRACEFUL_TIMEOUT = 0.6

# 单个进程强制结束后的等待时间。
FORCED_TIMEOUT = 2.5

# 结束后观察是否有守护服务把学生端重新拉起的时间窗口。
RESPAWN_WINDOW = 2.0

# 轮询进程列表的间隔。
POLL_INTERVAL = 0.2

# 守护服务的匹配关键字，与学生端安装目录的线索一致。
GUARDIAN_MARKERS = ("Mythware", "TopDomain", "e-Learning", "Student", "JiYu")

# 路径用 chr(92) 拼，避免源码里满屏反斜杠转义。
SEP = chr(92)
STUDENT_DIRECTORIES = (
    tuple(
        SEP.join(parts)
        for parts in (
            ["C:", "Program Files", "Mythware", "e-Learning Class"],
            ["C:", "Program Files (x86)", "Mythware", "e-Learning Class"],
            ["C:", "Program Files", "Mythware", "多媒体教学管理系统V6.0 2016 豪华版"],
            [
                "C:",
                "Program Files (x86)",
                "Mythware",
                "多媒体教学管理系统V6.0 2016 豪华版",
            ],
            ["C:", "e-Learning Class"],
            ["C:", "多媒体教学管理系统V6.0 2016 豪华版"],
        )
    )
    + tuple(
        SEP.join(["C:", "Program Files", folder, "e-Learning Class Standard", "1.00"])
        for folder in ("TopDomain", "Mythware", "JiYu")
    )
    + tuple(
        SEP.join(
            ["C:", "Program Files (x86)", folder, "e-Learning Class Standard", "1.00"]
        )
        for folder in ("TopDomain", "Mythware", "JiYu")
    )
)


def normalize_executable_path(value):
    """把设置里保存的路径规范化，空值与平台不符时返回空字符串。

    Args:
        value: 从设置文件读出的原始值。

    Returns:
        str: 去掉引号与首尾空白后的路径；无效时为空字符串。
    """
    text = str(value or "").strip().strip('"')
    if not text or sys.platform != "win32":
        return ""
    return text


def registry_paths():
    """拼出精确键与通配键的 PowerShell 路径参数，避免源码里写反斜杠转义。

    Returns:
        dict[str, list[str]]: ``exact`` 与 ``wildcard`` 两组注册表路径。
    """
    sep = chr(92)
    base = ["SOFTWARE", "Microsoft", "Windows", "CurrentVersion", "Uninstall"]
    exact = [*base, STUDENT_UNINSTALL_KEY]
    wow = ["SOFTWARE", "WOW6432Node", *base[1:], STUDENT_UNINSTALL_KEY]
    wildcard = [*base, "*"]
    wildcard_wow = ["SOFTWARE", "WOW6432Node", *base[1:], "*"]
    return {
        "exact": ["HKLM:" + sep.join(exact), "HKLM:" + sep.join(wow)],
        "wildcard": ["HKLM:" + sep.join(wildcard), "HKLM:" + sep.join(wildcard_wow)],
    }
