"""Anti-pattern detector for Solar Experience Memory.

Detects 5 known failure classes from sprint trajectories.
Input: trajectory dict → list[pattern_hit dicts]
"""
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

PATTERN_CLASSES = {
    "c_u_storm": "Excessive tmux send-keys / C-u operations flooding the pane",
    "mis_dispatch": "Sprint dispatched to wrong role, pane, or incarnation",
    "status_corruption": "Sprint status.json inconsistent with actual phase or outcome",
    "terminal_phase_wake": "Coordinator woke a sprint that is already in terminal phase",
    "queue_block": "Builder or evaluator queue blocked; lease held but no progress",
}


def _detect_c_u_storm(traj: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits = []
    events = traj.get("events_summary", {})
    c_u_count = events.get("c_u_events", 0)
    total = events.get("total_events", 0)
    if c_u_count > 5:
        ratio = c_u_count / max(total, 1)
        hits.append({
            "pattern": "c_u_storm",
            "confidence": min(0.5 + ratio * 0.5, 1.0),
            "evidence": f"c_u_events={c_u_count} ratio={ratio:.2f}",
            "advisory": (
                "High send-keys/C-u count detected. "
                "Check if previous prompt residue is being cleared excessively. "
                "Ensure pane is idle before dispatch."
            ),
        })
    return hits


def _detect_mis_dispatch(traj: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits = []
    tags = traj.get("tags", [])
    anti = traj.get("anti_patterns", [])
    # Heuristic: failed sprint with dispatch events but zero eval rounds = mis_dispatch
    events = traj.get("events_summary", {})
    if (traj.get("outcome") == "failure"
            and events.get("dispatch_events", 0) > 0
            and events.get("eval_rounds", 0) == 0):
        hits.append({
            "pattern": "mis_dispatch",
            "confidence": 0.7,
            "evidence": f"dispatch_events={events['dispatch_events']} eval_rounds=0 outcome=failure",
            "advisory": (
                "Sprint was dispatched but never evaluated. "
                "Possible wrong pane or incarnation. "
                "Verify coordinator pane-role mapping."
            ),
        })
    if "mis_dispatch" in anti:
        hits.append({
            "pattern": "mis_dispatch",
            "confidence": 0.9,
            "evidence": "explicitly flagged in trajectory anti_patterns",
            "advisory": "Previous extraction detected mis_dispatch. Review coordinator routing.",
        })
    return hits


def _detect_status_corruption(traj: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits = []
    status = traj.get("status", "")
    phase = traj.get("phase", "")
    # Passed sprint with failed outcome = corruption
    if status == "passed" and traj.get("outcome") == "failure":
        hits.append({
            "pattern": "status_corruption",
            "confidence": 0.95,
            "evidence": f"status=passed but outcome=failure",
            "advisory": (
                "status.json says passed but outcome is failure. "
                "status.json may have been overwritten incorrectly. "
                "Check update-contract and status write paths."
            ),
        })
    # Terminal phase with non-terminal status
    terminal_phases = {"passed", "finalized", "cancelled", "quarantined"}
    active_statuses = {"active", "reviewing", "drafting", "planning"}
    if phase in terminal_phases and status in active_statuses:
        hits.append({
            "pattern": "status_corruption",
            "confidence": 0.85,
            "evidence": f"phase={phase} but status={status}",
            "advisory": (
                "Phase indicates terminal state but status is active. "
                "Potential status.json write race condition."
            ),
        })
    return hits


def _detect_terminal_phase_wake(traj: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits = []
    phase = traj.get("phase", "")
    status = traj.get("status", "")
    terminal_phases = {"passed", "finalized", "cancelled", "quarantined"}
    terminal_statuses = {"passed", "failed", "cancelled", "quarantined"}
    # Sprint is terminal but still received dispatch events
    events = traj.get("events_summary", {})
    if (phase in terminal_phases or status in terminal_statuses):
        if events.get("dispatch_events", 0) > 0:
            hits.append({
                "pattern": "terminal_phase_wake",
                "confidence": 0.8,
                "evidence": (
                    f"phase={phase} status={status} "
                    f"dispatch_events={events['dispatch_events']}"
                ),
                "advisory": (
                    "Coordinator dispatched to a sprint that is already terminal. "
                    "Add terminal phase guard in pre_dispatch hook. "
                    "Check EXPERIENCE_HOOK pre_dispatch → abort if terminal."
                ),
            })
    # Also check if explicitly tagged
    if "terminal_phase_wake" in traj.get("anti_patterns", []):
        hits.append({
            "pattern": "terminal_phase_wake",
            "confidence": 0.95,
            "evidence": "explicitly in trajectory anti_patterns",
            "advisory": "Terminal phase wake previously identified. Enforce abort guard.",
        })
    return hits


def _detect_queue_block(traj: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits = []
    events = traj.get("events_summary", {})
    # Long duration + many rounds but outcome failure = queue block
    duration = events.get("duration_minutes", 0)
    eval_rounds = events.get("eval_rounds", 0)
    if (traj.get("outcome") == "failure"
            and duration > 60
            and eval_rounds == 0
            and events.get("total_events", 0) > 0):
        hits.append({
            "pattern": "queue_block",
            "confidence": 0.65,
            "evidence": f"duration={duration}min eval_rounds=0 outcome=failure",
            "advisory": (
                "Sprint ran for over an hour without evaluation. "
                "Possible lease held but builder/evaluator not responding. "
                "Check pane-lease.sh and queue.sh for stuck leases."
            ),
        })
    if "queue_block" in traj.get("anti_patterns", []):
        hits.append({
            "pattern": "queue_block",
            "confidence": 0.9,
            "evidence": "explicitly in trajectory anti_patterns",
            "advisory": "Queue block previously identified. Check lease expiry.",
        })
    return hits


def detect_patterns(trajectory: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Detect all anti-patterns in a trajectory. Returns list of pattern_hit dicts."""
    detectors = [
        _detect_c_u_storm,
        _detect_mis_dispatch,
        _detect_status_corruption,
        _detect_terminal_phase_wake,
        _detect_queue_block,
    ]
    hits = []
    for detector in detectors:
        try:
            hits.extend(detector(trajectory))
        except Exception as e:
            logger.warning("pattern detector %s failed: %s", detector.__name__, e)
    return hits
