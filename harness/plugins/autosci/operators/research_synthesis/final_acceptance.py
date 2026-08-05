"""Fail-closed deterministic gate for the draft research synthesis chain."""

from __future__ import annotations

import re
from typing import Any

from .base import (
    OperatorContext,
    ResearchOperatorError,
    build_node_result,
    evidence_ref,
    load_artifact,
    output_path,
    require_node,
    utc_now,
    write_artifact,
)


REJECTING_SEVERITIES = {"high", "critical"}
BASELINE_ARTIFACTS = ("independent_review", "report_draft", "evidence_synthesis", "source_validation")
ARTIFACT_ALIASES = {
    "independent_review": {
        "independent_review", "review_verdict", "review_outcome",
        "independent_acceptance_verdict", "acceptance_verdict",
    },
    "report_draft": {
        "report_draft", "draft_report", "report", "final_report",
        "markdown_report", "research_report", "report_artifact",
    },
    "evidence_synthesis": {
        "evidence_synthesis", "synthesis_notes", "synthesis",
        "evidence_index", "citation_index", "evidence_map", "claim_evidence_index",
    },
    "source_validation": {
        "source_validation", "validated_sources", "source_list",
        "validated_source_list", "source_index", "validated_source_index",
    },
}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _has_substantive_report_section(report_body: str, heading_pattern: str) -> bool:
    numbering = (
        r"(?:(?:\d+(?:\.\d+)*[.)\u3001\uff0e]?)|"
        r"(?:[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+[\u3001.\uff0e]))\s*"
    )
    heading = re.search(
        rf"(?im)^##\s+(?:{numbering})?[^\r\n]*(?:{heading_pattern})[^\r\n]*$",
        report_body,
    )
    if not heading:
        return False
    section_body = re.split(r"(?m)^#{1,2}\s+", report_body[heading.end():], maxsplit=1)[0]
    return bool(re.search(r"[A-Za-z0-9\u4e00-\u9fff]", section_body))


def _artifact_kind(value: str) -> str:
    normalized = _normalize(value)
    for kind, aliases in ARTIFACT_ALIASES.items():
        if normalized in aliases:
            return kind
    return ""


def _required_artifacts(context: OperatorContext) -> tuple[list[str], list[str]]:
    raw = context.payload.get("required_artifacts")
    if not isinstance(raw, list):
        task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
        deliverable = task_contract.get("deliverable") if isinstance(task_contract.get("deliverable"), dict) else {}
        raw = deliverable.get("artifact_expectations", [])
    required = list(BASELINE_ARTIFACTS)
    unsupported: list[str] = []
    for item in raw if isinstance(raw, list) else []:
        expectation = str(item).strip()
        if not expectation:
            continue
        kind = _artifact_kind(expectation)
        if kind:
            required.append(kind)
        else:
            unsupported.append(expectation)
    return list(dict.fromkeys(required)), unsupported


