"""Tests for research/ids.py: canonical ID generation helpers.

Acceptance:
- All helpers produce deterministic, prefixed IDs
- ID_PREFIXES covers all domain helpers
- SHA-256 hex suffix has correct length
- Empty parts produce stable empty-string hash
- Non-string parts are coerced to str
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent.parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import pytest

from research.ids import (
    AST_HEX_LEN, CLAIM_HEX_LEN, SEPARATOR, SHORT_HEX_LEN,
    ast_id, chapter_id, claim_id, citation_id, connector_id, doc_id,
    evidence_id, hit_id, link_id, make_id, section_id, ID_PREFIXES,
)


class TestMakeId:
    def test_empty_parts_produce_stable_hash(self):
        h1 = make_id()
        h2 = make_id()
        assert h1 == h2
        assert len(h1) == 64

    def test_single_part(self):
        h = make_id("hello")
        expected = hashlib.sha256("hello".encode("utf-8")).hexdigest()
        assert h == expected

    def test_uses_pipe_separator(self):
        h = make_id("a", "b", "c")
        expected = hashlib.sha256("a|b|c".encode("utf-8")).hexdigest()
        assert h == expected

    def test_non_string_parts_coerced(self):
        h_str = make_id("123", "456")
        h_int = make_id(123, 456)
        assert h_str == h_int

    def test_deterministic(self):
        assert make_id("x", 1) == make_id("x", 1)

    def test_different_inputs_different_hashes(self):
        assert make_id("a") != make_id("b")


class TestIdPrefixes:
    def test_all_helpers_have_prefix(self):
        for name, prefix in ID_PREFIXES.items():
            assert prefix.startswith(prefix[:3])

    def test_connector_id_prefix(self):
        cid = connector_id("brave")
        assert cid.startswith("sc_")

    def test_hit_id_prefix(self):
        hid = hit_id("sc_x", "query", 0)
        assert hid.startswith("hit_")

    def test_doc_id_prefix(self):
        did = doc_id("sc_x", "http://example.com", "2026-01-01")
        assert did.startswith("doc_")

    def test_evidence_id_prefix(self):
        eid = evidence_id("doc_x", 0, 10, "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789")
        assert eid.startswith("ev_")

    def test_claim_id_prefix(self):
        cid = claim_id(1, "test claim")
        assert cid.startswith("clm_")

    def test_link_id_prefix(self):
        lid = link_id("clm_1_x", "ev_2_y")
        assert lid.startswith("cel_")

    def test_citation_id_prefix(self):
        cit = citation_id("ch1/sec1", 0, 10, "ev_x")
        assert cit.startswith("cit_")

    def test_ast_id_prefix(self):
        aid = ast_id("sprint_001")
        assert aid.startswith("ast_")


class TestConnectorId:
    def test_with_explicit_timestamp(self):
        cid = connector_id("brave", unix_ts=1700000000)
        assert cid == "sc_brave_6553f100"

    def test_with_current_time(self):
        cid = connector_id("brave")
        assert cid.startswith("sc_brave_")
        ts_hex = cid.split("_")[2]
        assert len(ts_hex) > 0

    def test_different_connectors_different(self):
        assert connector_id("brave", unix_ts=100) != connector_id("exa", unix_ts=100)


class TestHitId:
    def test_deterministic(self):
        h1 = hit_id("sc_x", "test", 0)
        h2 = hit_id("sc_x", "test", 0)
        assert h1 == h2
        assert len(h1.split("_")[1]) == SHORT_HEX_LEN

    def test_different_rank_different(self):
        assert hit_id("sc_x", "q", 0) != hit_id("sc_x", "q", 1)

    def test_different_query_different(self):
        assert hit_id("sc_x", "a", 0) != hit_id("sc_x", "b", 0)


class TestDocId:
    def test_with_url(self):
        did = doc_id("sc_x", "http://example.com", "2026-01-01")
        assert did.startswith("doc_")
        assert len(did.split("_")[1]) == SHORT_HEX_LEN

    def test_none_url_uses_internal(self):
        did_url = doc_id("sc_x", "http://example.com", "2026-01-01")
        did_none = doc_id("sc_x", None, "2026-01-01")
        assert did_url != did_none

    def test_empty_string_url_uses_internal(self):
        did_empty = doc_id("sc_x", "", "2026-01-01")
        did_none = doc_id("sc_x", None, "2026-01-01")
        assert did_empty == did_none


class TestEvidenceId:
    def test_deterministic(self):
        h = "a" * 64
        e1 = evidence_id("doc_x", 0, 10, h)
        e2 = evidence_id("doc_x", 0, 10, h)
        assert e1 == e2

    def test_suffix_length(self):
        h = "b" * 64
        eid = evidence_id("doc_x", 0, 5, h)
        suffix = eid.split("_")[1]
        assert len(suffix) == SHORT_HEX_LEN


class TestClaimId:
    def test_format(self):
        cid = claim_id(42, "AI can hallucinate")
        assert cid.startswith("clm_0042_")
        text_hash = cid.split("_")[2]
        assert len(text_hash) == CLAIM_HEX_LEN

    def test_zero_padded_counter(self):
        cid1 = claim_id(1, "text")
        cid7 = claim_id(7, "text")
        assert cid1.split("_")[1] == "0001"
        assert cid7.split("_")[1] == "0007"


class TestAstId:
    def test_suffix_length(self):
        aid = ast_id("sprint_001")
        suffix = aid.split("_")[1]
        assert len(suffix) == AST_HEX_LEN

    def test_deterministic(self):
        assert ast_id("s") == ast_id("s")


class TestChapterSectionId:
    def test_chapter_id_simple(self):
        assert chapter_id(1) == "ch1"
        assert chapter_id(5) == "ch5"

    def test_section_id_simple(self):
        assert section_id(1, 2) == "ch1/sec2"
        assert section_id(3, 1) == "ch3/sec1"


class TestSeparatorConstant:
    def test_separator_is_pipe(self):
        assert SEPARATOR == "|"

    def test_hex_lengths(self):
        assert SHORT_HEX_LEN == 16
        assert AST_HEX_LEN == 12
        assert CLAIM_HEX_LEN == 8
