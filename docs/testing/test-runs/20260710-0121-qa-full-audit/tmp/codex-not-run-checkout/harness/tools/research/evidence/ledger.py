"""Evidence Ledger — write, read, and list EvidenceItem records.

Spec: sprint-20260513-solar-deepresearch-product-line-s02-architecture
      / deepresearch.schemas.md §4 (EvidenceItem)

Uses the `evidence_items` SQLite table defined in migrations/001_init.sql.

Column mapping between EvidenceItem dataclass and the table:

  EvidenceItem field    → evidence_items column
  ────────────────────   ────────────────────────
  evidence_id           → id
  source_id             → source_id
  span_text             → content
  content_hash          → content_hash
  span_start            → span_start
  span_end              → span_end
  evidence_type         → evidence_type (mapped)
  relevance_score       → confidence

Fields without a direct column (source_type, section_path, support_direction,
created_at, schema_version) are serialised as JSON appended after a NUL
separator in the content column.  When a metadata_json column is added via
a future migration, those fields will move out.
"""

from __future__ import annotations

import json
from typing import Optional

from .. import hashing, schemas
from ..storage import get_connection

# Map dataclass evidence_type → SQLite evidence_type enum.
_EVIDENCE_TYPE_MAP = {
    "direct_quote": "quoted",
    "paraphrase": "factual",
    "statistic": "statistical",
    "definition": "factual",
    "finding": "factual",
    "methodology": "factual",
    "result": "derived",
}

_NUL = "\x00"


def _row_to_evidence_item(row: "sqlite3.Row") -> schemas.EvidenceItem:
    """Convert a sqlite3.Row from evidence_items to an EvidenceItem."""
    content_raw: str = row["content"]
    span_text = content_raw
    meta: dict = {}

    if _NUL in content_raw:
        span_text, metadata_json = content_raw.split(_NUL, 1)
        try:
            meta = json.loads(metadata_json)
        except json.JSONDecodeError:
            pass

    return schemas.EvidenceItem(
        evidence_id=row["id"],
        source_id=row["source_id"],
        source_type=meta.get("source_type", "document"),
        content_hash=row["content_hash"],
        span_start=row["span_start"],
        span_end=row["span_end"],
        span_text=span_text,
        section_path=meta.get("section_path"),
        evidence_type=meta.get("evidence_type", "direct_quote"),
        relevance_score=row["confidence"],
        support_direction=meta.get("support_direction", "supporting"),
        created_at=meta.get("created_at", ""),
        schema_version=meta.get("schema_version", "v1"),
    )


def write_evidence(
    conn: "sqlite3.Connection",
    item: schemas.EvidenceItem,
    run_id: str,
) -> None:
    """Write an EvidenceItem to the evidence_items table.

    Args:
        conn: Active SQLite connection with the evidence_items table.
        item: A fully-validated EvidenceItem dataclass instance.
        run_id: The research run ID (required by FK constraint).

    Raises:
        ValueError: If content_hash or span bounds fail verification.
        sqlite3.IntegrityError: On FK violation or duplicate.
    """
    expected_hash = hashing.content_hash(item.span_text)
    if item.content_hash != expected_hash:
        raise ValueError(
            f"EvidenceItem.content_hash mismatch: "
            f"declared={item.content_hash[:12]}..., "
            f"computed={expected_hash[:12]}..."
        )

    if item.span_end - item.span_start != len(item.span_text):
        raise ValueError(
            f"span range ({item.span_end - item.span_start}) != "
            f"len(span_text) ({len(item.span_text)})"
        )

    sqlite_ev_type = _EVIDENCE_TYPE_MAP.get(item.evidence_type, "factual")

    extra = {
        "evidence_type": item.evidence_type,
        "source_type": item.source_type,
        "section_path": item.section_path,
        "support_direction": item.support_direction,
        "created_at": item.created_at,
        "schema_version": item.schema_version,
    }
    content_with_meta = item.span_text + _NUL + json.dumps(extra, ensure_ascii=False)

    conn.execute(
        """INSERT INTO evidence_items
               (id, run_id, source_id, content, evidence_type, confidence,
                span_start, span_end, content_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            item.evidence_id,
            run_id,
            item.source_id,
            content_with_meta,
            sqlite_ev_type,
            item.relevance_score,
            item.span_start,
            item.span_end,
            item.content_hash,
        ),
    )
    conn.commit()


def read_evidence(
    conn: "sqlite3.Connection",
    evidence_id: str,
) -> Optional[schemas.EvidenceItem]:
    """Read a single EvidenceItem by its evidence_id. Returns None if absent."""
    cur = conn.execute(
        "SELECT * FROM evidence_items WHERE id = ?", (evidence_id,)
    )
    row = cur.fetchone()
    if row is None:
        return None
    return _row_to_evidence_item(row)


def list_by_source(
    conn: "sqlite3.Connection",
    source_id: str,
) -> list[schemas.EvidenceItem]:
    """Return all EvidenceItems for a source_id, ordered by span_start."""
    cur = conn.execute(
        "SELECT * FROM evidence_items WHERE source_id = ? ORDER BY span_start",
        (source_id,),
    )
    return [_row_to_evidence_item(row) for row in cur.fetchall()]


def check_unsupported_claims(
    conn: "sqlite3.Connection",
    run_id: str,
    threshold: float = 0.05,
) -> dict:
    """Check for unsupported key claims in a research run.

    Returns dict with unsupported_rate and whether it exceeds threshold.
    """
    cur = conn.execute(
        "SELECT id FROM claims WHERE run_id = ?", (run_id,)
    )
    all_claims = [row["id"] for row in cur.fetchall()]

    if not all_claims:
        return {
            "total_claims": 0,
            "unsupported_count": 0,
            "unsupported_rate": 0.0,
            "unsupported_claim_ids": [],
            "exceeds_threshold": False,
        }

    cur = conn.execute(
        "SELECT DISTINCT claim_id FROM claim_evidence WHERE run_id = ?",
        (run_id,),
    )
    supported_ids = {row["claim_id"] for row in cur.fetchall()}

    unsupported = [cid for cid in all_claims if cid not in supported_ids]
    rate = len(unsupported) / len(all_claims)

    return {
        "total_claims": len(all_claims),
        "unsupported_count": len(unsupported),
        "unsupported_rate": rate,
        "unsupported_claim_ids": unsupported,
        "exceeds_threshold": rate > threshold,
    }
