"""Claim verification, report, review, publication, and evolution operators."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

from ....claim_scope import compare_claim_evidence_scope

from .common import (
    OperatorContext,
    ResearchOperatorError,
    completed_result,
    load_documents,
    output_location,
    require_list,
    require_text,
    stable_json_sha256,
    write_scoped_text,
)


CLAIM_VERIFIER_ID = "autosci-claim-verification-physical"
REPORT_PLANNER_ID = "autosci-report-planning-physical"
REPORT_DRAFTER_ID = "autosci-report-drafting-physical"
ARTIFACT_REVIEWER_ID = "autosci-artifact-review-physical"
PUBLICATION_PRODUCER_ID = "autosci-publication-production-physical"
WORKFLOW_EVOLVER_ID = "autosci-workflow-evolution-proposal-physical"
FINAL_EVALUATOR_ID = "autosci-final-publication-evaluation-physical"


def _outputs(document: dict[str, Any]) -> dict[str, Any]:
    return document.get("outputs") if isinstance(document.get("outputs"), dict) else document


def verify_claim(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    documents = load_documents(
        context,
        schemas=(
            "research_claims.v1",
            "research_paper.v1",
            "experiment_result.v1",
            "code_evidence_map.v1",
        ),
        payload_keys=("claims", "research_paper", "experiment_result"),
    )
    claims: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    papers: list[dict[str, Any]] = []
    for document in documents:
        if document.get("claim_id"):
            claims.append(document)
            continue
        if document.get("experiment_id") and document.get("outcome"):
            results.append(document)
            continue
        values = _outputs(document)
        raw_claims = values.get("claims") if isinstance(values, dict) else None
        if isinstance(raw_claims, list):
            claims.extend(item for item in raw_claims if isinstance(item, dict))
        raw_result = values.get("result") if isinstance(values, dict) else None
        if isinstance(raw_result, dict):
            results.append(raw_result)
        raw_paper = values.get("paper") if isinstance(values, dict) else None
        if isinstance(raw_paper, dict):
            papers.append(raw_paper)
    require_list(claims, "claims")
    experiment = results[0] if results else {}
    outcome = str(experiment.get("outcome") or "inconclusive")
    experiment_evidence = [str(item) for item in experiment.get("evidence_ids") or [] if str(item).strip()]
    criteria_results = experiment.get("criteria_results") if isinstance(experiment.get("criteria_results"), dict) else {}
    paper_ids = {
        str(paper.get("paper_id") or "").strip()
        for paper in papers
        if str(paper.get("paper_id") or "").strip()
    }
    paper_anchor_text: dict[str, list[str]] = {}
    for paper in papers:
        paper_id = str(paper.get("paper_id") or "").strip()
        for section in paper.get("sections") or []:
            if not isinstance(section, dict):
                continue
            anchor = str(section.get("source_anchor") or "").strip()
            if not anchor:
                continue
            normalized_text = re.sub(
                r"\s+", " ", str(section.get("text") or "")
            ).strip()
            paper_anchor_text.setdefault(anchor, []).append(normalized_text)
            if paper_id:
                paper_anchor_text.setdefault(
                    f"{paper_id}::{anchor}", []
                ).append(normalized_text)
    paper_anchors = set(paper_anchor_text)
    verdicts: list[dict[str, Any]] = []
    for claim in claims:
        claim_id = require_text(claim.get("claim_id"), "claim_id")
        criteria = [str(item) for item in claim.get("acceptance_criteria") or [] if str(item).strip()]
        claim_evidence_ids = {
            str(item).strip() for item in claim.get("evidence_ids") or [] if str(item).strip()
        }
        source_anchor = str(claim.get("source_anchor") or "").strip()
        resolved_paper_ids = sorted(claim_evidence_ids & paper_ids)
        anchor_resolved = bool(source_anchor and source_anchor in paper_anchors)
        literature_grounded = bool(resolved_paper_ids or anchor_resolved)
        normalized_claim_text = re.sub(
            r"\s+", " ", str(claim.get("text") or "")
        ).strip()
        valid_citation_spans: list[dict[str, Any]] = []
        for span in claim.get("citation_spans") or []:
            if not isinstance(span, dict):
                continue
            span_anchor = str(span.get("source_ref") or "").strip()
            source_candidates = paper_anchor_text.get(span_anchor, [])
            start = span.get("start_char")
            end = span.get("end_char")
            quote = str(span.get("quote") or "")
            expected_digest = str(span.get("source_text_sha256") or "").lower()
            if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
                continue
            if any(
                end <= len(source_text)
                and source_text[start:end] == quote == normalized_claim_text
                and hashlib.sha256(source_text.encode("utf-8")).hexdigest() == expected_digest
                for source_text in source_candidates
            ):
                valid_citation_spans.append(dict(span))
        source_reported_exact = bool(
            anchor_resolved
            and normalized_claim_text
            and any(
                normalized_claim_text.casefold() in source_text.casefold()
                for source_text in paper_anchor_text.get(source_anchor, [])
            )
        )
        matched = bool(criteria) and all(criteria_results.get(item) is True for item in criteria)
        rejected = any(criteria_results.get(item) is False for item in criteria)
        scope_comparison = compare_claim_evidence_scope(claim, experiment)
        scope_risks = list(scope_comparison["risks"])
        if results and (outcome == "refutes" or rejected):
            verdict, support_class, confidence = "not_supported", "unsupported", 0.9
            basis = "Experiment evidence refutes the claim or fails an explicit acceptance criterion."
        elif results and scope_risks:
            verdict, support_class, confidence = "insufficient", "insufficient_evidence", 0.35
            basis = "Claim scope exceeds the available evidence; local support cannot establish the broader assertion."
        elif results and outcome == "supports" and experiment_evidence and matched:
            verdict, support_class, confidence = "supported", "supported", 0.9
            basis = "Experiment evidence supports every explicit claim acceptance criterion."
        elif not results and source_reported_exact:
            verdict, support_class, confidence = "partially_supported", "source_reported", 0.85
            basis = (
                "The claim is an exact statement retained from the cited source section; "
                "the workflow did not independently reproduce the scientific result."
            )
        else:
            verdict, support_class, confidence = "insufficient", "insufficient_evidence", 0.3
            basis = (
                "Evidence does not establish every explicit acceptance criterion."
                if results
                else "The claim text could not be reproduced exactly from its cited retained source section."
            )
        retained_evidence_ids = [
            *experiment_evidence,
            *[str(item) for item in claim.get("evidence_ids") or [] if str(item).strip()],
        ]
        if retained_evidence_ids:
            evidence_ids = sorted(set([claim_id, *retained_evidence_ids]))
        else:
            evidence_ids = [f"missing-evidence:{claim_id}"]
        if support_class == "source_reported":
            limitations = [
                "Source-reported exact quotation only; no local reproduction or independent scientific validation was performed."
            ]
        elif support_class == "insufficient_evidence":
            limitations = [*(scope_risks or ["Missing or incomplete acceptance-criteria evidence."])]
        else:
            limitations = []
        if papers and not literature_grounded:
            limitations.append(
                "The claim's paper identifier or source anchor does not resolve in the retained paper evidence."
            )
            if support_class == "supported":
                verdict, support_class, confidence = "insufficient", "insufficient_evidence", 0.3
                basis = (
                    "Measured evidence is positive, but the claim's literature source does not resolve "
                    "in the retained paper evidence."
                )
        source_grounding = {
            "paper_evidence_supplied": bool(papers),
            "resolved": literature_grounded,
            "resolved_paper_ids": resolved_paper_ids,
            "source_anchor_resolved": anchor_resolved,
            "exact_quote_resolved": source_reported_exact,
        }
        if claim.get("citation_spans"):
            source_grounding["precise_source_span_resolved"] = bool(valid_citation_spans)
        verdict_record = {
            "claim_id": claim_id,
            "claim_text": str(claim.get("text") or "").strip(),
            "verdict": verdict,
            "support_classification": support_class,
            "confidence": confidence,
            "basis": basis,
            "evidence_ids": evidence_ids,
            "limitations": limitations,
            "acceptance_criteria_checked": criteria,
            "evidence_outcome": (
                "insufficient_evidence"
                if support_class == "insufficient_evidence"
                else "source_reported"
                if support_class == "source_reported"
                else outcome
            ),
            "verification_basis": (
                "source_reported_exact_quote"
                if support_class == "source_reported"
                else "measured_experiment" if results else "unresolved"
            ),
            "locally_reproduced": bool(results and outcome == "supports" and matched),
            "overclaim_risks": scope_risks,
            "scope_comparison": scope_comparison,
            "source_grounding": source_grounding,
        }
        if claim.get("citation_spans"):
            verdict_record["citation_spans"] = valid_citation_spans
        verdicts.append(verdict_record)
    return completed_result(
        context,
        operator_id=CLAIM_VERIFIER_ID,
        schema="claim_verdict.v1",
        outputs={"verdicts": verdicts},
        filename="claim_verdict.v1.json",
        artifact_id="claim_verdict",
    )


def _verdicts(context: OperatorContext) -> list[dict[str, Any]]:
    documents = load_documents(context, schemas=("claim_verdict.v1",), payload_keys=("verdicts", "claim_verdict"))
    rows: list[dict[str, Any]] = []
    for document in documents:
        if document.get("claim_id") and document.get("verdict"):
            rows.append(document)
            continue
        values = _outputs(document)
        verdicts = values.get("verdicts") if isinstance(values, dict) else None
        if isinstance(verdicts, list):
            rows.extend(item for item in verdicts if isinstance(item, dict))
    return require_list(rows, "verdicts")


def _grounded_evidence_ids(verdict: dict[str, Any]) -> list[str]:
    return [
        str(item)
        for item in verdict.get("evidence_ids") or []
        if str(item).strip() and not str(item).startswith("missing-evidence:")
    ]


def _method_evidence(context: OperatorContext) -> tuple[list[dict[str, Any]], list[str]]:
    documents = load_documents(
        context,
        schemas=("research_method.v1",),
        payload_keys=("research_method",),
        required=False,
    )
    methods: list[dict[str, Any]] = []
    limitations: list[str] = []
    for document in documents:
        values = _outputs(document)
        if isinstance(values.get("methods"), list):
            methods.extend(item for item in values["methods"] if isinstance(item, dict))
        limitations.extend(
            str(item)
            for item in document.get("limitations") or []
            if str(item).strip()
        )
    return methods, limitations


def _source_assessment_evidence(
    context: OperatorContext,
) -> tuple[dict[str, Any], list[str]]:
    documents = load_documents(
        context,
        schemas=("research_source_assessment.v1",),
        payload_keys=("source_assessment",),
        required=False,
    )
    assessment: dict[str, Any] = {}
    limitations: list[str] = []
    for document in documents:
        values = _outputs(document)
        if assessment:
            raise ResearchOperatorError(
                "Multiple source assessments were supplied to one report",
                error_type="artifact_identity_mismatch",
            )
        assessment = values
        limitations.extend(
            str(item) for item in document.get("limitations") or [] if str(item).strip()
        )
    return assessment, limitations


def _paper_evidence(
    context: OperatorContext,
) -> tuple[list[dict[str, Any]], list[str]]:
    documents = load_documents(
        context,
        schemas=("research_paper.v1",),
        payload_keys=("research_paper",),
        required=False,
    )
    papers: list[dict[str, Any]] = []
    limitations: list[str] = []
    seen: set[str] = set()
    for document in documents:
        values = _outputs(document)
        paper = values.get("paper") if isinstance(values, dict) else None
        if not isinstance(paper, dict):
            continue
        paper_id = require_text(paper.get("paper_id"), "paper_id")
        if paper_id in seen:
            raise ResearchOperatorError(
                f"Duplicate research paper identity supplied to one report: {paper_id}",
                error_type="artifact_identity_mismatch",
            )
        seen.add(paper_id)
        papers.append(paper)
        limitations.extend(
            str(item) for item in document.get("limitations") or [] if str(item).strip()
        )
    return papers, list(dict.fromkeys(limitations))


def _experiment_evidence(
    context: OperatorContext,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Load a matched measured experiment plan/result pair when supplied.

    Research-only reports remain valid without either artifact.  A report may
    not consume only one side of the pair, mix experiment identities, or call
    an outcome measured when no metrics or retained result evidence exist.
    """

    documents = load_documents(
        context,
        schemas=("experiment_plan.v1", "experiment_result.v1"),
        payload_keys=("experiment_plan", "experiment_result"),
        required=False,
    )
    experiment_plan: dict[str, Any] = {}
    experiment_result: dict[str, Any] = {}
    limitations: list[str] = []
    for document in documents:
        values = _outputs(document)
        raw_plan = values.get("experiment_plan") if isinstance(values, dict) else None
        raw_result = values.get("result") if isinstance(values, dict) else None
        if isinstance(raw_plan, dict):
            if experiment_plan:
                raise ResearchOperatorError(
                    "Multiple experiment plans were supplied to one report",
                    error_type="artifact_identity_mismatch",
                )
            experiment_plan = raw_plan
        if isinstance(raw_result, dict):
            if experiment_result:
                raise ResearchOperatorError(
                    "Multiple experiment results were supplied to one report",
                    error_type="artifact_identity_mismatch",
                )
            experiment_result = raw_result
        limitations.extend(
            str(item) for item in document.get("limitations") or [] if str(item).strip()
        )

    if bool(experiment_plan) != bool(experiment_result):
        raise ResearchOperatorError(
            "A combined experiment report requires both experiment_plan.v1 and experiment_result.v1",
            error_type="missing_input",
        )
    if not experiment_plan:
        return {}, {}, []

    plan_id = require_text(experiment_plan.get("experiment_id"), "experiment plan id")
    result_id = require_text(experiment_result.get("experiment_id"), "experiment result id")
    if plan_id != result_id:
        raise ResearchOperatorError(
            f"Experiment plan/result identity mismatch: {plan_id} != {result_id}",
            error_type="artifact_identity_mismatch",
        )
    metrics = [item for item in experiment_result.get("metrics") or [] if isinstance(item, dict)]
    evidence_ids = [
        str(item).strip()
        for item in experiment_result.get("evidence_ids") or []
        if str(item).strip()
    ]
    outcome = str(experiment_result.get("outcome") or "")
    if not evidence_ids:
        raise ResearchOperatorError(
            "Experiment reporting requires non-empty result or availability evidence ids",
            error_type="insufficient_evidence",
        )
    if outcome != "inconclusive" and not metrics:
        raise ResearchOperatorError(
            "A conclusive measured experiment result requires non-empty metrics",
            error_type="insufficient_evidence",
        )
    if outcome == "inconclusive" and not metrics:
        availability = (
            experiment_result.get("availability")
            if isinstance(experiment_result.get("availability"), dict)
            else {}
        )
        if str(availability.get("status") or "") != "unavailable":
            raise ResearchOperatorError(
                "A metric-free inconclusive result must retain unavailable-resource evidence",
                error_type="insufficient_evidence",
            )
    limitations.extend(
        str(item)
        for item in experiment_result.get("limitations") or []
        if str(item).strip()
    )
    return experiment_plan, experiment_result, list(dict.fromkeys(limitations))


