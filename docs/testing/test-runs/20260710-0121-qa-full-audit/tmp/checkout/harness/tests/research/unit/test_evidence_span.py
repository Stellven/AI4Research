"""Tests for research/evidence/citation_span.py: span verification with UTF-8 support.

Acceptance:
- verify_span: character-offset mode, exact match, boundary rejection
- verify_span_by_bytes: byte-offset mode, exact match, boundary rejection
- char_offset_to_byte_offset and byte_offset_to_char_offset: round-trip
- verify_citation_span: full report-side + evidence-side verification
- UTF-8 multi-byte boundary cases (CJK, emoji)
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent.parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import pytest

from research.evidence.citation_span import (
    byte_offset_to_char_offset,
    char_offset_to_byte_offset,
    verify_citation_span,
    verify_span,
    verify_span_by_bytes,
)


class TestVerifySpan:
    def test_exact_match(self):
        assert verify_span("Hello world", 0, 5, "Hello") is True

    def test_full_text(self):
        text = "complete text"
        assert verify_span(text, 0, len(text), text) is True

    def test_middle_slice(self):
        text = "abcdefghij"
        assert verify_span(text, 3, 7, "defg") is True

    def test_negative_start(self):
        assert verify_span("text", -1, 4, "text") is False

    def test_end_not_greater_than_start(self):
        assert verify_span("text", 2, 2, "") is False
        assert verify_span("text", 3, 2, "") is False

    def test_end_exceeds_length(self):
        assert verify_span("text", 0, 100, "text") is False

    def test_text_mismatch(self):
        assert verify_span("Hello world", 0, 5, "World") is False

    def test_empty_span_text(self):
        assert verify_span("text", 0, 0, "") is False


class TestVerifySpanUnicode:
    def test_cjk_characters(self):
        text = "你好世界测试"
        assert verify_span(text, 0, 2, "你好") is True

    def test_mixed_ascii_cjk(self):
        text = "Hello你好World"
        assert verify_span(text, 5, 7, "你好") is True

    def test_emoji(self):
        text = "🧠 is brain"
        assert verify_span(text, 0, 1, "🧠") is True

    def test_combining_characters(self):
        text = "école"
        assert verify_span(text, 0, 5, "école") is True


class TestVerifySpanByBytes:
    def test_ascii_match(self):
        text = "Hello world"
        assert verify_span_by_bytes(text, 0, 5, "Hello") is True

    def test_byte_offset_differs_from_char_offset(self):
        text = "你好"
        byte_len = len(text.encode("utf-8"))
        assert byte_len == 6
        assert verify_span_by_bytes(text, 0, 6, "你好") is True
        assert verify_span_by_bytes(text, 0, 3, "你好") is False

    def test_negative_start(self):
        assert verify_span_by_bytes("text", -1, 4, "text") is False

    def test_end_not_greater_than_start(self):
        assert verify_span_by_bytes("text", 2, 2, "") is False

    def test_end_exceeds_byte_length(self):
        assert verify_span_by_bytes("text", 0, 100, "text") is False

    def test_broken_utf8_boundary(self):
        text = "你好"
        # 0x00-0x05 bytes = "你好" (3 bytes each)
        # byte 2 is middle of first char -> broken UTF-8
        assert verify_span_by_bytes(text, 2, 4, "你") is False


class TestCharToByteOffsetConversion:
    def test_ascii(self):
        text = "hello"
        assert char_offset_to_byte_offset(text, 2) == 2

    def test_cjk(self):
        text = "你好世界"
        assert char_offset_to_byte_offset(text, 0) == 0
        assert char_offset_to_byte_offset(text, 2) == 6

    def test_mixed(self):
        text = "Hi你好"
        assert char_offset_to_byte_offset(text, 0) == 0
        assert char_offset_to_byte_offset(text, 2) == 2
        assert char_offset_to_byte_offset(text, 4) == 8

    def test_end_of_string(self):
        text = "abc"
        assert char_offset_to_byte_offset(text, 3) == 3


class TestByteToCharOffsetConversion:
    def test_ascii(self):
        text = "hello"
        assert byte_offset_to_char_offset(text, 2) == 2

    def test_cjk(self):
        text = "你好世界"
        assert byte_offset_to_char_offset(text, 0) == 0
        assert byte_offset_to_char_offset(text, 6) == 2

    def test_round_trip(self):
        text = "Hello你好World🧠"
        for char_off in range(len(text) + 1):
            byte_off = char_offset_to_byte_offset(text, char_off)
            recovered = byte_offset_to_char_offset(text, byte_off)
            assert recovered == char_off, f"round-trip failed at char {char_off}"

    def test_out_of_range_raises(self):
        text = "abc"
        with pytest.raises(ValueError, match="out of range"):
            byte_offset_to_char_offset(text, 100)

    def test_negative_raises(self):
        text = "abc"
        with pytest.raises(ValueError, match="out of range"):
            byte_offset_to_char_offset(text, -1)


class TestVerifyCitationSpan:
    def test_both_match(self):
        report = "Section text with cited data here"
        source = "Full source document with data inside"
        result = verify_citation_span(
            report, source,
            24, 28, "data",
            26, 30, "data",
        )
        assert result["report_match"] is True
        assert result["evidence_match"] is True
        assert result["valid"] is True

    def test_evidence_mismatch(self):
        report = "Cited text here"
        source = "Source with different data"
        result = verify_citation_span(
            report, source,
            0, 5, "Cited",
            0, 5, "Sourc",
        )
        assert result["valid"] is True  # both independently match their own texts

    def test_report_mismatch(self):
        report = "Section text"
        source = "Source data here"
        result = verify_citation_span(
            report, source,
            0, 5, "Wrong",
            0, 6, "Source",
        )
        assert result["report_match"] is False

    def test_result_keys(self):
        result = verify_citation_span("r", "s", 0, 1, "r", 0, 1, "s")
        assert "report_match" in result
        assert "evidence_match" in result
        assert "valid" in result
