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
from app.start.parser import GROUP_NAMES, build_flat_parser, build_group_parser


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
    """把本次参数快照写进日志，便于事后复现。"""
    cli_log.LOG.debug(
        "命令行参数",
        "命令行",
        "ip=%s；port=%s；msg=%s；msg_file=%s；file=%s；c=%s；l=%s；t=%s；e=%s；"
        "file_ip=%s；file_timeout=%s"
        % (
            arguments.ip,
            arguments.p,
            arguments.msg,
            arguments.msg_file,
            arguments.file,
            arguments.c,
            arguments.l,
            arguments.t,
            arguments.e,
            arguments.file_ip,
            arguments.file_timeout,
        ),
    )


def run_from_cmd(arguments):
    """校验参数并分发 CLI 请求。"""
    log_arguments(arguments)
    log = cli_log.LOG
    try:
        if arguments.shell or arguments.e == "nc":
            return shell_cli.run_shell(arguments)
        if (
            arguments.endstudent
            or arguments.list
            or arguments.start_student
            or arguments.pid
        ):
            return student_cli.run_student_command(arguments)
        if arguments.firewall:
            return firewall_cli.apply_firewall(arguments.firewall)
        if arguments.e == "g":
            return local_cli.print_local_info()
        if arguments.e in {"break", "continue"}:
            return firewall_cli.run_legacy_action(arguments.e)
        if arguments.file:
            if arguments.e or arguments.msg or arguments.msg_file or arguments.c:
                raise ValueError("文件传送不能与消息、命令或 -e 扩展功能同时使用")
            return files_cli.run_file_transfer(arguments)
        if arguments.file_ip or arguments.file_timeout != 120:
            raise ValueError("--file-ip 和 --file-timeout 仅用于文件传送")
        return send_cli.run_send(arguments)
    except Exception as e:
        print("[-] %s" % e)
        log.error("命令执行失败", "命令行", "异常：%s" % e)
        return 1


def _select_parser(arguments):
    """按首个参数选择分类写法或扁平写法的解析器。

    Args:
        arguments: 去掉程序名之后的参数列表。

    Returns:
        argparse.ArgumentParser: 首参数是 ``restriction``/``remote``/``local``
        时返回分类解析器，否则返回扁平解析器。
    """
    if arguments[:1] and arguments[0] in (*GROUP_NAMES, "-h", "--help"):
        return build_group_parser()
    return build_flat_parser()


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
        options = _select_parser(arguments).parse_args(arguments)
    except SystemExit as error:
        if error.code in (0, None):
            raise
        parse_error = error
    try:
        start_logging()
        cli_log.LOG.info(
            "命令行启动",
            "命令行",
            "参数：%s" % (" ".join(arguments) if arguments else "无"),
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
