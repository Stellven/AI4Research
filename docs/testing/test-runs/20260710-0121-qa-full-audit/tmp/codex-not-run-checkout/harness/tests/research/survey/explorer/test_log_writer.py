"""Tests for survey/explorer/log_writer.py.

S03 N6 implementation test per S02 exploration-arch.md §3 (kill_reason +
evidence_refs + decision_ts mandatory) + §10 FM-3 (incremental flush).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HARNESS_LIB = Path(__file__).resolve().parents[4] / "lib"
if str(_HARNESS_LIB) not in sys.path:
    sys.path.insert(0, str(_HARNESS_LIB))

from research.survey.explorer.log_writer import LogWriter  # noqa: E402
from research.survey.schemas import EliminationRecord  # noqa: E402


def _make_record(direction_id: str = "dir-a", kill_reason: str = "score too low") -> EliminationRecord:
    return EliminationRecord(
        direction_id=direction_id,
        direction_name=f"Direction {direction_id}",
        score=0.42,
        kill_reason=kill_reason,
        evidence_refs=["src-1", "src-2"],
        decision_ts="2026-05-17T23:00:00Z",
        direction_query="why is X better than Y",
        candidate_count=3,
        score_breakdown={"source_coverage": 0.5, "novelty": 0.3},
    )


def test_append_creates_jsonl_line(tmp_path: Path) -> None:
    writer = LogWriter(tmp_path / "elimination_log.jsonl")
    writer.append(_make_record())
    raw_lines = (tmp_path / "elimination_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 1
    payload = json.loads(raw_lines[0])
    assert payload["direction_id"] == "dir-a"
    assert payload["kill_reason"] == "score too low"
    assert payload["evidence_refs"] == ["src-1", "src-2"]


def test_append_multiple_records_preserves_order(tmp_path: Path) -> None:
    writer = LogWriter(tmp_path / "log.jsonl")
    writer.append(_make_record("dir-a"))
    writer.append(_make_record("dir-b"))
    writer.append(_make_record("dir-c"))
    records = writer.read_all()
    assert [r["direction_id"] for r in records] == ["dir-a", "dir-b", "dir-c"]
    assert writer.count() == 3


def test_resume_after_reopen_preserves_records(tmp_path: Path) -> None:
    log_path = tmp_path / "elimination_log.jsonl"
    writer1 = LogWriter(log_path)
    writer1.append(_make_record("dir-a"))
    writer1.append(_make_record("dir-b"))
    # Simulate process restart by instantiating a fresh LogWriter.
    writer2 = LogWriter(log_path)
    writer2.append(_make_record("dir-c"))
    assert writer2.count() == 3
    direction_ids = [r["direction_id"] for r in writer2.read_all()]
    assert direction_ids == ["dir-a", "dir-b", "dir-c"]


def test_append_flushes_immediately_for_concurrent_read(tmp_path: Path) -> None:
    log_path = tmp_path / "log.jsonl"
    writer = LogWriter(log_path)
    writer.append(_make_record("dir-a"))
    # Read on disk between two appends — must already see the first record.
    mid_records = log_path.read_text(encoding="utf-8").splitlines()
    assert len(mid_records) == 1
    writer.append(_make_record("dir-b"))
    final_records = log_path.read_text(encoding="utf-8").splitlines()
    assert len(final_records) == 2


def test_append_rejects_empty_kill_reason(tmp_path: Path) -> None:
    writer = LogWriter(tmp_path / "log.jsonl")
    with pytest.raises(ValueError, match="kill_reason"):
        writer.append(_make_record(kill_reason=""))
    with pytest.raises(ValueError, match="kill_reason"):
        writer.append(_make_record(kill_reason="   "))


def test_append_rejects_empty_evidence_refs(tmp_path: Path) -> None:
    writer = LogWriter(tmp_path / "log.jsonl")
    record_dict = {
        "direction_id": "dir-x",
        "direction_name": "X",
        "score": 0.1,
        "kill_reason": "low score",
        "evidence_refs": [],
        "decision_ts": "2026-05-17T23:00:00Z",
    }
    with pytest.raises(ValueError, match="evidence_refs"):
        writer.append(record_dict)


def test_append_rejects_empty_decision_ts(tmp_path: Path) -> None:
    writer = LogWriter(tmp_path / "log.jsonl")
    record_dict = {
        "direction_id": "dir-x",
        "direction_name": "X",
        "score": 0.1,
        "kill_reason": "low score",
        "evidence_refs": ["src-1"],
        "decision_ts": "",
    }
    with pytest.raises(ValueError, match="decision_ts"):
        writer.append(record_dict)


def test_constructor_creates_parent_dirs(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c" / "log.jsonl"
    writer = LogWriter(nested)
    assert nested.exists()
    assert writer.count() == 0
