"""Compat — backward-compatibility adapter for pre-existing wake/dispatch/status paths.

Per contract: "旧路径兼容，不破坏现有 wake/dispatch/status".
Translates between the old flat-file/JSONL format and the new schema-based
storage, so existing harness dispatch pipelines continue to work.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from schema import (
    PaperCanonical,
    PaperSnapshot,
    _gen_id,
    _title_hash,
    _utc_now,
)
from storage import PaperStore


class LegacyPaperFormat:
    """Adapter for reading/writing the old flat JSONL format."""

    @staticmethod
    def from_legacy_jsonl(line: str) -> Optional[dict]:
        try:
            return json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def to_legacy_jsonl(paper: PaperCanonical) -> str:
        return json.dumps(asdict(paper), ensure_ascii=False)

    @staticmethod
    def convert_snapshot_to_canonical(
        snapshot: PaperSnapshot,
        *,
        title: str = "",
        authors: Optional[list[str]] = None,
    ) -> PaperCanonical:
        return PaperCanonical(
            paper_id=snapshot.paper_id or _gen_id("paper-"),
            title=title,
            title_hash=_title_hash(title) if title else "",
            authors_json=json.dumps(authors or []),
            hf_url=snapshot.hf_url,
            first_seen_at=snapshot.observed_at,
            last_seen_at=snapshot.observed_at,
            seen_windows_json=json.dumps([
                {"window_type": snapshot.window_type.value,
                 "observed_at": snapshot.observed_at}
            ]),
        )


class CompatBridge:
    """Bridge between old wake/dispatch paths and new schema storage."""

    def __init__(self, store: PaperStore) -> None:
        self._store = store

    def ingest_legacy_batch(self, jsonl_path: str) -> dict:
        results = {"converted": 0, "skipped": 0, "errors": []}
        path = Path(jsonl_path)
        if not path.exists():
            results["errors"].append(f"File not found: {jsonl_path}")
            return results

        for line_num, line in enumerate(path.read_text().splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            old = LegacyPaperFormat.from_legacy_jsonl(line)
            if old is None:
                results["skipped"] += 1
                continue

            try:
                canonical = PaperCanonical(
                    paper_id=old.get("paper_id", _gen_id("paper-")),
                    title=old.get("title", ""),
                    title_hash=old.get("title_hash") or _title_hash(old.get("title", "")),
                    authors_json=json.dumps(old.get("authors", [])),
                    orgs_json=json.dumps(old.get("orgs", [])),
                    published_at=old.get("published_at"),
                    hf_url=old.get("hf_url", ""),
                    arxiv_id=old.get("arxiv_id"),
                    first_seen_at=old.get("first_seen_at", _utc_now()),
                    last_seen_at=old.get("last_seen_at", _utc_now()),
                )
                self._store.upsert(canonical)
                results["converted"] += 1
            except Exception as e:
                results["errors"].append(f"line {line_num}: {e}")

        return results

    def export_canonical_as_legacy(self, paper_id: str) -> Optional[str]:
        canonical = self._store.get(PaperCanonical, paper_id)
        if canonical is None:
            return None
        return LegacyPaperFormat.to_legacy_jsonl(canonical)
