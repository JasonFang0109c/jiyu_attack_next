"""settings.json 的读写：按 core 与 gui 两组存放界面与业务配置。

配置文件使用 JSON with comments，允许手写注释；程序保存时会重写整个文件，
因此手写注释只在未被保存覆盖前有效。键路径用 ``/`` 分隔，例如
``gui/window/close_behavior``。
"""

from pathlib import Path

from ..core import config

STATUS_NO_ERROR = 0
STATUS_ACCESS_ERROR = 1
STATUS_FORMAT_ERROR = 2

# 同一个配置文件的多个实例共享一份内存数据：主窗口与设备备注各自持有
# SettingsStore，各写各的会把彼此刚写入的分组整体覆盖掉。
_SHARED_DATA = {}

SETTINGS_COMMENTS = {
    "core/device_aliases": (
        "设备备注：备注名到 IPv4 地址的映射，地址支持单地址、末段范围与 /24 网段",
    ),
    "gui/window/close_behavior": ("关闭窗口行为：tray 保留在系统托盘，quit 直接退出",),
    "gui/window/first_close_prompt_shown": (
        "是否已经询问过首次关闭行为，true 之后不再提示",
    ),
    "gui/window/geometry": (
        "主窗口上次退出时的位置与大小（Qt 序列化结果转 base64），手改会导致恢复失败",
    ),
    "gui/window/material": ("窗口材质：mica 云母、acrylic 亚克力实时模糊、solid 纯色",),
    "gui/window/mica_enabled": (
        "旧版背景模糊开关，仅在没有 material 时用于换算材质，可删",
    ),
}


class SettingsStore:
    """把 JSON 配置读进内存，按键路径读取，保存时整体重写文件。

    Attributes:
        message: 最近一次读写失败的原因，成功时为空字符串。
    """

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.message = ""
        self._status = STATUS_NO_ERROR
        self._data = {}
        self.exists = False
        self.load()

    def _shared(self):
        """返回该配置文件在所有实例间共享的数据字典。"""
        return _SHARED_DATA.setdefault(str(self.path), self._data)

    def file_name(self):
        """返回配置文件路径，供日志说明写入位置。"""
        return str(self.path)

    def status(self):
        """返回最近一次读写的状态码，``STATUS_NO_ERROR`` 表示成功。"""
        return self._status

    def load(self):
        """读取配置文件；文件缺失时按空配置处理，格式错误时只记录原因。"""
        self.exists = self.path.exists()
        self.message = ""
        self._status = STATUS_NO_ERROR
        shared = self._shared()
        shared.clear()
        self._data = shared
        try:
            shared.update(config.read(self.path))
        except ValueError as error:
            self._status = STATUS_FORMAT_ERROR
            self.message = "配置文件读取失败：%s" % error
        except OSError as error:
            self._status = STATUS_ACCESS_ERROR
            self.message = "配置文件读取失败：%s" % error

    def value(self, key, default=None):
        """按 ``a/b/c`` 形式的键路径取值，缺失时返回默认值。"""
        node = self._data
        for part in str(key).split("/"):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return default if node is None else node

    def set_value(self, key, value):
        """写入一个配置值，缺少的中间层级会自动建好。"""
        parts = str(key).split("/")
        node = self._data
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value

    def sync(self):
        """把内存中的配置写回文件，失败时只更新状态与原因。"""
        self.message = ""
        self._status = STATUS_NO_ERROR
        # 即使某些分组暂时为空也保留 core 与 gui，方便用户直接编辑文件；
        # 同时固定成 core 在前、gui 在后，避免两次保存的顺序来回变化。
        ordered = {}
        for section in ("core", "gui"):
            group = self._data.get(section)
            ordered[section] = group if isinstance(group, dict) else {}
        for key, value in self._data.items():
            if key not in ordered:
                ordered[key] = value
        self._data.clear()
        self._data.update(ordered)
        try:
            config.write(self.path, self._data, SETTINGS_COMMENTS)
        except OSError as error:
            self._status = STATUS_ACCESS_ERROR
            self.message = "配置文件保存失败：%s" % error
        self.exists = self.path.exists()
