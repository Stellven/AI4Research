"""Compressor for Solar Experience Memory.

Aggregates trajectories + pattern hits → experience entries.
Clusters by trigger_sig + pattern_class (idempotent).
"""
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .index import init_db, upsert_entry
from .patterns import detect_patterns
from .schema import validate_entry

logger = logging.getLogger(__name__)

HARNESS_DIR = os.path.expanduser("~/.solar/harness")
TRAJECTORY_DIR = os.path.join(HARNESS_DIR, "experience", "trajectory")
ENTRIES_DIR = os.path.join(HARNESS_DIR, "experience", "entries")
SCHEMA_VERSION = "1.0.0"


def _entry_id(trigger_sig: str, pattern_class: str) -> str:
    raw = f"{trigger_sig}::{pattern_class}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _make_advisory(hits: List[Dict[str, Any]]) -> str:
    parts = []
    for h in hits:
        adv = h.get("advisory", "")
        if adv and adv not in parts:
            parts.append(adv)
    combined = " | ".join(parts)
    return combined[:2000]


def _make_repair_recipe(traj: Dict[str, Any], pattern_class: str) -> str:
    actions = traj.get("repair_actions", [])
    parts = []
    if pattern_class == "terminal_phase_mismatch" or pattern_class == "terminal_phase_wake":
        parts.append(
            "terminal_phase_mismatch: When coordinator wakes a terminal sprint, "
            "call pre_dispatch() → check status → abort if in {passed,failed,cancelled,quarantined}."
        )
    if actions:
        parts.append("Observed repairs: " + "; ".join(actions[:5]))
    recipe = " | ".join(parts)
    return recipe[:2000]


def compress_trajectories(trajectories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compress a list of trajectories into deduplicated experience entries.

    Clusters by (trigger_sig, pattern_class). Updates hit_count for existing clusters.
    Returns list of upserted entry dicts.
    """
    init_db()
    os.makedirs(ENTRIES_DIR, exist_ok=True)

    # Group by trigger_sig+pattern; also emit success_workflow entries
    clusters: Dict[str, Dict[str, Any]] = {}

    for traj in trajectories:
        trigger_sig = traj.get("trigger_sig", "unknown")
        hits = detect_patterns(traj)

        # If no anti-patterns detected and outcome is success → success_workflow
        if not hits and traj.get("outcome") == "success":
            hits = [{
                "pattern": "success_workflow",
                "confidence": 0.8,
                "evidence": "no anti-patterns + success outcome",
                "advisory": f"Successful workflow for phase={traj.get('phase')} status={traj.get('status')}",
            }]

        for hit in hits:
            pattern_class = hit["pattern"]
            eid = _entry_id(trigger_sig, pattern_class)

            if eid not in clusters:
                clusters[eid] = {
                    "entry_id": eid,
                    "trigger_sig": trigger_sig,
                    "state_sig": traj.get("state_sig"),
                    "pattern_class": pattern_class,
                    "tags": traj.get("tags", []),
                    "outcome": traj.get("outcome", "partial"),
                    "advisory": hit.get("advisory", ""),
                    "repair_recipe": _make_repair_recipe(traj, pattern_class),
                    "source_sids": [traj["sid"]],
                    "hit_count": 1,
                    "last_seen": traj.get("extracted_at"),
                    "created_at": traj.get("extracted_at",
                                           datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
                    "schema_version": SCHEMA_VERSION,
                }
            else:
                existing = clusters[eid]
                existing["hit_count"] += 1
                existing["last_seen"] = traj.get("extracted_at", existing["last_seen"])
                if traj["sid"] not in existing["source_sids"]:
                    existing["source_sids"].append(traj["sid"])
                # Merge advisory
                if hit.get("advisory") and hit["advisory"] not in existing["advisory"]:
                    existing["advisory"] = (existing["advisory"] + " | " + hit["advisory"])[:2000]

    entries = []
    for entry in clusters.values():
        try:
            validate_entry(entry)
        except ValueError as e:
            logger.warning("entry validation failed, skipping %s: %s", entry["entry_id"], e)
            continue

        # Write JSONL entry to state
        entry_path = os.path.join(ENTRIES_DIR, f"{entry['entry_id']}.json")
        try:
            with open(entry_path, "w") as f:
                json.dump(entry, f, indent=2)
        except Exception as e:
            logger.error("failed to write entry %s: %s", entry["entry_id"], e)
            continue

        upsert_entry(entry)
        entries.append(entry)
        logger.info("compressed entry %s pattern=%s", entry["entry_id"], entry["pattern_class"])

    return entries
