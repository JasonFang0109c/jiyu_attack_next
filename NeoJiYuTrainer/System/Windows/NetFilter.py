"""极域网络过滤驱动（TDNetFilter）的卸载接口。

上游 JiYuTrainer 在退出前会停止并删除极域安装的 TDNetFilter 服务，
否则它会继续拦截网络访问。这里用服务控制管理器直接操作，错误码与
提示文案与上游保持一致，界面层负责把返回的消息展示给用户。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from NeoJiYuTrainer.System.Windows.DriverLoader import force_delete_service_key

SERVICE_NAME = "TDNetFilter"
SC_MANAGER_CONNECT = 0x0001
SERVICE_QUERY_STATUS = 0x0004
SERVICE_STOP = 0x0020
SERVICE_CHANGE_CONFIG = 0x0002
DELETE = 0x00010000
ERROR_SERVICE_DOES_NOT_EXIST = 1060
ERROR_SERVICE_MARKED_FOR_DELETE = 1072
ERROR_SERVICE_ALREADY_RUNNING = 1056
SERVICE_CONTROL_STOP = 0x00000001

advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
advapi32.OpenSCManagerW.restype = wintypes.HANDLE
advapi32.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
advapi32.OpenServiceW.restype = wintypes.HANDLE
advapi32.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
advapi32.ControlService.restype = wintypes.BOOL
advapi32.ControlService.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.c_void_p,
]
advapi32.DeleteService.restype = wintypes.BOOL
advapi32.DeleteService.argtypes = [wintypes.HANDLE]
advapi32.CloseServiceHandle.restype = wintypes.BOOL
advapi32.CloseServiceHandle.argtypes = [wintypes.HANDLE]


class NetFilterError(OSError):
    """卸载网络过滤驱动失败。"""


def _force_delete_key() -> None:
    """删除被标记为待删除的服务注册表键。"""
    force_delete_service_key(SERVICE_NAME)


def uninstall() -> str:
    """停止并删除 TDNetFilter 服务，返回给用户看的结果文案。"""
    manager = advapi32.OpenSCManagerW(None, None, SC_MANAGER_CONNECT)
    if not manager:
        raise NetFilterError(
            "卸载驱动错误，打开驱动管理错误："
            f"{ctypes.get_last_error()}\n请尝试以管理员身份运行软件。"
        )
    try:
        service = advapi32.OpenServiceW(
            manager, SERVICE_NAME, SERVICE_QUERY_STATUS | SERVICE_STOP | DELETE
        )
        if not service:
            code = ctypes.get_last_error()
            if code == ERROR_SERVICE_DOES_NOT_EXIST:
                return "没有在这台计算机上找到驱动，可能是驱动已经被卸载了"
            raise NetFilterError(f"卸载驱动错误，打开驱动服务错误：{code}")
        try:
            status = (ctypes.c_byte * 64)()
            if not advapi32.ControlService(service, SERVICE_CONTROL_STOP, status):
                code = ctypes.get_last_error()
                if code not in (
                    ERROR_SERVICE_DOES_NOT_EXIST,
                    ERROR_SERVICE_ALREADY_RUNNING,
                ):
                    raise NetFilterError(f"卸载驱动错误，停止驱动失败：{code}")
            if not advapi32.DeleteService(service):
                code = ctypes.get_last_error()
                if code == ERROR_SERVICE_MARKED_FOR_DELETE:
                    _force_delete_key()
                    return "驱动已卸载并删除，请不要重复操作"
                if code != ERROR_SERVICE_DOES_NOT_EXIST:
                    raise NetFilterError(f"卸载驱动错误，删除驱动失败：{code}")
            _force_delete_key()
            return "驱动已卸载并删除，请不要重复操作"
        finally:
            advapi32.CloseServiceHandle(service)
    finally:
        advapi32.CloseServiceHandle(manager)
