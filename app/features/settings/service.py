"""GUI 设置工厂；与命令行共享同一份 JSON 存储。"""

from pathlib import Path

from app.features.settings.data import SETTINGS_FILE_NAME
from app.shared.paths import portable_data_dir
from app.shared.settings import SettingsStore


def portable_settings(data_dir=None):
    """返回便携设置对象，配置文件位于数据目录下的 settings.json。"""
    root = Path(data_dir).resolve() if data_dir is not None else portable_data_dir()
    return SettingsStore(root / SETTINGS_FILE_NAME)
