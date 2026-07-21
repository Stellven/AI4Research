"""Schema validation for Solar Experience Memory."""
import json
import os
from typing import Any, Dict

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "../../schemas/experience-memory.schema.json")
_SCHEMA_PATH = os.path.normpath(_SCHEMA_PATH)

VALID_STATUSES = {"passed", "failed", "cancelled", "quarantined"}
VALID_OUTCOMES = {"success", "failure", "partial"}
VALID_PATTERN_CLASSES = {
    "c_u_storm", "mis_dispatch", "status_corruption",
    "terminal_phase_wake", "queue_block", "success_workflow", "repair_recipe"
}


def validate_trajectory(data: Dict[str, Any]) -> None:
    """Validate a trajectory dict. Raises ValueError on failure."""
    required = {"schema_version", "sid", "status", "phase", "trigger_sig",
                "events_summary", "extracted_at"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"trajectory missing fields: {missing}")
    if data["status"] not in VALID_STATUSES:
        raise ValueError(f"trajectory invalid status: {data['status']}")
    if data.get("outcome") and data["outcome"] not in VALID_OUTCOMES:
        raise ValueError(f"trajectory invalid outcome: {data['outcome']}")
    if not isinstance(data.get("events_summary"), dict):
        raise ValueError("trajectory events_summary must be a dict")


def validate_entry(data: Dict[str, Any]) -> None:
    """Validate an entry dict. Raises ValueError on failure."""
    required = {"schema_version", "entry_id", "trigger_sig", "pattern_class",
                "outcome", "created_at"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"entry missing fields: {missing}")
    if data["pattern_class"] not in VALID_PATTERN_CLASSES:
        raise ValueError(f"entry invalid pattern_class: {data['pattern_class']}")
    if data["outcome"] not in VALID_OUTCOMES:
        raise ValueError(f"entry invalid outcome: {data['outcome']}")
    advisory = data.get("advisory", "")
    if advisory and len(advisory) > 2048:
        raise ValueError("entry advisory exceeds 2048 chars (bounded context rule)")
    recipe = data.get("repair_recipe", "")
    if recipe and len(recipe) > 2048:
        raise ValueError("entry repair_recipe exceeds 2048 chars")
