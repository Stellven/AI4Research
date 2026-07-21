"""Idempotent backfill for Solar Experience Memory.

Processes all sprints/*.status.json files. Safe to rerun — skips already-extracted sprints.
"""
import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

HARNESS_DIR = os.path.expanduser("~/.solar/harness")
SPRINTS_DIR = os.path.join(HARNESS_DIR, "sprints")
TRAJECTORY_DIR = os.path.join(HARNESS_DIR, "experience", "trajectory")
LOCK_FILE = os.path.join(HARNESS_DIR, "experience", "backfill.lock")


def run_backfill() -> Dict[str, Any]:
    """Backfill all terminal sprints. Idempotent — skips already extracted."""
    from .extractor import extract_sprint
    from .compressor import compress_trajectories

    os.makedirs(TRAJECTORY_DIR, exist_ok=True)

    if not os.path.exists(SPRINTS_DIR):
        return {"processed": 0, "skipped": 0, "errors": 0, "ok": True}

    status_files = sorted([
        f for f in os.listdir(SPRINTS_DIR)
        if f.endswith(".status.json")
    ])

    processed = 0
    skipped = 0
    errors = 0
    new_trajectories = []

    for fname in status_files:
        sid = fname[:-len(".status.json")]
        traj_path = os.path.join(TRAJECTORY_DIR, f"{sid}.json")

        # Idempotency: skip if trajectory already exists
        if os.path.exists(traj_path):
            skipped += 1
            continue

        try:
            traj = extract_sprint(sid)
            if traj is None:
                skipped += 1
            else:
                new_trajectories.append(traj)
                processed += 1
        except Exception as e:
            logger.error("backfill error for %s: %s", sid, e)
            errors += 1

    # Compress newly extracted trajectories
    if new_trajectories:
        try:
            compress_trajectories(new_trajectories)
        except Exception as e:
            logger.error("backfill compress failed: %s", e)
            errors += 1

    # Write lock file with stats
    try:
        import datetime
        lock_data = {
            "last_run": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "processed": processed,
            "skipped": skipped,
            "errors": errors,
        }
        with open(LOCK_FILE, "w") as f:
            json.dump(lock_data, f, indent=2)
    except Exception as e:
        logger.warning("could not write backfill.lock: %s", e)

    return {
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "ok": True,
    }
