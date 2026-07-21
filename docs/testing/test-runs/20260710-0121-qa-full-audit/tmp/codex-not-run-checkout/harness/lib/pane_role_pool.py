"""Shared pane role-pool discovery + dispatch-boundary hygiene helpers."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from pane_clear_manager import PaneClearManager
from pane_hygiene_registry import PaneHygieneRegistry, PaneState
from recover_detector import RecoverDetector


def harness_dir() -> Path:
    raw = os.environ.get("HARNESS_DIR")
    return Path(raw).expanduser() if raw else Path(__file__).resolve().parents[1]


SESSION = os.environ.get("SOLAR_HARNESS_SESSION", "solar-harness")
HARNESS_DIR = harness_dir()
REGISTRY_PATH = HARNESS_DIR / "run" / "pane-hygiene.json"
PHYSICAL_OPERATORS_PATH = Path(
    os.environ.get("SOLAR_MULTI_TASK_OPERATORS", HARNESS_DIR / "config" / "physical-operators.json")
)


def _current_harness_session() -> str:
    session = str(os.environ.get("SOLAR_HARNESS_SESSION") or SESSION or "solar-harness").strip()
    return session or "solar-harness"


def _pane_session_name(pane: str) -> str:
    return str(pane or "").split(":", 1)[0].strip()


def _allowed_pane_sessions() -> set[str]:
    session = _current_harness_session()
    allowed = {session, f"{session}-lab", f"{session}-multi-task"}
    for env_name in (
        "SOLAR_HARNESS_LAB_SESSION",
        "SOLAR_HARNESS_BG_SESSION",
        "SOLAR_HARNESS_MULTI_TASK_SESSION",
    ):
        value = str(os.environ.get(env_name) or "").strip()
        if value:
            allowed.add(value)
    for value in str(os.environ.get("SOLAR_HARNESS_ALLOWED_EXTRA_SESSIONS") or "").split(","):
        value = value.strip()
        if value:
            allowed.add(value)
    if session == "solar-harness":
        allowed.update({"solar-harness-lab", "solar-harness-multi-task"})
    return allowed


def _pane_in_harness_session_scope(pane: str) -> bool:
    return _pane_session_name(pane) in _allowed_pane_sessions()


def _pane_in_lab_session(pane: str) -> bool:
    session = _current_harness_session()
    names = {f"{session}-lab"}
    for env_name in ("SOLAR_HARNESS_LAB_SESSION", "SOLAR_HARNESS_BG_SESSION"):
        value = str(os.environ.get(env_name) or "").strip()
        if value:
            names.add(value)
    if session == "solar-harness":
        names.add("solar-harness-lab")
    return _pane_session_name(pane) in names


def _pane_in_multi_task_session(pane: str) -> bool:
    session = _current_harness_session()
    names = {f"{session}-multi-task"}
    value = str(os.environ.get("SOLAR_HARNESS_MULTI_TASK_SESSION") or "").strip()
    if value:
        names.add(value)
    if session == "solar-harness":
        names.add("solar-harness-multi-task")
    return _pane_session_name(pane) in names


def list_tmux_panes() -> list[dict[str, str]]:
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{session_name}:#{window_index}.#{pane_index}\t#{pane_title}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if result.returncode != 0:
        return []
    rows: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        pane, _, title = line.partition("\t")
        rows.append({"pane": pane.strip(), "title": title.strip()})
    return rows


def _allowed_session(pane: str) -> bool:
    return _pane_in_harness_session_scope(pane)


def _normalize_role(role: str) -> str:
    return str(role or "").strip().lower().replace("_", "-")


def _load_operator_registry() -> dict[str, Any]:
    if not PHYSICAL_OPERATORS_PATH.exists():
        return {"version": 1, "operators": {}}
    try:
        payload = json.loads(PHYSICAL_OPERATORS_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"version": 1, "operators": {}}
    except Exception:
        return {"version": 1, "operators": {}}


def _operator_roles(spec: dict[str, Any]) -> set[str]:
    raw_roles = spec.get("roles")
    values: list[str]
    if isinstance(raw_roles, str):
        values = [raw_roles]
    elif isinstance(raw_roles, list):
        values = [str(item) for item in raw_roles]
    else:
        values = []
    role = str(spec.get("role") or "").strip()
    if role:
        values.append(role)
    return {_normalize_role(item) for item in values if str(item or "").strip()}


def _pane_pattern_matches(pattern: str, pane: str) -> bool:
    raw = str(pattern or "").strip()
    if not raw:
        return False
    if raw.endswith(":*"):
        return pane.startswith(raw[:-1])
    return fnmatch.fnmatch(pane, raw)


def _registry_roles_for_pane(pane: str) -> set[str]:
    registry = _load_operator_registry()
    operators = registry.get("operators") if isinstance(registry.get("operators"), dict) else {}
    roles: set[str] = set()
    for spec in operators.values():
        if not isinstance(spec, dict):
            continue
        if not bool(spec.get("enabled", False)) or not bool(spec.get("available", False)):
            continue
        if not _pane_pattern_matches(str(spec.get("pane") or ""), pane):
            continue
        roles.update(_operator_roles(spec))
    return roles


def infer_role(pane: str, title: str) -> str:
    normalized = title or ""
    base = normalized.split("|", 1)[0].strip()
    lowered = base.lower()
    registry_roles = _registry_roles_for_pane(pane)
    session = _current_harness_session()
    if pane.endswith(":0.0") and pane.startswith(f"{session}:") and ("pm" in lowered or "产品经理" in base):
        return "pm"
    if "planner" in lowered or "规划者" in base:
        return "planner"
    if "evaluator" in lowered or "审判官" in base:
        return "evaluator"
    if "architect" in lowered or "架构师" in base:
        return "architect"
    if "observer" in lowered or "观察" in base:
        return "observer"
    if "builder" in lowered or "建设者" in base or "lab-builder" in lowered:
        return "builder"
    for candidate in ("planner", "evaluator", "architect", "builder", "pm"):
        if candidate in registry_roles:
            return candidate
    if _pane_in_lab_session(pane) or _pane_in_multi_task_session(pane):
        return "builder"
    if pane == f"{session}:0.0":
        return "pm"
    if pane == f"{session}:0.1":
        return "planner"
    if pane == f"{session}:0.3":
        return "evaluator"
    return "builder"


def _planner_rank(item: dict[str, str]) -> tuple[int, str]:
    role = item["host_role"]
    pane = item["pane"]
    if role == "planner":
        if pane.startswith(f"{_current_harness_session()}:"):
            return (0, pane)
        if _pane_in_multi_task_session(pane):
            return (1, pane)
        return (0, pane)
    if role == "architect":
        return (2, pane)
    if role == "builder":
        return (3, pane)
    return (9, pane)


def _evaluator_rank(item: dict[str, str]) -> tuple[int, str]:
    role = item["host_role"]
    pane = item["pane"]
    if role == "evaluator":
        if pane.startswith(f"{_current_harness_session()}:"):
            return (0, pane)
        if _pane_in_multi_task_session(pane):
            return (1, pane)
        return (0, pane)
    if role == "builder":
        return (2, pane)
    return (9, pane)


def _builder_rank(item: dict[str, str]) -> tuple[int, str]:
    pane = item["pane"]
    if _pane_in_lab_session(pane):
        return (0, pane)
    if _pane_in_multi_task_session(pane):
        return (1, pane)
    return (2, pane)


def discover_role_pool(role: str) -> list[dict[str, str]]:
    rows = []
    for item in list_tmux_panes():
        pane = item["pane"]
        if not _allowed_session(pane):
            continue
        registry_roles = _registry_roles_for_pane(pane)
        host_role = infer_role(pane, item["title"])
        effective_host_role = host_role
        if role in registry_roles:
            effective_host_role = role
        item = {
            "pane": pane,
            "title": item["title"],
            "host_role": effective_host_role,
            "registry_roles": sorted(registry_roles),
        }
        if role == "pm":
            if effective_host_role in {"pm", "observer"} or role in registry_roles:
                rows.append(item)
        elif role == "planner":
            if effective_host_role in {"planner", "architect", "builder"} or role in registry_roles:
                rows.append(item)
        elif role == "builder":
            if effective_host_role == "builder" or role in registry_roles:
                rows.append(item)
        elif role == "evaluator":
            if effective_host_role in {"evaluator", "builder"} or role in registry_roles:
                rows.append(item)
    if role == "planner":
        rows.sort(key=_planner_rank)
    elif role == "evaluator":
        rows.sort(key=_evaluator_rank)
    elif role == "builder":
        rows.sort(key=_builder_rank)
    else:
        rows.sort(key=lambda item: item["pane"])
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for item in rows:
        pane = item["pane"]
        if pane in seen:
            continue
        seen.add(pane)
        deduped.append(item)
    return deduped


def _entry_for_boundary(registry: PaneHygieneRegistry, pane: str, role: str):
    entry = registry.ensure_pane(pane, role)
    if entry.state == PaneState.clean:
        registry.transition_state(pane, PaneState.running, reason="dispatch_boundary_mark_running")
        entry = registry.transition_state(pane, PaneState.dirty, reason="dispatch_boundary_requires_clear")
    elif entry.state == PaneState.running:
        entry = registry.transition_state(pane, PaneState.dirty, reason="dispatch_boundary_requires_clear")
    elif entry.state == PaneState.dirty:
        entry = registry.get_pane_state(pane)
    return entry


def _pane_capture_tail(pane: str, lines: int = 14) -> str:
    try:
        out = subprocess.run(
            ["tmux", "capture-pane", "-t", pane, "-p"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    if out.returncode != 0:
        return ""
    return "\n".join(out.stdout.splitlines()[-lines:])


def _pane_actively_working(pane: str) -> bool:
    # Claude Code prints "esc to interrupt" while a turn is in flight. Never
    # reconcile a pane that is mid-task.
    return "esc to interrupt" in _pane_capture_tail(pane).lower()


def _pane_active_lease(pane: str) -> bool:
    safe = pane.replace(":", "_").replace(".", "_")
    lease = HARNESS_DIR / "run" / "pane-leases" / f"{safe}.json"
    if not lease.exists():
        return False
    try:
        data = json.loads(lease.read_text(encoding="utf-8"))
    except Exception:
        return True
    expires = str(data.get("expires") or data.get("expires_at") or "")
    if not expires:
        return True
    try:
        from datetime import datetime, timezone

        return datetime.fromisoformat(expires.replace("Z", "+00:00")) > datetime.now(timezone.utc)
    except Exception:
        return True


def _reconcile_stranded_main_pane(
    registry: PaneHygieneRegistry,
    manager: PaneClearManager,
    pane: str,
    state: PaneState,
) -> bool:
    """Unattended recovery for a MAIN cockpit pane stranded in a severe hygiene
    state (needs_respawn / needs_recover).

    pane_doctor never auto-respawns or repairs PROTECTED main panes, so a single
    exhausted /clear can strand a main pane — and the whole pipeline — forever
    (observed: PM pane stuck `needs_respawn` from a stale clear-exhaust, blocking
    every sprint at pm_prd_fix with "no usable pm"). Reconcile a pane back to
    `running` ONLY when it is unleased, not actively working, and not sitting on
    a real confirm/queued overlay — i.e. a live idle pane whose only problem is
    the stale severe-state latch. It then rejoins the normal dispatch-boundary
    clear path and clear_with_retry cleans any input residue. A genuinely wedged
    pane fails these guards and stays flagged (no fake recovery — that case still
    needs a real respawn)."""
    if state not in {PaneState.needs_respawn, PaneState.needs_recover}:
        return False
    if _pane_active_lease(pane):
        return False
    if _pane_actively_working(pane):
        return False
    _empty, no_queued, no_confirm = manager.verify_clear_success(pane)
    if not (no_queued and no_confirm):
        return False
    registry.transition_state(
        pane, PaneState.running, reason="stranded_main_pane_idle_reconcile"
    )
    return True


def ensure_clean_for_dispatch(pane: str, role: str, registry_path: Path | None = None) -> dict[str, Any]:
    registry = PaneHygieneRegistry(str((registry_path or REGISTRY_PATH).expanduser()))
    entry = _entry_for_boundary(registry, pane, role)
    manager = PaneClearManager(registry, RecoverDetector())
    if entry.state in {PaneState.cooling, PaneState.needs_recover, PaneState.needs_respawn}:
        if _reconcile_stranded_main_pane(registry, manager, pane, entry.state):
            entry = _entry_for_boundary(registry, pane, role)
        else:
            return {"ok": False, "pane": pane, "role": role, "reason": entry.state.value}
    result = manager.clear_with_retry(pane)
    if result.success:
        registry.update_context_fields(pane, persona=role)
    return {
        "ok": result.success,
        "pane": pane,
        "role": role,
        "reason": result.reason,
        "attempts": result.attempts,
        "final_state": result.final_state.value,
        "signal_empty": result.signal_empty,
        "signal_no_queued": result.signal_no_queued,
        "signal_no_confirm": result.signal_no_confirm,
    }


def reset_pane_hygiene_after_respawn(pane: str, registry_path: Path | None = None) -> dict[str, Any]:
    """Drop a pane's hygiene entry after it has been respawned (Fix C). A respawn
    launches a brand-new Claude process, so any prior severe state (needs_respawn /
    dirty / cooling / cooldown) no longer describes the live pane and must not strand
    it from dispatch. The next dispatch boundary re-registers the pane clean.
    Idempotent: a no-op if the pane has no entry."""
    registry = PaneHygieneRegistry(str((registry_path or REGISTRY_PATH).expanduser()))
    try:
        registry.unregister_pane(pane)
        return {"ok": True, "pane": pane, "reset": "unregistered"}
    except KeyError:
        return {"ok": True, "pane": pane, "reset": "absent"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pane role-pool + hygiene utilities")
    sub = parser.add_subparsers(dest="cmd", required=True)

    discover_cmd = sub.add_parser("discover-role-pool")
    discover_cmd.add_argument("--role", required=True)

    clear_cmd = sub.add_parser("ensure-clean")
    clear_cmd.add_argument("--pane", required=True)
    clear_cmd.add_argument("--role", required=True)
    clear_cmd.add_argument("--registry", default=str(REGISTRY_PATH))

    reset_cmd = sub.add_parser("reset-hygiene")
    reset_cmd.add_argument("--pane", required=True)
    reset_cmd.add_argument("--registry", default=str(REGISTRY_PATH))

    args = parser.parse_args(argv)
    if args.cmd == "discover-role-pool":
        print(json.dumps({"role": args.role, "panes": discover_role_pool(args.role)}, ensure_ascii=False))
        return 0
    if args.cmd == "ensure-clean":
        result = ensure_clean_for_dispatch(
            args.pane,
            args.role,
            registry_path=Path(args.registry).expanduser(),
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    if args.cmd == "reset-hygiene":
        result = reset_pane_hygiene_after_respawn(args.pane, registry_path=Path(args.registry).expanduser())
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
