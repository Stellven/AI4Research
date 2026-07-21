"""Replay test for activation_proof.sh JSONL output.

Acceptance:
- Reads JSONL produced by activation_proof.sh
- Validates >= 4/5 event types present
- Verifies each event is valid EventV2 (schema_version, event_type, timestamp, seq)
- Validates event-specific payload fields
- pytest exit 0
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_LIB_DIR = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

_HARNESS_DIR = Path(__file__).resolve().parent.parent.parent
_SCRIPT = _HARNESS_DIR / "autopilot" / "integration" / "activation_proof.sh"

REQUIRED_EVENT_TYPES = {
    "autopilot_heartbeat",
    "pane_deadlock",
    "requirement_intake",
    "pm_drafted",
    "role_transition",
}

MIN_COVERAGE = 4


def _run_proof(tmp_path):
    output = tmp_path / "proof.jsonl"
    result = subprocess.run(
        ["bash", str(_SCRIPT), "--mode", "quick", "--output", str(output)],
        capture_output=True,
        text=True,
        cwd=str(_HARNESS_DIR),
    )
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert output.exists(), "Output file not created"
    return output


def _parse_events(path: Path) -> list[dict]:
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


class TestActivationProofExecution:
    def test_script_produces_jsonl(self, tmp_path):
        output = _run_proof(tmp_path)
        events = _parse_events(output)
        assert len(events) >= 5

    def test_all_events_valid_json(self, tmp_path):
        output = _run_proof(tmp_path)
        events = _parse_events(output)
        for i, evt in enumerate(events):
            assert isinstance(evt, dict), f"Event {i} is not a dict"

    def test_event_type_coverage_at_least_4_of_5(self, tmp_path):
        output = _run_proof(tmp_path)
        events = _parse_events(output)
        found_types = {e.get("event_type") for e in events}
        covered = found_types & REQUIRED_EVENT_TYPES
        assert len(covered) >= MIN_COVERAGE, (
            f"Only {len(covered)}/{len(REQUIRED_EVENT_TYPES)} event types: {covered}"
        )

    def test_all_5_event_types_present(self, tmp_path):
        output = _run_proof(tmp_path)
        events = _parse_events(output)
        found_types = {e.get("event_type") for e in events}
        assert REQUIRED_EVENT_TYPES.issubset(found_types), (
            f"Missing types: {REQUIRED_EVENT_TYPES - found_types}"
        )


class TestEventV2Schema:
    @pytest.fixture
    def events(self, tmp_path):
        return _parse_events(_run_proof(tmp_path))

    def test_schema_version_present(self, events):
        for evt in events:
            assert "schema_version" in evt
            assert evt["schema_version"] == "1.0.0"

    def test_timestamp_iso_format(self, events):
        for evt in events:
            ts = evt.get("timestamp", "")
            assert ts.endswith("Z")
            assert "T" in ts

    def test_seq_increasing(self, events):
        seqs = [e.get("seq", 0) for e in events]
        assert seqs == sorted(seqs)


class TestPayloadFields:
    @pytest.fixture
    def events_by_type(self, tmp_path):
        events = _parse_events(_run_proof(tmp_path))
        by_type: dict[str, dict] = {}
        for e in events:
            by_type.setdefault(e["event_type"], []).append(e)
        return by_type

    def test_heartbeat_payload(self, events_by_type):
        hbs = events_by_type.get("autopilot_heartbeat", [])
        assert len(hbs) >= 1
        p = hbs[0].get("payload", {})
        assert "idle" in p
        assert "active_dispatches" in p
        assert "queue_depth" in p

    def test_deadlock_payload(self, events_by_type):
        dls = events_by_type.get("pane_deadlock", [])
        assert len(dls) >= 1
        p = dls[0].get("payload", {})
        assert "pane_id" in p
        assert "elapsed_seconds" in p
        assert "deadline_seconds" in p

    def test_requirement_intake_payload(self, events_by_type):
        ris = events_by_type.get("requirement_intake", [])
        assert len(ris) >= 1
        p = ris[0].get("payload", {})
        assert "requirement_id" in p
        assert "raw_requirement" in p

    def test_pm_drafted_payload(self, events_by_type):
        pms = events_by_type.get("pm_drafted", [])
        assert len(pms) >= 1
        p = pms[0].get("payload", {})
        assert "prd_ready" in p
        assert "outcome_count" in p

    def test_role_transition_payload(self, events_by_type):
        rts = events_by_type.get("role_transition", [])
        assert len(rts) >= 1
        p = rts[0].get("payload", {})
        assert "from_phase" in p
        assert "to_phase" in p


class TestLongMode:
    def test_long_mode_emits_extra_heartbeats(self, tmp_path):
        output = tmp_path / "proof-long.jsonl"
        result = subprocess.run(
            ["bash", str(_SCRIPT), "--mode", "long", "--output", str(output)],
            capture_output=True,
            text=True,
            cwd=str(_HARNESS_DIR),
            timeout=30,
        )
        assert result.returncode == 0
        events = _parse_events(output)
        assert len(events) >= 10
        hb_count = sum(1 for e in events if e["event_type"] == "autopilot_heartbeat")
        assert hb_count >= 6
