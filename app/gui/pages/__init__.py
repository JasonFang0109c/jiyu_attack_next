"""Fluent 工作页面集合。"""

from .about import AboutDetailCard, AboutInfoCard, AboutPage
from .alias import AliasPage
from .appcmd import AppCommandPage
from .chat import ChatPage
from .closewindow import CloseWindowPage
from .command import CommandPage
from .control import ControlPage
from .device import DevicePage
from .file import FilePage
from .firewall import FirewallPage
from .home import HomePage
from .local import LocalPage
from .log import LogPage
from .message import MessagePage
from .screen import ScreenPage
from .settings import SettingsPage
from .shell import ShellPage
from .students import StudentsPage

__all__ = [
    "AboutDetailCard",
    "AboutInfoCard",
    "AboutPage",
    "AliasPage",
    "AppCommandPage",
    "ChatPage",
    "CloseWindowPage",
    "CommandPage",
    "ControlPage",
    "DevicePage",
    "FilePage",
    "FirewallPage",
    "HomePage",
    "LocalPage",
    "LogPage",
    "MessagePage",
    "ScreenPage",
    "SettingsPage",
    "ShellPage",
    "StudentsPage",
]
