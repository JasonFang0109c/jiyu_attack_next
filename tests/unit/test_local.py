"""按模块组织的离线回归测试。"""

import socket
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.features.local.service as local_service
import app.system.net.local as local_net
from tests.fixtures.offline import OfflineCase


class LocalTests(OfflineCase):
    def test_local_ports_match_exact_pids_and_wildcard_addresses(self):
        tasks = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout='"StudentMain.exe","123"\n"other.exe","5123"\n',
        )
        ports = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout="UDP 0.0.0.0:4705 *:* 123\n"
            "UDP [::]:4705 *:* 123\n"
            "UDP 0.0.0.0:9999 *:* 5123\n",
        )
        with (
            patch.object(
                local_service, "run_windows_command", side_effect=[tasks, ports]
            ),
            patch.object(socket, "gethostbyname", return_value="192.168.50.22"),
        ):
            ip, result = local_service.local_ip_and_ports()
        self.assertEqual(ip, "192.168.50.22")
        self.assertEqual(result, ["4705"])

    def test_local_ip_and_ports_skips_unreachable_hostname_address(self):
        tasks = SimpleNamespace(returncode=0, stderr="", stdout="")
        with (
            patch.object(local_service, "run_windows_command", side_effect=[tasks]),
            patch.object(socket, "gethostbyname", return_value="198.18.0.3"),
            patch.object(
                local_service, "detect_local_ip", return_value="192.168.50.22"
            ) as detect,
        ):
            ip, result = local_service.local_ip_and_ports()
        detect.assert_called_once_with()
        self.assertEqual(ip, "192.168.50.22")
        self.assertEqual(result, [])

    def test_udp_port_owners_lists_other_processes_on_the_port(self):
        connections = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout="UDP 192.168.50.22:4705 *:* 17600\n"
            "UDP 0.0.0.0:4705 *:* 9001\n"
            "UDP 0.0.0.0:6536 *:* 9002\n",
        )
        tasks = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout='"StudentMain.exe","17600"\n"JiYuAttackNext.exe","9001"\n',
        )
        with patch.object(
            local_service,
            "run_windows_command",
            side_effect=[connections, tasks],
        ):
            owners = local_service.udp_port_owners(4705, exclude_pids=(9001,))
        self.assertEqual(
            owners,
            [
                {
                    "address": "192.168.50.22:4705",
                    "pid": 17600,
                    "name": "StudentMain.exe",
                }
            ],
        )

    def test_local_ip_detection_prefers_target_route(self):
        first = MagicMock()
        first.__enter__.return_value = first
        first.getsockname.return_value = ("10.0.0.20", 50000)
        with patch.object(socket, "socket", return_value=first):
            self.assertEqual(local_net.detect_local_ip("10.0.0.8"), "10.0.0.20")
        self.assertEqual(first.connect.call_args.args[0], ("10.0.0.8", 9))

    def test_local_ip_detection_ignores_tun_route_source(self):
        tun = MagicMock()
        tun.__enter__.return_value = tun
        tun.getsockname.return_value = ("198.18.0.0", 50000)
        with (
            patch.object(socket, "socket", return_value=tun),
            patch.object(
                socket,
                "getaddrinfo",
                return_value=[
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.0", 0)),
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.49.151.27", 0)),
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.22.16.1", 0)),
                ],
            ),
        ):
            self.assertEqual(local_net.detect_local_ip("10.49.131.30"), "10.49.151.27")
        self.assertFalse(local_service._is_usable_local_address("198.18.0.0"))
        self.assertFalse(
            local_service._is_usable_local_address("127.0.0.1", "192.168.1.10")
        )
        self.assertTrue(
            local_service._is_usable_local_address("127.0.0.1", "127.0.0.1")
        )
