"""Knowledge-store path conventions and JSON persistence for the influence plane.

Every write goes under a *resolvable* knowledge root so tests never touch the
live tree. Resolution order:

1. explicit ``root`` argument
2. ``KNOWLEDGE_ROOT`` environment variable (via ``os.environ``)
3. ``~/Knowledge`` fallback (only used outside tests)

New data lives exclusively under ``<root>/extracted/<bucket>/`` — additive, never
inside the legacy ``_raw`` ingest tree. The collector is the only operator that
*reads* ``_raw`` outputs (read-only) via :func:`read_json`.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any

# Sub-dirs created under <root>/extracted/ — all additive, all removable.
EXTRACTED_BUCKETS = (
    "influencer_profiles",
    "statements",
    "thesis",
    "mapped_evidence_packets",
    "resonance_seeds",
    "topic_cards",
    "project_briefs",
)

# Legacy ingest locations the collector adapts (read-only).
RAW_DIGEST_SUBDIRS = {
    "x_backend": "_raw/ai-influence-daily-digest",
    "youtube_transcript": "_raw/youtube-influence-digest",
}


def resolve_root(root: str | os.PathLike[str] | None = None) -> pathlib.Path:
    """Resolve the knowledge root without ever hardcoding the live path."""
    if root:
        return pathlib.Path(root).expanduser()
    env = os.environ.get("KNOWLEDGE_ROOT")
    if env:
        return pathlib.Path(env).expanduser()
    return pathlib.Path(os.path.expanduser("~/Knowledge"))


def extracted_dir(bucket: str, root: str | os.PathLike[str] | None = None) -> pathlib.Path:
    if bucket not in EXTRACTED_BUCKETS:
        raise ValueError(f"unknown extracted bucket: {bucket!r}")
    return resolve_root(root) / "extracted" / bucket


def raw_dir(source: str, root: str | os.PathLike[str] | None = None) -> pathlib.Path:
    """Read-only path to a legacy digest's raw output tree."""
    if source not in RAW_DIGEST_SUBDIRS:
        raise ValueError(f"unknown raw source: {source!r}")
    return resolve_root(root) / RAW_DIGEST_SUBDIRS[source]


def write_json(path: str | os.PathLike[str], payload: dict[str, Any]) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def read_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def persist(bucket: str, obj_id: str, payload: dict[str, Any],
            root: str | os.PathLike[str] | None = None) -> pathlib.Path:
    """Persist one object into its extracted bucket as ``<obj_id>.json``."""
    target = extracted_dir(bucket, root) / f"{obj_id}.json"
    return write_json(target, payload)
