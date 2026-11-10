"""配置解析与写回测试。"""

import shutil
import unittest
from pathlib import Path

import app.shared.config as config


class ConfigFileTests(unittest.TestCase):
    """JSON with comments 配置文件的解析与写回。"""

    def setUp(self):
        self.root = Path("build") / "test-config-temp"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    def test_comments_are_stripped_outside_strings(self):
        text = """
        {
          // 行注释
          "url": "http://example.invalid/a//b",
          /* 块注释 */
          "note": "含有 /* 的原样文本",
        }
        """
        data = config.loads(text)
        self.assertEqual(data["url"], "http://example.invalid/a//b")
        self.assertEqual(data["note"], "含有 /* 的原样文本")

    def test_missing_comments_and_empty_text_parse_as_empty_object(self):
        self.assertEqual(config.loads(""), {})
        self.assertEqual(config.loads("   "), {})
        self.assertEqual(config.loads('{"a": 1}'), {"a": 1})

    def test_invalid_json_raises_value_error(self):
        with self.assertRaises(ValueError):
            config.loads('{"a": }')
        with self.assertRaises(ValueError):
            config.loads("[1, 2, 3]")

    def test_write_adds_header_and_key_comments(self):
        path = self.root / "settings.json"
        config.write(
            path,
            {"core": {"device_aliases": {}}, "gui": {"window": {"mica_enabled": True}}},
            {"gui/window/mica_enabled": ("背景模糊开关",)},
        )
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("// JiYu Attack Next 配置文件"))
        self.assertIn("// 背景模糊开关", text)
        self.assertTrue(text.endswith("}" + chr(10)))
        self.assertEqual(
            config.loads(text),
            {"core": {"device_aliases": {}}, "gui": {"window": {"mica_enabled": True}}},
        )

    def test_read_returns_empty_object_for_missing_file(self):
        self.assertEqual(config.read(self.root / "absent.json"), {})

    def test_write_leaves_no_temp_file(self):
        path = self.root / "settings.json"
        config.write(path, {"core": {}}, None)
        self.assertEqual(
            sorted(item.name for item in self.root.iterdir()), ["settings.json"]
        )
