"""SHA-256 content hashing for DeepResearch records.

Spec: S02 schemas.md — content_hash = sha256(text.encode('utf-8')).hexdigest()

Used by:
- SourceDocument.content_hash (hash of raw_text)
- EvidenceItem.content_hash (hash of span_text)
- CitationSpan span verification
- ClaimEvidenceLink integrity checks
"""

from __future__ import annotations

import hashlib

HASH_HEX_LEN = 64


def content_hash(text: str) -> str:
    """Return the SHA-256 hex digest of `text` encoded as UTF-8.

    The output is the canonical content hash format used throughout the
    DeepResearch evidence ledger. Two records with identical text always
    produce identical hashes; any mutation of the underlying text changes
    the hash.

    Raises:
        TypeError: if `text` is not a str.
    """
    if not isinstance(text, str):
        raise TypeError(f"content_hash requires str, got {type(text).__name__}")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_content_hash(text: str, expected_hash: str) -> bool:
    """Return True iff content_hash(text) == expected_hash.

    Used by the evidence ledger to detect span_text tampering between write
    and verify phases.
    """
    return content_hash(text) == expected_hash
