#!/usr/bin/env python3
"""autopilot.py — S6 Control Plane: three-state pane autopilot + deadlock detection.

Pane states (per pane_lease.py):
  no_pane  — pane doesn't exist; clear assignment + emit event
  busy     — active live lease; wait (do NOT reclaim)
  dead     — pane exists, lease expired; eligible for reclaim or queue drain

Synthetic deadlock scenario handled:
  - Pane has a live lease (reports busy) BUT captures show no Claude Code prompt
    activity for > DEADLOCK_STALL_SEC seconds
  - Autopilot classifies as STALLED rather than busy; releases lease + re-queues

Four fault classes diagnosed per dispatch.md:
  handoff_stall   — sprint in reviewing for > STALL_SEC, no eval dispatched
  eval_stall      — sprint in reviewing, eval pane has stale lease, no new output
  dispatch_backlog— task queue depth > BACKLOG_THRESHOLD, no free workers
  hook_failure    — quarantine inbox has entries that haven't been resolved

CLI:
  python3 autopilot.py scan   [--sprint SID]      # scan all pending queues + panes
  python3 autopilot.py status [--sprint SID]      # current state per pane
  python3 autopilot.py resolve-deadlock --pane PANE --sprint SID --dispatch-id DID
  python3 autopilot.py fault-report [--sprint SID]
  python3 autopilot.py drain-queue --sprint SID   # pop queued tasks onto free workers
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))

# Pull in sibling modules from lib/
sys.path.insert(0, str(HARNESS_DIR / "lib"))
from pane_lease import pane_state, release, reap, list_leases  # noqa: E402
from task_queue import next_free_worker, enqueue, pop, depth   # noqa: E402
from graph_node_dispatcher import dispatch_queue_item          # noqa: E402
from context_projection import ContextProjection               # noqa: E402
from runtime_doctor import doctor_all, doctor_sprint            # noqa: E402
from solar_state_db import (                                    # noqa: E402
    open_state_db, init_db, emit_event as db_emit_event,
    get_pending_tasks, get_free_workers, release_task,
)

DEADLOCK_STALL_SEC = int(os.environ.get("AUTOPILOT_DEADLOCK_STALL_SEC", "300"))
STALL_SEC = int(os.environ.get("AUTOPILOT_STALL_SEC", "900"))
BACKLOG_THRESHOLD = int(os.environ.get("AUTOPILOT_BACKLOG_THRESHOLD", "3"))
QUARANTINE_DIR = HARNESS_DIR / "run" / "quarantine"
EVENTS_JSONL = HARNESS_DIR / "run" / "dispatch-ledger.jsonl"
RUNTIME_REPAIR_PRIORITY = int(os.environ.get("AUTOPILOT_RUNTIME_REPAIR_PRIORITY", "92"))


def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _seconds_since(ts: str) -> float:
    try:
        t = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        return (datetime.datetime.utcnow() - t).total_seconds()
    except Exception:
        return 0.0


# ── pane activity detection ───────────────────────────────────────────────────

def _capture_pane(pane: str) -> str:
    """Capture last 20 lines of pane output."""
    try:
        out = subprocess.check_output(
            ["tmux", "capture-pane", "-t", pane, "-p"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode(errors="replace")
        return "\n".join(out.splitlines()[-20:])
    except Exception:
        return ""


def _pane_has_active_prompt(pane: str) -> bool:
    """Return True if pane shows a live Claude Code prompt (❯ or spinner)."""
    capture = _capture_pane(pane)
    indicators = ["❯", "⏵", "… ", "Esc to interrupt", "auto accept edits"]
    return any(ind in capture for ind in indicators)


# ── stall detection ───────────────────────────────────────────────────────────

def _is_stalled(lease: dict) -> bool:
    """Check if a 'busy' lease is actually stalled (deadlock candidate)."""
    acquired_at = lease.get("acquired_at", "")
    if not acquired_at:
        return False
    age = _seconds_since(acquired_at)
    if age < DEADLOCK_STALL_SEC:
        return False
    pane = lease.get("pane", "")
    if not pane:
        return True
    return not _pane_has_active_prompt(pane)


# ── scan ─────────────────────────────────────────────────────────────────────

def scan(sprint_id: "str | None" = None) -> list[dict]:
    """Scan panes + queues; return action items."""
    conn = open_state_db()
    init_db(conn)
    actions: list[dict] = []

    leases = list_leases()
    for lease in leases:
        pane = lease.get("pane", "")
        sid = lease.get("sprint_id", sprint_id or "unknown")
        did = lease.get("dispatch_id", "")
        if sprint_id and sid != sprint_id:
            continue

        state = pane_state(pane)
        if state == "no_pane":
            actions.append({
                "action": "reclaim_no_pane",
                "pane": pane, "sprint_id": sid, "dispatch_id": did,
            })
            db_emit_event(conn, sid, "pane_gone", payload={"pane": pane, "dispatch_id": did})

        elif state == "busy" and _is_stalled(lease):
            actions.append({
                "action": "resolve_deadlock",
                "pane": pane, "sprint_id": sid, "dispatch_id": did,
                "stall_sec": _seconds_since(lease.get("acquired_at", "")),
            })
            db_emit_event(conn, sid, "deadlock_detected",
                          payload={"pane": pane, "stall_sec": _seconds_since(lease.get("acquired_at", ""))})

    # Check for unresolved quarantine entries (hook_failure fault class)
    if QUARANTINE_DIR.exists():
        inbox = QUARANTINE_DIR / "inbox.jsonl"
        if inbox.exists():
            unresolved: list[dict] = []
            for line in inbox.read_text().splitlines():
                try:
                    entry = json.loads(line)
                    if entry.get("action") not in ("resolved",):
                        unresolved.append(entry)
                except Exception:
                    pass
            if unresolved:
                actions.append({
                    "action": "hook_failure",
                    "count": len(unresolved),
                    "sample": unresolved[:3],
                    "inbox": str(inbox),
                })

    # Runtime doctor debt: long-running reliability issues are not just UI
    # warnings; they must become repairable autopilot actions.
    actions.extend(runtime_debt_actions(sprint_id=sprint_id, repair=False).get("actions", []))

    return actions


# ── runtime debt detection/repair ─────────────────────────────────────────────

def _repair_intent(kind: str, sid: str, detail: str) -> str:
    digest = hashlib.sha256(f"{kind}:{sid}:{detail}".encode()).hexdigest()[:12]
    return f"runtime_repair|kind={kind}|sid={sid}|hash={digest}"


def _enqueue_runtime_repair(sid: str, kind: str, detail: dict) -> dict:
    intent = _repair_intent(kind, sid, json.dumps(detail, sort_keys=True))
    payload = {
        "type": "runtime_repair",
        "kind": kind,
        "sprint_id": sid,
        "detail": detail,
        "created_at": _now(),
        "source": "autopilot.runtime_debt",
        "instruction": (
            "Investigate and repair runtime debt without fabricating success. "
            "Use session log, runtime doctor, and process audit evidence."
        ),
    }
    return enqueue(sid, intent, RUNTIME_REPAIR_PRIORITY, payload)


def _record_context_repair(sid: str) -> dict:
    cp = ContextProjection(sid, harness_dir=str(HARNESS_DIR))
    return cp.record_context_injected(
        query=sid,
        policy_name="autopilot-repair",
        budget_tokens=1200,
        actor="autopilot",
        source="autopilot_runtime_repair",
    )


def _runtime_debt_from_report(report: dict) -> list[dict]:
    sprints = report.get("sprints") if isinstance(report.get("sprints"), list) else [report]
    actions: list[dict] = []
    for sp in sprints:
        sid = sp.get("sprint_id") or sp.get("sid")
        if not sid:
            continue
        checks = sp.get("checks") or {}

        event_health = checks.get("event_log_health") or {}
        if event_health.get("bad_lines") or event_health.get("seq_gaps"):
            actions.append({
                "action": "runtime_repair_queue",
                "kind": "event_log_integrity",
                "sprint_id": sid,
                "detail": {
                    "bad_lines": event_health.get("bad_lines", 0),
                    "seq_gaps": event_health.get("seq_gaps", []),
                    "message": event_health.get("message", ""),
                },
            })

        context_runtime = checks.get("context_runtime") or {}
        if context_runtime.get("ok") and context_runtime.get("warn") and not context_runtime.get("context_injected_count"):
            actions.append({
                "action": "runtime_context_repair",
                "kind": "missing_context_event",
                "sprint_id": sid,
                "detail": {
                    "real_recall_hit_count": context_runtime.get("real_recall_hit_count", 0),
                    "message": context_runtime.get("message", ""),
                },
            })

        model_runtime = checks.get("model_call_runtime") or {}
        pending_model = model_runtime.get("pending_dispatch_ids") or []
        if pending_model:
            actions.append({
                "action": "runtime_repair_queue",
                "kind": "pending_model_call",
                "sprint_id": sid,
                "detail": {
                    "pending_dispatch_ids": pending_model,
                    "message": model_runtime.get("message", ""),
                },
            })

        process = checks.get("process_audit") or {}
        audit = process.get("audit") or {}
        side = audit.get("side_effect_boundaries") or {}
        hard_risks = process.get("hard_risks") or []
        if hard_risks:
            actions.append({
                "action": "runtime_repair_queue",
                "kind": "process_audit_risk",
                "sprint_id": sid,
                "detail": {
                    "risks": hard_risks,
                    "unstarted_commands": side.get("unstarted_commands", []),
                    "started_without_terminal": side.get("started_without_terminal", []),
                    "terminal_without_start": side.get("terminal_without_start", []),
                    "message": process.get("message", ""),
                },
            })

    return actions


def runtime_debt_actions(sprint_id: "str | None" = None, repair: bool = False) -> dict:
    """Detect runtime doctor warnings/errors and optionally repair/queue them."""
    report = doctor_sprint(sprint_id) if sprint_id else doctor_all(active_only=True)
    actions = _runtime_debt_from_report(report)
    repaired: list[dict] = []
    if repair:
        conn = open_state_db()
        init_db(conn)
        for action in actions:
            sid = action["sprint_id"]
            kind = action["kind"]
            if action["action"] == "runtime_context_repair":
                result = _record_context_repair(sid)
                db_emit_event(conn, sid, "runtime_context_repaired", payload=result)
                repaired.append({"action": action, "result": result, "mode": "record_context_event"})
            else:
                result = _enqueue_runtime_repair(sid, kind, action.get("detail") or {})
                db_emit_event(conn, sid, "runtime_repair_queued", payload={"kind": kind, "queue": result})
                repaired.append({"action": action, "result": result, "mode": "queued"})
    return {
        "ok": True,
        "sprint_id": sprint_id,
        "count": len(actions),
        "actions": actions,
        "repaired": repaired,
        "repaired_count": len(repaired),
        "scanned_at": _now(),
    }


# ── fault report ─────────────────────────────────────────────────────────────

def fault_report(sprint_id: "str | None" = None) -> dict:
    """Diagnose four fault classes; return structured report."""
    conn = open_state_db()
    init_db(conn)
    faults: list[dict] = []

    # handoff_stall: sprint reviewing for too long
    sprint_dir = HARNESS_DIR / "sprints"
    for sf in sorted(sprint_dir.glob("*.status.json")):
        try:
            data = json.loads(sf.read_text())
            sid = data.get("sprint_id", data.get("id", sf.stem.replace(".status", "")))
            if sprint_id and sid != sprint_id:
                continue
            if data.get("status") == "reviewing":
                updated = data.get("updated_at", "")
                age = _seconds_since(updated)
                if age > STALL_SEC:
                    faults.append({
                        "fault": "handoff_stall",
                        "sprint_id": sid,
                        "stall_sec": age,
                        "updated_at": updated,
                    })
        except Exception:
            pass

    # dispatch_backlog: deep queue + no free workers
    free_workers = get_free_workers(conn)
    for qf in sorted((HARNESS_DIR / "run" / "queue").glob("*.jsonl")):
        sid = qf.stem
        if sprint_id and sid != sprint_id:
            continue
        d = depth(sid)
        if d >= BACKLOG_THRESHOLD and not free_workers:
            faults.append({
                "fault": "dispatch_backlog",
                "sprint_id": sid,
                "queue_depth": d,
                "free_workers": 0,
            })

    # hook_failure: unresolved quarantine entries
    inbox = QUARANTINE_DIR / "inbox.jsonl"
    if inbox.exists():
        unresolved: list[dict] = []
        for line in inbox.read_text().splitlines():
            try:
                e = json.loads(line)
                if sprint_id and e.get("sid") != sprint_id:
                    continue
                if e.get("action") not in ("resolved",):
                    unresolved.append(e)
            except Exception:
                pass
        if unresolved:
            faults.append({
                "fault": "hook_failure",
                "unresolved_count": len(unresolved),
                "sample": unresolved[:3],
            })

    # deadlock (stalled leases)
    stalled = [a for a in scan(sprint_id) if a.get("action") == "resolve_deadlock"]
    faults.extend(stalled)

    runtime_debt = runtime_debt_actions(sprint_id=sprint_id, repair=False)
    for item in runtime_debt.get("actions", []):
        faults.append({
            "fault": "runtime_debt",
            "sprint_id": item.get("sprint_id"),
            "kind": item.get("kind"),
            "detail": item.get("detail"),
        })

    return {
        "ok": True,
        "sprint_id": sprint_id,
        "fault_count": len(faults),
        "faults": faults,
        "scanned_at": _now(),
    }


# ── resolve deadlock ──────────────────────────────────────────────────────────

def resolve_deadlock(pane: str, sprint_id: str, dispatch_id: str) -> dict:
    """Release stalled lease; re-enqueue the sprint's pending work."""
    result = release(pane, dispatch_id, reason="deadlock_resolved")
    conn = open_state_db()
    init_db(conn)
    db_emit_event(conn, sprint_id, "deadlock_resolved",
                  payload={"pane": pane, "dispatch_id": dispatch_id, "release": result})

    # Re-queue so coordinator picks it up next cycle
    q_result = enqueue(sprint_id, f"deadlock_requeue|pane={pane}|did={dispatch_id}", priority=80)
    return {
        "ok": True,
        "pane": pane,
        "sprint_id": sprint_id,
        "lease_released": result,
        "requeued": q_result,
    }


