"""按模块组织的离线回归测试。"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.features.student.service as student_service
from tests.fixtures.offline import OfflineCase


class StudentTests(OfflineCase):
    def test_find_student_processes_reports_listening_ports(self):
        exe = self._install_dir()
        tasks = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout='"StudentMain.exe","17600"\n"explorer.exe","9002"\n',
        )
        udp = SimpleNamespace(
            returncode=0, stderr="", stdout="UDP 192.168.50.22:4705 *:* 17600\n"
        )
        tcp = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout="TCP 192.168.50.22:51767 0.0.0.0:0 LISTENING 17600\n",
        )
        paths = SimpleNamespace(returncode=0, stderr="", stdout="17600|%s\n" % exe)
        with patch.object(
            student_service,
            "run_windows_command",
            side_effect=[tasks, udp, tcp, paths],
        ):
            processes = student_service.find_student_processes()
        self.assertEqual(
            processes,
            [
                {
                    "pid": 17600,
                    "name": "StudentMain.exe",
                    "ports": [4705, 51767],
                    "path": str(exe),
                    "genuine": True,
                }
            ],
        )

    def test_find_student_processes_marks_decoy_without_library(self):
        exe = self._install_dir(with_library=False)
        tasks = SimpleNamespace(
            returncode=0, stderr="", stdout='"StudentMain.exe","17600"\n'
        )
        ports = SimpleNamespace(returncode=0, stderr="", stdout="")
        paths = SimpleNamespace(returncode=0, stderr="", stdout="17600|%s\n" % exe)
        with patch.object(
            student_service,
            "run_windows_command",
            side_effect=[tasks, ports, ports, paths],
        ):
            processes = student_service.find_student_processes()
        self.assertFalse(processes[0]["genuine"])

    def test_stop_student_processes_escalates_from_graceful_to_force(self):
        outcomes = [
            {
                "pid": 17600,
                "code": 5,
                "output": "拒绝访问",
                "success": False,
                "forced": False,
            },
            {
                "pid": 17600,
                "code": 0,
                "output": "成功",
                "success": True,
                "forced": True,
            },
        ]
        with (
            patch.object(
                student_service, "_taskkill", side_effect=outcomes
            ) as taskkill,
            patch.object(student_service, "_wait_gone", side_effect=[False, True]),
            patch.object(student_service, "_pid_alive", return_value=False),
            patch.object(student_service, "find_student_processes", return_value=[]),
            patch.object(student_service, "_is_admin", return_value=True),
        ):
            results = student_service.stop_student_processes([17600])
        self.assertEqual(
            [item.kwargs["force"] for item in taskkill.call_args_list], [False, True]
        )
        self.assertTrue(results[0]["success"])
        self.assertTrue(results[0]["forced"])
        self.assertTrue(results[0]["gone"])

    def test_terminate_escalates_when_graceful_signal_leaves_it_running(self):
        # 极域学生端不响应正常退出，taskkill 不加 /F 也返回成功，要靠存活检查升级。
        graceful = {
            "pid": 17600,
            "code": 0,
            "output": "成功: 给进程发送了终止信号",
            "success": True,
            "forced": False,
        }
        forced = {
            "pid": 17600,
            "code": 0,
            "output": "成功: 已终止",
            "success": True,
            "forced": True,
        }
        with (
            patch.object(
                student_service, "_taskkill", side_effect=[graceful, forced]
            ) as taskkill,
            patch.object(student_service, "_wait_gone", side_effect=[False, True]),
        ):
            outcome = student_service._terminate(17600)
        self.assertEqual(
            [item.kwargs["force"] for item in taskkill.call_args_list], [False, True]
        )
        self.assertTrue(outcome["success"])
        self.assertTrue(outcome["gone"])

    def test_stop_student_processes_reports_respawned_student(self):
        respawn = {
            "pid": 19000,
            "name": "StudentMain.exe",
            "ports": [4705],
            "path": "",
            "genuine": False,
        }
        outcome = {
            "pid": 17600,
            "code": 0,
            "output": "成功",
            "success": True,
            "forced": True,
        }
        with (
            patch.object(student_service, "_taskkill", return_value=outcome),
            patch.object(student_service, "_wait_gone", return_value=True),
            patch.object(student_service, "_pid_alive", return_value=False),
            patch.object(
                student_service,
                "find_student_processes",
                side_effect=[[respawn]],
            ),
            patch.object(student_service, "_is_admin", return_value=True),
        ):
            results = student_service.stop_student_processes([17600])
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["success"])
        self.assertTrue(results[1]["respawned"])
        self.assertFalse(results[1]["success"])
        self.assertIn("守护服务", results[1]["output"])

    def test_find_student_executable_uses_service_directory(self):
        root = Path(self.test_root)
        service_dir = root / "Mythware"
        service_dir.mkdir(exist_ok=True)
        exe = service_dir / "StudentMain.exe"
        exe.write_text("", encoding="utf-8")
        plain = str(service_dir / "GATESRV.exe")
        services = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=plain + chr(10),
        )
        with (
            patch.object(student_service, "find_student_processes", return_value=[]),
            patch.object(student_service, "_uninstall_icon", return_value=[]),
            patch.object(student_service, "_registered_directories", return_value=[]),
            patch.object(
                student_service,
                "run_windows_command",
                return_value=services,
            ),
        ):
            found = student_service.find_student_executable()
        self.assertEqual(found, str(exe.resolve()))

    def test_toggle_student_process_follows_running_state(self):
        record = {
            "pid": 17600,
            "name": "StudentMain.exe",
            "ports": [4705],
            "path": "",
            "genuine": False,
        }
        with (
            patch.object(
                student_service,
                "find_student_processes",
                return_value=[record],
            ),
            patch.object(
                student_service,
                "stop_student_processes",
                return_value=[{"pid": 17600, "success": True}],
            ) as stop,
        ):
            stopped = student_service.toggle_student_process()
        self.assertEqual(stopped["action"], "stop")
        self.assertEqual(stop.call_args.args, ([17600],))
        with (
            patch.object(student_service, "find_student_processes", return_value=[]),
            patch.object(
                student_service,
                "start_student_process",
                return_value=[{"path": "C:/x/StudentMain.exe", "success": True}],
            ) as start,
        ):
            started = student_service.toggle_student_process("C:/x/StudentMain.exe")
        self.assertEqual(started["action"], "start")
        self.assertEqual(start.call_args.args, ("C:/x/StudentMain.exe",))

    def test_find_student_executable_prefers_genuine_running_process(self):
        genuine = self._install_dir()
        decoy_dir = self.test_root / "decoy"
        decoy_dir.mkdir(parents=True, exist_ok=True)
        decoy = decoy_dir / "StudentMain.exe"
        decoy.write_bytes(b"MZ")
        records = [
            {"pid": 100, "name": "StudentMain.exe", "ports": [], "path": str(decoy)},
            {
                "pid": 200,
                "name": "StudentMain.exe",
                "ports": [],
                "path": str(genuine),
            },
        ]
        with patch.object(
            student_service, "find_student_processes", return_value=records
        ):
            located = student_service.find_student_executable()
        self.assertEqual(located, str(genuine))

    def test_stop_student_processes_rejects_missing_targets(self):
        tasks = SimpleNamespace(
            returncode=0, stderr="", stdout='"explorer.exe","9002"\n'
        )
        with (
            patch.object(student_service, "run_windows_command", return_value=tasks),
            self.assertRaises(RuntimeError),
        ):
            student_service.stop_student_processes()
        with self.assertRaises(ValueError):
            student_service.stop_student_processes(["not-a-pid"])

    def test_student_helper_rejects_bad_arguments(self):
        self.assertEqual(student_service.run_student_helper([]), 2)
        self.assertEqual(
            student_service.run_student_helper(["17600", "--student-result"]), 2
        )

    def test_start_student_process_needs_existing_executable(self):
        missing = self.test_root / "missing-StudentMain.exe"
        with (
            patch.object(student_service, "find_student_processes", return_value=[]),
            self.assertRaises(RuntimeError) as raised,
        ):
            student_service.start_student_process(str(missing))
        self.assertIn("不存在", str(raised.exception))

    def test_start_student_process_refuses_second_instance(self):
        exe = self.test_root / "StudentMain.exe"
        exe.write_bytes(b"MZ")
        running = [{"pid": 17600, "name": "StudentMain.exe", "ports": [4705]}]
        with (
            patch.object(
                student_service,
                "find_student_processes",
                return_value=running,
            ),
            self.assertRaises(RuntimeError) as raised,
        ):
            student_service.start_student_process(str(exe))
        self.assertIn("已经有学生端在运行", str(raised.exception))

    def test_student_helper_starts_the_executable_and_reports_it(self):
        exe = self.test_root / "StudentMain.exe"
        exe.write_bytes(b"MZ")
        result_file = self.test_root / "student-start.json"
        result_file.unlink(missing_ok=True)
        launched = MagicMock(pid=4242)
        with patch.object(
            student_service.subprocess, "Popen", return_value=launched
        ) as popen:
            code = student_service.run_student_helper(
                ["start=" + str(exe), "--student-result", str(result_file)]
            )
        self.assertEqual(code, 0)
        self.assertEqual(popen.call_args.args[0], [str(exe)])
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(payload["results"][0]["pid"], 4242)
        self.assertTrue(payload["results"][0]["success"])
