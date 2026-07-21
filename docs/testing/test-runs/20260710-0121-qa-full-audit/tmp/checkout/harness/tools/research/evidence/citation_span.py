"""Citation Span Verifier — exact character-level span verification with
UTF-8 multi-byte boundary handling.

Spec: sprint-20260513-solar-deepresearch-product-line-s02-architecture
      / deepresearch.schemas.md §7 (CitationSpan invariant 1):
      "span_text must exactly equal the byte range in the section's final.md"

Python str slicing operates on Unicode code points, not bytes.  The schemas
specify "byte offset" but the invariants use Python slicing notation.  This
module resolves the ambiguity by offering both modes:

  verify_span()           — character-offset mode (default, Python slicing)
  verify_span_by_bytes()  — byte-offset mode (for storage-layer integrity)

Both modes are tested with multi-byte UTF-8 characters (CJK, emoji, combining
marks) to prove boundary safety.
"""

from __future__ import annotations

from typing import Any


def verify_span(
    source_text: str,
    span_start: int,
    span_end: int,
    span_text: str,
) -> bool:
    """Verify span_text exactly matches source_text[span_start:span_end].

    Uses character offsets (Python str slicing), safe for all Unicode text
    including multi-byte CJK characters and emoji.

    Returns False if offsets are out of bounds or text does not match.
    """
    if span_start < 0:
        return False
    if span_end <= span_start:
        return False
    if span_end > len(source_text):
        return False
    return source_text[span_start:span_end] == span_text


def verify_span_by_bytes(
    source_text: str,
    span_start: int,
    span_end: int,
    span_text: str,
) -> bool:
    """Verify span_text matches the UTF-8 byte range [span_start:span_end].

    Returns False if offsets are out of bounds, the byte slice is not valid
    UTF-8 (broken multi-byte boundary), or text does not match.
    """
    source_bytes = source_text.encode("utf-8")
    if span_start < 0:
        return False
    if span_end <= span_start:
        return False
    if span_end > len(source_bytes):
        return False
    try:
        actual = source_bytes[span_start:span_end].decode("utf-8")
    except UnicodeDecodeError:
        return False
    return actual == span_text


def char_offset_to_byte_offset(text: str, char_offset: int) -> int:
    """Convert a character offset to a byte offset in UTF-8 encoding."""
    return len(text[:char_offset].encode("utf-8"))


def byte_offset_to_char_offset(text: str, byte_offset: int) -> int:
    """Convert a byte offset to a character offset in UTF-8 encoding.

    Raises ValueError if byte_offset falls in the middle of a multi-byte char.
    """
    text_bytes = text.encode("utf-8")
    if byte_offset < 0 or byte_offset > len(text_bytes):
        raise ValueError(
            f"byte_offset {byte_offset} out of range [0, {len(text_bytes)}]"
        )
    return len(text_bytes[:byte_offset].decode("utf-8"))


def verify_citation_span(
    report_section_text: str,
    source_text: str,
    citation_span_start: int,
    citation_span_end: int,
    citation_span_text: str,
    evidence_span_start: int,
    evidence_span_end: int,
    evidence_span_text: str,
) -> dict[str, Any]:
    """Full citation span verification: report-side and evidence-side.

    Returns dict with report_match, evidence_match, and overall valid.
    """
    report_match = verify_span(
        report_section_text, citation_span_start, citation_span_end,
        citation_span_text,
    )
    evidence_match = verify_span(
        source_text, evidence_span_start, evidence_span_end,
        evidence_span_text,
    )
    return {
        "report_match": report_match,
        "evidence_match": evidence_match,
        "valid": report_match and evidence_match,
    }
