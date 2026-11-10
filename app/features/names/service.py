"""设备备注校验、持久化及变更通知，保持与界面框架无关。"""

import json

import app.system.net.targets as system_net_targets
from app.features.names.data import DEVICE_ALIAS_SETTINGS_KEY, MAX_NAME_LENGTH
from app.features.settings.service import portable_settings
from app.shared.settings import STATUS_NO_ERROR


class DeviceAliasService:
    """保存可复用的 IPv4 设备备注。"""

    SETTINGS_KEY = DEVICE_ALIAS_SETTINGS_KEY
    MAX_NAME_LENGTH = MAX_NAME_LENGTH

    def __init__(self, settings=None, changed=None, renamed=None, removed=None):
        self.changed = changed or (lambda: None)
        self.renamed = renamed or (lambda old, new: None)
        self.removed = removed or (lambda name: None)
        self._settings = settings if settings is not None else portable_settings()
        self._aliases = {}
        self.load_error = ""
        # 只有整体无法解析时才设为只读，避免把损坏的原数据覆盖掉。
        self._readonly = False
        self._load()

    def _load(self):
        """从设置文件读取备注；整体损坏时保留空表并拒绝写回。"""
        raw = self._settings.value(self.SETTINGS_KEY, {})
        try:
            if isinstance(raw, str):
                data = json.loads(raw) if raw else {}
            elif isinstance(raw, dict):
                data = raw
            else:
                raise ValueError("备注数据格式无效")
            if not isinstance(data, dict):
                raise ValueError("备注数据格式无效")
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            self.load_error = "设备备注读取失败：%s" % error
            self._readonly = True
            return
        aliases = {}
        invalid = 0
        for name, address in data.items():
            try:
                aliases[self._normalize_name(name)] = self._normalize_address(address)
            except (TypeError, ValueError):
                # 一条坏数据不该让整张备注表不可用，跳过它并提示保存会丢弃。
                invalid += 1
        self._aliases = aliases
        if invalid:
            self.load_error = "设备备注中有 %d 条无法读取，保存后会被丢弃" % invalid

    @classmethod
    def _normalize_name(cls, name):
        """校验备注名：非空、不超长、不含换行或 NUL，且不能是 IP 地址。"""
        if name is None:
            raise ValueError("请填写备注名")
        value = str(name).strip()
        if not value:
            raise ValueError("请填写备注名")
        if len(value) > cls.MAX_NAME_LENGTH:
            raise ValueError("备注名不能超过 %d 个字符" % cls.MAX_NAME_LENGTH)
        if any(character in value for character in ("\x00", "\r", "\n")):
            raise ValueError("备注名不能包含换行或 NUL 字符")
        try:
            # 备注名不能与地址混淆，这里只校验格式，不展开地址列表。
            system_net_targets.count_targets(value)
        except ValueError:
            return value
        raise ValueError("备注名不能使用 IP 地址格式")

    @staticmethod
    def _normalize_address(address):
        """校验地址；单地址规范化为点分形式，范围与 /24 保留原写法。"""
        value = str(address).strip()
        if not value:
            raise ValueError("请填写 IP 地址")
        try:
            hosts = system_net_targets.get_ip(value)
        except ValueError as error:
            raise ValueError(
                "IP 地址格式错误，请填写单个 IPv4 地址、末段范围或 /24 网段"
            ) from error
        return value if "-" in value or "/" in value else hosts[0]

    def items(self):
        """返回 (备注名, 地址) 列表，供下拉框与表格使用。"""
        return list(self._aliases.items())

    def _find_name(self, name):
        """按不区分大小写的方式查找已存在的备注名。"""
        key = str(name).strip().casefold()
        for existing in self._aliases:
            if existing.casefold() == key:
                return existing
        return None

    def match(self, target):
        """备注名命中时返回 (备注名, 地址)，否则返回 None。"""
        name = self._find_name(target)
        return (name, self._aliases[name]) if name is not None else None

    def resolve(self, target):
        """把备注名换成地址，未命中时原样返回输入。"""
        matched = self.match(target)
        return matched[1] if matched else str(target).strip()

    def format_target(self, target):
        """返回“备注名（地址）”的展示文本，未命中时原样返回。"""
        matched = self.match(target)
        if matched:
            return "%s（%s）" % matched
        return str(target).strip()

    def _save(self, aliases):
        """写入设置文件；读取阶段出错时拒绝写入，避免覆盖原数据。"""
        if self._readonly:
            raise OSError(
                "%s；为避免覆盖原数据，请先修复或清除该配置项" % self.load_error
            )
        self._settings.set_value(self.SETTINGS_KEY, dict(aliases))
        self._settings.sync()
        if self._settings.status() != STATUS_NO_ERROR:
            raise OSError(
                "设备备注保存失败：%s" % (self._settings.message or "写入失败")
            )
        self._aliases = aliases
        self.load_error = ""

    def add(self, name, address):
        """新增一条备注，重名或地址非法时抛出 ValueError。"""
        normalized_name = self._normalize_name(name)
        normalized_address = self._normalize_address(address)
        if self._find_name(normalized_name) is not None:
            raise ValueError("备注名已存在")
        aliases = dict(self._aliases)
        aliases[normalized_name] = normalized_address
        self._save(aliases)
        self.changed()

    def update(self, original_name, name, address):
        """修改备注；改名时额外发出 renamed 信号，供页面同步引用。"""
        existing_name = self._find_name(original_name)
        if existing_name is None:
            raise ValueError("要修改的备注不存在")
        normalized_name = self._normalize_name(name)
        normalized_address = self._normalize_address(address)
        duplicate = self._find_name(normalized_name)
        if duplicate is not None and duplicate.casefold() != existing_name.casefold():
            raise ValueError("备注名已存在")
        aliases = {}
        for alias_name, alias_address in self._aliases.items():
            if alias_name.casefold() == existing_name.casefold():
                aliases[normalized_name] = normalized_address
            else:
                aliases[alias_name] = alias_address
        self._save(aliases)
        if existing_name != normalized_name:
            self.renamed(existing_name, normalized_name)
        self.changed()

    def remove(self, name):
        """删除一条备注，不存在时抛出 ValueError。"""
        existing_name = self._find_name(name)
        if existing_name is None:
            raise ValueError("要删除的备注不存在")
        aliases = {
            alias_name: address
            for alias_name, address in self._aliases.items()
            if alias_name.casefold() != existing_name.casefold()
        }
        self._save(aliases)
        self.removed(existing_name)
        self.changed()

    def clear(self, persist=True):
        """清空全部设备备注；需要时可跳过写入以配合数据目录删除。"""
        previous_names = tuple(self._aliases)
        previous_error = self.load_error
        if persist:
            self.load_error = ""
            try:
                self._save({})
            except OSError:
                self.load_error = previous_error
                raise
        else:
            self._aliases = {}
            self.load_error = ""
        for name in previous_names:
            self.removed(name)
        self.changed()
