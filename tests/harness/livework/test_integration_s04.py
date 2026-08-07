"""Integration tests for S04 orchestration-ui slice.

Uses Flask test client (real HTTP, no mocks) to verify all 5 livework routes
return 2xx. Also loads livework_panel.html and verifies 4 DOM IDs + source tags.
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

# Load routes module (status-server dir has dash)
_routes_path = _BASE / "harness" / "status-server" / "routes" / "livework_routes.py"
_spec = importlib.util.spec_from_file_location("livework_routes", _routes_path)
_routes_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_routes_mod)
livework_bp = _routes_mod.livework_bp

_HTML = _BASE / "harness" / "status-server" / "templates" / "livework_panel.html"


@pytest.fixture
def app():
    app = Flask(__name__, template_folder=str(_BASE / "harness" / "status-server" / "templates"))
    app.register_blueprint(livework_bp)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ── Route integration tests ──────────────────────────────────────

class TestIdleStateRoute:
    def test_get_idle_state_200(self, client):
        resp = client.get("/api/idle-state")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_idle"] is True
        assert isinstance(data["active_panes"], list)
        assert isinstance(data["queue_depth"], int)
        assert "last_heartbeat_ts" in data

    def test_idle_state_no_active_panes_when_no_events(self, client):
        resp = client.get("/api/idle-state")
        data = resp.get_json()
        assert data["active_panes"] == []
        assert data["queue_depth"] == 0


class TestHeartbeatConfigRoute:
    def test_get_heartbeat_config_200(self, client):
        resp = client.get("/api/heartbeat-config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["interval_seconds"] == 300
        assert isinstance(data["should_emit_now"], bool)
        assert "current_utc" in data
        assert "last_heartbeat_ts" in data


class TestDeadlockAlertsRoute:
    def test_get_deadlock_alerts_200(self, client):
        resp = client.get("/api/deadlock-alerts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["active_deadlocks"], list)
        assert data["active_deadlocks"] == []
        assert data["deadline_seconds"] == 600
        assert "checked_at" in data


class TestRequirementsRoute:
    def test_post_valid_requirement_201(self, client):
        resp = client.post(
            "/api/requirements",
            json={"raw_requirement": "Fix status page to show idle state when no sprint active and all panes idle — must display No Active Work"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "created"
        assert "sprint_id" in data
        assert "phase" in data

    def test_post_vague_requirement_400(self, client):
        resp = client.post("/api/requirements", json={"raw_requirement": "fix bug"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "rejected"
        assert "error_code" in data

    def test_post_empty_body_400(self, client):
        resp = client.post("/api/requirements", content_type="application/json")
        assert resp.status_code == 400


class TestSprintNextStepRoute:
    def test_get_next_step_200(self, client):
        resp = client.get("/api/sprints/test-sprint-id/next-step")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sprint_id"] == "test-sprint-id"
        assert "phase" in data
        assert "next_action" in data
        assert isinstance(data["nodes"], list)
        assert "blocked_by" in data

    def test_get_next_step_unknown_sprint(self, client):
        resp = client.get("/api/sprints/nonexistent/next-step")
        data = resp.get_json()
        assert data["phase"] == "unknown"


# ── UI template verification ─────────────────────────────────────

class TestLiveworkPanelTemplate:
    @pytest.fixture
    def html(self):
        return _HTML.read_text(encoding="utf-8")

    def test_all_four_dom_ids_present(self, html):
        for dom_id in ["no-active-work-card", "role-next-step-card",
                        "deadlock-alerts-card", "events-tail-card"]:
            assert f'id="{dom_id}"' in html, f"Missing #{dom_id}"

    def test_source_tags_in_cards(self, html):
        assert html.count("source-tag") >= 4

    def test_empty_state_shows_unknown(self, html):
        assert html.count("unknown") >= 4

    def test_js_script_reference(self, html):
        assert "/static/livework_panel.js" in html
