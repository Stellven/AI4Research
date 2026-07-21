"""CLI view for ArgumentDensityProfile — formats gate output for display.

Pure functions that transform an ``ArgumentDensityProfile`` into CLI table
rows or a JSON-serializable dict.  No external I/O, no randomness.
"""

from __future__ import annotations

from ..schemas import ArgumentDensityProfile, to_dict


def format_argument_density(profile: ArgumentDensityProfile) -> str:
    """Format an ``ArgumentDensityProfile`` as human-readable CLI rows.

    Returns a multi-line string with per-dimension coverage, density score,
    low-density section flags, and not-applicable entries.
    """
    lines: list[str] = []
    lines.append(f"section_id:      {profile.section_id}")
    lines.append(f"density_score:   {profile.density_score:.2f}")

    # Per-dimension coverage table
    dim_names = [
        "mechanism_comparison",
        "method_taxonomy",
        "evaluation_protocol",
        "failure_negative_evidence",
        "engineering_implication",
    ]
    lines.append("dimensions:")
    for dim in dim_names:
        status = profile.dimension_coverages.get(dim, "absent")
        indicator_count = sum(
            1 for ind in profile.detected_indicators if ind.dimension == dim
        )
        lines.append(f"  {dim}: {status}" + (f" ({indicator_count} indicators)" if indicator_count else ""))

    # Low density sections (from issues)
    low_density = [
        issue for issue in profile.issues if "low_density" in issue
    ]
    if low_density:
        lines.append(f"low_density_flags: {len(low_density)}")
        for issue in low_density:
            lines.append(f"  - {issue}")

    # Not-applicable entries
    if profile.not_applicable_entries:
        lines.append(f"not_applicable: {len(profile.not_applicable_entries)}")
        for entry in profile.not_applicable_entries:
            lines.append(f"  - {entry.dimension}: {entry.reason}")

    # General issues (non-low-density)
    other_issues = [
        issue for issue in profile.issues if "low_density" not in issue
    ]
    if other_issues:
        lines.append(f"issues: {len(other_issues)}")
        for issue in other_issues:
            lines.append(f"  - {issue}")

    return "\n".join(lines)


def to_dict_argument_density(profile: ArgumentDensityProfile) -> dict:
    """Convert an ``ArgumentDensityProfile`` to a JSON-serializable dict.

    Uses the shared ``to_dict`` helper for nested dataclass unwinding.
    """
    return to_dict(profile)
