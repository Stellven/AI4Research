"""Tests for research/hashing.py: SHA-256 content hashing.

Acceptance:
- content_hash returns 64-char hex digest
- Identical text produces identical hash
- Different text produces different hash
- verify_content_hash returns True/False correctly
- Non-string input raises TypeError
- UTF-8 text is handled correctly
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent.parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import pytest

from research.hashing import HASH_HEX_LEN, content_hash, verify_content_hash


class TestContentHash:
    def test_returns_string(self):
        h = content_hash("hello")
        assert isinstance(h, str)

    def test_length_is_64(self):
        h = content_hash("test")
        assert len(h) == HASH_HEX_LEN

    def test_matches_manual_sha256(self):
        text = "hello world"
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert content_hash(text) == expected

    def test_deterministic(self):
        h1 = content_hash("deterministic test")
        h2 = content_hash("deterministic test")
        assert h1 == h2

    def test_different_inputs_different_hashes(self):
        assert content_hash("a") != content_hash("b")

    def test_empty_string(self):
        h = content_hash("")
        expected = hashlib.sha256("".encode("utf-8")).hexdigest()
        assert h == expected

    def test_unicode_text(self):
        h = content_hash("你好世界")
        assert len(h) == 64
        expected = hashlib.sha256("你好世界".encode("utf-8")).hexdigest()
        assert h == expected

    def test_emoji_text(self):
        h = content_hash("🧠 solar research")
        assert len(h) == 64

    def test_long_text(self):
        text = "x" * 100000
        h = content_hash(text)
        assert len(h) == 64

    def test_only_hex_chars(self):
        h = content_hash("test")
        int(h, 16)  # will raise if not hex


class TestContentHashTypeError:
    def test_rejects_int(self):
        with pytest.raises(TypeError, match="str"):
            content_hash(42)

    def test_rejects_bytes(self):
        with pytest.raises(TypeError, match="str"):
            content_hash(b"hello")

    def test_rejects_none(self):
        with pytest.raises(TypeError, match="str"):
            content_hash(None)

    def test_rejects_list(self):
        with pytest.raises(TypeError, match="str"):
            content_hash(["hello"])


class TestVerifyContentHash:
    def test_true_for_correct_hash(self):
        h = content_hash("correct")
        assert verify_content_hash("correct", h) is True

    def test_false_for_wrong_hash(self):
        assert verify_content_hash("text", "a" * 64) is False

    def test_false_for_empty_hash(self):
        assert verify_content_hash("text", "") is False

    def test_case_sensitive(self):
        h = content_hash("Case")
        assert verify_content_hash("Case", h.upper()) is False


class TestHashHexLen:
    def test_constant_is_64(self):
        assert HASH_HEX_LEN == 64
