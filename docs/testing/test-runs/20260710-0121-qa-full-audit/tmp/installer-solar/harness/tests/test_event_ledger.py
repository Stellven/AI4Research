"""Tests for event_ledger.py — SQLite WAL + JSONL mirror dual-write.

S03 N2 acceptance:
  1. append / replay / get_last_event_id
  2. SQLite WAL + JSONL dual-write order (validate->sqlite->jsonl; sqlite fail -> no jsonl)
  3. event_id UNIQUE INDEX
  4. 100 concurrent append PASS
  5. replay(sprint_id) idempotent
  6. pytest all PASS
  7. py_compile passes
"""

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from harness.lib.event_ledger import EventLedger, EventLedgerError


@pytest.fixture
def tmp_ledger(tmp_path):
    return EventLedger(base_dir=str(tmp_path / "run"))


def _make_event(
    event_type="action.proposed", sprint_id="sprint-test", actor="coordinator", **kw
):
    base = {"event_type": event_type, "sprint_id": sprint_id, "actor": actor}
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# AC1: append / replay / get_last_event_id
# ---------------------------------------------------------------------------


class TestCoreAPI:
    def test_append_returns_event_id(self, tmp_ledger):
        eid = tmp_ledger.append(_make_event())
        assert isinstance(eid, str) and len(eid) > 0

    def test_replay_returns_events(self, tmp_ledger):
        tmp_ledger.append(_make_event(node_id="N1"))
        tmp_ledger.append(_make_event(node_id="N2"))
        events = tmp_ledger.replay("sprint-test")
        assert len(events) == 2
        assert events[0]["node_id"] == "N1"
        assert events[1]["node_id"] == "N2"

    def test_get_last_event_id_empty(self, tmp_ledger):
        assert tmp_ledger.get_last_event_id() is None

    def test_get_last_event_id_returns_latest(self, tmp_ledger):
        tmp_ledger.append(_make_event(node_id="N1"))
        e2 = tmp_ledger.append(_make_event(node_id="N2"))
        assert tmp_ledger.get_last_event_id() == e2

    def test_replay_filters_by_sprint(self, tmp_ledger):
        tmp_ledger.append(_make_event(sprint_id="sprint-A"))
        tmp_ledger.append(_make_event(sprint_id="sprint-B"))
        tmp_ledger.append(_make_event(sprint_id="sprint-A"))
        assert len(tmp_ledger.replay("sprint-A")) == 2
        assert len(tmp_ledger.replay("sprint-B")) == 1

    def test_event_has_all_fields(self, tmp_ledger):
        eid = tmp_ledger.append(_make_event(payload={"key": "val"}))
        events = tmp_ledger.replay("sprint-test")
        e = events[0]
        assert e["event_id"] == eid
        assert e["event_type"] == "action.proposed"
        assert e["sprint_id"] == "sprint-test"
        assert e["actor"] == "coordinator"
        assert e["payload"] == {"key": "val"}
        assert "created_at" in e
        assert e["schema_version"] == "v1"


# ---------------------------------------------------------------------------
# AC2: dual-write order (validate->sqlite->jsonl; sqlite fail -> no jsonl)
# ---------------------------------------------------------------------------


class TestDualWrite:
    def test_jsonl_has_same_events_as_sqlite(self, tmp_ledger):
        tmp_ledger.append(_make_event(node_id="N1"))
        tmp_ledger.append(_make_event(node_id="N2"))
        jsonl_path = tmp_ledger._jsonl_path
        assert jsonl_path.exists()
        with open(jsonl_path) as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert len(lines) == 2
        assert lines[0]["node_id"] == "N1"

    def test_sqlite_failure_does_not_write_jsonl(self, tmp_path):
        ledger = EventLedger(base_dir=str(tmp_path / "run"))
        db_path = ledger._db_path
        os.chmod(str(db_path), 0o444)
        os.chmod(str(tmp_path / "run"), 0o555)

        jsonl_path = ledger._jsonl_path
        initial_lines = 0
        if jsonl_path.exists():
            with open(jsonl_path) as f:
                initial_lines = sum(1 for l in f if l.strip())

        with pytest.raises(EventLedgerError):
            ledger.append(_make_event())

        os.chmod(str(tmp_path / "run"), 0o755)
        os.chmod(str(db_path), 0o644)

        if jsonl_path.exists():
            with open(jsonl_path) as f:
                final_lines = sum(1 for l in f if l.strip())
            assert final_lines == initial_lines

    def test_validate_rejects_missing_fields(self, tmp_ledger):
        with pytest.raises(ValueError, match="missing required fields"):
            tmp_ledger.append({"event_type": "x"})


# ---------------------------------------------------------------------------
# AC3: event_id UNIQUE INDEX
# ---------------------------------------------------------------------------


class TestUniqueConstraint:
    def test_duplicate_event_id_raises(self, tmp_ledger):
        event = _make_event()
        event["event_id"] = "fixed-id-12345"
        tmp_ledger.append(event)
        with pytest.raises(EventLedgerError, match="duplicate"):
            tmp_ledger.append(event)


# ---------------------------------------------------------------------------
# AC4: 100 concurrent append PASS
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_100_concurrent_appends(self, tmp_path):
        ledger = EventLedger(base_dir=str(tmp_path / "run"))

        results = []
        errors = []

        def append_one(idx):
            try:
                eid = ledger.append(
                    _make_event(
                        event_type=f"action.{idx}",
                        node_id=f"N{idx}",
                        payload={"idx": idx},
                    )
                )
                results.append(eid)
            except Exception as exc:
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(append_one, i) for i in range(100)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"errors: {errors}"
        assert len(results) == 100
        assert len(set(results)) == 100, "duplicate event_ids detected"

        events = ledger.replay("sprint-test")
        assert len(events) == 100


# ---------------------------------------------------------------------------
# AC5: replay(sprint_id) idempotent
# ---------------------------------------------------------------------------


class TestReplayIdempotency:
    def test_replay_returns_same_result_on_multiple_calls(self, tmp_ledger):
        tmp_ledger.append(_make_event(node_id="N1"))
        tmp_ledger.append(_make_event(node_id="N2"))

        r1 = tmp_ledger.replay("sprint-test")
        r2 = tmp_ledger.replay("sprint-test")
        r3 = tmp_ledger.replay("sprint-test")

        assert r1 == r2 == r3
        assert len(r1) == 2

    def test_replay_no_side_effects(self, tmp_ledger):
        tmp_ledger.append(_make_event())
        count_before = len(tmp_ledger.replay("sprint-test"))
        tmp_ledger.replay("sprint-test")
        tmp_ledger.replay("sprint-test")
        count_after = len(tmp_ledger.replay("sprint-test"))
        assert count_before == count_after


# ---------------------------------------------------------------------------
# AC7: py_compile
# ---------------------------------------------------------------------------


class TestCompile:
    def test_py_compile(self):
        result = subprocess.run(
            [
                "python3",
                "-m",
                "py_compile",
                str(Path(__file__).parent.parent / "lib" / "event_ledger.py"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
