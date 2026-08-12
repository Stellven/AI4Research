from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest


SELECTOR = (
    "tests/journeys/phase22/code/test_j18_real_linux_status_lifecycle.py::"
    "test_p22_j18_real_linux_status_lifecycle"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _tail(text: str, limit: int = 2400) -> str:
    return (text or "")[-limit:]


def _redact_status_token(text: str) -> str:
    return re.sub(r'window\.__SOLAR_TOKEN__="[^"]+"', 'window.__SOLAR_TOKEN__="[redacted]"', text or "")


def _run(
    run_dir: Path,
    label: str,
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int = 60,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        proc = subprocess.CompletedProcess(
            argv,
            124,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr if isinstance(exc.stderr, str) else f"timed out after {timeout}s",
        )
        timed_out = True
    except FileNotFoundError as exc:
        proc = subprocess.CompletedProcess(argv, 127, stdout="", stderr=str(exc))
        timed_out = False

    idx = len(list((run_dir / "stdout").glob("*.txt"))) + 1
    stdout_path = run_dir / "stdout" / f"{idx:02d}-{label}.txt"
    stderr_path = run_dir / "stderr" / f"{idx:02d}-{label}.txt"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(proc.stdout or "", encoding="utf-8", errors="replace")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8", errors="replace")
    return {
        "label": label,
        "argv": argv,
        "cwd": str(cwd),
        "exit_code": proc.returncode,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout_path": str(stdout_path.relative_to(run_dir)),
        "stderr_path": str(stderr_path.relative_to(run_dir)),
        "stdout_tail": _tail(proc.stdout),
        "stderr_tail": _tail(proc.stderr),
    }


def _http_json(url: str, *, token: str | None = None) -> dict[str, Any]:
    headers = {"X-Solar-Token": token} if token else {}
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=10) as response:
            body = _redact_status_token(response.read().decode("utf-8", "replace"))
            if response.headers.get_content_type() == "application/json":
                payload: Any = json.loads(body)
            else:
                payload = body
            return {"status": response.status, "content_type": response.headers.get_content_type(), "body": payload}
    except HTTPError as exc:
        return {"status": exc.code, "content_type": exc.headers.get_content_type(), "error": str(exc), "body_prefix": exc.read().decode("utf-8", "replace")[:500]}
    except URLError as exc:
        return {"status": 0, "content_type": "", "error": str(exc), "body": None}


def _http_text(url: str, *, token: str | None = None) -> dict[str, Any]:
    headers = {"X-Solar-Token": token} if token else {}
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=10) as response:
            body = _redact_status_token(response.read().decode("utf-8", "replace"))
            return {"status": response.status, "content_type": response.headers.get_content_type(), "body_prefix": body[:500]}
    except HTTPError as exc:
        return {"status": exc.code, "content_type": exc.headers.get_content_type(), "error": str(exc), "body_prefix": exc.read().decode("utf-8", "replace")[:500]}
    except URLError as exc:
        return {"status": 0, "content_type": "", "error": str(exc), "body_prefix": ""}


def _wait_for_port(port_file: Path, deadline_seconds: int = 20) -> str:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        if port_file.exists() and port_file.read_text(encoding="utf-8").strip():
            return port_file.read_text(encoding="utf-8").strip()
        time.sleep(0.5)
    return ""


def _wait_for_text(path: Path, deadline_seconds: int = 20) -> str:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return path.read_text(encoding="utf-8").strip()
        time.sleep(0.5)
    return ""


