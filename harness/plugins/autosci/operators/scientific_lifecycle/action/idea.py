"""Idea generation and evaluation physical operators."""

from __future__ import annotations

from typing import Any

from ...research_synthesis.base import provider_usage_from
from .common import (
    OperatorContext,
    ResearchOperatorError,
    completed_result,
    load_documents,
    require_list,
    require_text,
    service_failure,
)


GENERATOR_ID = "autosci-idea-generation-physical"
EVALUATOR_ID = "autosci-idea-evaluation-physical"


def _idea_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_ideas = response.get("ideas")
    require_list(raw_ideas, "ideas")
    ideas: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_ideas):
        if not isinstance(raw, dict):
            raise ResearchOperatorError("Every idea must be an object", error_type="provider_contract_failure")
        evidence_ids = [str(item) for item in require_list(raw.get("origin_evidence_ids"), "origin_evidence_ids") if str(item).strip()]
        risks = [str(item) for item in require_list(raw.get("risks"), "risks") if str(item).strip()]
        falsifiability = require_text(raw.get("falsifiability"), "falsifiability")
        validation_method = require_text(raw.get("validation_method"), "validation_method")
        minimum_experiment = require_text(raw.get("minimum_experiment"), "minimum_experiment")
        source_proof = raw.get("source_proof") if isinstance(raw.get("source_proof"), dict) else {}
        source_proof = {
            "status": str(source_proof.get("status") or ("source_backed" if evidence_ids else "missing_source_proof")),
            "evidence_ids": [str(item) for item in source_proof.get("evidence_ids") or evidence_ids if str(item).strip()],
            "proof": str(source_proof.get("proof") or "Origin evidence ids were supplied by the idea generator."),
            "limitations": [str(item) for item in source_proof.get("limitations") or [] if str(item).strip()],
        }
        promotion_decision = "ready_for_evaluation" if (
            source_proof["evidence_ids"] and risks and falsifiability and validation_method and minimum_experiment
        ) else "revise_before_evaluation"
        idea = {
            "idea_id": require_text(raw.get("idea_id") or f"idea-{index + 1:03d}", "idea_id"),
            "title": require_text(raw.get("title"), "title"),
            "hypothesis": require_text(raw.get("hypothesis"), "hypothesis"),
            "approach": require_text(raw.get("approach"), "approach"),
            "origin_evidence_ids": evidence_ids,
            "source_proof": source_proof,
            "risks": risks,
            "falsifiability": falsifiability,
            "validation_method": validation_method,
            "minimum_experiment": minimum_experiment,
            "promotion_decision": str(raw.get("promotion_decision") or promotion_decision),
            "novelty_hypothesis": str(raw.get("novelty_hypothesis") or ""),
        }
        ideas.append(idea)
    return ideas


def generate_ideas(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    evidence = load_documents(
        context,
        schemas=("code_evidence_map.v1", "research_claims.v1", "research_method.v1"),
        payload_keys=("research_context", "evidence"),
    )
    generator = context.services.get("idea_generator")
    if not callable(generator):
        raise ResearchOperatorError("idea_generator service is unavailable", error_type="provider_unavailable")
    try:
        response = generator(evidence=evidence, constraints=context.payload.get("constraints") or {})
    except Exception as exc:  # provider boundary
        raise service_failure("idea_generator", exc) from exc
    if not isinstance(response, dict):
        raise ResearchOperatorError("idea_generator must return an object", error_type="provider_contract_failure")
    ideas = _idea_rows(response)
    return completed_result(
        context,
        operator_id=GENERATOR_ID,
        schema="idea_candidate.v1",
        outputs={"ideas": ideas},
        filename="idea_candidate.v1.json",
        artifact_id="idea_candidate",
        limitations=[str(item) for item in response.get("limitations") or [] if str(item).strip()],
        model_provider_usage=provider_usage_from(response, usage_kind="llm"),
    )


def _extract_ideas(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    for document in documents:
        if document.get("idea_id"):
            ideas.append(document)
            continue
        outputs = document.get("outputs") if isinstance(document.get("outputs"), dict) else document
        values = outputs.get("ideas") if isinstance(outputs, dict) else None
        if isinstance(values, list):
            ideas.extend(item for item in values if isinstance(item, dict))
    return ideas


def evaluate_ideas(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    ideas = _extract_ideas(load_documents(context, schemas=("idea_candidate.v1",), payload_keys=("ideas", "idea_candidate")))
    require_list(ideas, "ideas")
    evaluations: list[dict[str, Any]] = []
    for idea in ideas:
        risks = [str(item) for item in idea.get("risks") or [] if str(item).strip()]
        complete = all(str(idea.get(field) or "").strip() for field in ("falsifiability", "validation_method", "minimum_experiment"))
        origin = [str(item) for item in idea.get("origin_evidence_ids") or [] if str(item).strip()]
        feasibility = max(0.0, min(1.0, 0.8 - 0.1 * max(0, len(risks) - 1)))
        recommendation = "advance" if complete and origin else "revise"
        promotion_decision = "promote_to_experiment_design" if recommendation == "advance" else "hold_for_revision"
        evaluations.append({
            "idea_id": require_text(idea.get("idea_id"), "idea_id"),
            "novelty": float(idea.get("novelty_score", 0.5)),
            "feasibility": feasibility,
            "recommendation": recommendation,
            "promotion_decision": promotion_decision,
            "risks": risks or ["Risk analysis was not supplied."],
            "evidence_ids": origin,
            "source_proof_status": str((idea.get("source_proof") or {}).get("status") or "unknown"),
            "falsifiability_ready": complete,
            "minimum_experiment_ready": bool(str(idea.get("minimum_experiment") or "").strip()),
        })
    return completed_result(
        context,
        operator_id=EVALUATOR_ID,
        schema="idea_evaluation.v1",
        outputs={"evaluations": evaluations},
        filename="idea_evaluation.v1.json",
        artifact_id="idea_evaluation",
    )
