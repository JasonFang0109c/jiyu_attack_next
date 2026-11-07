"""命令行参数解析：按图形界面的分组提供分类子命令，并保留扁平写法。

图形界面的侧边栏分成“远程攻击”“教师端模拟”“本机工具”三组，每组下面是
具体页面；这里的子命令结构与之一一对应，一个页面就是一条子命令。
"""

import argparse

from ..core import runtime_version

# 与图形界面侧边栏的三个分组一一对应。
GROUPS = {
    "remote": "远程攻击",
    "teacher": "教师端模拟",
    "local": "本机工具",
}

# 每个分组下的子命令，同样对应图形界面的页面。
COMMANDS = {
    "remote": {
        "message": "文本消息",
        "file": "文件传送",
        "device": "设备操作",
        "command": "远程命令",
        "shell": "反弹终端",
    },
    "teacher": {
        "appcmd": "应用命令",
        "students": "学生信息",
        "screen": "屏幕画面",
        "control": "远程接管",
        "chat": "聊天消息",
        "closewindow": "关闭窗口",
    },
    "local": {
        "info": "本机信息",
        "firewall": "防火墙",
    },
}

GROUP_NAMES = tuple(GROUPS)


def _base_defaults():
    """子命令共用的属性默认值。

    分发函数沿用扁平写法的字段名，两条解析路径因此能共用同一套执行代码。

    Returns:
        dict: 属性名到默认值的映射，``peer`` 每次新建列表。
    """
    return {
        "ip": None,
        "p": 4705,
        "msg": None,
        "msg_file": None,
        "file": None,
        "c": None,
        "l": 1,
        "t": 22,
        "e": None,
        "power_delay": 0,
        "power_text": "",
        "power_no_force": False,
        "run": None,
        "run_args": "",
        "run_show": 0,
        "url": None,
        "kill": None,
        "blackscreen": None,
        "unlock": False,
        "rename": None,
        "lock_screen": False,
        "unlock_screen": False,
        "screen_password": None,
        "exit_student": False,
        "close_apps": False,
        "shell": False,
        "shell_port": 0,
        "shell_ip": "",
        "mouse": False,
        "key": False,
        "view_stop": False,
        "control_stop": False,
        "kill_window": None,
        "probe": False,
        "view": None,
        "preview": None,
        "all_preview": None,
        "announce": None,
        "students": None,
        "chat": None,
        "control": False,
        "no_lock": False,
        "no_auto_unlock": False,
        "blackout_text": "",
        "lcmd": False,
        "report": 0,
        "channel": 1,
        "teacher_name": "1",
        "peer": [],
        "tcp_port": 4806,
        "output_dir": "",
        "file_ip": None,
        "file_timeout": 120,
        "firewall": None,
    }


def _add_target(parser, required=True):
    """添加目标地址参数。"""
    parser.add_argument(
        "-ip",
        required=required,
        type=str,
        help="目标地址：单个地址、末段范围（如 192.168.1.10-20）或 /24 网段",
    )


def _add_port(parser):
    """添加目标端口参数。"""
    parser.add_argument(
        "-p",
        "--port",
        dest="p",
        type=int,
        default=4705,
        help="目标 UDP 端口，默认 4705",
    )


def _add_loop(parser):
    """添加轮数与间隔参数。"""
    parser.add_argument("-l", dest="l", type=int, default=1, help="轮数，默认为 1")
    parser.add_argument(
        "-t", dest="t", type=int, default=22, help="轮之间的间隔秒数，默认 22"
    )


def _add_session(parser, *, peer=False, teacher_name=False):
    """添加教师端模拟共用的会话参数。"""
    parser.add_argument(
        "--channel",
        type=int,
        default=1,
        metavar="N",
        help="教师端模拟的会话频道，默认 1",
    )
    if teacher_name:
        parser.add_argument(
            "--teacher-name",
            type=str,
            default="1",
            metavar="NAME",
            help="学生端显示的教师名，默认 1",
        )
    if peer:
        parser.add_argument(
            "--peer",
            action="append",
            default=[],
            metavar="IP",
            help="宣告时额外定向单发的地址，可重复，用于组播与广播都到不了的网段",
        )


