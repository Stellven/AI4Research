"""Synthesize per-chapter markdown into the final planned report."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from report_evidence import atomic_write_text, sanitize_public_markdown


def _strip_duplicate_title(markdown: str, title: str) -> str:
    lines = markdown.strip().splitlines()
    if not lines:
        return ""
    first = re.sub(r"^#+\s*", "", lines[0]).strip()
    if first == title.strip():
        return "\n".join(lines[1:]).strip()
    return markdown.strip()


def synthesize_report(report_ir: dict[str, Any], report_dir: Path, *, output_name: str = "report.synthesized.md") -> dict[str, Any]:
    """Merge passed chapter finals in IR order with manifest and executive summary."""
    chapters = [c for c in (report_ir.get("chapters") or []) if isinstance(c, dict)]
    manifest: list[dict[str, Any]] = []
    body_parts: list[str] = []
    for chapter in chapters:
        chapter_id = str(chapter.get("chapter_id") or "").strip()
        title = str(chapter.get("title") or chapter_id).strip()
        final_path = report_dir / "chapters" / f"{chapter_id}.final.md"
        if not final_path.exists():
            continue
        markdown = sanitize_public_markdown(final_path.read_text(encoding="utf-8"))
        content = _strip_duplicate_title(markdown, title)
        body_parts.append(f"## {title}\n\n{content}".strip())
        manifest.append({"chapter_ref": chapter_id, "title": title, "path": str(final_path)})
    title = str(report_ir.get("title") or "AI Influence YouTube Report").strip()
    summary = (
        "## Executive Summary\n\n"
        f"本报告按 {len(manifest)} 个章节逐章生成并合成。每章只使用对应证据包，"
        "证据不足的部分保留为观察项。"
    )
    manifest_block = "```synthesis_manifest\n" + json.dumps({
        "schema_version": "synthesis_manifest.v1",
        "report_id": report_ir.get("report_id"),
        "chapter_count": len(manifest),
        "chapters": manifest,
    }, ensure_ascii=False, indent=2) + "\n```"
    markdown = "\n\n".join([f"# {title}", manifest_block, summary, *body_parts]).strip() + "\n"
    out_path = report_dir / "synthesis" / output_name
    atomic_write_text(out_path, markdown)
    return {"path": str(out_path), "markdown": markdown, "manifest": manifest}
