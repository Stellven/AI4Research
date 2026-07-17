"""Unit tests for harness/lib/research/hashing.py.

Test integrity: no @mock.patch — pure-function SHA-256 tests.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

# Place harness/lib on sys.path (N5-style; no conftest, no package layout)
_LIB_DIR = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import pytest  # noqa: E402

from research import hashing  # noqa: E402


# Known-good SHA-256 of ASCII "hello"
HELLO_SHA = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
# Known-good SHA-256 of the empty string
EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TestContentHash:
    def test_hello_matches_known_sha256(self) -> None:
        assert hashing.content_hash("hello") == HELLO_SHA

    def test_empty_string_matches_known_sha256(self) -> None:
        assert hashing.content_hash("") == EMPTY_SHA

    def test_output_is_64_hex_chars(self) -> None:
        h = hashing.content_hash("any input")
        assert len(h) == hashing.HASH_HEX_LEN == 64
        # All hex
        int(h, 16)

    def test_deterministic_same_input(self) -> None:
        a = hashing.content_hash("solar deepresearch")
        b = hashing.content_hash("solar deepresearch")
        assert a == b

    def test_different_input_different_output(self) -> None:
        a = hashing.content_hash("foo")
        b = hashing.content_hash("bar")
        assert a != b

    def test_utf8_multibyte(self) -> None:
        # Two-byte (Chinese) characters — independently verify via stdlib
        text = "中文研究证据"
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert hashing.content_hash(text) == expected
        assert len(hashing.content_hash(text)) == 64

    def test_utf8_four_byte_emoji(self) -> None:
        text = "report \U0001F4D8"  # blue book emoji
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert hashing.content_hash(text) == expected

    def test_rejects_non_string_input(self) -> None:
        with pytest.raises(TypeError):
            hashing.content_hash(b"raw bytes are not str")
        with pytest.raises(TypeError):
            hashing.content_hash(12345)


class TestVerifyContentHash:
    def test_verify_true_for_matching_pair(self) -> None:
        assert hashing.verify_content_hash("payload", HELLO_SHA) is False
        assert hashing.verify_content_hash("hello", HELLO_SHA) is True

    def test_verify_false_for_mismatched_pair(self) -> None:
        assert hashing.verify_content_hash("hello", EMPTY_SHA) is False