# ── drain queue onto free workers ─────────────────────────────────────────────

def drain_queue(sprint_id: str) -> dict:
    """Pop queued tasks and log them as ready-to-dispatch; returns count."""
    dispatched: list[dict] = []
    while True:
        item = pop(sprint_id)
        if item is None:
            break
        if "graph_node|" in item.get("intent", "") or (item.get("payload") or {}).get("node"):
            result = dispatch_queue_item(item, dry_run=bool(os.environ.get("SOLAR_COORD_DRY_RUN")), ttl=900)
            conn = open_state_db()
            init_db(conn)
            db_emit_event(conn, sprint_id, "graph_queue_drain_dispatch", payload=result)
            dispatched.append({"item": item, "status": "graph_dispatched" if result.get("ok") else "graph_requeued", "result": result})
            if not result.get("ok"):
                break
            continue
        pane = next_free_worker(sprint_id)
        conn = open_state_db()
        init_db(conn)
        if pane:
            db_emit_event(conn, sprint_id, "queue_drain_dispatch",
                          payload={"item_id": item.get("id"), "pane": pane})
            dispatched.append({"item": item, "pane": pane, "status": "ready"})
        else:
            # Put it back by re-enqueuing
            enqueue(sprint_id, item.get("intent", ""), item.get("priority", 50))
            dispatched.append({"item": item, "pane": None, "status": "requeued"})
            break
    return {"ok": True, "sprint_id": sprint_id, "dispatched": len(dispatched), "items": dispatched}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(prog="autopilot.py")
    sub = ap.add_subparsers(dest="cmd")

    sc = sub.add_parser("scan")
    sc.add_argument("--sprint")

    st = sub.add_parser("status")
    st.add_argument("--sprint")

    rd = sub.add_parser("resolve-deadlock")
    rd.add_argument("--pane", required=True)
    rd.add_argument("--sprint", required=True)
    rd.add_argument("--dispatch-id", required=True)

    fr = sub.add_parser("fault-report")
    fr.add_argument("--sprint")

    dq = sub.add_parser("drain-queue")
    dq.add_argument("--sprint", required=True)

    rt = sub.add_parser("runtime-debt")
    rt.add_argument("--sprint")
    rt.add_argument("--repair", action="store_true")

    args = ap.parse_args()

    if args.cmd == "scan":
        actions = scan(getattr(args, "sprint", None))
        print(json.dumps({"ok": True, "actions": actions, "count": len(actions)}))

    elif args.cmd == "status":
        leases = list_leases()
        pane_states = []
        for lease in leases:
            pane = lease.get("pane", "")
            if getattr(args, "sprint", None) and lease.get("sprint_id") != args.sprint:
                continue
            state = pane_state(pane)
            stalled = state == "busy" and _is_stalled(lease)
            pane_states.append({
                "pane": pane,
                "state": state,
                "stalled": stalled,
                "sprint_id": lease.get("sprint_id"),
                "expires_at": lease.get("expires_at"),
            })
        print(json.dumps({"ok": True, "panes": pane_states}))

    elif args.cmd == "resolve-deadlock":
        result = resolve_deadlock(args.pane, args.sprint, args.dispatch_id)
        print(json.dumps(result))

    elif args.cmd == "fault-report":
        report = fault_report(getattr(args, "sprint", None))
        print(json.dumps(report, indent=2))

    elif args.cmd == "drain-queue":
        result = drain_queue(args.sprint)
        print(json.dumps(result))

    elif args.cmd == "runtime-debt":
        result = runtime_debt_actions(getattr(args, "sprint", None), repair=bool(args.repair))
        print(json.dumps(result, indent=2))

    else:
        ap.print_help()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
