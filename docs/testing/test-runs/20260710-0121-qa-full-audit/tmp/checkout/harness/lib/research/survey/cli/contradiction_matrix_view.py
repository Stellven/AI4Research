"""CLI view for ContradictionMatrix — formats gate output for display.

Pure functions that transform contradiction matrix data into CLI summary
rows or a JSON-serializable dict.  No external I/O, no randomness.

The view accepts the gate result dict (from ``controversy_gate``) which
contains ``rows``, ``decorative``, ``verdict`` and related fields.  It does
NOT re-compute decorative status — it reads the provided ``is_decorative``
or ``decorative`` field directly.
"""

from __future__ import annotations

from ..schemas import to_dict


def format_contradiction_matrix(gate_result: dict) -> str:
    """Format a controversy gate result as human-readable CLI rows.

    Parameters
    ----------
    gate_result:
        Dict returned by ``controversy_gate()`` with keys: verdict,
        verdict_reasons, matrix_row_count, decorative, rows.
    """
    lines: list[str] = []
    verdict = gate_result.get("verdict", "unknown")
    row_count = gate_result.get("matrix_row_count", 0)
    is_decorative = gate_result.get("decorative", False)
    rows = gate_result.get("rows", [])

    lines.append(f"verdict:              {verdict}")
    lines.append(f"total_claims:         {row_count}")

    # Counts from rows
    total_supporting = sum(r.get("supporting_count", 0) for r in rows)
    total_contradicting = sum(r.get("contradicting_count", 0) for r in rows)
    total_uncertain = sum(r.get("uncertain_count", 0) for r in rows)

    claims_with_negative = sum(
        1 for r in rows if r.get("contradicting_count", 0) > 0
    )
    lines.append(f"claims_with_negative: {claims_with_negative}")

    # Decorative warning
    if is_decorative:
        lines.append("[WARN] decorative matrix — no synthesis references found")

    # Per-claim summary
    for row in rows:
        cid = row.get("claim_id", "?")
        sup = row.get("supporting_count", 0)
        con = row.get("contradicting_count", 0)
        unc = row.get("uncertain_count", 0)
        ref = "Y" if row.get("synthesis_referenced") else "N"
        lines.append(
            f"  claim={cid}  sup={sup} con={con} unc={unc} ref={ref}"
        )

    # Verdict reasons
    for reason in gate_result.get("verdict_reasons", []):
        lines.append(f"reason:               {reason}")

    return "\n".join(lines)


def to_dict_contradiction_matrix(gate_result: dict) -> dict:
    """Return the gate result dict as-is (already JSON-serializable).

    The ``controversy_gate`` already returns a plain dict, so this
    function is an identity pass-through with type normalization.
    """
    return dict(gate_result)
