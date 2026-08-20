"""Claim verification, report, review, publication, and evolution operators."""

from __future__ import annotations

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
        schemas=("research_claims.v1", "experiment_result.v1", "code_evidence_map.v1"),
        payload_keys=("claims", "experiment_result"),
    )
    claims: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
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
    require_list(claims, "claims")
    experiment = results[0] if results else {}
    outcome = str(experiment.get("outcome") or "inconclusive")
    experiment_evidence = [str(item) for item in experiment.get("evidence_ids") or [] if str(item).strip()]
    criteria_results = experiment.get("criteria_results") if isinstance(experiment.get("criteria_results"), dict) else {}
    verdicts: list[dict[str, Any]] = []
    for claim in claims:
        claim_id = require_text(claim.get("claim_id"), "claim_id")
        criteria = [str(item) for item in claim.get("acceptance_criteria") or [] if str(item).strip()]
        matched = bool(criteria) and all(criteria_results.get(item) is True for item in criteria)
        rejected = any(criteria_results.get(item) is False for item in criteria)
        scope_comparison = compare_claim_evidence_scope(claim, experiment)
        scope_risks = list(scope_comparison["risks"])
        if outcome == "refutes" or rejected:
            verdict, support_class, confidence = "not_supported", "unsupported", 0.9
            basis = "Experiment evidence refutes the claim or fails an explicit acceptance criterion."
        elif scope_risks:
            verdict, support_class, confidence = "insufficient", "insufficient_evidence", 0.35
            basis = "Claim scope exceeds the available evidence; local support cannot establish the broader assertion."
        elif outcome == "supports" and experiment_evidence and matched:
            verdict, support_class, confidence = "supported", "supported", 0.9
            basis = "Experiment evidence supports every explicit claim acceptance criterion."
        else:
            verdict, support_class, confidence = "insufficient", "insufficient_evidence", 0.3
            basis = "Evidence does not establish every explicit acceptance criterion."
        evidence_ids = sorted(set([*experiment_evidence, *[str(item) for item in claim.get("evidence_ids") or [] if str(item).strip()]]))
        if not evidence_ids:
            evidence_ids = [f"missing-evidence:{claim_id}"]
        verdicts.append({
            "claim_id": claim_id,
            "claim_text": str(claim.get("text") or "").strip(),
            "verdict": verdict,
            "support_classification": support_class,
            "confidence": confidence,
            "basis": basis,
            "evidence_ids": evidence_ids,
            "limitations": [] if support_class != "insufficient_evidence" else [*(scope_risks or ["Missing or incomplete acceptance-criteria evidence."])],
            "acceptance_criteria_checked": criteria,
            "evidence_outcome": "insufficient_evidence" if support_class == "insufficient_evidence" else outcome,
            "overclaim_risks": scope_risks,
            "scope_comparison": scope_comparison,
        })
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


