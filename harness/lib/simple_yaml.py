"""Small YAML subset loader used when PyYAML is unavailable.

This parser intentionally supports only the subset used by Solar Harness
registry and capability capsule manifests: nested mappings, block sequences,
inline empty containers, inline scalar lists, quoted strings, booleans, nulls,
and numbers. It is not a general YAML implementation.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any


class SimpleYAMLError(ValueError):
    """Raised when the fallback loader cannot parse the supported subset."""


_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def safe_load(text: str) -> Any:
    """Parse a restricted YAML subset.

    The function mirrors ``yaml.safe_load`` for the simple files used by the
    harness runtime. JSON is accepted as a fast path.
    """

    source = text or ""
    stripped = source.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except Exception:
        pass

    lines = _preprocess(source)
    if not lines:
        return None
    value, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        indent, content = lines[index]
        raise SimpleYAMLError(f"unexpected YAML content at indent {indent}: {content}")
    return value


def _preprocess(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        content = _strip_inline_comment(raw.rstrip())
        if not content.strip():
            continue
        indent = len(content) - len(content.lstrip(" "))
        lines.append((indent, content.strip()))
    return lines


def _strip_inline_comment(line: str) -> str:
    quote = ""
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index].rstrip()
    return line


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return None, index
    if lines[index][1].startswith("- "):
        return _parse_sequence(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_mapping(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        line_indent, content = lines[index]
        if line_indent < indent:
            break
        if line_indent > indent:
            break
        if content.startswith("- "):
            break
        key, raw_value = _split_key_value(content)
        if raw_value == "":
            value, index = _parse_nested_value(lines, index, line_indent)
        elif raw_value in {"|", ">"}:
            value, index = _parse_multiline_scalar(lines, index + 1, line_indent, fold=(raw_value == ">"))
        else:
            value = _parse_scalar(raw_value)
            index += 1
        result[key] = value
    return result, index


def _parse_sequence(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        line_indent, content = lines[index]
        if line_indent < indent:
            break
        if line_indent > indent:
            break
        if not content.startswith("- "):
            break
        item_text = content[2:].strip()
        if item_text == "":
            if index + 1 < len(lines) and lines[index + 1][0] > line_indent:
                item, index = _parse_block(lines, index + 1, lines[index + 1][0])
            else:
                item = None
                index += 1
            result.append(item)
            continue

        split = _try_split_key_value(item_text)
        if split is None:
            result.append(_parse_scalar(item_text))
            index += 1
            continue

        key, raw_value = split
        item: dict[str, Any] = {}
        if raw_value == "":
            value, index = _parse_nested_value(lines, index, line_indent)
        elif raw_value in {"|", ">"}:
            value, index = _parse_multiline_scalar(lines, index + 1, line_indent, fold=(raw_value == ">"))
        else:
            value = _parse_scalar(raw_value)
            index += 1
        item[key] = value

        if index < len(lines) and lines[index][0] > line_indent:
            nested, index = _parse_block(lines, index, lines[index][0])
            if isinstance(nested, dict):
                item.update(nested)
            else:
                item.setdefault("items", nested)
        result.append(item)
    return result, index


def _parse_nested_value(lines: list[tuple[int, str]], index: int, line_indent: int) -> tuple[Any, int]:
    next_index = index + 1
    if next_index >= len(lines):
        return {}, next_index
    next_indent, next_content = lines[next_index]
    if next_indent > line_indent or next_content.startswith("- "):
        return _parse_block(lines, next_index, next_indent)
    return {}, next_index


def _parse_multiline_scalar(
    lines: list[tuple[int, str]],
    index: int,
    parent_indent: int,
    *,
    fold: bool,
) -> tuple[str, int]:
    parts: list[str] = []
    while index < len(lines):
        line_indent, content = lines[index]
        if line_indent <= parent_indent:
            break
        parts.append(content)
        index += 1
    return (" ".join(parts) if fold else "\n".join(parts)), index


def _split_key_value(text: str) -> tuple[str, str]:
    split = _try_split_key_value(text)
    if split is None:
        raise SimpleYAMLError(f"expected YAML mapping entry: {text}")
    return split


def _try_split_key_value(text: str) -> tuple[str, str] | None:
    quote = ""
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char != ":":
            continue
        key = text[:index].strip()
        if not key or not _KEY_RE.match(key):
            return None
        remainder = text[index + 1 :]
        if remainder and not remainder[0].isspace():
            return None
        return key, remainder.strip()
    return None


def _parse_scalar(value: str) -> Any:
    if value == "[]":
        return []
    if value == "{}":
        return {}
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in _split_inline_list(inner)]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        try:
            return ast.literal_eval(value)
        except Exception:
            return value[1:-1]
    if re.fullmatch(r"[-+]?\d+", value):
        try:
            return int(value)
        except Exception:
            pass
    if re.fullmatch(r"[-+]?\d+\.\d+", value):
        try:
            return float(value)
        except Exception:
            pass
    return value


def _split_inline_list(value: str) -> list[str]:
    items: list[str] = []
    start = 0
    quote = ""
    escaped = False
    depth = 0
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char in "[{":
            depth += 1
            continue
        if char in "]}":
            depth -= 1
            continue
        if char == "," and depth == 0:
            items.append(value[start:index])
            start = index + 1
    items.append(value[start:])
    return items
