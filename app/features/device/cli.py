"""设备操作的参数注册与报文适配。"""

from app.features.send.cli import add_port, add_target
from app.packets.codec import pkg_sendlist
from app.packets.constants import BLUE_SCREEN_COMMAND, LOGOFF_COMMAND, basicCMD


def register(commands, defaults):
    """注册功能子命令并沿用统一参数默认值。"""
    device = commands.add_parser("device", help="设备操作：重启、关机、注销、蓝屏")
    device.set_defaults(**dict(defaults))
    add_target(device)
    add_port(device)
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
    device_actions.add_argument(
        "--bluescreen",
        dest="e",
        action="store_const",
        const="b",
        help="触发蓝屏（走远程命令结束 wininit.exe）",
    )


def create_device_packets(arguments):
    """为重启、关机、注销或蓝屏操作构造报文。"""
    send_list = []
    # 重启与关机用来源项目的固定报文；注销与蓝屏没有独立报文，
    # 都走远程命令通道，命令文本在发送层统一组装。
    if arguments.e in {"r", "s"}:
        send_list.append(basicCMD["-" + arguments.e])
    elif arguments.e == "l":
        send_list.append(pkg_sendlist("-c", LOGOFF_COMMAND))
    elif arguments.e == "b":
        send_list.append(pkg_sendlist("-c", BLUE_SCREEN_COMMAND))
    return send_list
