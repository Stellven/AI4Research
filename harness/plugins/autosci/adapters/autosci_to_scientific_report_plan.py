"""Convert AutoSci report-planning data to `scientific_report_plan.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    limitations = list(raw.get("limitations") or [])
    sections = []
    for index, item in enumerate(raw.get("sections") or []):
        if not isinstance(item, dict):
            continue
        sections.append({
            "section_id": str(item.get("section_id") or f"section-{index + 1}"),
            "title": str(item.get("title") or f"Section {index + 1}"),
            "purpose": str(item.get("purpose") or item.get("body") or "Describe the planned section."),
            "evidence_ids": [
                str(evidence_id)
                for evidence_id in item.get("evidence_ids") or []
                if str(evidence_id).strip()
            ],
        })
    report_plan = {
        "report_id": str(raw.get("report_id") or "report-plan-001"),
        "title": str(raw.get("title") or "AutoSci Report Plan"),
        "audience": str(raw.get("audience") or "researcher"),
        "sections": sections,
        "supported_claim_ids": [
            str(claim_id)
            for claim_id in raw.get("supported_claim_ids") or []
            if str(claim_id).strip()
        ],
        "excluded_claim_ids": [
            str(claim_id)
            for claim_id in raw.get("excluded_claim_ids") or []
            if str(claim_id).strip()
        ],
        "evidence_ids": [
            str(evidence_id)
            for evidence_id in raw.get("evidence_ids") or []
            if str(evidence_id).strip()
        ],
    }
    if isinstance(raw.get("study_protocol"), dict):
        report_plan["study_protocol"] = raw["study_protocol"]
    return evidence_base(
        "scientific_report_plan.v1",
        envelope,
        {"report_plan": report_plan},
        artifacts=list(raw.get("artifacts") or []),
        status=str(raw.get("status") or "completed"),
        limitations=limitations,
    )
