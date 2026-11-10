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

NAVIGATION_MAX_HEIGHT = 680

LOCAL_IP_PLACEHOLDERS = ("未查询", "未获取")

TRAY_MESSAGE_ICONS = {
    "错误": QSystemTrayIcon.MessageIcon.Critical,
    "警告": QSystemTrayIcon.MessageIcon.Warning,
}

NAVIGATION_ALIASES_AFTER = "group_remote"

NAVIGATION_GROUPS = (
    (
        "group_restriction",
        FIF.SPEED_OFF,
        "解除限制",
        (("studentproc", FIF.POWER_BUTTON, "启停学生端"),),
    ),
    (
        "group_remote",
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
        "group_local",
        FIF.DEVELOPER_TOOLS,
        "本机工具",
        (
            ("local", FIF.IOT, "本机信息"),
            ("firewall", FIF.CERTIFICATE, "防火墙"),
        ),
    ),
)
