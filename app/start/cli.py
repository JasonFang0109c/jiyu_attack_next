"""命令行的解析、日志生命周期与功能分发。"""

import sys

from app.features.files import cli as files_cli
from app.features.firewall import cli as firewall_cli
from app.features.firewall.service import FIREWALL_HELPER_ARGUMENT, run_firewall_helper
from app.features.local import cli as local_cli
from app.features.send import cli as send_cli
from app.features.shell import cli as shell_cli
from app.features.student import cli as student_cli
from app.features.student.service import STUDENT_HELPER_ARGUMENT, run_student_helper
from app.shared.logs import cli as cli_log
from app.shared.paths import portable_cli_log_path
from app.start.parser import build_group_parser


def start_logging():
    """启用命令行日志；写入阈值跟构建变体一致，文件与界面日志分开。"""
    cli_log.configure(portable_cli_log_path())
    log = cli_log.LOG
    if log.storage_error:
        print("[-] %s" % log.storage_error)
        return log
    log.debug("命令行日志已启用", "命令行", "文件：%s" % log.path)
    return log


def log_arguments(arguments):
    """记录参数类别与数量，不把消息或命令正文写入日志。"""
    cli_log.LOG.debug(
        "命令行参数",
        "命令行",
        "group=%s；command=%s；target=%s；port=%s；message=%s；command_text=%s；"
        "file_count=%s；loops=%s；interval=%s"
        % (
            arguments.group,
            arguments.command,
            arguments.ip,
            arguments.p,
            "已提供" if arguments.msg or arguments.msg_file else "未提供",
            "已提供" if arguments.c else "未提供",
            len(arguments.file or ()),
            arguments.l,
            arguments.t,
        ),
    )


def run_from_cmd(arguments):
    """校验参数并分发 CLI 请求。"""
    log_arguments(arguments)
    log = cli_log.LOG
    try:
        if arguments.group == "restriction":
            return student_cli.run_student_command(arguments)
        if arguments.group == "local":
            if arguments.command == "firewall":
                return firewall_cli.apply_firewall(arguments.firewall)
            return local_cli.print_local_info()
        if arguments.command == "shell":
            return shell_cli.run_shell(arguments)
        if arguments.command == "file":
            return files_cli.run_file_transfer(arguments)
        return send_cli.run_send(arguments)
    except Exception as e:
        print("[-] %s" % e)
        log.error("命令执行失败", "命令行", "异常：%s" % e)
        return 1


def main(argv=None):
    """解析参数并执行 CLI 或隐藏的防火墙助手。"""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == [FIREWALL_HELPER_ARGUMENT]:
        return run_firewall_helper(arguments[1:])
    if arguments[:1] == [STUDENT_HELPER_ARGUMENT]:
        return run_student_helper(arguments[1:])
    parse_error = None
    try:
        # 由解析器识别所有层级的帮助与版本参数，避免把参数值误当成帮助。
        options = build_group_parser().parse_args(arguments)
    except SystemExit as error:
        if error.code in (0, None):
            raise
        parse_error = error
    try:
        start_logging()
        command_context = (
            "分组：%s；子命令：%s" % (options.group, options.command)
            if parse_error is None
            else "参数解析失败"
        )
        cli_log.LOG.info(
            "命令行启动",
            "命令行",
            "参数数量：%d；%s" % (len(arguments), command_context),
        )
        if parse_error is not None:
            cli_log.LOG.warning(
                "参数解析未通过", "命令行", "退出码：%s" % parse_error.code
            )
            raise parse_error
        code = run_from_cmd(options)
        cli_log.LOG.info("命令行结束", "命令行", "退出码：%s" % code)
        return code
    finally:
        cli_log.close()
