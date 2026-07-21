"""End-to-end user flow tests for livework visibility.

Covers 5 outcome happy paths via real Flask test client — no mocks.
  O1: no-active-work idle visibility
  O2: heartbeat config + deadlock detection
  O3: submit requirement through PM-first pipeline
  O4: PM-first route flow
  O5: role next-step display
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_BASE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BASE))
sys.path.insert(0, str(_BASE / "harness" / "lib"))

from flask import Flask

# Load routes module from file (status-server dir has dash)
_routes_path = _BASE / "harness" / "status-server" / "routes" / "livework_routes.py"
_spec = importlib.util.spec_from_file_location("livework_routes", _routes_path)
_routes_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_routes_mod)
livework_bp = _routes_mod.livework_bp

_HTML = _BASE / "harness" / "status-server" / "templates" / "livework_panel.html"


@pytest.fixture
def app():
    app = Flask(
        __name__,
        template_folder=str(_BASE / "harness" / "status-server" / "templates"),
        static_folder=str(_BASE / "harness" / "status-server" / "static"),
    )
    app.register_blueprint(livework_bp)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ── O1: No Active Work — idle visibility ─────────────────────────

class TestO1NoActiveWork:
    """When no events exist, the system reports idle with empty panes."""

    def test_idle_state_shows_no_active_work(self, client):
        resp = client.get("/api/idle-state")
        assert resp.status_code == 200
        data = resp.get_json()
        # O1: system correctly reports idle state
        assert data["is_idle"] is True
        assert data["active_panes"] == []
        assert data["queue_depth"] == 0
        assert data["idle_since"] is None
        assert "last_heartbeat_ts" in data  # None when no events

    def test_heartbeat_shows_idle(self, client):
        resp = client.get("/api/heartbeat-config")
        data = resp.get_json()
        # idle system should not need heartbeat
        assert data["interval_seconds"] == 300
        assert isinstance(data["should_emit_now"], bool)

    def test_ui_panel_shows_unknown_when_no_events(self):
        html = _HTML.read_text(encoding="utf-8")
        card = html[html.index('id="no-active-work-card"'):]
        card_end = card.index("</div>", card.index("card-content")) + 6
        card_block = card[:card_end]
        assert "unknown" in card_block.lower()


# ── O2: Heartbeat + Deadlock Detection ────────────────────────────

class TestO2HeartbeatDeadlock:
    """Heartbeat config returns valid interval; deadlock shows none."""

    def test_heartbeat_config_structure(self, client):
        resp = client.get("/api/heartbeat-config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "interval_seconds" in data
        assert "should_emit_now" in data
        assert "last_heartbeat_ts" in data
        assert "current_utc" in data
        # current_utc is ISO format
        assert "T" in data["current_utc"] or "Z" in data["current_utc"]

    def test_deadlock_alerts_empty(self, client):
        resp = client.get("/api/deadlock-alerts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["active_deadlocks"] == []
        assert data["deadline_seconds"] > 0
        assert "checked_at" in data


# ── O3: Submit Requirement — PM-first flow ────────────────────────

class TestO3SubmitRequirement:
    """Submit a valid requirement through the intake pipeline."""

    def test_accepts_clear_requirement(self, client):
        resp = client.post(
            "/api/requirements",
            json={
                "raw_requirement": (
                    "Fix the status page to show idle state when no sprint is active "
                    "and all panes are idle — must display No Active Work card "
                    "with source tag showing data origin"
                )
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "created"
        assert "sprint_id" in data
        assert "sprint_id" in data  # empty string when no real state
        assert "phase" in data
        assert data["phase"] in ("dispatched", "planner_pending", "pm_drafting")

    def test_rejects_vague_requirement(self, client):
        resp = client.post(
            "/api/requirements",
            json={"raw_requirement": "fix stuff"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "rejected"
        assert "E_REQUIREMENT_TOO_VAGUE" in data["error_code"]
        assert data["error_message"] != ""


# ── O4: PM-first route flow ──────────────────────────────────────

class TestO4PMFirstFlow:
    """PM intake pipeline validates, drafts, and dispatches."""

    def test_intake_with_source_metadata(self, client):
        resp = client.post(
            "/api/requirements",
            json={
                "raw_requirement": (
                    "Add deadlock detection alert card to live-work panel — "
                    "must show pane ID and elapsed seconds, refresh every 30s"
                ),
                "source": "chat",
                "submitted_by": "user",
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "created"
        assert "phase" in data
        # pipeline message confirms PM → Planner → Builder dispatch
        assert "PM" in data["message"] or "Pipeline" in data["message"]

    def test_empty_json_body_returns_400(self, client):
        resp = client.post("/api/requirements", content_type="application/json")
        assert resp.status_code == 400


# ── O5: Role Next-Step Display ───────────────────────────────────

class TestO5RoleNextStep:
    """Query role next-step for a sprint, even nonexistent ones."""

    def test_next_step_for_known_sprint(self, client):
        resp = client.get("/api/sprints/test-sprint/next-step")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sprint_id"] == "test-sprint"
        assert "phase" in data
        assert "next_action" in data
        assert isinstance(data["nodes"], list)
        assert "blocked_by" in data

    def test_next_step_for_unknown_sprint(self, client):
        resp = client.get("/api/sprints/nonexistent-sid/next-step")
        data = resp.get_json()
        assert data["phase"] == "unknown"
        assert data["sprint_id"] == "nonexistent-sid"
        assert data["next_action"] is not None

    def test_ui_panel_has_role_next_step_card(self):
        html = _HTML.read_text(encoding="utf-8")
        assert 'id="role-next-step-card"' in html
        card = html[html.index('id="role-next-step-card"'):]
        assert "source-tag" in card[:card.index("</div>", card.index("source-tag")) + 6]
