"""Tests for status-server orchestration routes Blueprint.

Covers the five read-only endpoints:
  GET /orchestration/epics
  GET /orchestration/epics/<epic_id>
  GET /orchestration/sprints/<sid>
  GET /orchestration/panes
  GET /orchestration/events (poll mode)

All responses must use the envelope format:
  {ok, schema_version, generated_at, degraded_sources, data}
"""
from __future__ import annotations

import json
import sys
import pytest
from pathlib import Path

import importlib.util

# Locate harness root
_HARNESS = Path(__file__).resolve().parents[2]
_STATUS_SERVER_DIR = _HARNESS / "status-server"

# Register status-server as importable "status_server" package
def _register_status_server() -> None:
    if "status_server" in sys.modules:
        return
    # Load the package __init__
    spec = importlib.util.spec_from_file_location(
        "status_server",
        _STATUS_SERVER_DIR / "__init__.py",
        submodule_search_locations=[str(_STATUS_SERVER_DIR)],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["status_server"] = mod
    spec.loader.exec_module(mod)

    # Register sub-packages
    for pkg in ("routes",):
        pkg_dir = _STATUS_SERVER_DIR / pkg
        if pkg_dir.is_dir():
            pkg_spec = importlib.util.spec_from_file_location(
                f"status_server.{pkg}",
                pkg_dir / "__init__.py",
                submodule_search_locations=[str(pkg_dir)],
            )
            pkg_mod = importlib.util.module_from_spec(pkg_spec)
            sys.modules[f"status_server.{pkg}"] = pkg_mod
            pkg_spec.loader.exec_module(pkg_mod)

    # Ensure harness lib is in path (for orchestration_routes imports)
    lib_path = str(_HARNESS / "lib")
    if lib_path not in sys.path:
        sys.path.insert(0, lib_path)

_register_status_server()

from flask import Flask


# ---------------------------------------------------------------------------
# Helpers to build minimal fixture data
# ---------------------------------------------------------------------------

def _sprint_status(sprint_id: str, epic_id: str, status: str = "active") -> dict:
    return {
        "sprint_id": sprint_id,
        "epic_id": epic_id,
        "title": f"Test sprint {sprint_id}",
        "status": status,
        "phase": "in_progress",
        "priority": 1,
    }


def _pane_state() -> dict:
    return {
        "panes": [
            {"id": "pane-0", "role": "builder", "state": "idle", "model": "claude", "mtime": 0},
            {"id": "pane-1", "role": "evaluator", "state": "active", "model": "gemini", "mtime": 0},
        ]
    }


def _autopilot_state() -> dict:
    return {
        "routing_decisions": [
            {
                "sprint_id": "sprint-abc",
                "node_id": "N1",
                "decision": "dispatched",
                "target_pane": "pane-0",
                "required_capabilities": ["python"],
                "provided_capabilities": ["python"],
                "blocked_by": [],
            }
        ]
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def harness_tree(tmp_path):
    sprints = tmp_path / "sprints"
    state = tmp_path / "state"
    sprints.mkdir()
    state.mkdir()

    # Write two sprints belonging to the same epic.
    # Filenames include the epic_id so _list_epics() count-by-name logic works.
    for sid in ("epic-test-sprint-001", "epic-test-sprint-002"):
        (sprints / f"{sid}.status.json").write_text(
            json.dumps(_sprint_status(sid, "epic-test"))
        )
    (sprints / "sprint-001.status.json").write_text(
        json.dumps(_sprint_status("sprint-001", "epic-other"))
    )
    (sprints / "sprint-abc.status.json").write_text(
        json.dumps(_sprint_status("sprint-abc", "epic-dashboard", status="active"))
    )
    (sprints / "sprint-abc.task_graph.json").write_text(json.dumps({
        "sprint_id": "sprint-abc",
        "required_gates": ["G_DASHBOARD"],
        "nodes": [
            {
                "id": "N1",
                "goal": "Build dashboard payload",
                "depends_on": [],
                "status": "passed",
                "required_capabilities": ["python"],
                "estimated_cost": 1,
                "gate": "G_DASHBOARD",
                "write_scope": ["status-server/*"],
                "read_scope": ["sprints/*.prd.md"],
            },
            {
                "id": "N2",
                "goal": "Render blocker diagnostics",
                "depends_on": ["N1"],
                "status": "blocked",
                "required_capabilities": ["frontend", "observability"],
                "estimated_cost": 2,
                "gate": "G_DASHBOARD",
                "write_scope": ["ui/*"],
                "read_scope": ["sprints/*.design.md"],
            },
        ],
    }))

    (state / "pane-state.json").write_text(json.dumps(_pane_state()))
    (state / "autopilot-state.json").write_text(json.dumps(_autopilot_state()))

    events_jsonl = tmp_path / "events.jsonl"
    events_jsonl.write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "event": "autopilot_capability_dispatched", "node_id": "N1", "pane": "pane-0"}) + "\n"
    )

    return {"root": tmp_path, "sprints": sprints, "state": state, "events": events_jsonl}


