#!/usr/bin/env python3
"""operator_runtime.py — S6 Control Plane: Operator runtime lease and state helper.

Classifies runtime state of physical operators and manages atomic process-safe leases.
"""

from __future__ import annotations

import argparse
import datetime
import file_lock_compat as fcntl
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from operator_persona import resolve_persona
from task_lifecycle import converge_execution_attempt_result, converge_status_file

try:  # Lane 3 gate ledger (R5/AC-R5.1): route records at the operatord seam (F7)
    import gate_ledger as _gate_ledger
except Exception:  # pragma: no cover
    _gate_ledger = None


def _route_sprints_dir() -> Path:
    """Single shared sprints-dir resolution for route records (round-4 G7).

    The ledger the route writer appends to must be the ledger the gates read —
    gate_ledger.default_sprints_dir() (HARNESS_SPRINTS_DIR > HARNESS_DIR >
    SOLAR_HARNESS_DIR > install default) is that shared rule."""
    if _gate_ledger is not None:
        try:
            return Path(_gate_ledger.default_sprints_dir())
        except Exception:
            pass
    return HARNESS_DIR / "sprints"


def _ledger_route(sprint_id: str, node_id: str, task_id: str, phase: str,
                  route: Dict[str, Any]) -> None:
    """Append a route record to the sprint's gate ledger.

    No-op unless SOLAR_GATE_LEDGER=1; best-effort — route evidence must never
    break the operator hot path."""
    if _gate_ledger is None:
        return
    try:
        if not _gate_ledger.enabled():
            return
        _gate_ledger.append_route_record(
            _route_sprints_dir(), sprint_id,
            node_id=node_id, task_id=task_id, phase=phase, route=route,
        )
    except Exception:
        pass


def _sync_graph_after_route_result(
    sprint_id: str,
    result_payload: Dict[str, Any] | None = None,
    result_path: Path | None = None,
) -> Dict[str, Any]:
    """Converge terminal graph proof after result.json becomes durable.

    An evaluator can invoke ``node-verdict`` from inside its model process.
    That updates the graph before operatord writes the provider-bearing
    ``result.json``.  Closeout deliberately waits at that point, so the result
    writer must provide the next convergence edge instead of relying on an
    unrelated coordinator mtime change.

    Non-graph operator tasks are a no-op.  Graph sync remains best-effort for
    the operator hot path; its return value keeps the failure inspectable in
    focused tests and callers that choose to surface it.
    """
    sid = str(sprint_id or "").strip()
    if not sid:
        return {"ok": True, "reason": "missing_sprint_id"}
    sprints_dir = _route_sprints_dir()
    graph_path = sprints_dir / f"{sid}.task_graph.json"
    if not graph_path.is_file():
        return {"ok": True, "reason": "graph_missing", "graph_path": str(graph_path)}
    try:
        import graph_scheduler  # type: ignore

        # operator_runtime may be imported before tests or an installed runner
        # override HARNESS_DIR.  Keep the scheduler on the same runtime roots as
        # the result artifact rather than its import-time defaults.
        graph_scheduler.HARNESS_DIR = HARNESS_DIR
        graph_scheduler.SPRINTS_DIR = sprints_dir
        graph = graph_scheduler.load_graph(graph_path)
        attempt_convergence: Dict[str, Any] = {
            "matched": False,
            "reason": "result_payload_missing",
        }
        if isinstance(result_payload, dict):
            node_id = str(result_payload.get("node_id") or "").strip()
            node = next(
                (
                    item
                    for item in graph.get("nodes", [])
                    if str(item.get("id") or "") == node_id
                ),
                None,
            )
            if isinstance(node, dict):
                attempt_convergence = converge_execution_attempt_result(
                    node,
                    result_payload,
                    result_path=result_path or "",
                )
                if attempt_convergence.get("matched"):
                    graph_scheduler.save_graph(graph_path, graph)
            else:
                attempt_convergence = {"matched": False, "reason": "node_missing"}
        projection = graph_scheduler.sync_status_cache_from_graph(
            graph,
            graph_path,
            actor="operator_runtime",
            event="route_result_recorded",
        )
        scheduler_tick: Dict[str, Any] = {
            "ok": True,
            "reason": "graph_dispatcher_unavailable",
        }
        evaluator_dispatch: Dict[str, Any] = {
            "ok": True,
            "reason": "graph_dispatcher_unavailable",
        }
        try:
            import graph_node_dispatcher  # type: ignore

            # Make result publication an active scheduler edge.  The
            # graph-scoped non-blocking lock inside dispatch_ready prevents a
            # simultaneous autopilot tick from dispatching the same node.
            graph_node_dispatcher.HARNESS_DIR = HARNESS_DIR
            graph_node_dispatcher.SPRINTS_DIR = sprints_dir
            scheduler_tick = graph_node_dispatcher.dispatch_ready(str(graph_path))
            evaluator_dispatch = graph_node_dispatcher.dispatch_node_evals(
                str(graph_path),
                max_items=1,
            )
        except Exception as dispatch_exc:
            # result.json is already durable. Keep the operator completion
            # successful and return an inspectable callback failure for the
            # polling monitor to recover on its next tick.
            scheduler_tick = {
                "ok": False,
                "reason": "route_result_dispatch_failed",
                "error": f"{type(dispatch_exc).__name__}: {dispatch_exc}",
            }
            evaluator_dispatch = {
                "ok": False,
                "reason": "route_result_dispatch_failed",
            }
        return {
            **projection,
            "attempt_convergence": attempt_convergence,
            "scheduler_tick": scheduler_tick,
            "evaluator_dispatch": evaluator_dispatch,
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": "route_result_sync_failed",
            "graph_path": str(graph_path),
            "error": f"{type(exc).__name__}: {exc}",
        }

