"""Report rendering seams with inline SVG output."""

from __future__ import annotations

from html import escape
from typing import Any

from .source_mapping import render_source_mapping_html


def render_platform_svg(title: str = "AI Influence YouTube Report Flow") -> str:
    safe_title = escape(title)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 220" role="img" aria-label="{safe_title}">
  <defs>
    <linearGradient id="g" x1="0" x2="1">
      <stop offset="0%" stop-color="#0f766e"/>
      <stop offset="100%" stop-color="#2563eb"/>
    </linearGradient>
  </defs>
  <rect width="840" height="220" rx="24" fill="#f8fafc"/>
  <text x="40" y="44" font-family="Georgia,serif" font-size="24" fill="#0f172a">{safe_title}</text>
  <g font-family="Verdana,sans-serif" font-size="14" fill="#0f172a">
    <rect x="40" y="78" width="130" height="54" rx="14" fill="#ccfbf1"/><text x="65" y="111">Transcript Gate</text>
    <rect x="205" y="78" width="130" height="54" rx="14" fill="#dbeafe"/><text x="237" y="111">Grouping</text>
    <rect x="370" y="78" width="130" height="54" rx="14" fill="#ede9fe"/><text x="398" y="111">ChatGPT Plan</text>
    <rect x="535" y="78" width="130" height="54" rx="14" fill="#fef3c7"/><text x="564" y="111">Chapters</text>
    <rect x="700" y="78" width="100" height="54" rx="14" fill="#dcfce7"/><text x="725" y="111">Archive</text>
  </g>
  <path d="M175 105h25M340 105h25M505 105h25M670 105h25" stroke="url(#g)" stroke-width="4" stroke-linecap="round"/>
</svg>"""


def render_report_html(markdown: str, evidence_pack: dict[str, Any], report_meta: dict[str, Any]) -> str:
    source_cards = "\n".join(render_source_mapping_html(entry) for entry in evidence_pack.get("entries", []))
    return f"""<!doctype html>
<html lang="zh">
<head><meta charset="utf-8"><title>{escape(str(report_meta.get('title') or 'AI Influence Report'))}</title></head>
<body>
{render_platform_svg(str(report_meta.get('title') or 'AI Influence Report'))}
<main>{escape(markdown)}</main>
<section class="sources">{source_cards}</section>
</body>
</html>"""