def build_group_parser():
    """创建分类子命令解析器。

    Returns:
        argparse.ArgumentParser: 形如 ``remote message -ip ...`` 的解析器。
    """
    parser = argparse.ArgumentParser(
        prog="JiYuAttackNext",
        description="极域课堂 UDP 报文测试工具：命令按图形界面的分组组织",
        epilog="分组：remote 远程攻击、teacher 教师端模拟、local 本机工具。"
        "每条子命令对应图形界面里的一个页面，例如 remote message 对应“文本消息”。",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=runtime_version(),
        help="显示版本号并退出",
    )
    groups = parser.add_subparsers(
        title="分组", dest="group", metavar="分组", required=True
    )

    remote = groups.add_parser("remote", help="远程攻击")
    remote_commands = remote.add_subparsers(
        title="子命令", dest="command", metavar="子命令", required=True
    )
    _build_remote(remote_commands)

    teacher = groups.add_parser("teacher", help="教师端模拟")
    teacher_commands = teacher.add_subparsers(
        title="子命令", dest="command", metavar="子命令", required=True
    )
    _build_teacher(teacher_commands)

    local = groups.add_parser("local", help="本机工具")
    local_commands = local.add_subparsers(
        title="子命令", dest="command", metavar="子命令", required=True
    )
    _build_local(local_commands)

    return parser


def _build_remote(commands):
    """注册远程攻击分组下的子命令。"""
    message = commands.add_parser("message", help="文本消息：发送自动分条的文本")
    message.set_defaults(**_base_defaults())
    _add_target(message)
    _add_port(message)
    message_options = message.add_mutually_exclusive_group(required=True)
    message_options.add_argument(
        "-msg", type=str, help="消息正文，支持多行；超长内容自动分条"
    )
    message_options.add_argument(
        "--msg-file",
        type=str,
        metavar="PATH",
        help="从 UTF-8 文件读取消息；使用 - 从标准输入读取",
    )
    _add_loop(message)

    file_command = commands.add_parser(
        "file", help="文件传送：把文件或文件夹送到目标桌面"
    )
    file_command.set_defaults(**_base_defaults())
    _add_target(file_command)
    _add_port(file_command)
    file_command.add_argument(
        "--file",
        type=str,
        nargs="+",
        required=True,
        metavar="PATH",
        help="一个或多个文件、文件夹，文件夹按原结构递归",
    )
    file_command.add_argument(
        "--file-ip", type=str, metavar="IP", help="发送端 IP，默认自动检测"
    )
    file_command.add_argument(
        "--file-timeout",
        type=int,
        default=120,
        metavar="SECONDS",
        help="等待目标下载文件的秒数，默认 120",
    )

    device = commands.add_parser("device", help="设备操作：重启、关机、注销")
    device.set_defaults(**_base_defaults())
    _add_target(device)
    _add_port(device)
    device_actions = device.add_mutually_exclusive_group(required=True)
    device_actions.add_argument(
        "--reboot",
        dest="e",
        action="store_const",
        const="r",
        help="重启目标电脑",
    )
    device_actions.add_argument(
        "--shutdown",
        dest="e",
        action="store_const",
        const="s",
        help="关闭目标电脑",
    )
    device_actions.add_argument(
        "--logoff",
        dest="e",
        action="store_const",
        const="l",
        help="注销当前用户（走远程命令 shutdown /l）",
    )
    device.add_argument(
        "--power-delay",
        type=int,
        default=0,
        metavar="SECONDS",
        help="倒计时秒数，默认 0（立即执行）；注销不支持",
    )
    device.add_argument(
        "--power-text",
        type=str,
        default="",
        metavar="TEXT",
        help="显示在学生机上的提示文字；注销不支持",
    )
    device.add_argument(
        "--power-no-force",
        action="store_true",
        help="等程序自行退出，不强制关闭；注销不支持",
    )

    command = commands.add_parser("command", help="远程命令：执行一条命令")
    command.set_defaults(**_base_defaults())
    _add_target(command)
    _add_port(command)
    command.add_argument(
        "-c", required=True, type=str, help='要执行的命令，例如 "cmd.exe /c ipconfig"'
    )
    _add_loop(command)

    shell = commands.add_parser("shell", help="反弹终端：本机监听并让目标连回来")
    shell.set_defaults(**_base_defaults())
    _add_target(shell)
    _add_port(shell)
    shell.set_defaults(shell=True)
    shell.add_argument(
        "--shell-port",
        type=int,
        default=0,
        metavar="PORT",
        help="本机监听端口，默认 0 表示随机",
    )
    shell.add_argument(
        "--shell-ip",
        type=str,
        default="",
        metavar="IP",
        help="写进目标连接命令的本机地址，默认自动探测",
    )


