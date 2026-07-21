"""Vocabulary correction helpers for transcript cleanup."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


SOURCE_KINDS = (
    "repo",
    "paper",
    "model",
    "product",
    "company",
    "people",
    "term",
)


@dataclass
class VocabDictionary:
    version_sha256: str
    sync_interval_hours: int
    entries: dict[str, str]
    sources_by_term: dict[str, str]


def build_vocab_dictionary(entries: list[dict[str, str]], *, sync_interval_hours: int = 168) -> VocabDictionary:
    normalized_entries: dict[str, str] = {}
    sources_by_term: dict[str, str] = {}
    for item in entries:
        wrong = str(item.get("wrong") or "").strip()
        correct = str(item.get("correct") or "").strip()
        source_kind = str(item.get("source_kind") or "term").strip()
        if not wrong or not correct:
            continue
        if source_kind not in SOURCE_KINDS:
            raise ValueError(f"Unsupported source_kind: {source_kind}")
        normalized_entries[wrong] = correct
        sources_by_term[correct] = source_kind
    digest = hashlib.sha256(
        "\n".join(f"{k}->{v}:{sources_by_term.get(v,'term')}" for k, v in sorted(normalized_entries.items())).encode("utf-8")
    ).hexdigest()
    return VocabDictionary(
        version_sha256=digest,
        sync_interval_hours=sync_interval_hours,
        entries=normalized_entries,
        sources_by_term=sources_by_term,
    )


def apply_vocab_corrections(text: str, vocab: VocabDictionary) -> tuple[str, list[str]]:
    corrected = text
    applied: list[str] = []
    for wrong, right in sorted(vocab.entries.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = re.compile(rf"\b{re.escape(wrong)}\b", re.IGNORECASE)
        if pattern.search(corrected):
            corrected = pattern.sub(right, corrected)
            applied.append(right)
    return corrected, sorted(set(applied))
