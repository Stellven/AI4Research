"""Tests for livework/dispatch_visibility.py: build_visibility_view.

Acceptance:
- Pure function with sprints_dir / events_dir / now all parameter-injected
- Returns epic_id, child_sprints, ready_nodes, blocked_nodes, capability_use, last_event_ts, source
- Covers empty / partial-ready / all-blocked / events-missing degradation
- pytest exit 0, assertions >= 10
- No import of requests / httpx; no time.time() / datetime.now()
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import json
import pytest

from livework.dispatch_visibility import build_visibility_view


@pytest.fixture
def tmp_sprints(tmp_path):
    """Create a temporary sprints dir with test fixtures."""
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    return sprints


def _write_graph(sprints_dir, sprint_id, nodes, node_results=None):
    graph = {
        "schema_version": "solar.task_graph.v1",
        "sprint_id": sprint_id,
        "nodes": nodes,
        "node_results": node_results or {},
    }
    path = sprints_dir / f"{sprint_id}.task_graph.json"
    path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    return path


def _write_status(sprints_dir, sprint_id, status):
    data = {"status": status, "sprint_id": sprint_id}
    path = sprints_dir / f"{sprint_id}.status.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_events(sprints_dir, sprint_id, events):
    path = sprints_dir / f"{sprint_id}.events.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Tests: empty directory
# ---------------------------------------------------------------------------

class TestEmpty:
    def test_empty_sprints_dir_returns_empty_lists(self, tmp_sprints):
        result = build_visibility_view(
            "epic-test",
            sprints_dir=tmp_sprints,
            now="2026-05-14T12:00:00Z",
        )
        assert result["epic_id"] == "epic-test"
        assert result["child_sprints"] == []
        assert result["ready_nodes"] == []
        assert result["blocked_nodes"] == []
        assert result["last_event_ts"] is None
        assert result["source"] == "dispatch_visibility"

    def test_no_matching_epic_returns_empty(self, tmp_sprints):
        _write_graph(tmp_sprints, "sprint-other-epic-001", [
            {"id": "N1", "goal": "Do stuff", "depends_on": []},
        ])
        result = build_visibility_view(
            "epic-test",
            sprints_dir=tmp_sprints,
            now="2026-05-14T12:00:00Z",
        )
        assert result["child_sprints"] == []


# ---------------------------------------------------------------------------
# Tests: partial ready (some nodes passed, some ready)
# ---------------------------------------------------------------------------

class TestPartialReady:
    def test_partial_ready_nodes(self, tmp_sprints):
        _write_graph(tmp_sprints, "epic-test-s01-req", [
            {"id": "N1", "goal": "Schema", "depends_on": []},
            {"id": "N2", "goal": "Implement", "depends_on": ["N1"]},
            {"id": "N3", "goal": "Test", "depends_on": ["N2"]},
        ], node_results={"N1": {"status": "passed"}})
        _write_status(tmp_sprints, "epic-test-s01-req", "active")

        result = build_visibility_view(
            "epic-test",
            sprints_dir=tmp_sprints,
            now="2026-05-14T12:00:00Z",
        )
        assert len(result["child_sprints"]) == 1
        assert result["child_sprints"][0]["status"] == "active"
        # N2 is ready (N1 passed), N3 blocked (N2 not passed)
        ready_ids = [n["id"] for n in result["ready_nodes"]]
        blocked_ids = [n["id"] for n in result["blocked_nodes"]]
        assert "N2" in ready_ids
        assert "N3" in blocked_ids

    def test_capability_use_aggregated(self, tmp_sprints):
        _write_graph(tmp_sprints, "epic-test-s01-req", [
            {"id": "N1", "goal": "A", "depends_on": [], "required_capabilities": ["python", "testing"]},
            {"id": "N2", "goal": "B", "depends_on": [], "required_capabilities": ["python", "docs"]},
        ])
        caps = build_visibility_view(
            "epic-test", sprints_dir=tmp_sprints, now="2026-05-14T12:00:00Z",
        )["capability_use"]
        assert caps["python"] == 2
        assert caps["testing"] == 1
        assert caps["docs"] == 1


# ---------------------------------------------------------------------------
# Tests: all-blocked
# ---------------------------------------------------------------------------

class TestAllBlocked:
    def test_all_nodes_blocked_by_unmet_deps(self, tmp_sprints):
        _write_graph(tmp_sprints, "epic-test-s02-arch", [
            {"id": "N1", "goal": "Design", "depends_on": ["N0_missing"]},
            {"id": "N2", "goal": "Implement", "depends_on": ["N1"]},
        ])
        result = build_visibility_view(
            "epic-test",
            sprints_dir=tmp_sprints,
            now="2026-05-14T12:00:00Z",
        )
        assert len(result["ready_nodes"]) == 0
        assert len(result["blocked_nodes"]) == 2
        assert all("blocked_by" in n for n in result["blocked_nodes"])

    def test_passed_nodes_excluded_from_ready_and_blocked(self, tmp_sprints):
        _write_graph(tmp_sprints, "epic-test-s01-req", [
            {"id": "N1", "goal": "Done", "depends_on": []},
            {"id": "N2", "goal": "Ready", "depends_on": ["N1"]},
        ], node_results={"N1": {"status": "passed"}, "N2": {"status": "passed"}})
        result = build_visibility_view(
            "epic-test", sprints_dir=tmp_sprints, now="2026-05-14T12:00:00Z",
        )
        assert result["ready_nodes"] == []
        assert result["blocked_nodes"] == []


# ---------------------------------------------------------------------------
# Tests: events missing degradation
# ---------------------------------------------------------------------------

class TestEventsMissing:
    def test_no_events_file_returns_none_ts(self, tmp_sprints):
        _write_graph(tmp_sprints, "epic-test-s01-req", [
            {"id": "N1", "goal": "Work", "depends_on": []},
        ])
        result = build_visibility_view(
            "epic-test", sprints_dir=tmp_sprints, now="2026-05-14T12:00:00Z",
        )
        assert result["last_event_ts"] is None

    def test_events_present_returns_latest_ts(self, tmp_sprints):
        _write_graph(tmp_sprints, "epic-test-s01-req", [
            {"id": "N1", "goal": "Work", "depends_on": []},
        ])
        _write_events(tmp_sprints, "epic-test-s01-req", [
            {"event_type": "autopilot_heartbeat", "timestamp": "2026-05-14T11:00:00Z"},
            {"event_type": "autopilot_heartbeat", "timestamp": "2026-05-14T12:00:00Z"},
        ])
        result = build_visibility_view(
            "epic-test", sprints_dir=tmp_sprints, now="2026-05-14T13:00:00Z",
        )
        assert result["last_event_ts"] == "2026-05-14T12:00:00Z"

    def test_corrupt_events_file_degrades_gracefully(self, tmp_sprints):
        _write_graph(tmp_sprints, "epic-test-s01-req", [
            {"id": "N1", "goal": "Work", "depends_on": []},
        ])
        events_path = tmp_sprints / "epic-test-s01-req.events.jsonl"
        events_path.write_text("not valid json\n", encoding="utf-8")
        result = build_visibility_view(
            "epic-test", sprints_dir=tmp_sprints, now="2026-05-14T12:00:00Z",
        )
        assert result["last_event_ts"] is None

    def test_unreadable_graph_degrades_gracefully(self, tmp_sprints):
        bad_path = tmp_sprints / "epic-test-bad.task_graph.json"
        bad_path.write_text("not valid json", encoding="utf-8")
        result = build_visibility_view(
            "epic-test", sprints_dir=tmp_sprints, now="2026-05-14T12:00:00Z",
        )
        assert len(result["child_sprints"]) == 1
        assert result["child_sprints"][0]["status"] == "graph_unreadable"


# ---------------------------------------------------------------------------
# Static purity checks
# ---------------------------------------------------------------------------

class TestPurity:
    def test_no_requests_import(self):
        source = Path(__file__).resolve().parent.parent.parent / "lib" / "livework" / "dispatch_visibility.py"
        text = source.read_text()
        assert "requests" not in text
        assert "httpx" not in text
        assert "time.time()" not in text
        assert "datetime.now()" not in text
        assert "datetime.utcnow()" not in text

    def test_now_param_returned(self, tmp_sprints):
        result = build_visibility_view(
            "epic-test", sprints_dir=tmp_sprints, now="2026-05-14T15:30:00Z",
        )
        assert result["now"] == "2026-05-14T15:30:00Z"
