"""防火墙的命令行参数与输出。"""

from app.features.firewall.service import request_firewall_rule
from app.shared.logs import cli as cli_log

# 动作与成功文案一一对应，阻断与恢复共用同一段输出与日志逻辑。
FIREWALL_RESULTS = {"block": "防火墙规则已阻断", "allow": "防火墙规则已恢复"}


def register(commands, defaults):
    """注册功能子命令并沿用统一参数默认值。"""
    firewall = commands.add_parser("firewall", help="防火墙：阻断或恢复学生端连接")
    firewall.set_defaults(**dict(defaults))
    firewall.add_argument(
        "firewall",
        choices=["block", "allow"],
        metavar="ACTION",
        help="block 阻断学生端、allow 恢复允许",
    )


def apply_firewall(action):
    """切换本机防火墙规则并输出结果，返回退出码。"""
    log = cli_log.LOG
    results = request_firewall_rule(action)
    if any(not item["success"] for item in results):
        print("[-] 部分防火墙设置失败，请检查管理员权限")
        log.warning("部分防火墙设置失败，请检查管理员权限", "防火墙")
        return 1
    print(FIREWALL_RESULTS.get(action, "防火墙规则已更新"))
    log.info("防火墙规则已更新", "防火墙", "动作：%s" % action)
    return 0