def test_p22_j18_real_linux_status_lifecycle(repo_root: Path, tmp_path: Path) -> None:
    if platform.system().lower() != "linux":
        pytest.skip("P22-J18 real Linux lifecycle must run on Linux or SolarUbuntu WSL.")
    if shutil.which("tmux") is None:
        pytest.skip("tmux is required for the status-server-backed TMUX lifecycle.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"p22-j18-real-linux-status-{stamp}-{os.getpid()}"
    run_dir = repo_root / "outputs" / "phase22-real-journeys" / run_id
    artifact_dir = run_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    sandbox_home = tmp_path / "home"
    solar_home = sandbox_home / ".solar"
    claude_dir = sandbox_home / ".claude"
    sandbox_home_b = tmp_path / "home-b"
    solar_home_b = sandbox_home_b / ".solar"
    claude_dir_b = sandbox_home_b / ".claude"
    tmux_tmpdir = tmp_path / "tmux"
    tmux_tmpdir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(sandbox_home),
            "USERPROFILE": str(sandbox_home),
            "SOLAR_HOME": str(solar_home),
            "CLAUDE_DIR": str(claude_dir),
            "HARNESS_DIR": str(solar_home / "harness"),
            "SOLAR_HARNESS_DIR": str(solar_home / "harness"),
            "SOLAR_PANE_RUNTIME": "codex",
            "PHASE22_SELECTED_RUNTIME": "codex",
            "SOLAR_NO_MCP": "true",
            "SOLAR_NO_HOOKS": "true",
            "SOLAR_BIND_HOST": "127.0.0.1",
            "TERM": "dumb",
            "TMUX_TMPDIR": str(tmux_tmpdir),
        }
    )
    env_b = dict(env)
    env_b.update(
        {
            "HOME": str(sandbox_home_b),
            "USERPROFILE": str(sandbox_home_b),
            "SOLAR_HOME": str(solar_home_b),
            "CLAUDE_DIR": str(claude_dir_b),
            "HARNESS_DIR": str(solar_home_b / "harness"),
            "SOLAR_HARNESS_DIR": str(solar_home_b / "harness"),
        }
    )

    commands: list[dict[str, Any]] = []
    http_checks: dict[str, Any] = {}
    tmux_checks: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    install_receipt_seen = False
    started_at = _utc_now()
    distro = {}

    try:
        commands.append(
            _run(
                run_dir,
                "install-kernel-harness",
                [
                    "bash",
                    str(repo_root / "install.sh"),
                    "--yes",
                    "--components",
                    "kernel,harness",
                    "--solar-home",
                    str(solar_home),
                    "--claude-dir",
                    str(claude_dir),
                    "--skip-llm-cli",
                    "--skip-py-deps",
                    "--no-hooks",
                    "--no-mcp",
                    "--set",
                    "runtime=codex",
                ],
                cwd=repo_root,
                env=env,
                timeout=180,
            )
        )
        distro_record = _run(
            run_dir,
            "distro-release",
            ["bash", "-lc", ". /etc/os-release; printf '%s\\n%s\\n' \"$ID\" \"$VERSION_ID\""],
            cwd=repo_root,
            env=env,
            timeout=30,
        )
        commands.append(distro_record)
        distro_lines = distro_record["stdout_tail"].strip().splitlines()
        distro = {
            "id": distro_lines[0] if distro_lines else "unknown",
            "version_id": distro_lines[1] if len(distro_lines) > 1 else "unknown",
            "wsl_distro_name": os.environ.get("WSL_DISTRO_NAME", ""),
        }
        solar_bin = solar_home / "bin" / "solar"
        harness_script = solar_home / "harness" / "solar-harness.sh"
        install_receipt_seen = (solar_home / "install-receipt.json").exists()
        commands.append(_run(run_dir, "doctor-json", [str(solar_bin), "doctor", "--json"], cwd=repo_root, env=env, timeout=60))
        commands.append(_run(run_dir, "status-json", [str(solar_bin), "status", "--json"], cwd=repo_root, env=env, timeout=60))
        commands.append(_run(run_dir, "status-server-start", [str(harness_script), "status-server", "start"], cwd=repo_root, env=env, timeout=60))

        port_file = solar_home / "harness" / "run" / "status-server.port"
        token_file = solar_home / "harness" / "run" / "status-server.token"
        port = _wait_for_port(port_file)
        if not port:
            match = re.search(r"port:\s*(\d+)", commands[-1]["stdout_tail"])
            port = match.group(1) if match else "8765"
        token = _wait_for_text(token_file) or None
        base = f"http://127.0.0.1:{port}"
        if port:
            http_checks["healthz"] = _http_text(f"{base}/healthz", token=token)
            http_checks["runtime_info"] = _http_json(f"{base}/runtime-info", token=token)
            http_checks["status"] = _http_json(f"{base}/status", token=token)
            http_checks["events"] = _http_json(f"{base}/events?limit=5", token=token)
            http_checks["settings"] = _http_json(f"{base}/settings", token=token)
            http_checks["root"] = _http_text(f"{base}/", token=token)

        commands.append(_run(run_dir, "status-server-status", [str(harness_script), "status-server", "status"], cwd=repo_root, env=env, timeout=60))
        commands.append(_run(run_dir, "tmux-list-sessions", ["tmux", "list-sessions", "-F", "#{session_name}"], cwd=repo_root, env=env, timeout=30))

        tmux_session_line = commands[-1]["stdout_tail"]
        tmux_checks = {
            "port_file": str(port_file),
            "port": port,
            "status_server_pid_file_exists": (solar_home / "harness" / "run" / "status-server.pid").exists(),
            "status_server_tmux_session_observed": "solar-harness-status-server-" in tmux_session_line,
            "tmux_sessions_tail": tmux_session_line,
        }

        commands.append(
            _run(
                run_dir,
                "install-second-kernel-harness",
                [
                    "bash",
                    str(repo_root / "install.sh"),
                    "--yes",
                    "--components",
                    "kernel,harness",
                    "--solar-home",
                    str(solar_home_b),
                    "--claude-dir",
                    str(claude_dir_b),
                    "--skip-llm-cli",
                    "--skip-py-deps",
                    "--no-hooks",
                    "--no-mcp",
                    "--set",
                    "runtime=codex",
                ],
                cwd=repo_root,
                env=env_b,
                timeout=180,
            )
        )
        solar_bin_b = solar_home_b / "bin" / "solar"
        harness_script_b = solar_home_b / "harness" / "solar-harness.sh"
        commands.append(_run(run_dir, "second-status-server-start", [str(harness_script_b), "status-server", "start"], cwd=repo_root, env=env_b, timeout=60))
        port_file_b = solar_home_b / "harness" / "run" / "status-server.port"
        token_file_b = solar_home_b / "harness" / "run" / "status-server.token"
        port_b = _wait_for_port(port_file_b)
        token_b = _wait_for_text(token_file_b) or None
        base_b = f"http://127.0.0.1:{port_b}"
        http_checks["second_healthz"] = _http_text(f"{base_b}/healthz", token=token_b) if port_b else {"status": 0}
        http_checks["second_runtime_info"] = _http_json(f"{base_b}/runtime-info", token=token_b) if port_b else {"status": 0}
        commands.append(_run(run_dir, "primary-status-server-stop-while-second-live", [str(harness_script), "status-server", "stop"], cwd=repo_root, env=env, timeout=60))
        http_checks["second_healthz_after_primary_stop"] = _http_text(f"{base_b}/healthz", token=token_b) if port_b else {"status": 0}
        commands.append(_run(run_dir, "primary-uninstall-while-second-live", [str(solar_bin), "uninstall", "--yes"], cwd=repo_root, env=env, timeout=120))
        http_checks["second_healthz_after_primary_uninstall"] = _http_text(f"{base_b}/healthz", token=token_b) if port_b else {"status": 0}
        commands.append(_run(run_dir, "tmux-list-after-primary-uninstall", ["tmux", "list-sessions", "-F", "#{session_name}"], cwd=repo_root, env=env_b, timeout=30))
        tmux_checks.update(
            {
                "second_port": port_b,
                "ports_are_distinct": bool(port and port_b and port != port_b),
                "second_runtime_owned_by_second_harness": http_checks["second_runtime_info"].get("body", {}).get("harness_dir") == str(solar_home_b / "harness"),
                "second_session_survived_primary_stop_and_uninstall": http_checks["second_healthz_after_primary_stop"].get("status") == 200
                and http_checks["second_healthz_after_primary_uninstall"].get("status") == 200,
                "second_tmux_session_remained": "solar-harness-status-server-" in commands[-1]["stdout_tail"],
            }
        )
    finally:
        if "harness_script" in locals() and harness_script.exists():
            commands.append(_run(run_dir, "status-server-stop", [str(harness_script), "status-server", "stop"], cwd=repo_root, env=env, timeout=60))
        if "solar_bin" in locals() and solar_bin.exists():
            commands.append(_run(run_dir, "uninstall-yes", [str(solar_bin), "uninstall", "--yes"], cwd=repo_root, env=env, timeout=120))
        if "harness_script_b" in locals() and harness_script_b.exists():
            commands.append(_run(run_dir, "second-status-server-stop", [str(harness_script_b), "status-server", "stop"], cwd=repo_root, env=env_b, timeout=60))
        if "solar_bin_b" in locals() and solar_bin_b.exists():
            commands.append(_run(run_dir, "second-uninstall-yes", [str(solar_bin_b), "uninstall", "--yes"], cwd=repo_root, env=env_b, timeout=120))
        cleanup = {
            "solar_home_exists_after_uninstall": solar_home.exists(),
            "claude_dir_exists_after_uninstall": claude_dir.exists(),
            "second_solar_home_exists_after_uninstall": solar_home_b.exists(),
            "second_claude_dir_exists_after_uninstall": claude_dir_b.exists(),
        }

    install_ok = commands[0]["exit_code"] == 0 and install_receipt_seen
    doctor_record = next((command for command in commands if command["label"] == "doctor-json"), {})
    status_record = next((command for command in commands if command["label"] == "status-json"), {})
    try:
        doctor_payload = json.loads((run_dir / doctor_record["stdout_path"]).read_text(encoding="utf-8"))
    except (KeyError, OSError, json.JSONDecodeError):
        doctor_payload = {}
    try:
        status_payload = json.loads((run_dir / status_record["stdout_path"]).read_text(encoding="utf-8"))
    except (KeyError, OSError, json.JSONDecodeError):
        status_payload = {}
    # The test intentionally skips Python/LLM CLI dependencies. A diagnostic
    # exit 1 is valid when the structured payload truthfully reports degraded
    # readiness while confirming the installed paths and Python minimum.
    doctor_ok = (
        doctor_record.get("exit_code") in {0, 1}
        and doctor_payload.get("paths", {}).get("solar_home") == "ok"
        and doctor_payload.get("paths", {}).get("receipt") == "ok"
        and doctor_payload.get("python", {}).get("min_ok") is True
        and doctor_payload.get("verdict") in {"pass", "fail"}
    )
    status_ok = (
        status_record.get("exit_code") in {0, 1}
        and status_payload.get("status") in {"installed", "ok", "degraded"}
        and status_payload.get("install", {}).get("paths", {}).get("receipt", {}).get("state") == "ok"
    )
    health_ok = http_checks.get("healthz", {}).get("status") == 200 and http_checks.get("healthz", {}).get("body_prefix") == "ok"
    runtime_ok = http_checks.get("runtime_info", {}).get("body", {}).get("harness_dir") == str(solar_home / "harness")
    status_payload_ok = isinstance(http_checks.get("status", {}).get("body"), dict)
    settings_payload_ok = isinstance(http_checks.get("settings", {}).get("body"), dict)
    root_ok = http_checks.get("root", {}).get("status") == 200
    tmux_ok = bool(tmux_checks.get("status_server_tmux_session_observed"))
    concurrent_isolation_ok = bool(
        tmux_checks.get("ports_are_distinct")
        and tmux_checks.get("second_runtime_owned_by_second_harness")
        and tmux_checks.get("second_session_survived_primary_stop_and_uninstall")
        and tmux_checks.get("second_tmux_session_remained")
    )
    uninstall_ok = not cleanup["solar_home_exists_after_uninstall"] and not cleanup["second_solar_home_exists_after_uninstall"]
    required = [
        install_ok,
        doctor_ok,
        status_ok,
        health_ok,
        runtime_ok,
        status_payload_ok,
        settings_payload_ok,
        root_ok,
        tmux_ok,
        concurrent_isolation_ok,
        uninstall_ok,
    ]
    final_status = "PASS_WITH_KNOWN_LIMITATIONS" if all(required) else "FAIL"

    evidence = {
        "schema_version": "phase22.j18.real_linux_status_lifecycle.v2",
        "journey_id": "P22-J18",
        "run_id": run_id,
        "selector": SELECTOR,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "platform": platform.platform(),
        "distribution": distro,
        "repo_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip(),
        "sandbox": {
            "primary": {"home": str(sandbox_home), "solar_home": str(solar_home), "claude_dir": str(claude_dir)},
            "secondary": {"home": str(sandbox_home_b), "solar_home": str(solar_home_b), "claude_dir": str(claude_dir_b)},
            "tmux_tmpdir": str(tmux_tmpdir),
        },
        "commands": commands,
        "http_checks": http_checks,
        "tmux_checks": tmux_checks,
        "cleanup": cleanup,
        "assertions": {
            "install_ok": install_ok,
            "doctor_ok": doctor_ok,
            "status_ok": status_ok,
            "health_ok": health_ok,
            "runtime_info_owned_by_sandbox_harness": runtime_ok,
            "status_payload_parseable": status_payload_ok,
            "settings_payload_parseable": settings_payload_ok,
            "dashboard_loaded": root_ok,
            "tmux_status_server_session_observed": tmux_ok,
            "concurrent_harness_sessions_isolated": concurrent_isolation_ok,
            "uninstall_cleanup_ok": uninstall_ok,
        },
        "observed_l2": [
            {
                "category": "Vertical",
                "level_2_feature": "Linux Cli",
                "status": final_status,
                "assertion_name": "j18_linux_cli_install_doctor_status_uninstall",
                "evidence_path": "journey-result.json",
                "known_limitations": [
                    f"Validated on {distro.get('id')} {distro.get('version_id')} WSL2 with kernel,harness only; did not cover every Linux distribution family, package manager, update, rollback, or repair variant."
                ],
            },
            {
                "category": "Vertical",
                "level_2_feature": "Workflow & Platform Status Visibility",
                "status": final_status,
                "assertion_name": "j18_status_server_health_status_runtime_projection",
                "evidence_path": "journey-result.json",
                "known_limitations": [
                    "Validated local status/runtime/settings projections only; did not cover remote hosts, all workflow states, or production authentication hardening."
                ],
            },
            {
                "category": "Vertical",
                "level_2_feature": "TMUX",
                "status": final_status,
                "assertion_name": "j18_status_server_tmux_session_lifecycle",
                "evidence_path": "journey-result.json",
                "known_limitations": [
                    f"Validated two concurrent local {distro.get('id')} {distro.get('version_id')} status-server TMUX sessions with cross-stop/uninstall isolation; did not cover remote hosts, other terminal implementations, or a broad interactive user-repair matrix."
                ],
            },
        ],
        "status": final_status,
    }
    result_path = _write_json(run_dir / "journey-result.json", evidence)
    _write_json(artifact_dir / "commands.json", commands)
    _write_json(artifact_dir / "http-checks.json", http_checks)
    _write_json(artifact_dir / "tmux-checks.json", tmux_checks)

    assert all(required), f"P22-J18 lifecycle failed; evidence: {result_path}"
