"""Trajectory extractor for Solar Experience Memory.

Reads terminal sprint artifacts and produces compact trajectory.json records.
Secret-strip filter is always active.
"""
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .schema import validate_trajectory

logger = logging.getLogger(__name__)

HARNESS_DIR = os.path.expanduser("~/.solar/harness")
SPRINTS_DIR = os.path.join(HARNESS_DIR, "sprints")
EXPERIENCE_DIR = os.path.join(HARNESS_DIR, "experience", "trajectory")
SCHEMA_VERSION = "1.0.0"
TERMINAL_STATUSES = {"passed", "failed", "cancelled", "quarantined"}

_SECRET_PATTERNS = [
    re.compile(r'(?i)(password|secret|token|api[_\-]?key|bearer|authorization)\s*[=:]\s*\S+'),
    re.compile(r'sk-[A-Za-z0-9]{20,}'),
    re.compile(r'ghp_[A-Za-z0-9]{36,}'),
    re.compile(r'xox[baprs]-[A-Za-z0-9\-]+'),
]


def _strip_secrets(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub(lambda m: m.group(0).split('=')[0].split(':')[0] + '=[REDACTED]', text)
    return text


def _make_trigger_sig(status_data: Dict[str, Any]) -> str:
    parts = [
        status_data.get("status", ""),
        status_data.get("phase", ""),
        str(status_data.get("round", 0)),
    ]
    triggers = status_data.get("triggers", [])
    if isinstance(triggers, list):
        parts.extend(triggers)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _make_state_sig(status_data: Dict[str, Any]) -> str:
    relevant = {k: status_data.get(k) for k in ("status", "phase", "round", "eval_verdict")}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:16]


def _summarize_events(sid: str) -> Dict[str, Any]:
    events_path = os.path.join(HARNESS_DIR, "events.jsonl")
    summary = {
        "total_events": 0,
        "c_u_events": 0,
        "dispatch_events": 0,
        "eval_rounds": 0,
        "duration_minutes": 0.0,
    }
    if not os.path.exists(events_path):
        return summary
    first_ts = last_ts = None
    try:
        with open(events_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("sid") != sid:
                    continue
                summary["total_events"] += 1
                ev_type = str(ev.get("type", ev.get("event", "")))
                if "c_u" in ev_type or "send_keys" in ev_type:
                    summary["c_u_events"] += 1
                if "dispatch" in ev_type:
                    summary["dispatch_events"] += 1
                if "eval" in ev_type:
                    summary["eval_rounds"] += 1
                ts_str = ev.get("ts") or ev.get("timestamp")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if first_ts is None or ts < first_ts:
                            first_ts = ts
                        if last_ts is None or ts > last_ts:
                            last_ts = ts
                    except Exception:
                        pass
    except Exception as e:
        logger.warning("events.jsonl read error for %s: %s", sid, e)
    if first_ts and last_ts:
        summary["duration_minutes"] = round((last_ts - first_ts).total_seconds() / 60, 2)
    return summary


def _extract_repair_actions(sid: str) -> List[str]:
    actions = []
    for suffix in (".eval.md", ".handoff.md"):
        path = os.path.join(SPRINTS_DIR, f"{sid}{suffix}")
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                content = _strip_secrets(f.read())
            for line in content.splitlines():
                low = line.lower()
                if any(kw in low for kw in ("fix:", "repair:", "fixed:", "resolved:", "patched:")):
                    actions.append(line.strip()[:200])
        except Exception as e:
            logger.warning("repair actions read error %s%s: %s", sid, suffix, e)
    return actions[:10]


def _get_tags(status_data: Dict[str, Any]) -> List[str]:
    tags = []
    phase = status_data.get("phase", "")
    if phase:
        tags.append(f"phase:{phase}")
    status = status_data.get("status", "")
    if status:
        tags.append(f"status:{status}")
    triggers = status_data.get("triggers", [])
    if isinstance(triggers, list):
        for t in triggers[:3]:
            tags.append(f"trigger:{t}")
    return tags


def extract_sprint(sid: str) -> Optional[Dict[str, Any]]:
    """Extract a terminal sprint into a compact trajectory dict.

    Returns None if the sprint is not terminal or artifacts are missing.
    Writes the trajectory to experience/trajectory/{sid}.json and returns the dict.
    """
    status_path = os.path.join(SPRINTS_DIR, f"{sid}.status.json")
    if not os.path.exists(status_path):
        logger.warning("status.json not found for %s", sid)
        return None

    try:
        with open(status_path) as f:
            status_data = json.load(f)
    except Exception as e:
        logger.error("failed to read status.json for %s: %s", sid, e)
        return None

    status = status_data.get("status", "")
    if status not in TERMINAL_STATUSES:
        logger.debug("sprint %s is not terminal (status=%s), skipping", sid, status)
        return None

    outcome_map = {"passed": "success", "failed": "failure",
                   "cancelled": "partial", "quarantined": "failure"}
    outcome = outcome_map.get(status, "partial")

    events_summary = _summarize_events(sid)
    repair_actions = _extract_repair_actions(sid)
    tags = _get_tags(status_data)

    # Detect anti-patterns from events summary
    anti_patterns = []
    if events_summary["c_u_events"] > 5:
        anti_patterns.append("c_u_storm")
    if status_data.get("phase") in ("passed", "finalized") and status_data.get("status") in ("failed",):
        anti_patterns.append("terminal_phase_wake")

    trajectory = {
        "schema_version": SCHEMA_VERSION,
        "sid": sid,
        "status": status,
        "phase": status_data.get("phase", "unknown"),
        "trigger_sig": _make_trigger_sig(status_data),
        "state_sig": _make_state_sig(status_data),
        "tags": tags,
        "events_summary": events_summary,
        "anti_patterns": anti_patterns,
        "outcome": outcome,
        "repair_actions": repair_actions,
        "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    try:
        validate_trajectory(trajectory)
    except ValueError as e:
        logger.error("trajectory validation failed for %s: %s", sid, e)
        return None

    out_path = os.path.join(EXPERIENCE_DIR, f"{sid}.json")
    os.makedirs(EXPERIENCE_DIR, exist_ok=True)
    try:
        with open(out_path, "w") as f:
            json.dump(trajectory, f, indent=2)
        logger.info("extracted trajectory for %s → %s", sid, out_path)
    except Exception as e:
        logger.error("failed to write trajectory for %s: %s", sid, e)
        return None

    return trajectory


def extract_all_terminal(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Extract all terminal sprints. Returns list of trajectory dicts."""
    if not os.path.exists(SPRINTS_DIR):
        return []
    results = []
    status_files = sorted(
        [f for f in os.listdir(SPRINTS_DIR) if f.endswith(".status.json")],
        reverse=True
    )
    for fname in status_files:
        sid = fname[:-len(".status.json")]
        traj = extract_sprint(sid)
        if traj is not None:
            results.append(traj)
            if limit and len(results) >= limit:
                break
    return results
