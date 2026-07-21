"""Canonical ID generation for DeepResearch records.

Spec: S02 schemas.md — each model has a deterministic SHA-256-based ID
algorithm so the same logical record always produces the same identifier.

Canonical separator between parts is "|" (U+007C). All parts are coerced to
str before joining. The joined string is encoded UTF-8, SHA-256'd, and the
first 16 hex chars are used as the suffix (12 for ReportAST).
"""

from __future__ import annotations

import hashlib
import time
from typing import Iterable

SEPARATOR = "|"
SHORT_HEX_LEN = 16
AST_HEX_LEN = 12
CLAIM_HEX_LEN = 8


def make_id(*parts: object) -> str:
    """Return SHA-256 hex digest of canonical-joined parts.

    Joins parts with "|" and SHA-256s the UTF-8 encoded result. This is the
    primitive used by every domain-specific id helper below.

    Empty parts list returns the SHA-256 of the empty string (a stable,
    well-known value) rather than raising — caller is responsible for the
    semantic check of "did I forget to pass any inputs".
    """
    canonical = SEPARATOR.join(str(p) for p in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Domain-specific ID helpers — exact algorithms per S02 schemas.md
# ---------------------------------------------------------------------------


def connector_id(connector_type: str, unix_ts: int | None = None) -> str:
    """sc_{connector_type}_{unix_timestamp_hex}"""
    ts = unix_ts if unix_ts is not None else int(time.time())
    return f"sc_{connector_type}_{ts:x}"


def hit_id(connector_id_: str, query: str, rank: int) -> str:
    """hit_{sha256(connector_id|query|rank)[:16]}"""
    return f"hit_{make_id(connector_id_, query, rank)[:SHORT_HEX_LEN]}"


def doc_id(connector_id_: str, source_url: str | None, fetch_timestamp: str) -> str:
    """doc_{sha256(connector_id|source_url-or-internal|fetch_ts)[:16]}"""
    url_part = source_url if source_url else "internal"
    return f"doc_{make_id(connector_id_, url_part, fetch_timestamp)[:SHORT_HEX_LEN]}"


def evidence_id(source_id: str, span_start: int, span_end: int, content_hash_: str) -> str:
    """ev_{sha256(source_id|span_start|span_end|content_hash)[:16]}"""
    return f"ev_{make_id(source_id, span_start, span_end, content_hash_)[:SHORT_HEX_LEN]}"


def claim_id(counter: int, claim_text: str) -> str:
    """clm_{counter:04d}_{sha256(claim_text)[:8]}"""
    text_hash = hashlib.sha256(claim_text.encode("utf-8")).hexdigest()[:CLAIM_HEX_LEN]
    return f"clm_{counter:04d}_{text_hash}"


def link_id(claim_id_: str, evidence_id_: str) -> str:
    """cel_{sha256(claim_id|evidence_id)[:16]}"""
    return f"cel_{make_id(claim_id_, evidence_id_)[:SHORT_HEX_LEN]}"


def citation_id(section_path: str, span_start: int, span_end: int, evidence_id_: str) -> str:
    """cit_{sha256(section_path|span_start|span_end|evidence_id)[:16]}"""
    return f"cit_{make_id(section_path, span_start, span_end, evidence_id_)[:SHORT_HEX_LEN]}"


def ast_id(sprint_id: str) -> str:
    """ast_{sha256(sprint_id)[:12]}"""
    h = hashlib.sha256(sprint_id.encode("utf-8")).hexdigest()
    return f"ast_{h[:AST_HEX_LEN]}"


def chapter_id(order: int) -> str:
    """ch{order}"""
    return f"ch{order}"


def section_id(chapter_order: int, section_order: int) -> str:
    """ch{N}/sec{M}"""
    return f"ch{chapter_order}/sec{section_order}"


# Mapping of helper name -> expected prefix, exposed for tests + introspection.
ID_PREFIXES = {
    "connector_id": "sc_",
    "hit_id": "hit_",
    "doc_id": "doc_",
    "evidence_id": "ev_",
    "claim_id": "clm_",
    "link_id": "cel_",
    "citation_id": "cit_",
    "ast_id": "ast_",
}