HOME = Path.home()
# HARNESS_DIR > SOLAR_HARNESS_DIR > install default — the graph_scheduler rule
# (round-4 G7: operator_runtime ignored SOLAR_HARNESS_DIR and could land run
# state in the live ~/.solar/harness during sandboxed runs).
HARNESS_DIR = Path(
    os.environ.get("HARNESS_DIR")
    or os.environ.get("SOLAR_HARNESS_DIR")
    or HOME / ".solar" / "harness"
)
OPERATOR_LEASE_DIR = HARNESS_DIR / "run" / "operator-leases"
OPERATOR_STATUS_DIR = HARNESS_DIR / "run" / "operator-status"
OPERATOR_INBOX_DIR = HARNESS_DIR / "run" / "operator-inbox"
OPERATOR_RESULTS_DIR = HARNESS_DIR / "run" / "operator-results"
OPERATOR_PERSONAS_DIR = HARNESS_DIR / "personas"
PHYSICAL_OPERATORS_PATH = Path(os.environ.get("SOLAR_MULTI_TASK_OPERATORS", HARNESS_DIR / "config" / "physical-operators.json"))

# Valid runtime states
VALID_STATES = {
    "idle",
    "leased",
    "running",
    "draining",
    "cooldown",
    "quota_exhausted",
    "auth_expired",
    "disabled"
}


class OperatorSubmitRejected(RuntimeError):
    """Structured refusal for capacity/policy states that forbid fallback."""

    def __init__(self, message: str, *, reason: str, state: str) -> None:
        super().__init__(message)
        self.reason = str(reason)
        self.state = str(state)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value: str) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(datetime.timezone.utc)
    except Exception:
        return None


def _ensure_dirs() -> None:
    OPERATOR_LEASE_DIR.mkdir(parents=True, exist_ok=True)
    OPERATOR_STATUS_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_inbox_dir(operator_id: str) -> Path:
    inbox = OPERATOR_INBOX_DIR / operator_id
    inbox.mkdir(parents=True, exist_ok=True)
    return inbox


def _coerce_pid(value: Any) -> Optional[int]:
    try:
        pid = int(value)
        return pid if pid > 0 else None
    except Exception:
        return None


def _pid_exists(pid: Optional[int]) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _active_record_processes_dead(record: Dict[str, Any]) -> bool:
    """True when a leased/running record has process evidence and all PIDs are gone."""
    pids = [
        pid
        for pid in (
            _coerce_pid(record.get("worker_pid")),
            _coerce_pid(record.get("daemon_pid")),
        )
        if pid is not None
    ]
    return bool(pids) and all(not _pid_exists(pid) for pid in pids)


def _active_status_without_process_stale(record: Dict[str, Any]) -> bool:
    """True when an active status has no process evidence and its heartbeat is stale."""
    if str(record.get("runtime_state") or record.get("state") or "") not in {"leased", "running", "draining"}:
        return False
    if _coerce_pid(record.get("worker_pid")) is not None or _coerce_pid(record.get("daemon_pid")) is not None:
        return False
    observed_at = _parse_utc(
        str(
            record.get("heartbeat_at")
            or record.get("updated_at")
            or record.get("started_at")
            or record.get("leased_at")
            or ""
        )
    )
    if observed_at is None:
        return True
    try:
        stale_seconds = int(os.environ.get("SOLAR_OPERATOR_ACTIVE_STATUS_STALE_SECONDS", "900") or "900")
    except Exception:
        stale_seconds = 900
    return (datetime.datetime.now(datetime.timezone.utc) - observed_at).total_seconds() >= max(1, stale_seconds)


