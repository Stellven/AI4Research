"""Build the synthesis plan `grounded_synthesis` compiles a report from.

`compile_grounded_report` takes a source pack and a plan. The pack now comes
from validated_pack.py; this builds the plan, so the workflow can stop using
its own report assembler -- the one that emitted every findings heading twice.

The plan schema is `solar.grounded_synthesis_plan.v2`:

    {schema_version, evidence_status, evidence_gaps,
     sections: [{section_id, title,
                 claims: [{text, uncertainty,
                           evidence_links: [{evidence_id, relation}]}]}]}

Two details of that schema matter more than the shape.

`relation` is one of supports / contradicts / qualifies / contextualizes, so
disagreement between sources is a first-class part of a claim rather than
something a later pass has to infer. Our synthesis claims currently carry only
supporting ids, so every link is written as "supports" and nothing is invented
-- but the field is where contradiction belongs once claim_compiler is wired,
and stating that here is cheaper than rediscovering it later.

`uncertainty` is required per claim and the compiler refuses a claim without
it. That is the right constraint and this module does not paper over it: a
claim with no recorded uncertainty is reported, not given a placeholder.
"""
from __future__ import annotations

import re
from typing import Any

SCHEMA = "solar.grounded_synthesis_plan.v2"


class SynthesisPlanError(Exception):
    """The claims cannot be expressed as a valid plan, and nothing was faked."""


def _evidence_ids_for(claim: dict[str, Any]) -> list[str]:
    raw = claim.get("evidence_ids") or claim.get("source_ids") or []
    return [str(item).strip() for item in raw if str(item).strip()]


def evidence_index(evidence_rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Map every id a claim might cite to the pack's evidence ids.

    write_source_pack mints content-addressed evidence ids (`ev_<hash>`) while
    claims cite the source id they came from. Those are different id spaces, and
    treating them as one makes every claim look like it cites missing evidence.
    Both keys are indexed so a claim resolves whichever it names.
    """
    index: dict[str, list[str]] = {}
    for row in evidence_rows:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        for key in (evidence_id, str(row.get("source_id") or "").strip()):
            if key:
                index.setdefault(key, []).append(evidence_id)
    return index


_SAFE_SECTION_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _section_id(title: str, taken: set[str]) -> str:
    """A section id the compiler will accept, derived from the theme.

    `grounded_synthesis` requires `^[A-Za-z0-9_.-]+$` and refuses duplicates, so
    an unslugged theme would abort the whole compile rather than degrade.
    """
    base = _SAFE_SECTION_ID_RE.sub("-", str(title or "").strip().lower()).strip("-")
    base = base or "section"
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"
        suffix += 1
    taken.add(candidate)
    return candidate


def _claim_theme(claim: dict[str, Any]) -> str:
    for key in ("theme", "section", "section_title", "topic"):
        value = " ".join(str(claim.get(key) or "").split())
        if value:
            return value
    return ""


def build_plan(
    *,
    claims: list[dict[str, Any]],
    evidence_index: dict[str, list[str]],
    section_title: str = "Findings",
) -> dict[str, Any]:
    """Express validated claims as a plan, or say why they cannot be.

    Claims citing evidence the pack does not contain are dropped and reported
    as gaps rather than carried into a report that appears to cite them. That
    is the same failure the relevance work was about, one layer along: a
    citation to something absent reads exactly like a citation to something
    present.
    """
    sections: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    # (theme, claim). The theme is whatever the synthesis operator labelled the
    # claim with; grouping happens after validation so a dropped claim cannot
    # leave an empty section behind.
    usable: list[tuple[str, dict[str, Any]]] = []

    for index, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or f"claim-{index:03d}")
        text = " ".join(str(claim.get("text") or "").split())
        if not text:
            gaps.append({"text": f"{claim_id} carries no claim text", "evidence_ids": []})
            continue

        cited = _evidence_ids_for(claim)
        # The quote the synthesis operator verified against the source text.
        # compile_grounded_report re-checks it as an exact substring of the
        # evidence content and hashes it into the report, so a claim without
        # one cannot be published -- which is the point.
        quote_by_source = {
            str(row.get("source_id") or ""): str(row.get("quote") or "")
            for row in (claim.get("evidence_quotes") or [])
            if isinstance(row, dict)
        }
        present: list[tuple[str, str]] = []
        missing: list[str] = []
        unquoted: list[str] = []
        for citation in cited:
            resolved = evidence_index.get(citation) or []
            if not resolved:
                missing.append(citation)
                continue
            quote = quote_by_source.get(citation) or ""
            if not quote:
                unquoted.append(citation)
                continue
            for eid in resolved:
                if all(eid != existing for existing, _ in present):
                    present.append((eid, quote))
        if unquoted:
            gaps.append({
                "text": (
                    f"{claim_id} cites sources with no verified supporting quote: "
                    + ", ".join(sorted(unquoted))
                ),
                "evidence_ids": sorted(unquoted),
            })
        if missing:
            gaps.append({
                "text": (
                    f"{claim_id} cites evidence absent from the source pack: "
                    + ", ".join(sorted(missing))
                ),
                "evidence_ids": sorted(missing),
            })
        if not present:
            continue

        uncertainty = claim.get("uncertainty")
        if isinstance(uncertainty, list):
            uncertainty = " ".join(str(item).strip() for item in uncertainty if str(item).strip())
        uncertainty = " ".join(str(uncertainty or "").split())
        if not uncertainty:
            # The compiler requires it and a placeholder would be a claim about
            # confidence that nobody made.
            gaps.append({
                "text": f"{claim_id} records no uncertainty and cannot be published as stated",
                "evidence_ids": sorted(eid for eid, _ in present),
            })
            continue

        usable.append((_claim_theme(claim), {
            "text": text,
            "uncertainty": uncertainty,
            "evidence_links": [
                # Only supporting links are asserted: the upstream claim model
                # records supporting ids only. contradicts/qualifies belong
                # here and are left to claim_compiler rather than guessed.
                {"evidence_id": eid, "relation": "supports", "quote": quote}
                for eid, quote in present
            ],
        }))

    # One section per theme, in the order the themes first appear, so the report
    # follows the synthesis rather than a re-sort nobody asked for. A run whose
    # claims carry no theme collapses to the single section this produced
    # before, which is why an unlabelled synthesis still compiles.
    taken: set[str] = set()
    grouped: dict[str, dict[str, Any]] = {}
    for theme, claim_payload in usable:
        title = theme or section_title
        bucket = grouped.get(title)
        if bucket is None:
            bucket = {"section_id": _section_id(title, taken), "title": title, "claims": []}
            grouped[title] = bucket
        bucket["claims"].append(claim_payload)
    sections.extend(grouped.values())

    status = "sufficient" if sections else "insufficient"
    if status == "insufficient" and not gaps:
        gaps.append({"text": "No claim survived validation against the source pack", "evidence_ids": []})

    return {
        "schema_version": SCHEMA,
        "evidence_status": status,
        "evidence_gaps": gaps,
        "sections": sections,
    }
