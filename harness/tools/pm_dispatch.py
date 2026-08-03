#!/usr/bin/env python3
"""pm_dispatch.py — PM 发号施令：从主四分屏 PM pane 向无头算子 pane 派发任务。

用法：
  python3 pm_dispatch.py submit --role builder --objective "检查 gate_check 函数"
  python3 pm_dispatch.py submit --operator mini-claude-sonnet-builder --objective "..."
  python3 pm_dispatch.py fleet-status
  python3 pm_dispatch.py inbox [--limit N]
  python3 pm_dispatch.py result --task-id pm-xxx

直接通过 solar-harness.sh：
  solar-harness pm-dispatch --role builder --objective "..."
  solar-harness pm-fleet status
  solar-harness pm-fleet inbox
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid
import io
import contextlib
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

# The tools dir is sys.path[0] when this file runs as a script, and it shadows
# ~150 shared-name lib modules with stale copies. An inherited PYTHONPATH that
# merely CONTAINS harness/lib (the live-e2e sandbox env) satisfies the usual
# 'if lib not in sys.path' guard without granting PRECEDENCE, so
# `import operator_runtime` still resolved the tools copy — the one without
# the Lane 3 route-record hooks (P2 smoke-4: zero route records while every
# other ledger kind landed). Force this script's sibling lib to the front.
_PM_LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")
if sys.path and sys.path[0] != _PM_LIB_DIR:
    while _PM_LIB_DIR in sys.path:
        sys.path.remove(_PM_LIB_DIR)
    sys.path.insert(0, _PM_LIB_DIR)

from task_lifecycle import activate_execution_attempt

HOME = Path.home()
HARNESS_DIR = Path(
    os.environ.get("HARNESS_DIR")
    or os.environ.get("SOLAR_HARNESS_DIR")
    or HOME / ".solar" / "harness"
)
PHYSICAL_OPERATORS_PATH = Path(
    os.environ.get("SOLAR_MULTI_TASK_OPERATORS", HARNESS_DIR / "config" / "physical-operators.json")
)
PERSONAS_DIR = HARNESS_DIR / "personas"
PM_INBOX_DIR = HARNESS_DIR / "run" / "pm-inbox"
OPERATOR_INBOX_DIR = HARNESS_DIR / "run" / "operator-inbox"
OPERATOR_RESULTS_DIR = HARNESS_DIR / "run" / "operator-results"
OPERATOR_STATUS_DIR = HARNESS_DIR / "run" / "operator-status"
SPRINTS_DIR = Path(os.environ.get("SOLAR_HARNESS_SPRINTS_DIR", HARNESS_DIR / "sprints"))
REPO_HARNESS_DIR = Path(__file__).resolve().parents[1]

# ── 角色别名映射 ───────────────────────────────────────────────────────────────
ROLE_ALIASES: dict[str, str] = {
    "build": "builder",
    "builder-main": "builder",
    "implementation": "builder",
    "implementer": "builder",
    "coder": "builder",
    "dev": "builder",
    "plan": "planner",
    "planning": "planner",
    "architect": "planner",
    "design": "planner",
    "eval": "evaluator",
    "review": "evaluator",
    "judge": "evaluator",
    "reviewer": "evaluator",
    "verifier": "evaluator",
    "knowledge": "builder",   # 知识提取走 builder 角色
    "extract": "builder",
    "product": "pm",
    "product-manager": "pm",
}

NON_DISPATCHABLE_STATES = {"leased", "running", "draining", "cooldown", "quota_exhausted", "auth_expired", "disabled"}
RATE_LIMIT_PRUNER_LABEL = os.environ.get("SOLAR_RATE_LIMIT_PRUNER_LABEL", "com.solar.harness-rate-limit-pruner")
DEFAULT_OPERATOR_PROVIDERS = frozenset(
    p.strip().lower()
    for p in os.environ.get(
        "SOLAR_PM_DEFAULT_PROVIDERS",
        os.environ.get("SOLAR_MULTI_TASK_DEFAULT_PROVIDERS", ""),
    ).split(",")
    if p.strip()
)


def _operator_matches_provider_policy(op: dict[str, Any]) -> bool:
    if not DEFAULT_OPERATOR_PROVIDERS:
        return True
    provider = str(op.get("provider") or op.get("vendor") or "").strip().lower()
    return bool(provider and provider in DEFAULT_OPERATOR_PROVIDERS)


def _provider_policy_label() -> str:
    return ",".join(sorted(DEFAULT_OPERATOR_PROVIDERS))


def _runtime_mode_from_env() -> str:
    runtime = str(os.environ.get("SOLAR_PANE_RUNTIME") or os.environ.get("SOLAR_RUNTIME") or "").strip().lower()
    if runtime in {"codex", "claude"}:
        return runtime
    if DEFAULT_OPERATOR_PROVIDERS == {"openai"}:
        return "codex"
    if DEFAULT_OPERATOR_PROVIDERS == {"anthropic"}:
        return "claude"
    return runtime or "mixed"


def _pm_work_dir_for_sprint(sprint_id: str, explicit: str = "") -> str:
    explicit = str(explicit or "").strip()
    if explicit:
        path = Path(explicit).expanduser()
    else:
        sid = str(sprint_id or "").strip() or f"pm-adhoc-{_short_id()}"
        path = SPRINTS_DIR / sid / "workdir"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _graph_path_for_sprint(sprint_id: str) -> str:
    sid = str(sprint_id or "").strip()
    if not sid:
        return ""
    path = SPRINTS_DIR / f"{sid}.task_graph.json"
    return str(path) if path.exists() else ""


def _build_pm_operator_envelope(
    *,
    task_id: str,
    sprint_id: str,
    node_id: str,
    operator_id: str,
    operator: dict[str, Any],
    task_type: str,
    objective: str,
    dispatch_file: Path,
    result_path: str,
    context: str = "",
    role: str = "",
    work_dir: str = "",
    logical_operator: str = "",
    task_graph_node: dict[str, Any] | None = None,
    capsule_submit: dict[str, Any] | None = None,
    expected_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    """Build the canonical PM/operator envelope.

    PM/planner dispatch and graph/multi-task dispatch used to carry different
    execution context. Codex command operators need the same deterministic
    workdir contract regardless of the path that submitted them.
    """
    capsule_submit = capsule_submit or {}
    graph_path = _graph_path_for_sprint(sprint_id)
    graph_policy: dict[str, Any] = {}
    if graph_path:
        try:
            payload = json.loads(Path(graph_path).read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                graph_policy = payload
        except (OSError, json.JSONDecodeError):
            graph_policy = {}
    envelope: dict[str, Any] = {
        "task_id": task_id,
        "sprint_id": sprint_id,
        "node_id": node_id,
        "operator_id": operator_id,
        "task_type": task_type or "pm_order",
        "objective": objective[:300],
        "dispatch_file": str(dispatch_file),
        "result_path": result_path,
        "issued_by": "pm_pane",
        "issued_at": _now(),
        "pm_context": context[:500] if context else "",
        "requested_role": normalize_role(role),
        "work_dir": _pm_work_dir_for_sprint(sprint_id, work_dir),
        "graph_path": graph_path,
        "runtime_mode": _runtime_mode_from_env(),
        "provider_policy": _provider_policy_label(),
        "operator_provider": str(operator.get("provider") or operator.get("vendor") or ""),
        "operator_backend": str(operator.get("backend") or ""),
        "operator_model": str(operator.get("model") or ""),
        "workflow_contract": str(graph_policy.get("workflow_contract") or ""),
        "strict_filesystem_boundaries": bool(graph_policy.get("strict_filesystem_boundaries")),
        "expected_artifacts": list(expected_artifacts or []),
    }
    if not envelope["graph_path"]:
        envelope.pop("graph_path", None)
    if operator.get("borrowed_for_role"):
        envelope["borrowed_for_role"] = operator.get("borrowed_for_role")
        envelope["borrowed_from_roles"] = operator.get("borrowed_from_roles", [])
        envelope["borrowed_original_role"] = operator.get("borrowed_original_role", "")
        envelope["borrowed_reason"] = operator.get("borrowed_reason", "")
    if logical_operator:
        envelope["logical_operator"] = logical_operator
    if task_graph_node:
        envelope["task_graph_node"] = {
            "id": task_graph_node.get("id"),
            "goal": task_graph_node.get("goal"),
            "acceptance": task_graph_node.get("acceptance", []),
            "requirement_ids": task_graph_node.get("requirement_ids", []),
        }
        envelope["read_scope"] = list(task_graph_node.get("read_scope") or [])
        envelope["write_scope"] = list(task_graph_node.get("write_scope") or [])
        envelope["write_scope_root"] = envelope["work_dir"]
        envelope["write_scope_resolution"] = "relative_to_write_scope_root"
    if capsule_submit.get("capability_capsule_id"):
        envelope["capability_native"] = bool(capsule_submit.get("capability_native", True))
        envelope["capability_capsule_id"] = str(capsule_submit["capability_capsule_id"])
        envelope["capsule_plan"] = capsule_submit.get("capsule_plan", {})
    if capsule_submit.get("capsule_override_reason"):
        envelope["capsule_override_reason"] = str(capsule_submit["capsule_override_reason"])
    return envelope


CODE_EXEC_TASK_TYPES = {
    "implementation",
    "code-edit",
    "repo-modification",
    "fast-patch",
    "patch",
    "refactor",
    "test",
    "tests",
    "debugging",
    "build",
}
CODE_EXEC_ROLES = {"builder", "implementation", "implementer", "coder", "dev"}
CODE_EXEC_AVOID_MARKERS = {"implementation", "code-edit", "repo-modification"}
BUILDER_READY_LOGICAL_OPERATORS = {
    "ImplementationWorker",
    "PatchWorker",
    "TestDesigner",
    "TestRunner",
    "BenchmarkRunner",
    "ResearchSynthesizer",
    "ArtifactCurator",
}
NON_BUILDER_READY_LOGICAL_OPERATORS = {
    "DeepArchitect",
    "ParallelExplorer",
    "ResearchScout",
    "ContextCompressor",
    "Critic",
    "Verifier",
    "VerifierLite",
    "SecurityGate",
    "QuotaBroker",
}


def _load_concurrency_policy_module() -> Any | None:
    try:
        lib_dir = HARNESS_DIR / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        import concurrency_policy  # type: ignore

        return concurrency_policy
    except Exception:
        return None


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _env_truthy(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _pm_operator_pool_enabled() -> bool:
    return _env_truthy("SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH") or _env_truthy("SOLAR_PM_OPERATOR_DISPATCH")


def _new_planner_dispatch_claim(now: str) -> dict[str, Any]:
    """Claim planner dispatch before ``prd_ready`` becomes externally visible.

    Intake publishes the status before the one-shot autopilot submits the
    physical planner task.  Without a claim, the concurrently polling
    coordinator can dispatch the legacy planner pane in that gap.  The claim
    is a bounded lease: autopilot promotes it to submitted or releases it on
    failure, and the coordinator may recover after expiry if intake crashes.
    The default covers the 120s consumer boundary plus the 60s role-submit
    boundary; deployments may tune it without changing code.
    """
    try:
        ttl_seconds = max(1, int(os.environ.get("SOLAR_PLANNER_DISPATCH_CLAIM_TTL_SEC", "180") or "180"))
    except (TypeError, ValueError):
        ttl_seconds = 180
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=ttl_seconds)
    return {
        "owner": "operator_pool",
        "state": "pending",
        "claimed_at": now,
        "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ttl_seconds": ttl_seconds,
        "source": "requirement_compiler",
    }


def _short_id() -> str:
    return str(uuid.uuid4())[:8]



def capture_entrypoint_raw_intent(
    *,
    source_channel: str,
    text: str,
    sprint_id: str = "",
    node_id: str = "",
    role: str = "",
    repo: str = "",
) -> dict[str, Any]:
    full_text = text.strip()
    if sprint_id or node_id or role:
        full_text = (
            f"[entrypoint_metadata]\n"
            f"sprint_id: {sprint_id or 'N/A'}\n"
            f"node_id: {node_id or 'N/A'}\n"
            f"role: {role or 'N/A'}\n\n"
            f"[raw_request]\n{full_text}"
        )
    cmd = [
        sys.executable,
        str(HARNESS_DIR / "lib" / "intent_gateway.py"),
        "capture",
        "--source-channel", source_channel,
        "--actor", "user",
        "--device", "mac_mini_pm_dispatch",
        "--repo", repo or str(HARNESS_DIR),
        "--source-trust", source_channel,
        "--text", full_text,
        "--json",
    ]
    if sprint_id:
        cmd.extend(["--sprint-id", sprint_id])
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "intent_gateway capture failed").strip())
    payload = json.loads(proc.stdout)
    intent_id = str(payload.get("intent_id") or "")
    if intent_id:
        consumer_cmd = [
            sys.executable,
            str(HARNESS_DIR / "lib" / "intent_consumer.py"),
            "consume",
            "--intent-id", intent_id,
            "--json",
        ]
        consumer = subprocess.run(consumer_cmd, text=True, capture_output=True, timeout=120)
        if consumer.returncode != 0:
            raise RuntimeError((consumer.stderr or consumer.stdout or "intent_consumer failed").strip())
        payload["consumer"] = json.loads(consumer.stdout)
    return payload


def print_intent_capture(payload: dict[str, Any], entrypoint: str) -> None:
    print("✅ RawIntent 已捕获")
    print(f"   entrypoint  = {entrypoint}")
    print(f"   intent_id   = {payload.get('intent_id', '')}")
    print(f"   title       = {payload.get('title', '')}")
    print(f"   lane        = {payload.get('lane', '')}")
    print(f"   raw_intent  = {payload.get('raw_intent', '')}")
    print(f"   requirement = {payload.get('requirement_ir', '')}")
    print("   direct_dispatch = disabled")


# ── Registry ──────────────────────────────────────────────────────────────────

def load_registry() -> dict[str, Any]:
    _prune_expired_operator_blocks()
    if not PHYSICAL_OPERATORS_PATH.exists():
        return {"version": 1, "operators": {}}
    try:
        return json.loads(PHYSICAL_OPERATORS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "operators": {}}


def _prune_expired_operator_blocks() -> dict[str, Any]:
    try:
        lib_dir = HARNESS_DIR / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        import operator_flow_control as ofc  # type: ignore

        return ofc.prune_expired_operator_config_blocks()
    except Exception as exc:
        return {"ok": False, "reason": f"prune_failed:{type(exc).__name__}", "error": str(exc)}


def _load_operator_runtime_module() -> Any | None:
    """Best-effort load of operator_runtime for lease-aware runtime state."""
    try:
        lib_dir = HARNESS_DIR / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        import operator_runtime  # type: ignore

        operator_runtime.HARNESS_DIR = HARNESS_DIR
        operator_runtime.OPERATOR_LEASE_DIR = HARNESS_DIR / "run" / "operator-leases"
        operator_runtime.OPERATOR_STATUS_DIR = HARNESS_DIR / "run" / "operator-status"
        operator_runtime.OPERATOR_INBOX_DIR = HARNESS_DIR / "run" / "operator-inbox"
        operator_runtime.OPERATOR_RESULTS_DIR = HARNESS_DIR / "run" / "operator-results"
        operator_runtime.OPERATOR_PERSONAS_DIR = HARNESS_DIR / "personas"
        operator_runtime.PHYSICAL_OPERATORS_PATH = PHYSICAL_OPERATORS_PATH
        return operator_runtime
    except Exception:
        return None


def get_operator_runtime_state(operator_id: str) -> str:
    runtime_mod = _load_operator_runtime_module()
    if runtime_mod is not None:
        try:
            state = runtime_mod.get_operator_runtime_state(operator_id)
            if state:
                return str(state)
        except Exception:
            pass

    status_file = OPERATOR_STATUS_DIR / f"{operator_id}.json"
    if not status_file.exists():
        return "idle"
    try:
        data = json.loads(status_file.read_text(encoding="utf-8"))
        return str(data.get("runtime_state", "idle"))
    except Exception:
        return "idle"


def get_operator_status_data(operator_id: str) -> dict[str, Any]:
    """Return the full status JSON for an operator, or empty dict if absent/expired."""
    status_file = OPERATOR_STATUS_DIR / f"{operator_id}.json"
    if not status_file.exists():
        return {}
    try:
        return json.loads(status_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _runtime_state_for_operator_record(operator_id: str, op: dict[str, Any]) -> str:
    state = get_operator_runtime_state(operator_id)
    if state == "disabled" and operator_id:
        status = get_operator_status_data(str(operator_id))
        status_state = str(status.get("runtime_state") or "").strip()
        if status_state:
            return status_state
        if op.get("enabled", False) and op.get("available", False):
            return "idle"
    return state


def _pid_exists(pid: int | None) -> bool:
    if not pid or pid <= 0:
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


def _parse_utc(value: str) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def _rate_limit_pruner_status() -> dict[str, Any]:
    """Return launchd/install status for the periodic operator block pruner."""
    plist_path = HOME / "Library" / "LaunchAgents" / f"{RATE_LIMIT_PRUNER_LABEL}.plist"
    stdout_log = HARNESS_DIR / "logs" / "operator-rate-limit-pruner.out.log"
    stderr_log = HARNESS_DIR / "logs" / "operator-rate-limit-pruner.err.log"
    payload: dict[str, Any] = {
        "label": RATE_LIMIT_PRUNER_LABEL,
        "plist_path": str(plist_path),
        "installed": plist_path.exists(),
        "launchd_loaded": False,
        "state": "unknown",
        "runs": None,
        "last_exit_code": None,
        "run_interval_seconds": None,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
    }
    if shutil.which("launchctl") is None:
        payload["state"] = "launchctl_unavailable"
        return payload
    try:
        result = subprocess.run(
            ["launchctl", "print", f"{_launchd_domain()}/{RATE_LIMIT_PRUNER_LABEL}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        payload["state"] = f"launchctl_error:{type(exc).__name__}"
        return payload
    if result.returncode != 0:
        payload["state"] = "not_loaded"
        return payload
    output = result.stdout or result.stderr or ""
    payload["launchd_loaded"] = True
    state_match = re.search(r"^\s*state = ([^\n]+)", output, re.M)
    runs_match = re.search(r"^\s*runs = (\d+)", output, re.M)
    exit_match = re.search(r"^\s*last exit code = (-?\d+)", output, re.M)
    interval_match = re.search(r"^\s*run interval = (\d+) seconds", output, re.M)
    if state_match:
        payload["state"] = state_match.group(1).strip()
    if runs_match:
        payload["runs"] = int(runs_match.group(1))
    if exit_match:
        payload["last_exit_code"] = int(exit_match.group(1))
    if interval_match:
        payload["run_interval_seconds"] = int(interval_match.group(1))
    return payload


def _operator_block_info(op_id: str, op: dict[str, Any], runtime_state: str, reason: str) -> dict[str, Any]:
    state = op.get("state") if isinstance(op.get("state"), dict) else {}
    status = get_operator_status_data(op_id)
    quota_state = str(op.get("quota_guard_state") or "").strip().lower()
    expires_at = str(
        op.get("quota_refresh_at")
        or state.get("cooldown_until")
        or status.get("expires_at")
        or ""
    ).strip()
    block_type = "none"
    reason_l = (reason or "").lower()
    state_l = (runtime_state or "").lower()
    if quota_state in {"cooldown", "quota_exhausted", "auth_expired"}:
        block_type = quota_state
    elif state_l in {"cooldown", "quota_exhausted", "auth_expired"}:
        block_type = state_l
    elif "health_check_failed" in reason_l or "unavailable:" in reason_l:
        block_type = "health"
    elif state_l in {"leased", "running", "draining"}:
        block_type = "busy"
    elif runtime_state == "disabled" or reason_l.startswith("disabled"):
        block_type = "disabled"
    elif reason:
        block_type = "other"
    return {
        "block_type": block_type,
        "quota_guard_state": quota_state or "ok",
        "cooldown_until": expires_at,
        "cooldown_eta": _format_reset_eta(expires_at),
    }


def _maybe_clear_stale_runtime(operator_id: str, state: str) -> str:
    """Best-effort release of clearly dead leases before declaring a builder busy."""
    if state not in {"leased", "running"}:
        return state
    policy_mod = _load_concurrency_policy_module()
    if policy_mod is None:
        return state
    try:
        recovery = policy_mod.recovery_settings()
        if not bool(recovery.get("auto_clear_stale_dead_pid", True)):
            return state
        stale_seconds = int(recovery.get("stale_runtime_seconds", 900))
    except Exception:
        stale_seconds = 900

    runtime_mod = _load_operator_runtime_module()
    if runtime_mod is None:
        return state
    try:
        lease = runtime_mod.get_operator_lease(operator_id)
    except Exception:
        lease = None
    if not isinstance(lease, dict):
        return state

    leased_at = _parse_utc(str(lease.get("leased_at") or ""))
    now = datetime.datetime.now(datetime.timezone.utc)
    if leased_at is None or (now - leased_at).total_seconds() < stale_seconds:
        return state

    dead_pids: list[str] = []
    for key in ("worker_pid", "daemon_pid"):
        raw = lease.get(key)
        try:
            pid = int(raw) if raw is not None else None
        except Exception:
            pid = None
        if pid is not None and not _pid_exists(pid):
            dead_pids.append(f"{key}={pid}")
    if not dead_pids:
        return state

    try:
        runtime_mod.release_operator_lease(operator_id, reason="builder_pool_dead_pid_recovery")
        return "idle"
    except Exception:
        return state


def _health_cache_path(operator_id: str) -> Path:
    return HARNESS_DIR / "run" / "operator-health" / f"{operator_id}.json"


def _read_health_cache(operator_id: str, max_age_seconds: int) -> tuple[bool | None, str]:
    path = _health_cache_path(operator_id)
    if max_age_seconds <= 0 or not path.exists():
        return None, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        checked_at = float(data.get("checked_at_epoch", 0))
        if time.time() - checked_at <= max_age_seconds:
            return bool(data.get("ok")), str(data.get("reason") or "")
    except Exception:
        pass
    return None, ""


def _write_health_cache(operator_id: str, ok: bool, reason: str) -> None:
    path = _health_cache_path(operator_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "operator_id": operator_id,
        "ok": ok,
        "reason": reason,
        "checked_at": _now(),
        "checked_at_epoch": time.time(),
    }
    fd, tmp = tempfile.mkstemp(prefix=f"{operator_id}.", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(path))


def _operator_uses_codex(op: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(op.get(key) or "")
        for key in ("operator_id", "provider", "vendor", "backend", "base_url", "model", "model_config", "command", "command_path")
    ).lower()
    return "codex" in haystack or ("openai" in haystack and "gpt" in haystack)


def _command_path_available(command_path: str, op: dict[str, Any]) -> tuple[bool, str]:
    command_path = str(command_path or "").strip()
    if not command_path:
        return False, "command_path_missing:N/A"
    if command_path.startswith("/"):
        if Path(command_path).exists():
            return True, ""
    elif shutil.which(command_path) is not None:
        return True, ""

    name = Path(command_path).name
    if name == "codex" and _operator_uses_codex(op):
        resolved = shutil.which("codex")
        if resolved:
            return True, f"command_path_resolved_via_path:{resolved}"
    return False, f"command_path_missing:{command_path}"


def _operator_external_health(op: dict[str, Any]) -> tuple[bool, str]:
    """Check declared command/http health for pool members without hard failing legacy operators."""
    operator_id = str(op.get("operator_id") or "")
    health = op.get("health_check") if isinstance(op.get("health_check"), dict) else {}
    if not health:
        command_path = str(op.get("command_path") or "").strip()
        if command_path:
            return _command_path_available(command_path, op)
        return True, ""

    policy_mod = _load_concurrency_policy_module()
    try:
        recovery = policy_mod.recovery_settings() if policy_mod else {}
        cache_seconds = int(health.get("cache_seconds", recovery.get("health_cache_seconds", 60)))
    except Exception:
        cache_seconds = 60
    cached_ok, cached_reason = _read_health_cache(operator_id, cache_seconds)
    if cached_ok is not None:
        command_path = str(health.get("command_path") or op.get("command_path") or "").strip()
        if (
            not cached_ok
            and cached_reason.startswith("command_path_missing:")
            and _command_path_available(command_path, op)[0]
        ):
            cached_ok = None
        else:
            return cached_ok, cached_reason

    kind = str(health.get("type") or "").strip().lower()
    timeout = float(health.get("timeout_seconds", 0.5))
    if kind == "http":
        url = str(health.get("url") or "").strip()
        if not url:
            result = (False, "health_url_missing")
        else:
            try:
                req = Request(url, headers={"User-Agent": "solar-harness-health/1.0"})
                with urlopen(req, timeout=timeout) as resp:
                    ok = 200 <= int(resp.status) < 500
                    result = (ok, f"http_status={resp.status}")
            except URLError as exc:
                result = (False, f"http_unreachable:{exc.reason}")
            except Exception as exc:
                result = (False, f"http_unreachable:{type(exc).__name__}")
    elif kind == "command":
        command_path = str(health.get("command_path") or op.get("command_path") or "").strip()
        result = _command_path_available(command_path, op)
    else:
        result = (True, "")

    _write_health_cache(operator_id, result[0], result[1])
    return result


def _try_auto_start_operator(op: dict[str, Any]) -> tuple[bool, str]:
    auto_start = op.get("auto_start") if isinstance(op.get("auto_start"), dict) else {}
    if not bool(auto_start.get("enabled", False)):
        return False, "auto_start_not_configured"
    command = str(auto_start.get("command") or "").strip()
    if not command:
        return False, "auto_start_command_missing"
    env = os.environ.copy()
    env["HARNESS_DIR"] = str(HARNESS_DIR)
    expanded = command.replace("$HARNESS_DIR", str(HARNESS_DIR)).replace("${HARNESS_DIR}", str(HARNESS_DIR))
    try:
        proc = subprocess.Popen(
            ["bash", "-lc", expanded],
            cwd=str(HARNESS_DIR),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True, f"started_pid={proc.pid}"
    except Exception as exc:
        return False, f"auto_start_failed:{type(exc).__name__}:{exc}"


def _format_reset_eta(expires_at: str) -> str:
    """Return a human-readable reset ETA string, or empty string if not available."""
    if not expires_at:
        return ""
    try:
        exp = datetime.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = exp - now
        total_secs = int(delta.total_seconds())
        if total_secs <= 0:
            return "soon"
        hours, rem = divmod(total_secs, 3600)
        minutes = rem // 60
        if hours > 0:
            return f"~{hours}h{minutes:02d}m"
        return f"~{minutes}m"
    except Exception:
        return ""


def is_dispatchable(op: dict[str, Any]) -> tuple[bool, str]:
    if not op.get("enabled", False):
        return False, f"disabled: {op.get('disabled_reason', 'unknown')}"
    if not op.get("available", False):
        return False, f"unavailable: health={op.get('health_status', 'unknown')}"
    operator_id = op.get("operator_id", "")
    quota_state = str(op.get("quota_guard_state") or "ok").strip().lower()
    if quota_state not in {"", "ok", "ready"}:
        expires_at = str(op.get("quota_refresh_at") or (op.get("state") or {}).get("cooldown_until") or "")
        expires_dt = _parse_utc(expires_at)
        if expires_dt is not None and expires_dt <= datetime.datetime.now(datetime.timezone.utc):
            try:
                lib_dir = HARNESS_DIR / "lib"
                if str(lib_dir) not in sys.path:
                    sys.path.insert(0, str(lib_dir))
                import operator_flow_control as ofc  # type: ignore

                ofc.clear_expired_operator_config_block(str(operator_id))
            except Exception:
                pass
        else:
            reason = f"quota_guard_state={quota_state}"
            eta = _format_reset_eta(expires_at)
            if eta:
                reason += f", resets {eta}"
            if expires_at:
                reason += f" (until {expires_at})"
            return False, reason
    # The central classifier reads the on-disk registry. Unit tests and some
    # dry-run probes pass an already-selected operator dict whose registry may
    # be monkeypatched/in-memory. In that case, "disabled" only means "not
    # visible to the central registry", so defer to the operator record/status
    # provided by the selector.
    state = _runtime_state_for_operator_record(str(operator_id), op)
    state = _maybe_clear_stale_runtime(str(operator_id), state)
    if state in NON_DISPATCHABLE_STATES:
        if state in ("cooldown", "quota_exhausted", "auth_expired"):
            status = get_operator_status_data(operator_id)
            expires_at = str(status.get("expires_at") or "")
            eta = _format_reset_eta(expires_at)
            reason = f"runtime_state={state}"
            if eta:
                reason += f", resets {eta}"
            if expires_at:
                reason += f" (until {expires_at})"
            return False, reason
        return False, f"runtime_state={state}"
    health_ok, health_reason = _operator_external_health(op)
    if not health_ok:
        return False, f"health_check_failed: {health_reason}"
    return True, ""


def load_task_graph_node(sprint_id: str, node_id: str) -> dict[str, Any] | None:
    path = SPRINTS_DIR / f"{sprint_id}.task_graph.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    for node in payload.get("nodes", []) or []:
        if str(node.get("id")) == node_id:
            return dict(node)
    return None


def _capsule_submit_metadata(node: dict[str, Any] | None) -> dict[str, Any]:
    if not node:
        return {}
    if not (
        node.get("capability_native")
        or node.get("capability_capsule_id")
        or node.get("execution_capsule_id")
        or node.get("capsule_plan")
    ):
        return {}
    capsule_plan = dict(node.get("capsule_plan") or {})
    return {
        "capability_native": bool(node.get("capability_native", True)),
        "capability_capsule_id": node.get("capability_capsule_id") or capsule_plan.get("capability_capsule_id"),
        "dispatch_task_type": node.get("dispatch_task_type") or capsule_plan.get("dispatch_task_type"),
        "logical_operator": node.get("logical_operator", ""),
        "capsule_plan": capsule_plan,
    }


EVALUATOR_VERIFICATION_TASK_TYPES = {
    "graph_eval",
    "verification",
    "review",
    "evidence",
    "tests",
    "quality-gate",
    "acceptance",
}
PM_CLOSEOUT_KINDS = {
    "planner",
    "builder",
    "evaluator",
    "graph_node_execution",
    "graph_eval",
}
VERIFICATION_CAPSULE_ID = "cap.requirement-compiler-verification"
IMPLEMENTATION_CAPSULE_ID = "cap.requirement-compiler-implementation"
IMPLEMENTATION_CAPSULE_TASK_TYPE_ALIASES = {
    "test": "implementation",
    "tests": "implementation",
    "test_gen": "implementation",
    "test_generation": "implementation",
    "test_authoring": "implementation",
}
AUDIT_CAPSULE_ID = "cap.requirement-compiler-audit"
AUDIT_CAPSULE_TASK_TYPE_ALIASES = {
    "": "audit_inventory",
    "analysis": "audit_inventory",
    "audit": "audit_inventory",
    "audit_inventory": "audit_inventory",
    "inventory": "audit_inventory",
    "inspection": "audit_inventory",
    "scope": "audit_inventory",
    "scope_review": "audit_inventory",
    "documentation": "documentation",
    "docs": "documentation",
    "report": "reporting",
    "reporting": "reporting",
    "evidence": "evidence",
}


def _canonicalize_capsule_task_type(capsule_submit: dict[str, Any], task_type: str) -> str:
    capsule_id = str(capsule_submit.get("capability_capsule_id") or "").strip()
    value = str(task_type or "").strip().lower()
    if capsule_id == IMPLEMENTATION_CAPSULE_ID:
        return IMPLEMENTATION_CAPSULE_TASK_TYPE_ALIASES.get(value, value or "implementation")
    if capsule_id == AUDIT_CAPSULE_ID:
        return AUDIT_CAPSULE_TASK_TYPE_ALIASES.get(value, value or "audit_inventory")
    return value


def _apply_role_capsule_override(
    *,
    role: str,
    task_type: str,
    capsule_submit: dict[str, Any],
    logical_operator: str,
) -> tuple[dict[str, Any], str]:
    """Make evaluator dispatch evaluate with the verification capsule.

    Graph eval submits against the builder node id (B1/S1/etc.) because the evaluator must review
    that node's handoff. Without this override, pm_dispatch inherits the builder node's
    implementation capsule/logical_operator and operator_runtime correctly rejects
    task_type=graph_eval. Role is the dispatch contract here: evaluator + graph_eval is a
    verification task even when the reviewed node is an implementation node.
    """
    norm_role = normalize_role(str(role or ""))
    task = str(task_type or "").strip().lower()
    if norm_role != "evaluator" or task not in EVALUATOR_VERIFICATION_TASK_TYPES:
        return capsule_submit, logical_operator

    out = dict(capsule_submit or {})
    capsule_plan = dict(out.get("capsule_plan") or {})
    capsule_plan["capability_capsule_id"] = VERIFICATION_CAPSULE_ID
    capsule_plan["dispatch_task_type"] = task or "verification"
    out.update(
        {
            "capability_native": True,
            "capability_capsule_id": VERIFICATION_CAPSULE_ID,
            "dispatch_task_type": task or "verification",
            "logical_operator": "Verifier",
            "capsule_plan": capsule_plan,
            "capsule_override_reason": "evaluator_role_requires_verification_capsule",
        }
    )
    return out, "Verifier"


def _pm_result_path_for_role(
    sprint_id: str,
    node_id: str,
    role: str,
    task_type: str,
    expected_artifacts: list[str] | None = None,
) -> Path:
    norm_role = normalize_role(str(role or ""))
    task = str(task_type or "").strip().lower()
    if norm_role == "evaluator" and task == "graph_eval":
        if expected_artifacts:
            eval_md = Path(expected_artifacts[0])
            return SPRINTS_DIR / f"{eval_md.stem}.pm-result.md"
        return SPRINTS_DIR / f"{sprint_id}.{node_id}-eval.pm-result.md"
    return SPRINTS_DIR / f"{sprint_id}.{node_id}.pm-result.md"


def _resolve_pm_closeout_kind(role: str, task_type: str, requested: str = "") -> str:
    """Resolve the artifact contract once, when the task is submitted.

    Logical graph-node roles are not sufficient authority for closeout.  A
    Verifier node is still an ordinary graph-node execution (handoff), while
    the later independent graph evaluation writes eval sidecars.  Callers that
    know the submission phase pass an explicit kind; legacy/adhoc callers keep
    the historical role-derived behavior.
    """
    explicit = str(requested or "").strip().lower()
    if explicit:
        if explicit not in PM_CLOSEOUT_KINDS:
            raise ValueError(f"unsupported_pm_closeout_kind:{explicit}")
        return explicit
    norm_role = normalize_role(str(role or ""))
    task = str(task_type or "").strip().lower()
    if norm_role == "evaluator" and task == "graph_eval":
        return "graph_eval"
    if norm_role in {"planner", "builder", "evaluator"}:
        return norm_role
    return "builder"


# ── 算子选择 ──────────────────────────────────────────────────────────────────

def normalize_role(role: str) -> str:
    r = role.strip().lower().replace("_", "-")
    return ROLE_ALIASES.get(r, r)


def _operator_roles(op: dict[str, Any]) -> set[str]:
    raw_roles = op.get("roles")
    if isinstance(raw_roles, str):
        values = [raw_roles]
    elif isinstance(raw_roles, list):
        values = raw_roles
    else:
        values = [op.get("role", "")]
    roles = {normalize_role(str(item)) for item in values if str(item or "").strip()}
    role = str(op.get("role") or "").strip()
    if role:
        roles.add(normalize_role(role))
    return roles


def _task_type_rejected(op: dict[str, Any], task_type: str) -> bool:
    if not task_type:
        return False
    rejected_types = [str(t).lower() for t in op.get("rejected_task_types", [])]
    return any(task_type.lower() == rt or task_type.lower() in rt for rt in rejected_types)


def _operator_reject_reason_for_task(op: dict[str, Any], role: str, task_type: str) -> str:
    """Hard guard for advisory-only operators.

    Some operators can critique plans and analyze failures but cannot prove file
    edits. The registry declares that through avoid_for / builder_pool metadata;
    dispatch must enforce it even when an operator is explicitly requested.
    """
    norm_role = normalize_role(role)
    task = str(task_type or "").strip().lower()
    if task in {"research", "scientific-research"}:
        research_markers = {
            "research",
            "scientific-research",
            "web-research",
            "knowledge-extraction",
            "evidence",
            "report-writing",
        }
        declared = {
            str(item).strip().lower()
            for field in ("task_classes", "strengths", "preferred_for")
            for item in (op.get(field) or [])
            if str(item or "").strip()
        }
        if not declared.intersection(research_markers):
            return "operator_lacks_scientific_research_capability"
    requested_code_exec = norm_role in CODE_EXEC_ROLES or task in CODE_EXEC_TASK_TYPES
    if not requested_code_exec:
        return ""

    avoid_for = {str(item).strip().lower() for item in op.get("avoid_for", []) if str(item or "").strip()}
    if avoid_for & CODE_EXEC_AVOID_MARKERS:
        return "operator_avoids_code_execution"

    pool = op.get("builder_pool") if isinstance(op.get("builder_pool"), dict) else {}
    disabled_reason = str(pool.get("disabled_reason") or "")
    if bool(pool) and not bool(pool.get("enabled", False)) and "file_execution" in disabled_reason:
        return "operator_not_verified_for_code_execution"

    return ""


def _active_role_spillover_count(role: str) -> int:
    norm_role = normalize_role(role)
    active_statuses = {"submitted", "submitted_fallback", "leased", "running", "pending"}
    active_runtime_states = {"leased", "running", "draining"}
    count = 0
    d = pm_inbox_dir()
    for path in d.glob("pm-*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        status = str(payload.get("status") or "").strip().lower()
        if status not in active_statuses:
            continue
        if normalize_role(str(payload.get("borrowed_for_role") or "")) == norm_role:
            operator_id = str(payload.get("operator_id") or "").strip()
            if operator_id:
                runtime_state = get_operator_runtime_state(operator_id)
                if status in {"submitted", "submitted_fallback", "pending"} and runtime_state not in active_runtime_states:
                    continue
            count += 1
    return count


def _role_spillover_spec(policy_mod: Any | None, policy: dict[str, Any], role: str) -> dict[str, Any]:
    if policy_mod is None:
        return {}
    try:
        if not bool(policy_mod.role_spillover_enabled(role, policy)):
            return {}
        return dict(policy_mod.role_spillover_spec(role, policy))
    except Exception:
        return {}


def _operator_priority(
    *,
    op: dict[str, Any],
    op_id: str,
    norm_role: str,
    task_type: str,
    logical_operator: str,
    preferred_ops: set[str],
    default_profile: str,
    pool_mode: bool,
    policy_mod: Any | None,
    policy: dict[str, Any],
    spillover_spec: dict[str, Any] | None = None,
) -> int:
    kind = str(op.get("launch_cmd_kind", "") or op.get("backend", ""))
    if pool_mode and policy_mod:
        group = policy_mod.infer_builder_group(op)
        pool_spec = op.get("builder_pool") if isinstance(op.get("builder_pool"), dict) else {}
        try:
            op_pool_priority = int(pool_spec.get("priority", 0))
        except Exception:
            op_pool_priority = 0
        priority = 100 + policy_mod.pool_group_priority(group, policy) + op_pool_priority
        if "print_once" in kind or "print" in kind:
            priority += 6
        elif "command" in kind:
            priority += 4
        else:
            priority += 1
    else:
        if "print_once" in kind or "print" in kind:
            priority = 10
        elif "command" in kind:
            priority = 5
        else:
            priority = 1

    if task_type:
        task_classes = [str(t).lower() for t in op.get("task_classes", [])]
        if any(task_type.lower() in tc for tc in task_classes):
            priority += 3
    preferred_for = [str(item).lower() for item in op.get("preferred_for", [])]
    if logical_operator and logical_operator.lower() in preferred_for:
        priority += 2
    if norm_role in preferred_for:
        priority += 2
    if preferred_ops and op_id in preferred_ops:
        priority += 20
    if default_profile and (op_id == default_profile or str(op.get("profile", "")) == default_profile):
        priority += 8

    if DEFAULT_OPERATOR_PROVIDERS:
        provider = str(op.get("provider") or op.get("vendor") or "").strip().lower()
        if provider in DEFAULT_OPERATOR_PROVIDERS:
            priority += 50
        elif provider:
            priority -= 20

    if spillover_spec and policy_mod:
        group = policy_mod.infer_builder_group(op)
        preferred_groups = [str(g).lower() for g in spillover_spec.get("preferred_groups", [])]
        if preferred_groups:
            if group in preferred_groups:
                priority += 40 + max(0, len(preferred_groups) - preferred_groups.index(group))
            else:
                priority -= 10
    return priority


def _role_spillover_candidates(
    *,
    operators: dict[str, Any],
    norm_role: str,
    task_type: str,
    logical_operator: str,
    preferred_ops: set[str],
    forbidden_ops: set[str],
    default_profile: str,
    policy_mod: Any | None,
    policy: dict[str, Any],
    spillover_spec: dict[str, Any],
) -> tuple[list[tuple[int, str, dict[str, Any]]], str]:
    max_active = int(spillover_spec.get("max_active", 0) or 0)
    if max_active <= 0:
        return [], f"role_spillover_disabled_or_zero_capacity: {norm_role}"
    active = _active_role_spillover_count(norm_role)
    if active >= max_active:
        return [], f"role_spillover_capacity_reached: {norm_role} active={active} max={max_active}"

    allowed_source_roles = {
        normalize_role(str(r))
        for r in spillover_spec.get("allowed_source_roles", [])
        if str(r or "").strip()
    }
    if not allowed_source_roles:
        return [], f"role_spillover_no_source_roles: {norm_role}"

    allowed_groups = {str(g).lower() for g in spillover_spec.get("allowed_groups", []) if str(g or "").strip()}
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for op_id, spec in operators.items():
        op = dict(spec)
        op["operator_id"] = op_id
        if op_id in forbidden_ops:
            continue
        if bool(op.get("deprecated")):
            continue
        if not _operator_matches_provider_policy(op):
            continue
        op_roles = _operator_roles(op)
        if norm_role in op_roles:
            continue
        if not (op_roles & allowed_source_roles):
            continue
        if allowed_groups and policy_mod and policy_mod.infer_builder_group(op) not in allowed_groups:
            continue
        ok, _ = is_dispatchable(op)
        if not ok:
            continue
        if _task_type_rejected(op, task_type):
            continue
        if _operator_reject_reason_for_task(op, norm_role, task_type):
            continue
        borrowed = dict(op)
        borrowed["borrowed_for_role"] = norm_role
        borrowed["borrowed_from_roles"] = sorted(op_roles)
        borrowed["borrowed_original_role"] = str(op.get("role") or "")
        borrowed["borrowed_reason"] = str(spillover_spec.get("reason") or "")
        borrowed["role"] = norm_role
        borrowed["roles"] = sorted(op_roles | {norm_role})
        borrowed["persona"] = norm_role
        priority = _operator_priority(
            op=borrowed,
            op_id=op_id,
            norm_role=norm_role,
            task_type=task_type,
            logical_operator=logical_operator,
            preferred_ops=preferred_ops,
            default_profile=default_profile,
            pool_mode=False,
            policy_mod=policy_mod,
            policy=policy,
            spillover_spec=spillover_spec,
        )
        candidates.append((priority, op_id, borrowed))
    return candidates, ""


def select_operator_by_role(
    role: str,
    task_type: str = "",
    prefer_operator: str = "",
    resolved_capsule: dict[str, Any] | None = None,
    logical_operator: str = "",
) -> tuple[str, dict[str, Any], str]:
    """选择最合适的可调度算子。

    Returns:
        (operator_id, operator_config, fallback_reason)
    """
    registry = load_registry()
    operators = registry.get("operators", {})
    norm_role = normalize_role(role)
    policy_mod = _load_concurrency_policy_module()
    policy = policy_mod.load_policy() if policy_mod else {}
    pool_enabled = bool(policy_mod.builder_pool_enabled(policy) if policy_mod else False)
    pool_member_ids = set(policy_mod.pool_member_ids(registry) if policy_mod else [])
    pool_mode = norm_role == "builder" and pool_enabled and bool(pool_member_ids)
    capsule_constraints = dict((resolved_capsule or {}).get("operator_constraints") or {})
    preferred_ops = set(capsule_constraints.get("preferred", []) or [])
    forbidden_ops = set(capsule_constraints.get("forbidden", []) or [])
    default_profile = str(capsule_constraints.get("default_operator_profile") or "")

    # 1. 指定 operator 优先
    if prefer_operator:
        if prefer_operator in operators:
            op = dict(operators[prefer_operator])
            op["operator_id"] = prefer_operator
            if not _operator_matches_provider_policy(op):
                provider = str(op.get("provider") or op.get("vendor") or "unknown")
                return "", {}, f"preferred_operator_provider_mismatch: {prefer_operator}: {provider}"
            task_reject_reason = _operator_reject_reason_for_task(op, norm_role, task_type)
            if task_reject_reason:
                return "", {}, f"preferred_operator_rejected_for_task: {prefer_operator}: {task_reject_reason}"
            ok, reason = is_dispatchable(op)
            if ok:
                return prefer_operator, op, ""
            else:
                return "", {}, f"preferred_operator_unavailable: {prefer_operator}: {reason}"
        return "", {}, f"preferred_operator_not_found: {prefer_operator}"

    # 2. 按 role 过滤；builder 默认从显式 builder_pool 中挑可用算子。
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for op_id, spec in operators.items():
        op = dict(spec)
        op["operator_id"] = op_id
        if bool(op.get("deprecated")):
            continue
        if not _operator_matches_provider_policy(op):
            continue
        ok, _ = is_dispatchable(op)
        if not ok:
            continue
        if op_id in forbidden_ops:
            continue
        op_roles = _operator_roles(op)
        if norm_role not in op_roles:
            continue
        if pool_mode and op_id not in pool_member_ids:
            continue
        # Hard-reject: operators may declare task types they will not accept.
        # This prevents stub/print-once operators from receiving complex tasks
        # (e.g. runtime-hardening, implementation, refactor) that require a
        # long-running interactive session.
        if _task_type_rejected(op, task_type):
            continue
        if _operator_reject_reason_for_task(op, norm_role, task_type):
            continue
        # 评分：builder pool 用统一池优先级；旧模式保留 print_once > command > interactive_repl。
        priority = _operator_priority(
            op=op,
            op_id=op_id,
            norm_role=norm_role,
            task_type=task_type,
            logical_operator=logical_operator,
            preferred_ops=preferred_ops,
            default_profile=default_profile,
            pool_mode=pool_mode,
            policy_mod=policy_mod,
            policy=policy,
        )
        candidates.append((priority, op_id, op))

    if not candidates:
        # In explicit single-provider modes (Codex-only / Claude-only), role spillover is unsafe:
        # it can borrow a builder as an evaluator and make the selected runtime look successful
        # while violating the user-visible role contract. Fail closed unless explicitly opted in.
        provider_mode_spillover = str(os.environ.get("SOLAR_PM_ALLOW_ROLE_SPILLOVER_IN_PROVIDER_MODE", "")).strip().lower() in {
            "1",
            "true",
            "on",
            "yes",
        }
        if DEFAULT_OPERATOR_PROVIDERS and not provider_mode_spillover:
            if pool_mode:
                return "", {}, f"no_dispatchable_operator_for_role: {norm_role}; builder_pool_depleted"
            return "", {}, f"no_dispatchable_operator_for_role: {norm_role}; provider_mode_role_spillover_disabled"
        spillover_spec = _role_spillover_spec(policy_mod, policy, norm_role)
        if spillover_spec and not prefer_operator:
            spillover_candidates, spillover_reason = _role_spillover_candidates(
                operators=operators,
                norm_role=norm_role,
                task_type=task_type,
                logical_operator=logical_operator,
                preferred_ops=preferred_ops,
                forbidden_ops=forbidden_ops,
                default_profile=default_profile,
                policy_mod=policy_mod,
                policy=policy,
                spillover_spec=spillover_spec,
            )
            if spillover_candidates:
                spillover_candidates.sort(key=lambda x: -x[0])
                _, best_id, best_op = spillover_candidates[0]
                return best_id, best_op, ""
            if spillover_reason:
                return "", {}, f"no_dispatchable_operator_for_role: {norm_role}; {spillover_reason}"
        if pool_mode:
            return "", {}, f"no_dispatchable_operator_for_role: {norm_role}; builder_pool_depleted"
        return "", {}, f"no_dispatchable_operator_for_role: {norm_role}"

    candidates.sort(key=lambda x: -x[0])
    _, best_id, best_op = candidates[0]
    return best_id, best_op, ""


# ── Dispatch 文件构建 ──────────────────────────────────────────────────────────

def persona_text(persona: str) -> tuple[str, str]:
    path = PERSONAS_DIR / f"{persona}.md"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return str(path), text[:10000]
    except Exception:
        return str(path), "N/A"


def build_pm_dispatch_text(
    task_id: str,
    operator_id: str,
    operator: dict[str, Any],
    objective: str,
    sprint_id: str,
    node_id: str,
    result_path: str,
    context: str = "",
    expected_artifacts: list[str] | None = None,
    closeout_kind: str = "",
) -> str:
    persona_name = str(operator.get("persona") or operator.get("role") or "builder")
    persona_path, persona_body = persona_text(persona_name)
    harness = HARNESS_DIR / "solar-harness.sh"
    borrow_block = ""
    if operator.get("borrowed_for_role"):
        borrow_block = (
            f"Borrowed for role: `{operator.get('borrowed_for_role')}`\n"
            f"Borrowed from roles: `{', '.join(operator.get('borrowed_from_roles') or [])}`\n"
        )

    ctx_block = ""
    if context.strip():
        ctx_block = f"\n## PM Context\n\n{context.strip()}\n"

    artifact_lines = "\n".join(
        f"- `{path}`" for path in (expected_artifacts or [])
    ) or "- No additional role artifact is required."
    closeout_contract = str(closeout_kind or "legacy_role_contract")

    return textwrap.dedent(f"""\
        <!-- SOLAR_PM_DISPATCH -->
        # Solar PM Dispatch

        Task ID: `{task_id}`
        Sprint: `{sprint_id}`
        Node: `{node_id}`
        Operator: `{operator_id}`
        Model: `{operator.get("model", "unknown")}`
        Backend: `{operator.get("backend", "unknown")}`
        {borrow_block}\
        Issued by: `PM pane (solar-harness:0.0)`
        Issued at: `{_now()}`

        ## Definition of Done

        任务没有完成，除非同时满足：

        1. 真实调用链接入：新增/修改功能已接入真实调用链。
        2. 禁止硬编码：不得硬编码业务数据、路径、token。
        3. 执行证据齐全：列出实际命令和结果摘要。
        4. 结构化收尾：已完成 / 已验证 / 未验证 / 风险 / 后续待办。

        ## Worker Persona

        Persona file: `{persona_path}`

        ```markdown
        {persona_body}
        ```
        {ctx_block}
        ## Objective (PM Order)

        {objective}

        ## Required Closeout

        Closeout contract: `{closeout_contract}`

        Required contract artifacts (these exact paths are checked by
        `pm_dispatch complete`):

        {artifact_lines}

        把结论写到：`{result_path}`

        格式：
        ```
        # PM Task Result — {task_id}

        ## 已完成
        ## 已验证
        ## 结论摘要
        ## 风险/限制
        ## 后续建议
        ```

        完成后运行（标记任务完成）：
        ```bash
        python3 "{HARNESS_DIR}/tools/pm_dispatch.py" complete --task-id "{task_id}"
        ```
    """)


# ── Inbox / Result 管理 ───────────────────────────────────────────────────────

def pm_inbox_dir() -> Path:
    PM_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    return PM_INBOX_DIR


def write_pm_task_record(task_id: str, record: dict[str, Any]) -> Path:
    path = pm_inbox_dir() / f"{task_id}.json"
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(path))
    return path


def read_pm_task_record(task_id: str) -> dict[str, Any] | None:
    path = pm_inbox_dir() / f"{task_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_pm_tasks(limit: int = 20) -> list[dict[str, Any]]:
    tasks = []
    d = pm_inbox_dir()
    for p in sorted(d.glob("pm-*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        try:
            tasks.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return tasks


def _pm_record_files() -> list[Path]:
    return sorted(pm_inbox_dir().glob("pm-*.json"), key=lambda x: x.stat().st_mtime, reverse=True)


def _active_pm_task_ids() -> set[str]:
    active: set[str] = set()
    for directory in (HARNESS_DIR / "run" / "operator-status", HARNESS_DIR / "run" / "operator-leases"):
        for path in directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for key in ("task_id", "current_task_id", "lease_id"):
                value = str(payload.get(key) or "").strip()
                if value.startswith("pm-"):
                    active.add(value)
            lease = payload.get("lease")
            if isinstance(lease, dict):
                value = str(lease.get("task_id") or "").strip()
                if value.startswith("pm-"):
                    active.add(value)
    return active


def _pm_status_is_terminal(status: str) -> bool:
    value = str(status or "").strip().lower()
    if not value:
        return False
    return value in {"completed", "cancelled"} or value.startswith("failed")


def _load_graph_scheduler_module() -> Any | None:
    """Load graph_scheduler from the live harness, falling back to this repo."""
    for lib_dir in (HARNESS_DIR / "lib", REPO_HARNESS_DIR / "lib"):
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
    try:
        import graph_scheduler  # type: ignore

        return graph_scheduler
    except Exception:
        return None


def _planning_complete_status_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(SPRINTS_DIR.glob("*.status.json"), key=lambda item: item.stat().st_mtime):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(payload.get("status") or "").strip().lower() != "active":
            continue
        if str(payload.get("phase") or "").strip().lower() != "planning_complete":
            continue
        files.append(path)
    return files


def _sprint_id_from_status_path(path: Path) -> str:
    return path.name[: -len(".status.json")] if path.name.endswith(".status.json") else path.stem


def _active_pm_record_for_node(sprint_id: str, node_id: str) -> dict[str, Any] | None:
    newest: dict[str, Any] | None = None
    newest_mtime = -1.0
    for path in pm_inbox_dir().glob("pm-*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(payload.get("sprint_id") or "") != sprint_id:
            continue
        if str(payload.get("node_id") or "") != node_id:
            continue
        if _pm_status_is_terminal(str(payload.get("status") or "")):
            continue
        mtime = path.stat().st_mtime
        if mtime > newest_mtime:
            newest = payload
            newest_mtime = mtime
    return newest


def _node_is_builder_ready(node: dict[str, Any]) -> bool:
    logical_operator = str(node.get("logical_operator") or "").strip()
    if logical_operator.startswith("builder."):
        return True
    if logical_operator in BUILDER_READY_LOGICAL_OPERATORS:
        return True
    if logical_operator in NON_BUILDER_READY_LOGICAL_OPERATORS:
        return False
    task_type = str(node.get("dispatch_task_type") or node.get("type") or "").strip().lower()
    if task_type in CODE_EXEC_TASK_TYPES:
        return True
    if not logical_operator and not task_type:
        return True
    return False


def _node_has_pm_dispatch_marker(graph: dict[str, Any], node_id: str, node: dict[str, Any]) -> bool:
    results = graph.get("node_results") or graph.get("results") or {}
    result = results.get(node_id) if isinstance(results, dict) and isinstance(results.get(node_id), dict) else {}
    for payload in (node, result):
        if not isinstance(payload, dict):
            continue
        if str(payload.get("pm_task_id") or "").strip():
            return True
        if str(payload.get("dispatch_id") or "").strip():
            return True
        if str(payload.get("dispatched_via") or "").strip() == "pm_dispatch":
            return True
    return False


def _node_has_non_latent_status(node: dict[str, Any]) -> bool:
    status = str(node.get("status") or "").strip().lower()
    return status in {
        "assigned",
        "blocked",
        "cancelled",
        "dispatched",
        "failed",
        "in_progress",
        "queued",
        "reviewing",
        "running",
        "skipped",
        "worker_blocked",
        "passed",
    }


def _node_builder_task_type(node: dict[str, Any]) -> str:
    task_type = str(node.get("dispatch_task_type") or node.get("type") or "").strip().lower()
    if task_type:
        return task_type
    logical_operator = str(node.get("logical_operator") or "").strip()
    if logical_operator == "TestDesigner":
        return "tests"
    if logical_operator == "TestRunner":
        return "test"
    if logical_operator == "PatchWorker":
        return "patch"
    if logical_operator == "BenchmarkRunner":
        return "benchmark"
    return "implementation"


def _node_builder_objective(sprint_id: str, node: dict[str, Any]) -> str:
    node_id = str(node.get("id") or "N/A")
    goal = str(node.get("goal") or node.get("title") or node.get("objective") or "").strip()
    if not goal:
        goal = f"Execute task graph node {node_id} for {sprint_id}."
    acceptance = node.get("acceptance") if isinstance(node.get("acceptance"), list) else []
    requirements = node.get("requirement_ids") if isinstance(node.get("requirement_ids"), list) else []
    lines = [
        f"执行 sprint `{sprint_id}` 的 builder-ready task_graph 节点 `{node_id}`。",
        "",
        "目标：",
        goal,
        "",
        "必交产物：",
        f"- 必须写入 canonical handoff：`{SPRINTS_DIR / f'{sprint_id}.{node_id}-handoff.md'}`。",
        "- handoff 必须包含：已完成、已验证、未验证、风险/阻塞、后续建议。",
        "- 只写 `.pm-result.md` 不算完成；缺 handoff 会被 evaluator/graph closeout 判为未交付。",
    ]
    if requirements:
        lines.extend(["", "关联需求：", ", ".join(str(item) for item in requirements)])
    if acceptance:
        lines.append("")
        lines.append("验收条件：")
        lines.extend(f"- {item}" for item in acceptance)
    if any("harness/tests/" in str(item) for item in acceptance):
        lines.extend(
            [
                "",
                "路径提示：",
                "- 如果当前工作目录是 live harness 根目录（例如 `~/.solar/harness`），"
                "请将 repo-relative `harness/tests/...` 映射为 `tests/...` 后执行；"
                "不要因为 cwd 差异把已存在的测试误判为缺失。",
            ]
        )
    lines.extend(
        [
            "",
            "请按 task_graph 节点约束完成实现/测试/交付，并写入上述 canonical handoff 证据。",
        ]
    )
    return "\n".join(lines)


def _builder_ready_nodes_for_sprint(sprint_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    graph_path = SPRINTS_DIR / f"{sprint_id}.task_graph.json"
    if not graph_path.exists():
        return [], {"ok": False, "reason": "task_graph_missing", "graph": str(graph_path)}
    graph_scheduler = _load_graph_scheduler_module()
    if graph_scheduler is None:
        return [], {"ok": False, "reason": "graph_scheduler_unavailable", "graph": str(graph_path)}
    try:
        graph_scheduler.SPRINTS_DIR = SPRINTS_DIR
        graph = graph_scheduler.load_graph(graph_path)
        try:
            import plan_validator  # type: ignore

            plan_guard = plan_validator.check_planner_graph_dispatchable(
                graph, sprints_dir=SPRINTS_DIR, sid=sprint_id
            )
        except Exception as guard_exc:
            if str(os.environ.get("SOLAR_PLAN_VALIDATOR") or "").strip().lower() not in {"0", "false", "no", "off"}:
                detail = " ".join(str(guard_exc).split())[:300]
                return [], {
                    "ok": False,
                    "reason": "plan_validator_dispatch_refused",
                    "errors": [
                        f"PLAN_VALIDATOR_UNCHECKABLE:{type(guard_exc).__name__}"
                        + (f":{detail}" if detail else "")
                    ],
                    "graph": str(graph_path),
                }
            plan_guard = {"ok": True}
        if not plan_guard.get("ok"):
            return [], {
                "ok": False,
                "reason": "plan_validator_dispatch_refused",
                "errors": plan_guard.get("errors") or [],
                "graph": str(graph_path),
            }
        ready = graph_scheduler.ready_nodes(graph)
    except Exception as exc:
        return [], {"ok": False, "reason": f"ready_nodes_failed:{type(exc).__name__}", "error": str(exc), "graph": str(graph_path)}
    nodes: list[dict[str, Any]] = []
    for node in ready:
        node_id = str(node.get("id") or "").strip()
        if not node_id or not _node_is_builder_ready(node):
            continue
        if _node_has_non_latent_status(node):
            continue
        if _node_has_pm_dispatch_marker(graph, node_id, node):
            continue
        if _active_pm_record_for_node(sprint_id, node_id):
            continue
        nodes.append(dict(node))
    return nodes, {"ok": True, "graph": str(graph_path), "ready_count": len(nodes)}


def _latent_builder_ready_items(limit: int = 0) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for status_path in _planning_complete_status_files():
        sprint_id = _sprint_id_from_status_path(status_path)
        nodes, meta = _builder_ready_nodes_for_sprint(sprint_id)
        if not meta.get("ok"):
            continue
        for node in nodes:
            items.append(
                {
                    "sprint_id": sprint_id,
                    "node_id": str(node.get("id") or ""),
                    "task_type": _node_builder_task_type(node),
                    "logical_operator": str(node.get("logical_operator") or ""),
                    "graph": str(meta.get("graph") or ""),
                    "objective": _node_builder_objective(sprint_id, node),
                }
            )
            if limit and len(items) >= limit:
                return items
    return items


def _latent_builder_ready_backlog_count() -> int:
    return len(_latent_builder_ready_items())


def _pm_expected_artifacts(record: dict[str, Any]) -> list[Path]:
    """Artifacts that prove the persisted submission contract was satisfied.

    New records carry an explicit closeout kind.  Old records deliberately
    retain the historical role-derived behavior so an upgrade does not change
    the meaning of already-running tasks.
    """
    role = normalize_role(str(record.get("requested_role") or ""))
    sprint_id = str(record.get("sprint_id") or "").strip()
    node_id = str(record.get("node_id") or "").strip()
    if not sprint_id:
        return []
    requested_kind = str(record.get("closeout_kind") or "").strip()
    if requested_kind:
        kind = _resolve_pm_closeout_kind(
            role,
            str(record.get("task_type") or ""),
            requested_kind,
        )
    else:
        # Backward compatibility is intentional: role was the only authority
        # in records written before the explicit closeout contract existed.
        kind = role
    if kind == "graph_node_execution" and node_id:
        canonical = [SPRINTS_DIR / f"{sprint_id}.{node_id}-handoff.md"]
    elif kind == "planner":
        canonical = [
            SPRINTS_DIR / f"{sprint_id}.plan.md",
            SPRINTS_DIR / f"{sprint_id}.task_graph.json",
        ]
    elif kind == "builder" and node_id:
        canonical = [SPRINTS_DIR / f"{sprint_id}.{node_id}-handoff.md"]
    elif kind in {"evaluator", "graph_eval"} and node_id:
        canonical = [
            SPRINTS_DIR / f"{sprint_id}.{node_id}-eval.md",
            SPRINTS_DIR / f"{sprint_id}.{node_id}-eval.json",
        ]
    else:
        canonical = []

    declared = record.get("expected_artifacts")
    if declared is None:
        return canonical
    if not isinstance(declared, list) or not all(isinstance(item, str) for item in declared):
        raise ValueError("expected_artifacts_must_be_string_list")
    explicit = [Path(item) for item in declared]
    if kind != "graph_eval":
        if explicit != canonical:
            raise ValueError("expected_artifacts_do_not_match_closeout_kind")
        return explicit

    # Quorum evaluation assigns q2/q3/... sidecars to secondary evaluators.
    # Allow only one exact md/json pair for this sprint+node, directly under
    # SPRINTS_DIR.  The CLI cannot turn expected artifacts into arbitrary path
    # write authority.
    if len(explicit) != 2:
        raise ValueError("graph_eval_requires_exact_md_json_pair")
    root = SPRINTS_DIR
    for path in explicit:
        if not path.is_absolute() or path.parent != root:
            raise ValueError("expected_artifact_outside_sprints_root")
    prefix = re.escape(f"{sprint_id}.{node_id}-eval")
    match_md = re.fullmatch(rf"{prefix}(?:-q([2-9][0-9]*))?\.md", explicit[0].name)
    match_json = re.fullmatch(rf"{prefix}(?:-q([2-9][0-9]*))?\.json", explicit[1].name)
    if not match_md or not match_json or match_md.group(1) != match_json.group(1):
        raise ValueError("graph_eval_artifact_pair_not_canonical")
    return explicit


def _pm_recover_missing_artifact(expected: Path, sprint_id: str) -> dict[str, str] | None:
    """Deterministic closeout recovery for the nested-write failure class.

    Workers are given the flat sprints path, but a path transcription slip can
    land the artifact — exact expected basename, non-empty — inside the
    sprint's own directory tree instead (P2 smoke-5: the S2 builder wrote
    sprints/<sid>/<basename> and then failed contract closeout with the file
    sitting right there). If EXACTLY ONE such candidate exists under
    SPRINTS_DIR/<sid>/, copy it to the canonical path and report the recovery;
    zero or multiple matches keep the failure, and files outside the sprint
    tree are never adopted. Only ever fires where the closeout would otherwise
    FAIL. Kill-switch: SOLAR_PM_CLOSEOUT_RECOVERY=0."""
    flag = str(os.environ.get("SOLAR_PM_CLOSEOUT_RECOVERY", "1")).strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return None
    sprint_tree = SPRINTS_DIR / sprint_id
    if not sprint_id or not sprint_tree.is_dir():
        return None
    try:
        matches = [
            path for path in sprint_tree.rglob(expected.name)
            if path.is_file() and path.stat().st_size > 0
        ]
    except Exception:
        return None
    if len(matches) != 1:
        return None
    try:
        shutil.copy2(matches[0], expected)
    except Exception:
        return None
    return {"artifact": str(expected), "recovered_from": str(matches[0])}


def _pm_repair_archived_artifact(expected: Path, record: dict[str, Any]) -> dict[str, str] | None:
    """G4 UI-rung run 3 trigger (also G3 run 12's failed_contract_closeout):
    the worker DID deliver the artifact — the gate consumed it and the repair
    flow ARCHIVED it to <stem>.repair*.<ts><suffix> seconds before this
    closeout check ran — and the closeout jailed the only builder for 900s
    (completed_without_required_artifacts), starving the pool. A non-empty
    repair-archived copy, no older than this task's submission, IS proof of
    delivery. It is acknowledged, never copied back: the repair flow archived
    it deliberately, and resurrecting the canonical file would confuse the
    repair-generation machinery. Shares the SOLAR_PM_CLOSEOUT_RECOVERY kill
    switch with the nested-write net above."""
    flag = str(os.environ.get("SOLAR_PM_CLOSEOUT_RECOVERY", "1")).strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return None
    try:
        candidates = sorted(expected.parent.glob(f"{expected.stem}.repair*{expected.suffix}"))
    except Exception:
        return None
    submitted = _parse_utc(str(record.get("submitted_at") or ""))
    for candidate in reversed(candidates):
        try:
            if not candidate.is_file() or candidate.stat().st_size <= 0:
                continue
            if submitted is not None:
                mtime = datetime.datetime.fromtimestamp(
                    candidate.stat().st_mtime, tz=datetime.timezone.utc
                )
                if mtime < submitted:
                    continue
            return {"artifact": str(expected), "archived_by_repair": str(candidate)}
        except Exception:
            continue
    return None


def _pm_closeout_status(record: dict[str, Any]) -> dict[str, Any]:
    try:
        expected = _pm_expected_artifacts(record)
    except ValueError as exc:
        return {
            "ok": False,
            "expected_artifacts": [],
            "missing_artifacts": [],
            "contract_error": str(exc),
        }
    persisted_expected = record.get("expected_artifacts")
    if persisted_expected is not None:
        observed = [str(path) for path in persisted_expected] if isinstance(persisted_expected, list) else []
        canonical = [str(path) for path in expected]
        if observed != canonical:
            return {
                "ok": False,
                "expected_artifacts": canonical,
                "missing_artifacts": [],
                "contract_error": "persisted_expected_artifacts_mismatch",
                "persisted_expected_artifacts": observed,
            }
    sprint_id = str(record.get("sprint_id") or "").strip()
    missing: list[str] = []
    recovered: list[dict[str, str]] = []
    for path in expected:
        if path.exists() and path.stat().st_size > 0:
            continue
        recovery = _pm_recover_missing_artifact(path, sprint_id)
        if recovery:
            recovered.append(recovery)
            continue
        archived = _pm_repair_archived_artifact(path, record)
        if archived:
            recovered.append(archived)
            continue
        missing.append(str(path))
    closeout: dict[str, Any] = {
        "ok": not missing,
        "expected_artifacts": [str(path) for path in expected],
        "missing_artifacts": missing,
    }
    if recovered:
        closeout["recovered_artifacts"] = recovered
    return closeout


def _record_age_minutes(record: dict[str, Any], path: Path) -> float:
    for key in ("submitted_at", "created_at", "updated_at", "ts"):
        parsed = _parse_utc(str(record.get(key) or ""))
        if parsed:
            return max(0.0, (datetime.datetime.now(datetime.timezone.utc) - parsed).total_seconds() / 60.0)
    return max(0.0, (time.time() - path.stat().st_mtime) / 60.0)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(path))


def _append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _new_sprint_id() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("sprint-%Y%m%d-%H%M%S")


def ensure_compiled_sprint_status(
    sprint_id: str,
    title: str,
    summary: str,
    *,
    status_value: str = "drafting",
    phase: str = "prd_ready",
    handoff_to: str = "planner",
    target_role: str = "planner",
) -> Path:
    status_path = SPRINTS_DIR / f"{sprint_id}.status.json"
    now = _now()
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            status = {}
    else:
        status = {
            "id": sprint_id,
            "title": title,
            "summary": summary,
            "created_at": now,
            "round": 0,
            "history": [],
        }

    status.update(
        {
            "id": sprint_id,
            "title": title,
            "summary": summary,
            "status": status_value,
            "phase": phase,
            "handoff_to": handoff_to,
            "target_role": target_role,
            "updated_at": now,
        }
    )
    if target_role == "planner":
        # Runtime-owned birth provenance: a planner may replace the graph,
        # but it cannot thereby turn a governed intake into legacy work.
        status["plan_compile_required"] = True
    else:
        status.pop("plan_compile_required", None)
        status.pop("planner_dispatch_claim", None)
    if _pm_operator_pool_enabled() and target_role == "planner":
        # This is written in the same atomic status replace as ``prd_ready``;
        # there is no coordinator-visible state in which owner is ambiguous.
        status["planner_dispatch_claim"] = _new_planner_dispatch_claim(now)
    history = list(status.get("history") or [])
    history.append({"ts": now, "event": "compiled_requirement_package_created", "by": "codex-pm-router"})
    status["history"] = history[-20:]
    _write_json_atomic(status_path, status)
    _append_event(
        SPRINTS_DIR / f"{sprint_id}.events.jsonl",
        {
            "ts": now,
            "actor": "pm_dispatch",
            "event": "compiled_requirement_package_created",
            "sid": sprint_id,
            "status": "info",
            "detail": {
                "phase": phase,
                "handoff_to": handoff_to,
                "target_role": target_role,
            },
        },
    )
    return status_path


def _planner_objective_for_compiled_sprint(sprint_id: str) -> str:
    base = str(SPRINTS_DIR / sprint_id)
    objective = textwrap.dedent(
        f"""\
        请接手 {sprint_id}：Requirement Compiler 已生成首版需求编译包。

        先读取：
        - {base}.product-brief.md
        - {base}.prd.md
        - {base}.contract.md
        - {base}.task_graph.json
        - {base}.requirement_ir.json
        - {base}.handoff.md

        你的任务：
        1. 基于 compiled requirement package 产出 design.md 和 plan.md。
        2. 如有必要，细化或修正 task_graph.json，但不得绕过 compiled contracts。
        3. 不要直接跳 Builder；保持 PM -> Planner -> task_graph -> Builder 主链。
        4. 如果 compiled package 缺失关键字段，先写明 blocker 和修正建议。
        """
    ).strip()
    # P5 G2: teach the planner the compile rules it will be checked against
    # (env-gated inside the helper; "" when SOLAR_PLAN_VALIDATOR is off, so
    # legacy prompts stay byte-identical). Prompt enrichment must never break
    # dispatch — enforcement lives at the compile/dispatch seams.
    try:
        import plan_validator  # type: ignore

        policy_block = plan_validator.planner_compile_policy_block(SPRINTS_DIR, sprint_id)
    except Exception:
        policy_block = ""
    if policy_block:
        objective = f"{objective}\n\n{policy_block}"
    return objective


def cmd_compile_request(args: argparse.Namespace) -> int:
    request_text = str(args.text or "").strip()
    if not request_text and args.input_file:
        request_text = Path(args.input_file).read_text(encoding="utf-8")
    if not request_text:
        request_text = sys.stdin.read().strip()
    if not request_text:
        print("ERROR: request text is required via --text, --input-file, or stdin", file=sys.stderr)
        return 1

    sprint_id = str(args.sprint or "")
    if os.environ.get("SOLAR_PM_DISPATCH_ALLOW_DIRECT") != "1":
        try:
            payload = capture_entrypoint_raw_intent(
                source_channel="pm_compile_request",
                text=request_text,
                sprint_id=sprint_id,
                role="pm",
                repo=str(Path(args.workspace_root or os.getcwd())),
            )
        except Exception as exc:
            print(f"ERROR: RawIntent capture failed: {exc}", file=sys.stderr)
            return 1
        print_intent_capture(payload, "pm_dispatch.compile-request")
        return 0

    sprint_id = str(args.sprint or _new_sprint_id())
    workspace_root = Path(args.workspace_root or os.getcwd())

    router_path = Path(__file__).resolve().parent / "codex_pm_router.py"
    spec = importlib.util.spec_from_file_location("codex_pm_router", router_path)
    if spec is None or spec.loader is None:
        print(f"ERROR: unable to load {router_path}", file=sys.stderr)
        return 1
    router = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(router)

    payload = router.build_pm_intake(
        request_text,
        papers=list(getattr(args, "paper", []) or []),
        logs=list(getattr(args, "log", []) or []),
        repo_context=list(getattr(args, "repo_context", []) or []),
        sprint_id=sprint_id,
        target_system=str(getattr(args, "target_system", "solar-harness") or "solar-harness"),
    )
    validation = router.validate_compiled_package(payload)
    if not validation.get("ok", False):
        print("ERROR: compiled requirement package failed validation", file=sys.stderr)
        for item in validation.get("errors", []) or []:
            print(f" - {item}", file=sys.stderr)
        return 2
    emitted = router.emit_requirement_package(
        payload,
        workspace_root=workspace_root,
        sprint_root=SPRINTS_DIR,
        sprint_id=sprint_id,
    )
    status_path = ensure_compiled_sprint_status(
        sprint_id,
        title=payload["compiled_artifacts"]["product_brief"]["title"],
        summary=payload["compiled_artifacts"]["product_brief"]["problem"][:180],
        status_value="drafting",
        phase="prd_ready",
        handoff_to="planner",
        target_role="planner",
    )
    emitted["status"] = str(status_path)

    if bool(getattr(args, "dispatch_planner", False)):
        submit_args = argparse.Namespace(
            role="planner",
            objective=_planner_objective_for_compiled_sprint(sprint_id),
            operator="",
            sprint=sprint_id,
            node="N0",
            task_type="planning",
            context=f"compiled_requirement_ir={emitted['requirement_ir']}",
            dry_run=bool(getattr(args, "dry_run", False)),
        )
        rc = cmd_submit(submit_args)
        if rc != 0:
            return rc

    print("OK: Requirement Compiler package ready")
    print(f"   sprint_id   = {sprint_id}")
    print(f"   workspace   = {workspace_root}")
    print(f"   pm_dir      = {emitted['pm_dir']}")
    print(f"   requirement = {emitted['requirement_ir']}")
    print(f"   product_brief = {emitted['sprint_product_brief']}")
    print(f"   prd         = {emitted['sprint_prd']}")
    print(f"   contract    = {emitted['sprint_contract']}")
    print(f"   task_graph  = {emitted['sprint_task_graph']}")
    print(f"   status      = {emitted['status']}")
    return 0


# ── 核心 submit 逻辑 ──────────────────────────────────────────────────────────

def _with_planner_compile_policy(objective: str, sprint_id: str) -> str:
    """P5 G2b: the submit choke point every role-pool planner dispatch flows
    through. The G2b battery proved objective-builder-level injection misses
    live paths (the autopilot role-handoff objective reached the planner with
    no policy block); enriching HERE covers every caller. Env-gated inside
    the helper ("" when SOLAR_PLAN_VALIDATOR is off); idempotent so an
    already-enriched objective (intent_consumer) is not double-appended."""
    if "## Plan compile policy" in objective:
        return objective
    try:
        import plan_validator  # type: ignore

        policy_block = plan_validator.planner_compile_policy_block(SPRINTS_DIR, sprint_id)
    except Exception:
        policy_block = ""
    if policy_block:
        return f"{objective}\n\n{policy_block}"
    return objective


def cmd_submit(args: argparse.Namespace) -> int:
    role = str(args.role or "builder")
    objective = str(args.objective or "").strip()
    if not objective:
        print("ERROR: --objective is required", file=sys.stderr)
        return 1

    prefer_operator = str(args.operator or "").strip()
    requested_sprint_id = str(args.sprint or "")
    node_id_for_intent = str(args.node or "N1")
    if os.environ.get("SOLAR_PM_DISPATCH_ALLOW_DIRECT") != "1":
        try:
            payload = capture_entrypoint_raw_intent(
                source_channel="pm_dispatch",
                text=objective + (f"\n\n[context]\n{args.context}" if str(args.context or "").strip() else ""),
                sprint_id=requested_sprint_id,
                node_id=node_id_for_intent,
                role=role,
                repo=str(HARNESS_DIR),
            )
        except Exception as exc:
            print(f"ERROR: RawIntent capture failed: {exc}", file=sys.stderr)
            return 1
        print_intent_capture(payload, "pm_dispatch.submit")
        return 0

    sprint_id = str(args.sprint or f"pm-adhoc-{_short_id()}")
    node_id = str(args.node or "N1")
    task_type = str(args.task_type or "")
    dry_run: bool = bool(args.dry_run)
    context = str(args.context or "")
    if normalize_role(role) == "planner":
        objective = _with_planner_compile_policy(objective, sprint_id)
    task_graph_node = load_task_graph_node(sprint_id, node_id)
    capsule_submit = _capsule_submit_metadata(task_graph_node)
    logical_operator = str(capsule_submit.get("logical_operator") or (task_graph_node or {}).get("logical_operator") or "")
    if not task_type:
        task_type = str(capsule_submit.get("dispatch_task_type") or (task_graph_node or {}).get("type") or "")
    capsule_submit, logical_operator = _apply_role_capsule_override(
        role=role,
        task_type=task_type,
        capsule_submit=capsule_submit,
        logical_operator=logical_operator,
    )
    task_type = _canonicalize_capsule_task_type(capsule_submit, task_type)
    if capsule_submit.get("capability_capsule_id"):
        capsule_submit["dispatch_task_type"] = task_type
        if isinstance(capsule_submit.get("capsule_plan"), dict):
            capsule_submit["capsule_plan"]["dispatch_task_type"] = task_type

    resolved_capsule: dict[str, Any] | None = None
    if capsule_submit.get("capability_capsule_id"):
        try:
            lib_dir = HARNESS_DIR / "lib"
            if str(lib_dir) not in sys.path:
                sys.path.insert(0, str(lib_dir))
            from capability_capsules import resolve_capability_capsule_for_task  # type: ignore

            resolved_capsule = resolve_capability_capsule_for_task(
                {
                    "task_type": task_type,
                    "objective": objective[:300],
                    "capability_capsule_id": capsule_submit["capability_capsule_id"],
                }
            )
        except Exception:
            resolved_capsule = None

    try:
        closeout_kind = _resolve_pm_closeout_kind(
            role,
            task_type,
            str(getattr(args, "closeout_kind", "") or ""),
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    contract_record = {
        "requested_role": normalize_role(role),
        "task_type": task_type,
        "closeout_kind": closeout_kind,
        "sprint_id": sprint_id,
        "node_id": node_id,
    }
    requested_artifacts = list(getattr(args, "expected_artifact", []) or [])
    if requested_artifacts:
        contract_record["expected_artifacts"] = requested_artifacts
    try:
        expected_artifacts = [str(path) for path in _pm_expected_artifacts(contract_record)]
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    task_id = f"pm-{sprint_id}-{node_id}-{_short_id()}"
    result_path = str(
        _pm_result_path_for_role(
            sprint_id,
            node_id,
            role,
            task_type,
            expected_artifacts=expected_artifacts,
        )
    )
    work_dir = _pm_work_dir_for_sprint(sprint_id, str(getattr(args, "work_dir", "") or ""))

    # 1. 选算子
    operator_id, operator, fallback_reason = select_operator_by_role(
        role=role,
        task_type=task_type,
        prefer_operator=prefer_operator,
        resolved_capsule=resolved_capsule,
        logical_operator=logical_operator,
    )
    if not operator_id:
        failure_record: dict[str, Any] = {
            "task_id": task_id,
            "sprint_id": sprint_id,
            "node_id": node_id,
            "operator_id": "",
            "objective": objective,
            "result_path": result_path,
            "status": "failed_no_dispatchable_operator",
            "submitted_at": _now(),
            "failed_at": _now(),
            "requested_role": normalize_role(role),
            "task_type": task_type,
            "closeout_kind": closeout_kind,
            "expected_artifacts": expected_artifacts,
            "failure_reason": fallback_reason or "no_dispatchable_operator_for_role",
        }
        if capsule_submit.get("capability_capsule_id"):
            failure_record["capability_capsule_id"] = capsule_submit["capability_capsule_id"]
            failure_record["logical_operator"] = logical_operator
        write_pm_task_record(task_id, failure_record)
        msg = f"ERROR: 没有可用算子 ({fallback_reason})"
        # Surface cooldown ETA when the fallback reason mentions cooldown/quota
        if any(kw in fallback_reason for kw in ("cooldown", "quota_exhausted", "auth_expired")):
            # Try to find the preferred/blocked operator for ETA details
            _blocked_op = prefer_operator or ""
            if _blocked_op:
                _status = get_operator_status_data(_blocked_op)
                _expires = str(_status.get("expires_at") or "")
                _eta = _format_reset_eta(_expires)
                if _eta:
                    msg += f"\n  ⏳ 冷却中，重置时间: {_eta}"
                if _expires:
                    msg += f" (until {_expires})"
        print(msg, file=sys.stderr)
        return 1

    # 3. 构建 dispatch 文件
    dispatch_text = build_pm_dispatch_text(
        task_id=task_id,
        operator_id=operator_id,
        operator=operator,
        objective=objective,
        sprint_id=sprint_id,
        node_id=node_id,
        result_path=result_path,
        context=context,
        expected_artifacts=expected_artifacts,
        closeout_kind=closeout_kind,
    )

    dispatch_dir = HARNESS_DIR / "run" / "pm-dispatch-files"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    dispatch_file = dispatch_dir / f"{task_id}.md"

    if dry_run:
        print(f"[DRY-RUN] operator_id = {operator_id}")
        if operator.get("borrowed_for_role"):
            print(
                "[DRY-RUN] role_spillover = "
                f"{operator.get('borrowed_for_role')} from {','.join(operator.get('borrowed_from_roles') or [])}"
            )
        print(f"[DRY-RUN] task_id     = {task_id}")
        print(f"[DRY-RUN] result_path = {result_path}")
        print(f"[DRY-RUN] dispatch_file = {dispatch_file}")
        print("\n--- dispatch preview ---")
        print(dispatch_text[:1500])
        return 0

    # 4. 写 dispatch 文件
    dispatch_file.write_text(dispatch_text, encoding="utf-8")

    # 5. 构建 task envelope → operator_runtime.submit
    envelope = _build_pm_operator_envelope(
        task_id=task_id,
        sprint_id=sprint_id,
        node_id=node_id,
        operator_id=operator_id,
        operator=operator,
        task_type=task_type,
        objective=objective,
        dispatch_file=dispatch_file,
        result_path=result_path,
        context=context,
        role=role,
        work_dir=work_dir,
        logical_operator=logical_operator,
        task_graph_node=task_graph_node,
        capsule_submit=capsule_submit,
        expected_artifacts=expected_artifacts,
    )

    record: dict[str, Any] = {
        "task_id": task_id,
        "sprint_id": sprint_id,
        "node_id": node_id,
        "operator_id": operator_id,
        "objective": objective,
        "dispatch_file": str(dispatch_file),
        "dispatch_path": str(dispatch_file),
        "result_path": result_path,
        "work_dir": work_dir,
        "status": "submitted",
        "submitted_at": _now(),
        "requested_role": normalize_role(role),
        "task_type": task_type,
        "closeout_kind": closeout_kind,
        "expected_artifacts": expected_artifacts,
        "runtime_mode": envelope.get("runtime_mode", ""),
        "provider_policy": envelope.get("provider_policy", ""),
    }
    if operator.get("borrowed_for_role"):
        record["borrowed_for_role"] = operator.get("borrowed_for_role")
        record["borrowed_from_roles"] = operator.get("borrowed_from_roles", [])
        record["borrowed_original_role"] = operator.get("borrowed_original_role", "")
        record["borrowed_reason"] = operator.get("borrowed_reason", "")
    if capsule_submit.get("capability_capsule_id"):
        record["capability_capsule_id"] = capsule_submit["capability_capsule_id"]
        record["logical_operator"] = logical_operator
    if capsule_submit.get("capsule_override_reason"):
        record["capsule_override_reason"] = str(capsule_submit["capsule_override_reason"])

    # 尝试通过 operator_runtime.submit 投递
    try:
        lib_dir = HARNESS_DIR / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        tools_dir = HARNESS_DIR / "tools"
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))

        from operator_runtime import submit  # type: ignore
    except Exception as exc:
        # fallback: 直接写 operator inbox（无 lease，operatord 会拾取）
        inbox_dir = OPERATOR_INBOX_DIR / operator_id
        inbox_dir.mkdir(parents=True, exist_ok=True)
        inbox_path = inbox_dir / f"{task_id}.json"
        tmp = str(inbox_path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2, ensure_ascii=False)
        os.replace(tmp, str(inbox_path))
        record["status"] = "submitted_fallback"
        record["inbox_path"] = str(inbox_path)
        record["submit_error"] = str(exc)
        submit_mode = "direct_inbox"
    else:
        try:
            result = submit(envelope)
        except Exception as exc:
            record["status"] = "failed_submit_exception"
            record["failed_at"] = _now()
            record["failure_reason"] = f"operator_runtime.submit failed: {exc}"
            record["submit_error"] = str(exc)
            write_pm_task_record(task_id, record)
            print(f"ERROR: operator_runtime.submit failed: {exc}", file=sys.stderr)
            return 1
        record["status"] = "submitted"
        record["lease_id"] = result.get("lease_id", "")
        record["inbox_path"] = result.get("inbox_path", "")
        if result.get("daemon_pid"):
            record["daemon_pid"] = result.get("daemon_pid")
        submit_mode = "operator_runtime.submit"

    # 6. 写 PM inbox 记录
    write_pm_task_record(task_id, record)

    # 7. 输出
    print("OK: PM task submitted")
    print(f"   task_id     = {task_id}")
    print(f"   operator    = {operator_id} ({operator.get('model', '?')})")
    if operator.get("borrowed_for_role"):
        print(
            "   spillover   = "
            f"{operator.get('borrowed_for_role')} <- {','.join(operator.get('borrowed_from_roles') or [])}"
        )
    print(f"   submit_mode = {submit_mode}")
    print(f"   dispatch    = {dispatch_file}")
    print(f"   result      = {result_path}")
    print()
    print("Inspect: solar-harness pm-fleet inbox")
    print(f"Wait for completion: watch cat '{result_path}'")

    return 0


def cmd_fleet_status(args: argparse.Namespace) -> int:
    registry = load_registry()
    operators = registry.get("operators", {})
    policy_mod = _load_concurrency_policy_module()
    if policy_mod is not None:
        policy = policy_mod.load_policy()
        level = policy_mod.active_level(policy)
        settings = policy_mod.level_settings(policy, level)
        print(
            "concurrency_knob="
            f"{level} graph_max_parallel={settings.get('graph_max_parallel', 'N/A')} "
            f"builder_dispatch_limit={settings.get('builder_dispatch_limit', 'N/A')}"
        )
    print(f"{'算子 ID':<40} {'角色':<12} {'模型':<20} {'运行时状态':<18} {'冷却/重置 ETA'}")
    print("-" * 110)
    for op_id, spec in operators.items():
        op = dict(spec)
        enabled = op.get("enabled", False)
        if not enabled:
            rt_state = "disabled"
            cooldown_col = ""
        else:
            op["operator_id"] = op_id
            rt_state = _runtime_state_for_operator_record(op_id, op)
            cooldown_col = ""
            if rt_state in ("cooldown", "quota_exhausted", "auth_expired"):
                status = get_operator_status_data(op_id)
                expires_at = str(status.get("expires_at") or "")
                eta = _format_reset_eta(expires_at)
                cooldown_col = f"{rt_state}"
                if eta:
                    cooldown_col += f" resets {eta}"
                if expires_at:
                    cooldown_col += f" [{expires_at}]"
        role = str(op.get("role", "?"))
        model = str(op.get("model", "?"))
        ok_sym = "✅" if enabled else "❌"
        print(f"{ok_sym} {op_id:<38} {role:<12} {model:<20} {rt_state:<18} {cooldown_col}")
    return 0


def _pending_pm_backlog_count() -> int:
    d = pm_inbox_dir()
    count = 0
    for path in d.glob("pm-*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        status = str(payload.get("status") or "").strip().lower()
        if not _pm_status_is_terminal(status):
            count += 1
    return count


def _builder_pool_backlog_breakdown() -> dict[str, int]:
    pending_pm = _pending_pm_backlog_count()
    latent_builder_ready = _latent_builder_ready_backlog_count()
    return {
        "pending_pm": pending_pm,
        "latent_builder_ready": latent_builder_ready,
        "total": pending_pm + latent_builder_ready,
    }


def builder_pool_snapshot(recover: bool = False) -> dict[str, Any]:
    registry = load_registry()
    operators = registry.get("operators", {})
    policy_mod = _load_concurrency_policy_module()
    if policy_mod is None:
        return {"ok": False, "reason": "concurrency_policy_unavailable"}
    policy = policy_mod.load_policy()
    pool = policy_mod.builder_pool_config(policy)
    groups_cfg = pool.get("groups") if isinstance(pool.get("groups"), dict) else {}
    groups: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    recovery_actions: list[dict[str, Any]] = []
    total_policy_available = 0
    for group, spec in groups_cfg.items():
        groups[group] = {
            "desired": int(policy_mod.pool_group_desired(group, policy) or (spec or {}).get("desired", 0)),
            "configured": 0,
            "available": 0,
            "blocked": 0,
            "cooldown": 0,
            "quota_exhausted": 0,
            "auth_expired": 0,
            "health": 0,
            "busy": 0,
            "disabled": 0,
            "other_blocked": 0,
        }

    rate_limit_blocks: list[dict[str, Any]] = []
    for op_id, spec in operators.items():
        op = {"operator_id": op_id, **dict(spec)}
        if not policy_mod.is_pool_member(op):
            continue
        provider_policy_eligible = _operator_matches_provider_policy(op)
        group = policy_mod.infer_builder_group(op) or "unknown"
        groups.setdefault(
            group,
            {
                "desired": policy_mod.pool_group_desired(group, policy),
                "configured": 0,
                "available": 0,
                "blocked": 0,
                "cooldown": 0,
                "quota_exhausted": 0,
                "auth_expired": 0,
                "health": 0,
                "busy": 0,
                "disabled": 0,
                "other_blocked": 0,
            },
        )
        groups[group]["configured"] += 1
        ok, reason = is_dispatchable(op)
        if recover and not ok and "health_check_failed" in reason:
            started, start_reason = _try_auto_start_operator(op)
            recovery_actions.append({"operator_id": op_id, "action": "auto_start", "ok": started, "reason": start_reason})
        state = get_operator_runtime_state(op_id) if op.get("enabled", False) else "disabled"
        block_info = _operator_block_info(op_id, op, state, reason)
        block_type = str(block_info.get("block_type") or "none")
        if ok:
            groups[group]["available"] += 1
            if provider_policy_eligible:
                total_policy_available += 1
        else:
            groups[group]["blocked"] += 1
            if block_type in {"cooldown", "quota_exhausted", "auth_expired", "health", "busy", "disabled"}:
                groups[group][block_type] += 1
            else:
                groups[group]["other_blocked"] += 1
        if block_type in {"cooldown", "quota_exhausted", "auth_expired"}:
            rate_limit_blocks.append(
                {
                    "operator_id": op_id,
                    "group": group,
                    "model": spec.get("model", "N/A"),
                    "block_type": block_type,
                    "quota_guard_state": block_info.get("quota_guard_state", "ok"),
                    "cooldown_until": block_info.get("cooldown_until", ""),
                    "cooldown_eta": block_info.get("cooldown_eta", ""),
                    "reason": reason or state,
                }
            )
        rows.append(
            {
                "operator_id": op_id,
                "group": group,
                "model": spec.get("model", "N/A"),
                "enabled": bool(spec.get("enabled", False)),
                "runtime_state": state,
                "available": ok,
                "provider_policy_eligible": provider_policy_eligible,
                "reason": reason or "ok",
                **block_info,
            }
        )

    backlog_breakdown = _builder_pool_backlog_breakdown()
    backlog = int(backlog_breakdown.get("total", 0))
    total_desired = int(policy_mod.builder_pool_desired_total(policy) or 0)
    if total_desired <= 0:
        total_desired = sum(int(item.get("desired", 0)) for item in groups.values())
    total_configured = sum(int(item.get("configured", 0)) for item in groups.values())
    total_available = sum(int(item.get("available", 0)) for item in groups.values())
    recovery = policy_mod.recovery_settings(policy)
    high_backlog = int(recovery.get("high_backlog_pending_tasks", 6))
    min_ratio = float(recovery.get("min_available_ratio", 0.5))
    ratio = (total_available / total_desired) if total_desired else 0.0
    recommended_action = "ok"
    if backlog >= high_backlog and ratio < min_ratio:
        recommended_action = "inspect_dead_or_unhealthy_builders"
        if bool(recovery.get("auto_start_services", False)):
            recommended_action = "auto_start_services_enabled"
    return {
        "ok": True,
        "level": policy_mod.active_level(policy),
        "policy_path": policy.get("_policy_path", "N/A"),
        "backlog": backlog,
        "backlog_breakdown": backlog_breakdown,
        "total_desired": total_desired,
        "total_configured": total_configured,
        "total_available": total_available,
        # Keep total_available as an all-provider health view, but expose the
        # capacity the current dispatch policy can actually use.  Product DAG
        # scheduling must not create virtual slots from an idle forbidden
        # provider while its sole eligible builder is busy.
        "total_policy_available": total_policy_available,
        "provider_policy": _provider_policy_label(),
        "available_ratio": round(ratio, 3),
        "recommended_action": recommended_action,
        "recovery_actions": recovery_actions,
        "rate_limit_pruner": _rate_limit_pruner_status(),
        "rate_limit_blocks": rate_limit_blocks,
        "groups": groups,
        "operators": rows,
    }


def cmd_builder_pool_status(args: argparse.Namespace) -> int:
    snapshot = builder_pool_snapshot(recover=bool(getattr(args, "recover", False)))
    if getattr(args, "json", False):
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))
        return 0 if snapshot.get("ok") else 1
    breakdown = snapshot.get("backlog_breakdown") if isinstance(snapshot.get("backlog_breakdown"), dict) else {}
    print(
        f"builder_pool level={snapshot.get('level', 'N/A')} "
        f"available={snapshot.get('total_available', 'N/A')}/{snapshot.get('total_desired', 'N/A')} "
        f"backlog={snapshot.get('backlog', 'N/A')} "
        f"(pm={breakdown.get('pending_pm', 'N/A')} latent={breakdown.get('latent_builder_ready', 'N/A')}) "
        f"action={snapshot.get('recommended_action', 'N/A')}"
    )
    pruner = snapshot.get("rate_limit_pruner") if isinstance(snapshot.get("rate_limit_pruner"), dict) else {}
    print(
        "rate_limit_pruner "
        f"installed={pruner.get('installed', 'N/A')} loaded={pruner.get('launchd_loaded', 'N/A')} "
        f"interval={pruner.get('run_interval_seconds') or 'N/A'}s "
        f"runs={pruner.get('runs') if pruner.get('runs') is not None else 'N/A'} "
        f"last_exit={pruner.get('last_exit_code') if pruner.get('last_exit_code') is not None else 'N/A'}"
    )
    print(
        f"{'group':<34} {'desired':>7} {'configured':>10} {'available':>9} "
        f"{'blocked':>8} {'cool':>5} {'quota':>5} {'auth':>4} {'health':>6} {'busy':>4}"
    )
    print("-" * 116)
    for group, data in (snapshot.get("groups") or {}).items():
        print(
            f"{group:<34} {int(data.get('desired', 0)):>7} "
            f"{int(data.get('configured', 0)):>10} {int(data.get('available', 0)):>9} {int(data.get('blocked', 0)):>8} "
            f"{int(data.get('cooldown', 0)):>5} {int(data.get('quota_exhausted', 0)):>5} "
            f"{int(data.get('auth_expired', 0)):>4} {int(data.get('health', 0)):>6} {int(data.get('busy', 0)):>4}"
        )
    blocks = snapshot.get("rate_limit_blocks") if isinstance(snapshot.get("rate_limit_blocks"), list) else []
    if blocks:
        print()
        print(f"{'rate-limited builder':<38} {'group':<28} {'state':<16} {'reset eta':<10} {'until'}")
        print("-" * 120)
        for item in blocks:
            print(
                f"{str(item.get('operator_id', 'N/A')):<38} "
                f"{str(item.get('group', 'N/A')):<28} "
                f"{str(item.get('block_type', 'N/A')):<16} "
                f"{str(item.get('cooldown_eta') or 'N/A'):<10} "
                f"{str(item.get('cooldown_until') or 'N/A')}"
            )
    return 0 if snapshot.get("ok") else 1


def _run_cmd_submit_for_builder_node(item: dict[str, Any], dry_run: bool, json_mode: bool) -> dict[str, Any]:
    sprint_id = str(item.get("sprint_id") or "")
    node_id = str(item.get("node_id") or "")
    before_task_ids = {
        str(payload.get("task_id") or "")
        for payload in [_active_pm_record_for_node(sprint_id, node_id)]
        if payload
    }
    args = argparse.Namespace(
        role="builder",
        objective=str(item.get("objective") or ""),
        operator="",
        sprint=sprint_id,
        node=node_id,
        task_type=str(item.get("task_type") or "implementation"),
        context=(
            f"auto_drain_source=planning_complete\n"
            f"task_graph={item.get('graph')}\n"
            f"logical_operator={item.get('logical_operator') or 'N/A'}"
        ),
        dry_run=dry_run,
    )
    old_direct = os.environ.get("SOLAR_PM_DISPATCH_ALLOW_DIRECT")
    os.environ["SOLAR_PM_DISPATCH_ALLOW_DIRECT"] = "1"
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        if json_mode:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = cmd_submit(args)
        else:
            rc = cmd_submit(args)
    finally:
        if old_direct is None:
            os.environ.pop("SOLAR_PM_DISPATCH_ALLOW_DIRECT", None)
        else:
            os.environ["SOLAR_PM_DISPATCH_ALLOW_DIRECT"] = old_direct

    record = _active_pm_record_for_node(sprint_id, node_id)
    task_id = ""
    operator_id = ""
    if record:
        task_id = str(record.get("task_id") or "")
        operator_id = str(record.get("operator_id") or "")
    if task_id in before_task_ids:
        task_id = ""
    return {
        **item,
        "ok": rc == 0,
        "returncode": rc,
        "task_id": task_id,
        "operator_id": operator_id,
        "stdout": stdout.getvalue() if json_mode else "",
        "stderr": stderr.getvalue() if json_mode else "",
    }


def _mark_graph_node_pm_dispatched(item: dict[str, Any], submitted: dict[str, Any]) -> dict[str, Any]:
    graph_scheduler = _load_graph_scheduler_module()
    if graph_scheduler is None:
        return {"ok": False, "reason": "graph_scheduler_unavailable"}
    graph_path = Path(str(item.get("graph") or ""))
    if not graph_path.exists():
        return {"ok": False, "reason": "graph_missing", "graph": str(graph_path)}
    sprint_id = str(item.get("sprint_id") or "")
    node_id = str(item.get("node_id") or "")
    task_id = str(submitted.get("task_id") or "")
    operator_id = str(submitted.get("operator_id") or "")
    try:
        graph_scheduler.SPRINTS_DIR = SPRINTS_DIR
        graph = graph_scheduler.load_graph(graph_path)
        graph_scheduler.set_node_status(graph, node_id, "dispatched", pane=operator_id or None, dispatch_id=task_id or None)
        for node in graph.get("nodes", []) or []:
            if str(node.get("id") or "") != node_id:
                continue
            activate_execution_attempt(
                node,
                task_id=task_id,
                dispatch_id=task_id,
                operator_id=operator_id,
                source="pm_dispatch",
                logical_role=str(item.get("requested_role") or item.get("role") or "builder"),
                status=str(submitted.get("status") or "submitted"),
                requires_operator_result=True,
                sprint_id=sprint_id,
                node_id=node_id,
                result_path=str(submitted.get("result_path") or ""),
                now=str(submitted.get("submitted_at") or _now()),
            )
            break
        graph.setdefault("node_results", {}).setdefault(node_id, {})
        graph["node_results"][node_id]["dispatched_via"] = "pm_dispatch"
        graph["node_results"][node_id]["pm_task_id"] = task_id
        graph["node_results"][node_id]["operator_id"] = operator_id
        graph["node_results"][node_id]["updated_at"] = _now()
        graph_scheduler.save_graph(graph_path, graph)
    except Exception as exc:
        return {"ok": False, "reason": f"mark_failed:{type(exc).__name__}", "error": str(exc), "sprint_id": sprint_id, "node_id": node_id}
    return {"ok": True, "sprint_id": sprint_id, "node_id": node_id, "task_id": task_id, "operator_id": operator_id}


def cmd_drain_builder_ready(args: argparse.Namespace) -> int:
    max_items = max(0, int(getattr(args, "max_items", 0) or 0))
    dry_run = bool(getattr(args, "dry_run", False))
    json_mode = bool(getattr(args, "json", False))
    requested_sprint = str(getattr(args, "sprint", "") or "").strip()

    if requested_sprint:
        nodes, meta = _builder_ready_nodes_for_sprint(requested_sprint)
        if not meta.get("ok"):
            payload = {
                "ok": False,
                "dry_run": dry_run,
                "max_items": max_items,
                "sprint": requested_sprint,
                "latent_builder_ready": 0,
                "submitted": [],
                "marked": [],
                "skipped": [{**meta, "sprint_id": requested_sprint}],
            }
            if json_mode:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(
                    "drain_builder_ready "
                    f"dry_run={dry_run} latent=0 submitted=0 marked=0 skipped=1"
                )
                print(f"  - {requested_sprint} reason={meta.get('reason')}")
            return 1
        items = [
            {
                "sprint_id": requested_sprint,
                "node_id": str(node.get("id") or ""),
                "task_type": _node_builder_task_type(node),
                "logical_operator": str(node.get("logical_operator") or ""),
                "graph": str(meta.get("graph") or SPRINTS_DIR / f"{requested_sprint}.task_graph.json"),
                "objective": _node_builder_objective(requested_sprint, node),
            }
            for node in nodes
        ]
        if max_items:
            items = items[:max_items]
    else:
        items = _latent_builder_ready_items(limit=max_items)

    submitted: list[dict[str, Any]] = []
    marked: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in items:
        if dry_run:
            skipped.append({**item, "reason": "dry_run"})
            continue
        result = _run_cmd_submit_for_builder_node(item, dry_run=False, json_mode=json_mode)
        submitted.append(result)
        if result.get("ok"):
            mark = _mark_graph_node_pm_dispatched(item, result)
            marked.append(mark)
        else:
            skipped.append({**item, "reason": "submit_failed", "returncode": result.get("returncode")})

    payload = {
        "ok": all(item.get("ok") for item in submitted) and all(item.get("ok") for item in marked),
        "dry_run": dry_run,
        "max_items": max_items,
        "sprint": requested_sprint or "",
        "latent_builder_ready": len(items),
        "submitted": submitted,
        "marked": marked,
        "skipped": skipped,
    }
    if json_mode:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(
            "drain_builder_ready "
            f"dry_run={dry_run} latent={len(items)} submitted={len(submitted)} "
            f"marked={sum(1 for item in marked if item.get('ok'))} skipped={len(skipped)}"
        )
        for item in (submitted or skipped)[:20]:
            print(
                f"  - {item.get('sprint_id')} {item.get('node_id')} "
                f"task={item.get('task_id') or 'N/A'} op={item.get('operator_id') or 'N/A'} "
                f"ok={item.get('ok', False)}"
            )
    return 0 if payload["ok"] else 1


def cmd_concurrency_status(args: argparse.Namespace) -> int:
    policy_mod = _load_concurrency_policy_module()
    if policy_mod is None:
        print("ERROR: concurrency_policy unavailable", file=sys.stderr)
        return 1
    policy = policy_mod.load_policy()
    level = policy_mod.active_level(policy)
    payload = {
        "ok": True,
        "active_level": level,
        "policy_path": policy.get("_policy_path", "N/A"),
        "settings": policy_mod.level_settings(policy, level),
        "levels": sorted((policy.get("levels") or {}).keys()),
    }
    autoscale = policy_mod.backlog_autoscaling_snapshot(policy)
    if autoscale:
        payload["backlog_autoscaling"] = autoscale
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"concurrency_level={level} policy={payload['policy_path']}")
        for name in payload["levels"]:
            settings = policy_mod.level_settings(policy, name)
            marker = "*" if name == level else " "
            print(
                f"{marker} {name:<7} graph={settings.get('graph_max_parallel', 'N/A')} "
                f"builder={settings.get('builder_dispatch_limit', 'N/A')} "
                f"drain={settings.get('drain_max_items', 'N/A')}"
            )
        if autoscale:
            metrics = autoscale.get("metrics") if isinstance(autoscale.get("metrics"), dict) else {}
            profile_limits = autoscale.get("profile_limits") if isinstance(autoscale.get("profile_limits"), dict) else {}
            logical_limits = autoscale.get("logical_operator_limits") if isinstance(autoscale.get("logical_operator_limits"), dict) else {}
            builder_pool = autoscale.get("builder_pool") if isinstance(autoscale.get("builder_pool"), dict) else {}
            global_limits = autoscale.get("global_limits") if isinstance(autoscale.get("global_limits"), dict) else {}
            print(
                "backlog_autoscale "
                f"drafting/spec={metrics.get('drafting_spec', 'N/A')} "
                f"prd_ready={metrics.get('active_prd_ready', 'N/A')} "
                f"planning_complete={metrics.get('active_planning_complete', 'N/A')} "
                f"handoff_ready={metrics.get('reviewing_handoff_ready', 'N/A')}"
            )
            print(
                "profile_limits "
                f"pm={profile_limits.get('pm', 'N/A')} "
                f"planner={profile_limits.get('planner', 'N/A')} "
                f"builder={profile_limits.get('builder', 'N/A')} "
                f"evaluator={profile_limits.get('evaluator', 'N/A')} "
                f"max_workers={global_limits.get('max_workers', 'N/A')}"
            )
            print(
                "logical_limits "
                f"DeepArchitect={logical_limits.get('DeepArchitect', 'N/A')} "
                f"ParallelExplorer={logical_limits.get('ParallelExplorer', 'N/A')} "
                f"ImplementationWorker={logical_limits.get('ImplementationWorker', 'N/A')} "
                f"Verifier={logical_limits.get('Verifier', 'N/A')}"
            )
            print(
                "builder_pool_targets "
                f"desired_total={builder_pool.get('desired_total', 'N/A')} "
                f"spark={((builder_pool.get('groups') or {}).get('codex-gpt-5.3-spark', 'N/A'))} "
                f"gpt55={((builder_pool.get('groups') or {}).get('codex-gpt-5.5-medium', 'N/A'))} "
                f"sonnet={((builder_pool.get('groups') or {}).get('sonnet', 'N/A'))}"
            )
    return 0


def cmd_concurrency_set(args: argparse.Namespace) -> int:
    level = str(args.level or "").strip().lower()
    if level not in {"low", "normal", "high", "burst"}:
        print("ERROR: --level must be one of low|normal|high|burst", file=sys.stderr)
        return 1
    policy_mod = _load_concurrency_policy_module()
    if policy_mod is None:
        print("ERROR: concurrency_policy unavailable", file=sys.stderr)
        return 1
    policy = policy_mod.load_policy()
    policy_path = Path(str(policy.get("_policy_path") or ""))
    if not policy_path.exists() or str(policy_path) == "builtin":
        policy_path = HARNESS_DIR / "config" / "concurrency-policy.json"
    policy.pop("_policy_path", None)
    policy["active_level"] = level
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(policy_path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(policy, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, str(policy_path))
    print(f"✅ concurrency_level set to {level}")
    print(f"   policy = {policy_path}")
    return 0


def cmd_quota_refresh(args: argparse.Namespace) -> int:
    tool = HARNESS_DIR / "tools" / "quota_refresh.py"
    if not tool.exists():
        print(f"ERROR: quota_refresh.py not found: {tool}", file=sys.stderr)
        return 1
    cmd = [sys.executable, str(tool)]
    if getattr(args, "json", False):
        cmd.append("--json")
    if getattr(args, "apply", False):
        cmd.append("--apply")
    proc = subprocess.run(cmd, cwd=str(HARNESS_DIR), text=True, capture_output=True, timeout=60, check=False)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode


def cmd_prune_rate_limits(args: argparse.Namespace) -> int:
    result = _prune_expired_operator_blocks()
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    pruned = result.get("pruned") if isinstance(result.get("pruned"), list) else []
    kept = result.get("kept") if isinstance(result.get("kept"), list) else []
    print(f"rate_limit_prune ok={result.get('ok', False)} pruned={len(pruned)} kept={len(kept)}")
    if pruned:
        for item in pruned:
            print(f"  cleared {item.get('operator_id')} state={item.get('runtime_state')} expired_at={item.get('expired_at')}")
    return 0 if result.get("ok") else 1


def cmd_inbox(args: argparse.Namespace) -> int:
    limit = int(getattr(args, "limit", 20))
    tasks = list_pm_tasks(limit=limit)
    if not tasks:
        print("PM inbox 为空（暂无任务记录）")
        return 0
    print(f"{'Task ID':<36} {'算子':<35} {'状态':<20} {'提交时间'}")
    print("-" * 110)
    for t in tasks:
        tid = str(t.get("task_id", "?"))[:35]
        op = str(t.get("operator_id", "?"))[:34]
        st = str(t.get("status", "?"))[:19]
        ts = str(t.get("submitted_at", "?"))[:19]
        print(f"{tid:<36} {op:<35} {st:<20} {ts}")
    return 0


def cmd_result(args: argparse.Namespace) -> int:
    task_id = str(args.task_id or "").strip()
    if not task_id:
        print("ERROR: --task-id required", file=sys.stderr)
        return 1
    record = read_pm_task_record(task_id)
    if not record:
        print(f"ERROR: task {task_id} not found in PM inbox", file=sys.stderr)
        return 1
    print(json.dumps(record, indent=2, ensure_ascii=False))

    # Surface any active cooldown for the operator that ran this task
    operator_id = str(record.get("operator_id") or "")
    if operator_id:
        rt_state = get_operator_runtime_state(operator_id)
        if rt_state in ("cooldown", "quota_exhausted", "auth_expired"):
            status = get_operator_status_data(operator_id)
            expires_at = str(status.get("expires_at") or "")
            eta = _format_reset_eta(expires_at)
            print(f"\n⚠️  算子冷却中: operator={operator_id} state={rt_state}", end="")
            if eta:
                print(f", resets {eta}", end="")
            if expires_at:
                print(f" (until {expires_at})", end="")
            print()

    result_path = Path(record.get("result_path", ""))
    if result_path.exists():
        print("\n--- 结果文件内容 ---")
        print(result_path.read_text(encoding="utf-8", errors="replace"))
    else:
        print(f"\n结果文件尚未生成：{result_path}")
    return 0


def cmd_complete(args: argparse.Namespace) -> int:
    """算子调用：标记任务完成（写入 PM inbox）"""
    task_id = str(args.task_id or "").strip()
    if not task_id:
        print("ERROR: --task-id required", file=sys.stderr)
        return 1
    record = read_pm_task_record(task_id) or {}
    record["task_id"] = task_id
    closeout = _pm_closeout_status(record)
    if not closeout.get("ok"):
        record["status"] = "failed_contract_closeout"
        record["failed_at"] = _now()
        record["failure_reason"] = "completed_without_required_artifacts"
        record["closeout_status"] = closeout
        record.setdefault("reconcile_history", []).append(
            {"ts": record["failed_at"], "action": "fail_contract_closeout", "reason": record["failure_reason"], **closeout}
        )
        write_pm_task_record(task_id, record)
        print(json.dumps({"ok": False, "task_id": task_id, "reason": record["failure_reason"], **closeout}, ensure_ascii=False))
        return 2
    record["status"] = "completed"
    record["completed_at"] = _now()
    record["closeout_status"] = closeout
    write_pm_task_record(task_id, record)
    print(f"✅ 任务 {task_id} 已标记为 completed")
    return 0


def cmd_fail(args: argparse.Namespace) -> int:
    """算子调用：标记任务失败（写入 PM inbox），避免 failed worker 继续显示 submitted。"""
    task_id = str(args.task_id or "").strip()
    if not task_id:
        print("ERROR: --task-id required", file=sys.stderr)
        return 1
    status = str(args.status or "failed").strip() or "failed"
    if not status.startswith("failed"):
        status = f"failed_{status}"
    record = read_pm_task_record(task_id) or {}
    record["task_id"] = task_id
    record["status"] = status
    record["failed_at"] = _now()
    record["failure_reason"] = str(args.reason or status).strip()[:2000]
    write_pm_task_record(task_id, record)
    print(f"❌ 任务 {task_id} 已标记为 {status}")
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    """Repair PM inbox projection drift without bypassing operator evidence."""
    max_age_minutes = max(1, int(args.max_age_minutes or 60))
    apply_changes = bool(args.apply)
    active_task_ids = _active_pm_task_ids()
    actions: list[dict[str, Any]] = []
    now = _now()

    for path in _pm_record_files():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            actions.append({"task_id": path.stem, "action": "skip_corrupt", "reason": type(exc).__name__})
            continue

        task_id = str(record.get("task_id") or path.stem)
        status = str(record.get("status") or "").strip()
        if status == "completed":
            closeout = _pm_closeout_status(record)
            if closeout.get("ok"):
                continue
            actions.append({
                "task_id": task_id,
                "action": "fail_contract_closeout",
                "reason": "completed_without_required_artifacts",
                **closeout,
            })
            if apply_changes:
                record["task_id"] = task_id
                record["status"] = "failed_contract_closeout"
                record["failed_at"] = now
                record["failure_reason"] = "completed_without_required_artifacts"
                record["closeout_status"] = closeout
                record.setdefault("reconcile_history", []).append(
                    {"ts": now, "action": "fail_contract_closeout", "reason": "completed_without_required_artifacts", **closeout}
                )
                write_pm_task_record(task_id, record)
            continue
        if _pm_status_is_terminal(status):
            continue

        result_path = Path(str(record.get("result_path") or ""))
        result_exists = bool(str(result_path) and result_path.exists())
        if result_exists:
            closeout = _pm_closeout_status(record)
            if not closeout.get("ok"):
                actions.append({
                    "task_id": task_id,
                    "action": "fail_contract_closeout",
                    "reason": "result_path_exists_but_required_artifacts_missing",
                    **closeout,
                })
                if apply_changes:
                    record["task_id"] = task_id
                    record["status"] = "failed_contract_closeout"
                    record["failed_at"] = now
                    record["failure_reason"] = "result_path_exists_but_required_artifacts_missing"
                    record["closeout_status"] = closeout
                    record.setdefault("reconcile_history", []).append(
                        {"ts": now, "action": "fail_contract_closeout", "reason": "result_path_exists_but_required_artifacts_missing", **closeout}
                    )
                    write_pm_task_record(task_id, record)
                continue
            actions.append({"task_id": task_id, "action": "complete", "reason": "result_path_exists", **closeout})
            if apply_changes:
                record["task_id"] = task_id
                record["status"] = "completed"
                record["completed_at"] = now
                record["closeout_status"] = closeout
                record.setdefault("reconcile_history", []).append(
                    {"ts": now, "action": "complete", "reason": "result_path_exists", **closeout}
                )
                write_pm_task_record(task_id, record)
            continue

        age = _record_age_minutes(record, path)
        if task_id in active_task_ids:
            actions.append({"task_id": task_id, "action": "keep_active", "age_min": round(age, 1)})
            continue
        if age >= max_age_minutes:
            actions.append(
                {
                    "task_id": task_id,
                    "action": "fail_missing_pm_result",
                    "age_min": round(age, 1),
                    "reason": "stale_without_live_lease",
                }
            )
            if apply_changes:
                record["task_id"] = task_id
                record["status"] = "failed_missing_pm_result"
                record["failed_at"] = now
                record["failure_reason"] = "stale_without_live_lease"
                record.setdefault("reconcile_history", []).append(
                    {"ts": now, "action": "fail_missing_pm_result", "age_min": round(age, 1)}
                )
                write_pm_task_record(task_id, record)

    summary: dict[str, int] = {}
    for item in actions:
        action = str(item.get("action") or "unknown")
        summary[action] = summary.get(action, 0) + 1
    payload = {"ok": True, "applied": apply_changes, "max_age_minutes": max_age_minutes, "summary": summary, "actions": actions}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"pm_reconcile applied={apply_changes} max_age_minutes={max_age_minutes}")
    for key in sorted(summary):
        print(f"  {key}: {summary[key]}")
    for item in actions[: int(args.limit or 40)]:
        print(f"  - {item.get('action')}: {item.get('task_id')} ({item.get('reason', 'N/A')})")
    return 0


def _preflight_task_type_for_role(role: str) -> str:
    role = normalize_role(role)
    if role == "planner":
        return "planning"
    if role == "evaluator":
        return "graph_eval"
    if role == "pm":
        return "pm_order"
    return "implementation"


def _provider_aliases(provider: str) -> set[str]:
    p = str(provider or "").strip().lower()
    aliases = {p} if p else set()
    if p == "openai":
        aliases.update({"codex", "gpt"})
    if p == "anthropic":
        aliases.update({"claude", "claude-code"})
    if p == "google":
        aliases.update({"gemini"})
    return aliases


def cmd_route_preflight(args: argparse.Namespace) -> int:
    """Verify that every requested runtime role resolves to the selected provider.

    This is intentionally no-model and no-dispatch. It makes runtime selection a
    hard contract before intake/approval spends user quota.
    """
    runtime = str(args.runtime or _runtime_mode_from_env() or "mixed").strip().lower()
    expected_provider = str(args.expect_provider or "").strip().lower()
    if not expected_provider:
        if runtime == "codex":
            expected_provider = "openai"
        elif runtime == "claude":
            expected_provider = "anthropic"
    roles = [
        normalize_role(item)
        for item in re.split(r"[, ]+", str(args.roles or "planner,builder,evaluator"))
        if str(item).strip()
    ]
    items: list[dict[str, Any]] = []
    ok = True
    for role in roles:
        task_type = _preflight_task_type_for_role(role)
        operator_id, operator, reason = select_operator_by_role(role, task_type=task_type)
        provider = str(operator.get("provider") or operator.get("vendor") or "").strip().lower() if operator else ""
        route_ok = bool(operator_id)
        if expected_provider:
            route_ok = route_ok and expected_provider in _provider_aliases(provider)
        if not route_ok:
            ok = False
        items.append(
            {
                "role": role,
                "task_type": task_type,
                "ok": route_ok,
                "operator_id": operator_id,
                "provider": provider,
                "backend": str(operator.get("backend") or "") if operator else "",
                "model": str(operator.get("model") or "") if operator else "",
                "runtime_state": get_operator_runtime_state(operator_id) if operator_id else "",
                "reason": "" if route_ok else (reason or "provider_mismatch_or_no_operator"),
            }
        )
    payload = {
        "ok": ok,
        "runtime": runtime,
        "expected_provider": expected_provider,
        "provider_policy": _provider_policy_label(),
        "roles": items,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if ok else 1


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        prog="pm_dispatch",
        description="PM 入口：默认只捕获 RawIntent；直接派发需显式 SOLAR_PM_DISPATCH_ALLOW_DIRECT=1",
    )
    sub = p.add_subparsers(dest="cmd")

    # submit
    s = sub.add_parser("submit", help="捕获 PM 原始需求为 RawIntent（默认不直接派发）")
    s.add_argument("--role", default="builder", help="目标角色 (builder/planner/evaluator/knowledge)")
    s.add_argument("--objective", required=True, help="任务描述（自然语言）")
    s.add_argument("--operator", default="", help="指定物理算子 ID（可选）")
    s.add_argument("--sprint", default="", help="关联 sprint ID（可选，默认 pm-adhoc-xxx）")
    s.add_argument("--node", default="N1", help="关联 DAG 节点 ID（默认 N1）")
    s.add_argument("--task-type", default="", help="任务类型提示（用于算子评分）")
    s.add_argument(
        "--closeout-kind",
        default="",
        choices=sorted(PM_CLOSEOUT_KINDS),
        help="显式完成产物契约；graph dispatch 必须声明 execution 或 eval 阶段",
    )
    s.add_argument(
        "--expected-artifact",
        action="append",
        default=[],
        help="closeout 检查的精确产物路径；仅 graph_eval 可覆盖为受限 quorum sidecar pair",
    )
    s.add_argument("--context", default="", help="额外上下文（注入 dispatch 文件）")
    s.add_argument("--work-dir", default="", help="算子工作目录；默认 <sprint>/workdir")
    s.add_argument("--dry-run", action="store_true", help="预览，不实际提交")

    cr = sub.add_parser("compile-request", help="捕获编译请求为 RawIntent（默认不直接创建 sprint/package）")
    cr.add_argument("--text", default="", help="原始需求文本")
    cr.add_argument("--input-file", default="", help="从文件读取原始需求")
    cr.add_argument("--paper", action="append", default=[], help="论文标题、链接或标识")
    cr.add_argument("--log", action="append", default=[], help="相关日志路径")
    cr.add_argument("--repo-context", action="append", default=[], help="repo/模块上下文")
    cr.add_argument("--sprint", default="", help="目标 sprint id；默认自动生成")
    cr.add_argument("--workspace-root", default="", help="写入 .pm/ 的工作区根目录；默认当前目录")
    cr.add_argument("--target-system", default="solar-harness", choices=["solar-harness", "codex"], help="下游目标系统")
    cr.add_argument("--dispatch-planner", action="store_true", help="编译后自动 handoff 给 planner")
    cr.add_argument("--dry-run", action="store_true", help="和 --dispatch-planner 配合时预览 planner 派单")

    # fleet-status
    sub.add_parser("fleet-status", help="查看所有物理算子的状态")

    rp = sub.add_parser("route-preflight", help="验证当前 runtime/provider 下的 PM/planner/builder/evaluator 路由")
    rp.add_argument("--runtime", default="", help="codex|claude；默认从环境/ provider policy 推断")
    rp.add_argument("--expect-provider", default="", help="openai|anthropic；默认由 runtime 推断")
    rp.add_argument("--roles", default="planner,builder,evaluator", help="逗号分隔角色列表")
    rp.add_argument("--pretty", action="store_true", help="pretty JSON")

    # builder-pool-status
    bps = sub.add_parser("builder-pool-status", help="查看 builder pool 与并发旋钮状态")
    bps.add_argument("--json", action="store_true", help="输出 JSON")
    bps.add_argument("--recover", action="store_true", help="尝试启动声明了 auto_start 的健康失败本地 builder 服务")

    drain = sub.add_parser("drain-builder-ready", help="把 planning_complete latent ready 节点提交到 PM builder pool")
    drain.add_argument("--sprint", default="", help="只 drain 指定 sprint")
    drain.add_argument("--max-items", type=int, default=0, help="最多提交的节点数；0 表示不限制")
    drain.add_argument("--dry-run", action="store_true", help="只列出将提交的 builder-ready 节点")
    drain.add_argument("--json", action="store_true", help="输出 JSON")

    cs = sub.add_parser("concurrency-status", help="查看统一并发旋钮状态")
    cs.add_argument("--json", action="store_true", help="输出 JSON")

    cset = sub.add_parser("concurrency-set", help="持久设置统一并发旋钮")
    cset.add_argument("--level", required=True, choices=["low", "normal", "high", "burst"], help="并发等级")

    prune = sub.add_parser("prune-rate-limits", help="清除已到期的物理算子 rate-limit/auth 熔断")
    prune.add_argument("--json", action="store_true", help="输出 JSON")

    qr = sub.add_parser("quota-refresh", help="刷新 provider quota/rate snapshot 并生成动态并发建议")
    qr.add_argument("--json", action="store_true", help="输出 JSON")
    qr.add_argument("--apply", action="store_true", help="写入 latest snapshot；动态策略自动读取")

    # inbox
    ib = sub.add_parser("inbox", help="查看 PM 任务收件箱")
    ib.add_argument("--limit", type=int, default=20, help="显示最近 N 条")

    # result
    r = sub.add_parser("result", help="查看任务结果")
    r.add_argument("--task-id", required=True, help="Task ID")

    # complete
    c = sub.add_parser("complete", help="标记任务完成（由算子调用）")
    c.add_argument("--task-id", required=True, help="Task ID")

    f = sub.add_parser("fail", help="标记任务失败（由算子调用）")
    f.add_argument("--task-id", required=True, help="Task ID")
    f.add_argument("--status", default="failed", help="失败状态，必须以 failed 开头；否则自动加 failed_ 前缀")
    f.add_argument("--reason", default="", help="失败原因摘要")

    rec = sub.add_parser("reconcile", help="修复 PM inbox 投影漂移：完成已有结果，失败无 live lease 的 stale 任务")
    rec.add_argument("--max-age-minutes", type=int, default=60, help="无结果且无 live lease 的 stale 判定分钟数")
    rec.add_argument("--apply", action="store_true", help="实际写入；默认只预览")
    rec.add_argument("--json", action="store_true", help="输出 JSON")
    rec.add_argument("--limit", type=int, default=40, help="非 JSON 输出显示前 N 条动作")

    args = p.parse_args()
    dispatch = {
        "submit": cmd_submit,
        "compile-request": cmd_compile_request,
        "fleet-status": cmd_fleet_status,
        "route-preflight": cmd_route_preflight,
        "builder-pool-status": cmd_builder_pool_status,
        "drain-builder-ready": cmd_drain_builder_ready,
        "concurrency-status": cmd_concurrency_status,
        "concurrency-set": cmd_concurrency_set,
        "quota-refresh": cmd_quota_refresh,
        "prune-rate-limits": cmd_prune_rate_limits,
        "inbox": cmd_inbox,
        "result": cmd_result,
        "complete": cmd_complete,
        "fail": cmd_fail,
        "reconcile": cmd_reconcile,
    }
    fn = dispatch.get(args.cmd or "")
    if fn is None:
        p.print_help()
        return 0
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
