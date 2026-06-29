#!/usr/bin/env python3
"""operatord — Solar Harness operator daemon CLI.

Launches a Solar operator process: resolves the operator config from the
physical-operators registry, loads the appropriate persona and evaluator
protocol, applies the tmux pane title, then emits a structured ready signal.

Usage
-----
    operatord run --operator <id> [options]
    operatord run --help
    operatord list
    operatord --help

Subcommands
-----------
run     Bootstrap one operator instance (persona load + pane title).
list    Print enabled operators from the registry.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import shlex
import sys
import re
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
PERSONAS_DIR = HARNESS_DIR / "personas"
OPERATOR_DAEMON_DIR = HARNESS_DIR / "run" / "operator-daemons"
PHYSICAL_OPERATORS_PATH = Path(
    os.environ.get(
        "SOLAR_MULTI_TASK_OPERATORS",
        HARNESS_DIR / "config" / "physical-operators.json",
    )
)

# Insert lib directory so the shared persona resolver can be imported regardless
# of the working directory from which operatord is invoked.
_LIB_DIR = Path(__file__).resolve().parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from operator_persona import (  # noqa: E402  (import after path setup)
    EVALUATOR_PROTOCOL_FILENAME,
    resolve_persona,
)

# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def _load_registry() -> dict[str, Any]:
    if not PHYSICAL_OPERATORS_PATH.exists():
        return {"version": 1, "operators": {}}
    try:
        return json.loads(PHYSICAL_OPERATORS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        _die(f"Cannot read operator registry {PHYSICAL_OPERATORS_PATH}: {exc}")


def _get_operator(operator_id: str) -> dict[str, Any]:
    registry = _load_registry()
    operators = registry.get("operators", {})
    if operator_id not in operators:
        available = ", ".join(sorted(operators.keys())) or "(none)"
        _die(
            f"Operator '{operator_id}' not found in registry.\n"
            f"Available: {available}"
        )
    return dict(operators[operator_id])


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _die(msg: str) -> None:
    print(f"[operatord] ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def _info(msg: str) -> None:
    print(f"[operatord] {msg}", flush=True)


def _daemon_lock_path(operator_id: str) -> Path:
    OPERATOR_DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    return OPERATOR_DAEMON_DIR / f"{operator_id}.lock"


def _daemon_pid_path(operator_id: str) -> Path:
    OPERATOR_DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    return OPERATOR_DAEMON_DIR / f"{operator_id}.json"


def _acquire_daemon_slot(operator_id: str, *, once: bool) -> tuple[Any | None, Path]:
    lock_path = _daemon_lock_path(operator_id)
    pid_path = _daemon_pid_path(operator_id)
    lock_fh = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        owner = {}
        try:
            owner = json.loads(pid_path.read_text(encoding="utf-8"))
        except Exception:
            owner = {}
        owner_pid = owner.get("pid", "unknown")
        owner_mode = "once" if owner.get("once") else "daemon"
        _info(
            f"Another operatord instance is already active for {operator_id} "
            f"(pid={owner_pid}, mode={owner_mode})"
        )
        lock_fh.close()
        return None, pid_path

    pid_payload = {
        "operator_id": operator_id,
        "pid": os.getpid(),
        "once": bool(once),
        "started_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    pid_path.write_text(json.dumps(pid_payload, indent=2), encoding="utf-8")
    return lock_fh, pid_path


def _release_daemon_slot(lock_fh: Any | None, pid_path: Path) -> None:
    try:
        if pid_path.exists():
            try:
                payload = json.loads(pid_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            if str(payload.get("pid") or "") == str(os.getpid()):
                pid_path.unlink()
    finally:
        if lock_fh is not None:
            try:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                lock_fh.close()
            except Exception:
                pass


def _read_status_snapshot(operator_id: str) -> dict[str, Any]:
    path = HARNESS_DIR / "run" / "operator-status" / f"{operator_id}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Daemon helpers
# ---------------------------------------------------------------------------


def _configured_launch_command(config: dict) -> str:
    surface = config.get("surface")
    if isinstance(surface, dict):
        launch_cmd = str(surface.get("launch_cmd") or "").strip()
        if launch_cmd:
            return launch_cmd
    return str(config.get("launch_cmd") or "").strip()


def _claude_model_arg(model: str) -> str:
    value = str(model or "sonnet").strip().lower()
    if value in {"glm", "glm-5", "glm-5.1", "zhipu", "zhipu-glm-5.1"}:
        return "opus"
    if "opus" in value:
        return "opus"
    if "sonnet" in value or value in {"claude", "anthropic"}:
        return "sonnet"
    return value or "sonnet"


def _model_route_metadata(config: dict[str, Any]) -> dict[str, str]:
    requested_model = str(config.get("model") or "").strip()
    provider = str(config.get("provider") or config.get("vendor") or "").strip().lower()
    backend = str(config.get("backend") or "").strip().lower()
    routing_model = requested_model
    effective_provider = provider or str(config.get("backend") or "").strip()
    effective_model = requested_model

    if backend == "claude-cli":
        routing_model = _claude_model_arg(requested_model)
        if provider in {"glm", "zhipu", "zhipuai"}:
            effective_provider = "zhipu"
            effective_model = "glm-5.1"
        elif provider in {"anthropic", "claude"}:
            effective_provider = "anthropic"
            effective_model = requested_model or routing_model

    return {
        "requested_model": requested_model or "N/A",
        "routing_model": routing_model or "N/A",
        "effective_provider": effective_provider or "N/A",
        "effective_model": effective_model or "N/A",
    }


_ANTIGRAVITY_NONFINAL_RE = re.compile(
    r"^\s*(i\s+will|i'll|i\s+am\s+going\s+to|let\s+me|i\s+need\s+to|i'll\s+now)\b",
    re.I,
)
_ANTIGRAVITY_PLACEHOLDER_RE = re.compile(r"^\s*#*\s*(handoff|completed|done)\s*#*\s*$", re.I)


def _antigravity_output_is_nonfinal(log_lines: list[str]) -> bool:
    content = [
        line.strip()
        for line in log_lines
        if line.strip() and not line.startswith("[solar-harness agy-multimodal] cmd=")
    ]
    if not content:
        return True
    first = content[0]
    joined = " ".join(content)
    if len(content) == 1 and _ANTIGRAVITY_PLACEHOLDER_RE.match(first):
        return True
    if _ANTIGRAVITY_NONFINAL_RE.match(first) and not re.search(
        r"\b(completed|verified|done|image_unsupported|smoke_ok|handoff)\b",
        joined,
        re.I,
    ):
        return True
    return False


def _dispatch_file_for_env(result_dir: Path, envelope: dict[str, Any]) -> Path | None:
    dispatch_text = str(envelope.get("dispatch_text") or "").strip()
    if dispatch_text:
        dispatch_file = result_dir / "dispatch.md"
        dispatch_file.write_text(dispatch_text, encoding="utf-8")
        return dispatch_file

    dispatch_file_value = str(envelope.get("dispatch_file") or "").strip()
    if not dispatch_file_value:
        return None

    dispatch_path = Path(dispatch_file_value).expanduser()
    if dispatch_path.exists():
        # Keep a local copy next to result.json for auditability while still
        # pointing the task at the canonical dispatch file.
        try:
            (result_dir / "dispatch.md").write_text(
                dispatch_path.read_text(encoding="utf-8", errors="replace"),
                encoding="utf-8",
            )
        except Exception:
            pass
        return dispatch_path
    return dispatch_path


def _materialize_envelope_context(result_dir: Path, envelope: dict) -> dict[str, str]:
    env: dict[str, str] = {}
    dispatch_file = _dispatch_file_for_env(result_dir, envelope)
    if dispatch_file is not None:
        env["SOLAR_MULTI_TASK_DISPATCH_FILE"] = str(dispatch_file)
        env["DISPATCH_FILE"] = str(dispatch_file)
    envelope_file = result_dir / "envelope.json"
    envelope_file.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    env["SOLAR_OPERATOR_ENVELOPE_JSON"] = str(envelope_file)
    handoff_path = str(envelope.get("handoff_path") or "").strip()
    if handoff_path:
        env["HANDOFF"] = handoff_path
    graph_path = str(envelope.get("graph_path") or "").strip()
    if graph_path:
        env["GRAPH"] = graph_path
    work_dir = str(envelope.get("work_dir") or "").strip()
    if work_dir:
        env["WORK_DIR"] = work_dir
        env["CODEX_WORKDIR"] = work_dir
    if str(envelope.get("node_id") or "").strip():
        env["NODE_ID"] = str(envelope["node_id"])
    if str(envelope.get("task_id") or "").strip():
        env["TASK_ID"] = str(envelope["task_id"])
    if str(envelope.get("sprint_id") or "").strip():
        env["SID"] = str(envelope["sprint_id"])
    result_path = str(envelope.get("result_path") or "").strip()
    if result_path:
        env["RESULT_PATH"] = result_path
        env["PM_RESULT_PATH"] = result_path
    pm_context = str(envelope.get("pm_context") or "").strip()
    if pm_context:
        env["PM_CONTEXT"] = pm_context
    env["TASK_DIR"] = str(result_dir)
    env["OUTPUT_LOG"] = str(result_dir / "output.log")
    env["HARNESS_DIR"] = str(HARNESS_DIR)
    env["SPRINTS_DIR"] = str(HARNESS_DIR / "sprints")
    return env


def _claude_print_command(config: dict[str, Any]) -> list[str]:
    model = _claude_model_arg(str(config.get("model") or "sonnet"))
    empty_mcp = HARNESS_DIR / "config" / "empty-mcp.json"
    provider = str(config.get("provider") or "").strip().lower()
    provider_env: list[str] = []
    if provider in {"glm", "zhipu", "zhipuai"}:
        provider_env = [
            'source "$HARNESS_DIR/model-config.sh" 2>/dev/null || true',
            'export ANTHROPIC_BASE_URL="${ZHIPU_BASE_URL:-https://api.z.ai/api/anthropic}"',
            'export ANTHROPIC_API_KEY="${ZHIPU_API_KEY:-${ZHIPU_AUTH_TOKEN:-}}"',
            'export ANTHROPIC_DEFAULT_OPUS_MODEL="${ZHIPU_MODEL:-GLM-5.1}"',
        ]
    command = "\n".join([
        *provider_env,
        "export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1",
        "export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1",
        "export DISABLE_NON_ESSENTIAL_MODEL_CALLS=1",
        "export CLAUDE_CODE_MAX_OUTPUT_TOKENS=${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-12000}",
        (
            "claude --dangerously-skip-permissions "
            "--permission-mode bypassPermissions "
            f"--model {shlex.quote(model)} "
            f"--add-dir {shlex.quote(str(HARNESS_DIR))} "
            f"--strict-mcp-config --mcp-config {shlex.quote(str(empty_mcp))} "
            '-p "$(cat "$DISPATCH_FILE")"'
        ),
    ])
    return ["bash", "-lc", command]


def _build_command(config: dict, envelope: dict) -> list[str]:
    """Return the shell command list to execute for this task.

    If the envelope carries an explicit ``command`` override, or if a command
    backend provides a configured launch command, operatord executes that
    command through a shell adapter. For any unsupported backend we still
    default to a safe echo so the daemon can be exercised without credentials
    in test/CI environments.
    """
    backend: str = str(config.get("backend", "local")).lower()

    # Explicit command in the envelope takes highest priority.
    cmd_val = envelope.get("command")
    if cmd_val:
        if isinstance(cmd_val, list):
            return [str(c) for c in cmd_val]
        return ["bash", "-lc", str(cmd_val)]

    launch_cmd = _configured_launch_command(config)
    if backend == "command" and launch_cmd:
        return ["bash", "-lc", launch_cmd]
    if backend == "command":
        configured_command = str(config.get("command") or "").strip()
        if configured_command:
            return ["bash", "-lc", configured_command]

    if backend == "claude-cli":
        return _claude_print_command(config)

    task_id: str = str(envelope.get("task_id", "unknown"))
    objective: str = str(envelope.get("objective", ""))[:120]

    if backend in ("local", "dummy", "echo"):
        return [
            "sh",
            "-c",
            (
                f"echo 'operatord: task={task_id}'; "
                f"echo 'objective={objective}'; "
                "sleep 0.05; "
                "echo 'operatord: completed'"
            ),
        ]

    # Real backends (claude-cli, agy, etc.) in non-interactive daemon context:
    # emit a safe placeholder so the daemon lifecycle can be validated without
    # actually spawning an AI process.
    return [
        "sh",
        "-c",
        (
            f"echo 'operatord: backend={backend} task={task_id}'; "
            "echo 'operatord: local-stub exit 0'; "
            "sleep 0.05"
        ),
    ]


def _is_pm_dispatch_task(envelope: dict[str, Any]) -> bool:
    task_id = str(envelope.get("task_id") or "").strip()
    result_path = str(envelope.get("result_path") or "").strip()
    return task_id.startswith("pm-") or result_path.endswith(".pm-result.md")


def _pm_result_path(envelope: dict[str, Any]) -> Path | None:
    value = str(envelope.get("result_path") or "").strip()
    if not value:
        return None
    return Path(value).expanduser()


def _pm_dispatch_complete_command(task_id: str) -> list[str]:
    return [sys.executable, str(HARNESS_DIR / "tools" / "pm_dispatch.py"), "complete", "--task-id", task_id]


def _pm_dispatch_fail_command(task_id: str, status: str, reason: str) -> list[str]:
    return [
        sys.executable,
        str(HARNESS_DIR / "tools" / "pm_dispatch.py"),
        "fail",
        "--task-id",
        task_id,
        "--status",
        status,
        "--reason",
        reason[:2000],
    ]


def _parse_utc(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _int_value(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _failure_flow_control_settings(config: dict[str, Any], envelope: dict[str, Any]) -> dict[str, int]:
    flow_control = dict(config.get("flow_control") or {})
    return {
        "rate_limit_cooldown_seconds": _int_value(
            envelope.get("rate_limit_cooldown_seconds")
            or os.environ.get("SOLAR_OPERATOR_RATE_LIMIT_COOLDOWN_SECONDS")
            or flow_control.get("rate_limit_cooldown_seconds"),
            3600,
        ),
        "auth_cooldown_seconds": _int_value(
            envelope.get("auth_cooldown_seconds")
            or os.environ.get("SOLAR_OPERATOR_AUTH_COOLDOWN_SECONDS")
            or flow_control.get("auth_cooldown_seconds"),
            21600,
        ),
    }


def _apply_failure_runtime_override(
    *,
    operator_id: str,
    config: dict[str, Any],
    envelope: dict[str, Any],
    task_dir: Path,
    failure_text: str,
) -> dict[str, Any]:
    import operator_flow_control as ofc  # noqa: E402

    settings = _failure_flow_control_settings(config, envelope)
    return ofc.apply_failure_flow_control(
        task_dir,
        operator_id=operator_id,
        failure_text=failure_text,
        rate_limit_cooldown_seconds=int(settings["rate_limit_cooldown_seconds"]),
        auth_cooldown_seconds=int(settings["auth_cooldown_seconds"]),
        defer_on_cooldown=False,
        defer_on_auth=False,
    )


# ---------------------------------------------------------------------------
# Subcommand: daemon
# ---------------------------------------------------------------------------


def cmd_daemon(args: argparse.Namespace) -> int:
    """Run the operator as a persistent daemon (or process one task with --once)."""
    import selectors
    import signal
    import subprocess
    import time

    from operator_runtime import (  # noqa: E402
        acquire_operator_lease,
        get_operator_lease,
        get_operator_runtime_state,
        list_inbox_tasks,
        release_operator_lease,
        update_operator_lease_metadata,
        update_operator_lease_state,
        write_heartbeat,
        write_result,
        HARNESS_DIR as _RT_HARNESS_DIR,
        OPERATOR_RESULTS_DIR,
    )

    operator_id: str = args.operator
    once: bool = args.once
    poll_interval: float = args.poll_interval
    once_max_wait_seconds: float = float(args.once_max_wait_seconds)
    task_timeout_seconds: float = float(
        os.environ.get("SOLAR_OPERATORD_TASK_TIMEOUT_SECONDS", "3600")
    )
    config = _get_operator(operator_id)

    if not config.get("enabled", False) and not args.force:
        _info(
            f"Operator '{operator_id}' is disabled. "
            "Pass --force to proceed anyway."
        )
        return 1

    resolved_persona: str = config.get("persona") or config.get("role", "")
    model_route = _model_route_metadata(config)

    # ── Signal handling ───────────────────────────────────────────────────────
    _state: dict[str, Any] = {
        "drain": False,
        "current_state": "idle",
        "current_proc": None,
        "current_task_id": None,
    }

    def _pid_exists(pid: int | None) -> bool:
        if not pid or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _terminate_worker(pid: int | None, *, reason: str) -> bool:
        if not _pid_exists(pid):
            return False
        try:
            os.killpg(pid, signal.SIGTERM)
            _info(f"Sent SIGTERM to worker process group pid={pid} ({reason})")
            return True
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
                _info(f"Sent SIGTERM to worker pid={pid} ({reason})")
                return True
            except Exception as exc:
                _info(f"Unable to terminate worker pid={pid} ({reason}): {exc}")
                return False

    def _kill_worker_force(pid: int | None, *, reason: str) -> bool:
        if not _pid_exists(pid):
            return False
        try:
            os.killpg(pid, signal.SIGKILL)
            _info(f"Sent SIGKILL to worker process group pid={pid} ({reason})")
            return True
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
                _info(f"Sent SIGKILL to worker pid={pid} ({reason})")
                return True
            except Exception as exc:
                _info(f"Unable to force kill worker pid={pid} ({reason}): {exc}")
                return False

    def _handle_signal(signum: int, frame: Any) -> None:
        _info(f"Signal {signum} received — transitioning to draining")
        _state["drain"] = True
        _state["current_state"] = "draining"
        proc = _state.get("current_proc")
        if proc is not None:
            try:
                _terminate_worker(int(proc.pid), reason=f"signal:{signum}")
            except Exception:
                pass
        write_heartbeat(
            operator_id,
            "draining",
            current_task_id=_state.get("current_task_id"),
            worker_pid=int(proc.pid) if proc is not None else None,
            resolved_persona=resolved_persona,
            model_route=model_route,
        )

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    _info(
        f"Daemon starting — operator_id={operator_id} "
        f"once={once} poll_interval={poll_interval}s"
    )
    daemon_lock_fh, daemon_pid_path = _acquire_daemon_slot(operator_id, once=once)
    if daemon_lock_fh is None:
        return 0
    write_heartbeat(operator_id, "idle", resolved_persona=resolved_persona, model_route=model_route)
    _state["current_state"] = "idle"

    processed: int = 0
    loop_started_at = time.monotonic()

    def _once_wait_expired() -> bool:
        if not once or processed > 0:
            return False
        if once_max_wait_seconds <= 0:
            return False
        return (time.monotonic() - loop_started_at) >= once_max_wait_seconds

    try:
        while True:
            # ── Drain check ───────────────────────────────────────────────────────
            if _state["drain"]:
                _info("Drain flag set — exiting daemon loop")
                write_heartbeat(operator_id, "idle", resolved_persona=resolved_persona, model_route=model_route)
                break

            lease_for_telemetry = get_operator_lease(operator_id)
            telemetry_task_id = None
            if lease_for_telemetry and _state["current_state"] != "running":
                telemetry_task_id = str(lease_for_telemetry.get("task_id") or "") or None

            # ── Heartbeat ─────────────────────────────────────────────────────────
            write_heartbeat(
                operator_id,
                _state["current_state"],
                current_task_id=telemetry_task_id,
                worker_pid=int(lease_for_telemetry.get("worker_pid")) if lease_for_telemetry and str(lease_for_telemetry.get("worker_pid") or "").isdigit() else None,
                resolved_persona=resolved_persona,
                model_route=model_route,
            )

            # ── Poll inbox ────────────────────────────────────────────────────────
            tasks = list_inbox_tasks(operator_id)

            if not tasks:
                if once:
                    if processed > 0:
                        # Already processed the one task; exit normally.
                        break
                    if _once_wait_expired():
                        _info(
                            f"Once mode max wait exceeded with no inbox task "
                            f"(operator_id={operator_id}, waited={once_max_wait_seconds}s)"
                        )
                        break
                    # Nothing yet — keep waiting.
                time.sleep(poll_interval)
                continue

            # ── Claim first available task ────────────────────────────────────────
            # If we already hold a lease for a specific task, prioritise that task
            # from the inbox so a stale head (leftover from a previous failed run)
            # cannot block the queue forever.
            lease = get_operator_lease(operator_id)
            leased_task_id = lease.get("task_id") if lease else None

            if leased_task_id and leased_task_id != tasks[0][0]:
                # Active lease is for a task that is NOT at the head.
                matching = [(tid, env, p) for tid, env, p in tasks if tid == leased_task_id]
                if matching:
                    # Re-order: leased task first.
                    tasks = matching + [t for t in tasks if t[0] != leased_task_id]
                    _info(
                        f"Leased task {leased_task_id} is not inbox head; "
                        f"re-ordered tasks to process leased task first"
                    )
                else:
                    # Orphaned lease — leased task is absent from inbox (already
                    # processed or never arrived).  Release the stale lease so the
                    # head can be claimed on the next cycle.
                    _info(
                        f"Releasing orphaned lease for task {leased_task_id} "
                        f"(task not found in inbox)"
                    )
                    release_operator_lease(operator_id, reason="orphaned_lease_absent_task")
                    lease = None
                    leased_task_id = None

            task_id, envelope, envelope_path = tasks[0]

            if lease is None or lease.get("task_id") != task_id:
                recovered_lease = None
                if lease is None:
                    try:
                        recovered_lease = acquire_operator_lease(
                            operator_id=operator_id,
                            task_id=task_id,
                            sprint_id=str(envelope.get("sprint_id") or ""),
                            node_id=str(envelope.get("node_id") or ""),
                            ttl_seconds=int(envelope.get("lease_ttl_seconds") or 3600),
                            initial_state="leased",
                        )
                        lease = recovered_lease
                        _info(f"Recovered missing/expired lease for task {task_id}")
                    except Exception as exc:
                        _info(f"Lease recovery failed for task {task_id}: {exc}")
                # Lease missing or for a different task; skip and wait.
                if lease is not None and lease.get("task_id") == task_id:
                    pass
                else:
                    _info(
                        f"No valid lease found for task {task_id} "
                        f"(current lease task: {lease.get('task_id') if lease else 'none'})"
                    )
                    if _once_wait_expired():
                        _info(
                            f"Once mode max wait exceeded while waiting for valid lease "
                            f"(operator_id={operator_id}, task_id={task_id})"
                        )
                        break
                    time.sleep(poll_interval)
                    continue

            if lease.get("state") == "running":
                status_snapshot = _read_status_snapshot(operator_id)
                status_state = str(status_snapshot.get("state") or "").strip().lower()
                status_task_id = str(status_snapshot.get("current_task_id") or "").strip()
                worker_pid_raw = lease.get("worker_pid")
                daemon_pid_raw = lease.get("daemon_pid")
                try:
                    worker_pid = int(worker_pid_raw) if worker_pid_raw is not None else None
                except Exception:
                    worker_pid = None
                try:
                    daemon_pid = int(daemon_pid_raw) if daemon_pid_raw is not None else None
                except Exception:
                    daemon_pid = None

                stale_reasons: list[str] = []
                if status_state != "running":
                    stale_reasons.append(f"status.state={status_state or 'N/A'}")
                if status_task_id != task_id:
                    stale_reasons.append(f"status.current_task_id={status_task_id or 'N/A'}")
                if worker_pid is not None and not _pid_exists(worker_pid):
                    stale_reasons.append(f"worker_pid_dead={worker_pid}")
                if daemon_pid is not None and not _pid_exists(daemon_pid):
                    stale_reasons.append(f"daemon_pid_dead={daemon_pid}")

                if stale_reasons:
                    _info(
                        f"Recovering stale running lease for task {task_id} "
                        f"({' ; '.join(stale_reasons)})"
                    )
                    if worker_pid is not None and _pid_exists(worker_pid):
                        _terminate_worker(worker_pid, reason="stale_running_lease_recovery")
                    try:
                        update_operator_lease_metadata(
                            operator_id,
                            worker_pid=None,
                            daemon_pid=None,
                        )
                        update_operator_lease_state(operator_id, "leased")
                    except RuntimeError as exc:
                        _info(f"Unable to recover stale running lease: {exc}")
                    else:
                        time.sleep(poll_interval)
                        continue

            if lease.get("state") not in ("leased",):
                _info(f"Task {task_id} lease state={lease.get('state')} — skipping")
                if _once_wait_expired():
                    _info(
                        f"Once mode max wait exceeded while lease state remained "
                        f"{lease.get('state')} for task {task_id}"
                    )
                    break
                time.sleep(poll_interval)
                continue

            _info(f"Claiming task {task_id}")
            try:
                update_operator_lease_state(operator_id, "running")
            except RuntimeError as exc:
                _info(f"Cannot transition lease to running: {exc}")
                if _once_wait_expired():
                    _info(
                        f"Once mode max wait exceeded while transitioning to running "
                        f"(operator_id={operator_id}, task_id={task_id})"
                    )
                    break
                time.sleep(poll_interval)
                continue

            _state["current_state"] = "running"
            write_heartbeat(
                operator_id,
                "running",
                current_task_id=task_id,
                resolved_persona=resolved_persona,
                model_route=model_route,
            )

            # ── Execute ───────────────────────────────────────────────────────────
            sprint_id: str = str(envelope.get("sprint_id", ""))
            node_id: str = str(envelope.get("node_id", ""))
            started_at: str = _now_utc()
            result_status: str = "failed"
            exit_code: int = -1
            log_lines: list[str] = []

            result_dir = OPERATOR_RESULTS_DIR / operator_id / task_id
            result_dir.mkdir(parents=True, exist_ok=True)
            log_path = result_dir / "output.log"
            exec_env = os.environ.copy()
            exec_env.update(_materialize_envelope_context(result_dir, envelope))
            pm_result_path = _pm_result_path(envelope) if _is_pm_dispatch_task(envelope) else None
            if pm_result_path is not None:
                try:
                    pm_result_path.parent.mkdir(parents=True, exist_ok=True)
                    if pm_result_path.exists():
                        pm_result_path.unlink()
                except Exception as exc:
                    _info(f"Unable to clear stale pm result {pm_result_path}: {exc}")

            cmd = _build_command(config, envelope)
            _info(f"Executing: {' '.join(shlex.quote(part) for part in cmd[:8])}")

            try:
                timed_out = False
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=exec_env,
                    start_new_session=True,
                )
                _state["current_proc"] = proc
                _state["current_task_id"] = task_id
                update_operator_lease_metadata(
                    operator_id,
                    worker_pid=int(proc.pid),
                    daemon_pid=int(os.getpid()),
                )
                write_heartbeat(
                    operator_id,
                    "running",
                    current_task_id=task_id,
                    worker_pid=int(proc.pid),
                    resolved_persona=resolved_persona,
                    model_route=model_route,
                )

                with open(log_path, "w", encoding="utf-8") as log_f:
                    assert proc.stdout is not None
                    selector = selectors.DefaultSelector()
                    selector.register(proc.stdout, selectors.EVENT_READ)
                    proc_started_at = time.monotonic()
                    last_runtime_heartbeat_at = proc_started_at

                    while True:
                        now_monotonic = time.monotonic()
                        if now_monotonic - last_runtime_heartbeat_at >= 15:
                            write_heartbeat(
                                operator_id,
                                "running",
                                current_task_id=task_id,
                                worker_pid=int(proc.pid),
                                resolved_persona=resolved_persona,
                                model_route=model_route,
                            )
                            last_runtime_heartbeat_at = now_monotonic

                        if task_timeout_seconds > 0 and (time.monotonic() - proc_started_at) >= task_timeout_seconds:
                            timed_out = True
                            log_lines.append(
                                f"[ERROR] task timeout after {int(task_timeout_seconds)}s"
                            )
                            _terminate_worker(int(proc.pid), reason="task_timeout")
                            try:
                                proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                _kill_worker_force(int(proc.pid), reason="task_timeout_escalation")
                                proc.wait(timeout=5)
                            break

                        events = selector.select(timeout=0.5)
                        if not events:
                            if proc.poll() is not None:
                                break
                            continue

                        for key, _mask in events:
                            line = key.fileobj.readline()
                            if not line:
                                continue
                            from operator_runtime import scrub_secrets  # noqa: E402
                            scrubbed = scrub_secrets(line)
                            log_f.write(scrubbed)
                            log_f.flush()
                            log_lines.append(scrubbed.rstrip())

                        if proc.poll() is not None:
                            break

                proc.wait()
                exit_code = proc.returncode if proc.returncode is not None else -1
                if timed_out:
                    exit_code = 124
                    result_status = "failed_timeout"
                else:
                    result_status = "completed" if exit_code == 0 else "failed"

            except Exception as exc:
                _info(f"Execution error: {exc}")
                log_lines.append(f"[ERROR] {exc}")
                result_status = "error"
            finally:
                _state["current_proc"] = None
                _state["current_task_id"] = None

            if _state["drain"]:
                # Signal arrived mid-execution; mark draining then tidy up.
                result_status = "draining"
                _state["current_state"] = "draining"

            finished_at: str = _now_utc()

            if (
                result_status == "completed"
                and "antigravity" in operator_id.lower()
                and _antigravity_output_is_nonfinal(log_lines)
            ):
                log_lines.append("[ERROR] Antigravity output was placeholder/non-final; refusing false completed status")
                result_status = "failed_nonfinal_output"
                exit_code = exit_code or 65

            if result_status == "completed" and pm_result_path is not None:
                if not pm_result_path.exists():
                    log_lines.append(f"[ERROR] missing pm_result: {pm_result_path}")
                    result_status = "failed_missing_pm_result"
                    exit_code = exit_code or 65
                else:
                    try:
                        started_dt = _parse_utc(started_at)
                        result_dt = dt.datetime.fromtimestamp(
                            pm_result_path.stat().st_mtime,
                            tz=dt.timezone.utc,
                        )
                        if result_dt < started_dt:
                            log_lines.append(f"[ERROR] stale pm_result predates current run: {pm_result_path}")
                            result_status = "failed_stale_pm_result"
                            exit_code = exit_code or 66
                    except Exception:
                        pass

            if result_status == "completed" and pm_result_path is not None:
                try:
                    completed = subprocess.run(
                        _pm_dispatch_complete_command(task_id),
                        capture_output=True,
                        text=True,
                        env=exec_env,
                        timeout=30,
                    )
                    stdout = completed.stdout.strip()
                    stderr = completed.stderr.strip()
                    if stdout:
                        log_lines.append(stdout)
                    if stderr:
                        log_lines.append(stderr)
                    if completed.returncode != 0:
                        log_lines.append(
                            f"[WARN] pm_dispatch complete returned {completed.returncode} for {task_id}"
                        )
                        result_status = "failed_contract_closeout"
                        exit_code = exit_code or 67
                except Exception as exc:
                    log_lines.append(f"[WARN] pm_dispatch complete hook failed: {exc}")
                    result_status = "failed_contract_closeout"
                    exit_code = exit_code or 67

            # ── Write result artifact ─────────────────────────────────────────────
            log_tail = "\n".join(log_lines[-50:])
            flow_control_decision: dict[str, Any] | None = None
            if result_status not in {"completed", "draining"} and log_tail.strip():
                try:
                    flow_control_decision = _apply_failure_runtime_override(
                        operator_id=operator_id,
                        config=config,
                        envelope=envelope,
                        task_dir=result_dir,
                        failure_text=log_tail,
                    )
                except Exception as exc:
                    log_lines.append(f"[WARN] failure flow control hook failed: {exc}")
                else:
                    runtime_state = str((flow_control_decision or {}).get("runtime_state") or "").strip()
                    if runtime_state:
                        log_lines.append(f"[flow-control] runtime_state={runtime_state}")
                log_tail = "\n".join(log_lines[-50:])
            result_path = write_result(
                operator_id=operator_id,
                task_id=task_id,
                sprint_id=sprint_id,
                node_id=node_id,
                status=result_status,
                exit_code=exit_code,
                started_at=started_at,
                finished_at=finished_at,
                log_tail=log_tail,
                model_route=model_route,
            )
            _info(f"Result written: {result_path}")

            if pm_result_path is not None and result_status not in {"completed", "draining"}:
                try:
                    failed = subprocess.run(
                        _pm_dispatch_fail_command(task_id, result_status, log_tail or result_status),
                        capture_output=True,
                        text=True,
                        env=exec_env,
                        timeout=30,
                    )
                    stdout = failed.stdout.strip()
                    stderr = failed.stderr.strip()
                    if stdout:
                        log_lines.append(stdout)
                    if stderr:
                        log_lines.append(stderr)
                    if failed.returncode != 0:
                        log_lines.append(
                            f"[WARN] pm_dispatch fail returned {failed.returncode} for {task_id}"
                        )
                except Exception as exc:
                    log_lines.append(f"[WARN] pm_dispatch fail hook failed: {exc}")

            # ── Cleanup ───────────────────────────────────────────────────────────
            try:
                envelope_path.unlink()
            except Exception:
                pass

            try:
                update_operator_lease_metadata(
                    operator_id,
                    worker_pid=None,
                    daemon_pid=None,
                )
            except Exception:
                pass

            try:
                release_operator_lease(operator_id, reason=result_status)
            except Exception:
                pass

            processed += 1
            _state["current_state"] = "idle"
            write_heartbeat(operator_id, "idle", resolved_persona=resolved_persona, model_route=model_route)
            _info(f"Task {task_id} done: {result_status} (exit={exit_code})")

            if once:
                break

            if _state["drain"]:
                break

            time.sleep(poll_interval)
    finally:
        write_heartbeat(operator_id, "idle", resolved_persona=resolved_persona, model_route=model_route)
        _release_daemon_slot(daemon_lock_fh, daemon_pid_path)

    return 0


def _now_utc() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    """Bootstrap an operator: load persona, apply pane title, emit ready."""
    # Lazy import to keep top-level clean
    try:
        from operator_naming import (  # type: ignore[import]
            canonical_operator_id,
            pane_title,
            apply_pane_title,
        )
    except ImportError:
        # Fallback if run from outside tools/ directory
        _tools_dir = Path(__file__).parent
        sys.path.insert(0, str(_tools_dir))
        from operator_naming import (  # type: ignore[import]
            canonical_operator_id,
            pane_title,
            apply_pane_title,
        )

    operator_id: str = args.operator
    config = _get_operator(operator_id)

    role: str = config.get("role", "builder")
    model: str = config.get("model", "")
    enabled: bool = config.get("enabled", False)

    # Warn but do not block on disabled operators (useful for testing)
    if not enabled and not args.force:
        _info(
            f"Operator '{operator_id}' is marked disabled "
            f"(reason: {config.get('disabled_reason', 'unknown')}). "
            "Pass --force to proceed anyway."
        )
        return 1

    # ── Canonical ID ─────────────────────────────────────────────────────────
    canon_id = canonical_operator_id(operator_id, config)
    _info(f"canonical_id  = {canon_id}")
    _info(f"role          = {role}")
    _info(f"model         = {model or '(unknown)'}")
    _info(f"display_name  = {config.get('display_name', operator_id)}")

    # ── Persona & evaluator protocol ──────────────────────────────────────────
    pr = None
    try:
        pr = resolve_persona(operator_id, config, PERSONAS_DIR)
    except RuntimeError as exc:
        _info(f"persona       = (not found: {exc})")

    if pr is not None:
        _info(f"persona       = {pr.persona_path}")
        if args.print_persona:
            print("\n" + "─" * 60)
            print(f"# Persona: {pr.persona_name}")
            print("─" * 60)
            print(pr.persona_text)
            print("─" * 60 + "\n")

        if pr.eval_protocol_loaded:
            _info(f"eval_protocol = {pr.eval_protocol_path}")
            if args.print_persona:
                print("\n" + "─" * 60)
                print("# Evaluator Verification Protocol")
                print("─" * 60)
                print(pr.eval_protocol_text)
                print("─" * 60 + "\n")
        elif pr.persona_name == "evaluator":
            _info(f"eval_protocol = (not found: {EVALUATOR_PROTOCOL_FILENAME})")

    # ── Pane title ────────────────────────────────────────────────────────────
    title = pane_title(
        operator_id=operator_id,
        role=role,
        config=config,
    )
    _info(f"pane_title    = {title}")
    pane_target = args.pane_id or os.environ.get("TMUX_PANE")
    apply_pane_title(title, pane_id=pane_target)

    # ── Ready signal ──────────────────────────────────────────────────────────
    ready: dict[str, Any] = {
        "status": "ready",
        "operator_id": operator_id,
        "canonical_id": canon_id,
        "role": role,
        "model": model,
        "persona_loaded": pr is not None,
        "eval_protocol_loaded": pr is not None and pr.eval_protocol_loaded,
        "pane_title": title,
    }
    if args.json:
        print(json.dumps(ready, indent=2))

    return 0


# ---------------------------------------------------------------------------
# Subcommand: list
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    registry = _load_registry()
    operators = registry.get("operators", {})
    if not operators:
        _info("No operators registered.")
        return 0

    if args.json:
        print(json.dumps(operators, indent=2))
        return 0

    fmt = "  {:<42} {:<12} {:<14} {:<8}"
    print(fmt.format("ID", "ROLE", "VENDOR/BACKEND", "ENABLED"))
    print("  " + "-" * 80)
    for oid, cfg in sorted(operators.items()):
        print(
            fmt.format(
                oid[:42],
                str(cfg.get("role", "?"))[:12],
                str(cfg.get("backend", cfg.get("provider", "?")))[:14],
                "yes" if cfg.get("enabled") else "no",
            )
        )
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="operatord",
        description="Solar Harness operator daemon — bootstrap and manage operator instances.",
    )
    sub = parser.add_subparsers(dest="subcommand", metavar="<subcommand>")

    # ── run ──────────────────────────────────────────────────────────────────
    run_p = sub.add_parser(
        "run",
        help="Bootstrap an operator instance (load persona, apply pane title).",
        description=(
            "Bootstrap a Solar Harness operator: resolve config from the physical-operators "
            "registry, load the operator persona file, load the evaluator verification protocol "
            "when the role is 'evaluator', apply the tmux pane title, and emit a ready signal."
        ),
    )
    run_p.add_argument(
        "--operator",
        required=True,
        metavar="ID",
        help="Operator ID from physical-operators.json (e.g. mini-claude-sonnet-builder).",
    )
    run_p.add_argument(
        "--harness-dir",
        metavar="PATH",
        default=str(HARNESS_DIR),
        help=f"Path to the Solar Harness root directory (default: {HARNESS_DIR}).",
    )
    run_p.add_argument(
        "--pane-id",
        metavar="PANE",
        default=None,
        help="Explicit tmux pane target (e.g. %%3). Defaults to $TMUX_PANE.",
    )
    run_p.add_argument(
        "--force",
        action="store_true",
        help="Run even if the operator is disabled in the registry.",
    )
    run_p.add_argument(
        "--print-persona",
        action="store_true",
        help="Print the full persona and evaluator protocol text to stdout.",
    )
    run_p.add_argument(
        "--json",
        action="store_true",
        help="Emit the ready signal as JSON.",
    )

    # ── list ─────────────────────────────────────────────────────────────────
    list_p = sub.add_parser(
        "list",
        help="List operators registered in physical-operators.json.",
    )
    list_p.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON.",
    )

    # ── daemon ───────────────────────────────────────────────────────────────
    daemon_p = sub.add_parser(
        "daemon",
        help="Run the operator as a persistent daemon that polls its inbox.",
        description=(
            "Bootstrap the operator and enter a polling loop. "
            "When a task envelope appears in run/operator-inbox/<id>/, the daemon "
            "claims it, executes the backend command, writes result artifacts, "
            "and returns to idle. Use --once to process exactly one task then exit."
        ),
    )
    daemon_p.add_argument(
        "--operator",
        required=True,
        metavar="ID",
        help="Operator ID from physical-operators.json.",
    )
    daemon_p.add_argument(
        "--once",
        action="store_true",
        help="Process one task then exit (useful for testing and CI).",
    )
    daemon_p.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        metavar="SECS",
        help="Seconds between inbox polls (default: 1.0).",
    )
    daemon_p.add_argument(
        "--once-max-wait-seconds",
        type=float,
        default=float(os.environ.get("SOLAR_OPERATORD_ONCE_MAX_WAIT_SECONDS", "15")),
        metavar="SECS",
        help="Maximum seconds a --once daemon waits before exiting if it never claims work (default: 15).",
    )
    daemon_p.add_argument(
        "--force",
        action="store_true",
        help="Run even if the operator is disabled in the registry.",
    )
    daemon_p.add_argument(
        "--harness-dir",
        metavar="PATH",
        default=str(HARNESS_DIR),
        help=f"Path to the Solar Harness root directory (default: {HARNESS_DIR}).",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Update HARNESS_DIR from --harness-dir if provided by run subcommand
    if hasattr(args, "harness_dir") and args.harness_dir:
        global HARNESS_DIR, PERSONAS_DIR, PHYSICAL_OPERATORS_PATH
        HARNESS_DIR = Path(args.harness_dir)
        PERSONAS_DIR = HARNESS_DIR / "personas"
        PHYSICAL_OPERATORS_PATH = Path(
            os.environ.get(
                "SOLAR_MULTI_TASK_OPERATORS",
                HARNESS_DIR / "config" / "physical-operators.json",
            )
        )

    if args.subcommand == "run":
        return cmd_run(args)
    elif args.subcommand == "list":
        return cmd_list(args)
    elif args.subcommand == "daemon":
        return cmd_daemon(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
