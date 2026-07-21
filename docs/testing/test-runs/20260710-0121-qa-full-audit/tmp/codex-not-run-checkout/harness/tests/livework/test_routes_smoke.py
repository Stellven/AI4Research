"""Smoke tests for livework Flask routes.

Uses Flask test client — no running server, no mocks, real livework modules.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BASE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BASE))
sys.path.insert(0, str(_BASE / "harness" / "lib"))

import importlib.util

from flask import Flask

# Load routes module from file path (status-server dir has dash, not a valid package)
_routes_path = _BASE / "harness" / "status-server" / "routes" / "livework_routes.py"
_spec = importlib.util.spec_from_file_location("livework_routes", _routes_path)
_routes_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_routes_mod)
livework_bp = _routes_mod.livework_bp


@pytest.fixture
def app(tmp_path: Path):
    app = Flask(__name__)
    app.register_blueprint(livework_bp)
    # Override events path for testing
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app: Flask):
    return app.test_client()


class TestGetIdleState:
    def test_returns_idle_when_no_events(self, client):
        resp = client.get("/api/idle-state")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "is_idle" in data
        assert data["is_idle"] is True
        assert data["active_panes"] == []
        assert data["queue_depth"] == 0

    def test_response_has_required_fields(self, client):
        resp = client.get("/api/idle-state")
        data = resp.get_json()
        assert "is_idle" in data
        assert "active_panes" in data
        assert "queue_depth" in data
        assert "last_heartbeat_ts" in data


class TestGetHeartbeatConfig:
    def test_returns_config(self, client):
        resp = client.get("/api/heartbeat-config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["interval_seconds"] == 300
        assert "should_emit_now" in data
        assert "current_utc" in data


class TestGetDeadlockAlerts:
    def test_returns_empty_when_no_events(self, client):
        resp = client.get("/api/deadlock-alerts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["active_deadlocks"] == []
        assert data["deadline_seconds"] == 600


class TestPostRequirement:
    def test_rejects_vague_requirement(self, client):
        resp = client.post(
            "/api/requirements",
            json={"raw_requirement": "fix bug"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "rejected"
        assert "error_code" in data

    def test_accepts_valid_requirement(self, client):
        resp = client.post(
            "/api/requirements",
            json={
                "raw_requirement": (
                    "Fix the status page to show idle state when no sprint is active "
                    "and all panes are idle — must display No Active Work"
                )
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "created"
        assert "phase" in data

    def test_missing_body_returns_400(self, client):
        resp = client.post("/api/requirements", content_type="application/json")
        assert resp.status_code == 400


class TestGetSprintNextStep:
    def test_returns_unknown_for_missing_sprint(self, client):
        resp = client.get("/api/sprints/nonexistent-sid/next-step")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["phase"] == "unknown"
        assert data["sprint_id"] == "nonexistent-sid"

    def test_response_has_required_fields(self, client):
        resp = client.get("/api/sprints/test-sid/next-step")
        data = resp.get_json()
        assert "phase" in data
        assert "next_action" in data
        assert "nodes" in data
        assert "blocked_by" in data