def _build_teacher(commands):
    """注册教师端模拟分组下的子命令。"""
    appcmd = commands.add_parser("appcmd", help="应用命令：运行程序、锁屏等")
    appcmd.set_defaults(**_base_defaults())
    _add_target(appcmd)
    _add_port(appcmd)
    _add_session(appcmd)
    actions = appcmd.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        "--run", metavar="PATH", help="在目标电脑上运行指定程序（应用命令 0x0F）"
    )
    actions.add_argument(
        "--url", metavar="URL", help="在目标电脑上打开网址或文件（应用命令 0x18）"
    )
    actions.add_argument(
        "--kill",
        metavar="PID|NAME",
        help="结束进程：填进程号直接下发，填进程名则先发现学生再按名匹配",
    )
    actions.add_argument(
        "--blackscreen",
        nargs="?",
        const=10,
        type=int,
        metavar="SECONDS",
        help="黑屏并显示 SECONDS 秒后自动解除，默认 10 秒；0 表示不自动解除",
    )
    actions.add_argument("--unlock", action="store_true", help="解除黑屏与键鼠锁")
    actions.add_argument(
        "--rename",
        metavar="NAME",
        help="修改目标电脑上显示的计算机名（应用命令 0x05）",
    )
    actions.add_argument(
        "--lock-screen", action="store_true", help="锁定目标电脑的屏幕（0x0A）"
    )
    actions.add_argument(
        "--unlock-screen",
        action="store_true",
        help="解除目标电脑的锁屏（0x0A，状态 0）",
    )
    actions.add_argument(
        "--screen-password",
        metavar="PASSWORD",
        help="设置锁屏解锁密码（0x0B），传空字符串表示清除",
    )
    actions.add_argument(
        "--exit-student", action="store_true", help="让目标电脑退出学生端"
    )
    actions.add_argument(
        "--close-apps", action="store_true", help="关闭目标电脑上的所有程序"
    )
    appcmd.add_argument(
        "--run-args", type=str, default="", metavar="TEXT", help="--run 的启动参数"
    )
    appcmd.add_argument(
        "--run-show",
        type=int,
        default=0,
        choices=[0, 1, 2],
        metavar="MODE",
        help="--run 的窗口状态：0 正常、1 最小化、2 最大化",
    )
    appcmd.add_argument(
        "--no-lock", action="store_true", help="--blackscreen 只黑屏，不锁键鼠"
    )
    appcmd.add_argument(
        "--no-auto-unlock",
        action="store_true",
        help="--blackscreen 结束后不自动解除，由 --unlock 或学生端计时结束",
    )
    appcmd.add_argument(
        "--blackout-text",
        type=str,
        default="",
        metavar="TEXT",
        help="黑屏中间显示的提示",
    )
    appcmd.add_argument(
        "--lcmd",
        action="store_true",
        help="改走不带事务应答的轻量通道 LCMD",
    )

    students = commands.add_parser(
        "students", help="学生信息：发现学生、拉缩略图、看进程与窗口"
    )
    students.set_defaults(**_base_defaults())
    _add_target(students, required=False)
    _add_port(students)
    _add_session(students, peer=True, teacher_name=True)
    students.set_defaults(students=8)
    students.add_argument(
        "--seconds",
        dest="students",
        nargs="?",
        const=8,
        type=int,
        metavar="SECONDS",
        help="宣告并监听的秒数，默认 8 秒",
    )
    students.add_argument(
        "--all-preview",
        nargs="?",
        const=8,
        type=int,
        metavar="SECONDS",
        help="拉取全员缩略图，默认监听 8 秒",
    )
    students.add_argument(
        "--kill",
        metavar="PID|NAME",
        help="结束进程：填进程号直接下发，填进程名则按名匹配",
    )
    students.add_argument(
        "--report",
        type=int,
        default=0,
        choices=[0, 1, 2],
        metavar="KIND",
        help="请求的上报类型：0 全部、1 窗口、2 进程，默认 0",
    )

    screen = commands.add_parser("screen", help="屏幕画面：缩略图、观看、端口探测")
    screen.set_defaults(**_base_defaults())
    _add_target(screen)
    _add_session(screen)
    screen.add_argument(
        "--tcp-port",
        type=int,
        default=4806,
        metavar="PORT",
        help="学生端屏幕传输的 TCP 端口，默认 4806",
    )
    screen.add_argument(
        "--output-dir",
        type=str,
        default="",
        metavar="DIR",
        help="保存图片的目录，默认当前目录下的 preview",
    )
    screen_actions = screen.add_mutually_exclusive_group(required=True)
    screen_actions.add_argument(
        "--preview",
        nargs="?",
        const=8,
        type=int,
        metavar="SECONDS",
        help="拉取并修正缩略图，默认监听 8 秒",
    )
    screen_actions.add_argument(
        "--view",
        nargs="?",
        const=15,
        type=int,
        metavar="SECONDS",
        help="观看实时画面，默认 15 秒",
    )
    screen_actions.add_argument(
        "--probe",
        action="store_true",
        help="只探测屏幕传输端口，不建立观看会话",
    )
    screen_actions.add_argument(
        "--stop",
        dest="view_stop",
        action="store_true",
        help="在图形界面里结束观看：命令行无法保存会话",
    )
    screen.add_argument(
        "--control",
        action="store_true",
        help="配合 --view 请求接管键鼠；命令行不转发输入",
    )

    control = commands.add_parser("control", help="远程接管：打开图形界面的接管窗口")
    control.set_defaults(**_base_defaults())
    # 接管要持续转发键鼠事件，命令行没有输入循环，解析后直接进图形界面。
    control.set_defaults(control=True)
    _add_target(control)
    _add_session(control)

    chat = commands.add_parser("chat", help="聊天消息：发一条会话聊天")
    chat.set_defaults(**_base_defaults())
    _add_target(chat)
    _add_port(chat)
    _add_session(chat, teacher_name=True)
    chat.add_argument("chat", metavar="TEXT", help="聊天内容")

    closewindow = commands.add_parser(
        "closewindow", help="关闭窗口：按句柄或标题关掉窗口"
    )
    closewindow.set_defaults(**_base_defaults())
    _add_target(closewindow)
    _add_port(closewindow)
    _add_session(closewindow, teacher_name=True)
    # 位置参数直接叫 kill_window，分发函数读到的就是扁平写法的字段名。
    closewindow.add_argument(
        "kill_window",
        metavar="HWND|TITLE",
        help="窗口句柄直接下发；填标题关键字则先拉窗口列表再匹配",
    )


