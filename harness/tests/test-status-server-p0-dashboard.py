#!/usr/bin/env python3
"""Regression coverage for the Phase-0 Solar Harness status-server dashboard."""

from __future__ import annotations

import importlib.util
import datetime
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "lib" / "symphony" / "status-server.py"


def load_module():
    spec = importlib.util.spec_from_file_location("solar_status_server_p0_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    mod = load_module()
    with tempfile.TemporaryDirectory(prefix="solar-p0-status-") as td:
        root = Path(td)
        harness = root / "harness"
        sprints = harness / "sprints"
        sessions = harness / "sessions"
        events = harness / "events"
        reports = harness / "reports"
        state = harness / "state"
        sid = "sprint-p0-dashboard"
        today = datetime.datetime.now().astimezone().date().isoformat()

        write(
            sprints / f"{sid}.status.json",
            json.dumps({"sprint_id": sid, "status": "active", "phase": "planning_complete", "title": "P0 Dashboard"}),
        )
        write(
            sprints / f"{sid}.task_dag.state.json",
            json.dumps(
                {
                    "nodes": [
                        {"id": "N1", "status": "passed", "depends_on": [], "required_capabilities": ["planning"]},
                        {
                            "id": "N2",
                            "status": "gate_blocked",
                            "depends_on": ["N1"],
                            "required_capabilities": ["implementation"],
                            "blocked_reason": "no_matching_worker",
                        },
                    ],
                    "required_gates": ["planner", "evaluator"],
                }
            ),
        )
        write(
            sessions / sid / "events.jsonl",
            json.dumps({"ts": "2026-06-15T00:00:00Z", "sprint_id": sid, "type": "session_first"}) + "\n",
        )
        write(
            events / "all.jsonl",
            json.dumps({"ts": "2026-06-15T00:00:01Z", "sprint_id": sid, "type": "global_fallback"}) + "\n"
            + json.dumps({"ts": "2026-06-15T00:00:02Z", "sprint_id": "other", "type": "other"}) + "\n",
        )
        write(sprints / f"{sid}.report.html", "<!doctype html><h1>Report</h1>")
        write(sprints / sid / ".research" / "notes.md", "# Notes\n")
        write(state / "quota-footer" / "claude-sonnet.json", json.dumps({"date": today, "model_key": "claude-sonnet", "used_tokens": 44100000}))
        write(state / "pane-state.json", json.dumps([{"id": "%1:0.1", "role": "Planner", "state": "running", "model": "claude-sonnet"}]))
        write(
            state / "autopilot-state.json",
            json.dumps([
                {
                    "sprint_id": sid,
                    "node_id": "N2",
                    "decision": "no_matching_worker",
                    "blocked_reason": "no_matching_worker",
                    "target_pane": "",
                }
            ]),
        )

        fake_bin = root / "bin"
        fake_solar = fake_bin / "solar"
        write(
            fake_solar,
            """#!/usr/bin/env bash
set -eu
sid=sprint-p0-intake
mkdir -p "$HARNESS_DIR/sprints"
printf '{"sprint_id":"%s","status":"active","phase":"spec","title":"Fake Intake"}\n' "$sid" > "$HARNESS_DIR/sprints/$sid.status.json"
echo "Sprint created: $sid"
""",
        )
        fake_solar.chmod(0o755)

        mod.HARNESS_DIR = harness
        mod.SPRINTS_DIR = sprints
        mod.SESSIONS_DIR = sessions
        mod.EVENTS_DIR = events
        mod.ALL_EVENTS = events / "all.jsonl"
        mod.REPORTS_DIR = reports
        mod.STATUS_SERVER_DIR = harness / "status-server"
        mod.STATUS_SERVER_STATIC_DIR = mod.STATUS_SERVER_DIR / "static"
        mod.STATUS_SERVER_TEMPLATES_DIR = mod.STATUS_SERVER_DIR / "templates"
        mod.OPEN_ALLOWED_ROOTS = [harness]
        os.environ["PATH"] = f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"
        os.environ["HARNESS_DIR"] = str(harness)

        dashboard = mod._orchestration_dashboard_payload(sid)
        data = dashboard["data"]
        assert dashboard["ok"] is True
        assert data["focus_sprint_id"] == sid
        assert data["generated_from"]["task_graph_json"].endswith(f"{sid}.task_dag.state.json")
        assert data["progress"]["total_nodes"] == 2
        assert data["progress"]["blocked_nodes"] == 1
        assert data["progress"]["status_counts"]["gate_blocked"] == 1
        assert data["stall"]["is_stalled"] is True
        assert data["stall"]["state"] == "no_matching_worker"
        assert data["dag"]["nodes"][1]["route_decision"] == "no_matching_worker"
        assert data["capabilities"]["pane_supply"][0]["pane_id"] == "%1:0.1"

        sprint_index = mod._sprint_index_payload(limit=10)
        assert sprint_index["ok"] is True
        assert sprint_index["data"]["sprints"][0]["sprint_id"] == sid
        assert sprint_index["data"]["sprints"][0]["node_status_counts"]["gate_blocked"] == 1

        session_events = mod._events_for_request(sid, limit=10)
        assert [item["type"] for item in session_events] == ["session_first"]
        (sessions / sid / "events.jsonl").unlink()
        global_events = mod._events_for_request(sid, limit=10)
        assert [item["type"] for item in global_events] == ["global_fallback"]

        usage = mod._usage_payload(refresh=False)
        assert usage["source"] == "Claude log scan / quota-footer"
        assert usage["scope"] == "model-day estimate"
        assert usage["not_per_sprint"] is True
        assert usage["not_per_agent"] is True
        assert usage["models"][0]["used_tokens_label"] == "44.1M"

        settings = mod._settings_payload()
        assert settings["ok"] is True
        assert settings["write_supported"] is False
        assert settings["source"] == "status-server read-only config scan"

        deliverables = mod._sprint_deliverables_payload(sid)
        names = {item["name"] for item in deliverables["items"]}
        assert f"{sid}.report.html" in names
        assert "notes.md" in names
        first = deliverables["items"][0]
        assert mod._resolve_sprint_deliverable(sid, first["rel_path"]) is not None

        intake = mod._intake_payload({"task": "fake task for p0 dashboard route"})
        assert intake["ok"] is True
        assert intake["sprint_id"] == "sprint-p0-intake"
        assert (sprints / "sprint-p0-intake.status.json").exists()

        html = mod._p0_dashboard_html()
        assert "Solar Harness Status" in html
        assert "/static/p0.js" in html or "/static/p0-app/" in html

    print("PASS status-server p0 dashboard")


if __name__ == "__main__":
    main()