@pytest.fixture
def app(harness_tree, monkeypatch):
    import status_server.routes.orchestration_routes as routes_mod

    monkeypatch.setattr(routes_mod, "SPRINTS_DIR", harness_tree["sprints"])
    monkeypatch.setattr(routes_mod, "STATE_DIR", harness_tree["state"])
    monkeypatch.setattr(routes_mod, "EVENTS_JSONL", harness_tree["events"])

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    from status_server.routes.orchestration_routes import orchestration_bp
    flask_app.register_blueprint(orchestration_bp)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Helper: assert envelope shape
# ---------------------------------------------------------------------------

def _assert_envelope(body: dict) -> dict:
    assert body.get("ok") is True, f"ok != True: {body}"
    assert "schema_version" in body
    assert "generated_at" in body
    assert "degraded_sources" in body
    assert "data" in body
    return body["data"]


# ---------------------------------------------------------------------------
# GET /orchestration/epics
# ---------------------------------------------------------------------------

class TestListEpics:
    def test_returns_ok_envelope(self, client):
        r = client.get("/orchestration/epics")
        assert r.status_code == 200
        body = r.get_json()
        data = _assert_envelope(body)
        assert "epics" in data

    def test_lists_epic_ids(self, client):
        r = client.get("/orchestration/epics")
        data = r.get_json()["data"]
        epic_ids = [e["epic_id"] for e in data["epics"]]
        assert "epic-test" in epic_ids

    def test_sprint_count_correct(self, client):
        r = client.get("/orchestration/epics")
        epics = r.get_json()["data"]["epics"]
        epic = next(e for e in epics if e["epic_id"] == "epic-test")
        assert epic["sprint_count"] == 2

    def test_schema_version_is_orchestration_v1(self, client):
        r = client.get("/orchestration/epics")
        assert "solar.orchestration.v1" in r.get_json()["schema_version"]


class TestDashboard:
    def test_dashboard_route_returns_html(self, client):
        r = client.get("/orchestration")
        assert r.status_code == 200
        assert b"Epic Runtime Dashboard" in r.data
        assert b"dag-flow" in r.data

    def test_dashboard_payload_contains_dag_resources_and_diagnostics(self, client):
        r = client.get("/orchestration/dashboard?sprint_id=sprint-abc")
        assert r.status_code == 200
        data = _assert_envelope(r.get_json())
        assert data["focus_sprint_id"] == "sprint-abc"
        assert data["progress"]["total_nodes"] == 2
        assert data["resources"]["estimated_total_cost"] == 3.0
        assert data["dag"]["edges"] == [{"from": "N1", "to": "N2"}]
        assert data["capabilities"]["demand"]["frontend"] == 1
        assert data["blocker_diagnostics"]

    def test_dashboard_payload_reports_missing_task_graph_guidance(self, client):
        r = client.get("/orchestration/dashboard?sprint_id=sprint-001")
        body = r.get_json()
        data = _assert_envelope(body)
        assert any("task_graph" in item for item in body["degraded_sources"])
        assert data["blocker_diagnostics"][0]["kind"] == "task_graph"
        assert "graph-scheduler validate" in " ".join(data["blocker_diagnostics"][0]["guidance"])


# ---------------------------------------------------------------------------
# GET /orchestration/epics/<epic_id>
# ---------------------------------------------------------------------------

