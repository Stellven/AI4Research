"""Reader-facing evidence map compiler."""

from __future__ import annotations

from typing import Any


FORBIDDEN_SOURCE_FIELDS = {"video_id", "V00x", "raw_refs", "pipeline_fields", "transcript_status", "processing_log"}


def build_evidence_map(items: list[dict[str, Any]]) -> dict[str, Any]:
    entries = []
    for item in items:
        if item.get("transcript_grade") == "T3":
            continue
        entries.append({
            "evidence_ref": item["evidence_ref"],
            "channel": item["channel"],
            "title": item["title"],
            "published_at": item["published_at"],
            "transcript_grade": item["transcript_grade"],
            "citation_span": item.get("citation_span", ""),
            "group_type": item.get("group_type", "other"),
        })
    return {"schema_version": "evidence_map.v1", "entries": entries}


def assert_reader_safe_mapping(entry: dict[str, Any]) -> None:
    leaked = FORBIDDEN_SOURCE_FIELDS & set(entry)
    if leaked:
        raise ValueError(f"reader-facing source mapping leaks internal fields: {sorted(leaked)}")
