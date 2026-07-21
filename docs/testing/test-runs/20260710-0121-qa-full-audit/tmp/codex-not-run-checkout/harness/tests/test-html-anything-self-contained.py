from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from html_anything_adapter import render, verify_self_contained


def test_verify_self_contained_true() -> None:
    html = render("# test", "prd", title="T", hero_title="T", lede="L")
    assert verify_self_contained(html)
    assert 'content="html-anything"' in html


def test_verify_self_contained_rejects_external_link() -> None:
    html = '<!doctype html><html><head><link rel="stylesheet" href="https://example.com/x.css"></head><body></body></html>'
    assert verify_self_contained(html) is False