def _build_local(commands):
    """注册本机工具分组下的子命令。"""
    info = commands.add_parser("info", help="本机信息：本机地址与学生端端口")
    info.set_defaults(**_base_defaults())
    info.set_defaults(e="g")

    firewall = commands.add_parser("firewall", help="防火墙：阻断或恢复学生端连接")
    firewall.set_defaults(**_base_defaults())
    firewall.add_argument(
        "firewall",
        choices=["block", "allow"],
        metavar="ACTION",
        help="block 阻断学生端、allow 恢复允许",
    )


def build_flat_parser():
    """创建扁平写法解析器。

    兼容来源项目与本程序早期的写法（``-ip ... -msg ...``），保留全部旧参数。

    Returns:
        argparse.ArgumentParser: 扁平参数解析器。
    """
    parser = argparse.ArgumentParser(
        description="极域课堂 UDP 报文测试工具（学生端控制与教师端模拟）"
    )
    # 分类写法才有的字段在这里补成默认值，分发函数因此能共用同一套属性名。
    parser.set_defaults(**_base_defaults())
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=runtime_version(),
        help="显示版本号并退出",
    )
    parser.add_argument("-ip", type=str, help="ip 指定目标IP地址")
    parser.add_argument(
        "-p", type=int, default=4705, help="port 指定监听端口，默认端口为4705"
    )
    message_options = parser.add_mutually_exclusive_group()
    message_options.add_argument(
        "-msg", type=str, help="发送文本消息，支持多行；超长内容自动分条"
    )
    message_options.add_argument(
        "--msg-file",
        type=str,
        metavar="PATH",
        help="从 UTF-8 文件读取消息；使用 - 从标准输入读取",
    )
    message_options.add_argument(
        "--file",
        type=str,
        nargs="+",
        metavar="PATH",
        help="传送一个或多个文件、文件夹到目标电脑桌面，文件夹按原结构递归",
    )
    parser.add_argument(
        "-c", type=str, help='command命令 eg: -c   "cmd.exe /c ipconfig"'
    )
    parser.add_argument("-l", type=int, default=1, help="循环次数，默认为1")
    parser.add_argument("-t", type=int, default=22, help="循环时间间隔，默认是22秒")
    parser.add_argument(
        "--file-ip", type=str, metavar="IP", help="文件传送时发送端 IP，默认自动检测"
    )
    parser.add_argument(
        "--file-timeout",
        type=int,
        default=120,
        metavar="SECONDS",
        help="等待目标下载文件的秒数，默认 120",
    )
    parser.add_argument(
        "-e",
        type=str,
        choices=["r", "s", "l", "g", "break", "continue", "nc"],
        help=(
            "额外选项：r 重启、s 关机、l 注销、g 本机信息、"
            "break 阻断学生端、continue 恢复允许、nc 反弹终端"
        ),
    )
    parser.add_argument(
        "--power-delay",
        type=int,
        default=0,
        metavar="SECONDS",
        help="配合 -e r/-e s 的倒计时秒数，默认 0（立即执行）",
    )
    parser.add_argument(
        "--power-text",
        type=str,
        default="",
        metavar="TEXT",
        help="配合 -e r/-e s 显示在学生机上的提示文字",
    )
    parser.add_argument(
        "--power-no-force",
        action="store_true",
        help="配合 -e r/-e s 时等待程序自行退出，不强制关闭",
    )
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--run",
        metavar="PATH",
        help="在目标电脑上运行指定程序（应用命令 0x0F）",
    )
    action_group.add_argument(
        "--url", metavar="URL", help="在目标电脑上打开网址（应用命令 0x18）"
    )
    action_group.add_argument(
        "--mouse",
        action="store_true",
        help="打开图形界面的远程接管页：鼠标输入只能在 GUI 里转发",
    )
    action_group.add_argument(
        "--key",
        action="store_true",
        help="打开图形界面的远程接管页：键盘输入只能在 GUI 里转发",
    )
    action_group.add_argument(
        "--view-stop",
        action="store_true",
        help="打开图形界面的屏幕画面页：观看会话在窗口里关闭",
    )
    action_group.add_argument(
        "--control-stop",
        action="store_true",
        help="打开图形界面的远程接管页：解除接管在窗口里操作",
    )
    action_group.add_argument(
        "--shell",
        action="store_true",
        help="启动反弹终端：本机监听并通过远程命令让目标连回来交互",
    )
    action_group.add_argument(
        "--kill",
        metavar="PID|NAME",
        help="结束目标进程，填进程号直接下发，填进程名则先发现学生再按名匹配",
    )
    action_group.add_argument(
        "--blackscreen",
        nargs="?",
        const=10,
        type=int,
        metavar="SECONDS",
        help="黑屏并显示 SECONDS 秒后自动解除，默认 10 秒；0 表示不自动解除",
    )
    action_group.add_argument(
        "--unlock", action="store_true", help="解除目标电脑的黑屏与键鼠锁"
    )
    action_group.add_argument(
        "--exit-student", action="store_true", help="让目标电脑退出学生端"
    )
    action_group.add_argument(
        "--close-apps", action="store_true", help="关闭目标电脑上的所有程序"
    )
    action_group.add_argument(
        "--rename",
        metavar="NAME",
        help="修改目标电脑上显示的计算机名（应用命令 0x05）",
    )
    action_group.add_argument(
        "--lock-screen", action="store_true", help="锁定目标电脑的屏幕（应用命令 0x0A）"
    )
    action_group.add_argument(
        "--unlock-screen",
        action="store_true",
        help="解除目标电脑的锁屏（应用命令 0x0A，状态 0）",
    )
    action_group.add_argument(
        "--all-preview",
        nargs="?",
        const=8,
        type=int,
        metavar="SECONDS",
        help="对发现到的全部学生拉取缩略图，默认监听 8 秒",
    )
    action_group.add_argument(
        "--announce",
        nargs="?",
        const=10,
        type=int,
        metavar="SECONDS",
        help="以教师端模拟身份发送宣告并监听 SECONDS 秒，默认 10 秒",
    )
    action_group.add_argument(
        "--students",
        nargs="?",
        const=8,
        type=int,
        metavar="SECONDS",
        help="发现学生机并拉取信息、进程与窗口，默认监听 8 秒",
    )
    action_group.add_argument(
        "--preview",
        nargs="?",
        const=8,
        type=int,
        metavar="SECONDS",
        help="拉取并修正目标电脑的屏幕缩略图，默认监听 8 秒",
    )
    action_group.add_argument(
        "--view",
        nargs="?",
        const=15,
        type=int,
        metavar="SECONDS",
        help="观看目标电脑的实时画面，默认 15 秒",
    )
    action_group.add_argument(
        "--chat",
        type=str,
        metavar="TEXT",
        help="向已登录学生发送会话聊天消息（MESS 0x800）",
    )
    action_group.add_argument(
        "--kill-window",
        metavar="HWND|TITLE",
        help="关闭目标窗口：填句柄直接下发，填标题关键字则先拉取窗口列表再匹配",
    )
    action_group.add_argument(
        "--probe",
        action="store_true",
        help="探测目标电脑的屏幕传输端口是否在监听，不建立观看会话",
    )
    parser.add_argument(
        "--run-args", type=str, default="", metavar="TEXT", help="--run 的启动参数"
    )
    parser.add_argument(
        "--run-show",
        type=int,
        default=0,
        choices=[0, 1, 2],
        metavar="MODE",
        help="--run 的窗口状态：0 正常、1 最小化、2 最大化",
    )
    parser.add_argument(
        "--shell-port",
        type=int,
        default=0,
        metavar="PORT",
        help="反弹终端的本机监听端口，默认 0 表示随机",
    )
    parser.add_argument(
        "--shell-ip",
        type=str,
        default="",
        metavar="IP",
        help="写进目标连接命令的本机地址，默认自动探测",
    )
    parser.add_argument(
        "--control",
        action="store_true",
        help="配合 --view 请求接管键鼠；单独使用会打开图形界面的远程接管页",
    )
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help="--blackscreen 只黑屏，不锁定键盘与鼠标",
    )
    parser.add_argument(
        "--no-auto-unlock",
        action="store_true",
        help="--blackscreen 结束后不自动解除，由 --unlock 或学生端自己计时结束",
    )
    parser.add_argument(
        "--blackout-text",
        type=str,
        default="",
        metavar="TEXT",
        help="黑屏中间显示的提示",
    )
    parser.add_argument(
        "--screen-password",
        type=str,
        default=None,
        metavar="PASSWORD",
        help="设置目标电脑的锁屏解锁密码（应用命令 0x0B），传空字符串表示清除",
    )
    parser.add_argument(
        "--lcmd",
        action="store_true",
        help="应用命令改走不带事务应答的轻量通道 LCMD",
    )
    parser.add_argument(
        "--report",
        type=int,
        default=0,
        choices=[0, 1, 2],
        metavar="KIND",
        help="--students 请求的上报类型：0 全部、1 窗口、2 进程，默认 0",
    )
    parser.add_argument(
        "--channel",
        type=int,
        default=1,
        metavar="N",
        help="教师端模拟的会话频道，默认 1",
    )
    parser.add_argument(
        "--teacher-name",
        type=str,
        default="1",
        metavar="NAME",
        help="学生端显示的教师名",
    )
    parser.add_argument(
        "--peer",
        action="append",
        default=[],
        metavar="IP",
        help="宣告时额外定向单发的地址，可重复，用于组播与广播都到不了的网段",
    )
    parser.add_argument(
        "--tcp-port",
        type=int,
        default=4806,
        metavar="PORT",
        help="学生端屏幕传输的 TCP 端口，默认 4806",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        metavar="DIR",
        help="--preview 与 --view 保存图片的目录，默认当前目录下的 preview",
    )
    return parser
