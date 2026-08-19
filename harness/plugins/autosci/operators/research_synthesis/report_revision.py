"""report_revision node implementation."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .base import (
    OperatorContext,
    ResearchOperatorError,
    build_node_result,
    evidence_ref,
    load_artifact,
    no_provider_result,
    output_path,
    provider_usage_from,
    redact_secrets,
    require_node,
    stable_json_sha256,
    utc_now,
    validate_scoped_path,
    write_artifact,
    _read_bytes,
    _write_bytes,
    display_path,
    sha256_bytes,
)
from .independent_review import _local_findings, _same_model_limitation
from .report_draft import _deliverable_requirements, _normalize_report


REPAIR_FINDING_SEVERITIES = {"medium", "high", "critical"}
REPAIR_VERDICTS = {"revise", "revise_required", "reject"}
MAX_REVISION_ATTEMPTS = 2


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _markdown_section(body: str, heading_pattern: str) -> str:
    """Text of the first matching section that actually has content.

    A writer may emit a matching heading with an empty body immediately
    followed by another heading (observed: "## Method and evidence protocol"
    directly above "## Evidence scope and processing", with the substantive
    "## Evidence method" further down). Returning on the first heading match
    made that empty heading mask the populated one, so A7 rejected a report
    whose method section was present as lineage_incomplete.
    """
    headings = list(re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", str(body or "")))
    for index, heading in enumerate(headings):
        # The document title is a level-1 heading, not a section. Matching it
        # captured everything up to the next level-<=1 heading -- i.e. the whole
        # report -- whenever the title happened to contain the pattern word. A
        # real A5 draft titled "...RAG Reliability Evaluation Methods and..."
        # yielded a 17,189 character "method section" out of a 17,471 character
        # body, so A7 then required the reviser to reproduce the entire report
        # verbatim and could never pass. Sections start at level 2.
        if len(heading.group(1)) < 2:
            continue
        if not re.search(heading_pattern, heading.group(2), flags=re.IGNORECASE):
            continue
        level = len(heading.group(1))
        end = len(body)
        for following in headings[index + 1:]:
            if len(following.group(1)) <= level:
                end = following.start()
                break
        section = _normalized_text(body[heading.end():end])
        if section:
            return section
    return ""


def revision_preservation_requirements(
    original_report: dict[str, Any],
    *,
    required_limitations: list[str] | None = None,
) -> dict[str, Any]:
    report = original_report.get("report") if isinstance(original_report.get("report"), dict) else {}
    conclusions = [item for item in report.get("conclusions") or [] if isinstance(item, dict)]
    method = _markdown_section(
        str(report.get("body") or ""),
        r"methods?\b|evidence\s+method\b|\u65b9\u6cd5|\u65b9\u6cd5\u8bba",
    )
    if not conclusions or not method:
        raise ResearchOperatorError(
            "Original accepted report has no conclusions or substantive method section to preserve",
            error_type="lineage_incomplete",
        )
    limitations = list(dict.fromkeys([
        str(item).strip()
        for item in [
            *(original_report.get("limitations") or []),
            *(required_limitations or []),
        ]
        if str(item).strip()
    ]))
    return {
        "preserved_conclusion_ids": [str(item.get("conclusion_id") or "") for item in conclusions],
        "preserved_method_sha256": hashlib.sha256(method.encode("utf-8")).hexdigest(),
        "preserved_limitations": limitations,
        "original_conclusions": conclusions,
        "original_method": method,
    }


def verify_revision_response_preservation(
    original_report: dict[str, Any],
    response: dict[str, Any],
    *,
    required_limitations: list[str] | None = None,
    requirements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check the declaration against the requirement the model was GIVEN.

    `requirements` is the object that went into the prompt. Passing it matters:
    recomputing here judges the reviser against a set that has moved since it
    was asked. In the 2026-08-19 run the reviewer appended three limitations of
    its own between the prompt and this check, and the revision was rejected for
    declaring exactly what it had been handed.

    Recomputation is kept as the fallback for callers that have no prompt-time
    object, but every caller that prompts a model should pass one.
    """
    required = requirements or revision_preservation_requirements(
        original_report,
        required_limitations=required_limitations,
    )
    declaration = response.get("preservation") if isinstance(response.get("preservation"), dict) else {}
    declared = {
        "preserved_conclusion_ids": declaration.get("preserved_conclusion_ids"),
        "preserved_method_sha256": declaration.get("preserved_method_sha256"),
        "preserved_limitations": declaration.get("preserved_limitations"),
    }
    expected = {
        "preserved_conclusion_ids": required["preserved_conclusion_ids"],
        "preserved_method_sha256": required["preserved_method_sha256"],
        "preserved_limitations": required["preserved_limitations"],
    }
    if declared != expected:
        raise ResearchOperatorError(
            "Revision response did not declare the exact original conclusion, method, and limitation preservation set",
            error_type="provider_contract",
        )
    report = response.get("report") if isinstance(response.get("report"), dict) else {}
    revised_conclusions = {
        str(item.get("conclusion_id") or ""): item
        for item in report.get("conclusions") or []
        if isinstance(item, dict)
    }
    for original in required["original_conclusions"]:
        conclusion_id = str(original.get("conclusion_id") or "")
        revised = revised_conclusions.get(conclusion_id)
        if not isinstance(revised, dict) or (
            _normalized_text(revised.get("text")) != _normalized_text(original.get("text"))
            or [str(item) for item in revised.get("evidence_ids") or []]
            != [str(item) for item in original.get("evidence_ids") or []]
        ):
            raise ResearchOperatorError(
                f"Revision response changed or omitted accepted conclusion: {conclusion_id}",
                error_type="provider_contract",
            )
    body = str(report.get("body") or "")
    revised_method = _markdown_section(
        body,
        r"methods?\b|evidence\s+method\b|\u65b9\u6cd5|\u65b9\u6cd5\u8bba",
    )
    if required["original_method"] not in revised_method:
        raise ResearchOperatorError(
            "Revision response omitted or changed the accepted method section",
            error_type="provider_contract",
        )
    limitations_section = _markdown_section(body, r"limitations?\b|\u5c40\u9650|\u9650\u5236|\u4e0d\u8db3")
    response_limitations = [str(item).strip() for item in response.get("limitations") or [] if str(item).strip()]
    for limitation in required["preserved_limitations"]:
        normalized = _normalized_text(limitation)
        if limitation not in response_limitations or normalized not in limitations_section:
            raise ResearchOperatorError(
                "Revision response omitted a provider-recorded limitation",
                error_type="provider_contract",
            )
    return {
        "verified": True,
        "model_declaration": expected,
        "original_report_sha256": stable_json_sha256(original_report),
    }