def _requirement_bindings(context: OperatorContext) -> list[dict[str, Any]]:
    """Preserve accepted RequirementIR obligations without claiming they passed."""

    document = context.payload.get("requirement_ir")
    if document is None:
        return []
    if not isinstance(document, dict) or not str(document.get("schema_version") or "").startswith(
        "solar.requirement_ir."
    ):
        raise ResearchOperatorError(
            "Accepted RequirementIR input is malformed",
            error_type="artifact_identity_mismatch",
        )
    raw_requirements = document.get("requirements")
    if not isinstance(raw_requirements, list) or not raw_requirements:
        raise ResearchOperatorError(
            "Accepted RequirementIR has no requirements",
            error_type="missing_input",
        )
    bindings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_requirements:
        if not isinstance(raw, dict):
            raise ResearchOperatorError(
                "RequirementIR contains a non-object requirement",
                error_type="invalid_input",
            )
        requirement_id = require_text(raw.get("requirement_id"), "requirement_id")
        if requirement_id in seen:
            raise ResearchOperatorError(
                f"RequirementIR contains duplicate requirement id: {requirement_id}",
                error_type="invalid_input",
            )
        seen.add(requirement_id)
        acceptance = raw.get("acceptance") if isinstance(raw.get("acceptance"), dict) else {}
        bindings.append(
            {
                "requirement_id": requirement_id,
                "statement": require_text(raw.get("statement"), f"requirement {requirement_id} statement"),
                "priority": str(raw.get("priority") or "must"),
                "check": str(raw.get("check") or ""),
                "acceptance": {
                    "kind": str(acceptance.get("kind") or ""),
                    "required_values": [
                        str(item)
                        for item in acceptance.get("required_values") or []
                        if str(item).strip()
                    ],
                },
            }
        )
    return bindings


def _unknown_resolution_traces(
    requirement_bindings: list[dict[str, Any]],
    evidence_ids: list[str],
    owned_requirement_ids: set[str],
) -> list[dict[str, Any]]:
    """Materialize unresolved-question obligations without inventing answers.

    The Requirement Compiler permits an unknown to be either resolved or
    explicitly retained as unresolved.  Report planning cannot infer a
    scientific resolution merely because evidence artifacts exist, so the
    conservative, truthful default is an explicit unresolved trace over the
    evidence set that was available to the planner.
    """

    traces: list[dict[str, Any]] = []
    for binding in requirement_bindings:
        if str(binding.get("check") or "") != "check.unknown_resolution_trace.v1":
            continue
        requirement_id = require_text(
            binding.get("requirement_id"), "unknown-resolution requirement_id"
        )
        statement = require_text(
            binding.get("statement"), f"unknown-resolution {requirement_id} statement"
        )
        owned_by_report_plan = requirement_id in owned_requirement_ids
        traces.append(
            {
                "requirement_id": requirement_id,
                "finding": (
                    (
                        "The report plan resolves this planning obligation with an explicit "
                        "section structure, requirement bindings, evidence identifiers, claim-status "
                        "mappings, and unresolved-question traces: "
                    )
                    if owned_by_report_plan
                    else (
                        "The available evidence did not establish a defensible resolution; "
                        "the report must preserve this question explicitly: "
                    )
                )
                + statement,
                "supporting_evidence": list(evidence_ids),
                "unresolved_status": (
                    "resolved" if owned_by_report_plan else "unresolved"
                ),
            }
        )
    return traces


