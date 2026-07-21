"""knowledge_grounding_hook.py — Read-only query grounding from extracted hits to raw/vault evidence spans.

GroundingHook resolves extracted_hits to grounded evidence with confidence scoring.
It is strictly read-only: does not modify registry, DB, or files.

Usage:
    from knowledge_grounding_hook import GroundingHook
    hook = GroundingHook(db_path=Path("..."))
    grounded = hook.ground("query text", extracted_hits)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import signal
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GroundingTimeout(Exception):
    """Raised when grounding exceeds the configured timeout."""


class GroundingHook:
    """Read-only query grounding from extracted hits to raw/vault evidence spans.

    Resolves candidate JSON claims to grounded evidence spans from the registry.
    Falls back to raw/vault-only evidence on timeout or missing spans.
    """

    def __init__(self, db_path: Path, timeout_s: float = 2.0):
        self.db_path = db_path
        self.timeout_s = timeout_s

    def ground(self, query: str, extracted_hits: list[dict]) -> list[dict]:
        """Resolve extracted hits to raw/vault evidence spans.

        Args:
            query: The original search query (for context).
            extracted_hits: List of extracted hit dicts with doc_id and candidate_json_path.

        Returns:
            List of grounded claim dicts with claim_text, evidence_spans, confidence, source_layer.
        """
        t0 = time.monotonic()
        deadline = t0 + self.timeout_s
        grounded: list[dict] = []

        for hit in extracted_hits:
            if time.monotonic() > deadline:
                logger.warning("GroundingHook: timeout after %.1fs, returning %d grounded claims", time.monotonic() - t0, len(grounded))
                break

            doc_id = hit.get("doc_id", "")
            candidate_path = hit.get("candidate_json_path", "")
            candidate = self._load_candidate(candidate_path)
            if candidate is None:
                continue

            core_facts = candidate.get("core_facts", [])
            if not core_facts:
                core_facts = candidate.get("claims", [])

            for claim in core_facts:
                if time.monotonic() > deadline:
                    break
                claim_text = claim.get("text", "") if isinstance(claim, dict) else str(claim)
                evidence_refs = claim.get("evidence", []) if isinstance(claim, dict) else []
                span_ids = evidence_refs if isinstance(evidence_refs, list) else []

                spans = self._resolve_spans(span_ids, doc_id)

                if not spans:
                    grounded.append({
                        "claim_text": claim_text,
                        "evidence_spans": [],
                        "confidence": 0.5,
                        "source_layer": "semantic",
                    })
                else:
                    grounded.append({
                        "claim_text": claim_text,
                        "evidence_spans": spans,
                        "confidence": 0.9,
                        "source_layer": "raw",
                    })

        return grounded

    def _resolve_spans(self, span_ids: list[str], doc_id: str) -> list[dict]:
        """Look up span IDs in the registry; drop missing ones with warning."""
        if not span_ids:
            return []
        if not self.db_path.exists():
            return []

        resolved: list[dict] = []
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=3.0)
            conn.execute("PRAGMA query_only=1")
            conn.execute("PRAGMA busy_timeout=3000")
            conn.row_factory = sqlite3.Row
            for local_id in span_ids:
                try:
                    # Registry stores span_id as "doc_id:local_id"
                    full_span_id = f"{doc_id}:{local_id}" if ":" not in local_id else local_id
                    row = conn.execute(
                        "SELECT span_id, doc_id, text_sha256, start_line, end_line "
                        "FROM spans WHERE span_id = ?",
                        (full_span_id,),
                    ).fetchone()
                    if row:
                        resolved.append({
                            "span_id": row["span_id"],
                            "doc_id": row["doc_id"],
                            "content_hash": row["text_sha256"],
                            "line_range": [row["start_line"], row["end_line"]],
                        })
                    else:
                        logger.warning("GroundingHook: span %s not found in registry, dropping claim reference", full_span_id)
                except Exception:
                    logger.warning("GroundingHook: error looking up span %s", local_id)
            conn.close()
        except Exception as e:
            logger.warning("GroundingHook: DB error during span resolution: %s", e)
        return resolved

    def _load_candidate(self, path: str) -> dict | None:
        """Load candidate JSON file. Returns None on any failure."""
        if not path:
            return None
        p = Path(path)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            logger.warning("GroundingHook: failed to load candidate %s: %s", path, e)
            return None
