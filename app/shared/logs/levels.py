"""日志等级：正常版本不记录 ``DEBUG``，调试版本固定全量记录。

正常版本的下拉框只给 ``INFO``、``WARNING``、``ERROR``；调试版本强制从
``DEBUG`` 起，界面与设置文件都改不动它。命令行共用这里的阈值。
"""

from app.shared.build_variant import IS_DEBUG

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
# 正常版本不产出 DEBUG 记录，下拉框里也就不给这个选项。
SELECTABLE_LEVELS = LEVELS if IS_DEBUG else ("INFO", "WARNING", "ERROR")
DEFAULT_LEVEL = "DEBUG" if IS_DEBUG else "WARNING"
MINIMUM_LEVEL = DEFAULT_LEVEL
# 调试版本固定阈值：设置文件里的默认等级不参与判断，界面也不给改。
FORCED_LEVEL = "DEBUG" if IS_DEBUG else None


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
