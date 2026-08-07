"""Write provenance-complete source packs for grounded research.

The runtime agent may author the same wire format directly.  This helper gives
connectors, deterministic fixtures, and future provider integrations one safe
implementation of ``sources.jsonl`` + ``evidence.jsonl`` + ``extracts/``.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .hashing import content_hash
from .ids import evidence_id
from .sources.base import FetchResult


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
CANONICAL_SOURCE_TYPES = (
    "paper",
    "code",
    "official_doc",
    "benchmark",
    "dataset",
    "news",
    "company",
    "standard",
    "web",
    "blog",
    "other",
)
_SOURCE_TYPE_ALIASES = {
    "documentation": "official_doc",
    "docs": "official_doc",
    "official": "official_doc",
    "official_api": "official_doc",
    "official_docs": "official_doc",
    "official_pricing": "official_doc",
    "preprint": "paper",
    "research_paper": "paper",
    "repo": "code",
    "repository": "code",
}


def canonical_source_type(value: Any) -> str:
    normalized = str(value or "web").strip().lower().replace("-", "_") or "web"
    return _SOURCE_TYPE_ALIASES.get(normalized, normalized)


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_name(source_id: str) -> str:
    stem = _SAFE_NAME_RE.sub("_", source_id).strip("._-")[:80] or "source"
    suffix = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:12]
    return f"{stem}-{suffix}.md"


def write_source_pack(
    output_dir: Path | str,
    fetches: list[FetchResult],
    provider: str | None = None,
) -> dict[str, Any]:
    """Persist successful fetched documents without inventing missing data."""
    root = Path(output_dir).expanduser()
    extracts_dir = root / "extracts"
    extracts_dir.mkdir(parents=True, exist_ok=True)
    retrieved_at = _utc_now()

    source_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()
    skipped = 0

    for document in fetches:
        if document.fetch_status != "fetched" or not document.raw_text.strip():
            skipped += 1
            continue
        source_id = str(document.source_id or "").strip()
        if not source_id:
            raise ValueError("source pack document has no source_id")
        if source_id in seen_source_ids:
            raise ValueError(f"source pack duplicate source_id: {source_id}")
        if not str(document.title or "").strip():
            raise ValueError(f"source pack document has no title: {source_id}")
        if not str(document.source_url or "").strip():
            raise ValueError(f"source pack document has no source_url: {source_id}")
        provider_name = str(provider or document.connector_id or "").strip()
        if not provider_name:
            raise ValueError(f"source pack document has no provider: {source_id}")
        seen_source_ids.add(source_id)

        digest = content_hash(document.raw_text)
        source_type = canonical_source_type((document.metadata or {}).get("source_type"))
        extract_path = extracts_dir / _extract_name(source_id)
        extract_path.write_text(document.raw_text, encoding="utf-8")
        source_rows.append(
            {
                "id": source_id,
                "source_id": source_id,
                "source_type": source_type,
                "title": document.title,
                "url": document.source_url,
                "retrieved_at": retrieved_at,
                "content_sha256": digest,
                "extract_path": str(extract_path.relative_to(root)),
                "provider": provider_name,
                "query": str(document.query or ""),
                "response_status": document.response_status,
            }
        )
        ev_id = evidence_id(source_id, 0, len(document.raw_text), digest)
        evidence_rows.append(
            {
                "id": ev_id,
                "evidence_id": ev_id,
                "source_id": source_id,
                "source_type": source_type,
                "content": document.raw_text,
                "content_hash": digest,
                "span_start": 0,
                "span_end": len(document.raw_text),
            }
        )

    sources_path = root / "sources.jsonl"
    evidence_path = root / "evidence.jsonl"
    sources_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in source_rows),
        encoding="utf-8",
    )
    evidence_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in evidence_rows),
        encoding="utf-8",
    )
    return {
        "source_count": len(source_rows),
        "evidence_count": len(evidence_rows),
        "skipped": skipped,
        "sources_path": str(sources_path),
        "evidence_path": str(evidence_path),
        "extracts_dir": str(extracts_dir),
        "provider_evidence": [
            {
                "source_id": row["source_id"],
                "title": row["title"],
                "source_url": row["url"],
                "provider": row["provider"],
                "query": row["query"],
                "retrieved_at": row["retrieved_at"],
                "response_status": row["response_status"],
                "content_sha256": row["content_sha256"],
            }
            for row in source_rows
        ],
    }
