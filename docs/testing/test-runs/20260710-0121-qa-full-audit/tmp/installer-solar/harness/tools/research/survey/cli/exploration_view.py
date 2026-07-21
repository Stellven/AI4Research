"""CLI view for ExplorationRunResult — formats exploration gate output for display.

Pure functions that transform an ``ExplorationRunResult`` into CLI table
rows or a JSON-serializable dict.  No external I/O, no randomness.
"""

from __future__ import annotations

from ..schemas import ExplorationRunResult, to_dict


def format_exploration(result: ExplorationRunResult) -> str:
    """Format an ``ExplorationRunResult`` as human-readable CLI rows.

    Returns a multi-line string with proposed/eliminated/selected counts,
    per-direction details, and elimination log path.
    """
    total_proposed = len(result.selected_directions) + len(result.eliminated_directions)
    selected_count = len(result.selected_directions)
    eliminated_count = len(result.eliminated_directions)

    lines: list[str] = []
    lines.append(f"run_id:               {result.run_id}")
    lines.append(f"proposed_count:       {total_proposed}")
    lines.append(f"selected_count:       {selected_count}")
    lines.append(f"eliminated_count:     {eliminated_count}")
    lines.append(f"elimination_log_path: {result.elimination_log_path}")

    # Selected directions
    if result.selected_directions:
        lines.append("selected_directions:")
        for d in result.selected_directions:
            lines.append(f"  - [{d.direction_id}] {d.direction_name} ({d.status})")
            if d.source_matrix:
                lines.append(f"    source_matrix: {d.source_matrix.section_id}")

    # Eliminated directions
    if result.eliminated_directions:
        lines.append("eliminated_directions:")
        for d in result.eliminated_directions:
            reason = ""
            if d.elimination_record and d.elimination_record.kill_reason:
                reason = f" — {d.elimination_record.kill_reason}"
            lines.append(f"  - [{d.direction_id}] {d.direction_name}{reason}")

    return "\n".join(lines)


def to_dict_exploration(result: ExplorationRunResult) -> dict:
    """Convert an ``ExplorationRunResult`` to a JSON-serializable dict.

    Uses the shared ``to_dict`` helper for nested dataclass unwinding.
    """
    return to_dict(result)
