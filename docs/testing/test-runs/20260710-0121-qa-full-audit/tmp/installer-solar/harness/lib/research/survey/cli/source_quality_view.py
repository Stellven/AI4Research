"""CLI view for SourceQualityDistribution — formats gate output for display.

Pure functions that transform a ``SourceQualityDistribution`` into CLI table
rows or a JSON-serializable dict.  No external I/O, no randomness.
"""

from __future__ import annotations

from ..schemas import SourceQualityDistribution, to_dict


def format_source_quality(dist: SourceQualityDistribution) -> str:
    """Format a ``SourceQualityDistribution`` as human-readable CLI rows.

    Returns a multi-line string with key metrics and stuffing alert summary.
    """
    lines: list[str] = []
    lines.append(f"section_id:          {dist.section_id}")
    lines.append(f"verdict:             {dist.verdict}")

    # Canonical coverage
    covered = [t for t, ok in dist.canonical_coverage.items() if ok]
    missing = [t for t, ok in dist.canonical_coverage.items() if not ok]
    lines.append(f"canonical_coverage:  {len(covered)}/{len(dist.canonical_coverage)} covered"
                 + (f" (missing: {','.join(missing)})" if missing else ""))

    # Primary ratio
    lines.append(f"primary_ratio:       {dist.primary_ratio:.2f}")

    # Source type counts
    type_parts = [f"{k}={v}" for k, v in sorted(dist.source_type_counts.items())]
    lines.append(f"source_types:        {' '.join(type_parts)}")

    # Stuffing alerts
    lines.append(f"stuffing_alerts:     {len(dist.stuffing_alerts)}")
    for alert in dist.stuffing_alerts:
        lines.append(f"  - domain={alert.domain} count={alert.count}")

    # Verdict reasons
    if dist.verdict_reasons:
        for reason in dist.verdict_reasons:
            lines.append(f"reason:              {reason}")

    return "\n".join(lines)


def to_dict_source_quality(dist: SourceQualityDistribution) -> dict:
    """Convert a ``SourceQualityDistribution`` to a JSON-serializable dict.

    Uses the shared ``to_dict`` helper for nested dataclass unwinding.
    """
    return to_dict(dist)
