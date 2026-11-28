"""窗口路由、显示名称与界面调度常量。"""

from PySide6.QtWidgets import QSystemTrayIcon
from qfluentwidgets import FluentIcon as FIF

APP_NAME = "NeoJiYuTrainer"

HOME_LINKS = {
    "repository": "https://github.com/JasonFang0109c/NeoJiYuTrainer",
    "document": "https://github.com/JasonFang0109c/NeoJiYuTrainer/blob/main/docs/usage/GUI.md",
    "feedback": "https://github.com/JasonFang0109c/NeoJiYuTrainer/issues",
}

CATEGORIES = {
    "message": "文本消息",
    "command": "远程命令",
    "device": "设备操作",
    "file": "文件传送",
    "local": "本机信息",
    "firewall": "防火墙",
    "studentproc": "课堂助手",
}

STUDENT_POLL_INTERVAL = 2000

# 标题栏三个窗口按钮高 32、标题栏高 48，补齐上下的等分留白才能居中。
CAPTION_BUTTON_MARGIN = 8

# 标题栏左侧文字留白。
TITLE_BAR_MARGIN = 6
# 组件库把标题栏固定在左侧 46 像素处，项目不改这个位置。
TITLE_BAR_OFFSET = 46
# 收起后的图标栏宽度，按钮把它整个占满。
SIDEBAR_COLLAPSED_WIDTH = 48
# 返回与菜单按钮各占 40×36；首页隐藏返回按钮时仍保留首个槽位。
SIDEBAR_BUTTON_WIDTH = 40
SIDEBAR_BUTTON_HEIGHT = 36
# 首个按钮的左上角，对应 WinUI 面板头部里工具按钮的内缩。
SIDEBAR_BUTTON_INSET = 5
SIDEBAR_BUTTON_TOP = 6
# 侧边栏顶部留白：首项要比内容区顶边（48）低 5 像素，按钮占 36 与 11 的间隙，
# 面板内容又从第 6 像素开始，所以顶部留 47（WinUI 的 PaneContentGrid 3 像
# 素加条目 2 像素）。
SIDEBAR_HEADER_INSET = 47

LOCAL_IP_PLACEHOLDERS = ("未查询", "未获取")

TRAY_MESSAGE_ICONS = {
    "错误": QSystemTrayIcon.MessageIcon.Critical,
    "警告": QSystemTrayIcon.MessageIcon.Warning,
}

# 侧边栏只保留一级入口；组内页面在容器页里用顶部导航栏切换，不再展开子项。
TAB_GROUPS = (
    (
        "classroomhub",
        FIF.EDUCATION,
        "课堂助手",
        (
            ("studentproc", FIF.POWER_BUTTON, "启停学生端"),
            ("classroom", FIF.SCROLL, "课堂助手"),
        ),
    ),
    (
        "remote",
        FIF.GLOBE,
        "远程攻击",
        (
            ("message", FIF.MESSAGE, "文本消息"),
            ("file", FIF.SEND, "文件传送"),
            ("device", FIF.POWER_BUTTON, "设备操作"),
            ("command", FIF.COMMAND_PROMPT, "远程命令"),
            ("shell", FIF.SPEED_HIGH, "反弹终端"),
        ),
    ),
    (
        "localtools",
        FIF.DEVELOPER_TOOLS,
        "本机工具",
        (
            ("local", FIF.IOT, "本机信息"),
            ("firewall", FIF.CERTIFICATE, "防火墙"),
        ),
    ),
)

NAVIGATION_ITEMS = (
    ("classroomhub", FIF.EDUCATION, "课堂助手"),
    ("remote", FIF.GLOBE, "远程攻击"),
    ("aliases", FIF.QUICK_NOTE, "设备备注"),
    ("localtools", FIF.DEVELOPER_TOOLS, "本机工具"),
)

# 子页面到容器页的映射，供 show_page 与当前页面识别使用。
PAGE_TABS = {
    child: host
    for host, _icon, _title, children in TAB_GROUPS
    for child, _, _ in children
}
