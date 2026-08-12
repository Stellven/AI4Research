from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


SELECTOR = (
    "tests/journeys/phase22/code/test_j18_status_auth_workflow_states.py::"
    "test_p22_j18_status_auth_and_workflow_states"
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _request(url: str, *, token: str = "", method: str = "GET") -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Solar-Token"] = token
    request = Request(url, headers=headers, method=method)
    try:
        with urlopen(request, timeout=12) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                body: Any = json.loads(raw)
            except json.JSONDecodeError:
                body = raw
            return response.status, body
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        return exc.code, body
    except URLError as exc:
        return 0, {"error": str(exc)}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(port_file: Path, proc: subprocess.Popen[str], expected_harness: Path) -> int:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"status-server exited before readiness: {proc.returncode}")
        try:
            port = int(port_file.read_text(encoding="utf-8").strip())
            status, body = _request(f"http://127.0.0.1:{port}/runtime-info")
            if status == 200 and isinstance(body, dict) and body.get("harness_dir") == str(expected_harness):
                return port
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise AssertionError("status-server did not become ready")


def _state_artifacts(sprints: Path, sid: str, status: str, phase: str, node_statuses: tuple[str, str]) -> None:
    _write_json(
        sprints / f"{sid}.status.json",
        {"sprint_id": sid, "title": "Phase 22 status visibility", "status": status, "phase": phase},
    )
    _write_json(
        sprints / f"{sid}.task_dag.state.json",
        {
            "nodes": [
                {"id": "plan", "status": node_statuses[0], "depends_on": []},
                {
                    "id": "build",
                    "status": node_statuses[1],
                    "depends_on": ["plan"],
                    "blocked_reason": "human_gate_pending" if node_statuses[1] == "gate_blocked" else "",
                },
            ],
            "required_gates": ["planner", "evaluator"],
        },
    )


