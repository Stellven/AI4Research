#!/usr/bin/env python3
"""task_queue.py — S6 Control Plane: Python task queue with worker selection.

Prevents single-builder squeeze: iterates all available builder panes,
skips busy ones, queues tasks explicitly when no free worker is found.

Queue storage: $HARNESS_DIR/run/queue/<sprint_id>.jsonl  (same location as queue.sh)

CLI:
  python3 task_queue.py enqueue --sprint SID --intent INTENT [--priority N] [--payload JSON]
  python3 task_queue.py enqueue-node --sprint SID --node-id S1 --payload JSON [--priority N]
  python3 task_queue.py enqueue --sprint SID --slice S1 [--priority N]
  python3 task_queue.py pop     [--sprint SID]
  python3 task_queue.py peek    [--sprint SID]
  python3 task_queue.py depth   [--sprint SID]
  python3 task_queue.py next-worker --sprint SID  [--role builder]
  python3 task_queue.py drain   --sprint SID
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
QUEUE_DIR = HARNESS_DIR / "run" / "queue"
LEASE_DIR = HARNESS_DIR / "run" / "pane-leases"
DEDUP_WINDOW_H = 24


def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _queue_file(sprint_id: str) -> Path:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    return QUEUE_DIR / f"{sprint_id}.jsonl"


def _queue_files(sprint_id: "str | None" = None) -> list[Path]:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    if sprint_id:
        return [_queue_file(sprint_id)]
    return sorted(QUEUE_DIR.glob("*.jsonl"))


def _intent_from_args(intent: "str | None", slice_id: "str | None", role: str) -> str:
    if intent:
        return intent
    if slice_id:
        return f"build_{slice_id.lower()}|role={role}"
    raise ValueError("enqueue requires --intent or --slice")


# ── enqueue ───────────────────────────────────────────────────────────────────

def enqueue(sprint_id: str, intent: str, priority: int = 50,
            payload: "dict | None" = None) -> dict:
    qf = _queue_file(sprint_id)
    intent_hash = hashlib.sha256(intent.encode()).hexdigest()[:12]
    now = _now()
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=DEDUP_WINDOW_H)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    lock_path = str(qf) + ".lock"
    with open(lock_path, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            existing: list[dict] = []
            if qf.exists():
                for line in qf.read_text().splitlines():
                    try:
                        existing.append(json.loads(line))
                    except Exception:
                        pass

            for item in existing:
                if (item.get("intent_hash") == intent_hash
                        and item.get("enqueued_at", "") >= cutoff
                        and not item.get("consumed")):
                    return {"ok": True, "result": "duplicate", "id": item.get("id")}

            item = {
                "id": secrets.token_hex(6),
                "sprint_id": sprint_id,
                "intent": intent,
                "intent_hash": intent_hash,
                "priority": priority,
                "retry_count": 0,
                "enqueued_at": now,
                "consumed": False,
            }
            if payload is not None:
                item["payload"] = payload
            with open(qf, "a") as f:
                f.write(json.dumps(item) + "\n")
            return {"ok": True, "result": "enqueued", "id": item["id"]}
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


# ── pop ───────────────────────────────────────────────────────────────────────

def pop(sprint_id: str) -> "dict | None":
    qf = _queue_file(sprint_id)
    if not qf.exists():
        return None

    lock_path = str(qf) + ".lock"
    with open(lock_path, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            items: list[dict] = []
            for line in qf.read_text().splitlines():
                try:
                    items.append(json.loads(line))
                except Exception:
                    pass

            pending = sorted(
                [i for i in items if not i.get("consumed")],
                key=lambda x: (-x.get("priority", 0), x.get("enqueued_at", ""))
            )
            if not pending:
                return None

            target = pending[0]
            target["consumed"] = True
            target["consumed_at"] = _now()

            for i, item in enumerate(items):
                if item.get("id") == target["id"]:
                    items[i] = target

            tmp = str(qf) + ".tmp"
            with open(tmp, "w") as f:
                for item in items:
                    f.write(json.dumps(item) + "\n")
            os.replace(tmp, str(qf))
            return target
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def peek(sprint_id: "str | None") -> "dict | None":
    all_pending: list[dict] = []
    for qf in _queue_files(sprint_id):
        if not qf.exists():
            continue
        for line in qf.read_text().splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            if not item.get("consumed"):
                if "sprint_id" not in item:
                    item["sprint_id"] = qf.stem
                all_pending.append(item)
    pending = sorted(
        all_pending,
        key=lambda x: (-x.get("priority", 0), x.get("enqueued_at", ""))
    )
    return pending[0] if pending else None


def peek_sprint(sprint_id: str) -> "dict | None":
    qf = _queue_file(sprint_id)
    if not qf.exists():
        return None
    items: list[dict] = []
    for line in qf.read_text().splitlines():
        try:
            items.append(json.loads(line))
        except Exception:
            pass
    pending = sorted(
        [i for i in items if not i.get("consumed")],
        key=lambda x: (-x.get("priority", 0), x.get("enqueued_at", ""))
    )
    return pending[0] if pending else None


def depth(sprint_id: "str | None") -> int:
    count = 0
    for qf in _queue_files(sprint_id):
        if not qf.exists():
            continue
        for line in qf.read_text().splitlines():
            try:
                item = json.loads(line)
                if not item.get("consumed"):
                    count += 1
            except Exception:
                pass
    return count


# ── worker selection (prevents single-builder squeeze) ────────────────────────

def _pane_safe(pane: str) -> str:
    return pane.replace(":", "_").replace(".", "_")


def _lease_file(pane: str) -> Path:
    return LEASE_DIR / f"{_pane_safe(pane)}.json"


def _pane_leased(pane: str) -> bool:
    lf = _lease_file(pane)
    if not lf.exists():
        return False
    try:
        data = json.loads(lf.read_text())
        return data.get("expires_at", "") > _now()
    except Exception:
        return False


def _pane_exists(pane: str) -> bool:
    try:
        subprocess.check_call(
            ["tmux", "select-pane", "-t", pane],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3
        )
        return True
    except Exception:
        return False


def _all_builder_panes() -> "list[str]":
    """List all tmux panes available as potential workers."""
    try:
        out = subprocess.check_output(
            ["tmux", "list-panes", "-a",
             "-F", "#{session_name}:#{window_index}.#{pane_index}"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode()
        return [p.strip() for p in out.splitlines() if p.strip()]
    except Exception:
        return []


def next_free_worker(sprint_id: str, role: str = "builder") -> "str | None":
    """Return first pane that is alive + not leased.

    Logs skip reasons to stderr so coordinator can see why workers were skipped
    (prevents silent single-builder squeeze).
    """
    candidates = _all_builder_panes()
    for pane in candidates:
        if not _pane_exists(pane):
            print(f"[worker-select] skip {pane}: pane does not exist", file=sys.stderr)
            continue
        if _pane_leased(pane):
            print(f"[worker-select] skip {pane}: lease active", file=sys.stderr)
            continue
        return pane

    print(f"[worker-select] no free worker for sprint={sprint_id} role={role}", file=sys.stderr)
    return None


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(prog="task_queue.py")
    sub = ap.add_subparsers(dest="cmd")

    enq = sub.add_parser("enqueue")
    enq.add_argument("--sprint", required=True)
    enq.add_argument("--intent")
    enq.add_argument("--slice", dest="slice_id")
    enq.add_argument("--role", default="builder")
    enq.add_argument("--priority", type=int, default=50)
    enq.add_argument("--payload")

    enq_node = sub.add_parser("enqueue-node")
    enq_node.add_argument("--sprint", required=True)
    enq_node.add_argument("--node-id", required=True)
    enq_node.add_argument("--payload", required=True)
    enq_node.add_argument("--priority", type=int, default=50)

    pop_p = sub.add_parser("pop")
    pop_p.add_argument("--sprint")

    peek_p = sub.add_parser("peek")
    peek_p.add_argument("--sprint")

    dep_p = sub.add_parser("depth")
    dep_p.add_argument("--sprint")

    nw = sub.add_parser("next-worker")
    nw.add_argument("--sprint", required=True)
    nw.add_argument("--role", default="builder")

    drain_p = sub.add_parser("drain")
    drain_p.add_argument("--sprint")

    args = ap.parse_args()

    if args.cmd == "enqueue":
        try:
            intent = _intent_from_args(args.intent, args.slice_id, args.role)
            payload = json.loads(args.payload) if args.payload else None
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 2
        except json.JSONDecodeError as exc:
            print(json.dumps({"ok": False, "error": f"invalid payload JSON: {exc}"}), file=sys.stderr)
            return 2
        result = enqueue(args.sprint, intent, args.priority, payload)
        print(json.dumps(result))

    elif args.cmd == "enqueue-node":
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as exc:
            print(json.dumps({"ok": False, "error": f"invalid payload JSON: {exc}"}), file=sys.stderr)
            return 2
        result = enqueue(args.sprint, f"graph_node|node_id={args.node_id}", args.priority, payload)
        print(json.dumps(result))

    elif args.cmd == "pop":
        if args.sprint:
            item = pop(args.sprint)
        else:
            first = peek(None)
            item = pop(first["sprint_id"]) if first else None
        print(json.dumps(item or {"ok": False, "reason": "empty"}))

    elif args.cmd == "peek":
        item = peek(args.sprint)
        print(json.dumps(item or {"ok": False, "reason": "empty"}))

    elif args.cmd == "depth":
        print(json.dumps({"ok": True, "sprint_id": args.sprint, "depth": depth(args.sprint)}))

    elif args.cmd == "next-worker":
        pane = next_free_worker(args.sprint, args.role)
        if pane:
            print(json.dumps({"ok": True, "pane": pane}))
        else:
            result = enqueue(args.sprint, f"pending|role={args.role}|queued_at={_now()}", priority=50)
            print(json.dumps({"ok": False, "reason": "no_free_worker", "queued": result}))
            return 2

    elif args.cmd == "drain":
        items: list[dict] = []
        if args.sprint:
            while True:
                item = pop(args.sprint)
                if item is None:
                    break
                items.append(item)
        else:
            while True:
                first = peek(None)
                if first is None:
                    break
                item = pop(first["sprint_id"])
                if item is not None:
                    items.append(item)
        print(json.dumps({"ok": True, "drained": len(items), "items": items}))

    else:
        ap.print_help()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
