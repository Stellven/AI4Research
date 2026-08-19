#!/usr/bin/env python3
"""Independent gate for research.evidence_to_poc.v1 artifacts.

Every stage of this workflow currently grades its own homework. The contract
declares ``evaluator_gate: {"kind": "none"}`` on all fifteen stages, so Solar
records a PASS with ``verdict_kind: content`` and
``proof_level: independent_verification`` for a stage nothing checked, in
0.0 seconds, having run no command. An operator that reports a false result
cannot be caught by construction.

This script is that missing check. It is deliberately **not** a second opinion
from a model: it recomputes the operator's own claims from the artifacts and
fails when they do not hold.

Design constraints, in order of importance:

* **Never trust the operator's verdict field.** `source_validation.json` records
  a `validation.relevance.class` per accepted source. That field is the thing
  under test, so it is read for comparison and never used as the answer. The
  relevance decision is recomputed here from the request and the source text.
* **Scoped to this workflow.** It reads only this contract's artifact paths and
  is bound only from this contract, so no other workflow's behaviour changes.
* **Fail closed, and say which item failed.** A gate that reports "something is
  wrong" costs as much time as no gate at all.

Modes mirror the shape rsi_demo's validator uses, so a stage can gate on the
part it is responsible for:

    --sources-only   accepted sources really are on topic, and traceable
    --claims-only    every report claim cites a source that was accepted
    (no flag)        both
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[1]
if str(HARNESS / "plugins" / "autosci") not in sys.path:
    sys.path.insert(0, str(HARNESS / "plugins" / "autosci"))

from operators.research_synthesis.base import subject_terms  # noqa: E402

ARTIFACT_ROOT = Path("artifacts/research_evidence_to_poc")
SOURCE_VALIDATION = ARTIFACT_ROOT / "validation" / "source_validation.json"
SEED_SNAPSHOT = ARTIFACT_ROOT / "seed" / "seed_snapshot.json"
EVIDENCE_SYNTHESIS = ARTIFACT_ROOT / "synthesis" / "evidence_synthesis.json"
REPORT_DRAFT = ARTIFACT_ROOT / "report" / "report_draft.json"
REPORT_MD = ARTIFACT_ROOT / "report" / "report.md"

# A claim reference in the report body, e.g. "claim-003" or "openalex-rag-01".
_CLAIM_RE = re.compile(r"\bclaim-\d+\b")


def resolve_workspace(given: Path) -> Path:
    """Find the directory that actually contains the artifact root.

    `<resolved_root>` substitutes to the PARENT of the contract's canonical
    root. rsi_demo's canonical is `sprints/<sid>/workdir/<report-dir>/`, so its
    parent is the workdir and its validator's assumption holds. This contract's
    canonical is already `sprints/<sid>/workdir/`, so the parent overshoots by
    one level and the artifacts sit in a child.

    Rather than encode either assumption, look for the artifact root at the
    given path and one level down. A gate that reports "file missing" because
    it was handed the wrong directory is a false failure indistinguishable from
    a real one, and with on_fail: fail it would block every run.
    """
    given = given.expanduser()
    candidates = [given, given / "workdir"]
    # The gate executes with cwd set to the harness root, while <resolved_root>
    # is relative to the SPRINTS root. Those are the same directory in a normal
    # install and different under the UAT layout, where the harness lives in
    # runtime-harness/ beside the sprints tree. A relative workspace then
    # resolves under the harness, where no sprint exists.
    if not given.is_absolute() or not (given / ARTIFACT_ROOT).is_dir():
        sprints_root = os.environ.get("HARNESS_SPRINTS_DIR") or os.environ.get("SOLAR_HARNESS_SPRINTS_DIR")
        rel = Path(*given.parts[1:]) if given.parts and given.parts[0] == "sprints" else given
        if sprints_root:
            base = Path(sprints_root).expanduser()
            candidates += [base / rel, base / rel / "workdir"]
        for anchor in (Path.cwd(), Path.cwd().parent):
            candidates += [anchor / given, anchor / given / "workdir"]
    for candidate in candidates:
        if (candidate / SOURCE_VALIDATION).is_file() or (candidate / ARTIFACT_ROOT).is_dir():
            return candidate
    return given


def _load(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _claims(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Claims live under `outputs` in evidence_synthesis, top-level elsewhere."""
    for holder in (payload, payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}):
        rows = holder.get("claims") if isinstance(holder, dict) else None
        if isinstance(rows, list) and rows:
            return [row for row in rows if isinstance(row, dict)]
    return []


def _request_text(workspace: Path) -> str:
    """The research request, as the seed snapshot recorded it."""
    seed = _load(workspace / SEED_SNAPSHOT) or {}
    for key in ("request", "topic", "query"):
        value = str(seed.get(key) or "").strip()
        if value:
            return value
    for entry in seed.get("seeds") or []:
        if isinstance(entry, dict):
            value = str(entry.get("content") or "").strip()
            if value:
                return value
    return ""


