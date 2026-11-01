"""协议、传输、防火墙与本机信息核心。"""

from . import constants, firewall, local_info, protocol, transport
from .constants import (
    COMMAND_MAX_BYTES, COMMAND_OFFSET, LOGOFF_COMMAND, MESSAGE_MAX_BYTES,
    MESSAGE_OFFSET, __version__, basicCMD, store,
)
from .firewall import (
    FIREWALL_HELPER_ARGUMENT, FIREWALL_RESULT_ARGUMENT, _decode_windows_output,
    _firewall_result, _is_admin, _run_elevated_process, _run_firewall_elevated,
    _windows_command, request_firewall_rule, run_firewall_helper,
    set_firewall_rule,
)
from .local_info import (
    _is_usable_local_address, detect_local_ip, local_ip_and_ports,
    validate_listen_ip,
)
from .protocol import (
    SendOptions, format_b4_send, get_ip, pkg_sendlist, prepare_packets,
    read_message, split_message, validate_options,
)
from .transport import (
    FileTransferServer, _FileTransferRequestHandler, _bootstrap_desktop_lines,
    _validate_transfer_request, build_bootstrap_script,
    build_items_bootstrap_script, build_transfer_command, collect_transfer_items,
    execute_send, format_size, normalize_transfer_items, send, transfer_file,
    validate_file_transfer,
)

__all__ = [
    "COMMAND_MAX_BYTES", "COMMAND_OFFSET", "LOGOFF_COMMAND", "MESSAGE_MAX_BYTES",
    "MESSAGE_OFFSET", "__version__", "basicCMD", "store", "constants", "protocol",
    "transport", "local_info", "firewall", "SendOptions", "format_b4_send", "get_ip",
    "pkg_sendlist", "prepare_packets", "read_message", "split_message",
    "validate_options", "FileTransferServer", "build_bootstrap_script",
    "build_items_bootstrap_script", "build_transfer_command",
    "collect_transfer_items", "execute_send", "format_size",
    "normalize_transfer_items", "send", "transfer_file", "validate_file_transfer",
    "detect_local_ip", "local_ip_and_ports", "validate_listen_ip",
    "request_firewall_rule", "run_firewall_helper", "set_firewall_rule",
    "FIREWALL_HELPER_ARGUMENT", "FIREWALL_RESULT_ARGUMENT",
]
