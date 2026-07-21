#!/usr/bin/env python3
"""monitor_bridge.py — emit operator fleet status snapshot as JSON.

Reads the physical-operators registry, enriches each entry with
lifecycle state, resolved persona, heartbeat, and submit/daemon fields
from live runtime artifacts, then writes the snapshot to stdout or a
named output file.

Usage
-----
    python tools/monitor_bridge.py
    python tools/monitor_bridge.py --out /tmp/fleet.json
    python tools/monitor_bridge.py --operators path/to/physical-operators.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))

# Insert lib into sys.path so multi_task_status is importable regardless of cwd.
_LIB_DIR = Path(__file__).resolve().parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from multi_task_status import (  # noqa: E402
    load_operator_fleet,
    load_actor_fleet,
    load_host_fleet,
    get_logical_operator_binding_summary,
    get_actor_status_entry,
    load_actors,
    load_hosts,
    PHYSICAL_OPERATORS_PATH,
    OPERATOR_PERSONAS_DIR,
    OPERATOR_STATUS_DIR,
    OPERATOR_LEASE_DIR,
    ACTORS_PATH,
    HOSTS_PATH,
    LOGICAL_OPS_PATH,
    ACTOR_LEASE_DIR,
    _redact_secrets,
)
from browser_job_runtime import BrowserSessionBroker  # noqa: E402


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _count_claude_print_processes() -> int:
    """Return the number of observed ``claude --print`` / ``claude -p`` processes.

    Uses ``pgrep -af claude`` to enumerate live claude processes, then filters
    lines that contain a standalone ``--print`` or `` -p `` flag.  Returns -1
    when the OS command is unavailable (Windows/non-POSIX environments).
    """
    try:
        result = subprocess.run(
            ["pgrep", "-af", "claude"],
            capture_output=True, text=True, timeout=5,
        )
        count = 0
        for line in result.stdout.splitlines():
            tokens = line.split()
            if "--print" in tokens or "-p" in tokens:
                count += 1
        return count
    except (FileNotFoundError, OSError):
        return -1
    except Exception:
        return -1


def load_browser_jobs(jobs_dir: Path, actors: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Load browser job state with monitor-friendly observability fields."""
    broker = BrowserSessionBroker(harness_dir=HARNESS_DIR)
    actor_map = actors or {}
    jobs: list[dict[str, Any]] = []
    if not jobs_dir.exists():
        return jobs

    for state_file in sorted(jobs_dir.glob("*/state.json")):
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        envelope = state.get("envelope") if isinstance(state.get("envelope"), dict) else {}
        actor_id = str(state.get("actor_id") or envelope.get("actor_id") or "")
        profile_ref = str(envelope.get("profile_ref") or "")
        account_label = str(envelope.get("account_label") or "")
        if profile_ref or account_label:
            health = broker.get_profile_health(profile_ref, account_label)
        else:
            raw_state = str(state.get("state") or "unknown")
            health = {
                "status": "reauth_required" if raw_state == "reauth_required" else "healthy",
                "projected_state": "WAITING_HUMAN" if raw_state == "reauth_required" else raw_state,
            }
        artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), list) else []
        evidence = [str(item.get("name")) for item in artifacts if isinstance(item, dict) and item.get("name")]
        paths: list[str] = []
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            if item.get("path"):
                paths.append(str(item.get("path")))
            elif item.get("name"):
                paths.append(str(state_file.parent / str(item.get("name"))))
        actor_entry = actor_map.get(actor_id) if isinstance(actor_map, dict) else {}
        jobs.append({
            "job_id": str(state.get("job_id") or state_file.parent.name),
            "actor_id": actor_id,
            "actor_state": actor_entry.get("state") if isinstance(actor_entry, dict) else None,
            "async_state": str(state.get("state") or "unknown"),
            "projected_state": str(state.get("projected_state") or health.get("projected_state") or state.get("state") or "unknown"),
            "login_state": str(state.get("login_state") or health.get("status") or "unknown"),
            "quota_state": str(state.get("quota_state") or "ok"),
            "consumer_sprint": envelope.get("sprint_id") or envelope.get("consumer_sprint"),
            "logical_operator": envelope.get("logical_operator") or envelope.get("operator_id"),
            "profile_ref": profile_ref or None,
            "account_label": account_label or None,
            "evidence": evidence,
            "paths": paths,
            "state_path": str(state_file),
        })
    return jobs


