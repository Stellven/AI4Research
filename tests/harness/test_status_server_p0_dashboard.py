#!/usr/bin/env python3
"""Regression coverage for the Phase-0 Solar Harness status-server dashboard."""

from __future__ import annotations

import importlib.util
import datetime
import json
import os
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path


ROOT = (Path(__file__).resolve().parents[2] / 'harness')
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


def request_json(base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    body = None
    headers = {"Accept": "application/json"}
    method = "GET"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(base_url + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            return response.status, data
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, json.loads(raw or "{}")


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
cmd="${2:-}"
mkdir -p "$HARNESS_DIR/sprints"
if [[ "$cmd" == "intake" ]]; then
  sid=sprint-p0-intake
  printf '{"sprint_id":"%s","status":"active","phase":"spec","title":"Fake Intake"}\n' "$sid" > "$HARNESS_DIR/sprints/$sid.status.json"
  echo "Sprint created: $sid"
elif [[ "$cmd" == "plan-verdict" || "$cmd" == "eval-verdict" || "$cmd" == "handoff-submit" ]]; then
  sid="${3:-}"
  verdict="${4:-}"
  status="active"
  phase="plan_reviewed"
  if [[ "$cmd" == "plan-verdict" && "$verdict" == "approve" ]]; then status="approved"; fi
  if [[ "$cmd" == "eval-verdict" && "$verdict" == "pass" ]]; then status="passed"; phase="eval_completed"; fi
  if [[ "$cmd" == "eval-verdict" && "$verdict" == "fail" ]]; then status="failed_review"; phase="eval_completed"; fi
  if [[ "$cmd" == "handoff-submit" ]]; then status="reviewing"; phase="implementation_completed"; fi
  printf '{"sprint_id":"%s","status":"%s","phase":"%s","title":"Fake Verdict"}\n' "$sid" "$status" "$phase" > "$HARNESS_DIR/sprints/$sid.status.json"
  echo "$cmd: $sid -> $status"
else
  echo "unsupported fake solar command: $*" >&2
  exit 2
fi
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
        # Keep this isolated Claude quota fixture independent of the owner's
        # real runtime selection (for example runtime=codex in user config).
        mod._read_user_config_runtime = lambda: ("claude", "test_fixture")
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

        projection = mod._orchestration_projection_payload(sid)
        projected = projection["data"]
        assert projection["ok"] is True
        assert projected["projection_schema"] == "solar.dashboard_projection.v1"
        assert projected["sprint_id"] == sid
        assert projected["sprint"]["sprint_id"] == sid
        assert "requirements" in projected
        assert "human_gates" in projected
        assert "dispatch" in projected
        assert projected["dispatch"]["capability_mismatch"]["present"] is True
        assert projected["operators"]
        assert projected["human_action_required"]["type"] == "capability_mismatch"
        assert projected["capability_mismatch"]["present"] is True
        assert projected["capability_mismatch"]["blocked_node"] == "N2"
        assert projected["available_actions"][0]["id"] == "view_artifacts"
        assert any(item["kind"] == "task_graph" for item in projected["artifacts"])
        assert projected["timeline"][0]["source"] == "event"

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
        assert settings["write_supported"] is True
        assert settings["source"] == "status-server settings scan"
        assert settings["runtime"]["value"] == "claude"
        assert settings["runtime"]["source"] == "test_fixture"

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

        verdict, verdict_status = mod._orchestration_verdict_payload("plan", sid, {"verdict": "approve", "reason": "scope ok"})
        assert verdict_status == 200, verdict
        assert verdict["ok"] is True
        assert verdict["projection"]["status"] == "approved"

        write(sprints / f"{sid}.handoff.md", "# Handoff\n")
        handoff, handoff_status = mod._orchestration_verdict_payload("handoff", sid, {})
        assert handoff_status == 200, handoff
        assert handoff["ok"] is True
        assert handoff["projection"]["status"] == "reviewing"

        html = mod._p0_dashboard_html()
        assert "AI4Research" in html
        assert "/static/p0.js" in html or "/static/p0-app/" in html

        server = mod.ThreadingHTTPServer(("127.0.0.1", 0), mod.StatusHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_address[1]}"

            status_code, http_projection = request_json(base_url, f"/orchestration/projection?sprint_id={sid}")
            assert status_code == 200, http_projection
            assert http_projection["ok"] is True
            assert http_projection["data"]["projection_schema"] == "solar.dashboard_projection.v1"
            assert http_projection["data"]["sprint_id"] == sid

            status_code, fast_projection = request_json(base_url, f"/orchestration/projection?sprint_id={sid}&mode=fast")
            assert status_code == 200, fast_projection
            assert fast_projection["ok"] is True
            assert fast_projection["data"]["projection_mode"] == "fast"
            assert fast_projection["data"]["events"] == []
            assert fast_projection["data"]["timeline"] == []
            assert fast_projection["data"]["lazy_slices"]["events"] == f"/events?sprint_id={sid}&limit=140"

            status_code, api_projection = request_json(base_url, f"/api/sprints/{sid}/projection")
            assert status_code == 200, api_projection
            assert api_projection["ok"] is True
            assert api_projection["data"]["sprint_id"] == sid

            write(
                sprints / f"{sid}.status.json",
                json.dumps({"sprint_id": sid, "status": "active", "phase": "planning_complete", "title": "P0 Dashboard"}),
            )
            status_code, http_plan = request_json(
                base_url,
                f"/api/sprints/{sid}/plan-verdict",
                {"verdict": "approve", "reason": "scope ok"},
            )
            assert status_code == 200, http_plan
            assert http_plan["ok"] is True
            assert http_plan["projection"]["status"] == "approved"

            write(sprints / f"{sid}.handoff.md", "# Handoff\n")
            status_code, http_handoff = request_json(base_url, f"/api/sprints/{sid}/handoff-submit", {})
            assert status_code == 200, http_handoff
            assert http_handoff["ok"] is True
            assert http_handoff["projection"]["status"] == "reviewing"

            status_code, http_eval = request_json(
                base_url,
                f"/api/sprints/{sid}/eval-verdict",
                {"verdict": "pass", "reason": "accepted"},
            )
            assert status_code == 200, http_eval
            assert http_eval["ok"] is True
            assert http_eval["projection"]["status"] == "passed"
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    print("PASS status-server p0 dashboard")


if __name__ == "__main__":
    main()
