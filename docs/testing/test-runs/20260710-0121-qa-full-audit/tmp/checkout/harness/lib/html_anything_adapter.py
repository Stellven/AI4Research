#!/usr/bin/env python3
"""html-anything-backed HTML shell adapter for Solar human-facing artifacts.

This adapter pins Solar's default human-readable HTML surfaces to the
html-anything profile family while preserving Solar's single-file,
self-contained artifact guarantees.
"""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve()
HARNESS_CODE_DIR = HERE.parent.parent
PROFILE_DIR = HARNESS_CODE_DIR / "templates" / "html-anything-profiles"

UPSTREAM_REPO_URL = "https://github.com/nexu-io/html-anything"
UPSTREAM_PINNED_COMMIT = "145a40ebd79624bbd6a28ec379148a895896573c"
DEFAULT_UPSTREAM_CHECKOUT = Path.home() / ".solar" / "harness" / "vendor" / "html-anything-upstream"


class HtmlAnythingAdapterError(RuntimeError):
    """Raised when the adapter cannot satisfy a render request."""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _escape_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def render_markdown_body(text: str) -> str:
    if not text.strip():
        return '<p class="ha-muted">N/A</p>'
    blocks: list[str] = []
    buf: list[str] = []
    in_code = False
    code_lines: list[str] = []
    list_mode: str | None = None

    def flush_paragraph() -> None:
        nonlocal buf
        if buf:
            blocks.append(f"<p>{_escape_inline(' '.join(x.strip() for x in buf if x.strip()))}</p>")
            buf = []

    def close_list() -> None:
        nonlocal list_mode
        if list_mode:
            blocks.append(f"</{list_mode}>")
            list_mode = None

    for raw in text.strip().splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            if in_code:
                blocks.append(f"<pre>{html.escape(chr(10).join(code_lines))}</pre>")
                in_code = False
                code_lines = []
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            flush_paragraph()
            close_list()
            continue
        if stripped.startswith("- "):
            flush_paragraph()
            if list_mode != "ul":
                close_list()
                blocks.append("<ul>")
                list_mode = "ul"
            blocks.append(f"<li>{_escape_inline(stripped[2:])}</li>")
            continue
        if re.match(r"^\d+\.\s+", stripped):
            flush_paragraph()
            if list_mode != "ol":
                close_list()
                blocks.append("<ol>")
                list_mode = "ol"
            item = re.sub(r"^\d+\.\s+", "", stripped)
            blocks.append(f"<li>{_escape_inline(item)}</li>")
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = min(len(heading.group(1)) + 1, 4)
            blocks.append(f"<h{level}>{_escape_inline(heading.group(2))}</h{level}>")
            continue
        buf.append(stripped)
    flush_paragraph()
    close_list()
    if in_code:
        blocks.append(f"<pre>{html.escape(chr(10).join(code_lines))}</pre>")
    return "\n".join(blocks)


def _load_profile(profile: str) -> dict[str, Any]:
    path = PROFILE_DIR / f"{profile}.json"
    if not path.is_file():
        raise HtmlAnythingAdapterError(f"profile_missing:{path}")
    return _read_json(path)


