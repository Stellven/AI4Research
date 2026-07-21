"""ArtifactStore basic schema + secret-redaction tests.

The dataclass field shapes are loaded from the actual module so the tests
remain accurate even if I5 reshuffles non-required fields.
"""

from __future__ import annotations

import json
import sys

import pytest

from integrations.gepa_optimizer.artifact_store import (
    ArtifactStore,
    CandidateRecord,
    RunRecord,
    SecretViolationError,
    _cache_key,
    _contains_secret,
    _redact_secrets,
)


def test_cache_key_is_stable():
    a = _cache_key("hello world")
    b = _cache_key("hello world")
    c = _cache_key("hello world!")
    assert a == b
    assert a != c
    assert len(a) == 64  # sha256 hex


def test_secret_detection_flags_api_key_assignment():
    """The regex must catch ``api_key=...`` style assignments."""
    assert _contains_secret("api_key=ABCDEF1234567890ABCDEF") is True
    assert _contains_secret("token=ghp_supersecretvalue1234567890ABCDEF1234") is True


def test_secret_detection_does_not_flag_plain_text():
    assert _contains_secret("the quick brown fox") is False


def test_secret_redaction_replaces_inline_value():
    redacted = _redact_secrets("api_key=AKIAIOSFODNN7EXAMPLE and some text")
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted


def test_run_record_construction():
    rec = RunRecord(run_id="r-1", run_dir="/tmp/x", started_at="2026-05-22T11:00:00Z")
    assert rec.run_id == "r-1"
    assert rec.run_dir == "/tmp/x"


def _make_candidate(**overrides) -> CandidateRecord:
    """Build a CandidateRecord with all 10 required fields populated."""
    defaults = dict(
        candidate_id="c-default",
        text="default candidate text",
        score=0.5,
        parent_id=None,
        lineage=(),
        generation=0,
        operator="mini-claude-sonnet-builder",
        created_at="2026-05-22T11:00:00Z",
        scores={},
        metadata={},
    )
    defaults.update(overrides)
    return CandidateRecord(**defaults)


def test_candidate_record_lineage_fields():
    cand = _make_candidate(candidate_id="c-1", text="seed text", score=0.5)
    assert cand.parent_id is None
    assert cand.generation == 0
    assert cand.score == 0.5


def test_secret_violation_raises_on_write(tmp_path):
    """If a caller tries to persist a secret-bearing candidate, the store must abort."""
    store = ArtifactStore(run_dir=str(tmp_path / "run-1"))
    with pytest.raises(SecretViolationError):
        store.write_candidate(
            text="api_key=AKIAIOSFODNN7EXAMPLE",
            score=0.5,
        )


def test_write_candidate_persists_to_disk(tmp_path):
    store = ArtifactStore(run_dir=str(tmp_path / "run-ok"))
    rec = store.write_candidate(
        text="a perfectly ordinary candidate",
        score=0.42,
    )
    assert isinstance(rec, CandidateRecord)
    # The store writes at least one artifact (candidates.jsonl, status, ...).
    written = list((tmp_path / "run-ok").rglob("*"))
    files = [p for p in written if p.is_file()]
    assert files, "ArtifactStore.write_candidate produced no files"


def test_write_candidate_redact_mode(tmp_path):
    store = ArtifactStore(run_dir=str(tmp_path / "run-redact"))
    rec = store.write_candidate(
        text="api_key=AKIAIOSFODNN7EXAMPLE here",
        score=0.1,
        redact=True,
    )
    assert "AKIAIOSFODNN7EXAMPLE" not in rec.text
