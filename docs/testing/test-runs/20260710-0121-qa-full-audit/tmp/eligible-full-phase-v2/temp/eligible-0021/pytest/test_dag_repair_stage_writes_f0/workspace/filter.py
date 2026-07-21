#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup


BLOCKED_TAGS = {"script", "iframe", "frame", "object", "embed"}


def sanitize(html: str) -> str:
    html = html.replace("\x00", "")
    html = re.sub(r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>", "", html, flags=re.I | re.S)
    soup = BeautifulSoup(html, "html.parser")
    for tag in list(soup.find_all(BLOCKED_TAGS)):
        tag.decompose()

    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            value = tag.attrs.get(attr)
            normalized = " ".join(value) if isinstance(value, list) else str(value)
            lowered_attr = attr.lower()
            lowered_value = normalized.lower().strip()
            if lowered_attr.startswith("on"):
                del tag.attrs[attr]
            elif any(marker in lowered_value for marker in ("javascript:", "vbscript:", "data:text/html")):
                del tag.attrs[attr]

    rendered = str(soup)
    rendered = re.sub(r"(?i)javascript:", "", rendered)
    rendered = re.sub(r"(?i)vbscript:", "", rendered)
    rendered = rendered.replace("<script", "&lt;script").replace("< script", "&lt; script")
    return rendered


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: filter.py <html-file>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    html = path.read_text(encoding="utf-8", errors="ignore")
    path.write_text(sanitize(html), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
