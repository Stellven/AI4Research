"""Convert AutoSci raw paper data to `research_paper.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


def _sections(raw: dict[str, Any], source_ref: str) -> list[dict[str, Any]]:
    raw_sections = raw.get("sections")
    if isinstance(raw_sections, list) and raw_sections:
        return list(raw_sections)
    abstract = str(raw.get("abstract") or "").strip()
    if str(raw.get("parse_status") or "") == "failed" or str(raw.get("status") or "") == "failed":
        return [
            {
                "section_id": "parse-failure",
                "title": "Parse Failure",
                "text": abstract or f"No source text was extracted from {source_ref}.",
                "source_anchor": f"{source_ref}#parse-failure",
            }
        ]
    if abstract:
        return [
            {
                "section_id": "abstract",
                "title": "Abstract",
                "text": abstract,
                "source_anchor": f"{source_ref}#abstract",
            }
        ]
    return [
        {
            "section_id": "unparsed-source",
            "title": "Unparsed Source",
            "text": "No abstract or section text was provided by the source parser.",
            "source_anchor": f"{source_ref}#unparsed-source",
        }
    ]


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    source_ref = str(raw.get("source_ref") or "unknown-source")
    paper = {
        "paper_id": str(raw.get("paper_id") or "paper-unresolved"),
        "title": str(raw.get("title") or "Unresolved paper source"),
        "source_type": str(raw.get("source_type") or "markdown"),
        "source_ref": source_ref,
        "identifiers": dict(raw.get("identifiers") or {}),
        "abstract": str(raw.get("abstract") or ""),
        "parse_status": str(raw.get("parse_status") or "parsed"),
        "sections": _sections(raw, source_ref),
    }
    if isinstance(raw.get("analysis"), dict):
        paper["analysis"] = dict(raw["analysis"])
    if isinstance(raw.get("preparation"), dict):
        paper["preparation"] = dict(raw["preparation"])
    if isinstance(raw.get("source_contract"), dict):
        paper["source_contract"] = dict(raw["source_contract"])
    if isinstance(raw.get("provenance"), dict):
        paper["provenance"] = dict(raw["provenance"])
    outputs = {"paper": paper}
    if isinstance(raw.get("final_source_registration_boundary"), dict):
        boundary = dict(raw["final_source_registration_boundary"])
        paper["final_source_registration_boundary"] = boundary
        outputs["final_source_registration_boundary"] = boundary
    return evidence_base(
        "research_paper.v1",
        envelope,
        outputs,
        artifacts=list(raw.get("artifacts") or []),
        status=str(raw.get("status") or "completed"),
        limitations=list(raw.get("limitations") or ["fixture-mode adapter output; not a production AutoSci run"]),
    )