def _claim_status_mappings(
    verdicts: list[dict[str, Any]],
    experiment_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Carry verifier truth and the experimental boundary into report planning."""

    experiment_evidence_ids = {
        str(item)
        for item in experiment_result.get("evidence_ids") or []
        if str(item).strip()
    }
    experiment_executed = bool(
        experiment_result
        and experiment_result.get("execution_attempted", True)
        and experiment_result.get("metrics")
    )
    mappings: list[dict[str, Any]] = []
    for item in verdicts:
        claim_id = require_text(item.get("claim_id"), "claim verdict claim_id")
        claim_evidence_ids = [
            str(value)
            for value in item.get("evidence_ids") or []
            if str(value).strip()
        ]
        verdict = require_text(item.get("verdict"), f"claim verdict {claim_id}")
        evidence_outcome = str(item.get("evidence_outcome") or verdict)
        contradicted = (
            verdict == "not_supported"
            or evidence_outcome in {"contradicted", "refuted"}
            or bool(item.get("contradicted_by"))
        )
        mapping = {
                "claim_id": claim_id,
                "verdict": verdict,
                "support_classification": str(
                    item.get("support_classification") or verdict
                ),
                "evidence_outcome": evidence_outcome,
                "evidence_ids": claim_evidence_ids,
                "contradiction_status": (
                    "contradicted" if contradicted else "no_recorded_contradiction"
                ),
                "tested_status": (
                    "tested"
                    if experiment_executed
                    and bool(set(claim_evidence_ids) & experiment_evidence_ids)
                    else "not_tested"
                ),
                "limitations": [
                    str(value)
                    for value in item.get("limitations") or []
                    if str(value).strip()
                ],
            }
        claim_text = str(item.get("claim_text") or "").strip()
        citation_spans = [
            dict(value)
            for value in item.get("citation_spans") or []
            if isinstance(value, dict)
        ]
        if claim_text and citation_spans:
            mapping["claim_text"] = claim_text
        if citation_spans:
            mapping["citation_spans"] = citation_spans
        mappings.append(mapping)
    return mappings


def _study_protocol_evidence(
    context: OperatorContext,
) -> tuple[dict[str, Any], list[str], list[str]]:
    documents = load_documents(
        context,
        schemas=("literature_discovery.v1",),
        payload_keys=("literature_discovery", "discovery_evidence"),
        required=False,
    )
    for document in documents:
        values = _outputs(document)
        protocol = values.get("study_protocol") if isinstance(values, dict) else None
        if not isinstance(protocol, dict):
            continue
        candidate_ids = [
            str(item.get("candidate_id"))
            for item in values.get("candidates") or []
            if isinstance(item, dict) and str(item.get("candidate_id") or "").strip()
        ]
        limitations = [
            str(item) for item in document.get("limitations") or [] if str(item).strip()
        ]
        return protocol, candidate_ids, limitations
    unresolved = [
        "search_strategy",
        "source_selection_criteria",
        "time_range",
        "inclusion_criteria",
        "exclusion_criteria",
    ]
    return (
        {
            "protocol_status": "unresolved",
            "search_strategy": "No literature-discovery protocol artifact reached report planning.",
            "source_selection_criteria": [],
            "time_range": {
                "status": "unresolved",
                "start": None,
                "end": None,
                "rationale": "No publication-date boundary was available to report planning.",
            },
            "inclusion_criteria": [],
            "exclusion_criteria": [],
            "unresolved_fields": unresolved,
        },
        ["unresolved:study-protocol"],
        ["The study protocol was not supplied by literature discovery."],
    )


def plan_report(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    verdicts = _verdicts(context)
    methods, method_limitations = _method_evidence(context)
    papers, paper_limitations = _paper_evidence(context)
    source_assessment, source_assessment_limitations = _source_assessment_evidence(context)
    experiment_plan, experiment_result, experiment_limitations = _experiment_evidence(
        context
    )
    study_protocol, protocol_evidence_ids, protocol_limitations = _study_protocol_evidence(
        context
    )
    requirement_bindings = _requirement_bindings(context)
    reportable = [
        item for item in verdicts
        if _grounded_evidence_ids(item) and str(item.get("claim_text") or "").strip()
    ]
    if not reportable:
        raise ResearchOperatorError("No source-grounded claims are available for the report", error_type="insufficient_evidence")
    topic = require_text(context.payload.get("topic") or context.payload.get("title"), "report topic")
    claim_evidence_ids = {
        evidence_id
        for item in reportable
        for evidence_id in _grounded_evidence_ids(item)
    }
    method_evidence_ids = {
        str(evidence_id)
        for method in methods
        for evidence_id in method.get("evidence_ids") or []
        if str(evidence_id).strip()
    }
    experiment_evidence_ids = {
        str(evidence_id)
        for evidence_id in experiment_result.get("evidence_ids") or []
        if str(evidence_id).strip()
    }
    source_assessment_evidence_ids = {
        str(evidence_id)
        for assessment in source_assessment.get("assessments") or []
        if isinstance(assessment, dict)
        for evidence_id in assessment.get("evidence_ids") or []
        if str(evidence_id).strip()
    }
    paper_evidence_ids = {
        evidence_id
        for paper in papers
        for evidence_id in (
            str(paper.get("paper_id") or "").strip(),
            *(
                str(section.get("source_anchor") or "").strip()
                for section in paper.get("sections") or []
                if isinstance(section, dict)
            ),
        )
        if evidence_id
    }
    evidence_ids = sorted(
        claim_evidence_ids
        | method_evidence_ids
        | experiment_evidence_ids
        | source_assessment_evidence_ids
        | paper_evidence_ids
        | set(protocol_evidence_ids)
    )
    unknown_resolution_traces = _unknown_resolution_traces(
        requirement_bindings,
        evidence_ids,
        {
            str(item)
            for item in context.payload.get("requirement_ids") or []
            if str(item).strip()
        },
    )
    claim_status_mappings = _claim_status_mappings(verdicts, experiment_result)
    sections = [
        {
            "section_id": "summary",
            "title": f"Summary: {topic}",
            "purpose": "Answer the requested topic.",
            "evidence_ids": evidence_ids,
            "requirement_ids": [],
        },
        {
            "section_id": "findings",
            "title": "Source-grounded findings",
            "purpose": "Present claims with their unchanged verification classification.",
            "evidence_ids": evidence_ids,
            "requirement_ids": [],
        },
        {
            "section_id": "study_protocol",
            "title": "Study protocol and selection boundaries",
            "purpose": (
                "Report the discovery search strategy, source-selection criteria, time range, "
                "inclusion criteria, exclusion criteria, and every unresolved protocol field."
            ),
            "evidence_ids": sorted(protocol_evidence_ids),
            "requirement_ids": [],
        },
    ]
    if requirement_bindings:
        sections.append(
            {
                "section_id": "requirements",
                "title": "Requested outcomes and verification boundary",
                "purpose": (
                    "Preserve each accepted requirement and its check contract; the independent evaluator, "
                    "not this producer, decides whether the report satisfies it."
                ),
                "evidence_ids": evidence_ids,
                "requirement_ids": [item["requirement_id"] for item in requirement_bindings],
            }
        )
    if unknown_resolution_traces:
        sections.append(
            {
                "section_id": "unknown_resolution",
                "title": "Resolved and unresolved research questions",
                "purpose": (
                    "State each compiler-identified unknown, the evidence available to assess it, "
                    "and whether it remains unresolved without inventing a resolution."
                ),
                "evidence_ids": evidence_ids,
                "requirement_ids": [
                    item["requirement_id"] for item in unknown_resolution_traces
                ],
            }
        )
    sections.append(
        {
            "section_id": "claim_audit",
            "title": "Claim verdicts, disagreements, and test boundary",
            "purpose": (
                "Map every claim to its actual verifier classification, recorded contradiction state, "
                "and tested-versus-not-tested status."
            ),
            "evidence_ids": evidence_ids,
            "requirement_ids": [],
        }
    )
    if methods or method_limitations:
        sections.append({
            "section_id": "methods",
            "title": "Methods and comparison basis",
            "purpose": (
                "Compare or explain the source-grounded methods retained for this report."
                if methods
                else "State that structured method evidence was insufficient."
            ),
            "evidence_ids": sorted(method_evidence_ids),
            "requirement_ids": [],
        })
    if source_assessment:
        sections.append({
            "section_id": "source_assessment",
            "title": "Source relevance, credibility, and benchmark resolution",
            "purpose": (
                "Report which discovered sources were selected, excluded, or unresolved, "
                "which benchmark candidates were identified, and the metadata-only credibility boundary."
            ),
            "evidence_ids": sorted(source_assessment_evidence_ids),
            "requirement_ids": [],
        })
    if papers:
        sections.append({
            "section_id": "source_evidence",
            "title": "Exact retained source evidence and unknowns",
            "purpose": (
                "Preserve exact quotations, source identifiers, parse state, and explicitly unknown paper fields."
            ),
            "evidence_ids": sorted(paper_evidence_ids),
            "requirement_ids": [],
        })
    if experiment_plan:
        sections.extend(
            [
                {
                    "section_id": "experiment_design",
                    "title": "Experiment design",
                    "purpose": (
                        "Describe the exact bounded experiment whose retained result is reported."
                    ),
                    "evidence_ids": sorted(experiment_evidence_ids),
                    "requirement_ids": [],
                },
                {
                    "section_id": "measured_results",
                    "title": (
                        "Measured experiment results"
                        if experiment_result.get("metrics")
                        and experiment_result.get("execution_attempted", True)
                        else "Experiment inconclusive status"
                    ),
                    "purpose": (
                        "Report measured metrics when execution occurred, or the exact unavailable-resource "
                        "reason when execution is inconclusive, without promoting either beyond its evidence."
                    ),
                    "evidence_ids": sorted(experiment_evidence_ids),
                    "requirement_ids": [],
                },
            ]
        )
    sections.append(
        {
            "section_id": "limitations",
            "title": "Limitations",
            "purpose": "List unsupported and insufficient claims.",
            "evidence_ids": evidence_ids,
            "requirement_ids": [],
        },
    )
    plan = {
        "report_id": str(context.payload.get("report_id") or "scientific-report"),
        "title": topic,
        "audience": str(context.payload.get("audience") or "researcher"),
        "sections": sections,
        "supported_claim_ids": [
            str(item["claim_id"])
            for item in reportable
            if str(item.get("support_classification") or "") == "supported"
        ],
        "reportable_claim_ids": [str(item["claim_id"]) for item in reportable],
        "excluded_claim_ids": [str(item["claim_id"]) for item in verdicts if item not in reportable],
        "evidence_ids": evidence_ids,
        "requirement_bindings": requirement_bindings,
        "unknown_resolution_traces": unknown_resolution_traces,
        "claim_status_mappings": claim_status_mappings,
        "study_protocol": study_protocol,
    }
    return completed_result(
        context,
        operator_id=REPORT_PLANNER_ID,
        schema="scientific_report_plan.v1",
        outputs={"report_plan": plan},
        filename="scientific_report_plan.v1.json",
        artifact_id="scientific_report_plan",
        limitations=[
            *method_limitations,
            *paper_limitations,
            *source_assessment_limitations,
            *experiment_limitations,
            *protocol_limitations,
        ],
    )


def _report_plan_and_verdicts(
    context: OperatorContext,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
    dict[str, Any],
    dict[str, Any],
    list[str],
    dict[str, Any],
    list[str],
]:
    documents = load_documents(
        context,
        schemas=(
            "scientific_report_plan.v1",
            "claim_verdict.v1",
            "research_method.v1",
            "research_source_assessment.v1",
            "experiment_plan.v1",
            "experiment_result.v1",
        ),
        payload_keys=(
            "report_plan",
            "verdicts",
            "research_method",
            "source_assessment",
            "experiment_plan",
            "experiment_result",
        ),
    )
    plan: dict[str, Any] = {}
    verdicts: list[dict[str, Any]] = []
    methods: list[dict[str, Any]] = []
    method_limitations: list[str] = []
    method_source_inputs: list[Any] = []
    for document in documents:
        if document.get("report_id") and document.get("sections"):
            plan = document
            continue
        if document.get("claim_id") and document.get("verdict"):
            verdicts.append(document)
            continue
        values = _outputs(document)
        if isinstance(values.get("report_plan"), dict):
            plan = values["report_plan"]
        if isinstance(values.get("verdicts"), list):
            verdicts.extend(item for item in values["verdicts"] if isinstance(item, dict))
        if isinstance(values.get("methods"), list):
            methods.extend(item for item in values["methods"] if isinstance(item, dict))
        if document.get("schema") == "research_method.v1":
            method_limitations.extend(str(item) for item in document.get("limitations") or [] if str(item).strip())
            method_source_inputs.append(document.get("inputs"))
    if not plan or not verdicts:
        raise ResearchOperatorError("Report plan and claim verdict evidence are required", error_type="missing_input")
    experiment_plan, experiment_result, experiment_limitations = _experiment_evidence(
        context
    )
    source_assessment, source_assessment_limitations = _source_assessment_evidence(context)
    methods = _named_method_catalog(methods, method_source_inputs, source_assessment)
    return (
        plan,
        verdicts,
        methods,
        method_limitations,
        experiment_plan,
        experiment_result,
        experiment_limitations,
        source_assessment,
        source_assessment_limitations,
    )


_GENERIC_METHOD_HEADINGS = {
    "method",
    "methods",
    "experiment",
    "experiments",
    "experiment results",
    "experimental setup",
    "general experiment settings",
    "implementation",
    "implementation details",
    "procedure",
    "protocol",
    "setup",
    "needle in a haystack experiment settings",
}
_NON_METHOD_IDENTIFIERS = {
    "API", "BERT", "CPU", "CUDA", "FP16", "GPU", "HTML", "INT4", "INT8",
    "JSON", "KV", "LLM", "LLMS", "MLLM", "MLLMS", "PDF", "QA", "RAM",
    "RAG", "TTFT", "TPOT", "URL", "CSV", "LLaVA", "Qwen", "Llama",
    "LongBench", "MileBench", "Hugging", "Transformers",
}
_NAMED_METHOD_PATTERN = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9]*[A-Z0-9][A-Za-z0-9-]*|[A-Z]{2,}[A-Z0-9-]*)\b"
)
_METHOD_SUBJECT_ACTION_PATTERN = re.compile(
    r"^\s*(?:\([^)]{0,60}\)\s*)?(?:quantizes?|uses?|proposes?|introduces?|"
    r"compresses?|evicts?|selects?|adapts?|assigns?|allocates?|couples?|alternates?|"
    r"implements?|retains?|prioritizes?)\b",
    re.IGNORECASE,
)
_METHOD_LIST_PREFIX_PATTERN = re.compile(
    r"\b(?:include|including|against|such\s+as|baselines?|methods?|approaches?|strategies?)\b"
    r"[^.!?;:]{0,120}$",
    re.IGNORECASE,
)
_METHOD_APPOSITIVE_SUFFIX_PATTERN = re.compile(
    r"^\s*,?\s+(?:a|an|which\s+is|which\s+are|are)\b.{0,80}"
    r"\b(?:method|approach|strategy|framework|technique)s?\b",
    re.IGNORECASE,
)


def _nested_papers(value: Any) -> list[dict[str, Any]]:
    """Find retained paper-shaped objects without depending on one envelope layout."""

    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        sections = value.get("sections")
        if isinstance(sections, list) and any(
            isinstance(item, dict) and str(item.get("text") or "").strip()
            for item in sections
        ):
            found.append(value)
        for child in value.values():
            found.extend(_nested_papers(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_nested_papers(child))
    return found


def _method_family(text: str) -> str:
    lowered = text.casefold()
    families = (
        ("quantization", ("quantiz", "low-bit", "int8", "int4")),
        ("eviction", ("evict", "discard", "drop token", "cache removal")),
        ("selection", ("select", "heavy-hitter", "token importance", "top-k")),
        ("sparsification", ("sparse", "sparsif", "attention sink")),
        ("compression", ("compress", "low-rank", "reduced cache")),
        ("system/cache sharing", ("shared", "pool", "serving", "scheduler", "offload")),
    )
    matched = [name for name, cues in families if any(cue in lowered for cue in cues)]
    return "/".join(matched[:2]) if matched else "other source-reported technique"


def _likely_method_identifier(name: str) -> bool:
    lowered = name.casefold()
    return bool(
        any(marker in lowered for marker in ("kv", "attn", "prune", "cache", "quant", "infer", "stream"))
        or re.search(r"(?:llm|gen|flow|mem|sparse)$", lowered)
        or re.fullmatch(r"[A-Za-z]\d[A-Za-z]", name)
    )


def _is_generic_method_heading(name: str) -> bool:
    lowered = " ".join(name.casefold().split())
    return lowered in _GENERIC_METHOD_HEADINGS or lowered.startswith(
        ("experiment ", "experimental ", "implementation details", "general experiment", "needle in a haystack")
    )


def _named_method_catalog(
    extracted: list[dict[str, Any]],
    source_inputs: list[Any],
    source_assessment: dict[str, Any],
) -> list[dict[str, Any]]:
    """Promote named, source-anchored techniques over generic section headings.

    The source parser already retains full paper sections in the method artifact's
    immutable input envelope.  This pass only identifies names that occur verbatim
    in those retained sections; it does not invent mechanisms or performance.
    """

    selected_ids = {
        str(item.get("source_id") or "")
        for item in source_assessment.get("assessments") or []
        if isinstance(item, dict) and str(item.get("decision") or "") == "selected"
    }
    records: dict[str, dict[str, Any]] = {}
    contexts: dict[str, list[str]] = {}

    def record(name: str, text: str, anchor: str, paper_id: str, *, strong_named: bool) -> None:
        clean = name.strip(" .,:;()[]{}")
        if (
            len(clean) < 3
            or clean.casefold() in {item.casefold() for item in _NON_METHOD_IDENTIFIERS}
            or _is_generic_method_heading(clean)
            or clean.casefold().endswith(("benchmark", "dataset"))
        ):
            return
        lowered = text.casefold()
        has_method_context = any(
            cue in lowered
            for cue in (
                "kv cache", "attention", "method", "approach", "baseline", "evict",
                "quantiz", "compress", "sparse", "select", "inference", "memory",
            )
        )
        if not strong_named and not has_method_context:
            return
        stable_anchor = anchor
        if Path(str(anchor)).is_absolute() or "/tmp/" in str(anchor).replace("\\", "/"):
            stable_anchor = paper_id
        key = clean.casefold()
        contexts.setdefault(key, []).append(text)
        row = records.setdefault(
            key,
            {
                "method_id": "",
                "name": clean,
                "summary": "",
                "procedure": [],
                "source_papers": [],
                "evidence_ids": [],
                "extraction_basis": "named_source_mention",
                "confidence": 0.8,
                "family": "",
                "evidence_status": "source_reported_not_locally_reproduced",
                "_strong_named": strong_named,
            },
        )
        row["_strong_named"] = bool(row.get("_strong_named")) or strong_named
        if paper_id and paper_id not in row["source_papers"]:
            row["source_papers"].append(paper_id)
        if stable_anchor and stable_anchor not in row["evidence_ids"]:
            row["evidence_ids"].append(stable_anchor)

    for source_input in source_inputs:
        for paper in _nested_papers(source_input):
            paper_id = str(paper.get("paper_id") or paper.get("source_id") or "")
            if selected_ids and paper_id and paper_id not in selected_ids:
                continue
            title = str(paper.get("title") or "").strip()
            prefix = title.split(":", 1)[0].strip()
            if title and prefix and len(prefix.split()) <= 3:
                for candidate in _NAMED_METHOD_PATTERN.findall(prefix):
                    record(candidate, title, str(paper.get("source_ref") or paper_id), paper_id, strong_named=True)
            for section in paper.get("sections") or []:
                if not isinstance(section, dict):
                    continue
                text = str(section.get("text") or "").strip()
                anchor = str(section.get("source_anchor") or paper_id)
                if not text:
                    continue
                for sentence in (
                    value.strip()
                    for value in re.split(r"(?<=[.!?])\s+|\n+", text)
                    if len(value.strip()) >= 20
                ):
                    for match in _NAMED_METHOD_PATTERN.finditer(sentence):
                        prefix = sentence[max(0, match.start() - 160):match.start()]
                        suffix = sentence[match.end():match.end() + 140]
                        if (
                            _METHOD_SUBJECT_ACTION_PATTERN.search(suffix)
                            or _METHOD_LIST_PREFIX_PATTERN.search(prefix)
                            or _METHOD_APPOSITIVE_SUFFIX_PATTERN.search(suffix)
                        ):
                            strong_named = bool(
                                _METHOD_SUBJECT_ACTION_PATTERN.search(suffix)
                                or _METHOD_APPOSITIVE_SUFFIX_PATTERN.search(suffix)
                            )
                            record(match.group(0), sentence, anchor, paper_id, strong_named=strong_named)

    for key, row in records.items():
        candidate_contexts = contexts.get(key) or []
        representative = min(candidate_contexts, key=len) if candidate_contexts else row["name"]
        representative = " ".join(representative.split())
        row["summary"] = representative[:700]
        row["procedure"] = [representative[:700]]
        row["family"] = _method_family(" ".join(candidate_contexts))

    named = sorted(
        (
            row
            for row in records.values()
            if bool(row.get("_strong_named")) or _likely_method_identifier(str(row.get("name") or ""))
        ),
        key=lambda item: (str(item.get("family")), str(item.get("name")).casefold()),
    )
    for index, row in enumerate(named, start=1):
        row["method_id"] = f"named-method-{index:03d}"
        row.pop("_strong_named", None)

    substantive_extracted = [
        item
        for item in extracted
        if not _is_generic_method_heading(str(item.get("name") or "").strip())
    ]
    known = {str(item.get("name") or "").casefold() for item in named}
    for item in substantive_extracted:
        if str(item.get("name") or "").casefold() not in known:
            named.append(item)
    return named or extracted


def _render_source_assessment(source_assessment: dict[str, Any]) -> tuple[str, list[str]]:
    rows: list[str] = []
    evidence_ids: set[str] = set()
    for assessment in source_assessment.get("assessments") or []:
        if not isinstance(assessment, dict):
            continue
        relevance = assessment.get("relevance") if isinstance(assessment.get("relevance"), dict) else {}
        credibility = assessment.get("credibility") if isinstance(assessment.get("credibility"), dict) else {}
        item_evidence = [
            str(item) for item in assessment.get("evidence_ids") or [] if str(item).strip()
        ]
        evidence_ids.update(item_evidence)
        rows.append(
            f"- {assessment.get('source_id')} — {assessment.get('title')}: "
            f"decision={assessment.get('decision')}; relevance={relevance.get('status')}; "
            f"credibility={credibility.get('status')} ({credibility.get('authority_class')}); "
            f"evidence={', '.join(item_evidence)}."
        )
    benchmarks = [
        item for item in source_assessment.get("benchmark_candidates") or [] if isinstance(item, dict)
    ]
    rows.append("\nBenchmark candidates:")
    rows.extend(
        f"- {item.get('title')} ({item.get('availability_status')}): {item.get('identification_basis')}"
        for item in benchmarks
    )
    if not benchmarks:
        rows.append("- No benchmark candidate was established from retained evidence.")
    unresolved = [
        str(item) for item in source_assessment.get("unresolved_questions") or [] if str(item).strip()
    ]
    if unresolved:
        rows.append("\nUnresolved questions:")
        rows.extend(f"- {item}" for item in unresolved)
    rows.append(
        "\nBoundary: credibility here describes retained authority/traceability metadata; "
        "it does not establish that a source's scientific findings are true."
    )
    return "\n".join(rows).strip(), sorted(evidence_ids)


def _render_method_section(
    methods: list[dict[str, Any]], method_limitations: list[str]
) -> tuple[str, list[str]]:
    rows: list[str] = []
    evidence_ids: set[str] = set()
    if methods:
        for method in methods:
            name = require_text(method.get("name"), "method name")
            summary = require_text(method.get("summary"), "method summary")
            procedure = [
                str(item).strip()
                for item in method.get("procedure") or []
                if str(item).strip()
            ]
            method_evidence_ids = [
                str(item).strip()
                for item in method.get("evidence_ids") or []
                if str(item).strip()
            ]
            evidence_ids.update(method_evidence_ids)
            extraction_basis = require_text(
                method.get("extraction_basis"), "method extraction basis"
            )
            rows.extend(
                [
                    f"### {name}",
                    f"- Family/category: {method.get('family') or 'not established by retained evidence'}",
                    f"- Evidence status: {method.get('evidence_status') or 'source_reported_not_locally_reproduced'}",
                    f"- Summary: {summary}",
                    "- Procedure:",
                    *[
                        f"  {index}. {step}"
                        for index, step in enumerate(procedure, start=1)
                    ],
                    f"- Evidence IDs: {', '.join(method_evidence_ids) or 'unavailable'}",
                    f"- Extraction basis: {extraction_basis}",
                ]
            )
    else:
        rows.append("Method evidence status: insufficient_evidence.")
        rows.extend(f"- Method limitation: {item}" for item in method_limitations)
    return "\n".join(rows).strip(), sorted(evidence_ids)


def _render_experiment_design(experiment_plan: dict[str, Any]) -> str:
    dataset = experiment_plan.get("dataset") if isinstance(experiment_plan.get("dataset"), dict) else {}
    variants = [
        item for item in experiment_plan.get("variants") or [] if isinstance(item, dict)
    ]
    rows = [
        f"- Experiment ID: {require_text(experiment_plan.get('experiment_id'), 'experiment id')}",
        f"- Objective: {require_text(experiment_plan.get('objective'), 'experiment objective')}",
        f"- Hypothesis: {require_text(experiment_plan.get('hypothesis'), 'experiment hypothesis')}",
        "- Planned metrics: "
        + (", ".join(str(item) for item in experiment_plan.get("metrics") or []) or "not recorded"),
        "- Procedure:",
        *[
            f"  {index}. {step}"
            for index, step in enumerate(experiment_plan.get("procedure") or [], start=1)
            if str(step).strip()
        ],
    ]
    if dataset:
        rows.append(
            "- Dataset: "
            f"{dataset.get('path', 'unavailable')} ({dataset.get('format', 'unknown')}; "
            f"role={dataset.get('role', 'unknown')})"
        )
    if variants:
        rows.append(
            "- Compared variants: "
            + "; ".join(
                f"{item.get('name', 'unnamed')} — {item.get('description', '')}" for item in variants
            )
        )
    seeds = experiment_plan.get("seeds")
    if not isinstance(seeds, list):
        seed = experiment_plan.get("random_seed")
        seeds = [seed] if seed is not None else []
    if seeds:
        rows.append("- Seeds: " + ", ".join(str(item) for item in seeds))
    return "\n".join(rows)


def _render_requirement_coverage(
    requirement_bindings: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    fallback_evidence_ids: list[str],
    *,
    reportable_claims: list[dict[str, Any]] | None = None,
    source_assessment: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Expose what source evidence does and does not cover without self-approval."""

    method_rows: list[tuple[str, set[str]]] = []
    for method in methods:
        searchable = re.sub(
            r"[^a-z0-9]+",
            " ",
            json.dumps(method, ensure_ascii=False, sort_keys=True).casefold(),
        ).strip()
        method_rows.append(
            (
                searchable,
                {
                    str(item)
                    for item in method.get("evidence_ids") or []
                    if str(item).strip()
                },
            )
        )
    for claim in reportable_claims or []:
        method_rows.append(
            (
                re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    json.dumps(claim, ensure_ascii=False, sort_keys=True).casefold(),
                ).strip(),
                {
                    str(item)
                    for item in claim.get("evidence_ids") or []
                    if str(item).strip()
                },
            )
        )
    for assessment in (source_assessment or {}).get("assessments") or []:
        if not isinstance(assessment, dict):
            continue
        method_rows.append(
            (
                re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    json.dumps(assessment, ensure_ascii=False, sort_keys=True).casefold(),
                ).strip(),
                {
                    str(item)
                    for item in assessment.get("evidence_ids") or []
                    if str(item).strip()
                },
            )
        )

    rows: list[str] = []
    enriched: list[dict[str, Any]] = []
    for binding in requirement_bindings:
        requirement_id = require_text(binding.get("requirement_id"), "requirement_id")
        required_values = [
            str(item).strip()
            for item in (binding.get("acceptance") or {}).get("required_values") or []
            if str(item).strip()
        ]
        matched_evidence: set[str] = set()
        value_rows: list[str] = []
        for required_value in required_values:
            normalized_value = re.sub(
                r"[^a-z0-9]+", " ", required_value.casefold()
            ).strip()
            value_evidence = {
                evidence_id
                for searchable, evidence_ids in method_rows
                if normalized_value and normalized_value in searchable
                for evidence_id in evidence_ids
            }
            matched_evidence.update(value_evidence)
            value_rows.append(
                f"{required_value}="
                + (
                    f"source_grounded ({', '.join(sorted(value_evidence))})"
                    if value_evidence
                    else "explicitly retained; source-specific coverage unresolved"
                )
            )
        rows.append(
            f"- {requirement_id}: "
            + ("; ".join(value_rows) or "no enumerated required values")
            + "."
        )
        all_values_grounded = bool(required_values) and all(
            "source_grounded" in row for row in value_rows
        )
        source_assessment_present = bool((source_assessment or {}).get("assessments"))
        artifact_fields = str((binding.get("acceptance") or {}).get("kind") or "") == "artifact_fields"
        status = (
            "evidence_present_for_independent_evaluation"
            if source_assessment_present and (all_values_grounded or artifact_fields)
            else "pending_independent_evaluation"
        )
        enriched.append({
            **binding,
            "requirement_text": str(binding.get("statement") or ""),
            "status": status,
            "coverage_status": status,
            "evidence_ids": sorted(matched_evidence) or list(fallback_evidence_ids),
        })
    return (
        "\n".join(rows) or "- No accepted requirement bindings were supplied.",
        enriched,
    )


