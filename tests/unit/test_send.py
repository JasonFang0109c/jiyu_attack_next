"""按模块组织的离线回归测试。"""

import socket
from threading import Event
from unittest.mock import MagicMock, call, patch

import app.features.send.data as send_data
import app.features.send.service as send_service
import app.packets.codec as codec
import app.packets.constants as constants
import app.system.net.data as net_data
import app.system.net.reachability as reachability
import app.system.net.udp as udp
from tests.fixtures.offline import OfflineCase


class SendTests(OfflineCase):
    def test_options_validation(self):
        good = send_data.SendOptions("192.168.1.10", message="通知")
        send_service.validate_options(good)
        send_service.validate_options(send_data.SendOptions("192.168.1.10", extra="l"))
        bad_cases = [
            send_data.SendOptions("", message="通知"),
            send_data.SendOptions("bad-address", message="通知"),
            send_data.SendOptions("192.168.1.10"),
            send_data.SendOptions("192.168.1.10", port=0, message="通知"),
            send_data.SendOptions("192.168.1.10", loops=0, message="通知"),
            send_data.SendOptions("192.168.1.10", interval=-1, message="通知"),
            send_data.SendOptions("192.168.1.10", message="通知", extra="nc"),
        ]
        for options in bad_cases:
            with self.subTest(options=options), self.assertRaises(ValueError):
                send_service.validate_options(options)

    def test_packet_preparation(self):
        options = send_data.SendOptions(
            "192.168.1.10", message="a" * 449, command="whoami"
        )
        packets = send_service.prepare_packets(options)
        self.assertEqual(len(packets), 3)
        self.assertEqual(
            self.message_text(packets[0]) + self.message_text(packets[1]), "a" * 449
        )
        self.assertEqual(self.command_text(packets[2]), "whoami")

        options.extra = "s"
        packets = send_service.prepare_packets(options)
        self.assertIsNot(packets[-1], constants.basicCMD["-s"])

        packets = send_service.prepare_packets(
            send_data.SendOptions("192.168.1.10", extra="l")
        )
        self.assertEqual(len(packets), 1)
        self.assertEqual(self.command_text(packets[0]), constants.LOGOFF_COMMAND)

    def test_gui_send_uses_bytes_and_shared_transport(self):
        options = send_data.SendOptions(
            "192.168.1.10", message="a" * 449, command="whoami", loops=2, interval=0
        )
        first = MagicMock()
        second = MagicMock()
        packets = [
            bytes(codec.pkg_sendlist("-msg", chunk))
            for chunk in codec.split_message(options.message)
        ]
        packets.append(bytes(codec.pkg_sendlist("-c", options.command)))
        with (
            patch.object(udp, "get_ip", return_value=["模拟目标甲", "模拟目标乙"]),
            patch.object(socket, "socket", side_effect=[first, second]),
            patch.object(
                udp,
                "ping_hosts",
                return_value={"模拟目标甲": True, "模拟目标乙": True},
            ),
        ):
            outcome = send_service.execute_send_report(options)
        self.assertEqual(outcome.sent, 12)
        # 每个目标各自建连接，轮询两轮后各发一遍完整报文序列。
        for client, host in ((first, "模拟目标甲"), (second, "模拟目标乙")):
            self.assertEqual(client.connect.call_args, call((host, 4705)))
            self.assertEqual(
                client.send.call_args_list,
                [call(packet) for _ in range(2) for packet in packets],
            )
            client.close.assert_called_once()
        self.assertEqual(len(outcome.deliveries), 2)
        self.assertTrue(all(item.ok for item in outcome.deliveries))

    def test_cancellation_before_send_opens_no_socket(self):
        stopped = Event()
        stopped.set()
        options = send_data.SendOptions(
            "192.168.1.10", message="通知", cancel_event=stopped
        )
        with (
            patch.object(udp, "get_ip", return_value=["模拟目标"]),
            patch.object(socket, "socket") as factory,
            self.assertRaisesRegex(RuntimeError, "操作已取消"),
        ):
            send_service.execute_send(options)
        factory.assert_not_called()

    def test_cancellation_interrupts_long_interval(self):
        stopped = Event()
        options = send_data.SendOptions(
            "192.168.1.10", message="通知", loops=2, interval=3600, cancel_event=stopped
        )
        fake_socket = MagicMock()
        fake_socket.__enter__.return_value = fake_socket

        def report(message):
            if "轮已发送" in message:
                stopped.set()

        with (
            patch.object(udp, "get_ip", return_value=["模拟目标"]),
            patch.object(socket, "socket", return_value=fake_socket),
            self.assertRaisesRegex(RuntimeError, "操作已取消"),
        ):
            send_service.execute_send(options, report)
        fake_socket.send.assert_called_once()
        fake_socket.close.assert_called_once()

    def test_send_error_closes_socket(self):
        fake_socket = MagicMock()
        fake_socket.__enter__.return_value = fake_socket
        fake_socket.sendto.side_effect = OSError("模拟发送失败")
        with (
            patch.object(udp, "get_ip", return_value=["模拟目标"]),
            patch.object(socket, "socket", return_value=fake_socket),
            self.assertRaisesRegex(OSError, "模拟发送失败"),
        ):
            udp.send([[1, 2, 3]], "模拟目标")
        fake_socket.__exit__.assert_called_once()

    def test_send_tracked_marks_rejected_and_unreachable_targets(self):
        rejected = MagicMock()
        rejected.send.side_effect = ConnectionResetError("端口不可达")
        unreachable = MagicMock()
        unreachable.connect.side_effect = OSError("网络不可达")
        with (
            patch.object(udp, "get_ip", return_value=["甲", "乙"]),
            patch.object(socket, "socket", side_effect=[rejected, unreachable]),
        ):
            outcome = udp.send_tracked([[1, 2, 3]], "模拟目标", interval=0)
        self.assertEqual(outcome.sent, 0)
        self.assertEqual(
            [item.state for item in outcome.deliveries],
            [net_data.DeliveryState.REJECTED, net_data.DeliveryState.UNREACHABLE],
        )
        self.assertEqual(outcome.failed, outcome.deliveries)

    def test_send_tracked_confirms_silent_targets_with_echo(self):
        client = MagicMock()
        with (
            patch.object(udp, "get_ip", return_value=["10.0.0.5"]),
            patch.object(socket, "socket", return_value=client),
            patch.object(udp, "ping_hosts", return_value={"10.0.0.5": True}),
        ):
            outcome = udp.send_tracked([[1], [2]], "模拟目标", interval=0)
        self.assertEqual(outcome.sent, 2)
        self.assertTrue(outcome.deliveries[0].ok)
        self.assertEqual(outcome.failed, ())

    def test_reachability_ignores_addresses_it_cannot_probe(self):
        self.assertEqual(reachability.ping_hosts([]), {})
        self.assertEqual(reachability.ping_hosts(["not-an-address"]), {})

    def test_send_tracked_reports_targets_that_never_answer(self):
        client = MagicMock()
        with (
            patch.object(udp, "get_ip", return_value=["10.0.0.6"]),
            patch.object(socket, "socket", return_value=client),
            patch.object(udp, "ping_hosts", return_value={"10.0.0.6": False}),
        ):
            outcome = udp.send_tracked([[1]], "模拟目标", interval=0)
        self.assertEqual(
            [item.state for item in outcome.deliveries],
            [net_data.DeliveryState.NO_RESPONSE],
        )
        self.assertEqual(outcome.deliveries[0].state.text, "失败：目标未响应")
