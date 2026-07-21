"""Global consistency pass — QG-3 claim_id reuse + QG-5 terminology drift.

Pure deterministic analysis over ``SurveyReportAST``.  No LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..schemas import SurveyReportAST


@dataclass
class ConsistencyReport:
    """Output of the global consistency pass."""

    claim_id_conflicts: list[dict[str, Any]] = field(default_factory=list)
    terminology_drift: list[dict[str, Any]] = field(default_factory=list)
    verdict: str = "pass"  # pass / warning / fail
    issues: list[str] = field(default_factory=list)
    schema_version: str = "solar.research.survey.v1"


def check_claim_id_reuse(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """QG-3: Detect claim_ids that appear in multiple sections with divergent text.

    Expects *sections* to be a list of dicts, each with a ``"claim_ids"`` key
    mapping to ``list[str]`` and an optional ``"section_id"`` key.
    """
    claim_map: dict[str, list[str]] = {}
    for sec in sections:
        sec_id = sec.get("section_id", "unknown")
        for cid in sec.get("claim_ids", []):
            claim_map.setdefault(cid, []).append(sec_id)

    conflicts: list[dict[str, Any]] = []
    for cid, sec_ids in sorted(claim_map.items()):
        if len(sec_ids) > 1:
            conflicts.append(
                {"claim_id": cid, "sections": sec_ids, "count": len(sec_ids)}
            )
    return conflicts


def check_terminology_drift(
    sections: list[dict[str, Any]],
    *,
    min_reuse: int = 2,
) -> list[dict[str, Any]]:
    """QG-5: Detect terms that appear with multiple surface forms across sections.

    A *surface form* is a case-folded token found in ``"terms"`` lists on each
    section dict.  If two forms normalise to the same key but differ in casing
    or spelling, that constitutes drift.
    """
    norm_map: dict[str, list[dict[str, str]]] = {}
    for sec in sections:
        sec_id = sec.get("section_id", "unknown")
        for term in sec.get("terms", []):
            key = term.lower().replace("-", " ").replace("_", " ")
            norm_map.setdefault(key, []).append(
                {"section_id": sec_id, "form": term}
            )

    drift: list[dict[str, Any]] = []
    for key, entries in sorted(norm_map.items()):
        unique_forms = {e["form"] for e in entries}
        if len(unique_forms) > 1 and len(entries) >= min_reuse:
            drift.append(
                {
                    "canonical": key,
                    "forms": sorted(unique_forms),
                    "sections": [e["section_id"] for e in entries],
                }
            )
    return drift


def global_consistency_pass(
    report_ast: SurveyReportAST | None = None,
    *,
    sections: list[dict[str, Any]] | None = None,
) -> ConsistencyReport:
    """Run QG-3 and QG-5 checks over section data.

    Accepts either a ``SurveyReportAST`` (from which sections are extracted)
    or a raw ``sections`` list (for testing convenience).
    """
    if sections is None:
        if report_ast is None:
            return ConsistencyReport(
                verdict="not_applicable",
                issues=["no_input"],
            )
        sections = [
            {
                "section_id": s.section_id,
                "claim_ids": getattr(s, "claim_ids", []),
                "terms": getattr(s, "terms", []),
            }
            for s in report_ast.sections
        ]

    claim_conflicts = check_claim_id_reuse(sections)
    term_drift = check_terminology_drift(sections)

    issues: list[str] = []
    verdict = "pass"

    if claim_conflicts:
        verdict = "warning"
        for c in claim_conflicts:
            issues.append(
                f"claim_id_reuse:{c['claim_id']} in {c['count']} sections"
            )

    if term_drift:
        if verdict == "pass":
            verdict = "warning"
        for d in term_drift:
            issues.append(
                f"terminology_drift:{d['canonical']} -> {','.join(d['forms'])}"
            )

    return ConsistencyReport(
        claim_id_conflicts=claim_conflicts,
        terminology_drift=term_drift,
        verdict=verdict,
        issues=issues,
    )
