"""窗口路由、显示名称与界面调度常量。"""

from PySide6.QtWidgets import QSystemTrayIcon
from qfluentwidgets import FluentIcon as FIF

APP_NAME = "JiYu Attack Next"

HOME_LINKS = {
    "repository": "https://github.com/JasonFang0109c/jiyu_attack_next",
    "document": "https://github.com/JasonFang0109c/jiyu_attack_next/blob/main/docs/usage/GUI.md",
    "feedback": "https://github.com/JasonFang0109c/jiyu_attack_next/issues",
}

CATEGORIES = {
    "message": "文本消息",
    "command": "远程命令",
    "device": "设备操作",
    "file": "文件传送",
    "local": "本机信息",
    "firewall": "防火墙",
    "studentproc": "解除限制",
}

STUDENT_POLL_INTERVAL = 2000

# 标题栏三个窗口按钮高 32、标题栏高 48，补齐上下的等分留白才能居中。
CAPTION_BUTTON_MARGIN = 8

# 标题栏左缘留白；返回按钮占用菜单按钮左侧时，图标与标题整体右移一个按钮宽。
TITLE_BAR_MARGIN = 6
TITLE_BAR_SHIFTED_MARGIN = 46

LOCAL_IP_PLACEHOLDERS = ("未查询", "未获取")

TRAY_MESSAGE_ICONS = {
    "错误": QSystemTrayIcon.MessageIcon.Critical,
    "警告": QSystemTrayIcon.MessageIcon.Warning,
}

# 侧边栏只保留一级入口；组内页面在容器页里用顶部导航栏切换，不再展开子项。
TAB_GROUPS = (
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
    ("studentproc", FIF.POWER_BUTTON, "启停学生端"),
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
