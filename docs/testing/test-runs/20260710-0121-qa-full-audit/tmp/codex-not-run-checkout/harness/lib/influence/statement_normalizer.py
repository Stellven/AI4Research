"""L1 StatementNormalizer — language, entities, quality flags.

Rule-based v0: deterministic and dependency-free so unit tests run without NER
models or network. Entities are surfaced via a lightweight capitalized-term /
known-term heuristic and tagged ``entities_source = "rule_based_v0"`` per S1-design
§4.3. A real NER backend can replace ``extract_entities`` without touching the
operator contract.
"""
from __future__ import annotations

import re
from typing import Iterable

from .models import Statement

ENTITIES_SOURCE_RULE = "rule_based_v0"

# Domain terms worth catching even when not capitalized as a proper noun.
_KNOWN_TERMS = (
    "scaling law", "transformer", "diffusion", "rlhf", "agentic", "inference",
    "quantization", "fine-tuning", "open source", "benchmark",
)
_MARKETING_MARKERS = ("buy now", "sign up", "discount", "promo", "giveaway", "link in bio")
_JOKE_MARKERS = ("lol", "lmao", "😂", "🤣", "just kidding", "/s")
_CAP_TOKEN = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:-[A-Za-z0-9]+)?)\b")
_NON_ASCII = re.compile(r"[^\x00-\x7F]")


def detect_language(text: str) -> str:
    """Coarse heuristic: ascii-dominant => en, else 'non-en'. Deterministic."""
    if not text:
        return "und"
    non_ascii = len(_NON_ASCII.findall(text))
    return "en" if non_ascii <= max(1, len(text) // 20) else "non-en"


def extract_entities(text: str) -> list[str]:
    found: list[str] = []
    lowered = text.lower()
    for term in _KNOWN_TERMS:
        if term in lowered and term not in found:
            found.append(term)
    for m in _CAP_TOKEN.findall(text):
        # Skip sentence-initial common words that are merely capitalized.
        if len(m) > 1 and m.lower() not in {"the", "this", "next", "gen"} and m not in found:
            found.append(m)
    return found


def derive_quality_flags(stmt: Statement) -> None:
    """Mutate stmt.quality_flags in place from text heuristics."""
    text = (stmt.text or "").lower()
    flags = stmt.quality_flags
    if any(marker in text for marker in _MARKETING_MARKERS):
        flags.is_marketing = True
    if any(marker in text for marker in _JOKE_MARKERS):
        flags.is_joke_or_meme = True
    if text.strip().startswith("@") or stmt.raw_metadata.get("in_reply_to"):
        flags.is_reply = True
    if stmt.raw_metadata.get("quoted_status") or text.strip().startswith(">"):
        flags.is_quote = True


def normalize(stmt: Statement) -> Statement:
    if not stmt.language:
        stmt.language = detect_language(stmt.text)
    if not stmt.entities:
        stmt.entities = extract_entities(stmt.text)
        stmt.entities_source = ENTITIES_SOURCE_RULE
    elif not stmt.entities_source:
        stmt.entities_source = ENTITIES_SOURCE_RULE
    derive_quality_flags(stmt)
    return stmt


def normalize_batch(statements: Iterable[Statement]) -> list[Statement]:
    return [normalize(s) for s in statements]
