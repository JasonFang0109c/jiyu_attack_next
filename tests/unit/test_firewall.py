"""按模块组织的离线回归测试。"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import app.features.firewall.service as firewall_service
from tests.fixtures.offline import OfflineCase


class FirewallTests(OfflineCase):
    def test_firewall_running_service_exit_code_is_reported_as_success(self):
        responses = [
            SimpleNamespace(returncode=2, stdout="", stderr="请求的服务已经启动。"),
            SimpleNamespace(returncode=0, stdout="确定。", stderr=""),
            SimpleNamespace(returncode=0, stdout="已更新 6 规则。", stderr=""),
        ]
        with patch.object(
            firewall_service, "run_windows_command", side_effect=responses
        ) as command:
            results = firewall_service.set_firewall_rule("block")
        self.assertEqual(command.call_count, 3)
        self.assertEqual(results[0]["command"], "net.exe start MpsSvc")
        self.assertTrue(results[0]["success"])
        self.assertIn("原本已在运行", results[0]["stdout"])
        self.assertTrue(results[1]["success"])
        self.assertTrue(results[2]["success"])

    def test_firewall_rule_elevates_only_when_needed(self):
        results = [{"command": "netsh", "success": True}]
        with (
            patch.object(firewall_service.sys, "platform", "win32"),
            patch.object(firewall_service, "_is_admin", return_value=False),
            patch.object(
                firewall_service, "_run_firewall_elevated", return_value=results
            ) as elevated,
            patch.object(firewall_service, "set_firewall_rule") as local,
        ):
            self.assertIs(firewall_service.request_firewall_rule("block"), results)
        elevated.assert_called_once_with("block")
        local.assert_not_called()

    def test_firewall_rule_runs_locally_when_already_admin(self):
        results = [{"command": "netsh", "success": True}]
        with (
            patch.object(firewall_service.sys, "platform", "win32"),
            patch.object(firewall_service, "_is_admin", return_value=True),
            patch.object(
                firewall_service, "set_firewall_rule", return_value=results
            ) as local,
            patch.object(firewall_service, "_run_firewall_elevated") as elevated,
        ):
            self.assertIs(firewall_service.request_firewall_rule("allow"), results)
        local.assert_called_once_with("allow")
        elevated.assert_not_called()

    def test_firewall_helper_reports_results_and_errors(self):
        result_path = self.test_root / "firewall-helper.json"
        self.addCleanup(lambda: result_path.unlink(missing_ok=True))
        results = [{"command": "netsh", "success": True}]
        with patch.object(firewall_service, "set_firewall_rule", return_value=results):
            code = firewall_service.run_firewall_helper(
                ["block", "--firewall-result", str(result_path)]
            )
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(result_path.read_text(encoding="utf-8")), {"results": results}
        )
        with patch.object(
            firewall_service,
            "set_firewall_rule",
            side_effect=RuntimeError("权限不足"),
        ):
            code = firewall_service.run_firewall_helper(
                ["block", "--firewall-result", str(result_path)]
            )
        self.assertEqual(code, 1)
        self.assertEqual(
            json.loads(result_path.read_text(encoding="utf-8")), {"error": "权限不足"}
        )

    def test_firewall_helper_rejects_invalid_arguments(self):
        self.assertEqual(firewall_service.run_firewall_helper([]), 2)
        self.assertEqual(firewall_service.run_firewall_helper(["block"]), 2)
