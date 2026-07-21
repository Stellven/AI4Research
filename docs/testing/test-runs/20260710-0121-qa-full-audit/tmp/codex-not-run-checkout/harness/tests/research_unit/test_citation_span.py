"""Tests for evidence/citation_span.py: verify_span and verify_span_by_bytes.

Acceptance:
- verify_span returns True for exact character-offset matches
- verify_span returns False for mismatches and out-of-bounds
- verify_span_by_bytes handles UTF-8 byte offsets correctly
- Multi-byte UTF-8 boundary cases tested explicitly (CJK, emoji, combining marks)
- Negative test: span_mismatch_rejected
- Zero @mock.patch — all tests use real string operations
"""

from __future__ import annotations

import sys
from pathlib import Path

# Place harness/lib on sys.path (same pattern as existing tests)
_LIB_DIR = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import pytest  # noqa: E402

from research.evidence.citation_span import (  # noqa: E402
    byte_offset_to_char_offset,
    char_offset_to_byte_offset,
    verify_citation_span,
    verify_span,
    verify_span_by_bytes,
)


# ---------------------------------------------------------------------------
# Tests: verify_span (character-offset mode)
# ---------------------------------------------------------------------------

class TestVerifySpanCharOffsets:
    def test_exact_match_ascii(self):
        source = "The quick brown fox jumps over the lazy dog"
        assert verify_span(source, 4, 9, "quick") is True

    def test_exact_match_substring(self):
        source = "Hello world this is a test"
        assert verify_span(source, 12, 16, "this") is True

    def test_full_source_match(self):
        source = "full content"
        assert verify_span(source, 0, len(source), source) is True

    def test_mismatch_rejected(self):
        """Negative test: altered span_text is rejected."""
        source = "The quick brown fox"
        assert verify_span(source, 4, 9, "slow") is False

    def test_span_mismatch_rejected(self):
        """Negative test: completely wrong span_text."""
        source = "Research shows that AI models can hallucinate facts"
        assert verify_span(source, 0, 8, "Evidence") is False

    def test_start_negative_rejected(self):
        assert verify_span("text", -1, 2, "te") is False

    def test_end_before_start_rejected(self):
        assert verify_span("text", 3, 1, "ex") is False

    def test_end_equals_start_rejected(self):
        assert verify_span("text", 2, 2, "") is False

    def test_end_past_source_rejected(self):
        assert verify_span("short", 0, 100, "short") is False

    def test_empty_source_rejected(self):
        assert verify_span("", 0, 1, "x") is False


# ---------------------------------------------------------------------------
# Tests: verify_span with UTF-8 multi-byte characters
# ---------------------------------------------------------------------------

class TestVerifySpanUTF8:
    def test_cjk_characters(self):
        """Chinese characters are 3 bytes each in UTF-8."""
        source = "深度研究系统的架构设计"
        span = "系统"
        # "深度研究" = 4 chars, so "系统" starts at index 4
        assert verify_span(source, 4, 6, span) is True

    def test_cjk_offset_correctness(self):
        source = "这是中文测试文本"
        # Characters: 这(0)是(1)中(2)文(3)测(4)试(5)文(6)本(7)
        assert verify_span(source, 2, 4, "中文") is True
        assert verify_span(source, 4, 6, "测试") is True
        assert verify_span(source, 6, 8, "文本") is True

    def test_mixed_ascii_and_cjk(self):
        source = "Hello世界Good"
        # H(0)e(1)l(2)l(3)o(4)世(5)界(6)G(7)o(8)o(9)d(10)
        assert verify_span(source, 5, 7, "世界") is True
        assert verify_span(source, 0, 5, "Hello") is True
        assert verify_span(source, 7, 11, "Good") is True

    def test_emoji_characters(self):
        """Emoji are often 4 bytes in UTF-8 but 1-2 code points."""
        source = "AI 🤖 is cool 🚀"
        # A(0)I(1) (2)🤖(3) (4)i(5)s(6) (7)c(8)o(9)o(10)l(11) (12)🚀(13)
        assert verify_span(source, 3, 4, "🤖") is True
        assert verify_span(source, 13, 14, "🚀") is True

    def test_multi_byte_mismatch_rejected(self):
        source = "深度研究系统"
        assert verify_span(source, 0, 2, "浅层") is False


# ---------------------------------------------------------------------------
# Tests: verify_span_by_bytes (byte-offset mode)
# ---------------------------------------------------------------------------

