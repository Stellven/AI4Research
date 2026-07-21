"""Render-safe source mapping helpers."""

from __future__ import annotations

from html import escape
from typing import Any

from .evidence_map import assert_reader_safe_mapping


def source_mapping_from_evidence(entry: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "schema_version": "source_mapping.v1",
        "channel": entry["channel"],
        "title": entry["title"],
        "published_at": entry["published_at"],
        "trust_level": "core" if entry.get("transcript_grade") in {"T0", "T1"} else "weak",
        "cited_segment_snippet": entry.get("citation_span", ""),
    }
    assert_reader_safe_mapping(mapping)
    return mapping


def render_source_mapping_markdown(entry: dict[str, Any]) -> str:
    mapping = source_mapping_from_evidence(entry)
    return (
        f"- 来源：{mapping['channel']}｜{mapping['title']}｜{mapping['published_at']}｜"
        f"{mapping['trust_level']}\\n"
        f"  引用片段：{mapping['cited_segment_snippet']}"
    )


def render_source_mapping_html(entry: dict[str, Any]) -> str:
    mapping = source_mapping_from_evidence(entry)
    return (
        '<div class="source-card">'
        f"<strong>{escape(mapping['channel'])}</strong>"
        f"<span>{escape(mapping['title'])}</span>"
        f"<time>{escape(mapping['published_at'])}</time>"
        f"<em>{escape(mapping['trust_level'])}</em>"
        f"<blockquote>{escape(mapping['cited_segment_snippet'])}</blockquote>"
        "</div>"
    )
