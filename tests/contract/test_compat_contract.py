"""验证兼容层数据、协议与延迟转发契约。"""

import sys
import unittest
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import patch

from app.compat.errors import (
    BackendOperationError,
    CompatibilityError,
    UnsupportedBackendError,
)
from app.compat.flags import GUARD_ALL
from app.compat.legacy import (
    execute_send_report,
    prepare_packets,
    run_uninstall,
    start_guard,
    student_status,
)
from app.compat.models import GuardPolicy, OperationResult, StudentSnapshot, Target
from app.compat.protocols import (
    DriverBackend,
    GuardBackend,
    StudentController,
    UdpTransport,
    UninstallBackend,
    WindowController,
)


class FakeBackend:
    """满足各兼容协议的纯 Python 假后端。"""

    def send(self, packets, target):
        return OperationResult(True, details={"count": len(packets)})

    def snapshot(self, exe_path=None):
        return StudentSnapshot(port=4705, executable_path=exe_path or "")

    def terminate(self, pid):
        return OperationResult(True, gone=True, details={"pid": pid})

    def close_process_windows(self, pid):
        return 1

    def start(self, pid, policy):
        return (pid, policy.flags)

    def stop(self, session):
        return OperationResult(True, details={"session": session})

    def remove(self):
        return OperationResult(True, kernel=True)

    def run(self, keep_user_data=False, remove_driver=True):
        return OperationResult(
            True,
            details={"keep_user_data": keep_user_data, "remove_driver": remove_driver},
        )


class DataModelContractTests(unittest.TestCase):
    """验证数据模型输入约束与序列化形状。"""

    def test_target_validates_host_and_port(self):
        self.assertEqual(Target(" host ", 4705), Target("host", 4705))
        for host, port in ((" ", 1), ("host", 0), ("host", 65536), ("host", True)):
            with self.subTest(host=host, port=port), self.assertRaises(ValueError):
                Target(host, port)

    def test_guard_policy_masks_unknown_flags_and_queries_bits(self):
        policy = GuardPolicy(GUARD_ALL | 32)
        self.assertEqual(policy.flags, GUARD_ALL)
        self.assertTrue(policy.enabled())
        self.assertTrue(policy.enabled(1))
        self.assertTrue(policy.has(3))
        self.assertFalse(GuardPolicy(0).enabled())
        self.assertFalse(policy.has(32))

    def test_operation_result_is_dataclass_serializable(self):
        result = OperationResult(
            True,
            "done",
            code=0,
            forced=True,
            gone=True,
            kernel=False,
            details={"pid": 42},
        )
        self.assertEqual(
            asdict(result),
            {
                "success": True,
                "message": "done",
                "code": 0,
                "forced": True,
                "gone": True,
                "kernel": False,
                "details": {"pid": 42},
            },
        )
        self.assertEqual(asdict(StudentSnapshot())["processes"], ())

    def test_compatibility_exception_hierarchy(self):
        self.assertTrue(issubclass(UnsupportedBackendError, CompatibilityError))
        self.assertTrue(issubclass(BackendOperationError, CompatibilityError))
        self.assertTrue(issubclass(CompatibilityError, Exception))


class ProtocolContractTests(unittest.TestCase):
    """验证假后端可通过运行时协议检查并正常调用。"""

    def test_fake_backend_satisfies_protocols_and_calls(self):
        backend = FakeBackend()
        for protocol in (
            UdpTransport,
            StudentController,
            WindowController,
            GuardBackend,
            DriverBackend,
            UninstallBackend,
        ):
            with self.subTest(protocol=protocol.__name__):
                self.assertIsInstance(backend, protocol)

        target = Target("127.0.0.1", 4705)
        self.assertEqual(backend.send([b"packet"], target).details["count"], 1)
        self.assertEqual(backend.snapshot("student.exe").executable_path, "student.exe")
        self.assertTrue(backend.terminate(42).gone)
        self.assertEqual(backend.close_process_windows(42), 1)
        session = backend.start(42, GuardPolicy(1))
        self.assertTrue(backend.stop(session).success)
        self.assertTrue(backend.remove().kernel)
        self.assertTrue(backend.run(keep_user_data=True).success)


class LegacyForwardingContractTests(unittest.TestCase):
    """验证旧服务转发按需导入且不触发 Qt 导入。"""

    def test_legacy_forwarders_are_lazy_and_do_not_load_qt(self):
        sentinel = object()
        calls = []

        def fake_import(module_name):
            calls.append(module_name)
            return SimpleNamespace(
                prepare_packets=lambda *args, **kwargs: (args, kwargs),
                execute_send_report=lambda *args, **kwargs: sentinel,
                student_status=lambda *args, **kwargs: sentinel,
                start_guard=lambda *args, **kwargs: sentinel,
                run_uninstall=lambda *args, **kwargs: sentinel,
            )

        qt_before = {
            name for name in sys.modules if name.startswith(("PySide6", "PyQt"))
        }
        self.assertEqual(calls, [])
        with patch("app.compat.legacy.import_module", side_effect=fake_import):
            self.assertEqual(
                prepare_packets("options", report="callback"),
                (("options",), {"report": "callback"}),
            )
            self.assertIs(execute_send_report("options"), sentinel)
            self.assertIs(student_status(exe_path="student.exe"), sentinel)
            self.assertIs(start_guard(flags=3), sentinel)
            self.assertIs(run_uninstall(True), sentinel)

        self.assertEqual(
            calls,
            [
                "app.features.send.service",
                "app.features.send.service",
                "app.features.student.service",
                "app.features.classroom.service",
                "app.features.uninstall.service",
            ],
        )
        qt_after = {
            name for name in sys.modules if name.startswith(("PySide6", "PyQt"))
        }
        self.assertEqual(qt_after, qt_before)


if __name__ == "__main__":
    unittest.main()
