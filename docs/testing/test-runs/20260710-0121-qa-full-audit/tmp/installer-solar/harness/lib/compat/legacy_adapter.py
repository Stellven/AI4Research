"""Legacy compatibility adapter for wake/dispatch/status dual-write.

S03 N5: bridges old harness paths with new event ledger, preserving
backward compatibility per S02 compatibility-matrix.md LR-01~LR-06.

All broker/ledger imports are lazy (function-level) to satisfy LR-06.
Importing this module does NOT trigger event_ledger or execution_broker.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_HARNESS_BASE = Path(__file__).resolve().parent.parent.parent


def _status_json_path(sprint_id: str, base_dir: Optional[str] = None) -> Path:
    base = Path(base_dir) if base_dir else _HARNESS_BASE
    return base / "sprints" / f"{sprint_id}.status.json"


def _write_status_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _read_status_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# wake — dual-write
# ---------------------------------------------------------------------------

def wake(
    sprint_id: str,
    base_dir: Optional[str] = None,
    *,
    actor: str = "wake",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Wake a sprint.

    Old path: write status.json with ``drafting`` state.
    New path (optional): append ``wake.activated`` to event ledger.
    Ledger failure does NOT block the wake.
    """
    status_path = _status_json_path(sprint_id, base_dir)
    status_data = _read_status_json(status_path)
    status_data["sprint_id"] = sprint_id
    status_data["status"] = status_data.get("status", "drafting")
    status_data["woke_at"] = status_data.get("woke_at")
    if not status_data["woke_at"]:
        from datetime import datetime, timezone
        status_data["woke_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    _write_status_json(status_path, status_data)

    result: Dict[str, Any] = {
        "sprint_id": sprint_id,
        "status": status_data["status"],
        "status_json_written": True,
        "ledger_written": False,
    }

    # Lazy ledger write (best-effort, LR-06)
    try:
        from harness.lib.event_ledger import EventLedger

        run_dir = str(Path(base_dir) / "run") if base_dir else None
        ledger = EventLedger(base_dir=run_dir)
        ledger.append(
            {
                "event_type": "wake.activated",
                "sprint_id": sprint_id,
                "actor": actor,
                "payload": {"legacy": True, **kwargs},
            }
        )
        result["ledger_written"] = True
    except Exception as exc:
        logger.debug("ledger unavailable for wake(%s): %s", sprint_id, exc)

    return result


# ---------------------------------------------------------------------------
# dispatch — dual-write
# ---------------------------------------------------------------------------

def dispatch(
    sprint_id: str,
    node_id: str,
    base_dir: Optional[str] = None,
    *,
    actor: str = "coordinator",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Dispatch a DAG node.

    Old path: update status.json with dispatched node state.
    New path (optional): append ``dispatch.issued`` to event ledger.
    """
    status_path = _status_json_path(sprint_id, base_dir)
    status_data = _read_status_json(status_path)
    nodes = status_data.setdefault("nodes", {})
    nodes[node_id] = nodes.get(node_id, {})
    nodes[node_id]["status"] = "dispatched"
    _write_status_json(status_path, status_data)

    result: Dict[str, Any] = {
        "sprint_id": sprint_id,
        "node_id": node_id,
        "dispatched": True,
        "status_json_written": True,
        "ledger_written": False,
    }

    try:
        from harness.lib.event_ledger import EventLedger

        run_dir = str(Path(base_dir) / "run") if base_dir else None
        ledger = EventLedger(base_dir=run_dir)
        ledger.append(
            {
                "event_type": "dispatch.issued",
                "sprint_id": sprint_id,
                "node_id": node_id,
                "actor": actor,
                "payload": {"legacy": True, **kwargs},
            }
        )
        result["ledger_written"] = True
    except Exception as exc:
        logger.debug("ledger unavailable for dispatch(%s/%s): %s", sprint_id, node_id, exc)

    return result


# ---------------------------------------------------------------------------
# status — dual-read
# ---------------------------------------------------------------------------

def status(
    sprint_id: str,
    base_dir: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Read sprint status.

    Old path: read status.json.
    New path (optional): add ledger event count if ledger exists.
    """
    status_path = _status_json_path(sprint_id, base_dir)
    status_data = _read_status_json(status_path)

    result: Dict[str, Any] = {
        "sprint_id": sprint_id,
        "status": status_data.get("status", "unknown"),
        "nodes": status_data.get("nodes", {}),
        "status_json_found": status_path.exists(),
        "ledger_event_count": 0,
    }

    try:
        from harness.lib.event_ledger import EventLedger

        run_dir = str(Path(base_dir) / "run") if base_dir else None
        ledger = EventLedger(base_dir=run_dir)
        events = ledger.replay(sprint_id)
        result["ledger_event_count"] = len(events)
        if events:
            result["last_event_id"] = events[-1]["event_id"]
    except Exception as exc:
        logger.debug("ledger unavailable for status(%s): %s", sprint_id, exc)

    return result
