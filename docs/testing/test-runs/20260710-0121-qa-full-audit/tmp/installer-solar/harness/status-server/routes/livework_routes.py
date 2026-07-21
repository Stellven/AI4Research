"""Livework HTTP routes for Solar-Harness status-server.

6 routes matching S02 interfaces.md response shapes:
  GET  /api/idle-state        — O1 idle/no-active visibility
  GET  /api/heartbeat-config   — O2 heartbeat configuration
  GET  /api/deadlock-alerts    — O2/O3 deadlock detection alerts
  GET  /api/requirement-coverage — requirement coverage summary
  POST /api/requirements       — O3/O4 PM-first requirement intake
  GET  /api/sprints/<sid>/next-step — O5 role next-step query

Flask Blueprint — register in app.py with:
    from status_server.routes.livework_routes import livework_bp
    app.register_blueprint(livework_bp)
"""

from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, jsonify, request

from harness.lib.livework.intake_state_machine import intake_requirement
from harness.lib.livework.idle_detector import detect_deadlock, is_idle, should_emit_heartbeat
from harness.lib.livework.state_aggregator import aggregate_pane_state, resolve_role

livework_bp = Blueprint("livework", __name__, url_prefix="/api")

EVENTS_PATH = Path.home() / ".solar" / "harness" / "events.jsonl"
SPRINTS_DIR = Path.home() / ".solar" / "harness" / "sprints"
HEARTBEAT_INTERVAL_DEFAULT = 300
DEADLOCK_DEADLINE_DEFAULT = 600


def _read_events(path: Path = EVENTS_PATH) -> list[dict]:
    if not path.exists():
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def _requirement_coverage_payload(sid: str | None = None) -> dict:
    candidates: list[str] = []
    if sid:
        candidates.append(sid)
    status_files = sorted(SPRINTS_DIR.glob("*.status.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in status_files:
        name = path.name.removesuffix(".status.json")
        if name not in candidates:
            candidates.append(name)
    for candidate in candidates:
        coverage_path = SPRINTS_DIR / f"{candidate}.coverage_report.json"
        verdict_path = SPRINTS_DIR / f"{candidate}.acceptance_verdict.json"
        if not coverage_path.exists():
            continue
        try:
            coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
            verdict = json.loads(verdict_path.read_text(encoding="utf-8")) if verdict_path.exists() else {}
        except Exception:
            continue
        summary = coverage.get("summary", {}) or {}
        return {
            "status": "ok",
            "sprint_id": candidate,
            "total": int(summary.get("total", 0)),
            "done": int(summary.get("done", 0)),
            "partial": int(summary.get("partial", 0)),
            "missing": int(summary.get("missing", 0)),
            "coverage_ratio": summary.get("coverage_ratio", 0),
            "graph_complete": bool(summary.get("graph_complete", False)),
            "acceptance_verdict": verdict.get("verdict", "N/A"),
        }
    return {
        "status": "missing",
        "sprint_id": sid or "",
        "total": 0,
        "done": 0,
        "partial": 0,
        "missing": 0,
        "coverage_ratio": 0,
        "graph_complete": False,
        "acceptance_verdict": "N/A",
    }


@livework_bp.route("/idle-state", methods=["GET"])
def get_idle_state():
    """O1: Return current idle/active harness state."""
    events = _read_events()
    pane_state = aggregate_pane_state(events)
    return jsonify({
        "is_idle": pane_state.is_idle,
        "active_panes": pane_state.active_panes,
        "queue_depth": pane_state.queue_depth,
        "idle_since": pane_state.last_heartbeat_ts if pane_state.is_idle else None,
        "last_heartbeat_ts": pane_state.last_heartbeat_ts,
    })


@livework_bp.route("/heartbeat-config", methods=["GET"])
def get_heartbeat_config():
    """O2: Return heartbeat configuration and current state."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    events = _read_events()
    pane_state = aggregate_pane_state(events)
    should_emit = should_emit_heartbeat(
        pane_state.last_heartbeat_ts, now, HEARTBEAT_INTERVAL_DEFAULT
    )
    return jsonify({
        "interval_seconds": HEARTBEAT_INTERVAL_DEFAULT,
        "should_emit_now": should_emit,
        "last_heartbeat_ts": pane_state.last_heartbeat_ts,
        "current_utc": now,
    })


@livework_bp.route("/deadlock-alerts", methods=["GET"])
def get_deadlock_alerts():
    """O2/O3: Return active deadlock alerts."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    events = _read_events()
    alerts = detect_deadlock(events, now, DEADLOCK_DEADLINE_DEFAULT)
    return jsonify({
        "active_deadlocks": [
            {"pane_id": a.pane_id, "elapsed_seconds": a.elapsed_seconds}
            for a in alerts
        ],
        "deadline_seconds": DEADLOCK_DEADLINE_DEFAULT,
        "checked_at": now,
    })


@livework_bp.route("/requirement-coverage", methods=["GET"])
def get_requirement_coverage():
    """Return latest requirement coverage summary for active or recent sprint."""
    sid = request.args.get("sid", "").strip() or None
    return jsonify(_requirement_coverage_payload(sid))


@livework_bp.route("/requirements", methods=["POST"])
def post_requirement():
    """O3/O4: Submit a requirement through PM-first intake FSM."""
    data = request.get_json(silent=True) or {}
    text = data.get("raw_requirement", "")
    source = data.get("source", "chat")
    submitted_by = data.get("submitted_by", "user")
    result = intake_requirement(text)
    if result.rejected:
        return jsonify({
            "status": "rejected",
            "error_code": "E_REQUIREMENT_TOO_VAGUE",
            "error_message": result.rejection_reason,
            "hint": "Include a clear goal and at least one acceptance criterion.",
        }), 400
    return jsonify({
        "status": "created",
        "sprint_id": result.sprint_id,
        "phase": result.state,
        "message": "Requirement captured. Pipeline: PM → Planner → Builder dispatch.",
    }), 201


@livework_bp.route("/sprints/<sid>/next-step", methods=["GET"])
def get_sprint_next_step(sid):
    """O5: Return current phase and next step for a sprint."""
    events = _read_events()
    role = resolve_role(events, sid)
    return jsonify({
        "sprint_id": role.sprint_id,
        "phase": role.phase,
        "next_action": role.next_action,
        "nodes": [
            {"id": n.id, "status": n.status, "goal": n.goal}
            for n in role.nodes
        ],
        "blocked_by": role.blocked_by,
    })