class TestGetEpic:
    def test_returns_child_sprints(self, client):
        r = client.get("/orchestration/epics/epic-test")
        assert r.status_code == 200
        data = _assert_envelope(r.get_json())
        assert len(data["child_sprints"]) == 2

    def test_returns_gate_summary(self, client):
        r = client.get("/orchestration/epics/epic-test")
        data = r.get_json()["data"]
        gs = data["gate_status_summary"]
        assert "total" in gs
        assert gs["total"] == 2

    def test_missing_epic_returns_empty_children(self, client):
        r = client.get("/orchestration/epics/epic-nonexistent")
        assert r.status_code == 200
        data = r.get_json()["data"]
        assert data["child_sprints"] == []

    def test_epic_id_in_response(self, client):
        r = client.get("/orchestration/epics/epic-test")
        data = r.get_json()["data"]
        assert data["epic_id"] == "epic-test"

    def test_degraded_sources_when_no_task_graph(self, client):
        r = client.get("/orchestration/epics/epic-test")
        body = r.get_json()
        assert any("task_graph" in s for s in body["degraded_sources"])


# ---------------------------------------------------------------------------
# GET /orchestration/sprints/<sid>
# ---------------------------------------------------------------------------

class TestGetSprint:
    def test_known_sprint_returns_ok(self, client):
        r = client.get("/orchestration/sprints/sprint-001")
        assert r.status_code == 200
        data = _assert_envelope(r.get_json())
        assert data["sprint_id"] == "sprint-001"

    def test_unknown_sprint_returns_404(self, client):
        r = client.get("/orchestration/sprints/sprint-does-not-exist")
        assert r.status_code == 404
        body = r.get_json()
        assert body["ok"] is False

    def test_sprint_contains_routing_fields(self, client):
        r = client.get("/orchestration/sprints/sprint-001")
        data = r.get_json()["data"]
        assert "node_capability_hits" in data
        assert "routing_decisions" in data

    def test_sprint_contains_sidecar_verifier_refs(self, client):
        r = client.get("/orchestration/sprints/sprint-001")
        data = r.get_json()["data"]
        assert "sidecar_refs" in data
        assert "verifier_refs" in data

    def test_sprint_degraded_when_no_task_graph(self, client):
        r = client.get("/orchestration/sprints/sprint-001")
        body = r.get_json()
        assert any("task_graph" in s for s in body["degraded_sources"])


# ---------------------------------------------------------------------------
# GET /orchestration/panes
# ---------------------------------------------------------------------------

class TestGetPanes:
    def test_returns_panes_list(self, client):
        r = client.get("/orchestration/panes")
        assert r.status_code == 200
        data = _assert_envelope(r.get_json())
        assert "panes" in data
        assert len(data["panes"]) == 2

    def test_pane_has_required_fields(self, client):
        r = client.get("/orchestration/panes")
        pane = r.get_json()["data"]["panes"][0]
        for field in ("pane_id", "role", "state", "provided_capabilities"):
            assert field in pane, f"missing field: {field}"

    def test_in_use_by_derived_from_routing_decisions(self, client):
        r = client.get("/orchestration/panes")
        panes = r.get_json()["data"]["panes"]
        pane0 = next((p for p in panes if p["pane_id"] == "pane-0"), None)
        assert pane0 is not None
        # autopilot-state has decision=dispatched for pane-0, sprint-abc
        assert pane0["in_use_by"] == "sprint-abc"


# ---------------------------------------------------------------------------
# GET /orchestration/events (poll mode)
# ---------------------------------------------------------------------------

class TestGetEvents:
    def test_returns_ok_envelope(self, client):
        r = client.get("/orchestration/events")
        assert r.status_code == 200
        data = _assert_envelope(r.get_json())
        assert "events" in data

    def test_returns_capability_events(self, client):
        r = client.get("/orchestration/events")
        events = r.get_json()["data"]["events"]
        assert len(events) >= 1
        assert any("autopilot_capability" in e.get("event", "") for e in events)

    def test_sse_content_type_when_accept_header(self, client):
        r = client.get("/orchestration/events?since=",
                       headers={"Accept": "text/event-stream"})
        # SSE response should be streaming
        assert "text/event-stream" in r.content_type
