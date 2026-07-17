"""Unit tests for harness/lib/research/ids.py.

Test integrity: no @mock.patch — pure-function ID derivation tests.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import pytest  # noqa: E402

from research import ids  # noqa: E402


class TestMakeId:
    def test_returns_64_hex_chars(self) -> None:
        h = ids.make_id("a", "b", "c")
        assert len(h) == 64
        int(h, 16)  # raises if not hex

    def test_deterministic(self) -> None:
        assert ids.make_id("alpha", "beta") == ids.make_id("alpha", "beta")

    def test_order_matters(self) -> None:
        assert ids.make_id("a", "b") != ids.make_id("b", "a")

    def test_empty_parts_returns_sha256_of_empty_string(self) -> None:
        empty_sha = hashlib.sha256(b"").hexdigest()
        assert ids.make_id() == empty_sha

    def test_separator_is_pipe(self) -> None:
        # make_id("a","b") must be sha256("a|b"), not sha256("ab")
        expected = hashlib.sha256("a|b".encode("utf-8")).hexdigest()
        assert ids.make_id("a", "b") == expected

    def test_int_part_coerced_to_str(self) -> None:
        # rank=0 in hit_id must be canonicalized as "0"
        expected = hashlib.sha256("x|q|0".encode("utf-8")).hexdigest()
        assert ids.make_id("x", "q", 0) == expected


class TestDomainIds:
    def test_connector_id_prefix_and_timestamp_hex(self) -> None:
        cid = ids.connector_id("arxiv", unix_ts=0x1F2E)
        assert cid == "sc_arxiv_1f2e"
        assert cid.startswith(ids.ID_PREFIXES["connector_id"])

    def test_hit_id_format(self) -> None:
        hid = ids.hit_id("sc_brave_192a", "deepresearch", 0)
        assert hid.startswith("hit_")
        # 4 prefix chars + 16 hex chars = 20
        assert len(hid) == 4 + ids.SHORT_HEX_LEN

    def test_hit_id_deterministic(self) -> None:
        a = ids.hit_id("sc_brave_192a", "deepresearch", 3)
        b = ids.hit_id("sc_brave_192a", "deepresearch", 3)
        assert a == b
        # different rank produces different id
        c = ids.hit_id("sc_brave_192a", "deepresearch", 4)
        assert a != c

    def test_doc_id_internal_vs_url_branch(self) -> None:
        internal = ids.doc_id("sc_internal_mirage_1", None, "2026-05-14T00:00:00Z")
        urled = ids.doc_id("sc_internal_mirage_1", "https://x.example/a", "2026-05-14T00:00:00Z")
        assert internal.startswith("doc_") and urled.startswith("doc_")
        assert internal != urled

    def test_evidence_id_matches_spec(self) -> None:
        # ev_{sha256(source_id|span_start|span_end|content_hash)[:16]}
        canonical = "doc_abc|10|42|deadbeef"
        expected = "ev_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        assert ids.evidence_id("doc_abc", 10, 42, "deadbeef") == expected

    def test_claim_id_format(self) -> None:
        cid = ids.claim_id(1, "Solar is an AI-native runtime.")
        # clm_0001_<8 hex chars>
        assert re.fullmatch(r"clm_0001_[0-9a-f]{8}", cid) is not None

    def test_claim_id_counter_padding(self) -> None:
        cid = ids.claim_id(42, "x")
        assert cid.startswith("clm_0042_")
        cid_big = ids.claim_id(9999, "x")
        assert cid_big.startswith("clm_9999_")

    def test_link_id_prefix_and_length(self) -> None:
        lid = ids.link_id("clm_0001_aaaaaaaa", "ev_bbbbbbbbbbbbbbbb")
        assert lid.startswith("cel_")
        assert len(lid) == 4 + ids.SHORT_HEX_LEN

    def test_citation_id_prefix(self) -> None:
        cit = ids.citation_id("ch01/sec01", 0, 12, "ev_x")
        assert cit.startswith("cit_")
        assert len(cit) == 4 + ids.SHORT_HEX_LEN

    def test_ast_id_uses_12_hex_chars(self) -> None:
        aid = ids.ast_id("sprint-foo-bar")
        assert aid.startswith("ast_")
        # 4 prefix + 12 hex = 16
        assert len(aid) == 4 + ids.AST_HEX_LEN
        assert re.fullmatch(r"ast_[0-9a-f]{12}", aid) is not None

    def test_chapter_and_section_id_formats(self) -> None:
        assert ids.chapter_id(3) == "ch3"
        assert ids.section_id(2, 5) == "ch2/sec5"

    def test_id_prefixes_registry_complete(self) -> None:
        # Every prefix listed must be referenced by at least one helper
        assert set(ids.ID_PREFIXES.keys()) == {
            "connector_id", "hit_id", "doc_id", "evidence_id",
            "claim_id", "link_id", "citation_id", "ast_id",
        }


class TestNoCrossContamination:
    def test_different_helpers_different_prefixes(self) -> None:
        a = ids.hit_id("sc_x", "q", 0)
        b = ids.doc_id("sc_x", "url", "ts")
        c = ids.evidence_id("doc_x", 0, 1, "h")
        assert a[:4] != b[:4]
        assert b[:4] != c[:3]
        assert a.startswith("hit_") and b.startswith("doc_") and c.startswith("ev_")