def test_p22_j18_status_auth_and_workflow_states(repo_root: Path, tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"p22-j18-status-auth-states-{stamp}-{os.getpid()}"
    run_dir = repo_root / "outputs" / "phase22-real-journeys" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    for name in ("events", "reports", "run", "sessions", "sprints", "state"):
        (harness / name).mkdir(parents=True, exist_ok=True)
    sid = "sprint-phase22-status-visibility"
    status_server = repo_root / "harness" / "lib" / "symphony" / "status-server.py"
    auth_token = "phase22-ephemeral-status-token"
    isolated_port = _free_port()
    port_file = harness / "run" / "status-server.port"
    port_file.unlink(missing_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "HARNESS_DIR": str(harness),
            "SOLAR_HARNESS_DIR": str(harness),
            "SOLAR_BIND_HOST": "127.0.0.1",
            "SOLAR_REQUIRE_TOKEN": "1",
            "SOLAR_AUTH_TOKEN": auth_token,
            "SOLAR_STATUS_PORT_START": str(isolated_port),
            "SOLAR_STATUS_PORT_END": str(isolated_port),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    command = [sys.executable, "-u", str(status_server)]
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    proc = subprocess.Popen(
        command,
        cwd=repo_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    auth_checks: dict[str, Any] = {}
    projections: list[dict[str, Any]] = []
    cleanup: dict[str, Any] = {}
    try:
        port = _wait_for_server(port_file, proc, harness)
        base = f"http://127.0.0.1:{port}"

        unauth_root_status, unauth_root_body = _request(base + "/")
        wrong_status, _ = _request(base + "/status", token="wrong-token")
        auth_root_status, auth_root_body = _request(base + "/", token=auth_token)
        query_root_status, query_root_body = _request(base + f"/?token={quote(auth_token, safe='')}")
        unauth_status, unauth_status_body = _request(base + "/status")
        unauth_head, unauth_head_body = _request(base + "/status", method="HEAD")
        health_status, health_body = _request(base + "/healthz")
        auth_checks = {
            "unauthenticated_dashboard_status": unauth_root_status,
            "unauthenticated_dashboard_disclosed_token": auth_token in str(unauth_root_body),
            "wrong_token_status": wrong_status,
            "authenticated_dashboard_status": auth_root_status,
            "authenticated_dashboard_received_token_bootstrap": auth_token in str(auth_root_body),
            "query_token_dashboard_status": query_root_status,
            "query_token_dashboard_received_token_bootstrap": auth_token in str(query_root_body),
            "unauthenticated_status_api_status": unauth_status,
            "unauthenticated_status_api_disclosed_token": auth_token in str(unauth_status_body),
            "unauthenticated_status_head": unauth_head,
            "unauthenticated_status_head_body_empty": unauth_head_body == "",
            "public_health_status": health_status,
            "public_health_body": health_body,
        }

        state_cases = [
            ("queued", "intake", ("pending", "pending")),
            ("active", "planning", ("running", "gate_blocked")),
            ("approved", "plan_reviewed", ("passed", "pending")),
            ("reviewing", "evaluation", ("passed", "running")),
            ("passed", "completed", ("passed", "passed")),
        ]
        for expected_status, phase, nodes in state_cases:
            _state_artifacts(sprints, sid, expected_status, phase, nodes)
            code, payload = _request(
                f"{base}/orchestration/projection?sprint_id={quote(sid)}&mode=fast",
                token=auth_token,
            )
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            projected_nodes = {
                str(item.get("id") or item.get("node_id")): str(item.get("status") or "")
                for item in data.get("nodes", [])
                if isinstance(item, dict)
            }
            projections.append(
                {
                    "expected_status": expected_status,
                    "expected_phase": phase,
                    "http_status": code,
                    "projected_status": data.get("status"),
                    "projected_phase": data.get("phase"),
                    "projected_nodes": projected_nodes,
                    "degraded_sources": payload.get("degraded_sources", []) if isinstance(payload, dict) else [],
                }
            )

        invalid_code, invalid_payload = _request(
            f"{base}/orchestration/projection?sprint_id={quote('../foreign', safe='')}",
            token=auth_token,
        )
        auth_checks["invalid_sprint_id_status"] = invalid_code
        auth_checks["invalid_sprint_id_error"] = invalid_payload.get("error") if isinstance(invalid_payload, dict) else ""
    finally:
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=5)
        runtime_files = [
            harness / "run" / "status-server.pid",
            harness / "run" / "status-server.port",
            harness / "run" / "status-server.token",
        ]
        stale_before_test_cleanup = [path.name for path in runtime_files if path.exists()]
        # Popen.terminate uses TerminateProcess on Windows, so Python cannot run the server's
        # finally block. This journey owns an isolated harness and removes those ephemeral files
        # itself; graceful lifecycle cleanup remains covered by the Linux/tmux J18 selector.
        for path in runtime_files:
            path.unlink(missing_ok=True)
        cleanup = {
            "process_exit_code": proc.returncode,
            "process_stopped": proc.poll() is not None,
            "runtime_files_left_by_forced_termination": stale_before_test_cleanup,
            "test_owned_runtime_files_removed": all(not path.exists() for path in runtime_files),
            "stdout_tail": (stdout or "")[-1200:].replace(auth_token, "[redacted]"),
            "stderr_tail": (stderr or "")[-1200:].replace(auth_token, "[redacted]"),
        }

    auth_ok = (
        auth_checks.get("unauthenticated_dashboard_status") == 403
        and auth_checks.get("unauthenticated_dashboard_disclosed_token") is False
        and auth_checks.get("wrong_token_status") == 403
        and auth_checks.get("authenticated_dashboard_status") == 200
        and auth_checks.get("authenticated_dashboard_received_token_bootstrap") is True
        and auth_checks.get("query_token_dashboard_status") == 200
        and auth_checks.get("query_token_dashboard_received_token_bootstrap") is True
        and auth_checks.get("unauthenticated_status_api_status") == 403
        and auth_checks.get("unauthenticated_status_api_disclosed_token") is False
        and auth_checks.get("unauthenticated_status_head") == 403
        and auth_checks.get("unauthenticated_status_head_body_empty") is True
        and auth_checks.get("public_health_status") == 200
        and auth_checks.get("invalid_sprint_id_status") == 400
    )
    states_ok = len(projections) == 5 and all(
        item["http_status"] == 200
        and item["projected_status"] == item["expected_status"]
        and item["projected_phase"] == item["expected_phase"]
        for item in projections
    )
    cleanup_ok = cleanup.get("process_stopped") is True and cleanup.get("test_owned_runtime_files_removed") is True
    passed = auth_ok and states_ok and cleanup_ok
    evidence = {
        "schema_version": "phase22.j18.status_auth_workflow_states.v1",
        "journey_id": "P22-J18",
        "run_id": run_id,
        "selector": SELECTOR,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip(),
        "production_entrypoint": str(status_server.relative_to(repo_root)),
        "command": command,
        "environment": {
            "bind_host": "127.0.0.1",
            "token_enforcement": True,
            "token_value_archived": False,
            "harness_dir": str(harness),
        },
        "auth_checks": auth_checks,
        "workflow_state_projections": projections,
        "cleanup": cleanup,
        "assertions": {
            "forced_token_boundary_rejects_unauthenticated_data_access": auth_ok,
            "five_runtime_workflow_states_project_truthfully": states_ok,
            "isolated_test_process_and_runtime_files_cleaned": cleanup_ok,
        },
        "observed_l2": [
            {
                "category": "Vertical",
                "level_2_feature": "Workflow & Platform Status Visibility",
                "status": "PASS_WITH_KNOWN_LIMITATIONS" if passed else "FAIL",
                "assertion_name": "j18_status_auth_and_workflow_state_projection",
                "evidence_path": "journey-result.json",
                "known_limitations": [
                    "Validated a real local status-server with forced token auth and queued, active/blocked, approved, reviewing, and passed projections. Remote-host transport, TLS termination, federated identity, and cross-host authorization were not tested."
                ],
            }
        ],
        "status": "PASS_WITH_KNOWN_LIMITATIONS" if passed else "FAIL",
    }
    _write_json(run_dir / "journey-result.json", evidence)
    assert passed, f"P22-J18 status auth/state journey failed; evidence: {run_dir / 'journey-result.json'}"
