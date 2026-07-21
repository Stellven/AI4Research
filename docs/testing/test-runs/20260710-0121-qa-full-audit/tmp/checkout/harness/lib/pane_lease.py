#!/usr/bin/env python3
"""pane_lease.py — S6 Control Plane: Python-native pane lease with 3-state classification.

Three pane states:
  no_pane  — tmux pane does not exist (session gone, pane killed)
  busy     — pane exists AND has a live lease held by another sprint
  dead     — pane exists but lease expired / no activity (safe to reclaim)

The bash pane-lease.sh is the authoritative writer; this module reads + classifies
for the Python autopilot without needing to shell out to bash.

CLI:
  python3 pane_lease.py check  --pane PANE
  python3 pane_lease.py state  --pane PANE
  python3 pane_lease.py acquire --pane PANE --sprint SID --dispatch-id DID [--ttl N]
  python3 pane_lease.py release --pane PANE --dispatch-id DID [--reason R]
  python3 pane_lease.py reap
  python3 pane_lease.py list
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
LEASE_DIR = HARNESS_DIR / "run" / "pane-leases"
DEFAULT_TTL = 600


def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _pane_safe(pane: str) -> str:
    return pane.replace(":", "_").replace(".", "_")


def _lease_path(pane: str) -> Path:
    LEASE_DIR.mkdir(parents=True, exist_ok=True)
    return LEASE_DIR / f"{_pane_safe(pane)}.json"


def _lock_path(lp: Path) -> Path:
    return Path(str(lp) + ".lock")


def _unlink_lock(lock_path: Path) -> bool:
    try:
        lock_path.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _remove_lock_if_unlocked(lock_path: Path) -> bool:
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "a") as lf:
            try:
                fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            try:
                return _unlink_lock(lock_path)
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    except Exception:
        return False


# ── pane existence check ──────────────────────────────────────────────────────

def pane_exists(pane: str) -> bool:
    try:
        subprocess.check_call(
            ["tmux", "select-pane", "-t", pane],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3
        )
        return True
    except Exception:
        return False


# ── lease I/O ─────────────────────────────────────────────────────────────────

def read_lease(pane: str) -> "dict | None":
    lp = _lease_path(pane)
    if not lp.exists():
        return None
    try:
        return json.loads(lp.read_text())
    except Exception:
        return None


def _write_lease_atomic(pane: str, data: dict) -> None:
    lp = _lease_path(pane)
    lock = _lock_path(lp)
    with open(lock, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            tmp = str(lp) + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, str(lp))
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def _remove_lease(pane: str) -> None:
    lp = _lease_path(pane)
    lock = _lock_path(lp)
    with open(lock, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            if lp.exists():
                lp.unlink()
            _unlink_lock(lock)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


# ── 3-state classification ─────────────────────────────────────────────────────

def pane_state(pane: str) -> str:
    """Return 'no_pane' | 'busy' | 'dead'."""
    if not pane_exists(pane):
        return "no_pane"
    lease = read_lease(pane)
    if lease and lease.get("expires_at", "") > _now():
        return "busy"
    return "dead"


# ── acquire / release ─────────────────────────────────────────────────────────

def acquire(pane: str, sprint_id: str, dispatch_id: str, ttl: int = DEFAULT_TTL) -> dict:
    """Acquire lease. Returns {acquired, ...}. Fails if pane is busy."""
    if not pane_exists(pane):
        return {"acquired": False, "reason": "no_pane", "pane": pane}

    lp = _lease_path(pane)
    lock = _lock_path(lp)
    now = _now()

    with open(lock, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            existing = None
            if lp.exists():
                try:
                    existing = json.loads(lp.read_text())
                except Exception:
                    pass

            if existing and existing.get("expires_at", "") > now:
                return {
                    "acquired": False,
                    "reason": "pane_busy",
                    "held_by": existing.get("dispatch_id"),
                    "held_sid": existing.get("sid") or existing.get("sprint_id"),
                    "expires_at": existing.get("expires_at"),
                }

            expires_at = (
                datetime.datetime.utcnow() + datetime.timedelta(seconds=ttl)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            lease = {
                "pane": pane,
                "sid": sprint_id,
                "sprint_id": sprint_id,
                "dispatch_id": dispatch_id,
                "acquired_at": now,
                "expires_at": expires_at,
                "ttl_sec": ttl,
            }
            tmp = str(lp) + ".tmp"
            with open(tmp, "w") as f:
                json.dump(lease, f)
            os.replace(tmp, str(lp))
            return {"acquired": True, "dispatch_id": dispatch_id, "expires_at": expires_at}
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def release(pane: str, dispatch_id: str, reason: str = "explicit") -> dict:
    """Release lease only if dispatch_id matches."""
    lp = _lease_path(pane)
    lock = _lock_path(lp)
    if not lp.exists():
        _remove_lock_if_unlocked(lock)
        return {"released": True, "note": "lease_already_gone"}

    with open(lock, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            existing = json.loads(lp.read_text())
            if existing.get("dispatch_id") != dispatch_id:
                return {
                    "released": False,
                    "reason": "dispatch_id_mismatch",
                    "held_by": existing.get("dispatch_id"),
                }
            lp.unlink()
            _unlink_lock(lock)
            return {"released": True, "release_reason": reason}
        except FileNotFoundError:
            _unlink_lock(lock)
            return {"released": True, "note": "already_gone"}
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


# ── reap expired leases ───────────────────────────────────────────────────────

def reap() -> dict:
    """Remove all expired lease files. Returns count."""
    if not LEASE_DIR.exists():
        return {"ok": True, "reaped": 0}
    now = _now()
    reaped = 0
    for lf in LEASE_DIR.glob("*.json"):
        try:
            data = json.loads(lf.read_text())
            if data.get("expires_at", "") <= now:
                lf.unlink(missing_ok=True)
                reaped += 1
                if _remove_lock_if_unlocked(_lock_path(lf)):
                    reaped += 1
        except Exception:
            pass
    for lock in LEASE_DIR.glob("*.json.lock"):
        lease_path = Path(str(lock)[:-5])
        if lease_path.exists():
            continue
        if _remove_lock_if_unlocked(lock):
            reaped += 1
    return {"ok": True, "reaped": reaped}


def list_leases() -> list[dict]:
    if not LEASE_DIR.exists():
        return []
    now = _now()
    result = []
    for lf in sorted(LEASE_DIR.glob("*.json")):
        try:
            data = json.loads(lf.read_text())
            data["_expired"] = data.get("expires_at", "") <= now
            result.append(data)
        except Exception:
            pass
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(prog="pane_lease.py")
    sub = ap.add_subparsers(dest="cmd")

    chk = sub.add_parser("check")
    chk.add_argument("--pane", required=True)

    st = sub.add_parser("state")
    st.add_argument("--pane", required=True)

    acq = sub.add_parser("acquire")
    acq.add_argument("--pane", required=True)
    acq.add_argument("--sprint", required=True)
    acq.add_argument("--dispatch-id", required=True)
    acq.add_argument("--ttl", type=int, default=DEFAULT_TTL)

    rel = sub.add_parser("release")
    rel.add_argument("--pane", required=True)
    rel.add_argument("--dispatch-id", required=True)
    rel.add_argument("--reason", default="explicit")

    sub.add_parser("reap")
    sub.add_parser("list")

    args = ap.parse_args()

    if args.cmd == "check":
        lease = read_lease(args.pane)
        print(json.dumps(lease or {}))

    elif args.cmd == "state":
        s = pane_state(args.pane)
        print(json.dumps({"pane": args.pane, "state": s}))
        return 0 if s in ("dead",) else (1 if s == "busy" else 2)

    elif args.cmd == "acquire":
        result = acquire(args.pane, args.sprint, args.dispatch_id, args.ttl)
        print(json.dumps(result))
        return 0 if result.get("acquired") else 1

    elif args.cmd == "release":
        result = release(args.pane, args.dispatch_id, args.reason)
        print(json.dumps(result))
        return 0 if result.get("released") else 1

    elif args.cmd == "reap":
        print(json.dumps(reap()))

    elif args.cmd == "list":
        leases = list_leases()
        print(json.dumps({"ok": True, "count": len(leases), "leases": leases}))

    else:
        ap.print_help()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
