"""Fluent 工作页面集合。"""

from .about import AboutDetailCard, AboutInfoCard, AboutPage
from .alias import AliasPage
from .command import CommandPage
from .device import DevicePage
from .file import FilePage
from .firewall import FirewallPage
from .local import LocalPage
from .log import LogPage
from .message import MessagePage
from .settings import SettingsPage

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
