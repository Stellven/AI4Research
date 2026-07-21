#!/usr/bin/env python3
"""pane_doctor.py — canonical diagnosis for TUI pane lifecycle drift.

This module keeps pane lifecycle decisions out of the dispatcher hot path. It
diagnoses tmux/TUI/hygiene/lease/cooldown state together, and can apply only
safe registry/cooldown repairs. Respawn support is intentionally limited to
lab builder panes and is guarded by lease/TUI activity checks.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
LIB_DIR = HARNESS_DIR / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import graph_node_dispatcher as gnd  # noqa: E402
from pane_hygiene_registry import IllegalTransitionError, PaneHygieneRegistry, PaneState  # noqa: E402
from pane_lease import read_lease  # noqa: E402
from ledger_writer import LedgerWriter  # noqa: E402


SESSION = os.environ.get("SOLAR_HARNESS_SESSION", "solar-harness")
LAB_SESSION = os.environ.get("SOLAR_HARNESS_LAB_SESSION", "solar-harness-lab")
DISPATCH_SESSION = os.environ.get("SOLAR_HARNESS_DISPATCH_SESSION", "solar-harness-dispatch")
MULTI_TASK_SESSION = os.environ.get("SOLAR_HARNESS_MULTI_TASK_SESSION", "solar-harness-multi-task")
CONTEXT_TOKEN_RESPAWN_THRESHOLD = int(os.environ.get("SOLAR_PANE_DOCTOR_CONTEXT_TOKEN_RESPAWN_THRESHOLD", "250000"))
PROTECTED_PANES = {f"{SESSION}:0.0", f"{SESSION}:0.1", f"{SESSION}:0.2", f"{SESSION}:0.3"}
LAB_PANE_RE = re.compile(rf"^{re.escape(LAB_SESSION)}:0\.([0-3])$")
STATE_SEVERITY = {
    "clean": 0,
    "running": 1,
    "dirty": 2,
    "cooling": 3,
    "needs_recover": 4,
    "needs_respawn": 5,
}


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _utc_now() -> str:
    return gnd._utc_now()


def _pane_rows() -> list[tuple[str, str]]:
    try:
        out = subprocess.check_output(
            ["tmux", "list-panes", "-a", "-F", "#{session_name}:#{window_index}.#{pane_index}\t#{pane_title}"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode()
    except Exception:
        return []
    rows: list[tuple[str, str]] = []
    for raw in out.splitlines():
        if not raw.strip():
            continue
        pane, _, title = raw.partition("\t")
        pane = pane.strip()
        if pane.startswith((f"{SESSION}:", f"{LAB_SESSION}:", f"{DISPATCH_SESSION}:", f"{MULTI_TASK_SESSION}:")):
            rows.append((pane, title.strip()))
    return sorted(rows)


def _pane_visibly_idle(pane: str, tail: str | None = None) -> bool:
    """Compatibility wrapper for graph dispatcher idle-prompt detection.

    `graph_node_dispatcher._pane_visibly_idle` existed in earlier TUI lifecycle
    builds, then the idle check moved into lower-level tail helpers. Pane doctor
    is an operational health command, so it must degrade to conservative local
    detection instead of crashing when that private helper moves.
    """
    helper = getattr(gnd, "_pane_visibly_idle", None)
    if callable(helper):
        return bool(helper(pane))
    text = tail if tail is not None else gnd._pane_tail(pane)
    tail_helper = getattr(gnd, "_tail_has_idle_prompt_footer", None)
    if callable(tail_helper) and tail_helper(text):
        return True
    return bool(re.search(r"❯[\s\u00a0]+Try\s+\"", text))


def _host_role(pane: str, title: str) -> str:
    lower = f"{pane} {title}".lower()
    if pane == f"{SESSION}:0.0" or " pm" in lower or "产品经理" in title:
        return "pm"
    if pane == f"{SESSION}:0.1" or "planner" in lower or "规划者" in title:
        return "planner"
    if pane == f"{SESSION}:0.3" or "evaluator" in lower or "审判官" in title:
        return "evaluator"
    if pane.startswith((f"{LAB_SESSION}:", f"{DISPATCH_SESSION}:", f"{MULTI_TASK_SESSION}:")):
        return "builder"
    if pane == f"{SESSION}:0.2":
        return "builder"
    return "unknown"


def _tail_token_count(tail: str) -> int:
    matches = re.findall(r"([0-9][0-9,]*)\s+tokens\b", tail, re.I)
    if not matches:
        return 0
    try:
        return max(int(item.replace(",", "")) for item in matches)
    except Exception:
        return 0


def _registry(path: Path | None = None) -> PaneHygieneRegistry:
    return PaneHygieneRegistry(str(path or HARNESS_DIR / "run" / "pane-hygiene.json"))


def _lab_state_file() -> Path:
    return HARNESS_DIR / "state" / "parallel-builder-lab.env"


def _read_shell_state(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        key, sep, value = raw.partition("=")
        if not sep or not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
            value = value[1:-1]
        data[key.strip()] = value
    return data


def _lab_model_matrix() -> str:
    state = _read_shell_state(_lab_state_file())
    if state.get("LAB_MODEL_MATRIX"):
        return state["LAB_MODEL_MATRIX"]
    try:
        return subprocess.check_output(
            ["bash", "-lc", f"source {str(HARNESS_DIR / 'lib' / 'harness-config.sh')!r}; solar_lab_builder_matrix"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode().strip()
    except Exception:
        return ""


def _lab_work_dir() -> Path:
    state = _read_shell_state(_lab_state_file())
    raw = state.get("WORK_DIR") or os.environ.get("SOLAR_LAB_WORK_DIR") or str(HARNESS_DIR)
    return Path(raw).expanduser()


def _lab_slot_for_pane(pane: str) -> str:
    match = LAB_PANE_RE.match(pane)
    if not match:
        return ""
    return f"lab-builder-{int(match.group(1)) + 1}"


def _tmux_pane_id(pane: str) -> str:
    try:
        return subprocess.check_output(
            ["tmux", "display-message", "-p", "-t", pane, "#{pane_id}"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode().strip()
    except Exception:
        return ""


def _clear_pane_cooldown(pane: str) -> bool:
    path = HARNESS_DIR / "run" / "graph-dispatch-pane-cooldowns.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        data = {}
    if not isinstance(data, dict) or pane not in data:
        return False
    data.pop(pane, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def _record_respawn(pane: str, before_state: str, after_state: str, *, success: bool, reason: str, extra: dict[str, Any]) -> None:
    try:
        writer = LedgerWriter(
            str(HARNESS_DIR / "run" / "pane-lifecycle-ledger.jsonl"),
            str(HARNESS_DIR / "run" / "pane-lifecycle-ledger.sqlite"),
        )
        writer.record_respawn(
            pane,
            before_state=before_state,
            after_state=after_state,
            success=success,
            reason=reason,
            extra=extra,
        )
    except Exception:
        return


def _ensure_registry_entry(registry: PaneHygieneRegistry, pane: str, role: str, model: str = "") -> dict[str, Any]:
    try:
        entry = registry.ensure_pane(pane, role, model=model or None)
    except Exception:
        return {"state": "missing", "pane_role": role}
    return {
        "state": entry.state.value,
        "pane_role": entry.pane_role,
        "cooldown_until": entry.cooldown_until,
        "cooldown_reason": entry.cooldown_reason,
        "consecutive_fail_count": entry.consecutive_fail_count,
        "respawn_count": entry.respawn_count,
    }


def _desired_hygiene_state(finding: dict[str, Any]) -> str:
    if finding["status"] == "running":
        return "running"
    if finding["status"] == "blocked":
        return "dirty"
    if finding["status"] == "respawn_required":
        return "needs_respawn"
    if finding["status"] in {"cooldown", "runtime_missing"}:
        return "needs_recover"
    return "clean"


def _transition_to(registry: PaneHygieneRegistry, pane: str, target: str, reason: str) -> dict[str, Any]:
    try:
        entry = registry.get_pane_state(pane)
    except Exception as exc:
        return {"ok": False, "reason": f"registry_missing:{exc}"}
    current = entry.state
    desired = PaneState(target)
    if current == desired:
        return {"ok": True, "changed": False, "state": current.value}

    paths: dict[tuple[PaneState, PaneState], list[PaneState]] = {
        (PaneState.clean, PaneState.dirty): [PaneState.running, PaneState.dirty],
        (PaneState.clean, PaneState.needs_recover): [PaneState.running, PaneState.needs_recover],
        (PaneState.clean, PaneState.needs_respawn): [PaneState.running, PaneState.needs_recover, PaneState.needs_respawn],
        (PaneState.running, PaneState.clean): [PaneState.dirty, PaneState.clean],
        (PaneState.running, PaneState.needs_respawn): [PaneState.needs_recover, PaneState.needs_respawn],
        (PaneState.dirty, PaneState.running): [PaneState.clean, PaneState.running],
        (PaneState.dirty, PaneState.needs_respawn): [PaneState.needs_recover, PaneState.needs_respawn],
        (PaneState.cooling, PaneState.clean): [PaneState.dirty, PaneState.clean],
        (PaneState.cooling, PaneState.running): [PaneState.needs_recover, PaneState.running],
        (PaneState.cooling, PaneState.needs_respawn): [PaneState.needs_recover, PaneState.needs_respawn],
        (PaneState.needs_recover, PaneState.clean): [PaneState.running, PaneState.dirty, PaneState.clean],
        (PaneState.needs_respawn, PaneState.clean): [PaneState.running, PaneState.dirty, PaneState.clean],
        (PaneState.needs_respawn, PaneState.dirty): [PaneState.running, PaneState.dirty],
    }
    steps = paths.get((current, desired), [desired])
    applied: list[str] = []
    try:
        for step in steps:
            entry = registry.transition_state(pane, step, reason=reason)
            applied.append(step.value)
        return {"ok": True, "changed": True, "from": current.value, "to": entry.state.value, "steps": applied}
    except (IllegalTransitionError, ValueError) as exc:
        return {"ok": False, "reason": str(exc), "from": current.value, "target": desired.value, "steps": applied}


def diagnose_pane(pane: str, title: str, registry: PaneHygieneRegistry | None = None) -> dict[str, Any]:
    role = _host_role(pane, title)
    reg = registry or _registry()
    hygiene = _ensure_registry_entry(reg, pane, role)
    tail = gnd._pane_tail(pane)
    command = gnd._pane_current_command(pane)
    lease = read_lease(pane) or {}
    cooldown_reason = gnd._pane_cooldown_reason(pane)
    runtime_reason = "" if cooldown_reason else gnd._pane_runtime_unavailable_reason(pane, title)
    unavailable_reason = "" if (cooldown_reason or runtime_reason) else gnd._pane_unavailable_reason(pane)
    tui_busy = gnd._pane_tui_busy(pane)
    token_count = _tail_token_count(tail)
    visibly_idle = _pane_visibly_idle(pane, tail)

    status = "clean"
    reason = "ready"
    action = "none"
    if lease and str(lease.get("expires_at") or "") > _utc_now():
        status, reason, action = "running", "live_lease", "wait"
    elif tui_busy:
        status, reason, action = "running", "tui_busy", "wait"
    elif cooldown_reason:
        status, reason, action = "cooldown", cooldown_reason, "wait_or_recover_when_idle"
    elif token_count >= CONTEXT_TOKEN_RESPAWN_THRESHOLD and visibly_idle:
        status, reason, action = "respawn_required", "idle_huge_context", "mark_needs_respawn"
    elif runtime_reason:
        status, reason, action = "runtime_missing", runtime_reason, "mark_needs_recover"
    elif unavailable_reason:
        status, reason, action = "blocked", unavailable_reason, "mark_dirty"
    elif visibly_idle:
        status, reason, action = "clean", "visible_idle", "mark_clean"

    return {
        "pane": pane,
        "role": role,
        "status": status,
        "reason": reason,
        "recommended_action": action,
        "title": title,
        "command": command,
        "hygiene_state": hygiene.get("state", "missing"),
        "desired_hygiene_state": _desired_hygiene_state({"status": status}),
        "cooldown_reason": cooldown_reason,
        "runtime_reason": runtime_reason,
        "unavailable_reason": unavailable_reason,
        "tui_busy": tui_busy,
        "visibly_idle": visibly_idle,
        "token_count": token_count,
        "lease": {
            "dispatch_id": str(lease.get("dispatch_id") or ""),
            "sprint_id": str(lease.get("sid") or lease.get("sprint_id") or ""),
            "expires_at": str(lease.get("expires_at") or ""),
        } if lease else {},
    }


def diagnose_all() -> dict[str, Any]:
    reg = _registry()
    findings = [diagnose_pane(pane, title, reg) for pane, title in _pane_rows()]
    counts: dict[str, int] = {}
    for item in findings:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {"ok": True, "ts": _utc_now(), "counts": counts, "panes": findings}


def repair_all(*, dry_run: bool = False, include_protected: bool = False) -> dict[str, Any]:
    reg = _registry()
    findings = [diagnose_pane(pane, title, reg) for pane, title in _pane_rows()]
    repairs: list[dict[str, Any]] = []
    for item in findings:
        pane = item["pane"]
        desired = item["desired_hygiene_state"]
        current = item.get("hygiene_state") or "missing"
        cooldown_reason = str(item.get("cooldown_reason") or "")
        stale_idle_recover_cooldown = (
            item.get("status") == "cooldown"
            and cooldown_reason.startswith("pane_recover_cooldown:")
            and (
                "exhausted" in cooldown_reason
                or "clear_gate_failed" in cooldown_reason
                or "assigned_pane_unavailable:pane_title_active_work" in cooldown_reason
            )
            and (item.get("visibly_idle") or "exhausted" in cooldown_reason)
            and not item.get("lease")
            and not item.get("runtime_reason")
            and not item.get("unavailable_reason")
            and not item.get("tui_busy")
        )
        lab_stale_title_active_cooldown = (
            item.get("status") == "cooldown"
            and "assigned_pane_unavailable:pane_title_active_work" in cooldown_reason
            and LAB_PANE_RE.match(pane)
            and not item.get("lease")
        )
        lab_unleased_tui_residue = False
        if (
            item.get("status") == "running"
            and item.get("reason") == "tui_busy"
            and LAB_PANE_RE.match(pane)
            and not item.get("lease")
        ):
            tail = gnd._pane_tail(pane)
            bottom = "\n".join(tail.splitlines()[-40:])
            has_dispatch_prompt = bool(gnd._pane_dispatch_prompt_reason(bottom))
            has_prompt_residue = bool(gnd._pane_current_prompt_has_residue(bottom))
            is_processing = bool(gnd.PANE_PROCESSING_RE.search(bottom))
            lab_unleased_tui_residue = has_prompt_residue or (has_dispatch_prompt and not is_processing)
        if stale_idle_recover_cooldown:
            # A recover cooldown is a protection latch, not work state.  Once a
            # pane is visibly back at an idle prompt with no lease, keeping a
            # more severe registry state permanently starves the dispatcher.
            desired = PaneState.clean.value
        elif lab_stale_title_active_cooldown:
            # A lab worker with no lease but a stale active title/cooldown is
            # not safe to reuse directly. Mark it for controlled respawn so the
            # scheduler does not keep rediscovering the same dead pane forever.
            desired = PaneState.needs_respawn.value
        elif lab_unleased_tui_residue:
            # A lab worker with no lease that is sitting on a live confirmation
            # prompt or unsubmitted input is not doing useful work.  Normal key
            # recovery can concatenate input (for example `yy`) and leave the
            # scheduler stuck forever, so escalate to controlled respawn.
            desired = PaneState.needs_respawn.value
        if current == desired:
            if stale_idle_recover_cooldown and not dry_run:
                _clear_pane_cooldown(pane)
            continue
        if pane in PROTECTED_PANES and not include_protected:
            repairs.append({
                "pane": pane,
                "from": current,
                "to": desired,
                "reason": item["reason"],
                "dry_run": dry_run,
                "skipped": True,
                "skip_reason": "protected_pane",
            })
            continue
        preserve_severe_state = current in {
            PaneState.cooling.value,
            PaneState.needs_recover.value,
            PaneState.needs_respawn.value,
        }
        recovered_to_clean = (
            desired == PaneState.clean.value
            and (item.get("status") == "clean" or stale_idle_recover_cooldown)
            and not item.get("lease")
            and (not item.get("cooldown_reason") or stale_idle_recover_cooldown)
            and not item.get("runtime_reason")
            and not item.get("unavailable_reason")
            and not item.get("tui_busy")
        )
        if preserve_severe_state and not recovered_to_clean and STATE_SEVERITY.get(current, 0) > STATE_SEVERITY.get(desired, 0):
            repairs.append({
                "pane": pane,
                "from": current,
                "to": desired,
                "reason": item["reason"],
                "dry_run": dry_run,
                "skipped": True,
                "skip_reason": "existing_state_more_severe",
            })
            continue
        repair = {
            "pane": pane,
            "from": current,
            "to": desired,
            "reason": item["reason"],
            "dry_run": dry_run,
        }
        if not dry_run:
            repair["result"] = _transition_to(reg, pane, desired, f"pane_doctor:{item['reason']}")
            if stale_idle_recover_cooldown and repair["result"].get("ok"):
                repair["cooldown_cleared"] = _clear_pane_cooldown(pane)
        repairs.append(repair)
    return {"ok": True, "ts": _utc_now(), "dry_run": dry_run, "repairs": repairs, "panes": findings}


def _lab_respawn_candidate(item: dict[str, Any]) -> tuple[bool, str]:
    pane = item["pane"]
    if not LAB_PANE_RE.match(pane):
        return False, "not_lab_builder_pane"
    if item.get("lease"):
        return False, "live_lease"
    if item.get("hygiene_state") != PaneState.needs_respawn.value:
        return False, f"hygiene_state_not_needs_respawn:{item.get('hygiene_state') or 'missing'}"
    return True, "needs_respawn"


def respawn_lab(*, dry_run: bool = False, max_items: int = 1, pane_filter: str = "") -> dict[str, Any]:
    """Safely respawn only lab builder panes marked needs_respawn.

    This is deliberately narrower than ensure_parallel_builder_lab(): it never
    respawns all panes, never touches main protected panes, and refuses to act
    when a live lease is present.  A pane already marked needs_respawn is
    considered unsafe to trust even if its TUI scrollback still looks busy.
    """
    reg = _registry()
    rows = _pane_rows()
    findings = [diagnose_pane(pane, title, reg) for pane, title in rows]
    actions: list[dict[str, Any]] = []
    selected = 0
    matrix = _lab_model_matrix()
    work_dir = _lab_work_dir()
    for item in findings:
        pane = item["pane"]
        if pane_filter and pane != pane_filter:
            continue
        ok, reason = _lab_respawn_candidate(item)
        action = {
            "pane": pane,
            "dry_run": dry_run,
            "eligible": ok,
            "reason": reason,
            "before_state": item.get("hygiene_state") or "missing",
            "status": item.get("status"),
        }
        if not ok:
            if LAB_PANE_RE.match(pane) or pane_filter:
                actions.append(action | {"skipped": True})
            continue
        if selected >= max(0, max_items):
            actions.append(action | {"skipped": True, "skip_reason": "max_items_reached"})
            continue
        selected += 1
        slot = _lab_slot_for_pane(pane)
        pane_id = _tmux_pane_id(pane)
        if not pane_id:
            actions.append(action | {"skipped": True, "skip_reason": "tmux_pane_id_missing"})
            continue
        respawn_cmd = (
            f"TMUX_PANE={pane_id} "
            f"SOLAR_BUILDER_SLOT={slot} "
            f"SOLAR_LAB_BUILDER_MODEL_MATRIX={matrix} "
            f"SOLAR_CLAUDE_BYPASS=1 "
            f"bash {str(HARNESS_DIR / 'pane-launcher.sh')!r} lab-builder {str(work_dir)!r}"
        )
        action.update({"slot": slot, "pane_id": pane_id, "work_dir": str(work_dir), "model_matrix": matrix})
        if dry_run:
            actions.append(action | {"skipped": False, "command": respawn_cmd})
            continue
        before_state = action["before_state"]
        try:
            subprocess.run(["tmux", "respawn-pane", "-k", "-t", pane, respawn_cmd], check=True, timeout=10)
            trans = _transition_to(reg, pane, PaneState.running.value, "pane_doctor:lab_respawn_completed")
            cooldown_cleared = _clear_pane_cooldown(pane)
            _record_respawn(
                pane,
                before_state,
                PaneState.running.value,
                success=bool(trans.get("ok")),
                reason="pane_doctor_lab_respawn",
                extra={"slot": slot, "cooldown_cleared": cooldown_cleared, "work_dir": str(work_dir)},
            )
            actions.append(action | {
                "skipped": False,
                "ok": bool(trans.get("ok")),
                "transition": trans,
                "cooldown_cleared": cooldown_cleared,
            })
        except Exception as exc:
            _record_respawn(
                pane,
                before_state,
                before_state,
                success=False,
                reason="pane_doctor_lab_respawn_failed",
                extra={"error": str(exc), "slot": slot, "work_dir": str(work_dir)},
            )
            actions.append(action | {"skipped": False, "ok": False, "error": str(exc)})
    return {
        "ok": True,
        "ts": _utc_now(),
        "dry_run": dry_run,
        "max_items": max_items,
        "pane_filter": pane_filter,
        "actions": actions,
        "panes": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="pane_doctor.py")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status")
    p_repair = sub.add_parser("repair")
    p_repair.add_argument("--dry-run", action="store_true")
    p_repair.add_argument("--include-protected", action="store_true")
    p_respawn = sub.add_parser("respawn-lab")
    p_respawn.add_argument("--dry-run", action="store_true")
    p_respawn.add_argument("--max-items", type=int, default=1)
    p_respawn.add_argument("--pane", default="")
    args = parser.parse_args()

    if args.cmd in {None, "status"}:
        result = diagnose_all()
    elif args.cmd == "repair":
        result = repair_all(dry_run=args.dry_run, include_protected=args.include_protected)
    elif args.cmd == "respawn-lab":
        result = respawn_lab(dry_run=args.dry_run, max_items=args.max_items, pane_filter=args.pane)
    else:
        parser.print_help()
        return 1
    print(_json(result))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
