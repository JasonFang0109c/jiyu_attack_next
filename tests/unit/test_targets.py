"""按模块组织的离线回归测试。"""

import app.system.net.targets as targets
from tests.fixtures.offline import OfflineCase


class TargetsTests(OfflineCase):
    def test_ip_formats(self):
        self.assertEqual(targets.get_ip("192.168.1.10"), ["192.168.1.10"])
        self.assertEqual(
            targets.get_ip("192.168.1.1-3")[:3],
            ["192.168.1.1", "192.168.1.2", "192.168.1.3"],
        )
        network = targets.get_ip("192.168.1.0/24")
        self.assertEqual(len(network), 254)
        self.assertEqual(network[0], "192.168.1.1")
        self.assertEqual(network[-1], "192.168.1.254")

    def test_target_count_matches_expansion(self):
        for value in ["192.168.1.10", "192.168.1.1-3", "192.168.1.0/24", "10.0.0.5/24"]:
            with self.subTest(value=value):
                self.assertEqual(
                    targets.count_targets(value), len(targets.get_ip(value))
                )
        for value in [
            "",
            "bad-address",
            "192.168.1.10-1",
            "192.168.1.1-255",
            "10.0.0.0/16",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                targets.count_targets(value)

    def test_invalid_reverse_range_is_rejected(self):
        for value in ["192.168.1.10-1", "192.168.1.0-10", "192.168.1.1-255"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                targets.get_ip(value)
