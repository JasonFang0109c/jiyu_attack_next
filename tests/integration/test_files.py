"""按模块组织的离线回归测试。"""

import shutil
import urllib.request
from threading import Event
from unittest.mock import patch

import app.features.files.service as files_service
import app.packets.constants as constants
from tests.fixtures.offline import OfflineCase


class FilesTests(OfflineCase):
    def test_file_transfer_validation(self):
        directory = self.test_root / "validation"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "测试 文件.txt"
            source.write_bytes(b"hello")
            result = files_service.validate_file_transfer(
                "192.168.1.10", 4705, str(source)
            )
            self.assertEqual(result, source.resolve())
            self.assertEqual(
                files_service.validate_file_transfer(
                    "192.168.1.1-2", 4705, str(source)
                ),
                source.resolve(),
            )
            self.assertEqual(
                files_service.validate_file_transfer(
                    "192.168.1.0/24", 4705, str(source)
                ),
                source.resolve(),
            )
            with self.assertRaisesRegex(ValueError, "IP 格式错误"):
                files_service.validate_file_transfer(
                    "192.168.1.10-1", 4705, str(source)
                )
            with self.assertRaisesRegex(ValueError, "文件不存在"):
                files_service.validate_file_transfer(
                    "192.168.1.10", 4705, str(source) + ".missing"
                )
            with self.assertRaisesRegex(ValueError, "文件"):
                files_service.validate_file_transfer(
                    "192.168.1.10", 4705, str(directory)
                )
            with self.assertRaisesRegex(ValueError, "端口"):
                files_service.validate_file_transfer("192.168.1.10", 0, str(source))
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_supports_multiple_targets(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "multi-target"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "payload.bin"
            payload = b"multi-mode-payload"
            source.write_bytes(payload)
            reported = []
            sent_hosts = []

            def fake_send(
                packets, target, port, loops, interval, report=None, cancel_event=None
            ):
                sent_hosts.append(target)
                command = (
                    bytes(packets[0][constants.COMMAND_OFFSET :])
                    .decode("utf-16le")
                    .split("\x00", 1)[0]
                )
                bootstrap_url = command.split('-o "%TEMP%\\jyt.cmd" "', 1)[1].split(
                    '"', 1
                )[0]
                with urllib.request.urlopen(bootstrap_url, timeout=5) as response:
                    script = response.read().decode("utf-8-sig")
                file_url = script.split(
                    'curl.exe -fsSL --noproxy "*" --retry 2 -o "%PART%" "', 1
                )[1].split('"', 1)[0]
                with urllib.request.urlopen(file_url, timeout=5) as response:
                    self.assertEqual(response.read(), payload)
                return 1

            with patch.object(files_service, "send", side_effect=fake_send):
                result = files_service.transfer_file(
                    "192.168.1.1-3",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=5,
                    report=reported.append,
                )
            self.assertEqual(sent_hosts, ["192.168.1.1", "192.168.1.2", "192.168.1.3"])
            self.assertEqual(result["targets"], sent_hosts)
            self.assertEqual(result["transferred"], sent_hosts)
            self.assertIsNone(result["port"])
            self.assertTrue(any("全部 3 个目标" in message for message in reported))
            self.assertTrue(
                any("目标 2/3（192.168.1.2）" in message for message in reported)
            )
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_continues_after_one_target_fails(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "multi-failure"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "payload.bin"
            source.write_bytes(b"partial-payload")
            requested = []

            def fake_send(
                packets, target, port, loops, interval, report=None, cancel_event=None
            ):
                if target.endswith(".1"):
                    return 1
                requested.append(target)
                command = (
                    bytes(packets[0][constants.COMMAND_OFFSET :])
                    .decode("utf-16le")
                    .split("\x00", 1)[0]
                )
                bootstrap_url = command.split('-o "%TEMP%\\jyt.cmd" "', 1)[1].split(
                    '"', 1
                )[0]
                with urllib.request.urlopen(bootstrap_url, timeout=5) as response:
                    script = response.read().decode("utf-8-sig")
                file_url = script.split(
                    'curl.exe -fsSL --noproxy "*" --retry 2 -o "%PART%" "', 1
                )[1].split('"', 1)[0]
                with urllib.request.urlopen(file_url, timeout=5) as response:
                    self.assertEqual(response.read(), b"partial-payload")
                return 1

            with (
                patch.object(files_service, "send", side_effect=fake_send),
                self.assertRaisesRegex(RuntimeError, "完成 1/2 个目标") as failure,
            ):
                files_service.transfer_file(
                    "192.168.1.1-2",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=0.2,
                    attempts=1,
                    retry_delay=0,
                )
            self.assertIn("192.168.1.1", str(failure.exception))
            self.assertEqual(requested, ["192.168.1.2"])
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_collect_transfer_items_expands_folders(self):
        directory = self.test_root / "collect"
        shutil.rmtree(directory, ignore_errors=True)
        (directory / "包" / "子目录").mkdir(parents=True)
        try:
            (directory / "包" / "a.txt").write_text("a", encoding="utf-8")
            (directory / "包" / "子目录" / "b.bin").write_bytes(b"bb")
            (directory / "单.txt").write_text("c", encoding="utf-8")
            items = files_service.collect_transfer_items(
                [directory / "包", directory / "单.txt", directory / "包" / "a.txt"]
            )
            relatives = [relative for _, relative, _ in items]
            self.assertEqual(relatives, ["包/a.txt", "包/子目录/b.bin", "单.txt"])
            self.assertEqual([size for _, _, size in items], [1, 2, 1])
            with self.assertRaisesRegex(ValueError, "文件夹中没有可传送的文件"):
                empty = directory / "空"
                empty.mkdir()
                files_service.collect_transfer_items([empty])
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_bootstrap_script_restores_folder_structure(self):
        script = files_service.build_items_bootstrap_script(
            [("素材/说明.txt", 3), ("素材/第二章/示例.docx", 5)],
            ["http://192.168.1.10:1/f/t", "http://192.168.1.10:1/f/t/1"],
            desktop_dir=r"C:\Users\测试\Desktop",
        )
        self.assertIn('if not exist "%DESKTOP%\\素材" mkdir', script)
        self.assertIn('if not exist "%DESKTOP%\\素材\\第二章" mkdir', script)
        self.assertIn('set "TARGET=%DESKTOP%\\素材\\第二章\\示例.docx"', script)
        self.assertEqual(script.count("curl.exe"), 2)
        with self.assertRaisesRegex(ValueError, "不一致"):
            files_service.build_items_bootstrap_script([("a.txt", 1)], [])

    def test_file_transfer_serves_multiple_selected_files(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "multi-file"
        shutil.rmtree(directory, ignore_errors=True)
        (directory / "资料" / "子").mkdir(parents=True)
        try:
            (directory / "资料" / "a.txt").write_text("aaa", encoding="utf-8")
            (directory / "资料" / "子" / "b.txt").write_text("bbbb", encoding="utf-8")
            payloads = {}
            reported = []

            def fake_send(
                packets, target, port, loops, interval, report=None, cancel_event=None
            ):
                command = (
                    bytes(packets[0][constants.COMMAND_OFFSET :])
                    .decode("utf-16le")
                    .split("\x00", 1)[0]
                )
                bootstrap_url = command.split('-o "%TEMP%\\jyt.cmd" "', 1)[1].split(
                    '"', 1
                )[0]
                with urllib.request.urlopen(bootstrap_url, timeout=5) as response:
                    script = response.read().decode("utf-8-sig")
                for line in script.splitlines():
                    if not line.startswith("curl.exe"):
                        continue
                    file_url = line.split('-o "%PART%" "', 1)[1].rstrip('"')
                    with urllib.request.urlopen(file_url, timeout=5) as response:
                        payloads[file_url.rsplit("/", 1)[-1]] = response.read()
                return 1

            items = files_service.collect_transfer_items([directory / "资料"])
            with patch.object(files_service, "send", side_effect=fake_send):
                result = files_service.transfer_file(
                    "192.168.1.10",
                    4705,
                    None,
                    listen_ip="127.0.0.1",
                    timeout=5,
                    report=reported.append,
                    items=[(str(path), relative) for path, relative, _ in items],
                )
            self.assertEqual(sorted(payloads.values()), [b"aaa", b"bbbb"])
            self.assertEqual(result["file_count"], 2)
            self.assertEqual(result["files"], ["资料/a.txt", "资料/子/b.txt"])
            self.assertEqual(result["size"], 7)
            self.assertEqual(result["name"], "2 个文件")
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_command_and_bootstrap_script(self):
        command = files_service.build_transfer_command(
            "http://192.168.1.10:54321/b/token"
        )
        self.assertIn("cmd /c curl ", command)
        self.assertNotIn("powershell", command.lower())
        self.assertIn("http://192.168.1.10:54321/b/token", command)
        self.assertLessEqual(
            len(command.encode("utf-16le")) // 2, constants.COMMAND_MAX_BYTES // 2
        )
        with self.assertRaisesRegex(ValueError, "报文容量"):
            files_service.build_transfer_command("http://" + "a" * 400)
        script = files_service.build_bootstrap_script(
            "http://192.168.1.10:54321/f/token",
            "报告 100% O'Brien.txt",
            12,
            desktop_dir=r"C:\Users\测试\Desktop",
        )
        self.assertIn("curl.exe", script)
        self.assertIn("报告 100%% O'Brien.txt", script)
        self.assertIn('set "DESKTOP=C:\\Users\\测试\\Desktop"', script)
        self.assertIn('"%%~zA"=="12"', script)
        self.assertNotIn("powershell", script.lower())

    def test_file_transfer_retries_udp_command_until_target_requests_file(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "retry"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "payload.bin"
            source.write_bytes(b"retry-payload")
            sends = []
            server_holder = []

            def fake_send(
                packets, target, port, loops, interval, report=None, cancel_event=None
            ):
                sends.append((target, port))
                if len(sends) == 2:
                    server = server_holder[0]
                    with urllib.request.urlopen(
                        server.file_url("127.0.0.1"), timeout=5
                    ) as response:
                        self.assertEqual(response.read(), b"retry-payload")
                return 1

            original_init = files_service.FileTransferServer.__init__

            def capture_server(server, *args, **kwargs):
                original_init(server, *args, **kwargs)
                server_holder.append(server)

            with (
                patch.object(files_service, "send", side_effect=fake_send),
                patch.object(
                    files_service.FileTransferServer, "__init__", capture_server
                ),
            ):
                files_service.transfer_file(
                    "192.168.1.10",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=5,
                    attempts=3,
                    retry_delay=0.01,
                )
            self.assertEqual(len(sends), 2)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_timeout_reports_connection_stage(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "timeout-stage"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "payload.bin"
            source.write_bytes(b"data")
            with (
                patch.object(files_service, "send", return_value=1),
                self.assertRaisesRegex(RuntimeError, "目标未访问文件服务.*发送端 IP"),
            ):
                files_service.transfer_file(
                    "192.168.1.10",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=0.2,
                    attempts=1,
                )
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_uses_http_server_and_sends_command(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "server"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "payload.bin"
            payload = b"file-payload" * 100
            source.write_bytes(payload)
            reported = []
            desktop = directory / "desktop"
            desktop.mkdir()
            sent = []

            def fake_send(
                packets, target, port, loops, interval, report=None, cancel_event=None
            ):
                sent.append((packets, target, port, loops, interval))
                command = (
                    bytes(packets[0][constants.COMMAND_OFFSET :])
                    .decode("utf-16le")
                    .split("\x00", 1)[0]
                )
                bootstrap_url = command.split('-o "%TEMP%\\jyt.cmd" "', 1)[1].split(
                    '"', 1
                )[0]
                with urllib.request.urlopen(bootstrap_url, timeout=5) as response:
                    script = response.read().decode("utf-8-sig")
                file_url = script.split(
                    'curl.exe -fsSL --noproxy "*" --retry 2 -o "%PART%" "', 1
                )[1].split('"', 1)[0]
                with urllib.request.urlopen(file_url, timeout=5) as response:
                    self.assertEqual(response.read(), payload)
                return 1

            with patch.object(files_service, "send", side_effect=fake_send):
                result = files_service.transfer_file(
                    "192.168.1.10",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=5,
                    report=reported.append,
                    desktop_dir=str(desktop),
                )
            self.assertEqual(result["name"], "payload.bin")
            self.assertEqual(result["size"], len(payload))
            self.assertEqual(sent[0][1:], ("192.168.1.10", 4705, 1, 0))
            self.assertTrue(any("下载文件" in message for message in reported))
            self.assertTrue(any("目标已下载文件" in message for message in reported))
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_file_transfer_timeout_and_cancellation(self):
        self.network_guard.stop()
        self.addCleanup(self.network_guard.start)
        directory = self.test_root / "timeout"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            source = directory / "payload.bin"
            source.write_bytes(b"data")
            with (
                patch.object(files_service, "send", return_value=1),
                self.assertRaisesRegex(RuntimeError, "超时"),
            ):
                files_service.transfer_file(
                    "192.168.1.10",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=0.2,
                )
            stopped = Event()
            stopped.set()
            with self.assertRaisesRegex(RuntimeError, "操作已取消"):
                files_service.transfer_file(
                    "192.168.1.10",
                    4705,
                    str(source),
                    listen_ip="127.0.0.1",
                    timeout=1,
                    cancel_event=stopped,
                )
        finally:
            shutil.rmtree(directory, ignore_errors=True)
