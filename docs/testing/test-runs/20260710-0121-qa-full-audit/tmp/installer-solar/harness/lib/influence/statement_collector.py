"""L1 StatementCollector — adapt existing digest outputs into canonical Statements.

This is the *only* influence module that knows about the legacy scripts. It does
NOT re-implement collection; it adapts the raw outputs already produced by:

- ``scripts/ai_influence_digest.py``      -> source ``x_backend``
- ``scripts/youtube_influence_digest.py`` -> source ``youtube_transcript``

Adaptation is read-only: raw records are read (via ``read_text``-backed
``store.read_json``) from the legacy ``_raw`` tree and mapped onto ``Statement``.
New platforms (Bluesky, HN, blog) are out of MVP scope and gated off in
``source_adapters.yaml``.
"""
from __future__ import annotations

import pathlib
from typing import Any, Iterable

from .models import Author, QualityFlags, Statement
from .store import raw_dir, read_json


def _statement_from_raw(raw: dict[str, Any], source: str, index: int) -> Statement:
    author = raw.get("author", {})
    sid = raw.get("statement_id") or raw.get("id") or f"stmt-{source}-{index:04d}"
    return Statement(
        statement_id=sid,
        source=source,
        text=raw.get("text", raw.get("content", "")),
        author=Author(
            platform=author.get("platform", "x" if source == "x_backend" else "youtube"),
            handle=author.get("handle", raw.get("handle", "")),
            display_name=author.get("display_name", raw.get("display_name", "")),
        ),
        timestamp=raw.get("timestamp", raw.get("published_at", "")),
        source_url=raw.get("source_url", raw.get("url", "")),
        raw_metadata=dict(raw.get("raw_metadata", raw.get("metrics", {}))),
    )


def collect_statements(raw_records: Iterable[dict[str, Any]], source: str) -> list[Statement]:
    """Map an iterable of raw digest records onto canonical Statement objects."""
    return [_statement_from_raw(raw, source, i) for i, raw in enumerate(raw_records)]


def collect_from_dir(source: str, root: str | pathlib.Path | None = None) -> list[Statement]:
    """Read every ``*.json`` raw record from a legacy digest's output tree.

    Read-only: never writes into ``_raw``. Returns ``[]`` if the dir is absent so
    the pipeline degrades gracefully when a digest has not run yet.
    """
    base = raw_dir(source, root)
    if not base.exists():
        return []
    statements: list[Statement] = []
    for i, jf in enumerate(sorted(base.rglob("*.json"))):
        statements.append(_statement_from_raw(read_json(jf), source, i))
    return statements