def plan_report(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    verdicts = _verdicts(context)
    reportable = [
        item for item in verdicts
        if _grounded_evidence_ids(item) and str(item.get("claim_text") or "").strip()
    ]
    if not reportable:
        raise ResearchOperatorError("No source-grounded claims are available for the report", error_type="insufficient_evidence")
    topic = require_text(context.payload.get("topic") or context.payload.get("title"), "report topic")
    evidence_ids = sorted({evidence_id for item in reportable for evidence_id in _grounded_evidence_ids(item)})
    sections = [
        {"section_id": "summary", "title": f"Summary: {topic}", "purpose": "Answer the requested topic.", "evidence_ids": evidence_ids},
        {"section_id": "findings", "title": "Source-grounded findings", "purpose": "Present claims with their unchanged verification classification.", "evidence_ids": evidence_ids},
        {"section_id": "limitations", "title": "Limitations", "purpose": "List unsupported and insufficient claims.", "evidence_ids": evidence_ids},
    ]
    plan = {
        "report_id": str(context.payload.get("report_id") or "scientific-report"),
        "title": topic,
        "audience": str(context.payload.get("audience") or "researcher"),
        "sections": sections,
        # The ABI field is retained for compatibility.  It means reportable,
        # evidence-linked claims here; each claim's support classification is
        # preserved in the report and is never promoted from inconclusive.
        "supported_claim_ids": [str(item["claim_id"]) for item in reportable],
        "excluded_claim_ids": [str(item["claim_id"]) for item in verdicts if item not in reportable],
        "evidence_ids": evidence_ids,
    }
    return completed_result(
        context,
        operator_id=REPORT_PLANNER_ID,
        schema="scientific_report_plan.v1",
        outputs={"report_plan": plan},
        filename="scientific_report_plan.v1.json",
        artifact_id="scientific_report_plan",
    )


def _report_plan_and_verdicts(context: OperatorContext) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    documents = load_documents(
        context,
        schemas=("scientific_report_plan.v1", "claim_verdict.v1", "research_method.v1"),
        payload_keys=("report_plan", "verdicts", "research_method"),
    )
    plan: dict[str, Any] = {}
    verdicts: list[dict[str, Any]] = []
    methods: list[dict[str, Any]] = []
    method_limitations: list[str] = []
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
    if not plan or not verdicts:
        raise ResearchOperatorError("Report plan and claim verdict evidence are required", error_type="missing_input")
    return plan, verdicts, methods, method_limitations


def draft_report(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    plan, verdicts, methods, method_limitations = _report_plan_and_verdicts(context)
    supported_ids = set(str(item) for item in plan.get("supported_claim_ids") or [])
    reportable = [item for item in verdicts if str(item.get("claim_id")) in supported_ids]
    if not reportable:
        raise ResearchOperatorError("Report plan has no still-reportable source-grounded claim", error_type="insufficient_evidence")
    title = require_text(plan.get("title"), "report title")
    sections: list[dict[str, Any]] = []
    markdown_parts = [f"# {title}"]
    methods_rendered = False
    for section in require_list(plan.get("sections"), "report sections"):
        section_id = require_text(section.get("section_id"), "section_id")
        section_title = require_text(section.get("title"), "section title")
        evidence_ids = [str(item) for item in section.get("evidence_ids") or [] if str(item).strip()]
        if section_id == "limitations" and not methods_rendered:
            method_rows = ["\n## Methods"]
            if methods:
                for method in methods:
                    name = require_text(method.get("name"), "method name")
                    summary = require_text(method.get("summary"), "method summary")
                    procedure = [str(item).strip() for item in method.get("procedure") or [] if str(item).strip()]
                    evidence_ids_for_method = [str(item).strip() for item in method.get("evidence_ids") or [] if str(item).strip()]
                    extraction_basis = require_text(method.get("extraction_basis"), "method extraction basis")
                    method_rows.extend([
                        f"\n### {name}",
                        f"- Summary: {summary}",
                        "- Procedure:",
                        *[f"  {index}. {step}" for index, step in enumerate(procedure, start=1)],
                        f"- Evidence IDs: {', '.join(evidence_ids_for_method) or 'unavailable'}",
                        f"- Extraction basis: {extraction_basis}",
                    ])
            else:
                method_rows.append("Method evidence status: insufficient_evidence.")
                method_rows.extend(f"- Method limitation: {item}" for item in method_limitations)
            markdown_parts.extend(method_rows)
            sections.append({
                "section_id": "methods",
                "title": "Methods",
                "body": "\n".join(method_rows[1:]).strip(),
                "evidence_ids": sorted({
                    str(evidence_id)
                    for method in methods
                    for evidence_id in method.get("evidence_ids") or []
                    if str(evidence_id).strip()
                }),
            })
            methods_rendered = True
        if section_id == "findings":
            body = "\n".join(
                f"- {item['claim_id']} ({item['support_classification']}): {item['claim_text']} "
                f"Evidence: {', '.join(str(value) for value in item.get('evidence_ids') or [])}."
                for item in reportable
            )
        elif section_id == "limitations":
            rows = [
                f"- {item['claim_id']}: {item['support_classification']} — {item['basis']}"
                for item in reportable
                if item.get("support_classification") != "supported"
            ]
            rows.extend(f"- Method limitation: {item}" for item in method_limitations)
            body = "\n".join(rows) or "- No additional limitations recorded."
        else:
            body = (
                f"This report addresses {title} using {len(reportable)} source-grounded claim(s). "
                "Claims marked insufficient_evidence are retained as limitations, not promoted to verified findings."
            )
        require_text(body, f"section {section_id} body")
        sections.append({"section_id": section_id, "title": section_title, "body": body, "evidence_ids": evidence_ids})
        markdown_parts.extend([f"\n## {section_title}", body])
    markdown = "\n".join(markdown_parts).strip() + "\n"
    if title.lower() not in markdown.lower():
        raise ResearchOperatorError("Draft is not relevant to the requested topic", error_type="product_failure")
    unsupported = [str(item.get("claim_id")) for item in verdicts if item not in reportable]
    report = {
        "report_id": require_text(plan.get("report_id"), "report_id"),
        "title": title,
        "sections": sections,
        "evidence_ids": sorted({str(eid) for item in reportable for eid in item.get("evidence_ids") or []}),
        "unsupported_claims": unsupported,
        "methods": methods,
        "method_evidence_status": "available" if methods else "insufficient_evidence",
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
        limitations=method_limitations,
        extra_artifacts=extra_artifacts,
        extra_hashes=extra_hashes,
    )


def _report(context: OperatorContext) -> dict[str, Any]:
    documents = load_documents(context, schemas=("scientific_report.v1",), payload_keys=("report", "scientific_report"))
    values = _outputs(documents[0])
    report = values.get("report") if isinstance(values.get("report"), dict) else values
    if not isinstance(report, dict):
        raise ResearchOperatorError("Scientific report is malformed", error_type="invalid_input")
    return report


def review_artifact(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
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


def _report_and_review(context: OperatorContext) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    documents = load_documents(
        context,
        schemas=("scientific_report.v1", "artifact_review.v1"),
        payload_keys=("report", "artifact_review"),
    )
    report: dict[str, Any] = {}
    review: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []
    for document in documents:
        values = _outputs(document)
        if isinstance(values.get("report"), dict):
            report = values["report"]
        if isinstance(values.get("review"), dict):
            review = values["review"]
            findings = [item for item in values.get("findings") or [] if isinstance(item, dict)]
    if not report or not review:
        raise ResearchOperatorError("Report and artifact review are required", error_type="missing_input")
    return report, review, findings


def produce_publication(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    report, review, findings = _report_and_review(context)
    if review.get("recommendation") != "pass_with_review_required" or any(item.get("severity") == "high" for item in findings):
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
    first_scope = context.write_scope[0] if context.write_scope else ""
    markdown_scope = next((scope for scope in context.write_scope if Path(scope).suffix.lower() == ".md"), "")
    if markdown_scope:
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
            relative_path=first_scope.rstrip("/\\") + "/publication.md",
            content=markdown,
            artifact_id="publication_markdown",
            schema="text/markdown",
        )
        extra_artifacts.append(compiled_ref)
        extra_hashes.append(compiled_hash)
        files = [{"type": "markdown", "path": compiled_ref["path"], "sha256": compiled_ref["sha256"]}]
    else:
        files = [{"type": "embedded_markdown", "path": output_location(context, "publication_bundle.v1.json")}]
    bundle = {
        "bundle_id": str(context.payload.get("bundle_id") or f"bundle-{report.get('report_id', 'report')}"),
        "publication_type": publication_type,
        "files": files,
        "source_report_id": require_text(report.get("report_id"), "source_report_id"),
        "evidence_ids": [str(item) for item in report.get("evidence_ids") or []],
        "compiled_markdown": markdown,
        "deliverable_inspection": {
            "status": "inspected",
            "format": "markdown",
            "body_characters": len(non_heading_markdown),
            "evidence_linked": bool(report.get("evidence_ids")),
            "not_schema_only": True,
        },
        "review_score": review.get("score"),
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
