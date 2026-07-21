"""Epic status view — renders epic traceability as a status table.

Pure function that reads a traceability JSON dict and formats it as a
multi-row status table with 7 columns.  No external I/O, no randomness.
"""

from __future__ import annotations

from typing import Any


def render_epic_status(traceability: dict[str, Any]) -> str:
    """Render an epic traceability dict as a CLI status table.

    Parameters
    ----------
    traceability:
        A dict matching the ``solar.epic.traceability.v1`` schema with
        ``children`` list containing sprint entries.

    Returns a multi-line string with header + one row per child sprint.
    Columns: slice / sprint_id_short / status / ready_or_blocked / deps_missing
    """
    children = traceability.get("children", [])
    epic_id = traceability.get("epic_id", "?")

    lines: list[str] = []
    lines.append(f"epic: {epic_id}")
    lines.append("")
    lines.append(f"{'slice':<20} {'status':<12} {'ready':<8} {'deps_missing'}")
    lines.append(f"{'-----':<20} {'------':<12} {'-----':<8} {'------------'}")

    for child in children:
        slice_name = child.get("slice", "?")
        status = child.get("status", "?")
        deps = child.get("depends_on", [])

        ready_fields = [k for k in ("outcomes_ready", "architecture_ready", "core_runtime_ready", "orchestration_ui_ready") if child.get(k)]
        ready_str = "Y" if ready_fields else "-"

        deps_missing = ",".join(deps) if deps else "-"
        lines.append(f"{slice_name:<20} {status:<12} {ready_str:<8} {deps_missing}")

    return "\n".join(lines)
