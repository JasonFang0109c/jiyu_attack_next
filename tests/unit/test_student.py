"""按模块组织的离线回归测试。"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app.features.student.service as student_service
import app.system.windows.process as windows_process
from tests.fixtures.offline import OfflineCase


def _record(pid=17600, path="", ports=(4705,), genuine=True, creation=123):
    """构造一条学生端进程记录。"""
    return {
        "pid": pid,
        "name": "StudentMain.exe",
        "ports": list(ports),
        "path": path,
        "genuine": genuine,
        "creation": creation,
    }


class StudentTests(OfflineCase):
    def test_find_student_processes_reports_listening_ports(self):
        exe = self._install_dir()
        rows = [
            {"pid": 17600, "name": "StudentMain.exe", "path": str(exe)},
            {"pid": 9002, "name": "explorer.exe", "path": "C:/Windows/explorer.exe"},
        ]
        with (
            patch.object(student_service, "list_processes", return_value=rows),
            patch.object(
                student_service,
                "listening_ports",
                return_value={17600: {4705, 51767}},
            ),
            patch.object(student_service, "process_creation_time", return_value=999),
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
                    "creation": 999,
                }
            ],
        )

    def test_find_student_processes_skips_other_programs_in_the_same_folder(self):
        # 极域安装目录里还有 DispcapHelper.exe 之类的同目录程序，不能被当成学生端。
        exe = self._install_dir()
        helper = exe.parent / "DispcapHelper.exe"
        helper.write_bytes(b"MZ")
        rows = [
            {"pid": 100, "name": "DispcapHelper.exe", "path": str(helper)},
            {"pid": 200, "name": "StudentMain.exe", "path": str(exe)},
        ]
        with (
            patch.object(student_service, "list_processes", return_value=rows),
            patch.object(student_service, "listening_ports", return_value={}),
            patch.object(student_service, "process_creation_time", return_value=1),
        ):
            processes = student_service.find_student_processes()
        self.assertEqual([item["pid"] for item in processes], [200])

    def test_find_student_processes_marks_decoy_without_library(self):
        exe = self._install_dir(with_library=False)
        rows = [{"pid": 17600, "name": "StudentMain.exe", "path": str(exe)}]
        with (
            patch.object(student_service, "list_processes", return_value=rows),
            patch.object(student_service, "listening_ports", return_value={}),
            patch.object(student_service, "process_creation_time", return_value=1),
        ):
            processes = student_service.find_student_processes()
        self.assertFalse(processes[0]["genuine"])

    def test_find_student_processes_falls_back_to_tasklist(self):
        tasks = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout='"StudentMain.exe","17600"\n"explorer.exe","9002"\n',
        )
        with (
            patch.object(
                student_service, "list_processes", side_effect=OSError("denied")
            ),
            patch.object(student_service, "run_windows_command", return_value=tasks),
            patch.object(student_service, "listening_ports", return_value={}),
            patch.object(student_service, "process_creation_time", return_value=1),
        ):
            processes = student_service.find_student_processes()
        self.assertEqual([item["pid"] for item in processes], [17600])
        self.assertEqual(processes[0]["path"], "")

    def test_stop_student_processes_forces_when_window_close_is_ignored(self):
        forced = {
            "pid": 17600,
            "code": 0,
            "output": "已强制结束",
            "success": True,
            "forced": True,
            "gone": True,
        }
        with (
            patch.object(
                student_service, "find_student_processes", side_effect=[[_record()], []]
            ),
            patch.object(student_service, "close_main_windows") as close,
            patch.object(student_service, "_wait_gone", return_value=False),
            patch.object(
                student_service, "terminate_process", return_value=dict(forced)
            ) as terminate,
            patch.object(student_service, "_is_admin", return_value=True),
        ):
            results = student_service.stop_student_processes([17600], guardian=False)
        close.assert_called_once_with(17600)
        self.assertEqual(terminate.call_args.args[:2], (17600, 123))
        self.assertTrue(results[0]["success"])
        self.assertTrue(results[0]["forced"])

    def test_stop_student_processes_treats_graceful_exit_as_success(self):
        with (
            patch.object(
                student_service, "find_student_processes", side_effect=[[_record()], []]
            ),
            patch.object(student_service, "close_main_windows"),
            patch.object(student_service, "_wait_gone", return_value=True),
            patch.object(student_service, "terminate_process") as terminate,
            patch.object(student_service, "_is_admin", return_value=True),
        ):
            results = student_service.stop_student_processes([17600], guardian=False)
        terminate.assert_not_called()
        self.assertTrue(results[0]["success"])
        self.assertFalse(results[0]["forced"])

    def test_stop_student_processes_elevates_when_denied(self):
        denied = {
            "pid": 17600,
            "code": 5,
            "output": "拒绝访问，需要管理员权限",
            "success": False,
            "forced": True,
            "gone": False,
            "elevatable": True,
        }
        elevated = {
            "pid": 17600,
            "code": 0,
            "output": "已强制结束",
            "success": True,
            "forced": True,
            "gone": True,
        }
        with (
            patch.object(
                student_service,
                "find_student_processes",
                side_effect=[[_record()], []],
            ),
            patch.object(student_service, "close_main_windows"),
            patch.object(student_service, "_wait_gone", return_value=False),
            patch.object(
                student_service, "terminate_process", return_value=dict(denied)
            ),
            patch.object(student_service, "_is_admin", return_value=False),
            patch.object(
                student_service, "_run_student_elevated", return_value=[elevated]
            ) as elevate,
        ):
            results = student_service.stop_student_processes([17600], guardian=False)
        elevate.assert_called_once_with("17600")
        self.assertTrue(results[0]["success"])

    def test_stop_student_processes_reports_respawned_student(self):
        respawn = _record(pid=19000)
        outcome = {
            "pid": 17600,
            "code": 0,
            "output": "已强制结束",
            "success": True,
            "forced": True,
            "gone": True,
        }
        with (
            patch.object(
                student_service,
                "find_student_processes",
                side_effect=[[_record()], [], [respawn]],
            ),
            patch.object(student_service, "close_main_windows"),
            patch.object(student_service, "_wait_gone", return_value=False),
            patch.object(
                student_service, "terminate_process", return_value=dict(outcome)
            ),
            patch.object(student_service, "_is_admin", return_value=True),
            patch.object(student_service.time, "sleep"),
        ):
            results = student_service.stop_student_processes([17600])
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["success"])
        self.assertTrue(results[1]["respawned"])
        self.assertFalse(results[1]["success"])
        self.assertIn("守护服务", results[1]["output"])

    def test_stop_student_processes_skips_guardian_window_on_request(self):
        with (
            patch.object(
                student_service, "find_student_processes", side_effect=[[_record()], []]
            ),
            patch.object(student_service, "close_main_windows"),
            patch.object(student_service, "_wait_gone", return_value=True),
            patch.object(student_service, "_is_admin", return_value=True),
        ):
            results = student_service.stop_student_processes([17600], guardian=False)
        self.assertEqual(len(results), 1)

    def test_find_student_executable_uses_service_directory(self):
        service_dir = Path(self.test_root) / "MythwareServices"
        service_dir.mkdir(exist_ok=True)
        exe = service_dir / "StudentMain.exe"
        exe.write_text("", encoding="utf-8")
        services = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=str(service_dir / "GATESRV.exe") + chr(10),
        )
        with (
            patch.object(student_service, "find_student_processes", return_value=[]),
            patch.object(student_service, "_uninstall_icon", return_value=[]),
            patch.object(student_service, "_registered_directories", return_value=[]),
            patch.object(student_service, "_saved_executable", return_value=""),
            patch.object(student_service, "run_windows_command", return_value=services),
        ):
            found = student_service.find_student_executable()
        self.assertEqual(found, str(exe.resolve()))

    def test_find_student_executable_prefers_saved_path(self):
        exe = self._install_dir()
        with (
            patch.object(student_service, "_saved_executable", return_value=str(exe)),
            patch.object(student_service, "find_student_processes") as probe,
        ):
            found = student_service.find_student_executable()
        self.assertEqual(found, str(exe.resolve()))
        probe.assert_not_called()

    def test_find_student_executable_prefers_genuine_running_process(self):
        genuine = self._install_dir()
        decoy_dir = Path(self.test_root) / "decoy"
        decoy_dir.mkdir(parents=True, exist_ok=True)
        decoy = decoy_dir / "StudentMain.exe"
        decoy.write_bytes(b"MZ")
        records = [
            _record(pid=100, path=str(decoy)),
            _record(pid=200, path=str(genuine)),
        ]
        with (
            patch.object(
                student_service, "find_student_processes", return_value=records
            ),
            patch.object(student_service, "_saved_executable", return_value=""),
        ):
            located = student_service.find_student_executable()
        self.assertEqual(located, str(genuine))

    def test_toggle_student_process_follows_running_state(self):
        with (
            patch.object(
                student_service, "find_student_processes", return_value=[_record()]
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

    def test_student_status_reports_port_owner_and_saved_path(self):
        exe = self._install_dir()
        with (
            patch.object(
                student_service,
                "find_student_processes",
                return_value=[_record(pid=200, path=str(exe), ports=(4705, 53176))],
            ),
            patch.object(student_service, "_saved_executable", return_value=""),
        ):
            status = student_service.student_status()
        self.assertEqual(status["port_owner"], 200)
        self.assertEqual(status["exe_path"], str(exe))
        self.assertEqual(status["port"], 4705)
        self.assertEqual(status["saved_path"], "")

    def test_student_status_uses_explicit_path_without_probing_executable(self):
        with (
            patch.object(student_service, "find_student_processes", return_value=[]),
            patch.object(student_service, "_saved_executable") as saved,
        ):
            status = student_service.student_status("C:/x/StudentMain.exe")
        saved.assert_not_called()
        self.assertEqual(status["saved_path"], "C:/x/StudentMain.exe")
        self.assertEqual(status["port_owner"], 0)

    def test_stop_student_processes_rejects_missing_targets(self):
        with (
            patch.object(student_service, "find_student_processes", return_value=[]),
            self.assertRaises(RuntimeError),
        ):
            student_service.stop_student_processes()
        with (
            patch.object(student_service, "find_student_processes", return_value=[]),
            self.assertRaises(ValueError),
        ):
            student_service.stop_student_processes(["not-a-pid"])

    def test_student_helper_rejects_bad_arguments(self):
        self.assertEqual(student_service.run_student_helper([]), 2)
        self.assertEqual(
            student_service.run_student_helper(["17600", "--student-result"]), 2
        )
        self.assertEqual(student_service.run_student_helper(["", "out.json"]), 2)

    def test_start_student_process_needs_existing_executable(self):
        missing = Path(self.test_root) / "missing-StudentMain.exe"
        with (
            patch.object(student_service, "find_student_processes", return_value=[]),
            self.assertRaises(RuntimeError) as raised,
        ):
            student_service.start_student_process(str(missing))
        self.assertIn("不存在", str(raised.exception))

    def test_start_student_process_refuses_second_instance(self):
        exe = Path(self.test_root) / "StudentMain.exe"
        exe.write_bytes(b"MZ")
        with (
            patch.object(
                student_service, "find_student_processes", return_value=[_record()]
            ),
            self.assertRaises(RuntimeError) as raised,
        ):
            student_service.start_student_process(str(exe))
        self.assertIn("已经有学生端在运行", str(raised.exception))

    def test_start_student_process_confirms_visible_process(self):
        exe = self._install_dir()
        with (
            patch.object(
                student_service,
                "find_student_processes",
                side_effect=[[], [_record(path=str(exe))]],
            ),
            patch.object(student_service, "_is_admin", return_value=True),
            patch.object(
                student_service,
                "_spawn",
                return_value={"path": str(exe), "success": True},
            ),
            patch.object(student_service, "save_executable") as save,
            patch.object(student_service.time, "sleep"),
        ):
            results = student_service.start_student_process(str(exe))
        self.assertTrue(results[0]["success"])
        self.assertTrue(results[0]["confirmed"])
        self.assertEqual(results[0]["pid"], 17600)
        save.assert_called_once_with(str(exe.resolve()))

    def test_start_student_process_reports_unconfirmed_when_nothing_appears(self):
        exe = self._install_dir()
        with (
            patch.object(student_service, "find_student_processes", return_value=[]),
            patch.object(student_service, "_is_admin", return_value=True),
            patch.object(
                student_service,
                "_spawn",
                return_value={"path": str(exe), "success": True},
            ),
            patch.object(student_service, "_wait_for_start", return_value={}),
            patch.object(student_service, "save_executable"),
        ):
            results = student_service.start_student_process(str(exe))
        self.assertTrue(results[0]["success"])
        self.assertFalse(results[0]["confirmed"])
        self.assertIn("没有检测到", results[0]["output"])

    def test_start_student_process_elevates_when_not_admin(self):
        exe = self._install_dir()
        with (
            patch.object(student_service, "find_student_processes", return_value=[]),
            patch.object(student_service, "_is_admin", return_value=False),
            patch.object(
                student_service,
                "_run_student_elevated",
                return_value=[{"path": str(exe), "success": True}],
            ) as elevate,
            patch.object(
                student_service,
                "_wait_for_start",
                return_value=_record(path=str(exe)),
            ),
            patch.object(student_service, "save_executable"),
        ):
            student_service.start_student_process(str(exe))
        elevate.assert_called_once_with("start=" + str(exe.resolve()))

    def test_student_helper_starts_the_executable_and_reports_it(self):
        exe = Path(self.test_root) / "StudentMain.exe"
        exe.write_bytes(b"MZ")
        result_file = Path(self.test_root) / "student-start.json"
        result_file.unlink(missing_ok=True)
        spawned = {
            "path": str(exe),
            "pid": 4242,
            "code": 0,
            "output": "已启动",
            "success": True,
            "forced": False,
        }
        with patch.object(student_service, "_spawn", return_value=spawned) as spawn:
            code = student_service.run_student_helper(
                ["start=" + str(exe), "--student-result", str(result_file)]
            )
        self.assertEqual(code, 0)
        self.assertEqual(spawn.call_args.args, (str(exe),))
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(payload["results"][0]["pid"], 4242)
        self.assertTrue(payload["results"][0]["success"])

    def test_student_helper_terminates_each_pid(self):
        result_file = Path(self.test_root) / "student-stop.json"
        done = {
            "pid": 1,
            "code": 0,
            "output": "已强制结束",
            "success": True,
            "forced": True,
            "gone": True,
        }
        with (
            patch.object(student_service, "process_creation_time", return_value=11),
            patch.object(
                student_service, "_terminate", return_value=dict(done)
            ) as terminate,
        ):
            code = student_service.run_student_helper(["17600,17601", str(result_file)])
        self.assertEqual(code, 0)
        self.assertEqual(terminate.call_count, 2)


class WindowsProcessTests(OfflineCase):
    def test_tasklist_output_is_still_parsed(self):
        rows = windows_process.process_rows(
            '"StudentMain.exe","17600"\n"explorer.exe","9002"\n'
        )
        self.assertEqual(rows, [("StudentMain.exe", "17600"), ("explorer.exe", "9002")])

    def test_is_process_alive_returns_false_on_non_windows(self):
        with patch.object(windows_process, "sys") as fake_sys:
            fake_sys.platform = "linux"
            self.assertFalse(windows_process.is_process_alive(4))

    def test_terminate_process_reports_access_denied_without_taskkill(self):
        # 拒绝访问要靠提权解决，此时不该再退回 taskkill 浪费时间。
        with (
            patch.object(windows_process, "_require_windows"),
            patch.object(windows_process, "_kernel32"),
            patch.object(windows_process, "is_process_alive", return_value=True),
            patch.object(windows_process, "enable_debug_privilege"),
            patch.object(windows_process, "_open_process", return_value=None),
            patch.object(windows_process.ctypes, "get_last_error", return_value=5),
            patch.object(windows_process, "_taskkill") as taskkill,
        ):
            outcome = windows_process.terminate_process(17600)
        taskkill.assert_not_called()
        self.assertFalse(outcome["success"])
        self.assertTrue(outcome["elevatable"])
        self.assertIn("管理员权限", outcome["output"])

    def test_terminate_process_returns_success_when_already_gone(self):
        with (
            patch.object(windows_process, "_require_windows"),
            patch.object(windows_process, "_kernel32"),
            patch.object(windows_process, "is_process_alive", return_value=False),
        ):
            outcome = windows_process.terminate_process(17600)
        self.assertTrue(outcome["success"])
        self.assertTrue(outcome["gone"])
        self.assertIn("已经退出", outcome["output"])
