"""Fluent 工作页面集合。"""

from .message import MessagePage
from .command import CommandPage
from .device import DevicePage
from .file import FilePage
from .alias import AliasPage
from .local import LocalPage
from .firewall import FirewallPage
from .log import LogPage
from .settings import SettingsPage
from .about import AboutInfoCard, AboutDetailCard, AboutPage

__all__ = [
    "AboutDetailCard",
    "AboutInfoCard",
    "AboutPage",
    "AliasPage",
    "CommandPage",
    "DevicePage",
    "FilePage",
    "FirewallPage",
    "LocalPage",
    "LogPage",
    "MessagePage",
    "SettingsPage",
]