def _load_chain_artifacts(
    context: OperatorContext,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
    specs = {
        "independent_review": "research_synthesis.independent_review.v1",
        "report_draft": "research_synthesis.report_draft.v1",
        "evidence_synthesis": "research_synthesis.evidence_synthesis.v1",
        "source_validation": "research_synthesis.source_validation.v1",
    }
    artifacts: dict[str, dict[str, Any]] = {}
    refs: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    for node_id, schema in specs.items():
        try:
            payload, ref = load_artifact(
                context,
                schemas=(schema,),
                artifact_ids=(node_id,),
                filenames=(f"{node_id}.json",),
                payload_keys=(),
                expected_node_ids=(node_id,),
                require_hash=True,
            )
        except ResearchOperatorError as exc:
            issues.append(f"{node_id}: {exc}")
            continue
        if not payload or ref is None:
            issues.append(f"{node_id}: actual scoped artifact reference is missing")
            continue
        artifacts[node_id] = payload
        refs[node_id] = ref
    return artifacts, refs, issues


def _recompute_chain(
    artifacts: dict[str, dict[str, Any]],
    refs: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    review = artifacts.get("independent_review", {})
    report_draft = artifacts.get("report_draft", {})
    synthesis = artifacts.get("evidence_synthesis", {})
    validation = artifacts.get("source_validation", {})
    report = report_draft.get("report") if isinstance(report_draft.get("report"), dict) else {}
    report_body = str(report.get("body") or "").strip()
    normalized_report_body = " ".join(report_body.split()).casefold()
    conclusions = [item for item in report.get("conclusions", []) if isinstance(item, dict)]
    claims = [item for item in synthesis.get("claims", []) if isinstance(item, dict)]
    accepted = [item for item in validation.get("accepted", []) if isinstance(item, dict)]
    accepted_source_ids = {str(item.get("source_id")) for item in accepted if item.get("source_id")}
    synthesis_lineage = synthesis.get("input_lineage") if isinstance(synthesis.get("input_lineage"), dict) else {}
    synthesis_hashes = synthesis.get("input_artifact_hashes") if isinstance(synthesis.get("input_artifact_hashes"), dict) else {}
    report_hashes = report_draft.get("input_artifact_hashes") if isinstance(report_draft.get("input_artifact_hashes"), dict) else {}
    reviewed_hashes = review.get("reviewed_artifact_hashes") if isinstance(review.get("reviewed_artifact_hashes"), dict) else {}
    report_lineage = {_artifact_kind(str(item)) for item in report_draft.get("evidence_lineage", []) if str(item).strip()}
    review_lineage = {_artifact_kind(str(item)) for item in review.get("evidence_lineage", []) if str(item).strip()}
    claim_sources = {
        str(item.get("claim_id")): {str(source_id) for source_id in item.get("evidence_ids", []) if str(source_id).strip()}
        for item in claims if item.get("claim_id")
    }
    report_claim_sources = report_draft.get("claim_source_lineage") if isinstance(report_draft.get("claim_source_lineage"), dict) else {}
    cited_claim_ids: set[str] = set()
    cited_source_ids: set[str] = set()

    if not accepted_source_ids:
        issues.append("source_validation contains no accepted sources")
    if not claims:
        issues.append("evidence_synthesis contains no claims")
    if str(synthesis_lineage.get("source_validation") or "") != "source_validation":
        issues.append("evidence_synthesis does not preserve source_validation lineage")
    if str(synthesis_hashes.get("source_validation") or "") != str(refs.get("source_validation", {}).get("sha256") or ""):
        issues.append("evidence_synthesis source_validation hash lineage does not match the actual artifact")
    if "evidence_synthesis" not in report_lineage or "source_validation" not in report_lineage:
        issues.append("report_draft does not preserve synthesis and validation lineage")
    if str(report_hashes.get("evidence_synthesis") or "") != str(refs.get("evidence_synthesis", {}).get("sha256") or ""):
        issues.append("report_draft synthesis hash lineage does not match the actual artifact")
    if not conclusions:
        issues.append("report_draft contains no conclusions")
    for claim_id, source_ids in claim_sources.items():
        if not source_ids:
            issues.append(f"synthesis claim `{claim_id}` has no source ids")
        unknown = sorted(source_ids - accepted_source_ids)
        if unknown:
            issues.append(f"synthesis claim `{claim_id}` cites unvalidated sources: {', '.join(unknown)}")
        declared_sources = report_claim_sources.get(claim_id)
        normalized_declared = {str(value) for value in declared_sources if str(value).strip()} if isinstance(declared_sources, list) else set()
        if normalized_declared != source_ids:
            issues.append(f"report claim lineage for `{claim_id}` does not match evidence_synthesis")
    for index, conclusion in enumerate(conclusions, start=1):
        conclusion_claims = {str(value) for value in conclusion.get("evidence_ids", []) if str(value).strip()}
        if not conclusion_claims:
            issues.append(f"report conclusion {index} has no evidence ids")
        unknown_claims = sorted(conclusion_claims - set(claim_sources))
        if unknown_claims:
            issues.append(f"report conclusion {index} cites unknown claims: {', '.join(unknown_claims)}")
        cited_claim_ids.update(conclusion_claims)
        for claim_id in conclusion_claims & set(claim_sources):
            cited_source_ids.update(claim_sources[claim_id])
        conclusion_text = " ".join(str(conclusion.get("text") or "").split()).casefold()
        if not conclusion_text or conclusion_text not in normalized_report_body:
            issues.append(f"report conclusion {index} is not rendered in the report body")
    expected_review_lineage = set(BASELINE_ARTIFACTS) - {"independent_review"}
    if not expected_review_lineage.issubset(review_lineage):
        issues.append("independent_review lineage omits an actual upstream artifact")
    for reviewed_kind in ("report_draft", "source_validation"):
        if str(reviewed_hashes.get(reviewed_kind) or "") != str(refs.get(reviewed_kind, {}).get("sha256") or ""):
            issues.append(f"independent_review {reviewed_kind} hash does not match the actual artifact")

    findings = [item for item in review.get("findings", []) if isinstance(item, dict)] if isinstance(review.get("findings"), list) else []
    high_risk = [item for item in findings if str(item.get("severity") or "").lower() in REJECTING_SEVERITIES]
    verdict = str(review.get("verdict_suggestion") or "").strip().lower()
    provider_limitations = [
        " ".join(str(item).split()).casefold()
        for item in report_draft.get("limitations", [])
        if str(item).strip()
    ] if isinstance(report_draft.get("limitations"), list) else []
    limitations_section_present = _has_substantive_report_section(
        report_body,
        r"limitations?\b|\u5c40\u9650|\u9650\u5236|\u4e0d\u8db3",
    )
    provider_limitations_rendered = all(item in normalized_report_body for item in provider_limitations)
    facts = {
        "chain_complete": not issues,
        "seed_collected": bool(str(synthesis_lineage.get("seed_snapshot") or "")),
        "validated_source_count": len(accepted_source_ids),
        "claim_count": len(claim_sources),
        "conclusion_count": len(conclusions),
        "cited_claim_count": len(cited_claim_ids),
        "cited_source_count": len(cited_source_ids),
        "all_conclusions_grounded": bool(conclusions) and not any(
            "not rendered" not in issue
            and any(token in issue for token in ("conclusion", "claim", "source"))
            for issue in issues
        ),
        "report_body_present": bool(report_body),
        "all_conclusions_rendered": bool(conclusions) and all(
            bool(" ".join(str(item.get("text") or "").split()))
            and " ".join(str(item.get("text") or "").split()).casefold() in normalized_report_body
            for item in conclusions
        ),
        "limitations_rendered": limitations_section_present and provider_limitations_rendered,
        "method_rendered": _has_substantive_report_section(
            report_body,
            r"methods?\b|\u65b9\u6cd5|\u65b9\u6cd5\u8bba",
        ),
        "review_verdict": verdict,
        "high_risk_finding_count": len(high_risk),
        "review_finding_count": len(findings),
    }
    claimed_chain = review.get("chain_validation") if isinstance(review.get("chain_validation"), dict) else {}
    if claimed_chain and bool(claimed_chain.get("complete")) != bool(facts["chain_complete"]):
        issues.append("independent_review chain_validation conflicts with recomputed artifact chain")
        facts["chain_complete"] = False
    return facts, issues


def _evaluate_clause(clause: str, facts: dict[str, Any]) -> dict[str, str]:
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", clause.lower()).split())
    unsupported = {"roughly", "approximately", "about", "adequate", "good", "quality", "unless", "except", "without"}
    if any(re.search(rf"\b{token}\b", normalized) for token in unsupported) or re.search(r"\bnot\b", normalized):
        return {"clause": clause, "status": "unsupported", "evidence": "Ambiguous or negated wording has no deterministic evaluator."}

    numeric_patterns = (
        (r"at least (\d+) validated sources?", "validated_source_count", lambda actual, target: actual >= target),
        (r"exactly (\d+) validated sources?", "validated_source_count", lambda actual, target: actual == target),
        (r"at least (\d+) conclusions?", "conclusion_count", lambda actual, target: actual >= target),
        (r"exactly (\d+) conclusions?", "conclusion_count", lambda actual, target: actual == target),
        (r"at least (\d+) cited sources?", "cited_source_count", lambda actual, target: actual >= target),
        (r"at most (\d+) high (?:or )?critical findings?", "high_risk_finding_count", lambda actual, target: actual <= target),
    )
    for pattern, fact_key, comparison in numeric_patterns:
        match = re.fullmatch(pattern, normalized)
        if match:
            target = int(match.group(1))
            actual = int(facts.get(fact_key) or 0)
            passed = comparison(actual, target)
            return {"clause": clause, "status": "passed" if passed else "failed", "evidence": f"Observed {fact_key}={actual}; required threshold={target}."}
    if re.search(r"\d", normalized):
        return {"clause": clause, "status": "unsupported", "evidence": "Numeric wording does not match a supported exact threshold form."}
    if "conclusion" in normalized and any(token in normalized for token in ("evidence", "citation", "source")):
        passed = bool(facts.get("all_conclusions_grounded"))
        return {"clause": clause, "status": "passed" if passed else "failed", "evidence": "Conclusion lineage was recomputed from actual artifacts."}
    if "report" in normalized and any(token in normalized for token in ("non empty", "body", "content")):
        passed = bool(facts.get("report_body_present"))
        return {"clause": clause, "status": "passed" if passed else "failed", "evidence": "Report body or sections are present." if passed else "Report body and sections are empty."}
    if "independent review" in normalized and any(token in normalized for token in ("accept", "outcome", "verdict")):
        passed = facts.get("review_verdict") == "accept"
        return {"clause": clause, "status": "passed" if passed else "failed", "evidence": f"Independent review verdict is `{facts.get('review_verdict') or 'missing'}`."}
    if "validated source" in normalized and any(token in normalized for token in ("trace", "ground", "cite", "linked", "produced")):
        passed = int(facts.get("validated_source_count") or 0) > 0 and bool(facts.get("chain_complete"))
        return {"clause": clause, "status": "passed" if passed else "failed", "evidence": f"Validated source count is {facts.get('validated_source_count', 0)}."}
    return {"clause": clause, "status": "unsupported", "evidence": "No deterministic evaluator is defined for this clause."}


def _evaluate_success_criteria(task_contract: dict[str, Any], facts: dict[str, Any]) -> list[dict[str, Any]]:
    criteria = task_contract.get("success_criteria") if isinstance(task_contract.get("success_criteria"), list) else []
    evaluations: list[dict[str, Any]] = []
    for raw in criteria:
        criterion = str(raw).strip()
        normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", criterion.lower()).split())
        if all(token in normalized for token in ("seed", "validated source", "synthesis", "review")):
            passed = bool(facts.get("seed_collected")) and bool(facts.get("chain_complete")) and facts.get("review_verdict") == "accept"
            checks = [{"clause": criterion, "status": "passed" if passed else "failed", "evidence": "Actual seed, validation, synthesis, report, and review chain was checked."}]
        else:
            clauses = [item.strip(" .,;") for item in re.split(r"\band\b", criterion, flags=re.IGNORECASE) if item.strip(" .,;")]
            checks = [_evaluate_clause(clause, facts) for clause in clauses]
        statuses = {item["status"] for item in checks}
        status = "unsupported" if "unsupported" in statuses else "failed" if "failed" in statuses else "passed" if checks else "unsupported"
        evaluations.append({"criterion": criterion, "status": status, "checks": checks})
    return evaluations


def _evaluate_required_content(task_contract: dict[str, Any], facts: dict[str, Any]) -> list[dict[str, str]]:
    deliverable = task_contract.get("deliverable") if isinstance(task_contract.get("deliverable"), dict) else {}
    requirements = deliverable.get("required_content") if isinstance(deliverable.get("required_content"), list) else []
    results: list[dict[str, str]] = []
    for item in requirements:
        if not isinstance(item, dict) or not bool(item.get("required", False)):
            continue
        requirement_id = str(item.get("requirement_id") or "").strip()
        if requirement_id == "result_claims":
            passed = bool(facts.get("all_conclusions_rendered"))
            evidence = (
                "Every source-grounded conclusion is rendered verbatim in the report body."
                if passed else "At least one source-grounded conclusion is missing from the report body."
            )
        elif requirement_id == "limitations":
            passed = bool(facts.get("limitations_rendered"))
            evidence = (
                "The report contains a substantive explicit limitations section and renders every provider-recorded limitation."
                if passed else "A substantive explicit limitations section is missing or omits a provider-recorded limitation."
            )
        elif requirement_id == "method_evidence":
            passed = bool(facts.get("method_rendered"))
            evidence = "The report contains an explicit method section." if passed else "The report lacks an explicit method section."
        else:
            passed = False
            evidence = "No deterministic evaluator is registered for this explicit requirement."
        results.append({
            "requirement_id": requirement_id or "invalid_requirement",
            "status": "passed" if passed else "failed",
            "evidence": evidence,
        })
    return results


def execute(node_request: dict, context: OperatorContext) -> dict:
    require_node(context, "final_acceptance")
    artifacts, artifact_refs, chain_issues = _load_chain_artifacts(context)
    facts, cross_check_issues = _recompute_chain(artifacts, artifact_refs)
    chain_issues.extend(cross_check_issues)
    review = artifacts.get("independent_review", {})
    findings = [item for item in review.get("findings", []) if isinstance(item, dict)] if isinstance(review.get("findings"), list) else []
    high_risk_findings = [item for item in findings if str(item.get("severity") or "").lower() in REJECTING_SEVERITIES]
    verdict = str(review.get("verdict_suggestion") or "").strip().lower()
    required_artifacts, unsupported_expectations = _required_artifacts(context)
    missing_artifacts = [kind for kind in required_artifacts if kind not in artifacts]
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    criteria_evaluation = _evaluate_success_criteria(task_contract, facts)
    criteria_passed = bool(criteria_evaluation) and all(item["status"] == "passed" for item in criteria_evaluation)
    required_content_evaluation = _evaluate_required_content(task_contract, facts)
    required_content_passed = all(item["status"] == "passed" for item in required_content_evaluation)
    accepted = (
        len(artifacts) == len(BASELINE_ARTIFACTS)
        and not chain_issues
        and not high_risk_findings
        and not missing_artifacts
        and not unsupported_expectations
        and verdict == "accept"
        and criteria_passed
        and required_content_passed
        and context.secret_verification_complete
    )
    reasons: list[str] = []
    reasons.extend(chain_issues)
    if high_risk_findings:
        reasons.append(f"{len(high_risk_findings)} high-risk review finding(s) block acceptance")
    if missing_artifacts:
        reasons.append("required artifact(s) missing: " + ", ".join(missing_artifacts))
    if unsupported_expectations:
        reasons.append("unsupported artifact expectation(s): " + ", ".join(unsupported_expectations))
    if verdict != "accept":
        reasons.append(f"review verdict suggestion is {verdict or 'missing'}")
    if not criteria_evaluation:
        reasons.append("task contract has no evaluable minimum success criteria")
    elif not criteria_passed:
        reasons.append("one or more task success criteria failed or are unsupported")
    if not required_content_passed:
        reasons.append("one or more explicit deliverable content requirements failed")
    if not context.secret_verification_complete:
        reasons.append("secret absence could not be verified because an authorized secret value was not supplied in memory")
    if not reasons:
        reasons.append("Actual scoped artifacts, hashes, lineage, review, and task success criteria passed the deterministic gate.")
    decision = "accepted" if accepted else "rejected"
    artifact_payload = {
        "schema": "research_synthesis.final_acceptance.v1",
        "node_id": "final_acceptance",
        "created_at": utc_now(),
        "decision": decision,
        "accepted": accepted,
        "gate_outcome": "pass" if accepted else "fail",
        "reasons": reasons,
        "review_verdict_suggestion": verdict,
        "review_finding_count": len(findings),
        "missing_required_artifacts": missing_artifacts,
        "unsupported_artifact_expectations": unsupported_expectations,
        "recomputed_chain_facts": facts,
        "success_criteria_evaluation": criteria_evaluation,
        "required_content_evaluation": required_content_evaluation,
        "does_not_modify_graph_or_run_state": True,
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "final_acceptance.json"),
        artifact_payload,
        artifact_id="final_acceptance",
        schema="research_synthesis.final_acceptance.v1",
    )
    errors = [] if accepted else [{
        "error_id": "final_acceptance.rejected",
        "error_type": "acceptance_gate_rejected",
        "message": "Final acceptance gate rejected the research result; inspect the decision artifact for bounded reasons.",
    }]
    return build_node_result(
        context,
        status="completed" if accepted else "failed",
        output_artifacts=[artifact],
        evidence=[evidence_ref("final_acceptance.decision", "acceptance_gate_outcome", f"Machine-enforceable gate outcome: {artifact_payload['gate_outcome']}.", artifact["artifact_id"])],
        hashes=[hash_record],
        errors=errors,
        limitations=["Final acceptance emits evidence only; Solar remains responsible for graph and run state."],
    )