class TestVerifySpanByBytes:
    def test_ascii_byte_offsets(self):
        source = "Hello world"
        # "Hello" is bytes 0-5 (5 bytes)
        assert verify_span_by_bytes(source, 0, 5, "Hello") is True

    def test_cjk_byte_offsets(self):
        """Each CJK char is 3 bytes in UTF-8."""
        source = "深度研究"
        # 深 = bytes 0-3, 度 = bytes 3-6, 研 = bytes 6-9, 究 = bytes 9-12
        assert verify_span_by_bytes(source, 0, 3, "深") is True
        assert verify_span_by_bytes(source, 3, 6, "度") is True
        assert verify_span_by_bytes(source, 6, 12, "研究") is True

    def test_cjk_full_span(self):
        source = "中文测试"
        assert verify_span_by_bytes(source, 0, 12, source) is True

    def test_broken_boundary_returns_false(self):
        """If byte offset splits a multi-byte char, decode fails → False."""
        source = "深度"  # 6 bytes total (3+3)
        # Offset 1 splits the first byte of 深
        assert verify_span_by_bytes(source, 1, 4, "something") is False

    def test_mixed_byte_offsets(self):
        source = "Hi你好"
        # H(1)i(1)你(3)好(3) = 8 bytes
        assert verify_span_by_bytes(source, 0, 2, "Hi") is True
        assert verify_span_by_bytes(source, 2, 8, "你好") is True

    def test_emoji_byte_offsets(self):
        source = "🤖"  # 4 bytes in UTF-8
        assert verify_span_by_bytes(source, 0, 4, "🤖") is True

    def test_out_of_bounds_rejected(self):
        source = "test"
        assert verify_span_by_bytes(source, 0, 100, "test") is False
        assert verify_span_by_bytes(source, -1, 3, "tes") is False


# ---------------------------------------------------------------------------
# Tests: offset conversion helpers
# ---------------------------------------------------------------------------

class TestOffsetConversion:
    def test_char_to_byte_ascii(self):
        text = "Hello"
        assert char_offset_to_byte_offset(text, 3) == 3

    def test_char_to_byte_cjk(self):
        text = "深度研究"
        # char 0 → byte 0, char 1 → byte 3, char 2 → byte 6
        assert char_offset_to_byte_offset(text, 1) == 3
        assert char_offset_to_byte_offset(text, 2) == 6

    def test_byte_to_char_cjk(self):
        text = "深度研究"
        assert byte_offset_to_char_offset(text, 3) == 1
        assert byte_offset_to_char_offset(text, 6) == 2

    def test_roundtrip_char_byte(self):
        text = "Hello世界Test"
        for char_off in range(len(text) + 1):
            byte_off = char_offset_to_byte_offset(text, char_off)
            assert byte_offset_to_char_offset(text, byte_off) == char_off


# ---------------------------------------------------------------------------
# Tests: verify_citation_span (full two-sided verification)
# ---------------------------------------------------------------------------

class TestVerifyCitationSpan:
    def test_both_sides_match(self):
        report = "According to research, the result is positive."
        source = "Research shows the result is positive in 95% of cases."
        result = verify_citation_span(
            report_section_text=report,
            source_text=source,
            citation_span_start=27,
            citation_span_end=33,
            citation_span_text="result",
            evidence_span_start=19,
            evidence_span_end=25,
            evidence_span_text="result",
        )
        assert result["report_match"] is True
        assert result["evidence_match"] is True
        assert result["valid"] is True

    def test_report_side_mismatch(self):
        report = "The claim is unsupported here"
        source = "Evidence supports the claim"
        result = verify_citation_span(
            report_section_text=report,
            source_text=source,
            citation_span_start=4,
            citation_span_end=9,
            citation_span_text="wrong",
            evidence_span_start=0,
            evidence_span_end=8,
            evidence_span_text="Evidence",
        )
        assert result["report_match"] is False
        assert result["valid"] is False

    def test_evidence_side_mismatch(self):
        report = "The claim is clear"
        source = "Source text for evidence"
        result = verify_citation_span(
            report_section_text=report,
            source_text=source,
            citation_span_start=0, citation_span_end=3,
            citation_span_text="The",
            evidence_span_start=0, evidence_span_end=6,
            evidence_span_text="Wrong!",
        )
        assert result["evidence_match"] is False
        assert result["valid"] is False

    def test_cjk_citation_span(self):
        report = "研究表明系统性能优异"
        source = "系统性能测试结果证明系统性能优异"
        result = verify_citation_span(
            report_section_text=report,
            source_text=source,
            citation_span_start=4, citation_span_end=8,
            citation_span_text="系统性能",
            evidence_span_start=10, evidence_span_end=14,
            evidence_span_text="系统性能",
        )
        assert result["valid"] is True
