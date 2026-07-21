"""CLI view for GateReport — formats aggregated gate output for display.

Pure functions that transform a ``GateReport`` into a 4-gate verdict table
with artifact paths and summary, or a JSON-serializable dict.  No external
I/O, no randomness.
"""

from __future__ import annotations

from ..schemas import GateReport, to_dict


def format_gate_report(report: GateReport) -> str:
    """Format a ``GateReport`` as human-readable CLI output.

    Prints a verdict table for each registered gate, lists artifact paths,
    and shows a summary line with overall status and partial-verdict count.
    """
    lines: list[str] = []

    # Header
    lines.append(f"report_id:  {report.report_id}")

    # 4-gate verdict table
    lines.append("")
    lines.append("gate               verdict")
    lines.append("----               -------")
    for gate_id, gv in sorted(report.gate_verdicts.items()):
        lines.append(f"{gate_id:<19}{gv.verdict}")

    # Artifact paths
    if report.artifact_paths:
        lines.append("")
        lines.append("artifact_paths:")
        for key, path in sorted(report.artifact_paths.items()):
            lines.append(f"  {key}: {path}")

    # Summary
    verdicts = [gv.verdict for gv in report.gate_verdicts.values()]
    worst = "pass"
    for v in verdicts:
        if v == "fail":
            worst = "fail"
            break
        if v == "warning" and worst != "fail":
            worst = "warning"
        if v == "not_applicable" and worst == "pass":
            worst = "pass"

    partial = getattr(report, "partial_verdicts", [])
    lines.append("")
    lines.append(f"summary:            {worst}")
    if partial:
        lines.append(f"partial_verdicts:   {','.join(partial)}")

    return "\n".join(lines)


def to_dict_gate_report(report: GateReport) -> dict:
    """Convert a ``GateReport`` to a JSON-serializable dict.

    Uses the shared ``to_dict`` helper for nested dataclass unwinding.
    """
    d = to_dict(report)
    # Include partial_verdicts if attached (dynamic attribute from N7)
    partial = getattr(report, "partial_verdicts", None)
    if partial is not None:
        d["partial_verdicts"] = list(partial)
    return d
