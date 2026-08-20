"""Decide what the grounded compiler will accept, before asking it.

`compile_grounded_report` is strict and fails closed: the first link whose
quote is not byte-exact, or is 19 characters long, aborts the entire compile.
That strictness is correct for a component that certifies a report is grounded,
and it is Solar's, shared by other workflows, so it is not loosened here.

What is wrong is using an abort as the response to an ordinary research
outcome. Research at this scale always produces some evidence that will not
ground cleanly -- PDF ligatures, smart quotes, a model quoting across an
ellipsis, a claim whose support did not survive validation. Losing fifteen
stages of work over one link out of thirty is not rigour, it is brittleness.

So this module applies the compiler's rules non-fatally first. A link that
would abort the compile is dropped and recorded; a claim with no surviving
`supports` link is dropped and recorded; a section with no surviving claims is
dropped and recorded. What reaches the compiler then compiles, and the compiler
still certifies it byte-for-byte.

Two things this deliberately does NOT do:

* It does not silence attrition. Everything dropped is returned with its reason
  and counted, so a report that lost half its claims is visibly a report that
  lost half its claims rather than a smaller report that passed.
* It does not decide sufficiency. A floor belongs to the caller, because "too
  thin to publish" is a policy question, not a compiler rule. Without one, this
  module would turn every failure into a green run with one claim in it.

`contradicts` links are first-class here and are never attrition. A source that
disagrees with a claim is a finding the report exists to carry, and the
compiler already renders the relation.

The rule constants are imported from the compiler rather than restated. A
second copy of "quotes must be at least 20 characters" that drifts by one is
precisely the seam this module exists to close.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_LIB = Path(__file__).resolve().parents[4] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from research.grounded_synthesis import (  # noqa: E402
    _LINK_RELATIONS,
    _MAX_EVIDENCE_QUOTE_CHARS,
    _MIN_EVIDENCE_QUOTE_CHARS,
    _canonical_evidence_id,
    _tokens,
)

__all__ = ["admit_plan", "AdmissionReport"]


class AdmissionReport(dict):
    """Attrition record. A dict so it serialises straight into the artifact."""

    @property
    def claim_retention(self) -> float:
        total = int(self["claims_in"])
        return 1.0 if not total else int(self["claims_out"]) / total


def _link_rejection(
    link: Any,
    *,
    claim_text: str,
    evidence_by_id: dict[str, dict[str, Any]],
    evidence_aliases: dict[str, str],
    seen: set[str],
) -> tuple[str | None, str | None]:
    """Return (evidence_id, reason). `reason is None` means the compiler accepts it."""
    if not isinstance(link, dict):
        return None, "link_invalid: not an object"
    try:
        evidence_id = _canonical_evidence_id(
            link.get("evidence_id"),
            evidence_by_id=evidence_by_id,
            evidence_aliases=evidence_aliases,
        )
    except Exception as exc:  # the compiler's own resolution failure, made non-fatal
        return None, f"evidence_id_unresolved: {exc}"
    if evidence_id in seen:
        return evidence_id, "evidence_link_duplicate"
    relation = str(link.get("relation") or "").strip().lower()
    if relation not in _LINK_RELATIONS:
        return evidence_id, f"relation_invalid: {relation or '?'}"
    quote = str(link.get("quote") or "").strip()
    if not quote:
        return evidence_id, "quote_missing"
    if len(quote) < _MIN_EVIDENCE_QUOTE_CHARS:
        return evidence_id, f"quote_too_short: {len(quote)}<{_MIN_EVIDENCE_QUOTE_CHARS}"
    if len(quote) > _MAX_EVIDENCE_QUOTE_CHARS:
        return evidence_id, f"quote_too_long: {len(quote)}>{_MAX_EVIDENCE_QUOTE_CHARS}"
    evidence_text = str(evidence_by_id[evidence_id].get("content") or "")
    if quote not in evidence_text:
        # The seam the CRISPR run hit. After canonical_text the common cause is
        # gone, but PDF ligatures and smart quotes will reproduce it, and one
        # such quote must not cost the whole report.
        return evidence_id, "quote_not_exact"
    if not _tokens(claim_text).intersection(_tokens(quote)):
        return evidence_id, "quote_shares_no_term_with_claim"
    return evidence_id, None


def admit_plan(
    *, plan: dict[str, Any], evidence_rows: list[dict[str, Any]]
) -> tuple[dict[str, Any], AdmissionReport]:
    """Return a plan the compiler will accept, plus what was dropped and why."""
    evidence_by_id: dict[str, dict[str, Any]] = {}
    evidence_aliases: dict[str, str] = {}
    for row in evidence_rows:
        ev_id = str(row.get("evidence_id") or row.get("id") or "")
        if not ev_id:
            continue
        evidence_by_id[ev_id] = row
        evidence_aliases.setdefault(ev_id, ev_id)
        source_id = str(row.get("source_id") or "")
        if source_id:
            evidence_aliases.setdefault(source_id, ev_id)

    dropped_links: list[dict[str, Any]] = []
    dropped_claims: list[dict[str, Any]] = []
    dropped_sections: list[dict[str, Any]] = []
    claims_in = claims_out = links_in = links_out = 0
    contradiction_links = 0

    admitted_sections: list[dict[str, Any]] = []
    for section in plan.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_id") or "")
        kept_claims: list[dict[str, Any]] = []
        for claim in section.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            claims_in += 1
            claim_text = str(claim.get("text") or "")
            # build_plan emits text/uncertainty/evidence_links and drops
            # claim_id, because the compiler does not need it. An attrition
            # record that cannot name what it dropped is not a record, so the
            # claim text stands in as the identity.
            claim_id = str(claim.get("claim_id") or "").strip() or (
                f"{claim_text[:70]}..." if len(claim_text) > 70 else claim_text
            ) or "<untitled claim>"
            seen: set[str] = set()
            kept_links: list[dict[str, Any]] = []
            for link in claim.get("evidence_links") or []:
                links_in += 1
                evidence_id, reason = _link_rejection(
                    link,
                    claim_text=claim_text,
                    evidence_by_id=evidence_by_id,
                    evidence_aliases=evidence_aliases,
                    seen=seen,
                )
                if reason is not None:
                    dropped_links.append(
                        {
                            "section_id": section_id,
                            "claim_id": claim_id,
                            "evidence_id": evidence_id or "",
                            "reason": reason,
                        }
                    )
                    continue
                seen.add(str(evidence_id))
                links_out += 1
                if str(link.get("relation") or "").strip().lower() == "contradicts":
                    contradiction_links += 1
                kept_links.append(link)

            # The compiler requires at least one `supports` link. A claim whose
            # only surviving evidence contradicts it is not publishable as a
            # finding of the report -- but it is not silently discarded either.
            supports = [
                item
                for item in kept_links
                if str(item.get("relation") or "").strip().lower() == "supports"
            ]
            if not supports:
                dropped_claims.append(
                    {
                        "section_id": section_id,
                        "claim_id": claim_id,
                        "text": claim_text,
                        "reason": (
                            "no_surviving_support"
                            if kept_links
                            else "no_compilable_evidence_link"
                        ),
                        "surviving_relations": sorted(
                            {str(item.get("relation") or "") for item in kept_links}
                        ),
                    }
                )
                continue
            claims_out += 1
            kept_claims.append({**claim, "evidence_links": kept_links})

        if not kept_claims:
            dropped_sections.append({"section_id": section_id, "title": section.get("title")})
            continue
        admitted_sections.append({**section, "claims": kept_claims})

    admitted = {**plan, "sections": admitted_sections}
    report = AdmissionReport(
        claims_in=claims_in,
        claims_out=claims_out,
        links_in=links_in,
        links_out=links_out,
        contradiction_links=contradiction_links,
        sections_in=len(plan.get("sections") or []),
        sections_out=len(admitted_sections),
        dropped_links=dropped_links,
        dropped_claims=dropped_claims,
        dropped_sections=dropped_sections,
    )
    return admitted, report
