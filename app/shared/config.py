"""JSON with comments 配置文件的解析与生成。

配置文件按 VS Code 的 ``jsonc`` 习惯书写：允许 ``//`` 与 ``/* */`` 注释，
也允许对象和数组末尾多一个逗号。注释只在解析前剥离，不参与数据本身。
"""

import json
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile

HEADER = (
    "// JiYu Attack Next 配置文件（JSON with comments）",
    "// 允许 // 与 /* */ 注释和尾逗号；文件由程序重写，手写的注释在下次保存后丢失。",
)


def _string_end(text, start):
    """返回从 ``start`` 处引号开始的字符串结束位置（结束引号之后）。"""
    index = start + 1
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == '"':
            return index + 1
        index += 1
    return length


def strip_comments(text):
    """去掉注释，字符串内部的 ``//`` 与 ``/* */`` 原样保留。

    Args:
        text: 带注释的 JSON 文本。

    Returns:
        str: 仅含数据与空白的文本，保留注释原有的换行与位置。

    Raises:
        ValueError: 块注释未闭合。
    """
    pieces = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == '"':
            end = _string_end(text, index)
            pieces.append(text[index:end])
            index = end
            continue
        if text.startswith("//", index):
            end = index + 2
            while end < length and text[end] not in "\r\n":
                end += 1
            pieces.append(" " * (end - index))
            index = end
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("配置文件包含未闭合的块注释")
            end += 2
            # 注释是空白而非空串，避免把 1/**/2 拼成合法的 12。
            pieces.append(
                "".join(char if char in "\r\n" else " " for char in text[index:end])
            )
            index = end
            continue
        pieces.append(char)
        index += 1
    return "".join(pieces)


def strip_trailing_commas(text):
    """去掉对象与数组末尾多余的逗号，字符串内容原样保留。

    用逐字符扫描而不是正则替换：正则无法区分字符串里的 ``,}`` 与真正的尾逗号，
    会把 ``"a,}"`` 这类值悄悄改掉。

    Args:
        text: 已去掉注释的 JSON 文本。

    Returns:
        str: 去掉尾逗号的文本。
    """
    pieces = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == '"':
            end = _string_end(text, index)
            pieces.append(text[index:end])
            index = end
            continue
        if char == ",":
            look = index + 1
            while look < length and text[look] in " \t\r\n":
                look += 1
            if look < length and text[look] in "}]":
                index += 1
                continue
        pieces.append(char)
        index += 1
    return "".join(pieces)


def loads(text):
    """解析带注释的 JSON 文本，空内容视为空对象。

    Args:
        text: 配置文件全文。

    Returns:
        dict: 顶层配置对象。

    Raises:
        ValueError: 内容不是合法的 JSON 对象。
    """
    cleaned = strip_comments(text or "")
    if not cleaned.strip():
        return {}
    cleaned = strip_trailing_commas(cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ValueError("配置文件不是合法的 JSON：%s" % error) from error
    if not isinstance(data, dict):
        raise ValueError("配置文件顶层必须是 JSON 对象")
    return data


def _emit_mapping(mapping, indent, lines, comments, path):
    """把一层映射写成带注释的文本行，``path`` 用斜杠拼接键路径。"""
    pad = "  " * indent
    items = list(mapping.items())
    for position, (key, value) in enumerate(items):
        key_path = "%s/%s" % (path, key) if path else str(key)
        for note in comments.get(key_path, ()):
            lines.append("%s// %s" % (pad, note))
        head = "%s%s: " % (pad, json.dumps(key, ensure_ascii=False))
        last = position == len(items) - 1
        if isinstance(value, dict) and value:
            lines.append(head + "{")
            _emit_mapping(value, indent + 1, lines, comments, key_path)
            lines.append("%s}%s" % (pad, "" if last else ","))
            continue
        lines.append(
            head + json.dumps(value, ensure_ascii=False) + ("" if last else ",")
        )


def dumps(data, comments=None):
    """生成带注释的配置文本，键顺序沿用 ``data`` 的插入顺序。

    Args:
        data: 顶层配置对象。
        comments: 键路径到注释行的映射，键路径用 ``/`` 分隔。

    Returns:
        str: 以换行结尾的配置文件全文。
    """
    lines = list(HEADER)
    lines.append("{")
    _emit_mapping(data, 1, lines, comments or {}, "")
    lines.append("}")
    return "\n".join(lines) + "\n"


def read(path):
    """读取配置文件；文件不存在时返回空对象。

    Args:
        path: 配置文件路径。

    Returns:
        dict: 顶层配置对象。

    Raises:
        OSError: 文件存在但无法读取。
        ValueError: 内容格式非法。
    """
    target = Path(path)
    if not target.exists():
        return {}
    return loads(target.read_text(encoding="utf-8-sig"))


def write(path, data, comments=None):
    """通过同目录下的独立临时文件替换配置，失败时清理本次临时文件。

    Args:
        path: 配置文件路径。
        data: 顶层配置对象。
        comments: 键路径到注释行的映射。

    Raises:
        OSError: 目录不可写或替换失败。
        TypeError: 数据包含不支持 JSON 序列化的值。
        UnicodeEncodeError: 文本无法编码为 UTF-8。
    """
    text = dumps(data, comments)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temp_path = Path(temporary.name)
            temporary.write(text)
        # Windows 替换前需要先关闭句柄，独立文件名避免并发保存互相覆盖。
        temp_path.replace(target)
    finally:
        if temp_path is not None:
            with suppress(OSError):
                temp_path.unlink(missing_ok=True)