def _clear_stale_active_status(operator_id: str) -> bool:
    status = get_operator_status(operator_id)
    if not status:
        return False
    if status.get("runtime_state") in {"leased", "running", "draining"} and (
        _active_record_processes_dead(status) or _active_status_without_process_stale(status)
    ):
        clear_operator_status(operator_id)
        return True
    return False


# ── Registry Access ───────────────────────────────────────────────────────────

def load_registry() -> Dict[str, Any]:
    """Loads the physical operators registry from config."""
    if not PHYSICAL_OPERATORS_PATH.exists():
        return {"version": 1, "operators": {}}
    try:
        return json.loads(PHYSICAL_OPERATORS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "operators": {}}


def get_operator_config(operator_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves config for a specific operator from the registry."""
    registry = load_registry()
    operators = registry.get("operators", {})
    if operator_id in operators:
        return dict(operators[operator_id])
    return None


# ── Dynamic Status/Override Management ────────────────────────────────────────

def get_operator_status(operator_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves the dynamic status override for an operator, if set and not expired."""
    path = OPERATOR_STATUS_DIR / f"{operator_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "expires_at" in data:
            if _now() > data["expires_at"]:
                try:
                    path.unlink()
                except Exception:
                    pass
                return None
        return data
    except Exception:
        return None


def set_operator_status(
    operator_id: str,
    runtime_state: str,
    ttl_seconds: Optional[int] = None
) -> Dict[str, Any]:
    """Sets a dynamic status override (e.g. cooldown, quota_exhausted, auth_expired)."""
    if runtime_state not in VALID_STATES:
        raise ValueError(f"Invalid runtime state: {runtime_state}. Must be one of {VALID_STATES}")
    
    _ensure_dirs()
    path = OPERATOR_STATUS_DIR / f"{operator_id}.json"
    lock_path = OPERATOR_STATUS_DIR / f"{operator_id}.lock"
    
    data = {
        "operator_id": operator_id,
        "runtime_state": runtime_state,
        "updated_at": _now()
    }
    if ttl_seconds is not None:
        expires_at = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=ttl_seconds)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        data["expires_at"] = expires_at
        
    with open(lock_path, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            tmp = str(path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, str(path))
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
            
    return data


def clear_operator_status(operator_id: str) -> None:
    """Clears the dynamic status override for an operator."""
    path = OPERATOR_STATUS_DIR / f"{operator_id}.json"
    lock_path = OPERATOR_STATUS_DIR / f"{operator_id}.lock"
    
    with open(lock_path, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            if path.exists():
                path.unlink()
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


# ── Lease Management ──────────────────────────────────────────────────────────

def get_operator_lease(operator_id: str) -> Optional[Dict[str, Any]]:
    """Gets the active, non-expired lease for an operator if exists."""
    path = OPERATOR_LEASE_DIR / f"{operator_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("expires_at", "") <= _now():
            try:
                path.unlink()
            except Exception:
                pass
            return None
        return data
    except Exception:
        return None


def acquire_operator_lease(
    operator_id: str,
    task_id: str,
    sprint_id: str,
    node_id: str,
    ttl_seconds: int,
    initial_state: str = "leased"
) -> Dict[str, Any]:
    """Acquires an active lease for the operator. Prevents duplicates."""
    if initial_state not in VALID_STATES:
        raise ValueError(f"Invalid initial lease state: {initial_state}. Must be one of {VALID_STATES}")

    # Verify operator exists and is enabled in registry
    config = get_operator_config(operator_id)
    if not config:
        raise ValueError(f"Operator '{operator_id}' not found in registry")
        
    if not config.get("enabled", True):
        raise RuntimeError(f"Cannot lease disabled operator '{operator_id}'")

    _ensure_dirs()
    path = OPERATOR_LEASE_DIR / f"{operator_id}.json"
    lock_path = OPERATOR_LEASE_DIR / f"{operator_id}.lock"
    
    with open(lock_path, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            # Check for existing active lease
            if path.exists():
                existing = None
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    pass  # Overwrite corrupt lease files
                if existing and existing.get("expires_at", "") > _now():
                    raise OperatorSubmitRejected(
                        f"Duplicate active lease rejected: operator '{operator_id}' is already leased",
                        reason="operator_busy",
                        state=str(existing.get("state") or "leased"),
                    )
            
            # Create new lease
            now_str = _now()
            expires_at = (
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=ttl_seconds)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            
            lease = {
                "operator_id": operator_id,
                "task_id": task_id,
                "sprint_id": sprint_id,
                "node_id": node_id,
                "leased_at": now_str,
                "expires_at": expires_at,
                "state": initial_state
            }
            
            tmp = str(path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(lease, f, indent=2)
            os.replace(tmp, str(path))
            return lease
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def update_operator_lease_state(operator_id: str, state: str) -> Dict[str, Any]:
    """Updates the state of an active lease (e.g. from 'leased' to 'running')."""
    if state not in VALID_STATES:
        raise ValueError(f"Invalid lease state: {state}. Must be one of {VALID_STATES}")

    _ensure_dirs()
    path = OPERATOR_LEASE_DIR / f"{operator_id}.json"
    lock_path = OPERATOR_LEASE_DIR / f"{operator_id}.lock"
    
    with open(lock_path, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            if not path.exists():
                raise RuntimeError(f"No active lease exists for operator '{operator_id}'")
            
            lease = json.loads(path.read_text(encoding="utf-8"))
            if lease.get("expires_at", "") <= _now():
                raise RuntimeError(f"Lease for operator '{operator_id}' has expired")
                
            lease["state"] = state
            
            tmp = str(path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(lease, f, indent=2)
            os.replace(tmp, str(path))
            return lease
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def update_operator_lease_metadata(operator_id: str, **fields: Any) -> Dict[str, Any]:
    """Merge additional metadata into the active lease for an operator."""
    _ensure_dirs()
    path = OPERATOR_LEASE_DIR / f"{operator_id}.json"
    lock_path = OPERATOR_LEASE_DIR / f"{operator_id}.lock"

    with open(lock_path, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            if not path.exists():
                raise RuntimeError(f"No active lease exists for operator '{operator_id}'")

            lease = json.loads(path.read_text(encoding="utf-8"))
            if lease.get("expires_at", "") <= _now():
                raise RuntimeError(f"Lease for operator '{operator_id}' has expired")

            for key, value in fields.items():
                if value is None:
                    lease.pop(key, None)
                else:
                    lease[key] = value

            tmp = str(path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(lease, f, indent=2)
            os.replace(tmp, str(path))
            return lease
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def release_operator_lease(operator_id: str, reason: str = "completed") -> bool:
    """Releases the active lease for the operator."""
    _ensure_dirs()
    path = OPERATOR_LEASE_DIR / f"{operator_id}.json"
    lock_path = OPERATOR_LEASE_DIR / f"{operator_id}.lock"
    
    with open(lock_path, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            if not path.exists():
                return False
            path.unlink()
            return True
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


# ── State Classification ──────────────────────────────────────────────────────

def get_operator_runtime_state(operator_id: str) -> str:
    """Classifies the current runtime state of the operator."""
    config = get_operator_config(operator_id)
    if not config:
        return "disabled"
        
    # Standard check: check registry level enabled/disabled status
    if not config.get("enabled", True):
        return "disabled"
        
    # Check if registry state properties specify disabled
    reg_state = config.get("state", {})
    if isinstance(reg_state, dict):
        if reg_state.get("availability") == "disabled" or reg_state.get("runtime_state") == "disabled":
            return "disabled"
            
    # Check active lease (highest precedence for active state)
    lease = get_operator_lease(operator_id)
    if lease:
        state = lease.get("state")
        if state in {"leased", "running"} and _active_record_processes_dead(lease):
            release_operator_lease(operator_id, reason="stale_dead_pid")
            _clear_stale_active_status(operator_id)
        else:
            if state in VALID_STATES:
                return state
            return "leased"
        
    # Check dynamic status override
    status = get_operator_status(operator_id)
    if status:
        r_state = status.get("runtime_state")
        if r_state in {"leased", "running", "draining"} and (
            _active_record_processes_dead(status) or _active_status_without_process_stale(status)
        ):
            clear_operator_status(operator_id)
            r_state = ""
        if r_state in VALID_STATES:
            return r_state
            
    # Check registry baseline runtime_state
    if isinstance(reg_state, dict):
        baseline = reg_state.get("runtime_state")
        blocked_until = _parse_utc(str(reg_state.get("cooldown_until") or config.get("quota_refresh_at") or ""))
        if baseline in {"cooldown", "quota_exhausted", "auth_expired"} and blocked_until is not None:
            if blocked_until <= datetime.datetime.now(datetime.timezone.utc):
                baseline = ""
        if baseline in VALID_STATES:
            return baseline
            
    return "idle"


# ── Submit ───────────────────────────────────────────────────────────────────

# States that prevent task submission
_NON_DISPATCHABLE_STATES = {
    "disabled",
    "leased",
    "running",
    "draining",
    "cooldown",
    "quota_exhausted",
    "auth_expired",
}

# Required keys in a task envelope
_REQUIRED_ENVELOPE_KEYS = {"task_id", "sprint_id", "node_id", "operator_id", "task_type", "objective"}

_DEFAULT_LEASE_TTL = 3600


def _operatord_script_path() -> Path:
    deployed = HARNESS_DIR / "tools" / "operatord.py"
    if deployed.exists():
        return deployed
    return Path(__file__).resolve().parents[1] / "tools" / "operatord.py"


def _operatord_once_command(operator_id: str) -> list[str]:
    poll_interval = str(os.environ.get("SOLAR_OPERATORD_ONCE_POLL_INTERVAL", "0.2"))
    return [
        sys.executable,
        str(_operatord_script_path()),
        "daemon",
        "--operator",
        operator_id,
        "--once",
        "--poll-interval",
        poll_interval,
    ]


def _kick_operatord_once(operator_id: str) -> int:
    """Best-effort bootstrap so submit() progresses beyond leased -> running."""
    env = os.environ.copy()
    env["HARNESS_DIR"] = str(HARNESS_DIR)
    # Observability: send operatord output to a per-operator log instead of /dev/null,
    # so a crash/exit is diagnosable (previously discarded -> operatord deaths were invisible).
    try:
        _log_dir = HARNESS_DIR / "run" / "operator-daemons"
        _log_dir.mkdir(parents=True, exist_ok=True)
        _log_out = open(_log_dir / f"{operator_id}.log", "a", encoding="utf-8")
    except Exception:
        _log_out = subprocess.DEVNULL
    proc = subprocess.Popen(
        _operatord_once_command(operator_id),
        stdin=subprocess.DEVNULL,
        stdout=_log_out,
        stderr=subprocess.STDOUT,
        cwd=str(HARNESS_DIR),
        env=env,
        start_new_session=True,
    )
    # The auto-kicked daemon is itself run-owned.  Register it immediately so
    # `solar-harness kill` can reap both the daemon and the detached worker it
    # may spawn.  Fail closed if ownership cannot be established: leaving an
    # unregistered daemon is precisely the RC9 live-run leak this seam guards.
    try:
        import run_process_registry as _rpr

        _rpr.register(
            "harness",
            "operatord",
            int(proc.pid),
            meta={"operator_id": str(operator_id)},
            harness_dir=HARNESS_DIR,
        )
    except Exception:
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        raise
    return int(proc.pid)


def _auto_kick_enabled() -> bool:
    value = str(os.environ.get("SOLAR_OPERATORD_AUTO_KICK", "1")).strip().lower()
    return value not in {"0", "false", "no", "off"}


def submit(task_envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Validates a task, checks operator dispatchability, acquires a lease,
    and writes the task envelope to the operator's inbox.

    Args:
        task_envelope: Must contain task_id, sprint_id, node_id, operator_id,
            task_type, and objective. Optional: lease_ttl_seconds.

    Returns:
        dict with task_id, operator_id, lease_id, inbox_path, status, submitted_at.

    Raises:
        ValueError: Malformed envelope or unknown operator.
        RuntimeError: Operator not dispatchable (disabled/leased/running/
            quota_exhausted/auth_expired) or missing persona binding.
    """
    # ── 1. Envelope validation ─────────────────────────────────────────────
    missing = _REQUIRED_ENVELOPE_KEYS - set(task_envelope.keys())
    if missing:
        raise ValueError(f"Task envelope missing required keys: {sorted(missing)}")

    operator_id = task_envelope["operator_id"]
    task_id = task_envelope["task_id"]
    sprint_id = task_envelope["sprint_id"]
    node_id = task_envelope["node_id"]
    ttl = int(task_envelope.get("lease_ttl_seconds", _DEFAULT_LEASE_TTL))

    # ── 1b. Capability Capsule resolution gate (capability-native only) ───
    payload = dict(task_envelope)
    capability_capsule_requested = (
        payload.get("capability_native")
        or payload.get("capability_capsule_id")
        or payload.get("execution_capsule_id")
    )
    if capability_capsule_requested:
        from capability_capsules import resolve_capability_capsule_for_envelope

        resolved_capsule = resolve_capability_capsule_for_envelope(payload)
        payload["resolved_capability_capsule"] = resolved_capsule
        payload["capability_capsule_id"] = resolved_capsule["capability_capsule_id"]
        payload.pop("execution_capsule_id", None)

    # ── 2. Operator existence check ────────────────────────────────────────
    config = get_operator_config(operator_id)
    if config is None:
        raise ValueError(f"Unknown operator: '{operator_id}' not found in registry")

    # ── 3. Dispatchability check ───────────────────────────────────────────
    current_state = get_operator_runtime_state(operator_id)
    if current_state in _NON_DISPATCHABLE_STATES:
        reason = (
            "operator_busy"
            if current_state in {"leased", "running", "draining"}
            else "operator_unavailable"
        )
        raise OperatorSubmitRejected(
            f"Operator '{operator_id}' is not dispatchable: state={current_state}",
            reason=reason,
            state=current_state,
        )

    # ── 4. Persona binding check ───────────────────────────────────────────
    resolve_persona(operator_id, config, OPERATOR_PERSONAS_DIR, load_content=False)

    # ── 5. Acquire lease ──────────────────────────────────────────────────
    lease = acquire_operator_lease(
        operator_id=operator_id,
        task_id=task_id,
        sprint_id=sprint_id,
        node_id=node_id,
        ttl_seconds=ttl,
        initial_state="leased",
    )

    # ── 6. Write envelope to inbox (atomic) ───────────────────────────────
    inbox_dir = _ensure_inbox_dir(operator_id)
    inbox_path = inbox_dir / f"{task_id}.json"
    tmp_path = str(inbox_path) + ".tmp"
    submitted_at = _now()
    payload["submitted_at"] = submitted_at
    payload["lease_expires_at"] = lease["expires_at"]

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, str(inbox_path))

    lease_id = f"{operator_id}:{task_id}:{lease['leased_at']}"
    daemon_pid: Optional[int] = None
    if _auto_kick_enabled():
        try:
            daemon_pid = _kick_operatord_once(operator_id)
        except Exception as exc:
            try:
                if inbox_path.exists():
                    inbox_path.unlink()
            except Exception:
                pass
            try:
                release_operator_lease(operator_id, reason="submit_bootstrap_failed")
            except Exception:
                pass
            raise RuntimeError(
                f"Operator '{operator_id}' submit bootstrap failed: unable to start operatord --once: {exc}"
            ) from exc

    # AC-R5.1: the envelope write IS the stage-start route evidence — a run
    # killed before any result still proves what was routed where. Recorded
    # AFTER the auto-kick block (round-4 G8): a bootstrap failure rolls the
    # envelope+lease back, so a 'submitted' record for a stage that never ran
    # would be untruthful.
    _ledger_route(sprint_id, node_id, task_id, "submitted", {
        "provider": str((config or {}).get("provider") or ""),
        "model": str((config or {}).get("model") or ""),
        "operator_id": operator_id,
        "backend": str((config or {}).get("backend") or ""),
        "started_at": submitted_at,
    })

    result = {
        "task_id": task_id,
        "operator_id": operator_id,
        "lease_id": lease_id,
        "inbox_path": str(inbox_path),
        "status": "submitted",
        "submitted_at": submitted_at,
        "daemon_pid": daemon_pid,
    }
    return result


# ── Secret Scrubbing ─────────────────────────────────────────────────────────

# Compiled once at module load for performance.
_SECRET_PATTERNS: list = [
    (re.compile(r'sk-[a-zA-Z0-9]{32,}'), '[SCRUBBED]'),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}'), '[SCRUBBED]'),
    (re.compile(r'github_pat_[a-zA-Z0-9_]{82}'), '[SCRUBBED]'),
    (re.compile(r'AKIA[0-9A-Z]{16}'), '[SCRUBBED]'),
    (re.compile(r'Bearer [a-zA-Z0-9\-._~+/=]{20,}'), 'Bearer [SCRUBBED]'),
    (re.compile(r'(?i)(api[_-]?key|apikey|api_secret)\s*[=:]\s*[^\s"\']{8,}'), r'\1=[SCRUBBED]'),
    (re.compile(r'(?i)(password|passwd)\s*[=:]\s*[^\s"\']{4,}'), r'\1=[SCRUBBED]'),
    (re.compile(r'(?i)(token|secret)\s*[=:]\s*[^\s"\']{8,}'), r'\1=[SCRUBBED]'),
]


def scrub_secrets(text: str) -> str:
    """Replace known credential patterns with [SCRUBBED]."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ── Inbox Helpers ─────────────────────────────────────────────────────────────

def list_inbox_tasks(operator_id: str) -> List[tuple]:
    """Return pending task envelopes from the operator inbox.

    Returns a list of ``(task_id, envelope_dict, envelope_path)`` tuples
    sorted by file name (oldest first, assuming task_id timestamps sort
    lexicographically).
    """
    inbox = OPERATOR_INBOX_DIR / operator_id
    if not inbox.exists():
        return []
    results = []
    for p in sorted(inbox.glob("*.json")):
        try:
            envelope = json.loads(p.read_text(encoding="utf-8"))
            results.append((p.stem, envelope, p))
        except Exception:
            pass
    return results


# ── Heartbeat ─────────────────────────────────────────────────────────────────

def write_heartbeat(
    operator_id: str,
    state: str,
    *,
    current_task_id: Optional[str] = None,
    worker_pid: Optional[int] = None,
    resolved_persona: Optional[str] = None,
    model_route: Optional[Dict[str, Any]] = None,
) -> None:
    """Write a daemon heartbeat to the operator status file.

    Uses ``runtime_state`` as the primary key so that
    ``get_operator_runtime_state`` picks it up correctly, and also writes
    ``state`` for daemon-readable convenience.
    """
    _ensure_dirs()
    path = OPERATOR_STATUS_DIR / f"{operator_id}.json"
    lock_path = OPERATOR_STATUS_DIR / f"{operator_id}.lock"

    with open(lock_path, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            existing: Dict[str, Any] = {}
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}
            preserved_runtime_state = str(existing.get("runtime_state") or "").strip()
            preserve_block_override = preserved_runtime_state in {"cooldown", "quota_exhausted", "auth_expired"}

            data: Dict[str, Any] = {
                "operator_id": operator_id,
                "runtime_state": preserved_runtime_state if preserve_block_override else state,
                "state": state,
                "heartbeat_at": _now(),
            }
            if current_task_id is not None:
                data["current_task_id"] = current_task_id
            if worker_pid is not None:
                data["worker_pid"] = int(worker_pid)
            if resolved_persona is not None:
                data["resolved_persona"] = resolved_persona
            if model_route:
                route = dict(model_route)
                data["model_route"] = route
                for key in ("requested_model", "routing_model", "effective_provider", "effective_model"):
                    if str(route.get(key) or "").strip():
                        data[key] = str(route[key])
            if preserve_block_override:
                if str(existing.get("expires_at") or "").strip():
                    data["expires_at"] = str(existing["expires_at"])
                if str(existing.get("updated_at") or "").strip():
                    data["updated_at"] = str(existing["updated_at"])

            tmp = str(path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, str(path))
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


# ── Result Artifacts ──────────────────────────────────────────────────────────

def write_result(
    operator_id: str,
    task_id: str,
    sprint_id: str,
    node_id: str,
    status: str,
    exit_code: int,
    started_at: str,
    finished_at: str,
    log_tail: str,
    model_route: Optional[Dict[str, Any]] = None,
) -> Path:
    """Write the result.json artifact for a completed task.

    ``log_tail`` is scrubbed for secrets before writing.  The artifact is
    written atomically via a .tmp rename.

    Returns the path to the written result.json.
    """
    result_dir = OPERATOR_RESULTS_DIR / operator_id / task_id
    result_dir.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {
        "task_id": task_id,
        "operator_id": operator_id,
        "sprint_id": sprint_id,
        "node_id": node_id,
        "status": status,
        "exit_code": exit_code,
        "started_at": started_at,
        "finished_at": finished_at,
        "log_tail": scrub_secrets(log_tail),
    }
    if model_route:
        route = dict(model_route)
        result["model_route"] = route
        for key in ("requested_model", "routing_model", "effective_provider", "effective_model"):
            if str(route.get(key) or "").strip():
                result[key] = str(route[key])

    result_path = result_dir / "result.json"
    tmp_path = str(result_path) + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    os.replace(tmp_path, str(result_path))

    converge_status_file(
        HARNESS_DIR / "run" / "multi-task" / task_id / "status.json",
        result,
        result_path=result_path,
    )

    route = dict(model_route or {})
    try:
        config = get_operator_config(operator_id) or {}
    except Exception:
        config = {}
    _ledger_route(sprint_id, node_id, task_id, "completed", {
        "provider": str(route.get("effective_provider") or config.get("provider") or ""),
        "model": str(route.get("effective_model") or route.get("routing_model")
                     or route.get("requested_model") or config.get("model") or ""),
        "operator_id": operator_id,
        "backend": str(config.get("backend") or ""),
        "exit_code": exit_code,
        "started_at": started_at,
        "finished_at": finished_at,
        "result_status": status,
    })
    graph_callback = _sync_graph_after_route_result(sprint_id, result, result_path)
    callback_path = result_dir / "graph-callback.json"
    callback_tmp_path = str(callback_path) + ".tmp"
    with open(callback_tmp_path, "w", encoding="utf-8") as f:
        json.dump(graph_callback, f, indent=2, default=str)
    os.replace(callback_tmp_path, str(callback_path))
    return result_path


# ── CLI Interface ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Solar Operator Runtime State & Lease Helper")
    subparsers = parser.add_subparsers(dest="cmd", help="Sub-commands")
    
    # status
    status_parser = subparsers.add_parser("status", help="Get operator runtime state")
    status_parser.add_argument("--operator", required=True, help="Operator ID")
    
    # acquire
    acq_parser = subparsers.add_parser("acquire", help="Acquire operator lease")
    acq_parser.add_argument("--operator", required=True, help="Operator ID")
    acq_parser.add_argument("--task-id", required=True, help="Task ID")
    acq_parser.add_argument("--sprint-id", required=True, help="Sprint ID")
    acq_parser.add_argument("--node-id", required=True, help="Node ID")
    acq_parser.add_argument("--ttl", type=int, required=True, help="TTL in seconds")
    acq_parser.add_argument("--state", default="leased", help="Initial lease state")
    
    # update-state
    update_parser = subparsers.add_parser("update-state", help="Update lease state")
    update_parser.add_argument("--operator", required=True, help="Operator ID")
    update_parser.add_argument("--state", required=True, help="New lease state")
    
    # release
    rel_parser = subparsers.add_parser("release", help="Release operator lease")
    rel_parser.add_argument("--operator", required=True, help="Operator ID")
    rel_parser.add_argument("--reason", default="completed", help="Release reason")
    
    # set-override
    override_parser = subparsers.add_parser("set-override", help="Set dynamic status override")
    override_parser.add_argument("--operator", required=True, help="Operator ID")
    override_parser.add_argument("--state", required=True, help="Override state")
    override_parser.add_argument("--ttl", type=int, help="Optional TTL in seconds")
    
    # clear-override
    clear_parser = subparsers.add_parser("clear-override", help="Clear dynamic status override")
    clear_parser.add_argument("--operator", required=True, help="Operator ID")

    # submit
    submit_parser = subparsers.add_parser("submit", help="Submit a task envelope to an operator inbox")
    submit_parser.add_argument("--envelope", required=True, help="Path to task envelope JSON file")
    
    args = parser.parse_args()
    
    try:
        if args.cmd == "status":
            state = get_operator_runtime_state(args.operator)
            lease = get_operator_lease(args.operator)
            override = get_operator_status(args.operator)
            
            output = {
                "operator_id": args.operator,
                "runtime_state": state,
                "lease": lease,
                "override": override
            }
            print(json.dumps(output, indent=2))
            return 0
            
        elif args.cmd == "acquire":
            lease = acquire_operator_lease(
                operator_id=args.operator,
                task_id=args.task_id,
                sprint_id=args.sprint_id,
                node_id=args.node_id,
                ttl_seconds=args.ttl,
                initial_state=args.state
            )
            print(json.dumps({"acquired": True, "lease": lease}, indent=2))
            return 0
            
        elif args.cmd == "update-state":
            lease = update_operator_lease_state(
                operator_id=args.operator,
                state=args.state
            )
            print(json.dumps({"updated": True, "lease": lease}, indent=2))
            return 0
            
        elif args.cmd == "release":
            released = release_operator_lease(args.operator, args.reason)
            print(json.dumps({"released": released}, indent=2))
            return 0 if released else 1
            
        elif args.cmd == "set-override":
            override = set_operator_status(
                operator_id=args.operator,
                runtime_state=args.state,
                ttl_seconds=args.ttl
            )
            print(json.dumps({"override_set": True, "override": override}, indent=2))
            return 0
            
        elif args.cmd == "clear-override":
            clear_operator_status(args.operator)
            print(json.dumps({"override_cleared": True}, indent=2))
            return 0

        elif args.cmd == "submit":
            envelope_path = Path(args.envelope)
            if not envelope_path.exists():
                print(json.dumps({"error": f"Envelope file not found: {args.envelope}"}), file=sys.stderr)
                return 1
            envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
            result = submit(envelope)
            print(json.dumps(result, indent=2))
            return 0

        else:
            parser.print_help()
            return 1
            
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
