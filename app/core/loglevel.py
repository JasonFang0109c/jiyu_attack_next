"""日志写入阈值：由构建变体固定，运行时不可更改。

正常版本只保留 ``WARNING`` 及以上，debug 版本从 ``DEBUG`` 起全量记录。
界面上不再提供切换入口：等级写进产物，避免用户误调导致问题记录缺失。
"""

from .buildvariant import IS_DEBUG

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
MINIMUM_LEVEL = "DEBUG" if IS_DEBUG else "WARNING"


def allows(level):
    """判断某个等级的记录是否达到写入阈值。

    Args:
        level: 等级文本，大小写不敏感。

    Returns:
        bool: 达到阈值返回 True，未知等级返回 False。
    """
    try:
        return LEVELS.index(str(level).upper()) >= LEVELS.index(MINIMUM_LEVEL)
    except ValueError:
        return False
