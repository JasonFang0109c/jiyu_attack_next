"""文档链接校验:确保文档之间的相对链接与锚点都能真正打开。"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = [
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    *sorted((ROOT / "Docs").rglob("*.md")),
]

LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"#{1,6}\s+(.*)")

_heading_cache: dict[Path, set[str]] = {}


def anchor_of(heading):
    """按 GitHub 的规则把标题转成锚点:小写、去标点、空格改连字符。"""
    text = heading.strip().lower()
    text = re.sub(r"[`*_]", "", text)
    text = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", text)
    return text.replace(" ", "-").strip("-")


def anchors(path):
    """取出一个文档里的全部标题锚点,结果缓存避免重复解析。"""
    resolved = path.resolve()
    if resolved not in _heading_cache:
        found = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            match = HEADING.match(line)
            if match:
                found.add(anchor_of(match.group(1)))
        _heading_cache[resolved] = found
    return _heading_cache[resolved]


def relative_target(document, href):
    """把文档里的相对链接还原成实际路径,外部链接返回 None。"""
    if href.startswith(("http://", "https://", "mailto:")):
        return None
    target = href.partition("#")[0]
    if not target:
        return document
    return (document.parent / target).resolve()


class DocumentLinkTests(unittest.TestCase):
    def test_relative_links_point_to_existing_files(self):
        missing = []
        for document in DOCUMENTS:
            for href in LINK.findall(document.read_text(encoding="utf-8")):
                target = relative_target(document, href)
                if target is None or target.exists():
                    continue
                missing.append(f"{document.relative_to(ROOT)} -> {href}")
        self.assertEqual(missing, [], "以下相对链接指向的文件不存在")

    def test_anchor_links_resolve_to_a_heading(self):
        dangling = []
        for document in DOCUMENTS:
            for href in LINK.findall(document.read_text(encoding="utf-8")):
                if "#" not in href:
                    continue
                target = relative_target(document, href)
                if target is None:
                    continue
                if not target.exists():
                    continue
                anchor = href.partition("#")[2]
                if anchor not in anchors(target):
                    dangling.append(f"{document.relative_to(ROOT)} -> {href}")
        self.assertEqual(dangling, [], "以下链接的锚点没有对应标题")