def check_sources(workspace: Path) -> list[str]:
    """Recompute relevance for every accepted source.

    This is the check that would have caught the worst defect this workflow
    had: a CRISPR request accepting seven Retrieval-Augmented Generation
    papers, none about CRISPR, and writing a report from them. The operator
    recorded `relevance.class: content_described` for each. That record is
    exactly what must not be believed.
    """
    failures: list[str] = []
    payload = _load(workspace / SOURCE_VALIDATION)
    if payload is None:
        return [f"source_validation_unreadable:{SOURCE_VALIDATION}"]

    accepted = [item for item in (payload.get("accepted") or []) if isinstance(item, dict)]
    declared = payload.get("accepted_count")
    if isinstance(declared, int) and declared != len(accepted):
        failures.append(f"accepted_count_mismatch:declared={declared},actual={len(accepted)}")

    request = _request_text(workspace)
    if not request:
        # No request means relevance is uncheckable. Say so rather than passing.
        failures.append("request_text_missing:relevance_cannot_be_recomputed")
        return failures

    wanted = subject_terms(request)
    for index, source in enumerate(accepted):
        source_id = str(source.get("source_id") or f"index-{index}")
        haystack = " ".join(
            str(source.get(key) or "")
            for key in ("title", "content_summary", "canonical_id", "url")
        )
        if wanted and not (wanted & subject_terms(haystack)):
            claimed = (
                ((source.get("validation") or {}).get("relevance") or {}).get("class")
                if isinstance(source.get("validation"), dict)
                else None
            )
            failures.append(
                f"accepted_source_off_topic:{source_id}"
                f":operator_recorded={claimed}:no_subject_overlap_with_request"
            )
        if not str(source.get("canonical_id") or source.get("url") or "").strip():
            failures.append(f"accepted_source_untraceable:{source_id}:no_canonical_id_or_url")
    return failures


def check_claims(workspace: Path) -> list[str]:
    """Every claim the report makes must cite a source that survived validation.

    A report can be perfectly formatted, cite an id in every sentence, and cite
    ids that were rejected or never existed. Linkage is only meaningful against
    the accepted set.
    """
    failures: list[str] = []
    validation = _load(workspace / SOURCE_VALIDATION)
    draft = _load(workspace / REPORT_DRAFT)
    if validation is None:
        return [f"source_validation_unreadable:{SOURCE_VALIDATION}"]
    if draft is None:
        return [f"report_draft_unreadable:{REPORT_DRAFT}"]

    accepted_ids = {
        str(item.get("source_id") or "").strip()
        for item in (validation.get("accepted") or [])
        if isinstance(item, dict)
    } - {""}
    rejected_ids = {
        str(item.get("source_id") or "").strip()
        for item in (validation.get("rejected") or [])
        if isinstance(item, dict)
    } - {""}

    claims = _claims(draft) or _claims(_load(workspace / EVIDENCE_SYNTHESIS) or {})
    if not claims:
        return ["no_claims_found:nothing_to_verify"]

    # Sources by id, so a claim can be checked against what it actually cites.
    by_id = {
        str(item.get("source_id") or "").strip(): item
        for item in (validation.get("accepted") or [])
        if isinstance(item, dict)
    }

    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            failures.append(f"claim_malformed:index={index}")
            continue
        claim_id = str(claim.get("claim_id") or f"index-{index}")
        cited = [
            str(item).strip()
            for item in (claim.get("evidence_ids") or claim.get("source_ids") or [])
            if str(item).strip()
        ]
        if not cited:
            failures.append(f"claim_uncited:{claim_id}")
            continue
        text = str(claim.get("text") or claim.get("statement") or "").strip()
        if not text:
            failures.append(f"claim_has_no_text:{claim_id}")
        for source_id in cited:
            if source_id in rejected_ids:
                failures.append(f"claim_cites_rejected_source:{claim_id}->{source_id}")
            elif source_id not in accepted_ids:
                failures.append(f"claim_cites_unknown_source:{claim_id}->{source_id}")
        # Linkage is not support. A claim can cite a real, accepted, on-topic
        # paper and misrepresent it entirely. Byte-level span verification is
        # the right check, but these claims carry source ids rather than text
        # spans, so the strongest available test is that the claim and at least
        # one cited source talk about the same subject. That catches gross
        # misattribution; it does not catch subtle misreading, and the gap is
        # why claims need spans.
        if text and cited:
            subjects = subject_terms(text)
            grounded = any(
                subjects & subject_terms(
                    " ".join(
                        str((by_id.get(sid) or {}).get(key) or "")
                        for key in ("title", "content_summary")
                    )
                )
                for sid in cited
            )
            if subjects and not grounded:
                failures.append(
                    f"claim_not_grounded_in_cited_sources:{claim_id}:cites={cited}"
                )

    # A report body that references claim ids the draft never defined is the
    # same failure one layer up.
    report_md = workspace / REPORT_MD
    if report_md.is_file():
        defined = {
            str(claim.get("claim_id") or "").strip()
            for claim in claims
            if isinstance(claim, dict)
        } - {""}
        try:
            body = report_md.read_text(encoding="utf-8")
        except OSError:
            body = ""
        for referenced in sorted(set(_CLAIM_RE.findall(body))):
            if defined and referenced not in defined:
                failures.append(f"report_references_undefined_claim:{referenced}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--sources-only", action="store_true")
    parser.add_argument("--claims-only", action="store_true")
    args = parser.parse_args(argv)

    workspace = resolve_workspace(Path(args.workspace))
    run_sources = args.sources_only or not args.claims_only
    run_claims = args.claims_only or not args.sources_only

    failures: list[str] = []
    if run_sources:
        failures.extend(check_sources(workspace))
    if run_claims:
        failures.extend(check_claims(workspace))

    verdict = {
        "schema": "solar.evidence_to_poc_gate.v1",
        "workspace": str(workspace),
        "checked": {"sources": run_sources, "claims": run_claims},
        "ok": not failures,
        "failures": failures,
    }
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
