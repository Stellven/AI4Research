#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import finish, has_any_evidence_ids, limitations, outputs, require_non_empty_list, run_cli, validate_schema

CANDIDATE_SCHEMA = "idea_candidate.v1"
EVALUATION_SCHEMA = "idea_evaluation.v1"


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    schema = str(payload.get("schema") or "")
    expected = EVALUATION_SCHEMA if schema == EVALUATION_SCHEMA else CANDIDATE_SCHEMA
    reasons, warnings = validate_schema(payload, expected)
    out = outputs(payload)
    task_id = str(payload.get("task_id") or "")
    sprint_id = str(payload.get("sprint_id") or "")
    input_values = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    smoke_allowed = bool(input_values.get("smoke_mode")) or "fixture" in task_id or "smoke" in task_id or "smoke" in sprint_id
    if expected == CANDIDATE_SCHEMA:
        ideas = require_non_empty_list(out.get("ideas"), "outputs.ideas", reasons)
        for index, idea in enumerate(ideas):
            if not isinstance(idea, dict):
                reasons.append(f"ideas[{index}] must be an object")
                continue
            if not has_any_evidence_ids(idea.get("origin_evidence_ids")):
                reasons.append(f"ideas[{index}].origin_evidence_ids must contain at least one id")
            source_mode = str(idea.get("source_mode") or "")
            idea_text = " ".join(str(idea.get(field) or "") for field in ("title", "hypothesis", "approach"))
            if not smoke_allowed and (source_mode == "fixture" or "fixture" in idea_text.lower()):
                reasons.append(f"ideas[{index}] fixture-only ideas require explicit smoke evidence")
            if not smoke_allowed and source_mode == "missing" and idea.get("status") != "blocked":
                reasons.append(f"ideas[{index}] missing-source idea must be blocked")
    else:
        evaluations = require_non_empty_list(out.get("evaluations"), "outputs.evaluations", reasons)
        for index, evaluation in enumerate(evaluations):
            if not isinstance(evaluation, dict):
                reasons.append(f"evaluations[{index}] must be an object")
                continue
            if not has_any_evidence_ids(evaluation.get("evidence_ids")):
                reasons.append(f"evaluations[{index}].evidence_ids must contain at least one id")
            if evaluation.get("recommendation") in {"reject", "inconclusive"}:
                if not evaluation.get("risks") and not limitations(payload):
                    reasons.append(f"evaluations[{index}] reject/inconclusive recommendation requires risks or limitations")
            source_mode = str(evaluation.get("source_mode") or "")
            if not smoke_allowed and source_mode == "fixture":
                reasons.append(f"evaluations[{index}] fixture-only evaluation requires explicit smoke evidence")
            if not smoke_allowed and source_mode == "missing" and evaluation.get("recommendation") == "advance":
                reasons.append(f"evaluations[{index}] missing-source evaluation cannot advance")
            if (
                not smoke_allowed
                and source_mode in {"wiki", "wiki_state", "discovery", "mixed", "target", "external"}
                and evaluation.get("recommendation") in {"advance", "revise"}
            ):
                if not evaluation.get("closest_prior_work"):
                    reasons.append(f"evaluations[{index}] sourced evaluation requires closest_prior_work")
                if evaluation.get("review_score") in {None, "", "N/A"}:
                    reasons.append(f"evaluations[{index}] sourced evaluation requires review_score")
                if not evaluation.get("review_mode"):
                    reasons.append(f"evaluations[{index}] sourced evaluation requires review_mode")
                elif evaluation.get("review_mode") == "review_llm":
                    review_llm = evaluation.get("review_llm")
                    if evaluation.get("review_available") is not True:
                        reasons.append(f"evaluations[{index}] review_llm mode requires review_available=true")
                    if not isinstance(review_llm, dict) or str(review_llm.get("status") or "") != "completed":
                        reasons.append(f"evaluations[{index}] review_llm mode requires completed review_llm evidence")
                external_novelty = evaluation.get("external_novelty")
                if not isinstance(external_novelty, dict) or str(external_novelty.get("status") or "") not in {"completed", "unavailable", "invalid"}:
                    reasons.append(f"evaluations[{index}] sourced evaluation requires external_novelty status")
                elif external_novelty.get("status") == "completed":
                    provenance = external_novelty.get("provenance")
                    if not isinstance(provenance, dict) or str(provenance.get("status") or "") not in {"passed", "failed"}:
                        reasons.append(f"evaluations[{index}] completed external_novelty requires provenance status")
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, CANDIDATE_SCHEMA))
