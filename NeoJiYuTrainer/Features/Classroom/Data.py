"""课堂助手：窗口识别规则、看护参数与极域注册表常量。

窗口标题匹配与几何算法取自 JiYuTrainer（MIT）的 ``TrainerWorker.cpp``，这里只保留
纯数据与常量，方便单元测试直接断言移植结果。
"""

# 上游 CheckWindowTextIsGb 的标题匹配规则：包含这些词即为极域课堂窗口。
BROADCAST_TITLE_KEYWORDS = ("广播", "演示", "共享")
# 旧版极域的屏幕演播室窗口标题，需要整串相等才算。
BROADCAST_TITLE_EXACT = "屏幕演播室窗口"
BLACK_SCREEN_TITLE = "BlackScreen Window"

# 黑屏窗口被缩到屏幕左上角并隐藏，尺寸与上游 FixWindow 一致。
BLACK_SCREEN_GEOMETRY = (20, 20, 90, 150)

# 假全屏关闭后窗口占屏幕的比例，取自上游 FakeFull 的 3/4 与 4/5。
WINDOWED_WIDTH_RATIO = 3 / 4
WINDOWED_HEIGHT_RATIO = 4 / 5

# 设置键沿用仓库的 core/<功能>/<项> 分组，写入同一份 settings.json。
SETTINGS_AUTO_REPAIR = "core/classroom/auto_repair"
SETTINGS_INTERVAL = "core/classroom/interval"
SETTINGS_ALLOW_TOP = "core/classroom/allow_top"
SETTINGS_INCLUDE_FULLSCREEN = "core/classroom/include_fullscreen"
SETTINGS_HIDE_BLACK_SCREEN = "core/classroom/hide_black_screen"
SETTINGS_GUARD_FLAGS = "core/classroom/guard_flags"

DEFAULT_AUTO_REPAIR = True
# 上游默认 3100 毫秒查一次窗口，这里取整成 3 秒。
DEFAULT_INTERVAL = 3
INTERVAL_RANGE = (1, 10)
DEFAULT_ALLOW_TOP = False
DEFAULT_INCLUDE_FULLSCREEN = True
DEFAULT_HIDE_BLACK_SCREEN = True
# 课堂防护位与 NeoJiYuTrainerHooks/Policy.h 的 JIYU_GUARD_* 一一对应。
DEFAULT_GUARD_FLAGS = 0
GUARD_ITEMS = (
    (1, "阻止屏幕监视"),
    (2, "阻止远程控制"),
    (4, "禁止关闭窗口"),
    (8, "禁止结束进程"),
    (16, "监控远程命令"),
)

# 设置键到业务字段的映射：页面信号发的是设置键，业务层用短名。
OPTION_NAMES = {
    SETTINGS_AUTO_REPAIR: "auto_repair",
    SETTINGS_INTERVAL: "interval",
    SETTINGS_ALLOW_TOP: "allow_top",
    SETTINGS_INCLUDE_FULLSCREEN: "include_fullscreen",
    SETTINGS_HIDE_BLACK_SCREEN: "hide_black_screen",
    SETTINGS_GUARD_FLAGS: "guard_flags",
}

# 极域把卸载密码放在 Uninstall\e-Learning Class V6.0 之外的另一个键。
PASSWORD_KEY_PATHS = (
    r"SOFTWARE\TopDomain\e-Learning Class Standard\1.00",
    r"SOFTWARE\Wow6432Node\TopDomain\e-Learning Class Standard\1.00",
)
PASSWORD_VALUE_NAME = "UninstallPasswd"
# 6.0 起明文位换成这个标记，真正的密码要解 Knock1。
PASSWORD_KNOCK_SENTINEL = "Passwd[123456]"
PASSWORD_PLAIN_PREFIX_LENGTH = 6

KNOCK_KEY_PATHS = (
    r"SOFTWARE\Wow6432Node\TopDomain\e-Learning Class\Student",
    r"SOFTWARE\TopDomain\e-Learning Class\Student",
)
KNOCK_VALUE_NAME = "Knock1"
KNOCK_MAX_LENGTH = 32

# 上游 UnDecryptJiyuKnock 的两轮 XOR 常量，按小端 DWORD 依次异或。
KNOCK_XOR_FIRST = 0x50434C45
KNOCK_XOR_SECOND = 0x454C4350
