#!/usr/bin/env python3
"""Symphony Scheduler — dry-run orchestration of Solar sprints.

Reads issue-adapter output, maintains claimed/running/retry/completed state,
and writes structured JSONL event logs.

P0 = dry-run only (no real agent launch).
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HARNESS_DIR = os.path.expanduser("~/.solar/harness")
STATE_DIR = os.path.join(HARNESS_DIR, "state", "symphony")
LOG_FILE = os.path.join(HARNESS_DIR, "logs", "symphony-events.jsonl")
SPRINTS_DIR = os.path.join(HARNESS_DIR, "sprints")

ADAPTER_PATH = os.path.join(HARNESS_DIR, "lib", "symphony", "issue-adapter.py")
WORKSPACE_MGR = os.path.join(HARNESS_DIR, "lib", "symphony", "workspace-manager.sh")
RUNNER_PATH = os.path.join(HARNESS_DIR, "lib", "symphony", "runner.sh")


def ensure_dirs():
    for subdir in ["claimed", "running", "retry", "completed"]:
        os.makedirs(os.path.join(STATE_DIR, subdir), exist_ok=True)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_event(event: str, **kwargs):
    entry = {"ts": now_iso(), "event": event}
    entry.update(kwargs)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_state(subdir: str, sprint_id: str, data: dict):
    path = os.path.join(STATE_DIR, subdir, f"{sprint_id}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def read_state(subdir: str, sprint_id: str) -> dict:
    path = os.path.join(STATE_DIR, subdir, f"{sprint_id}.json")
    if not os.path.isfile(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def list_state(subdir: str) -> list:
    pattern = os.path.join(STATE_DIR, subdir, "*.json")
    results = []
    for path in sorted(glob(pattern)):
        try:
            with open(path) as f:
                results.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return results


def get_issues(states: list = None) -> list:
    cmd = [sys.executable, ADAPTER_PATH, "--list"]
    if states:
        cmd.extend(["--states", ",".join(states)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        print(f"Warning: issue-adapter failed: {result.stderr}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def dry_run(max_concurrent: int = 1):
    ensure_dirs()

    # Get candidate issues (active, planning, approved states)
    issues = get_issues(states=["active", "draft", "planning"])
    if not issues:
        print("No candidate issues found for scheduling.")
        return

    # Filter out already completed or running
    completed_ids = {s["sprint_id"] for s in list_state("completed")}
    running_ids = {s["sprint_id"] for s in list_state("running")}
    claimed_ids = {s["sprint_id"] for s in list_state("claimed")}

    candidates = [
        i for i in issues
        if i["id"] not in completed_ids
        and i["id"] not in running_ids
        and i["id"] not in claimed_ids
    ]

    available_slots = max_concurrent - len(running_ids) - len(claimed_ids)
    if available_slots <= 0:
        print(f"At concurrency limit ({max_concurrent}). No new claims.")
        return

    to_claim = candidates[:available_slots]

    for issue in to_claim:
        sprint_id = issue["id"]

        # Claim
        emit_event("claimed", sprint_id=sprint_id, priority=issue["priority"])
        write_state("claimed", sprint_id, {
            "sprint_id": sprint_id,
            "claimed_at": now_iso(),
            "priority": issue["priority"],
        })

        # Create workspace
        try:
            ws_result = subprocess.run(
                ["bash", WORKSPACE_MGR, "create", sprint_id],
                capture_output=True, text=True, timeout=15
            )
            ws_path = ws_result.stdout.strip()
            emit_event("workspace_created", sprint_id=sprint_id, path=ws_path)
        except Exception as e:
            emit_event("workspace_failed", sprint_id=sprint_id, error=str(e))
            continue

        # Move to running
        os.rename(
            os.path.join(STATE_DIR, "claimed", f"{sprint_id}.json"),
            os.path.join(STATE_DIR, "running", f"{sprint_id}.json"),
        )
        write_state("running", sprint_id, {
            "sprint_id": sprint_id,
            "started_at": now_iso(),
            "workspace": ws_path,
        })
        emit_event("runner_started", sprint_id=sprint_id, mode="dry-run")

        # Run runner (dry-run)
        try:
            run_result = subprocess.run(
                ["bash", RUNNER_PATH, "--dry-run", "--sprint-id", sprint_id],
                capture_output=True, text=True, timeout=30
            )
            exit_code = run_result.returncode
            emit_event("runner_completed", sprint_id=sprint_id, exit_code=exit_code)
        except Exception as e:
            exit_code = -1
            emit_event("runner_failed", sprint_id=sprint_id, error=str(e))

        # Move to completed
        result_val = "pass" if exit_code == 0 else "fail"
        os.rename(
            os.path.join(STATE_DIR, "running", f"{sprint_id}.json"),
            os.path.join(STATE_DIR, "completed", f"{sprint_id}.json"),
        )
        write_state("completed", sprint_id, {
            "sprint_id": sprint_id,
            "completed_at": now_iso(),
            "result": result_val,
        })
        emit_event("completed", sprint_id=sprint_id, result=result_val)


def show_status():
    ensure_dirs()
    claimed = list_state("claimed")
    running = list_state("running")
    retry = list_state("retry")
    completed = list_state("completed")

    status = {
        "claimed": len(claimed),
        "running": len(running),
        "retry": len(retry),
        "completed": len(completed),
        "issues": {
            "claimed": claimed,
            "running": running,
            "retry": retry,
        },
    }
    print(json.dumps(status, indent=2, ensure_ascii=False))


import glob as glob_mod  # noqa: E402 — needed at module level for list_state

# Fix: use the imported glob module
glob = glob_mod.glob


def main():
    parser = argparse.ArgumentParser(description="Symphony Scheduler")
    parser.add_argument("--status", action="store_true", help="Show current status")
    parser.add_argument("--dry-run", action="store_true", help="Run dry-run scheduling")
    parser.add_argument("--max-concurrent", type=int, default=1, help="Max concurrent agents")
    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.dry_run:
        dry_run(args.max_concurrent)
    else:
        # Default: show status
        show_status()


if __name__ == "__main__":
    main()
