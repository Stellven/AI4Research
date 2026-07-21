"""Negative-control fixtures for DeepResearch tests.

Contains intentionally broken evidence items and claims that should be
rejected or flagged by the verification pipeline.
"""

BROKEN_EVIDENCE = {
    "evidence_id": "ev_broken_001",
    "source_id": "src_001",
    "source_type": "document",
    "content_hash": "0000000000000000000000000000000000000000000000000000000000000000",
    "span_start": 0,
    "span_end": 10,
    "span_text": "This text is intentionally mismatched with the hash",
    "evidence_type": "direct_quote",
    "relevance_score": 0.7,
    "support_direction": "supporting",
}

BROKEN_CLAIM = {
    "claim_id": "claim_broken_001",
    "claim_text": "This claim has no evidence linking to it",
    "section_path": "analysis",
    "source_method": "author_assertion",
    "is_key": True,
    "claim_type": "factual",
    "support_rating": "unsupported",
    "evidence_ids": [],
}

MISMATCHED_SPAN = {
    "source_text": "The quick brown fox jumps over the lazy dog",
    "span_start": 4,
    "span_end": 15,
    "span_text": "WRONG TEXT HERE",
}
