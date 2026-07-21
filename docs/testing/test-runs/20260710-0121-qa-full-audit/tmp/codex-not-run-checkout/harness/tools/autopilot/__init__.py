"""autopilot package — pluggable event recording extensions.

This package provides event recording helpers that write structured
`unblocked` and `active` events into sprint status.json files, enabling
the status dashboard and downstream tooling to track node lifecycle
transitions with full evidence.

Usage:
    from tools.autopilot import EventRecorder
    recorder = EventRecorder(status_path)
    recorder.record_node_unblocked(node_id, deps_passed=["N0"])
    recorder.record_node_active(node_id, pane="operator-pool:builder.0",
                                dispatch_id="graph-…-N1-…")
"""
from __future__ import annotations

from tools.autopilot.event_recorder import EventRecorder, record_node_unblocked, record_node_active

__all__ = ["EventRecorder", "record_node_unblocked", "record_node_active"]
