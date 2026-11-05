"""Fluent 工作页面集合。"""

from .about import AboutDetailCard, AboutInfoCard, AboutPage
from .alias import AliasPage
from .appcmd import AppCommandPage
from .command import CommandPage
from .device import DevicePage
from .file import FilePage
from .firewall import FirewallPage
from .home import HomePage
from .local import LocalPage
from .log import LogPage
from .message import MessagePage
from .settings import SettingsPage
from .students import StudentsPage

__all__ = [
    "AboutDetailCard",
    "AboutInfoCard",
    "AboutPage",
    "AliasPage",
    "AppCommandPage",
    "CommandPage",
    "DevicePage",
    "FilePage",
    "FirewallPage",
    "HomePage",
    "LocalPage",
    "LogPage",
    "MessagePage",
    "SettingsPage",
    "StudentsPage",
]
