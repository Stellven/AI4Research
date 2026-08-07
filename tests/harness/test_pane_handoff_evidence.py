#!/usr/bin/env python3
"""test_pane_handoff_evidence.py — N7: pane_handoff evidence_validator tests.

Acceptance criteria:
  - evidence_validator.validate(handoff.md) returns ok=True iff event_id/artifact_path/action_id referenced
  - Referenced event_id must exist in events.jsonl (real lookup with 5s timeout fallback)
  - Pure 'done/passed/finished' keyword without ref → ok=False with missing_refs list
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

HARNESS_LIB = (Path(__file__).resolve().parents[2] / 'harness') / "lib"
sys.path.insert(0, str(HARNESS_LIB))

from pane_handoff.evidence_validator import (
    validate,
    ValidationResult,
    _extract_refs,
    _find_uncovered_claims,
    _lookup_event_ids,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REAL_EVENT_ID = "19cafd5a-0f1a-46b3-ab07-88f15596c12a"
FAKE_EVENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture
def tmp_events(tmp_path):
    """Create a minimal events.jsonl with one real event_id."""
    f = tmp_path / "events.jsonl"
    rows = [
        {"ts": "2026-05-20T10:00:00Z", "id": REAL_EVENT_ID, "event": "state_transition", "actor": "coordinator"},
        {"ts": "2026-05-20T10:01:00Z", "event": "log_message", "actor": "builder"},
    ]
    f.write_text("\n".join(json.dumps(r) for r in rows))
    return f


@pytest.fixture
def handoff_with_event_id(tmp_path):
    f = tmp_path / "handoff.md"
    f.write_text(
        "# Handoff\n\n## Summary\n\n"
        f"Node N1 dispatched, event_id `{REAL_EVENT_ID}` confirmed.\n\n"
        "## Verification Evidence\n\nTests pass.\n"
    )
    return f


@pytest.fixture
def handoff_with_artifact_path(tmp_path):
    f = tmp_path / "handoff.md"
    f.write_text(
        "# Handoff\n\n## Summary\n\n"
        "Output written to `~/.solar/harness/sprints/sprint-foo.handoff.md`.\n"
    )
    return f


@pytest.fixture
def handoff_with_action_id(tmp_path):
    f = tmp_path / "handoff.md"
    f.write_text(
        "# Handoff\n\n## Summary\n\n"
        "Dispatch ID: `graph-sprint-test-N2-20260520T155216Z` confirmed accepted.\n"
    )
    return f


@pytest.fixture
def handoff_pure_claims(tmp_path):
    """Handoff with only bare claim words, no references."""
    f = tmp_path / "handoff.md"
    f.write_text(
        "# Handoff\n\n## Summary\n\nDone.\n\n"
        "## Verification\n\nPassed.\n\n"
        "## Result\n\nFinished and implemented.\n"
    )
    return f


@pytest.fixture
def handoff_mixed(tmp_path):
    """Handoff with both claim words and references."""
    f = tmp_path / "handoff.md"
    f.write_text(
        "# Handoff\n\n## Summary\n\n"
        f"Task is done. Evidence: event_id `{REAL_EVENT_ID}`.\n\n"
        "## Verification\n\nPassed. See `/tmp/test/output.json`.\n"
    )
    return f


# ---------------------------------------------------------------------------
# Acceptance 1: ok=True iff event_id/artifact_path/action_id referenced
# ---------------------------------------------------------------------------

class TestOkWhenRefsPresent:
    def test_ok_true_with_event_id(self, handoff_with_event_id):
        result = validate(handoff_with_event_id, events_jsonl_paths=[])
        assert result.ok is True

    def test_ok_true_with_artifact_path(self, handoff_with_artifact_path):
        result = validate(handoff_with_artifact_path, events_jsonl_paths=[])
        assert result.ok is True

    def test_ok_true_with_action_id(self, handoff_with_action_id):
        result = validate(handoff_with_action_id, events_jsonl_paths=[])
        assert result.ok is True

    def test_ok_false_with_no_refs(self, tmp_path):
        f = tmp_path / "handoff.md"
        f.write_text("# Handoff\n\n## Summary\n\nNo references here.\n")
        result = validate(f, events_jsonl_paths=[])
        assert result.ok is False

    def test_ok_false_empty_handoff(self, tmp_path):
        f = tmp_path / "handoff.md"
        f.write_text("")
        result = validate(f, events_jsonl_paths=[])
        assert result.ok is False

    def test_refs_populated_with_event_id(self, handoff_with_event_id):
        result = validate(handoff_with_event_id, events_jsonl_paths=[])
        assert REAL_EVENT_ID in result.refs["event_ids"]

    def test_refs_populated_with_path(self, handoff_with_artifact_path):
        result = validate(handoff_with_artifact_path, events_jsonl_paths=[])
        assert len(result.refs["artifact_paths"]) >= 1

    def test_refs_populated_with_action_id(self, handoff_with_action_id):
        result = validate(handoff_with_action_id, events_jsonl_paths=[])
        assert any("graph-sprint-test-N2" in aid for aid in result.refs["action_ids"])

    def test_validate_accepts_raw_text(self):
        text = f"# Handoff\n\nEvent `{REAL_EVENT_ID}` confirmed.\n"
        result = validate(text, events_jsonl_paths=[])
        assert result.ok is True

    def test_validate_returns_validation_result_type(self, handoff_with_event_id):
        result = validate(handoff_with_event_id, events_jsonl_paths=[])
        assert isinstance(result, ValidationResult)

    def test_to_dict_has_ok_key(self, handoff_with_event_id):
        result = validate(handoff_with_event_id, events_jsonl_paths=[])
        d = result.to_dict()
        assert "ok" in d
        assert "refs" in d
        assert "missing_refs" in d


# ---------------------------------------------------------------------------
# Acceptance 2: Referenced event_id must exist in events.jsonl (5s timeout)
# ---------------------------------------------------------------------------

class TestEventIdLookup:
    def test_event_id_verified_when_in_events_jsonl(self, handoff_with_event_id, tmp_events):
        result = validate(
            handoff_with_event_id,
            events_jsonl_paths=[str(tmp_events)],
            timeout=5.0,
        )
        assert REAL_EVENT_ID in result.verified_event_ids

    def test_event_id_unverified_when_not_in_events_jsonl(self, tmp_path, tmp_events):
        f = tmp_path / "handoff.md"
        f.write_text(f"# Handoff\n\nEvent `{FAKE_EVENT_ID}` not in log.\n")
        result = validate(f, events_jsonl_paths=[str(tmp_events)], timeout=5.0)
        assert FAKE_EVENT_ID in result.unverified_event_ids
        # Still ok=True because a ref exists (the event_id itself is a reference)
        assert result.ok is True

    def test_timeout_fallback_graceful(self, handoff_with_event_id, tmp_path, monkeypatch):
        """When lookup times out, ok is still based on reference presence."""
        huge = tmp_path / "huge_events.jsonl"
        # Write a large events file (simulate slow read)
        huge.write_text("{}\n" * 1)

        import pane_handoff.evidence_validator as mod

        original_load = mod._load_event_ids_from_file

        def slow_load(path):
            import time
            time.sleep(10)  # Force timeout
            return original_load(path)

        monkeypatch.setattr(mod, "_load_event_ids_from_file", slow_load)

        result = validate(
            handoff_with_event_id,
            events_jsonl_paths=[str(huge)],
            timeout=0.05,  # Very short timeout
        )
        assert result.events_lookup_timeout is True
        # ok is based on reference presence, not event lookup
        assert result.ok is True

    def test_empty_events_jsonl_handled_gracefully(self, handoff_with_event_id, tmp_path):
        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        result = validate(
            handoff_with_event_id,
            events_jsonl_paths=[str(empty)],
            timeout=5.0,
        )
        assert result.events_lookup_timeout is False
        assert REAL_EVENT_ID in result.unverified_event_ids
        assert result.ok is True  # ref still present

    def test_missing_events_jsonl_handled_gracefully(self, handoff_with_event_id, tmp_path):
        nonexistent = tmp_path / "nonexistent.jsonl"
        result = validate(
            handoff_with_event_id,
            events_jsonl_paths=[str(nonexistent)],
            timeout=5.0,
        )
        assert result.ok is True
        assert REAL_EVENT_ID in result.unverified_event_ids

    def test_multiple_event_ids_all_checked(self, tmp_path, tmp_events):
        other_id = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
        f = tmp_path / "handoff.md"
        f.write_text(
            f"# Handoff\n\nEvents: `{REAL_EVENT_ID}` and `{other_id}`.\n"
        )
        result = validate(f, events_jsonl_paths=[str(tmp_events)], timeout=5.0)
        assert REAL_EVENT_ID in result.verified_event_ids
        assert other_id in result.unverified_event_ids


# ---------------------------------------------------------------------------
# Acceptance 3: Pure 'done/passed/finished' without ref → ok=False + missing_refs
# ---------------------------------------------------------------------------

class TestPureClaimKeywordRejection:
    def test_pure_done_returns_ok_false(self, handoff_pure_claims):
        result = validate(handoff_pure_claims, events_jsonl_paths=[])
        assert result.ok is False

    def test_pure_passed_returns_ok_false(self, tmp_path):
        f = tmp_path / "handoff.md"
        f.write_text("# Handoff\n\n## Summary\n\nPassed.\n")
        result = validate(f, events_jsonl_paths=[])
        assert result.ok is False

    def test_pure_finished_returns_ok_false(self, tmp_path):
        f = tmp_path / "handoff.md"
        f.write_text("# Handoff\n\n## Summary\n\nAll tests finished.\n")
        result = validate(f, events_jsonl_paths=[])
        assert result.ok is False

    def test_missing_refs_populated_on_failure(self, handoff_pure_claims):
        result = validate(handoff_pure_claims, events_jsonl_paths=[])
        assert len(result.missing_refs) > 0

    def test_missing_refs_contains_keyword(self, handoff_pure_claims):
        result = validate(handoff_pure_claims, events_jsonl_paths=[])
        keywords = [r["keyword"].lower() for r in result.missing_refs]
        assert any(k in keywords for k in ("done", "passed", "finished", "implemented"))

    def test_claim_with_nearby_ref_is_ok(self, handoff_mixed):
        """Claim word with nearby evidence reference should not fail."""
        result = validate(handoff_mixed, events_jsonl_paths=[])
        # 'done' and 'passed' each have nearby refs in handoff_mixed
        assert result.ok is True

    def test_all_claim_keywords_detected(self, tmp_path):
        f = tmp_path / "handoff.md"
        f.write_text(
            "# Handoff\n\ndone completed implemented fixed resolved passed finished\n"
        )
        result = validate(f, events_jsonl_paths=[])
        assert result.ok is False
        assert len(result.missing_refs) >= 5

    def test_case_insensitive_keyword_detection(self, tmp_path):
        f = tmp_path / "handoff.md"
        f.write_text("# Handoff\n\nDONE.\n\nPASSED.\n")
        result = validate(f, events_jsonl_paths=[])
        assert result.ok is False

    def test_missing_refs_has_section_context(self, handoff_pure_claims):
        result = validate(handoff_pure_claims, events_jsonl_paths=[])
        for r in result.missing_refs:
            assert "section" in r
            assert "keyword" in r


# ---------------------------------------------------------------------------
# Tests: _extract_refs internals
# ---------------------------------------------------------------------------

class TestExtractRefs:
    def test_extracts_uuid_event_id(self):
        text = f"event_id `{REAL_EVENT_ID}` was confirmed."
        refs = _extract_refs(text)
        assert REAL_EVENT_ID in refs["event_ids"]

    def test_extracts_absolute_path(self):
        text = "Output at `~/.solar/harness/sprints/foo.md`."
        refs = _extract_refs(text)
        assert len(refs["artifact_paths"]) >= 1

    def test_extracts_action_id(self):
        text = "dispatch-id: `graph-sprint-test-N1-20260520T100000Z`"
        refs = _extract_refs(text)
        assert any("graph-sprint-test-N1" in aid for aid in refs["action_ids"])

    def test_no_refs_returns_empty_lists(self):
        refs = _extract_refs("Hello world, nothing here.")
        assert refs["event_ids"] == []
        assert refs["action_ids"] == []

    def test_deduplicates_event_ids(self):
        text = f"`{REAL_EVENT_ID}` and `{REAL_EVENT_ID}` again."
        refs = _extract_refs(text)
        assert refs["event_ids"].count(REAL_EVENT_ID) == 1


# ---------------------------------------------------------------------------
# Tests: Real events.jsonl lookup (integration)
# ---------------------------------------------------------------------------

class TestRealEventsJsonlLookup:
    def test_real_events_jsonl_exists_and_readable(self):
        """Verify harness/run/events.jsonl is present and parseable."""
        events_path = (Path(__file__).resolve().parents[2] / 'harness') / "run" / "events.jsonl"
        assert events_path.exists(), f"events.jsonl not found at {events_path}"
        lines = events_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        assert len(lines) > 0, "events.jsonl is empty"
        # At least one line should be valid JSON
        parsed = 0
        for raw in lines[:10]:
            try:
                json.loads(raw)
                parsed += 1
            except Exception:
                pass
        assert parsed > 0, "No valid JSON lines in events.jsonl"

    def test_lookup_with_real_events_jsonl(self):
        """Lookup a fake event_id against real events.jsonl — should be unverified."""
        events_path = (Path(__file__).resolve().parents[2] / 'harness') / "run" / "events.jsonl"
        verified, unverified, timed_out, sources = _lookup_event_ids(
            [FAKE_EVENT_ID],
            [events_path],
            timeout=5.0,
        )
        assert timed_out is False
        assert FAKE_EVENT_ID in unverified