def build_snapshot(
    operators_path: Path = PHYSICAL_OPERATORS_PATH,
    *,
    personas_dir: Path = OPERATOR_PERSONAS_DIR,
    status_dir: Path = OPERATOR_STATUS_DIR,
    lease_dir: Path = OPERATOR_LEASE_DIR,
    actors_path: Path = ACTORS_PATH,
    hosts_path: Path = HOSTS_PATH,
    logical_ops_path: Path = LOGICAL_OPS_PATH,
    actor_lease_dir: Path = ACTOR_LEASE_DIR,
) -> dict[str, Any]:
    """Build and return the operator fleet snapshot dict.

    Fields
    ------
    schema                   ``"solar.monitor_bridge.operator_fleet.v2"``
    observed_at              ISO-8601 UTC timestamp.
    operator_count           Total number of registered operators.
    submit_count             Operators with an active (non-expired) lease / submit_state.
    daemon_active_count      Operators whose daemon_state is not idle/N/A.
    lifecycle_counts         ``{state: count}`` breakdown.
    claude_print_process_count  Observed count of live ``claude --print`` OS processes
                             (from ``pgrep``).  -1 if pgrep is unavailable.
    operator_fleet           ``{operator_id: enriched_entry}`` for all operators.
    actor_fleet              ``{actor_id: enriched_actor_entry}`` for all actors.
    host_fleet               ``{host_id: enriched_host_entry}`` for all hosts.
    logical_operator_bindings  Summary of all 16 P0 operator bindings.
    """
    fleet = load_operator_fleet(
        operators_path,
        personas_dir=personas_dir,
        status_dir=status_dir,
        lease_dir=lease_dir,
    )

    submit_count = sum(
        1 for entry in fleet.values() if entry.get("submit_state") is not None
    )
    daemon_active_count = sum(
        1
        for entry in fleet.values()
        if entry.get("daemon_state") not in ("idle", "N/A", None, "")
    )

    lifecycle_counts: dict[str, int] = {}
    for entry in fleet.values():
        state = str(entry.get("lifecycle_state") or "N/A")
        lifecycle_counts[state] = lifecycle_counts.get(state, 0) + 1

    # Actor fleet (N4)
    actor_fleet = load_actor_fleet(actors_path, hosts_path, lease_dir=actor_lease_dir)
    actor_lease_counts: dict[str, int] = {}
    for aentry in actor_fleet.values():
        ls = str(aentry.get("lease_state") or "unknown")
        actor_lease_counts[ls] = actor_lease_counts.get(ls, 0) + 1

    # Host fleet (N4)
    host_fleet = load_host_fleet(hosts_path)

    # Logical operator binding summary (N4)
    lo_bindings = get_logical_operator_binding_summary(logical_ops_path)
    browser_jobs = load_browser_jobs(HARNESS_DIR / "run" / "browser-jobs", actor_fleet)

    return {
        "schema": "solar.monitor_bridge.operator_fleet.v2",
        "observed_at": _now_iso(),
        "operator_count": len(fleet),
        "submit_count": submit_count,
        "daemon_active_count": daemon_active_count,
        "lifecycle_counts": dict(sorted(lifecycle_counts.items())),
        "claude_print_process_count": _count_claude_print_processes(),
        "operator_fleet": dict(sorted(fleet.items())),
        "actor_fleet": dict(sorted(actor_fleet.items())),
        "actor_lease_counts": dict(sorted(actor_lease_counts.items())),
        "host_fleet": dict(sorted(host_fleet.items())),
        "logical_operator_bindings": dict(sorted(lo_bindings.items())),
        "browser_job_count": len(browser_jobs),
        "browser_jobs": browser_jobs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="monitor_bridge",
        description=(
            "Emit operator fleet status with lifecycle state, resolved persona, "
            "heartbeat, and submit/daemon fields."
        ),
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        default=None,
        help="Write JSON to this file instead of stdout.",
    )
    parser.add_argument(
        "--operators",
        metavar="PATH",
        default=str(PHYSICAL_OPERATORS_PATH),
        help="Path to physical-operators.json.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="One-shot mode (default behaviour; flag kept for scripting compatibility).",
    )
    args = parser.parse_args(argv)

    snapshot = build_snapshot(Path(args.operators))
    text = json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n"

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(out_path.suffix + f".{os.getpid()}.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(out_path)
        print(f"[monitor_bridge] written: {out_path}", file=sys.stderr)
    else:
        sys.stdout.write(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