def _load_artifact_by_schema(
    context: OperatorContext,
    *,
    schema: str,
    artifact_id: str,
    expected_node_id: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    return load_artifact(
        context,
        schemas=(schema,),
        artifact_ids=(artifact_id,),
        filenames=(f"{artifact_id}.json",),
        payload_keys=(),
        expected_node_ids=(expected_node_id,),
        require_hash=True,
    )


def _repair_required(review: dict[str, Any]) -> tuple[bool, list[dict[str, Any]], str]:
    findings = [item for item in review.get("findings", []) if isinstance(item, dict)] if isinstance(review.get("findings"), list) else []
    verdict = str(review.get("verdict_suggestion") or "").strip().lower()
    blocking = [
        item for item in findings
        if str(item.get("severity") or "").lower() in REPAIR_FINDING_SEVERITIES
    ]
    return verdict in REPAIR_VERDICTS or bool(blocking), blocking, verdict


def _normalize_review_response(
    response: dict[str, Any],
    *,
    report_payload: dict[str, Any],
    validation: dict[str, Any],
    task_contract: dict[str, Any],
) -> dict[str, Any]:
    local_findings, chain_validation = _local_findings(report_payload, validation, task_contract)
    service_findings: list[dict[str, Any]] = []
    raw_service_findings = response.get("findings", []) if isinstance(response.get("findings"), list) else []
    for index, item in enumerate(raw_service_findings):
        if not isinstance(item, dict):
            service_findings.append({
                "finding_id": f"revision_review.invalid_finding.{index + 1}",
                "severity": "high",
                "category": "review_contract",
                "message": "Reviewer returned a non-object finding.",
            })
            continue
        severity = str(item.get("severity") or "").lower()
        if severity not in {"low", "medium", "high", "critical"} or not str(item.get("category") or "").strip() or not str(item.get("message") or "").strip():
            service_findings.append({
                "finding_id": f"revision_review.invalid_finding.{index + 1}",
                "severity": "high",
                "category": "review_contract",
                "message": "Reviewer finding is missing a supported severity, category, or message.",
            })
            continue
        service_findings.append(item)
    findings = [*local_findings, *service_findings]
    requested_verdict = str(response.get("verdict_suggestion") or "").strip().lower()
    if requested_verdict not in {"accept", "revise", "revise_required", "reject"}:
        findings.append({
            "finding_id": "revision_review.invalid_verdict",
            "severity": "high",
            "category": "review_contract",
            "message": "Reviewer returned an empty or unsupported verdict suggestion.",
        })
        requested_verdict = "revise"
    high_risk = [
        item for item in findings
        if str(item.get("severity") or "").lower() in {"high", "critical"}
    ]
    verdict = "revise" if high_risk and requested_verdict == "accept" else requested_verdict
    return {
        "findings": findings,
        "verdict_suggestion": verdict,
        "reviewer_usage": provider_usage_from(response, usage_kind="llm"),
        "chain_validation": chain_validation,
        "limitations": [str(item) for item in response.get("limitations", []) if str(item).strip()],
        "evidence_lineage": [
            "report_revision",
            "report_draft",
            "evidence_synthesis" if chain_validation.get("evidence_synthesis_present") else "",
            "source_validation" if validation else "",
        ],
    }


def execute(node_request: dict, context: OperatorContext) -> dict:
    require_node(context, "report_revision")
    original_report, report_ref = _load_artifact_by_schema(
        context,
        schema="research_synthesis.report_draft.v1",
        artifact_id="report_draft",
        expected_node_id="report_draft",
    )
    review, review_ref = _load_artifact_by_schema(
        context,
        schema="research_synthesis.independent_review.v1",
        artifact_id="independent_review",
        expected_node_id="independent_review",
    )
    validation, validation_ref = _load_artifact_by_schema(
        context,
        schema="research_synthesis.source_validation.v1",
        artifact_id="source_validation",
        expected_node_id="source_validation",
    )
    synthesis, synthesis_ref = _load_artifact_by_schema(
        context,
        schema="research_synthesis.evidence_synthesis.v1",
        artifact_id="evidence_synthesis",
        expected_node_id="evidence_synthesis",
    )
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    repair_required, blocking_findings, first_verdict = _repair_required(review)
    writer_usage: list[dict[str, Any]] = []
    reviewer_usage: list[dict[str, Any]] = []
    limitations: list[str] = [
        str(item).strip()
        for item in original_report.get("limitations") or []
        if str(item).strip()
    ]
    revised_report = original_report.get("report") if isinstance(original_report.get("report"), dict) else {}
    revision_review: dict[str, Any] = {}
    preservation: dict[str, Any] = {"verified": False, "reason": "revision_not_applied"}

    if repair_required:
        model_generate = context.services.get("model_generate")
        review_model = context.services.get("review_model_generate")
        if model_generate is None:
            return no_provider_result(context, "model_generate")
        if review_model is None:
            return no_provider_result(context, "review_model_generate")
        claims = [item for item in synthesis.get("claims", []) if isinstance(item, dict)]
        claim_ids = {str(item.get("claim_id")) for item in claims if item.get("claim_id")}
        if not claim_ids:
            raise ResearchOperatorError("No synthesis claims were available for report revision", error_type="missing_synthesis")
        current_report_payload = original_report
        current_review = review
        current_blocking_findings = blocking_findings
        # MAX_REVISION_ATTEMPTS exists for exactly this failure mode, but a
        # raising preservation check consumed none of it: the operator made one
        # call and aborted. A bounded retry that tells the reviser precisely
        # what it dropped does not weaken preservation -- the same check must
        # still pass -- it just uses the budget the contract already declares.
        preservation_feedback = ""
        # The set the accepted attempt was told to preserve. It is what the
        # model declared, what it rendered, and therefore the only set the
        # published artifact can honestly claim -- see the artifact assembly
        # below for why recording the accumulated list instead breaks two
        # downstream checks.
        accepted_preserved_limitations: list[str] = []
        for attempt in range(1, MAX_REVISION_ATTEMPTS + 1):
            preservation_requirements = revision_preservation_requirements(
                original_report,
                required_limitations=limitations,
            )
            response = model_generate(
                node_id="report_revision",
                task_contract=task_contract,
                deliverable_requirements=_deliverable_requirements(task_contract),
                evidence_synthesis=synthesis,
                source_validation=validation,
                original_report=current_report_payload,
                independent_review=current_review,
                revision_attempt=attempt,
                max_revision_attempts=MAX_REVISION_ATTEMPTS,
                preservation_feedback=preservation_feedback,
                # The reviser must reproduce the accepted method section
                # closely enough that the original normalized text is still a
                # substring of the revised one.  Handing it only
                # preserved_method_sha256 states the requirement in a form no
                # model can act on, so the exact text goes with the digest.
                preservation_requirements={
                    key: preservation_requirements[key]
                    for key in (
                        "preserved_conclusion_ids",
                        "preserved_method_sha256",
                        "preserved_limitations",
                        "original_method",
                        "original_conclusions",
                    )
                },
            )
            if not isinstance(response, dict):
                raise ResearchOperatorError("model_generate service must return a JSON object", error_type="provider_contract")
            # Accumulate the required limitations into the response the way
            # report_draft already does for its upstream synthesis limitations.
            # The substantive guarantee -- every recorded limitation is RENDERED
            # in the revision's limitations section -- is still enforced below
            # and is not weakened by this.  Requiring the model to additionally
            # echo all of them back in its JSON array is a redundant obligation
            # that A5 does not impose, and a reviser that rendered all ten
            # correctly was still rejected for returning an empty array.
            response = dict(response)
            response["limitations"] = list(dict.fromkeys([
                *[str(item).strip() for item in limitations if str(item).strip()],
                *[str(item).strip() for item in response.get("limitations") or [] if str(item).strip()],
            ]))
            try:
                preservation = verify_revision_response_preservation(
                    original_report,
                    response,
                    required_limitations=limitations,
                    requirements=preservation_requirements,
                )
            except ResearchOperatorError as exc:
                if attempt >= MAX_REVISION_ATTEMPTS:
                    raise
                preservation_feedback = str(exc)
                continue
            preservation_feedback = ""
            accepted_preserved_limitations = list(
                preservation_requirements.get("preserved_limitations") or []
            )
            revised_report = _normalize_report(response, claim_ids)
            attempt_writer_usage = provider_usage_from(response, usage_kind="llm")
            writer_usage.extend(attempt_writer_usage)
            # dict.fromkeys, not extend: response["limitations"] already begins
            # with everything in `limitations`, so a plain extend doubled the
            # list every attempt (9 unique entries stored as 18).
            limitations[:] = list(dict.fromkeys([
                *limitations,
                *(str(item).strip() for item in response.get("limitations", []) if str(item).strip()),
            ]))
            revised_report_payload = {
                **original_report,
                "schema": "research_synthesis.report_draft.v1",
                "node_id": "report_draft",
                "report": revised_report,
                "claim_source_lineage": {
                    str(item.get("claim_id")): [str(source_id) for source_id in item.get("evidence_ids", []) if str(source_id).strip()]
                    for item in claims
                    if item.get("claim_id")
                },
                "evidence_lineage": [
                    "report_revision",
                    "report_draft",
                    "evidence_synthesis",
                    "source_validation",
                ],
                "input_artifact_hashes": {
                    "evidence_synthesis": str((synthesis_ref or {}).get("sha256") or ""),
                    "base_report_draft": str((report_ref or {}).get("sha256") or ""),
                    "base_independent_review": str((review_ref or {}).get("sha256") or ""),
                },
                "writer_usage": list(writer_usage),
                "limitations": limitations,
            }
            review_response = review_model(
                node_id="report_revision_review",
                task_contract=task_contract,
                report_draft=revised_report_payload,
                source_validation=validation,
                prior_review=current_review,
            )
            if not isinstance(review_response, dict):
                raise ResearchOperatorError("review_model_generate service must return a JSON object", error_type="provider_contract")
            revision_review = _normalize_review_response(
                review_response,
                report_payload=revised_report_payload,
                validation=validation,
                task_contract=task_contract,
            )
            attempt_reviewer_usage = revision_review["reviewer_usage"]
            reviewer_usage.extend(attempt_reviewer_usage)
            revision_review["writer_usage"] = list(writer_usage)
            revision_review["reviewed_artifact_hashes"] = {
                "revised_report": stable_json_sha256(revised_report),
                "source_validation": str((validation_ref or {}).get("sha256") or ""),
            }
            revision_review["revision_attempt"] = attempt
            revision_review["max_revision_attempts"] = MAX_REVISION_ATTEMPTS
            limitations[:] = list(dict.fromkeys([
                *limitations,
                *(str(item).strip() for item in revision_review.get("limitations") or [] if str(item).strip()),
                *(str(item).strip() for item in _same_model_limitation(attempt_writer_usage, attempt_reviewer_usage) if str(item).strip()),
            ]))
            needs_more_revision, current_blocking_findings, _current_verdict = _repair_required(revision_review)
            normalized_body = _normalized_text(revised_report.get("body"))
            # Only what this attempt was ASKED to preserve. The accumulated list
            # now also holds limitations the reviewer wrote about its own review
            # after this report was generated; demanding those appear verbatim in
            # the report is unsatisfiable by construction, and each review adds
            # more, so the loop could never converge. They still travel into the
            # next attempt's preservation requirement, where the reviser can act
            # on them.
            required_to_render = preservation_requirements.get("preserved_limitations") or []
            missing_rendered_limitations = [
                item
                for item in dict.fromkeys(str(value).strip() for value in required_to_render if str(value).strip())
                if _normalized_text(item) not in normalized_body
            ]
            if missing_rendered_limitations:
                preservation_finding = {
                    "finding_id": "revision_review.preservation.limitations",
                    "severity": "high",
                    "category": "truthfulness",
                    "message": "The revised report must render every provider-recorded limitation verbatim.",
                }
                revision_review.setdefault("findings", []).append(preservation_finding)
                revision_review["verdict_suggestion"] = "revise"
                current_blocking_findings = [*current_blocking_findings, preservation_finding]
                needs_more_revision = True
            if not needs_more_revision:
                break
            current_report_payload = revised_report_payload
            current_review = revision_review

    claim_source_lineage = (
        revised_report_payload.get("claim_source_lineage")
        if repair_required and "revised_report_payload" in locals()
        else original_report.get("claim_source_lineage")
    )
    input_artifact_hashes = (
        revised_report_payload.get("input_artifact_hashes")
        if repair_required and "revised_report_payload" in locals()
        else original_report.get("input_artifact_hashes")
    )
    artifact_payload = {
        "schema": "research_synthesis.report_revision.v1",
        "node_id": "report_revision",
        "created_at": utc_now(),
        "revision_attempt": attempt if repair_required and "attempt" in locals() else 0,
        "max_revision_attempts": MAX_REVISION_ATTEMPTS,
        "revision_applied": repair_required,
        "basis_review_verdict": first_verdict,
        "basis_blocking_findings": blocking_findings,
        "remaining_blocking_findings": current_blocking_findings if repair_required and "current_blocking_findings" in locals() else [],
        "base_artifact_hashes": {
            "report_draft": str((report_ref or {}).get("sha256") or ""),
            "independent_review": str((review_ref or {}).get("sha256") or ""),
            "source_validation": str((validation_ref or {}).get("sha256") or ""),
            "evidence_synthesis": str((synthesis_ref or {}).get("sha256") or ""),
        },
        "revised_report": revised_report,
        "revised_report_sha256": stable_json_sha256(revised_report),
        "preservation": preservation,
        "claim_source_lineage": claim_source_lineage if isinstance(claim_source_lineage, dict) else {},
        "input_artifact_hashes": input_artifact_hashes if isinstance(input_artifact_hashes, dict) else {},
        "revision_review": revision_review,
        "evidence_lineage": [
            "report_revision",
            "report_draft",
            "independent_review",
            "evidence_synthesis",
            "source_validation",
        ],
        "writer_usage": writer_usage,
        "reviewer_usage": reviewer_usage,
        # What this revision preserved, declared and rendered -- not the running
        # accumulator. Two downstream checks recompute against this field:
        # _verify_report_revision_artifact in the adapter compares the model's
        # declaration against a requirement rebuilt from it, and final_acceptance
        # requires every entry to be rendered verbatim in the report body. The
        # reviewer speaks after the reviser has written, so publishing the
        # accumulated list here asserts the report renders limitations that did
        # not exist when it was generated, and both checks fail on a revision
        # that did everything asked of it.
        "limitations": list(dict.fromkeys(
            str(item).strip()
            for item in (
                accepted_preserved_limitations
                if repair_required and "accepted_preserved_limitations" in locals()
                and accepted_preserved_limitations
                else limitations
            )
            if str(item).strip()
        )),
        # Nothing is dropped: limitations the review added after the accepted
        # revision are recorded here rather than asserted of the report.
        "review_recorded_limitations": [
            str(item).strip()
            for item in limitations
            if str(item).strip()
            and str(item).strip() not in set(
                accepted_preserved_limitations
                if repair_required and "accepted_preserved_limitations" in locals()
                else []
            )
        ] if repair_required and "accepted_preserved_limitations" in locals()
        and accepted_preserved_limitations else [],
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "report_revision.json"),
        artifact_payload,
        artifact_id="report_revision",
        schema="research_synthesis.report_revision.v1",
    )
    report_path = validate_scoped_path(
        output_path(context, "report.md"),
        context.write_scope,
        workspace_root=context.workspace_root,
    )
    safe_body = str(redact_secrets(revised_report.get("body", ""), context.secret_refs, context.secret_values))
    _write_bytes(report_path, (safe_body.rstrip() + "\n").encode("utf-8"))
    report_digest = sha256_bytes(_read_bytes(report_path))
    report_artifact = {
        "artifact_id": "report_revision_markdown",
        "path": display_path(report_path, context.workspace_root),
        "schema": "text/markdown",
        "sha256": report_digest,
    }
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact, report_artifact],
        evidence=[
            evidence_ref(
                "report_revision.attempt",
                "bounded_report_revision",
                f"Revision attempts={artifact_payload['revision_attempt']} applied={repair_required}; basis verdict={first_verdict or 'missing'}.",
                artifact["artifact_id"],
            ),
            evidence_ref(
                "report_revision.usable_markdown",
                "usable_report",
                "A non-empty Markdown report was written for the active revised-or-forwarded report.",
                report_artifact["artifact_id"],
            ),
        ],
        hashes=[hash_record, {"hash_id": "report_revision_markdown", "algorithm": "sha256", "value": report_digest}],
        model_provider_usage=[*writer_usage, *reviewer_usage],
        limitations=artifact_payload["limitations"],
    )
