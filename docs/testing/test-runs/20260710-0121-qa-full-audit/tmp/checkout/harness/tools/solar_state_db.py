#!/usr/bin/env python3
"""solar_state_db.py — S6 Control Plane: durable SQLite state for sprint tasks.

DB path: $HARNESS_DIR/run/state.db  (separate from ~/.solar/solar.db)

Tables:
  tasks          sprint slices with lifecycle status + gate tracking
  assignments    pane→task assignments (who is working on what)
  leases         pane lease mirror (Python-native; bash pane-lease.sh is authoritative)
  events         immutable event log (append-only)
  artifacts      output files registered per task
  capabilities   worker/pane capability declarations

CLI:
  python3 solar_state_db.py init
  python3 solar_state_db.py task-upsert  --sprint SID --slice S0 --status pending
  python3 solar_state_db.py task-status  --sprint SID [--slice S0]
  python3 solar_state_db.py gate-pass    --sprint SID --gate G0
  python3 solar_state_db.py assign       --sprint SID --slice S0 --pane PANE
  python3 solar_state_db.py release      --sprint SID --slice S0
  python3 solar_state_db.py emit-event   --sprint SID --event EVT [--payload JSON]
  python3 solar_state_db.py workers
  python3 solar_state_db.py parent-check --sprint SID
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
STATE_DB = Path(os.environ.get("HARNESS_STATE_DB", str(HARNESS_DIR / "run" / "state.db")))

# ── connection ────────────────────────────────────────────────────────────────

def open_state_db(path: "Path | None" = None) -> sqlite3.Connection:
    db = path or STATE_DB
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_id   TEXT NOT NULL,
    slice_id    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    gate        TEXT,
    gate_passed INTEGER NOT NULL DEFAULT 0,
    blocked_by  TEXT,
    priority    INTEGER NOT NULL DEFAULT 50,
    assigned_to TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE(sprint_id, slice_id)
);

CREATE TABLE IF NOT EXISTS assignments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_id   TEXT NOT NULL,
    slice_id    TEXT NOT NULL,
    pane        TEXT NOT NULL,
    dispatch_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    released_at TEXT,
    release_reason TEXT
);

CREATE TABLE IF NOT EXISTS leases (
    pane        TEXT PRIMARY KEY,
    sprint_id   TEXT,
    dispatch_id TEXT,
    acquired_at TEXT,
    expires_at  TEXT,
    status      TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_id   TEXT NOT NULL,
    slice_id    TEXT,
    event_type  TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'autopilot',
    payload     TEXT,
    ts          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_id     TEXT NOT NULL,
    slice_id      TEXT,
    path          TEXT NOT NULL,
    artifact_type TEXT,
    sha256        TEXT,
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capabilities (
    pane        TEXT NOT NULL,
    capability  TEXT NOT NULL,
    level       INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (pane, capability)
);

CREATE INDEX IF NOT EXISTS idx_tasks_sprint  ON tasks(sprint_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status  ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_events_sprint ON events(sprint_id, ts);
CREATE INDEX IF NOT EXISTS idx_asgn_pane     ON assignments(pane, released_at);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


# ── helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def task_upsert(conn: sqlite3.Connection, sprint_id: str, slice_id: str,
                status: str = "pending", gate: "str | None" = None,
                blocked_by: "list[str] | None" = None,
                priority: int = 50) -> None:
    now = _now()
    blocked_json = json.dumps(blocked_by) if blocked_by else None
    conn.execute("""
        INSERT INTO tasks (sprint_id, slice_id, status, gate, blocked_by, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(sprint_id, slice_id) DO UPDATE SET
            status     = excluded.status,
            gate       = COALESCE(excluded.gate, gate),
            blocked_by = COALESCE(excluded.blocked_by, blocked_by),
            priority   = excluded.priority,
            updated_at = excluded.updated_at
    """, (sprint_id, slice_id, status, gate, blocked_json, priority, now, now))
    conn.commit()


# Gate → owning slice mapping (plan.md §0)
_GATE_SLICE: dict[str, str] = {
    "G0": "S0", "G2": "S1", "G3": "S1", "G4": "S2",
    "G5": "S3", "G6": "S6", "A10": "S4", "A9": "S5", "G7": "S7",
}


def gate_pass(conn: sqlite3.Connection, sprint_id: str, gate: str) -> "list[str]":
    """Mark gate passed; return slice_ids now unblocked."""
    now = _now()
    conn.execute(
        "UPDATE tasks SET gate_passed=1, updated_at=? WHERE sprint_id=? AND gate=?",
        (now, sprint_id, gate)
    )
    unlocked_slice = _GATE_SLICE.get(gate)
    unblocked: list[str] = []
    if unlocked_slice:
        rows = conn.execute(
            "SELECT slice_id, blocked_by FROM tasks WHERE sprint_id=? AND status='blocked'",
            (sprint_id,)
        ).fetchall()
        for row in rows:
            blockers: list[str] = json.loads(row["blocked_by"] or "[]")
            if unlocked_slice in blockers:
                new_blockers = [b for b in blockers if b != unlocked_slice]
                if not new_blockers:
                    conn.execute(
                        "UPDATE tasks SET status='pending', blocked_by=NULL, updated_at=? WHERE sprint_id=? AND slice_id=?",
                        (now, sprint_id, row["slice_id"])
                    )
                    unblocked.append(row["slice_id"])
                else:
                    conn.execute(
                        "UPDATE tasks SET blocked_by=?, updated_at=? WHERE sprint_id=? AND slice_id=?",
                        (json.dumps(new_blockers), now, sprint_id, row["slice_id"])
                    )
    conn.commit()
    return unblocked


def assign_task(conn: sqlite3.Connection, sprint_id: str, slice_id: str,
                pane: str, dispatch_id: str) -> None:
    now = _now()
    conn.execute(
        "UPDATE tasks SET status='dispatched', assigned_to=?, updated_at=? WHERE sprint_id=? AND slice_id=?",
        (pane, now, sprint_id, slice_id)
    )
    conn.execute(
        "INSERT INTO assignments (sprint_id, slice_id, pane, dispatch_id, acquired_at) VALUES (?,?,?,?,?)",
        (sprint_id, slice_id, pane, dispatch_id, now)
    )
    conn.commit()


def release_task(conn: sqlite3.Connection, sprint_id: str, slice_id: str,
                 reason: str = "explicit") -> None:
    now = _now()
    conn.execute(
        "UPDATE assignments SET released_at=?, release_reason=? WHERE sprint_id=? AND slice_id=? AND released_at IS NULL",
        (now, reason, sprint_id, slice_id)
    )
    conn.execute(
        "UPDATE tasks SET status='pending', assigned_to=NULL, updated_at=? WHERE sprint_id=? AND slice_id=?",
        (now, sprint_id, slice_id)
    )
    conn.commit()


def emit_event(conn: sqlite3.Connection, sprint_id: str, event_type: str,
               actor: str = "autopilot", payload: "dict | None" = None,
               slice_id: "str | None" = None) -> None:
    conn.execute(
        "INSERT INTO events (sprint_id, slice_id, event_type, actor, payload, ts) VALUES (?,?,?,?,?,?)",
        (sprint_id, slice_id, event_type, actor, json.dumps(payload) if payload else None, _now())
    )
    conn.commit()


def get_pending_tasks(conn: sqlite3.Connection,
                      sprint_id: "str | None" = None) -> "list[sqlite3.Row]":
    if sprint_id:
        return conn.execute(
            "SELECT * FROM tasks WHERE sprint_id=? AND status='pending' ORDER BY priority DESC, id ASC",
            (sprint_id,)
        ).fetchall()
    return conn.execute(
        "SELECT * FROM tasks WHERE status='pending' ORDER BY priority DESC, id ASC"
    ).fetchall()


def get_free_workers(conn: sqlite3.Connection) -> "list[str]":
    """Return pane IDs with no active assignment and no live pane-lease."""
    busy = {row[0] for row in conn.execute(
        "SELECT DISTINCT pane FROM assignments WHERE released_at IS NULL"
    ).fetchall()}
    lease_dir = HARNESS_DIR / "run" / "pane-leases"
    now = _now()
    leased: set[str] = set()
    if lease_dir.exists():
        for lf in lease_dir.glob("*.json"):
            try:
                data = json.loads(lf.read_text())
                if data.get("expires_at", "") > now:
                    leased.add(data.get("pane", ""))
            except Exception:
                pass
    all_builders = _discover_builder_panes()
    return [p for p in all_builders if p not in busy and p not in leased]


def _discover_builder_panes() -> "list[str]":
    try:
        out = subprocess.check_output(
            ["tmux", "list-panes", "-a",
             "-F", "#{session_name}:#{window_index}.#{pane_index}"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode()
        return [p.strip() for p in out.splitlines() if p.strip()]
    except Exception:
        return []


def parent_check(conn: sqlite3.Connection, sprint_id: str) -> dict:
    """Check whether all registered slices for sprint_id have passed."""
    rows = conn.execute(
        "SELECT slice_id, status, gate, gate_passed FROM tasks WHERE sprint_id=?",
        (sprint_id,)
    ).fetchall()
    if not rows:
        return {"ready": False, "reason": "no_tasks_registered", "sprint_id": sprint_id}
    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "passed")
    open_slices = [r["slice_id"] for r in rows if r["status"] not in ("passed",)]
    failed = [r["slice_id"] for r in rows if r["status"] == "failed"]
    return {
        "sprint_id": sprint_id,
        "total": total,
        "passed": passed,
        "open": open_slices,
        "failed": failed,
        "ready": passed == total and not failed,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(prog="solar_state_db.py")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("init")

    tu = sub.add_parser("task-upsert")
    tu.add_argument("--sprint", required=True)
    tu.add_argument("--slice", required=True)
    tu.add_argument("--status", default="pending")
    tu.add_argument("--gate")
    tu.add_argument("--blocked-by", nargs="*")
    tu.add_argument("--priority", type=int, default=50)

    ts = sub.add_parser("task-status")
    ts.add_argument("--sprint", required=True)
    ts.add_argument("--slice")

    gp = sub.add_parser("gate-pass")
    gp.add_argument("--sprint", required=True)
    gp.add_argument("--gate", required=True)

    asgn = sub.add_parser("assign")
    asgn.add_argument("--sprint", required=True)
    asgn.add_argument("--slice", required=True)
    asgn.add_argument("--pane", required=True)
    asgn.add_argument("--dispatch-id", required=True)

    rel = sub.add_parser("release")
    rel.add_argument("--sprint", required=True)
    rel.add_argument("--slice", required=True)
    rel.add_argument("--reason", default="explicit")

    ee = sub.add_parser("emit-event")
    ee.add_argument("--sprint", required=True)
    ee.add_argument("--event", required=True)
    ee.add_argument("--slice")
    ee.add_argument("--payload")
    ee.add_argument("--actor", default="autopilot")

    sub.add_parser("workers")

    pc = sub.add_parser("parent-check")
    pc.add_argument("--sprint", required=True)

    args = ap.parse_args()
    conn = open_state_db()
    init_db(conn)

    if args.cmd == "init":
        print(json.dumps({"ok": True, "db": str(STATE_DB)}))

    elif args.cmd == "task-upsert":
        task_upsert(conn, args.sprint, args.slice, args.status,
                    args.gate, args.blocked_by, args.priority)
        print(json.dumps({"ok": True}))

    elif args.cmd == "task-status":
        if args.slice:
            row = conn.execute(
                "SELECT * FROM tasks WHERE sprint_id=? AND slice_id=?",
                (args.sprint, args.slice)
            ).fetchone()
            print(json.dumps(dict(row) if row else {"error": "not_found"}))
        else:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE sprint_id=? ORDER BY id",
                (args.sprint,)
            ).fetchall()
            print(json.dumps([dict(r) for r in rows]))

    elif args.cmd == "gate-pass":
        unblocked = gate_pass(conn, args.sprint, args.gate)
        emit_event(conn, args.sprint, "gate_passed",
                   payload={"gate": args.gate, "unblocked": unblocked})
        print(json.dumps({"ok": True, "gate": args.gate, "unblocked": unblocked}))

    elif args.cmd == "assign":
        assign_task(conn, args.sprint, args.slice, args.pane, args.dispatch_id)
        print(json.dumps({"ok": True}))

    elif args.cmd == "release":
        release_task(conn, args.sprint, args.slice, args.reason)
        print(json.dumps({"ok": True}))

    elif args.cmd == "emit-event":
        payload = json.loads(args.payload) if args.payload else None
        emit_event(conn, args.sprint, args.event, args.actor, payload, args.slice)
        print(json.dumps({"ok": True}))

    elif args.cmd == "workers":
        free = get_free_workers(conn)
        print(json.dumps({"ok": True, "free_workers": free, "count": len(free)}))

    elif args.cmd == "parent-check":
        result = parent_check(conn, args.sprint)
        print(json.dumps(result))

    else:
        ap.print_help()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