def _theme_css(profile_cfg: dict[str, Any]) -> str:
    theme = profile_cfg.get("theme", {})
    colors = theme.get("colors", {})
    typography = theme.get("typography", {})
    layout = theme.get("layout", {})
    accent = colors.get("accent", "#1B365D")
    bg = colors.get("background", "#f5f4ed")
    surface = colors.get("surface", "#faf9f5")
    ink = colors.get("ink", "#1f1d18")
    muted = colors.get("muted", "#6b665b")
    rule = colors.get("rule", "#d9d5c8")
    badge = colors.get("badge_bg", "#efeee5")
    hero_size = typography.get("hero_size", "clamp(44px, 6vw, 84px)")
    mono = typography.get("mono", "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace")
    serif = typography.get("serif", "Georgia, Cambria, 'Times New Roman', serif")
    sans = typography.get("sans", "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
    max_w = layout.get("max_width", "1040px")
    toc_w = layout.get("toc_width", "260px")
    card_min = layout.get("card_min_height", "180px")
    return f"""
:root {{
  --ha-bg: {bg};
  --ha-surface: {surface};
  --ha-ink: {ink};
  --ha-muted: {muted};
  --ha-accent: {accent};
  --ha-rule: {rule};
  --ha-badge: {badge};
  --ha-serif: {serif};
  --ha-sans: {sans};
  --ha-mono: {mono};
  --ha-max: {max_w};
  --ha-toc: {toc_w};
  --ha-hero: {hero_size};
  --ha-card-min: {card_min};
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: var(--ha-bg); color: var(--ha-ink); }}
body {{
  font-family: var(--ha-sans);
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}}
.ha-wrap {{ max-width: var(--ha-max); margin: 0 auto; padding: 40px 32px 72px; }}
.ha-topline, .ha-footline {{
  display:flex; justify-content:space-between; gap:16px; align-items:center;
  border-bottom:1px solid var(--ha-rule); padding: 0 0 12px;
  font-family: var(--ha-mono); font-size: 11px; text-transform: uppercase; letter-spacing: .14em; color: var(--ha-muted);
}}
.ha-footline {{ border-bottom:none; border-top:1px solid var(--ha-rule); margin-top: 48px; padding-top: 16px; }}
.ha-hero {{ padding: 36px 0 28px; }}
.ha-kicker {{
  display:inline-flex; gap:10px; align-items:center; background: var(--ha-badge); color: var(--ha-accent);
  padding: 5px 12px; border-radius: 999px; font-family: var(--ha-mono); font-size: 11px; letter-spacing: .14em; text-transform: uppercase;
}}
.ha-title {{
  margin: 18px 0 0; font-family: var(--ha-serif); font-size: var(--ha-hero); line-height: 1.03; letter-spacing: -.03em; font-weight: 500;
}}
.ha-title em {{ color: var(--ha-accent); font-style: italic; }}
.ha-lede {{ max-width: 52rem; margin: 18px 0 0; color: #3a382f; font-size: 19px; }}
.ha-badges {{ display:flex; flex-wrap:wrap; gap:8px; margin-top: 18px; }}
.ha-badge {{
  display:inline-flex; align-items:center; gap:6px; border: 1px solid var(--ha-rule);
  padding: 6px 10px; border-radius: 999px; font-family: var(--ha-mono); font-size: 11px; color: var(--ha-muted);
}}
.ha-layout {{ display:grid; grid-template-columns: minmax(0, 1fr); gap: 24px; }}
@media (min-width: 1100px) {{
  .ha-layout {{ grid-template-columns: var(--ha-toc) minmax(0, 1fr); gap: 28px; }}
}}
.ha-toc {{
  position: sticky; top: 18px; align-self: start; border: 1px solid var(--ha-rule); background: var(--ha-surface);
  padding: 18px 18px 14px; border-radius: 18px;
}}
.ha-toc h2 {{ margin: 0 0 10px; font-size: 13px; font-family: var(--ha-mono); text-transform: uppercase; letter-spacing: .14em; color: var(--ha-muted); }}
.ha-toc ol {{ margin: 0; padding-left: 18px; }}
.ha-toc li {{ margin: 8px 0; }}
.ha-toc a {{ color: var(--ha-ink); text-decoration: none; }}
.ha-main section {{
  border-top: 1px solid var(--ha-rule); padding-top: 26px; margin-top: 26px;
}}
.ha-main h2 {{
  margin: 0 0 16px; font-family: var(--ha-serif); font-size: clamp(28px, 3vw, 42px); line-height: 1.06; letter-spacing: -.02em; font-weight: 500;
}}
.ha-main h3, .ha-main h4 {{ font-family: var(--ha-serif); letter-spacing: -.01em; }}
.ha-grid-2 {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 18px; }}
.ha-card {{
  border: 1px solid var(--ha-rule); background: var(--ha-surface); padding: 20px 20px 18px; min-height: var(--ha-card-min);
}}
.ha-card h3 {{ margin: 0 0 10px; font-size: 24px; }}
.ha-main p {{ margin: 0 0 14px; }}
.ha-main ul, .ha-main ol {{ margin: 0 0 16px 20px; }}
.ha-main li {{ margin: 6px 0; }}
.ha-main pre {{
  overflow:auto; background:#f0ede4; color:#2b2923; padding:16px 18px; border-radius: 14px; border:1px solid var(--ha-rule);
  font-family: var(--ha-mono); font-size: 12px; line-height: 1.55;
}}
.ha-main code {{
  font-family: var(--ha-mono); background:#ece7db; padding: 2px 6px; border-radius: 6px; font-size: .92em;
}}
.ha-main table {{ width:100%; border-collapse: collapse; background: var(--ha-surface); border:1px solid var(--ha-rule); }}
.ha-main th, .ha-main td {{ border-bottom:1px solid var(--ha-rule); padding: 12px 14px; vertical-align: top; text-align:left; font-size: 14px; }}
.ha-main th {{ font-family: var(--ha-mono); font-size: 11px; text-transform: uppercase; letter-spacing: .14em; color: var(--ha-muted); background: #f2efe6; }}
.ha-diagram {{
  white-space: pre-wrap; background: #171614; color: #f7f4eb; border-radius: 18px; padding: 18px 20px; font-family: var(--ha-mono); font-size: 12px; line-height: 1.7;
}}
.ha-muted {{ color: var(--ha-muted); }}
.ha-generator {{
  margin-top: 18px; font-family: var(--ha-mono); font-size: 11px; color: var(--ha-muted);
}}
"""


def _upstream_marker(profile_cfg: dict[str, Any]) -> str:
    source = profile_cfg.get("upstream", {})
    skill = source.get("skill", "N/A")
    rel = source.get("path", "N/A")
    checkout = os.environ.get("SOLAR_HTML_ANYTHING_UPSTREAM", str(DEFAULT_UPSTREAM_CHECKOUT))
    return (
        f"html-anything profile={html.escape(str(profile_cfg.get('id', 'unknown')))} "
        f"skill={html.escape(str(skill))} commit={html.escape(UPSTREAM_PINNED_COMMIT)} "
        f"repo={html.escape(UPSTREAM_REPO_URL)} checkout={html.escape(checkout)} path={html.escape(str(rel))}"
    )


def _normalize_badges(badges: list[str] | None) -> str:
    badges = badges or []
    if not badges:
        return ""
    chips = "".join(f'<span class="ha-badge">{html.escape(item)}</span>' for item in badges)
    return f'<div class="ha-badges">{chips}</div>'


def _ensure_self_contained(html_text: str) -> str:
    sanitized = re.sub(r'<script[^>]+src="https?://[^"]+"[^>]*>\s*</script>', "", html_text, flags=re.I)
    sanitized = re.sub(r'<link[^>]+href="https?://[^"]+"[^>]*>', "", sanitized, flags=re.I)
    sanitized = re.sub(r'@import\s+url\([^)]+\);?', "", sanitized, flags=re.I)
    return sanitized


def verify_self_contained(html_text: str) -> bool:
    lowered = html_text.lower()
    if "<link" in lowered and "rel=\"stylesheet\"" in lowered:
        return False
    if re.search(r'<script[^>]+\bsrc=["\']https?://', lowered):
        return False
    if re.search(r'<img[^>]+\bsrc=["\']https?://', lowered):
        return False
    if re.search(r'<source[^>]+\bsrc=["\']https?://', lowered):
        return False
    if re.search(r'<iframe[^>]+\bsrc=["\']https?://', lowered):
        return False
    if re.search(r'<link[^>]+\bhref=["\']https?://', lowered):
        return False
    return True


def render(
    markdown_text: str,
    profile: str,
    *,
    title: str = "",
    hero_title: str = "",
    lede: str = "",
    meta: str = "",
    body_html: str | None = None,
    toc_html: str = "",
    badges: list[str] | None = None,
    surface_label: str | None = None,
    topline_left: str | None = None,
    topline_center: str | None = None,
    topline_right: str | None = None,
    footer_left: str | None = None,
    footer_right: str | None = None,
    footer_tail: str | None = None,
    show_generator: bool = True,
    extra_css: str = "",
) -> str:
    """Render a self-contained html-anything-themed HTML page."""
    profile_cfg = _load_profile(profile)
    title = title or hero_title or profile_cfg.get("title", "Solar HTML Artifact")
    hero_title = hero_title or title
    lede = lede or profile_cfg.get("default_lede", "")
    body = body_html if body_html is not None else render_markdown_body(markdown_text)
    top_meta = meta or profile_cfg.get("meta", "")
    kicker = topline_left or profile_cfg.get("kicker", "HTML Anything")
    footer_left = footer_left or profile_cfg.get("footer_left", "Solar Harness")
    footer_right = footer_right or profile_cfg.get("footer_right", "Default HTML Renderer")
    footer_tail = footer_tail or profile_cfg.get("id", profile)
    generator = _upstream_marker(profile_cfg)
    css = _theme_css(profile_cfg)
    hero_surface_label = surface_label or profile_cfg.get("surface_label", profile)
    top_center = topline_center if topline_center is not None else top_meta or "Solar Harness"
    top_right = topline_right if topline_right is not None else "Apache-2.0"
    generator_html = f'<div class="ha-generator">{html.escape(generator)}</div>' if show_generator else ""
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="generator" content="html-anything solar adapter">
  <meta name="x-solar-renderer" content="html-anything">
  <meta name="x-html-anything-profile" content="{html.escape(profile)}">
  <style>
{css}
{extra_css}
  </style>
</head>
<body>
  <div class="ha-wrap">
    <header class="ha-topline">
      <span>{html.escape(kicker)}</span>
      <span>{html.escape(top_center)}</span>
      <span>{html.escape(top_right)}</span>
    </header>

    <section class="ha-hero">
      <div class="ha-kicker">{html.escape(hero_surface_label)}</div>
      <h1 class="ha-title">{hero_title}</h1>
      <p class="ha-lede">{html.escape(lede)}</p>
      {_normalize_badges(badges)}
      {generator_html}
    </section>

    <div class="ha-layout">
      {toc_html}
      <main class="ha-main">
        {body}
      </main>
    </div>

    <footer class="ha-footline">
      <span>{html.escape(footer_left)}</span>
      <span>{html.escape(footer_right)}</span>
      <span>{html.escape(footer_tail)}</span>
    </footer>
  </div>
</body>
</html>
"""
    final_html = _ensure_self_contained(page)
    if not verify_self_contained(final_html):
        raise HtmlAnythingAdapterError("self_contained_verification_failed")
    return final_html
