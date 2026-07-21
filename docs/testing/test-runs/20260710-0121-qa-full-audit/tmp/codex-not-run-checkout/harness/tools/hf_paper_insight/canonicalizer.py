"""Canonicalizer — identity resolution + dedup for HF papers.

Per interfaces.md §2: canonicalize_paper, dedup_check, merge_seen_window.
"""
from __future__ import annotations

import json
from typing import Optional, Protocol, Tuple

from schema import (
    PaperCanonical,
    PaperSnapshot,
    _gen_id,
    _title_hash,
    _utc_now,
)


class StoreProto(Protocol):
    def upsert(self, entity: object) -> None: ...
    def find_canonical_by_title_hash(self, title_hash: str) -> Optional[PaperCanonical]: ...
    def find_canonical_by_arxiv(self, arxiv_id: str) -> Optional[PaperCanonical]: ...
    def merge_seen_window(self, paper_id: str, window_type: str, observed_at: str) -> None: ...


def _extract_arxiv_id(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    import re
    m = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", url)
    return m.group(1) if m else None


class Canonicalizer:
    def __init__(self, store: StoreProto) -> None:
        self._store = store

    def canonicalize_paper(self, snapshot: PaperSnapshot) -> PaperCanonical:
        title = getattr(snapshot, "_raw_title", "") or ""
        authors_json = getattr(snapshot, "_raw_authors_json", "[]") or "[]"
        arxiv_abs_url = getattr(snapshot, "_raw_arxiv_url", None)
        arxiv_id = _extract_arxiv_id(arxiv_abs_url)
        title_hash = _title_hash(title) if title else ""

        now = _utc_now()
        dedup_keys = {
            "title_hash": title_hash,
            "arxiv_id": arxiv_id or "",
            "hf_url": snapshot.hf_url,
        }

        return PaperCanonical(
            paper_id=snapshot.paper_id,
            title=title,
            title_hash=title_hash,
            authors_json=authors_json,
            orgs_json="[]",
            published_at=getattr(snapshot, "_raw_published_at", None),
            hf_url=snapshot.hf_url,
            arxiv_abs_url=arxiv_abs_url,
            arxiv_pdf_url=f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None,
            semantic_scholar_id=None,
            arxiv_id=arxiv_id,
            first_seen_at=now,
            last_seen_at=now,
            seen_windows_json=json.dumps([{
                "window_type": snapshot.window_type.value,
                "observed_at": snapshot.observed_at,
            }]),
            dedup_keys_json=json.dumps(dedup_keys),
            updated_at=now,
        )

    def canonicalize_from_raw(self, paper_id: str, title: str, hf_url: str,
                              *, authors_json: str = "[]",
                              arxiv_abs_url: Optional[str] = None,
                              published_at: Optional[str] = None) -> PaperCanonical:
        title_hash = _title_hash(title) if title else ""
        arxiv_id = _extract_arxiv_id(arxiv_abs_url)
        now = _utc_now()
        dedup_keys = {
            "title_hash": title_hash,
            "arxiv_id": arxiv_id or "",
            "hf_url": hf_url,
        }

        return PaperCanonical(
            paper_id=paper_id,
            title=title,
            title_hash=title_hash,
            authors_json=authors_json,
            orgs_json="[]",
            published_at=published_at,
            hf_url=hf_url,
            arxiv_abs_url=arxiv_abs_url,
            arxiv_pdf_url=f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None,
            semantic_scholar_id=None,
            arxiv_id=arxiv_id,
            first_seen_at=now,
            last_seen_at=now,
            seen_windows_json="[]",
            dedup_keys_json=json.dumps(dedup_keys),
            updated_at=now,
        )

    def dedup_check(self, canonical: PaperCanonical) -> Tuple[bool, str]:
        existing = self._store.find_canonical_by_title_hash(canonical.title_hash)
        if existing:
            return True, existing.paper_id

        if canonical.arxiv_id:
            existing = self._store.find_canonical_by_arxiv(canonical.arxiv_id)
            if existing:
                return True, existing.paper_id

        return False, ""

    def merge_seen_window(self, paper_id: str, window_type: str, observed_at: str) -> None:
        self._store.merge_seen_window(paper_id, window_type, observed_at)