def _resolve_report_unknowns_from_governed_artifacts(
    traces: list[dict[str, Any]],
    requirement_bindings: list[dict[str, Any]],
    *,
    methods: list[dict[str, Any]],
    source_assessment: dict[str, Any],
    report_requirement_bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve only unknown classes directly answered by typed input artifacts."""

    statements = {
        str(item.get("requirement_id") or ""): str(item.get("statement") or "")
        for item in requirement_bindings
    }
    grounded_coverage = any(
        str(item.get("coverage_status") or "")
        == "evidence_present_for_independent_evaluation"
        and str((item.get("acceptance") or {}).get("kind") or "") == "coverage"
        for item in report_requirement_bindings
    )
    selected_sources = [
        item
        for item in source_assessment.get("assessments") or []
        if isinstance(item, dict) and str(item.get("decision") or "") == "selected"
    ]
    resolved: list[dict[str, Any]] = []
    for trace in traces:
        row = dict(trace)
        statement = statements.get(str(row.get("requirement_id") or ""), "").casefold()
        asks_source_set = any(
            token in statement
            for token in ("sources", "papers", "benchmarks", "repositories", "datasets")
        )
        asks_methods = "method" in statement or "taxonomy" in statement
        if asks_source_set and selected_sources:
            row["unresolved_status"] = "resolved"
            row["finding"] = (
                f"The governed source assessment selected {len(selected_sources)} traceable source(s), "
                "retained exclusions and unresolved candidates, and identified benchmark candidates."
            )
        elif asks_methods and methods and grounded_coverage:
            row["unresolved_status"] = "resolved"
            row["finding"] = (
                f"The governed method evidence contains {len(methods)} source-linked method or evaluation "
                "record(s), and the source assessment covers the requested method families."
            )
        resolved.append(row)
    return resolved


def _render_measured_results(experiment_result: dict[str, Any]) -> str:
    rows = [
        f"- Experiment ID: {require_text(experiment_result.get('experiment_id'), 'experiment id')}",
        f"- Recorded outcome: {require_text(experiment_result.get('outcome'), 'experiment outcome')}",
        "- Measured metrics:",
    ]
    for metric in experiment_result.get("metrics") or []:
        if not isinstance(metric, dict):
            continue
        name = require_text(metric.get("name"), "metric name")
        value = metric.get("value")
        unit = str(metric.get("unit") or "").strip()
        rows.append(f"  - {name}: {value}{f' {unit}' if unit else ''}")
    rows.append(
        "- Result evidence IDs: "
        + ", ".join(str(item) for item in experiment_result.get("evidence_ids") or [])
    )
    return "\n".join(rows)


def _semantic_report_draft(
    context: OperatorContext,
    *,
    title: str,
    reportable: list[dict[str, Any]],
    requirement_bindings: list[dict[str, Any]],
    unknown_resolution_traces: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    source_assessment: dict[str, Any],
    plan_review: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    """Optionally synthesize the narrative with a real injected model service.

    The deterministic action remains the evidence owner.  The model receives
    only already-governed claims and typed metadata, and its conclusion links
    are checked against the exact claim-id set before any text is published.
    """

    model_generate = context.services.get("model_generate")
    if model_generate is None:
        return {}, [], []
    grounded_claims = [
        {
            "claim_id": str(item.get("claim_id") or ""),
            "text": str(item.get("claim_text") or ""),
            "evidence_ids": [
                str(value) for value in item.get("evidence_ids") or [] if str(value).strip()
            ],
            "uncertainty": str(item.get("uncertainty") or item.get("confidence") or "unknown"),
            "limitations": [
                str(value) for value in item.get("limitations") or [] if str(value).strip()
            ],
        }
        for item in reportable
    ]
    response = model_generate(
        node_id="report_draft",
        task_contract={
            "user_intent": title,
            "deliverable": {"language": "preserve_user_request"},
        },
        deliverable_requirements={
            "requirements": requirement_bindings,
            "unknowns": unknown_resolution_traces,
            "methods": methods,
            "source_assessment": source_assessment,
            "pre_draft_plan_review": plan_review,
            "rules": [
                "Produce a comprehensive source-bounded landscape, not a concatenation of extracts.",
                "Resolve each unknown when the supplied evidence permits it; otherwise state exactly why it remains unresolved.",
                "Do not reproduce a claim whose source text is visibly truncated mid-sentence.",
                "Compare requested method families only to the depth supported by supplied evidence.",
                "Address every pre-draft review finding when the governed evidence permits it; otherwise retain the finding explicitly as a limitation.",
            ],
        },
        evidence_synthesis={"claims": grounded_claims},
    )
    if not isinstance(response, dict):
        raise ResearchOperatorError(
            "model_generate service must return a JSON object",
            error_type="provider_contract_failure",
        )
    model_report = response.get("report") if isinstance(response.get("report"), dict) else {}
    body = require_text(model_report.get("body"), "semantic report body")
    allowed_claim_ids = {
        str(item.get("claim_id") or "") for item in grounded_claims if str(item.get("claim_id") or "")
    }
    conclusions = [
        item for item in model_report.get("conclusions") or [] if isinstance(item, dict)
    ]
    for conclusion in conclusions:
        cited = {str(item) for item in conclusion.get("evidence_ids") or [] if str(item).strip()}
        unknown = sorted(cited - allowed_claim_ids)
        if unknown:
            raise ResearchOperatorError(
                "Semantic report conclusion cited unknown claim ids: " + ", ".join(unknown),
                error_type="artifact_identity_mismatch",
            )
    sections = [
        {
            "section_id": f"semantic-{index}",
            "title": require_text(item.get("title"), f"semantic section {index} title"),
            "body": require_text(item.get("body"), f"semantic section {index} body"),
        }
        for index, item in enumerate(model_report.get("sections") or [], start=1)
        if isinstance(item, dict)
    ]
    return (
        {
            "title": str(model_report.get("title") or title),
            "body": body,
            "sections": sections,
            "conclusions": conclusions,
        },
        [str(item) for item in response.get("limitations") or [] if str(item).strip()],
        [item for item in response.get("provider_usage") or [] if isinstance(item, dict)],
    )


_REPORT_RELEVANCE_STOPWORDS = frozenset(
    {
        "artifact",
        "comprehensive",
        "conclusion",
        "conclusions",
        "draft",
        "evidence",
        "final",
        "generation",
        "grounded",
        "methodology",
        "perform",
        "produce",
        "producing",
        "report",
        "research",
        "reviewed",
        "source",
        "structured",
        "supported",
        "synthesis",
        "technical",
    }
)


def _report_relevance_terms(value: str) -> set[str]:
    """Extract deterministic domain terms, including CJK bigrams."""

    text = str(value or "").casefold()
    latin = {
        token
        for token in re.findall(r"[a-z][a-z0-9-]{3,}", text)
        if token not in _REPORT_RELEVANCE_STOPWORDS
    }
    cjk: set[str] = set()
    for sequence in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+", text):
        if len(sequence) == 1:
            cjk.add(sequence)
        else:
            cjk.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return latin | cjk


def _semantic_report_is_relevant(title: str, semantic_report: dict[str, Any], markdown: str) -> bool:
    """Check topic fidelity without requiring an action sentence verbatim."""

    normalized_markdown = " ".join(str(markdown or "").split()).casefold()
    if " ".join(str(title or "").split()).casefold() in normalized_markdown:
        return True
    requested_terms = _report_relevance_terms(title)
    generated_terms = _report_relevance_terms(
        f"{semantic_report.get('title') or ''}\n{markdown}"
    )
    if not requested_terms:
        return False
    required_overlap = 1 if len(requested_terms) <= 2 else 2 if len(requested_terms) <= 8 else 3
    return len(requested_terms & generated_terms) >= required_overlap


def _semantic_unknown_resolution(
    traces: list[dict[str, Any]],
    requirement_bindings: list[dict[str, Any]],
    markdown: str,
) -> list[dict[str, Any]]:
    """Promote only text-addressed unknowns to a producer-proposed resolution.

    This is not acceptance: the independent evaluator still decides whether
    the narrative actually resolves the question.  The lexical floor merely
    prevents a producer from claiming resolution when the report omitted the
    subject entirely.
    """

    statements = {
        str(item.get("requirement_id") or ""): str(item.get("statement") or "")
        for item in requirement_bindings
    }
    report_terms = set(re.findall(r"[a-z0-9][a-z0-9_-]{3,}", markdown.casefold()))
    stop = {"what", "which", "should", "would", "could", "report", "resolve", "explicitly", "unresolved", "question", "current"}
    resolved: list[dict[str, Any]] = []
    for trace in traces:
        row = dict(trace)
        statement = statements.get(str(row.get("requirement_id") or ""), "")
        terms = {
            value
            for value in re.findall(r"[a-z0-9][a-z0-9_-]{3,}", statement.casefold())
            if value not in stop
        }
        overlap = len(terms & report_terms) / max(1, len(terms))
        if row.get("supporting_evidence") and overlap >= 0.5:
            row["unresolved_status"] = "resolved"
            row["finding"] = (
                "The source-bounded report narrative addresses this question using the retained "
                "evidence identifiers; independent evaluation remains authoritative: " + statement
            )
        resolved.append(row)
    return resolved


def _render_study_protocol(protocol: dict[str, Any]) -> str:
    time_range = protocol.get("time_range") if isinstance(protocol.get("time_range"), dict) else {}
    start = str(time_range.get("start") or "unresolved")
    end = str(time_range.get("end") or "unresolved")
    rows = [
        f"- Protocol status: {str(protocol.get('protocol_status') or 'unresolved')}",
        f"- Search strategy: {str(protocol.get('search_strategy') or 'unresolved')}",
        f"- Time range: {start} to {end} ({str(time_range.get('status') or 'unresolved')})",
        f"- Time-range rationale: {str(time_range.get('rationale') or 'not recorded')}",
        "- Source-selection criteria:",
        *[f"  - {item}" for item in protocol.get("source_selection_criteria") or ["unresolved"]],
        "- Inclusion criteria:",
        *[f"  - {item}" for item in protocol.get("inclusion_criteria") or ["unresolved"]],
        "- Exclusion criteria:",
        *[f"  - {item}" for item in protocol.get("exclusion_criteria") or ["unresolved"]],
        (
            "- Unresolved protocol fields: "
            + ", ".join(str(item) for item in protocol.get("unresolved_fields") or [])
            if protocol.get("unresolved_fields")
            else "- Unresolved protocol fields: none"
        ),
    ]
    return "\n".join(rows).strip()


def draft_report(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    (
        plan,
        verdicts,
        methods,
        method_limitations,
        experiment_plan,
        experiment_result,
        experiment_limitations,
        source_assessment,
        source_assessment_limitations,
    ) = _report_plan_and_verdicts(context)
    review_documents = load_documents(
        context,
        schemas=("scientific_report_plan_review.v1",),
        payload_keys=("report_plan_review",),
        required=False,
    )
    plan_sha256 = stable_json_sha256(plan)
    plan_review: dict[str, Any] = {}
    plan_review_findings: list[dict[str, Any]] = []
    if review_documents:
        review_document = review_documents[0]
        review_outputs = _outputs(review_document)
        plan_review = review_outputs.get("review") if isinstance(review_outputs.get("review"), dict) else {}
        plan_review_findings = [
            item for item in review_outputs.get("findings") or [] if isinstance(item, dict)
        ]
        if (
            review_document.get("schema") != "scientific_report_plan_review.v1"
            or review_document.get("status") != "completed"
            or plan_review.get("review_stage") != "pre_draft_plan"
            or plan_review.get("target_schema") != "scientific_report_plan.v1"
            or plan_review.get("reviewed_artifact_sha256") != plan_sha256
        ):
            raise ResearchOperatorError(
                "Pre-draft review is missing or does not match the routed scientific report plan",
                error_type="artifact_identity_mismatch",
            )
    study_protocol = (
        plan.get("study_protocol")
        if isinstance(plan.get("study_protocol"), dict)
        else {
            "protocol_status": "unresolved",
            "search_strategy": "The report plan did not carry a study protocol.",
            "source_selection_criteria": [],
            "time_range": {
                "status": "unresolved",
                "start": None,
                "end": None,
                "rationale": "Missing from report plan.",
            },
            "inclusion_criteria": [],
            "exclusion_criteria": [],
            "unresolved_fields": [
                "search_strategy",
                "source_selection_criteria",
                "time_range",
                "inclusion_criteria",
                "exclusion_criteria",
            ],
        }
    )
    protocol_limitations = [
        f"Study protocol field remains unresolved: {item}."
        for item in study_protocol.get("unresolved_fields") or []
    ]
    reportable_ids = set(
        str(item)
        for item in (
            plan.get("reportable_claim_ids")
            or plan.get("supported_claim_ids")
            or []
        )
    )
    reportable = [item for item in verdicts if str(item.get("claim_id")) in reportable_ids]
    reportable = [
        item
        for item in reportable
        if not (
            len(str(item.get("claim_text") or "")) > 180
            and not re.search(r"[.!?][\"')\]]?$", str(item.get("claim_text") or "").strip())
        )
    ]
    if not reportable:
        raise ResearchOperatorError("Report plan has no still-reportable source-grounded claim", error_type="insufficient_evidence")
    title = require_text(context.payload.get("topic") or plan.get("title"), "report title")
    sections: list[dict[str, Any]] = []
    markdown_parts = [f"# {title}"]
    methods_rendered = False
    requirement_bindings = [
        item for item in plan.get("requirement_bindings") or [] if isinstance(item, dict)
    ]
    requirements_by_id = {
        str(item.get("requirement_id") or ""): item
        for item in requirement_bindings
        if str(item.get("requirement_id") or "")
    }
    unknown_resolution_traces = [
        item
        for item in plan.get("unknown_resolution_traces") or []
        if isinstance(item, dict)
    ]
    claim_status_mappings = [
        item
        for item in plan.get("claim_status_mappings") or []
        if isinstance(item, dict)
    ]
    report_evidence_ids = sorted(
        {
            str(evidence_id)
            for item in reportable
            for evidence_id in item.get("evidence_ids") or []
            if str(evidence_id).strip()
        }
    )
    coverage_body, report_requirement_bindings = _render_requirement_coverage(
        requirement_bindings,
        methods,
        report_evidence_ids,
        reportable_claims=reportable,
        source_assessment=source_assessment,
    )
    unknown_resolution_traces = _resolve_report_unknowns_from_governed_artifacts(
        unknown_resolution_traces,
        requirement_bindings,
        methods=methods,
        source_assessment=source_assessment,
        report_requirement_bindings=report_requirement_bindings,
    )
    semantic_report, semantic_limitations, semantic_usage = _semantic_report_draft(
        context,
        title=title,
        reportable=reportable,
        requirement_bindings=requirement_bindings,
        unknown_resolution_traces=unknown_resolution_traces,
        methods=methods,
        source_assessment=source_assessment,
        plan_review={"review": plan_review, "findings": plan_review_findings},
    )
    for section in require_list(plan.get("sections"), "report sections"):
        section_id = require_text(section.get("section_id"), "section_id")
        section_title = require_text(section.get("title"), "section title")
        evidence_ids = [str(item) for item in section.get("evidence_ids") or [] if str(item).strip()]
        requirement_ids = [
            str(item) for item in section.get("requirement_ids") or [] if str(item).strip()
        ]
        if section_id == "study_protocol":
            body = _render_study_protocol(study_protocol)
        elif section_id == "methods":
            body, method_section_evidence_ids = _render_method_section(
                methods, method_limitations
            )
            evidence_ids = sorted(set(evidence_ids) | set(method_section_evidence_ids))
            methods_rendered = True
        elif section_id == "source_assessment":
            if not source_assessment:
                raise ResearchOperatorError(
                    "Report plan requires source assessment evidence that was not supplied",
                    error_type="missing_input",
                )
            body, assessment_evidence_ids = _render_source_assessment(source_assessment)
            evidence_ids = sorted(set(evidence_ids) | set(assessment_evidence_ids))
        elif section_id == "experiment_design":
            if not experiment_plan:
                raise ResearchOperatorError(
                    "Report plan requires experiment design evidence that was not supplied",
                    error_type="missing_input",
                )
            body = _render_experiment_design(experiment_plan)
        elif section_id == "measured_results":
            if not experiment_result:
                raise ResearchOperatorError(
                    "Report plan requires measured experiment evidence that was not supplied",
                    error_type="missing_input",
                )
            body = _render_measured_results(experiment_result)
            evidence_ids = sorted(
                set(evidence_ids)
                | {
                    str(item)
                    for item in experiment_result.get("evidence_ids") or []
                    if str(item).strip()
                }
            )
        elif section_id == "limitations" and not methods_rendered and (methods or method_limitations):
            method_body, method_section_evidence_ids = _render_method_section(
                methods, method_limitations
            )
            markdown_parts.extend(["\n## Methods", method_body])
            sections.append(
                {
                    "section_id": "methods",
                    "title": "Methods",
                    "body": method_body,
                    "evidence_ids": method_section_evidence_ids,
                }
            )
            methods_rendered = True
            rows = [
                f"- {item['claim_id']}: {item['support_classification']} — {item['basis']}"
                for item in reportable
                if item.get("support_classification") != "supported"
            ]
            rows.extend(f"- Method limitation: {item}" for item in method_limitations)
            body = "\n".join(rows) or "- No additional limitations recorded."
        elif section_id == "findings":
            body = "\n".join(
                f"- {item['claim_id']} ({item['support_classification']}): {item['claim_text']} "
                f"Evidence: {', '.join(str(value) for value in item.get('evidence_ids') or [])}."
                for item in reportable
            )
        elif section_id == "requirements":
            rows = []
            for requirement_id in requirement_ids:
                binding = next(
                    (
                        item
                        for item in report_requirement_bindings
                        if item.get("requirement_id") == requirement_id
                    ),
                    None,
                )
                if not binding:
                    raise ResearchOperatorError(
                        f"Report plan references unknown requirement: {requirement_id}",
                        error_type="artifact_identity_mismatch",
                    )
                required_values = [
                    str(item)
                    for item in (binding.get("acceptance") or {}).get("required_values") or []
                    if str(item).strip()
                ]
                rows.append(
                    f"- {requirement_id} [{str(binding.get('status') or '').replace('_', ' ')}]: "
                    f"{binding.get('statement')}. "
                    f"Required evidence/fields: {', '.join(required_values) or 'not specified'}. "
                    f"Retained evidence: {', '.join(binding.get('evidence_ids') or []) or 'none'}."
                )
            body = "\n".join(rows) or "- No accepted report requirements were supplied."
        elif section_id == "unknown_resolution":
            traces_by_id = {
                str(item.get("requirement_id") or ""): item
                for item in unknown_resolution_traces
                if str(item.get("requirement_id") or "")
            }
            rows = []
            for requirement_id in requirement_ids:
                trace = traces_by_id.get(requirement_id)
                if not trace:
                    raise ResearchOperatorError(
                        f"Report plan is missing unknown-resolution trace: {requirement_id}",
                        error_type="artifact_identity_mismatch",
                    )
                supporting_evidence = [
                    str(item)
                    for item in trace.get("supporting_evidence") or []
                    if str(item).strip()
                ]
                rows.append(
                    f"- {requirement_id} [{trace.get('unresolved_status')}]: "
                    f"{trace.get('finding')} Supporting evidence reviewed: "
                    f"{', '.join(supporting_evidence) or 'none available'}."
                )
                evidence_ids = sorted(set(evidence_ids) | set(supporting_evidence))
            body = "\n".join(rows) or "- No unresolved questions were recorded."
        elif section_id == "claim_audit":
            rows = []
            for mapping in claim_status_mappings:
                claim_id = require_text(mapping.get("claim_id"), "claim audit claim_id")
                rows.append(
                    f"- {claim_id}: verdict={mapping.get('verdict')}; "
                    f"support={mapping.get('support_classification')}; "
                    f"evidence_outcome={mapping.get('evidence_outcome')}; "
                    f"contradiction={mapping.get('contradiction_status')}; "
                    f"experimental_status={mapping.get('tested_status')}."
                )
            body = "\n".join(rows) or "- No claim-verdict mappings were supplied."
        elif section_id == "limitations":
            rows = [
                f"- {item['claim_id']}: {item['support_classification']} — {item['basis']}"
                for item in reportable
                if item.get("support_classification") != "supported"
            ]
            rows.extend(f"- Method limitation: {item}" for item in method_limitations)
            rows.extend(
                f"- Experiment limitation: {item}" for item in experiment_limitations
            )
            rows.extend(
                f"- Source-assessment limitation: {item}"
                for item in source_assessment_limitations
            )
            body = "\n".join(rows) or "- No additional limitations recorded."
        else:
            body = (
                f"This report addresses {title} using {len(reportable)} source-grounded claim(s). "
                "Claims marked insufficient_evidence are retained as limitations, not promoted to verified findings."
            )
        require_text(body, f"section {section_id} body")
        sections.append(
            {
                "section_id": section_id,
                "title": section_title,
                "body": body,
                "evidence_ids": evidence_ids,
                "requirement_ids": requirement_ids,
            }
        )
        markdown_parts.extend([f"\n## {section_title}", body])
    if requirement_bindings:
        sections.append(
            {
                "section_id": "coverage",
                "title": "Required coverage and unresolved gaps",
                "body": coverage_body,
                "evidence_ids": report_evidence_ids,
                "requirement_ids": [
                    str(item.get("requirement_id"))
                    for item in report_requirement_bindings
                ],
            }
        )
        markdown_parts.extend(["\n## Required coverage and unresolved gaps", coverage_body])
    unsupported = [str(item.get("claim_id")) for item in verdicts if item not in reportable]
    if unsupported:
        unsupported_body = "\n".join(
            f"- {claim_id}: excluded from report conclusions because its retained verdict did not meet "
            "the report plan's evidence threshold."
            for claim_id in unsupported
        )
        sections.append(
            {
                "section_id": "unsupported_claims",
                "title": "Unsupported or excluded claims",
                "body": unsupported_body,
                "evidence_ids": report_evidence_ids,
                "requirement_ids": [],
            }
        )
        markdown_parts.extend(["\n## Unsupported or excluded claims", unsupported_body])
    conclusions = [
        {
            "conclusion_id": f"conclusion-{index:03d}",
            "text": str(item.get("claim_text") or "").strip(),
            "claim_ids": [str(item.get("claim_id") or "")],
            "evidence_ids": [
                str(value) for value in item.get("evidence_ids") or [] if str(value).strip()
            ],
            "evidence_status": str(item.get("support_classification") or "source_reported"),
            "tested_status": "not_locally_reproduced",
        }
        for index, item in enumerate(reportable, start=1)
        if str(item.get("claim_text") or "").strip()
    ]
    if conclusions:
        conclusion_body = "\n".join(
            f"- {item['conclusion_id']} [{item['evidence_status']}; not locally reproduced]: "
            f"{item['text']} Evidence: {', '.join(item['evidence_ids'])}."
            for item in conclusions
        )
        markdown_parts.extend(["\n## Evidence-bounded conclusions", conclusion_body])
    review_trace_rows = [
        f"- {item.get('finding_id')} [{item.get('severity')} / {item.get('category')}]: "
        f"{item.get('evidence')} Action: {item.get('suggestion')}"
        for item in plan_review_findings
    ]
    review_trace_body = "\n".join(review_trace_rows) or "- The pre-draft reviewer returned no findings."
    if plan_review:
        sections.append(
            {
                "section_id": "pre_draft_review_trace",
                "title": "Pre-draft artifact review trace",
                "body": review_trace_body,
                "evidence_ids": [
                    str(item) for item in plan_review.get("evidence_ids") or [] if str(item).strip()
                ],
                "requirement_ids": [],
            }
        )
        markdown_parts.extend(["\n## Pre-draft artifact review trace", review_trace_body])
    markdown = "\n".join(markdown_parts).strip() + "\n"
    if semantic_report:
        semantic_sections = [
            {
                **item,
                "evidence_ids": report_evidence_ids,
                "requirement_ids": [
                    str(binding.get("requirement_id")) for binding in requirement_bindings
                ],
            }
            for item in semantic_report.get("sections") or []
        ]
        markdown = require_text(semantic_report.get("body"), "semantic report body").rstrip() + "\n"
        sections = semantic_sections or sections
        if plan_review:
            markdown += "\n## Pre-draft artifact review trace\n" + review_trace_body + "\n"
        if semantic_sections and plan_review:
            sections.append(
                {
                    "section_id": "pre_draft_review_trace",
                    "title": "Pre-draft artifact review trace",
                    "body": review_trace_body,
                    "evidence_ids": [
                        str(item) for item in plan_review.get("evidence_ids") or [] if str(item).strip()
                    ],
                    "requirement_ids": [],
                }
            )
        unknown_resolution_traces = _semantic_unknown_resolution(
            unknown_resolution_traces,
            requirement_bindings,
            markdown,
        )
        report_requirement_bindings = [
            {
                key: value
                for key, value in binding.items()
                if key not in {"status", "coverage_status"}
            }
            for binding in report_requirement_bindings
        ]
    if semantic_report:
        relevant = _semantic_report_is_relevant(title, semantic_report, markdown)
    else:
        relevant = title.casefold() in markdown.casefold()
    if not relevant:
        raise ResearchOperatorError("Draft is not relevant to the requested topic", error_type="product_failure")
    report = {
        "report_id": require_text(plan.get("report_id"), "report_id"),
        "title": title,
        "sections": sections,
        "evidence_ids": sorted(
            {
                str(eid)
                for item in reportable
                for eid in item.get("evidence_ids") or []
            }
            | {
                str(eid)
                for eid in experiment_result.get("evidence_ids") or []
                if str(eid).strip()
            }
            | {
                str(eid)
                for assessment in source_assessment.get("assessments") or []
                if isinstance(assessment, dict)
                for eid in assessment.get("evidence_ids") or []
                if str(eid).strip()
            }
        ),
        "unsupported_claims": unsupported,
        "methods": methods,
        "method_evidence_status": "available" if methods else "insufficient_evidence",
        "requirement_bindings": report_requirement_bindings,
        "unknown_resolution_traces": unknown_resolution_traces,
        "claim_status_mappings": claim_status_mappings,
        "requirement_evaluation_status": (
            "independent_evaluation_required"
            if semantic_report and requirement_bindings
            else "pending_independent_evaluation"
            if requirement_bindings
            else "not_supplied"
        ),
        "conclusions": semantic_report.get("conclusions") or conclusions,
        "scope": {
            "source_count": len(source_assessment.get("selected_source_ids") or []),
            "claim_count": len(reportable),
            "method_count": len(methods),
            "tested_boundary": "Source-reported findings were not locally reproduced unless an experiment result is attached.",
        },
        "comparative_analysis": [
            {
                "family": family,
                "methods": sorted(
                    str(item.get("name") or "")
                    for item in methods
                    if str(item.get("family") or "") == family
                ),
                "evidence_ids": sorted(
                    {
                        str(value)
                        for item in methods
                        if str(item.get("family") or "") == family
                        for value in item.get("evidence_ids") or []
                        if str(value).strip()
                    }
                ),
            }
            for family in sorted(
                {str(item.get("family") or "unclassified") for item in methods}
            )
        ],
        "source_assessments": source_assessment.get("assessments") or [],
        "benchmark_coverage": source_assessment.get("benchmark_candidates") or [],
        "coverage_matrix": report_requirement_bindings,
        "disagreements": [
            item
            for item in claim_status_mappings
            if str(item.get("contradiction_status") or "")
            not in {"", "none", "no_recorded_contradiction"}
        ],
        "experiment": (
            {
                "experiment_id": experiment_result.get("experiment_id"),
                "outcome": experiment_result.get("outcome"),
                "metrics": experiment_result.get("metrics"),
                "evidence_ids": experiment_result.get("evidence_ids"),
            }
            if experiment_result
            else None
        ),
        "study_protocol": study_protocol,
        "pre_draft_review": (
            {
                "reviewed_artifact_sha256": plan_sha256,
                "recommendation": str(plan_review.get("recommendation") or ""),
                "finding_ids": [
                    str(item.get("finding_id") or "")
                    for item in plan_review_findings
                    if str(item.get("finding_id") or "")
                ],
                "disposition": "consumed_and_retained",
            }
            if plan_review
            else None
        ),
        "markdown": markdown,
    }
    extra_artifacts: list[dict[str, Any]] = []
    extra_hashes: list[dict[str, str]] = []
    if len(context.write_scope) > 1:
        markdown_ref, markdown_hash = write_scoped_text(
            context,
            relative_path=context.write_scope[1],
            content=markdown,
            artifact_id="scientific_report_markdown",
            schema="text/markdown",
        )
        extra_artifacts.append(markdown_ref)
        extra_hashes.append(markdown_hash)
    return completed_result(
        context,
        operator_id=REPORT_DRAFTER_ID,
        schema="scientific_report.v1",
        outputs={"report": report},
        filename="scientific_report.v1.json",
        artifact_id="scientific_report",
        limitations=[
            *method_limitations,
            *source_assessment_limitations,
            *experiment_limitations,
            *semantic_limitations,
            *protocol_limitations,
        ],
        extra_artifacts=extra_artifacts,
        extra_hashes=extra_hashes,
        model_provider_usage=semantic_usage,
    )


def _report(context: OperatorContext) -> dict[str, Any]:
    documents = load_documents(context, schemas=("scientific_report.v1",), payload_keys=("report", "scientific_report"))
    values = _outputs(documents[0])
    report = values.get("report") if isinstance(values.get("report"), dict) else values
    if not isinstance(report, dict):
        raise ResearchOperatorError("Scientific report is malformed", error_type="invalid_input")
    return report


def _review_final_report(context: OperatorContext) -> dict[str, Any]:
    """Retain the existing post-draft structural-review behavior for its ABI."""

    report = _report(context)
    findings: list[dict[str, Any]] = []
    markdown = str(report.get("markdown") or "").strip()
    sections = report.get("sections") if isinstance(report.get("sections"), list) else []
    if not markdown:
        findings.append({"finding_id": "empty-report", "severity": "high", "category": "completeness", "evidence": "Report markdown is empty.", "suggestion": "Produce a non-empty report."})
    if len(sections) < 3:
        findings.append({"finding_id": "weak-structure", "severity": "high", "category": "structure", "evidence": f"Only {len(sections)} sections are present.", "suggestion": "Include summary, findings, and limitations."})
    if not report.get("evidence_ids"):
        findings.append({"finding_id": "missing-evidence", "severity": "high", "category": "evidence", "evidence": "No report evidence IDs are present.", "suggestion": "Link supported findings to evidence."})
    if report.get("methods") and "## Methods" not in markdown:
        findings.append({"finding_id": "missing-method-section", "severity": "high", "category": "fidelity", "evidence": "Method evidence exists but the report has no Methods section.", "suggestion": "Render method summary, procedure, evidence IDs, and extraction basis."})
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    score = max(0.0, 1.0 - 0.3 * len(findings))
    recommendation = "pass_with_review_required" if not findings else "revise_required"
    review = {
        "artifact_id": require_text(report.get("report_id"), "report_id"),
        "target": "scientific_report",
        "review_mode": "local_surrogate",
        "review_available": True,
        "difficulty": str(context.payload.get("difficulty") or "standard"),
        "focus": str(context.payload.get("focus") or "completeness"),
        "score": score,
        "recommendation": recommendation,
        "evidence_ids": [str(item) for item in report.get("evidence_ids") or []] or ["review:missing-evidence"],
        "review_scope": "local_structural_only",
        "independent_peer_review": False,
        "task_contract_sha256": stable_json_sha256(task_contract),
        "reviewed_artifact_hashes": {
            "scientific_report": stable_json_sha256(report),
            "task_contract": stable_json_sha256(task_contract),
        },
        "writer_self_assessment_trusted": False,
        "independent_invocation_context": {
            "inputs_reloaded_from_scoped_artifacts": True,
            "checks_recomputed_from_markdown_and_evidence_ids": True,
            "writer_verdict_consumed": False,
        },
    }
    return completed_result(
        context,
        operator_id=ARTIFACT_REVIEWER_ID,
        schema="artifact_review.v1",
        outputs={"review": review, "findings": findings, "artifact": {"report_id": report.get("report_id"), "title": report.get("title")}},
        filename="artifact_review.v1.json",
        artifact_id="artifact_review",
        limitations=["Local structural review does not replace independent scientific peer review."],
    )


def review_artifact(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    documents = load_documents(
        context,
        schemas=("scientific_report_plan.v1",),
        payload_keys=("report_plan",),
        required=False,
    )
    if not documents:
        return _review_final_report(context)
    document = documents[0]
    values = _outputs(document)
    plan = values.get("report_plan") if isinstance(values.get("report_plan"), dict) else values
    if not isinstance(plan, dict) or not plan:
        raise ResearchOperatorError("Scientific report plan is malformed", error_type="invalid_input")
    review_model = context.services.get("review_model_generate")
    if review_model is None:
        raise ResearchOperatorError(
            "Pre-draft artifact review requires the configured review model service",
            error_type="provider_unavailable",
        )
    findings: list[dict[str, Any]] = []
    sections = plan.get("sections") if isinstance(plan.get("sections"), list) else []
    if len(sections) < 3:
        findings.append({"finding_id": "plan.weak-structure", "severity": "high", "category": "structure", "evidence": f"Only {len(sections)} planned sections are present.", "suggestion": "Add enough planned sections to cover methods, findings, limitations, and conclusions."})
    reportable_ids = [
        str(item) for item in (plan.get("reportable_claim_ids") or plan.get("supported_claim_ids") or [])
        if str(item).strip()
    ]
    if not reportable_ids:
        findings.append({"finding_id": "plan.no-reportable-claims", "severity": "high", "category": "evidence", "evidence": "The report plan contains no reportable claim identifiers.", "suggestion": "Retain at least one source-grounded claim or explicitly stop for insufficient evidence."})
    if not [item for item in plan.get("requirement_bindings") or [] if isinstance(item, dict)]:
        findings.append({"finding_id": "plan.no-requirement-bindings", "severity": "high", "category": "coverage", "evidence": "The report plan contains no requirement bindings.", "suggestion": "Bind accepted requirements to report sections and evidence before drafting."})
    protocol = plan.get("study_protocol") if isinstance(plan.get("study_protocol"), dict) else {}
    unresolved_protocol = [str(item) for item in protocol.get("unresolved_fields") or [] if str(item).strip()]
    if unresolved_protocol:
        findings.append({"finding_id": "plan.protocol-unresolved", "severity": "medium", "category": "coverage", "evidence": "Unresolved protocol fields: " + ", ".join(unresolved_protocol), "suggestion": "Retain these fields as explicit limitations unless governed evidence resolves them during drafting."})
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    response = review_model(
        node_id="artifact_review",
        task_contract=task_contract,
        report_plan=plan,
    )
    if not isinstance(response, dict):
        raise ResearchOperatorError(
            "review_model_generate service must return a JSON object",
            error_type="provider_contract_failure",
        )
    for index, item in enumerate(response.get("findings") or [], start=1):
        if not isinstance(item, dict):
            raise ResearchOperatorError(
                "Review model returned a non-object finding",
                error_type="provider_contract_failure",
            )
        message = require_text(item.get("message"), f"review finding {index} message")
        severity = str(item.get("severity") or "").strip().lower()
        if severity not in {"low", "medium", "high", "critical"}:
            raise ResearchOperatorError(
                "Review model returned an unsupported finding severity",
                error_type="provider_contract_failure",
            )
        findings.append(
            {
                "finding_id": require_text(item.get("finding_id"), f"review finding {index} id"),
                "severity": severity,
                "category": require_text(item.get("category"), f"review finding {index} category"),
                "evidence": message,
                "suggestion": f"Address or explicitly retain this pre-draft finding: {message}",
            }
        )
    requested = str(response.get("verdict_suggestion") or "").strip().lower()
    if requested not in {"accept", "revise", "reject"}:
        raise ResearchOperatorError(
            "Review model returned an unsupported verdict suggestion",
            error_type="provider_contract_failure",
        )
    blocking = any(str(item.get("severity") or "") in {"high", "critical"} for item in findings)
    recommendation = "revise_plan" if blocking or requested != "accept" else "ready_with_findings"
    score = max(0.0, 1.0 - 0.2 * sum(str(item.get("severity") or "") in {"high", "critical"} for item in findings) - 0.05 * sum(str(item.get("severity") or "") in {"low", "medium"} for item in findings))
    plan_sha256 = stable_json_sha256(plan)
    evidence_ids = sorted({
        *[str(item.get("finding_id")) for item in findings if item.get("finding_id")],
        *[str(item) for item in reportable_ids],
        f"report-plan:{str(plan.get('report_id') or 'unknown')}",
    })
    review = {
        "artifact_id": require_text(plan.get("report_id"), "report_id"),
        "target_schema": "scientific_report_plan.v1",
        "review_stage": "pre_draft_plan",
        "review_mode": "review_llm",
        "review_available": True,
        "score": score,
        "recommendation": recommendation,
        "evidence_ids": evidence_ids,
        "reviewed_artifact_sha256": plan_sha256,
        "review_scope": "pre_draft_evidence_and_coverage",
        "task_contract_sha256": stable_json_sha256(task_contract),
        "writer_self_assessment_trusted": False,
        "reviewer_usage": [item for item in response.get("provider_usage") or [] if isinstance(item, dict)],
    }
    return completed_result(
        context,
        operator_id=ARTIFACT_REVIEWER_ID,
        schema="scientific_report_plan_review.v1",
        outputs={
            "review": review,
            "findings": findings,
            "artifact": {
                "report_id": plan.get("report_id"),
                "title": plan.get("title"),
                "schema": "scientific_report_plan.v1",
                "sha256": plan_sha256,
            },
        },
        filename="scientific_report_plan_review.v1.json",
        artifact_id="scientific_report_plan_review",
        limitations=[
            *[str(item) for item in response.get("limitations") or [] if str(item).strip()],
            "This pre-draft review guides report generation and does not replace the post-generation Evidence Gate.",
        ],
        model_provider_usage=[item for item in response.get("provider_usage") or [] if isinstance(item, dict)],
    )


def _report_and_optional_review(
    context: OperatorContext,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    documents = load_documents(
        context,
        schemas=("scientific_report.v1", "artifact_review.v1"),
        payload_keys=("report", "artifact_review"),
    )
    report: dict[str, Any] = {}
    review: dict[str, Any] = {}
    requirement_ir = (
        context.payload.get("requirement_ir")
        if isinstance(context.payload.get("requirement_ir"), dict)
        else {}
    )
    findings: list[dict[str, Any]] = []
    for document in documents:
        values = _outputs(document)
        if isinstance(values.get("report"), dict):
            report = values["report"]
        if isinstance(values.get("review"), dict):
            review = values["review"]
            findings = [item for item in values.get("findings") or [] if isinstance(item, dict)]
    if not report:
        raise ResearchOperatorError("Scientific report is required", error_type="missing_input")
    return report, review, findings, requirement_ir


def _safe_delivery_path(value: Any, *, label: str, directory: bool = False) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if directory:
        raw = raw.rstrip("/")
    path = Path(raw)
    if (
        not raw
        or raw.startswith("/")
        or re.match(r"^[A-Za-z]:", raw)
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in raw.split("/"))
    ):
        raise ResearchOperatorError(f"Unsafe delivery path: {label}", error_type="invalid_input")
    return raw


def _json_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in _json_keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in _json_keys(child)}
    return set()


def _validated_delivery_content(row: dict[str, Any], content: Any) -> str:
    text = require_text(content, f"delivery content for {row.get('relative_path')}")
    media_type = str(row.get("media_type") or "")
    required_fields = [str(item) for item in row.get("required_fields") or []]
    if media_type == "application/json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ResearchOperatorError(
                f"Delivery JSON is invalid: {row.get('relative_path')}",
                error_type="provider_contract_failure",
            ) from exc
        missing = [field for field in required_fields if field not in _json_keys(parsed)]
        if missing:
            raise ResearchOperatorError(
                f"Delivery JSON is missing required fields: {', '.join(missing)}",
                error_type="provider_contract_failure",
            )
    elif media_type == "text/csv":
        try:
            header = next(csv.reader(io.StringIO(text)))
        except (csv.Error, StopIteration) as exc:
            raise ResearchOperatorError(
                f"Delivery CSV is invalid: {row.get('relative_path')}",
                error_type="provider_contract_failure",
            ) from exc
        missing = [field for field in required_fields if field not in header]
        if missing:
            raise ResearchOperatorError(
                f"Delivery CSV is missing required columns: {', '.join(missing)}",
                error_type="provider_contract_failure",
            )
    elif media_type == "text/html" and not re.search(r"<html(?:\s|>)", text, re.IGNORECASE):
        raise ResearchOperatorError(
            f"Delivery HTML has no html root: {row.get('relative_path')}",
            error_type="provider_contract_failure",
        )
    return text


def _bind_claim_index_spans(content: str, report: dict[str, Any]) -> str:
    """Replace model-authored citation locations with verified upstream spans."""

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return content
    if not isinstance(payload, dict):
        return content
    claims = payload.get("claims")
    if not isinstance(claims, list):
        return content
    mappings = {
        str(item.get("claim_id") or ""): item
        for item in report.get("claim_status_mappings") or []
        if isinstance(item, dict) and str(item.get("claim_id") or "")
    }
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        mapping = mappings.get(str(claim.get("claim_id") or ""))
        if not mapping:
            continue
        spans = [
            dict(item)
            for item in mapping.get("citation_spans") or []
            if isinstance(item, dict)
        ]
        if spans:
            claim["citation_spans"] = spans
        evidence_ids = [
            str(item)
            for item in mapping.get("evidence_ids") or []
            if str(item).strip()
        ]
        if evidence_ids:
            claim["evidence_ids"] = evidence_ids
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _run_manifest_content(
    content: str,
    *,
    rows: list[dict[str, Any]],
    refs_by_path: dict[str, dict[str, Any]],
    self_path: str,
    run_context: dict[str, Any],
) -> str:
    """Record post-materialization hashes without claiming an impossible self hash."""

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ResearchOperatorError(
            f"Delivery JSON is invalid: {self_path}",
            error_type="provider_contract_failure",
        ) from exc
    if not isinstance(payload, dict):
        raise ResearchOperatorError(
            f"Research run manifest must be a JSON object: {self_path}",
            error_type="provider_contract_failure",
        )
    snapshot = (
        run_context.get("runtime_execution_snapshot")
        if isinstance(run_context.get("runtime_execution_snapshot"), dict)
        else {}
    )
    snapshot_nodes = [
        dict(item)
        for item in snapshot.get("nodes") or []
        if isinstance(item, dict) and str(item.get("node_id") or "").strip()
    ]
    if snapshot.get("availability") != "available" or not snapshot_nodes:
        raise ResearchOperatorError(
            "Research run manifest requires an available Scheduler runtime execution snapshot",
            error_type="invalid_input",
        )

    def bind_node_statuses(existing: Any) -> list[dict[str, Any]]:
        existing_by_id = {
            str(item.get("node_id") or item.get("id") or ""): dict(item)
            for item in existing or []
            if isinstance(item, dict)
            and str(item.get("node_id") or item.get("id") or "").strip()
        }
        bound: list[dict[str, Any]] = []
        for observed in snapshot_nodes:
            node_id = str(observed["node_id"])
            row = existing_by_id.get(node_id, {"node_id": node_id})
            row["node_id"] = node_id
            row["status"] = str(observed.get("status") or "")
            row["attempt"] = int(observed.get("attempt") or 0)
            row["blocked_by"] = [str(value) for value in observed.get("blocked_by") or []]
            row["status_source"] = "scheduler_runtime_execution_snapshot"
            bound.append(row)
        return bound

    graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else {}
    graph["nodes"] = bind_node_statuses(graph.get("nodes"))
    payload["graph"] = graph
    if isinstance(payload.get("nodes"), list):
        payload["nodes"] = bind_node_statuses(payload.get("nodes"))
    payload["runtime_execution_snapshot"] = snapshot
    prior_status = payload.get("status")
    status = dict(prior_status) if isinstance(prior_status, dict) else {}
    if prior_status is not None and not isinstance(prior_status, dict):
        status["semantic_author_status"] = prior_status
    status.update(
        {
            "publication_materialization": "completed_pending_deterministic_evaluation",
            "Evidence Gate": "pending_deterministic_evaluation",
            "Closure-status": "pending_scheduler_closure",
        }
    )
    payload["status"] = status
    existing_paths = {
        str(item.get("relative_path") or ""): item
        for item in payload.get("artifact_paths") or []
        if isinstance(item, dict) and str(item.get("relative_path") or "")
    }
    artifact_paths: list[dict[str, Any]] = []
    artifact_hashes: list[dict[str, str]] = []
    for row in rows:
        relative_path = str(row.get("relative_path") or "")
        if relative_path == self_path:
            continue
        ref = refs_by_path.get(relative_path)
        if not ref:
            raise ResearchOperatorError(
                f"Research run manifest cannot bind missing artifact: {relative_path}",
                error_type="product_failure",
            )
        digest = str(ref.get("sha256") or "")
        item = dict(existing_paths.get(relative_path) or {})
        item.update(
            {
                "relative_path": relative_path,
                "media_type": str(row.get("media_type") or "text/plain"),
                "content_hash_sha256": digest,
            }
        )
        artifact_paths.append(item)
        artifact_hashes.append(
            {"relative_path": relative_path, "algorithm": "sha256", "value": digest}
        )
    payload["artifact_paths"] = artifact_paths
    payload["artifact_hashes"] = artifact_hashes
    payload["manifest_self_hash"] = {
        "relative_path": self_path,
        "algorithm": "sha256",
        "recorded_in": "publication_bundle.v1.outputs.bundle.files",
        "reason": "The outer publication bundle records the byte hash after this manifest is finalized.",
    }
    limitations = [
        str(item)
        for item in payload.get("limitations") or []
        if str(item).strip()
        and not (
            "hash" in str(item).casefold()
            and "could not be computed" in str(item).casefold()
        )
    ]
    payload["limitations"] = limitations
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _publication_limitations(
    response: dict[str, Any], report: dict[str, Any], generated_by_path: dict[str, dict[str, Any]]
) -> list[str]:
    values = [str(item) for item in response.get("limitations") or [] if str(item).strip()]
    for generated in generated_by_path.values():
        try:
            parsed = json.loads(str(generated.get("content") or ""))
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        values.extend(str(item) for item in parsed.get("limitations") or [] if str(item).strip())
        values.extend(
            str(item.get("detail") or "")
            for item in parsed.get("failures_and_degraded_states") or []
            if isinstance(item, dict) and str(item.get("detail") or "").strip()
        )
    for section in report.get("sections") or []:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or "").casefold()
        body = str(section.get("body") or "").strip()
        if body and ("limitation" in title or "evidence gate" in title):
            values.append(body)
    if not values:
        values.append(
            "Bundle materialization preserves the source scientific report's evidence boundary and does not independently validate its claims."
        )
    return list(dict.fromkeys(values))


def _manifest_publication(
    context: OperatorContext,
    *,
    report: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]], list[str], list[dict[str, Any]]]:
    rows = [item for item in manifest.get("files") or [] if isinstance(item, dict)]
    if not rows or len(rows) != len(manifest.get("files") or []):
        raise ResearchOperatorError("Delivery manifest requires file rows", error_type="invalid_input")
    expected_paths = [_safe_delivery_path(row.get("relative_path"), label=f"files[{index}]")
                      for index, row in enumerate(rows)]
    if len(expected_paths) != len(set(expected_paths)):
        raise ResearchOperatorError("Delivery manifest contains duplicate paths", error_type="invalid_input")
    model_generate = context.services.get("model_generate")
    if model_generate is None:
        raise ResearchOperatorError(
            "Manifest-driven publication requires the configured semantic model service",
            error_type="provider_unavailable",
        )
    response = model_generate(
        node_id="publication_produce",
        task_contract=context.payload.get("task_contract") or {},
        delivery_manifest=manifest,
        scientific_report=report,
        run_context=context.payload.get("run_context") or {},
    )
    if not isinstance(response, dict):
        raise ResearchOperatorError(
            "model_generate service must return a JSON object",
            error_type="provider_contract_failure",
        )
    generated = [item for item in response.get("files") or [] if isinstance(item, dict)]
    generated_paths = [str(item.get("relative_path") or "") for item in generated]
    if (
        len(generated) != len(response.get("files") or [])
        or len(generated_paths) != len(set(generated_paths))
        or set(generated_paths) != set(expected_paths)
    ):
        raise ResearchOperatorError(
            "Generated file set does not exactly match delivery manifest",
            error_type="provider_contract_failure",
        )
    generated_by_path = {str(item["relative_path"]): item for item in generated}
    validated_by_path = {
        path: _validated_delivery_content(row, generated_by_path[path].get("content"))
        for row, path in zip(rows, expected_paths)
    }
    for path, row in zip(expected_paths, rows):
        if Path(path).name == "claim_evidence_index.json":
            validated_by_path[path] = _validated_delivery_content(
                row, _bind_claim_index_spans(validated_by_path[path], report)
            )
    first_scope = context.write_scope[0] if context.write_scope else ""
    if not first_scope or Path(first_scope).suffix:
        raise ResearchOperatorError(
            "Manifest-driven publication requires a directory write scope",
            error_type="scope_violation",
        )
    expected_root = _safe_delivery_path(
        manifest.get("output_root"),
        label="output_root",
        directory=True,
    )
    normalized_scope = str(first_scope).replace("\\", "/").rstrip("/")
    if normalized_scope != expected_root and not normalized_scope.endswith("/" + expected_root):
        raise ResearchOperatorError(
            "Frozen publication write scope does not match delivery manifest output_root",
            error_type="scope_violation",
        )
    refs_by_path: dict[str, dict[str, Any]] = {}
    hashes_by_path: dict[str, dict[str, str]] = {}
    run_manifest_paths = [path for path in expected_paths if Path(path).name == "research_run_manifest.json"]
    write_order = [path for path in expected_paths if path not in run_manifest_paths]
    for relative_path in write_order:
        index = expected_paths.index(relative_path) + 1
        row = rows[index - 1]
        artifact_id = f"publication_file_{index}"
        ref, digest = write_scoped_text(
            context,
            relative_path=f"{first_scope.rstrip('/\\')}/{relative_path}",
            content=validated_by_path[relative_path],
            artifact_id=artifact_id,
            schema=str(row.get("media_type") or "text/plain"),
        )
        refs_by_path[relative_path] = ref
        hashes_by_path[relative_path] = digest
    for relative_path in run_manifest_paths:
        index = expected_paths.index(relative_path) + 1
        row = rows[index - 1]
        content = _run_manifest_content(
            validated_by_path[relative_path],
            rows=rows,
            refs_by_path=refs_by_path,
            self_path=relative_path,
            run_context=context.payload.get("run_context") or {},
        )
        content = _validated_delivery_content(row, content)
        ref, digest = write_scoped_text(
            context,
            relative_path=f"{first_scope.rstrip('/\\')}/{relative_path}",
            content=content,
            artifact_id=f"publication_file_{index}",
            schema=str(row.get("media_type") or "application/json"),
        )
        refs_by_path[relative_path] = ref
        hashes_by_path[relative_path] = digest
        generated_by_path[relative_path]["content"] = content
    artifacts = [refs_by_path[path] for path in expected_paths]
    hashes = [hashes_by_path[path] for path in expected_paths]
    files = [
        {
            "type": str(row.get("media_type") or "text/plain"),
            "path": refs_by_path[path]["path"],
            "sha256": refs_by_path[path]["sha256"],
            "manifest_relative_path": path,
        }
        for row, path in zip(rows, expected_paths)
    ]
    limitations = _publication_limitations(response, report, generated_by_path)
    usage = [item for item in response.get("provider_usage") or [] if isinstance(item, dict)]
    return files, artifacts, hashes, limitations, usage


def produce_publication(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    report, review, findings, requirement_ir = _report_and_optional_review(context)
    if review and (
        review.get("recommendation") != "pass_with_review_required"
        or any(item.get("severity") in {"high", "critical"} for item in findings)
    ):
        raise ResearchOperatorError("Artifact review requires revision before publication", error_type="quality_gate_failed")
    publication_type = str(context.payload.get("publication_type") or "paper")
    if publication_type not in {"paper", "poster", "rebuttal", "slides", "supplement", "mixed"}:
        raise ResearchOperatorError("Unsupported publication type", error_type="invalid_input")
    markdown = require_text(report.get("markdown"), "report markdown")
    non_heading_markdown = re.sub(r"(?m)^\s*#+\s+.*$", "", markdown).strip()
    if len(non_heading_markdown) < 80:
        raise ResearchOperatorError("Compiled deliverable body is too small to inspect as a real deliverable", error_type="quality_gate_failed")
    extra_artifacts: list[dict[str, Any]] = []
    extra_hashes: list[dict[str, str]] = []
    result_limitations: list[str] = []
    model_provider_usage: list[dict[str, Any]] = []
    first_scope = context.write_scope[0] if context.write_scope else ""
    markdown_scope = next((scope for scope in context.write_scope if Path(scope).suffix.lower() == ".md"), "")
    semantic_contract = (
        requirement_ir.get("semantic_contract")
        if isinstance(requirement_ir.get("semantic_contract"), dict)
        else {}
    )
    delivery_manifest = semantic_contract.get("delivery_manifest")
    if isinstance(delivery_manifest, dict):
        files, extra_artifacts, extra_hashes, result_limitations, model_provider_usage = _manifest_publication(
            context,
            report=report,
            manifest=delivery_manifest,
        )
    elif markdown_scope:
        compiled_ref, compiled_hash = write_scoped_text(
            context,
            relative_path=markdown_scope,
            content=markdown,
            artifact_id="publication_markdown",
            schema="text/markdown",
        )
        extra_artifacts.append(compiled_ref)
        extra_hashes.append(compiled_hash)
        files = [{"type": "markdown", "path": compiled_ref["path"], "sha256": compiled_ref["sha256"]}]
    elif first_scope and not Path(first_scope).suffix:
        compiled_ref, compiled_hash = write_scoped_text(
            context,
            relative_path=f"{first_scope.rstrip('/\\')}/publication.md",
            content=markdown,
            artifact_id="publication_markdown",
            schema="text/markdown",
        )
        extra_artifacts.append(compiled_ref)
        extra_hashes.append(compiled_hash)
        files = [{"type": "markdown", "path": compiled_ref["path"], "sha256": compiled_ref["sha256"]}]
    else:
        files = [{"type": "embedded_markdown", "path": output_location(context, "publication_bundle.v1.json")}]
    source_report_id = require_text(report.get("report_id"), "source_report_id")
    evidence_ids = list(dict.fromkeys([
        source_report_id,
        *[str(item) for item in report.get("evidence_ids") or [] if str(item).strip()],
    ]))
    bundle = {
        "bundle_id": str(context.payload.get("bundle_id") or f"bundle-{report.get('report_id', 'report')}"),
        "publication_type": publication_type,
        "files": files,
        "source_report_id": source_report_id,
        "evidence_ids": evidence_ids,
        "compiled_markdown": markdown,
        "deliverable_inspection": {
            "status": "inspected",
            "format": "markdown",
            "body_characters": len(non_heading_markdown),
            "evidence_linked": bool(report.get("evidence_ids")),
            "not_schema_only": True,
        },
        "review_score": review.get("score") if review else None,
    }
    if isinstance(delivery_manifest, dict):
        bundle["delivery_manifest"] = delivery_manifest
        bundle["delivery_manifest_sha256"] = stable_json_sha256(delivery_manifest)
        bundle["deliverable_inspection"] = {
            "status": "inspected",
            "format": "mixed" if len({item["type"] for item in files}) > 1 else files[0]["type"],
            "body_characters": sum(len(Path(context.workspace_root, item["path"]).read_text(encoding="utf-8")) for item in files),
            "evidence_linked": bool(report.get("evidence_ids")),
            "not_schema_only": True,
            "exact_manifest_match": True,
        }
    return completed_result(
        context,
        operator_id=PUBLICATION_PRODUCER_ID,
        schema="publication_bundle.v1",
        outputs={"bundle": bundle},
        filename="publication_bundle.v1.json",
        artifact_id="publication_bundle",
        extra_artifacts=extra_artifacts,
        extra_hashes=extra_hashes,
        limitations=result_limitations,
        model_provider_usage=model_provider_usage,
    )


def evaluate_final_publication(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    """Evaluate the produced publication evidence without changing Solar state."""

    documents = load_documents(
        context,
        schemas=(
            "publication_bundle.v1",
            "artifact_review.v1",
            "scientific_report.v1",
            "research_method.v1",
            "claim_verdict.v1",
            "research_paper.v1",
        ),
        payload_keys=("publication_bundle", "artifact_review", "report", "research_method", "verdicts", "research_paper"),
    )
    bundle: dict[str, Any] = {}
    review: dict[str, Any] = {}
    report: dict[str, Any] = {}
    methods: list[dict[str, Any]] = []
    method_limitations: list[str] = []
    verdicts: list[dict[str, Any]] = []
    paper_present = False
    review_limitations: list[str] = []
    for document in documents:
        values = _outputs(document)
        if isinstance(values.get("bundle"), dict):
            bundle = values["bundle"]
        if isinstance(values.get("review"), dict):
            review = values["review"]
            review_limitations.extend(str(item) for item in document.get("limitations") or [] if str(item).strip())
        if isinstance(values.get("report"), dict):
            report = values["report"]
        if isinstance(values.get("methods"), list):
            methods.extend(item for item in values["methods"] if isinstance(item, dict))
            method_limitations.extend(str(item) for item in document.get("limitations") or [] if str(item).strip())
        if isinstance(values.get("verdicts"), list):
            verdicts.extend(item for item in values["verdicts"] if isinstance(item, dict))
        if isinstance(values.get("paper"), dict) and values["paper"].get("sections"):
            paper_present = True
    markdown = str(bundle.get("compiled_markdown") or "").strip()
    normalized_markdown = " ".join(markdown.split()).casefold()
    body_without_headings = re.sub(r"(?m)^\s*#+\s+.*$", "", markdown).strip()
    evidence_ids = [str(item) for item in bundle.get("evidence_ids") or [] if str(item).strip()]
    files = [item for item in bundle.get("files") or [] if isinstance(item, dict)]
    reportable_verdicts = [
        item for item in verdicts
        if str(item.get("claim_text") or "").strip() and _grounded_evidence_ids(item)
    ]
    claims_preserved = bool(reportable_verdicts) and all(
        " ".join(str(item["claim_text"]).split()).casefold() in normalized_markdown
        for item in reportable_verdicts
    )
    method_section_present = "## methods" in markdown.casefold() or "## method" in markdown.casefold()
    if methods:
        method_fidelity = method_section_present and all(
            all(
                " ".join(str(value).split()).casefold() in normalized_markdown
                for value in (
                    item.get("name"),
                    item.get("summary"),
                    *(item.get("procedure") or []),
                    *(item.get("evidence_ids") or []),
                    item.get("extraction_basis"),
                )
                if str(value or "").strip()
            )
            for item in methods
        )
        method_evaluation = "available_and_rendered" if method_fidelity else "available_but_not_rendered"
    else:
        method_fidelity = (
            str(report.get("method_evidence_status") or "") == "insufficient_evidence"
            and method_section_present
            and "insufficient_evidence" in normalized_markdown
            and bool(method_limitations)
        )
        method_evaluation = "insufficient_evidence_disclosed" if method_fidelity else "insufficient_evidence_not_disclosed"
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    deliverable = task_contract.get("deliverable") if isinstance(task_contract.get("deliverable"), dict) else {}
    review_requirement = deliverable.get("review_requirement") if isinstance(deliverable.get("review_requirement"), dict) else {}
    expected_review_mode = str(review_requirement.get("expected_mode") or "local_surrogate")
    independent_required = bool(review_requirement.get("independent_peer_review_required", False))
    limitation_required = bool(review_requirement.get("limitation_disclosure_required", expected_review_mode == "local_surrogate"))
    review_mode_matches = str(review.get("review_mode") or "") == expected_review_mode
    independent_review_honest = (
        (not independent_required and review.get("independent_peer_review") is False)
        or (independent_required and review.get("independent_peer_review") is True)
    )
    review_limitation_disclosed = not limitation_required or bool(review_limitations)
    review_contract_matches = str(review.get("task_contract_sha256") or "") == stable_json_sha256(task_contract)
    review_passed = (
        review.get("recommendation") == "pass_with_review_required"
        and review_mode_matches
        and independent_review_honest
        and review_limitation_disclosed
        and review_contract_matches
    )
    prompt = str(task_contract.get("user_intent") or "")
    ignored_terms = {"report", "research", "paper", "source", "using", "synthesize", "synthesis", "attached", "local", "please"}
    intent_terms = {
        value.casefold() for value in re.findall(r"[^\W\d_]{4,}", prompt, flags=re.UNICODE)
        if value.casefold() not in ignored_terms
    }
    overlap = {term for term in intent_terms if term in normalized_markdown}
    relevance_passed = claims_preserved and (not intent_terms or bool(overlap))
    checks = {
        "publication_bundle_present": bool(bundle),
        "non_empty_report": len(body_without_headings) >= 80,
        "evidence_linked": bool(evidence_ids),
        "usable_file_manifest": bool(files),
        "artifact_review_passed": review_passed,
        "user_intent_relevance": relevance_passed,
        "core_result_claims_present": claims_preserved,
        "method_evidence_honestly_rendered": method_fidelity,
    }
    requirement_results: list[dict[str, str]] = []
    for requirement in deliverable.get("required_content") or []:
        if not isinstance(requirement, dict):
            continue
        requirement_id = str(requirement.get("requirement_id") or "").strip()
        if requirement_id == "method_evidence":
            passed, evidence = method_fidelity, method_evaluation
        elif requirement_id == "result_claims":
            passed, evidence = claims_preserved, f"Preserved {len(reportable_verdicts)} source-grounded result claim(s)."
        elif requirement_id == "limitations":
            passed = "## limitations" in markdown.casefold() and bool(report.get("sections"))
            evidence = "The final report has an explicit Limitations section." if passed else "The final report lacks an explicit Limitations section."
        else:
            passed, evidence = False, "No deterministic evaluator is registered for this explicit requirement."
        requirement_results.append({
            "requirement_id": requirement_id or "invalid_requirement",
            "status": "passed" if passed else "failed",
            "evidence": evidence,
        })
    criterion_results: list[dict[str, str]] = []
    for criterion in task_contract.get("success_criteria") or []:
        normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", str(criterion).lower()).split())
        if "parsed" in normalized and "local source" in normalized:
            passed, evidence = paper_present, "A parsed research_paper.v1 with source sections is present."
        elif ("reported claim" in normalized or "conclusion" in normalized) and ("evidence" in normalized or "source" in normalized):
            passed, evidence = claims_preserved, "Source-grounded claim text and evidence IDs were checked against the final report."
        elif "final report" in normalized and ("non empty" in normalized or "body content" in normalized):
            passed, evidence = checks["non_empty_report"], f"Non-heading report body length is {len(body_without_headings)} characters."
        elif "local structural review" in normalized and "limitation" in normalized:
            passed, evidence = review_passed, "Review mode, task-contract hash, independence flag, and limitation disclosure were checked."
        else:
            passed, evidence = False, "Criterion was not evaluated because no deterministic evaluator is registered."
        criterion_results.append({
            "criterion": str(criterion),
            "status": "passed" if passed else "failed",
            "evidence": evidence,
        })
    accepted = (
        all(checks.values())
        and bool(criterion_results)
        and all(item["status"] in {"passed", "not_applicable"} for item in criterion_results)
        and all(item["status"] in {"passed", "not_applicable"} for item in requirement_results)
    )
    if not accepted:
        failed_checks = [key for key, value in checks.items() if not value]
        failed_checks.extend(f"criterion:{item['criterion']}" for item in criterion_results if item["status"] == "failed")
        failed_checks.extend(f"requirement:{item['requirement_id']}" for item in requirement_results if item["status"] == "failed")
        raise ResearchOperatorError(
            f"Final publication evaluation failed: {', '.join(failed_checks)}",
            error_type="quality_gate_failed",
        )
    evaluation_limitations = [
        "Final evaluation assesses produced evidence; Solar alone derives and commits the run final status.",
        *review_limitations,
        *method_limitations,
    ]
    evaluation_limitations = list(dict.fromkeys(item for item in evaluation_limitations if item))
    evaluation = {
        "decision": "accepted_with_limitations" if len(evaluation_limitations) > 1 else "accepted",
        "accepted": True,
        "blockers": [],
        "residual_risks": evaluation_limitations,
        "follow_up": [
            "Run independent peer review before representing the deliverable as externally validated."
        ] if review_limitations else [],
        "checks": checks,
        "criterion_results": criterion_results,
        "requirement_results": requirement_results,
        "method_evaluation": method_evaluation,
        "review_assessment": {
            "expected_mode": expected_review_mode,
            "actual_mode": str(review.get("review_mode") or ""),
            "independent_peer_review_required": independent_required,
            "independent_peer_review_performed": review.get("independent_peer_review") is True,
            "task_contract_matches": review_contract_matches,
            "limitation_disclosed": review_limitation_disclosed,
        },
        "source_report_id": str(bundle.get("source_report_id") or ""),
        "publication_bundle_id": str(bundle.get("bundle_id") or ""),
        "evidence_ids": evidence_ids,
        "run_provenance": task_contract.get("run_provenance") if isinstance(task_contract.get("run_provenance"), dict) else {},
        "does_not_modify_graph_or_run_state": True,
    }
    return completed_result(
        context,
        operator_id=FINAL_EVALUATOR_ID,
        schema="research_final_evaluation.v1",
        outputs={"evaluation": evaluation},
        filename="research_final_evaluation.v1.json",
        artifact_id="research_final_evaluation",
        limitations=evaluation_limitations,
    )


def propose_workflow_evolution(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    observations = load_documents(
        context,
        schemas=("artifact_review.v1", "experiment_status.v1", "claim_verdict.v1", "research_memory_update.v1"),
        payload_keys=("observations", "findings"),
    )
    evidence_ids = sorted({
        str(item)
        for document in observations
        for item in (
            (_outputs(document).get("review") or {}).get("evidence_ids")
            if isinstance((_outputs(document).get("review") or {}), dict)
            else []
        ) or []
        if str(item).strip()
    }) or ["workflow-observation:local"]
    target = require_text(context.payload.get("target") or "scientific_research_lifecycle_full_v1", "target")
    description = require_text(context.payload.get("description") or "Review lifecycle evidence and strengthen the failing gate.", "description")
    change = {
        "change_id": str(context.payload.get("change_id") or "workflow-change-001"),
        "category": str(context.payload.get("category") or "gate"),
        "target": target,
        "description": description,
        "evidence_ids": evidence_ids,
        "review_required": True,
        "application_state": "proposed_only",
    }
    evolution = {
        "proposal_id": str(context.payload.get("proposal_id") or "workflow-evolution-001"),
        "scope": target,
        "change_type": str(context.payload.get("change_type") or "gate"),
        "rationale": require_text(context.payload.get("rationale") or "Observed lifecycle evidence indicates a bounded improvement opportunity.", "rationale"),
        "expected_effect": require_text(context.payload.get("expected_effect") or "Reduce recurrence of the observed failure without changing production state automatically.", "expected_effect"),
        "approval_state": "proposed",
        "evidence_ids": evidence_ids,
        "proposed_changes": [change],
        "review": {
            "human_accept_reject_required": True,
            "protected_core_edits_applied": False,
            "application_state": "proposed_only",
        },
    }
    return completed_result(
        context,
        operator_id=WORKFLOW_EVOLVER_ID,
        schema="workflow_evolution.v1",
        outputs={"evolution": evolution},
        filename="workflow_evolution.v1.json",
        artifact_id="workflow_evolution",
        limitations=["This operator emits proposals only and never mutates workflow definitions."],
    )
