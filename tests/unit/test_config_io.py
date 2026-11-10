"""配置解析边界与原子写入的离线回归测试。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.shared import config


class ConfigCommentTests(unittest.TestCase):
    def test_comments_do_not_join_separate_tokens(self):
        for text in ('{"n": 1/**/2}', '{"enabled": tr/**/ue}', '{"n": 1/*x*/.5}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                config.loads(text)

    def test_unterminated_block_comment_is_an_error(self):
        for text in ("/* unfinished", '{"n": 1} /* unfinished'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                config.loads(text)

    def test_line_comment_ends_at_each_json_newline(self):
        for newline in ("\n", "\r", "\r\n"):
            text = "// comment" + newline + '{"n": 1}'
            with self.subTest(newline=newline):
                self.assertEqual(config.loads(text), {"n": 1})

    def test_comments_preserve_error_coordinates(self):
        text = '{\n/* first\n second */\n"n": nope\n}'
        with self.assertRaises(ValueError) as caught:
            config.loads(text)
        error = caught.exception.__cause__
        self.assertIsInstance(error, json.JSONDecodeError)
        self.assertEqual((error.lineno, error.colno), (4, 6))

    def test_valid_comments_and_string_literals_still_round_trip(self):
        data = {"text": chr(34) + " // /* */ ,}", "nested": {"values": [1, 2]}}
        self.assertEqual(config.loads(config.dumps(data)), data)
        self.assertEqual(config.loads('{/* note */"n": 1, // note\n}'), {"n": 1})
        self.assertEqual(config.loads("// only\r/* comment */"), {})


class ConfigWriteTests(unittest.TestCase):
    def setUp(self):
        build = Path("build")
        build.mkdir(exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=build, prefix="audit_cli_config_")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.target = self.root / "settings.json"
        self.target.write_text('{"old": true}\n', encoding="utf-8")

    def test_write_preserves_existing_sibling_temp_file(self):
        sibling = self.target.with_name(self.target.name + ".tmp")
        sibling.write_text("other writer data", encoding="utf-8")
        config.write(self.target, {"new": True})
        self.assertTrue(sibling.exists(), "另一个写入者的临时文件应保留")
        self.assertEqual(sibling.read_text(encoding="utf-8"), "other writer data")
        self.assertEqual(config.read(self.target), {"new": True})

    def test_interleaved_writes_have_independent_staging_files(self):
        replace = Path.replace
        staged = []

        def interleave(source, destination):
            staged.append(source)
            if len(staged) == 1:
                config.write(self.target, {"writer": "second"})
            return replace(source, destination)

        with patch.object(Path, "replace", interleave):
            config.write(self.target, {"writer": "first"})
        self.assertEqual(len(set(staged)), 2)
        self.assertEqual(config.read(self.target), {"writer": "first"})
        self.assertEqual(list(self.root.iterdir()), [self.target])

    def test_failed_replace_preserves_original_and_removes_own_temp(self):
        with (
            patch.object(Path, "replace", side_effect=OSError("replace blocked")),
            self.assertRaisesRegex(OSError, "replace blocked"),
        ):
            config.write(self.target, {"new": True})
        self.assertEqual(config.read(self.target), {"old": True})
        self.assertEqual(list(self.root.iterdir()), [self.target])

    def test_encoding_failure_preserves_original_and_removes_own_temp(self):
        with self.assertRaises(UnicodeEncodeError):
            config.write(self.target, {"text": "\ud800"})
        self.assertEqual(config.read(self.target), {"old": True})
        self.assertEqual(list(self.root.iterdir()), [self.target])

    def test_serialization_failure_preserves_existing_files(self):
        with self.assertRaises(TypeError):
            config.write(self.target, {"value": object()})
        self.assertEqual(config.read(self.target), {"old": True})
        self.assertEqual(list(self.root.iterdir()), [self.target])

    def test_write_creates_nested_parent_and_leaves_no_temp(self):
        target = self.root / "nested" / "settings.json"
        config.write(target, {"text": "配置内容"})
        self.assertEqual(config.read(target), {"text": "配置内容"})
        self.assertEqual(list(target.parent.iterdir()), [target])


if __name__ == "__main__":
    unittest.main()
