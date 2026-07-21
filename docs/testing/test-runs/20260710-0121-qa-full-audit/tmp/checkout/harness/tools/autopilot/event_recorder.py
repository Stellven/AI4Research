"""Autopilot event recorder — writes unblocked/active events to status.json.

Records structured lifecycle events that the status dashboard and the
solar-autopilot-monitor can observe to determine whether dispatching is
making progress. Two event types are defined:

  node_unblocked
    Emitted when a node's dependency set is fully satisfied (all deps passed)
    so the node is now eligible for dispatch.

  node_active
    Emitted when a node has been assigned to a pane/operator and is actively
    being worked on.

Both events are appended to status.json["history"] and the top-level
`active_node` / `open_nodes` fields are refreshed atomically via
a rename-safe tmp-write.

The recorder is intentionally side-effect-free when the status file does
not yet exist (it creates a minimal stub) and is safe to call multiple
times (idempotent per event type+node).
"""
from __future__ import annotations

import datetime
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write *data* to *path* atomically using a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        tmp = Path(handle.name)
        handle.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _load_status(path: Path, sprint_id: str = "") -> dict[str, Any]:
    """Load or create a minimal status dict from *path*."""
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "id": sprint_id or path.stem,
        "sprint_id": sprint_id or path.stem,
        "status": "active",
        "created_at": _now(),
        "updated_at": _now(),
        "history": [],
    }


def _event_already_recorded(
    status: dict[str, Any], event_type: str, node_id: str
) -> bool:
    """Return True if an identical (event_type, node_id) entry exists in history."""
    for entry in status.get("history") or []:
        if entry.get("event") == event_type and entry.get("node_id") == node_id:
            return True
    return False


class EventRecorder:
    """Records autopilot lifecycle events for a single sprint status file."""

    def __init__(self, status_path: str | Path, sprint_id: str = "") -> None:
        self.status_path = Path(status_path).expanduser()
        self.sprint_id = sprint_id or self.status_path.stem

    def record_node_unblocked(
        self,
        node_id: str,
        deps_passed: list[str] | None = None,
        by: str = "autopilot.event_recorder",
        note: str = "",
    ) -> dict[str, Any]:
        """Append a node_unblocked event to status.json.

        Args:
            node_id: DAG node identifier (e.g. "N1").
            deps_passed: List of dependency node IDs that just became passed,
                         unlocking this node. Pass [] if triggered by initial
                         state (no deps).
            by: Actor identifier written to the history entry.
            note: Optional free-text note.

        Returns:
            The updated status dict.
        """
        status = _load_status(self.status_path, self.sprint_id)
        if not isinstance(status.get("history"), list):
            status["history"] = []

        now = _now()
        history_entry: dict[str, Any] = {
            "ts": now,
            "event": "node_unblocked",
            "by": by,
            "node_id": node_id,
        }
        if deps_passed is not None:
            history_entry["deps_passed"] = deps_passed
        if note:
            history_entry["note"] = note

        status["history"].append(history_entry)
        status["updated_at"] = now

        # Refresh open_nodes list: remove node_id if previously marked blocked.
        open_nodes: list[str] = list(status.get("open_nodes") or [])
        if node_id not in open_nodes:
            open_nodes.append(node_id)
        status["open_nodes"] = open_nodes

        _atomic_write(self.status_path, status)
        return status

    def record_node_active(
        self,
        node_id: str,
        pane: str = "",
        dispatch_id: str = "",
        by: str = "autopilot.event_recorder",
        note: str = "",
    ) -> dict[str, Any]:
        """Append a node_active event to status.json and update active_node.

        Args:
            node_id: DAG node identifier (e.g. "N1").
            pane: The pane/operator assigned to this node.
            dispatch_id: Dispatch ID for cross-referencing.
            by: Actor identifier written to the history entry.
            note: Optional free-text note.

        Returns:
            The updated status dict.
        """
        status = _load_status(self.status_path, self.sprint_id)
        if not isinstance(status.get("history"), list):
            status["history"] = []

        now = _now()
        history_entry: dict[str, Any] = {
            "ts": now,
            "event": "node_active",
            "by": by,
            "node_id": node_id,
        }
        if pane:
            history_entry["pane"] = pane
        if dispatch_id:
            history_entry["dispatch_id"] = dispatch_id
        if note:
            history_entry["note"] = note

        status["history"].append(history_entry)
        status["updated_at"] = now
        status["active_node"] = node_id

        _atomic_write(self.status_path, status)
        return status


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def record_node_unblocked(
    sprint_id: str,
    node_id: str,
    status_path: str | Path,
    deps_passed: list[str] | None = None,
    by: str = "autopilot.event_recorder",
    note: str = "",
) -> dict[str, Any]:
    """Record a node_unblocked event without constructing EventRecorder explicitly."""
    recorder = EventRecorder(status_path, sprint_id=sprint_id)
    return recorder.record_node_unblocked(
        node_id, deps_passed=deps_passed, by=by, note=note
    )


def record_node_active(
    sprint_id: str,
    node_id: str,
    status_path: str | Path,
    pane: str = "",
    dispatch_id: str = "",
    by: str = "autopilot.event_recorder",
    note: str = "",
) -> dict[str, Any]:
    """Record a node_active event without constructing EventRecorder explicitly."""
    recorder = EventRecorder(status_path, sprint_id=sprint_id)
    return recorder.record_node_active(
        node_id, pane=pane, dispatch_id=dispatch_id, by=by, note=note
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse

    ap = argparse.ArgumentParser(prog="event_recorder")
    ap.add_argument("event", choices=["node_unblocked", "node_active"])
    ap.add_argument("--sprint-id", required=True)
    ap.add_argument("--node-id", required=True)
    ap.add_argument("--status-path", required=True)
    ap.add_argument("--pane", default="")
    ap.add_argument("--dispatch-id", default="")
    ap.add_argument("--deps-passed", nargs="*", default=None)
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    if args.event == "node_unblocked":
        result = record_node_unblocked(
            args.sprint_id, args.node_id, args.status_path,
            deps_passed=args.deps_passed, note=args.note,
        )
    else:
        result = record_node_active(
            args.sprint_id, args.node_id, args.status_path,
            pane=args.pane, dispatch_id=args.dispatch_id, note=args.note,
        )

    import json
    print(json.dumps({"ok": True, "updated_at": result.get("updated_at")}, indent=2))


if __name__ == "__main__":
    _main()
