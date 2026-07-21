from __future__ import annotations

from evaluators.scientific.idea_gate import evaluate


def base_payload(*, source_mode: str = "wiki", task_id: str = "task-idea") -> dict:
    return {
        "schema": "idea_candidate.v1",
        "task_id": task_id,
        "sprint_id": "sprint-idea",
        "node_id": "node-idea",
        "status": "completed",
        "inputs": {},
        "outputs": {
            "ideas": [
                {
                    "idea_id": "idea-001",
                    "title": "Source-grounded idea",
                    "hypothesis": "A sourced hypothesis can be tested.",
                    "approach": "Use cited source evidence to build a pilot.",
                    "origin_evidence_ids": ["wiki:papers/source"],
                    "source_mode": source_mode,
                    "status": "candidate",
                }
            ]
        },
        "artifacts": [],
        "provenance": {
            "operator_id": "test",
            "implementation_package": "test",
            "timestamp": "2026-06-24T00:00:00Z",
        },
        "limitations": [],
    }


def test_idea_gate_accepts_source_grounded_candidate() -> None:
    result = evaluate(base_payload())
    assert result.ok is True
    assert result.status == "passed"


def test_idea_gate_rejects_non_smoke_fixture_candidate() -> None:
    payload = base_payload(source_mode="fixture")
    payload["outputs"]["ideas"][0]["title"] = "Fixture research idea"
    result = evaluate(payload)
    assert result.ok is False
    assert result.status == "failed"
    assert any("fixture-only" in reason for reason in result.reasons)


def test_idea_gate_allows_explicit_fixture_smoke_candidate() -> None:
    payload = base_payload(source_mode="fixture", task_id="task-autosci-generate-ideas-fixture")
    payload["outputs"]["ideas"][0]["title"] = "Fixture research idea"
    result = evaluate(payload)
    assert result.ok is True
    assert result.status == "passed"


def test_idea_gate_requires_deep_validation_fields_for_sourced_evaluation() -> None:
    payload = {
        "schema": "idea_evaluation.v1",
        "task_id": "task-evaluate-idea",
        "sprint_id": "sprint-idea",
        "node_id": "node-evaluate",
        "status": "completed",
        "inputs": {},
        "outputs": {
            "evaluations": [
                {
                    "idea_id": "idea-001",
                    "novelty": 0.6,
                    "feasibility": 0.6,
                    "recommendation": "revise",
                    "risks": ["Needs validation."],
                    "evidence_ids": ["idea-001", "wiki:papers/source"],
                    "source_mode": "wiki",
                }
            ]
        },
        "artifacts": [],
        "provenance": {
            "operator_id": "test",
            "implementation_package": "test",
            "timestamp": "2026-06-24T00:00:00Z",
        },
        "limitations": [],
    }
    result = evaluate(payload)
    assert result.ok is False
    assert any("closest_prior_work" in reason for reason in result.reasons)
    payload["outputs"]["evaluations"][0]["closest_prior_work"] = [{"source_id": "wiki:papers/source"}]
    payload["outputs"]["evaluations"][0]["review_score"] = 0.55
    payload["outputs"]["evaluations"][0]["review_mode"] = "local_surrogate"
    payload["outputs"]["evaluations"][0]["external_novelty"] = {"status": "unavailable"}
    result = evaluate(payload)
    assert result.ok is True
    assert result.status == "passed"


def test_idea_gate_requires_deep_validation_fields_for_wiki_state_evaluation() -> None:
    payload = {
        "schema": "idea_evaluation.v1",
        "task_id": "task-evaluate-wiki-state-idea",
        "sprint_id": "sprint-idea",
        "node_id": "node-evaluate",
        "status": "completed",
        "inputs": {},
        "outputs": {
            "evaluations": [
                {
                    "idea_id": "idea-skillgen",
                    "novelty": 0.62,
                    "feasibility": 0.55,
                    "recommendation": "revise",
                    "risks": ["Needs external novelty and Review LLM validation."],
                    "evidence_ids": ["idea-skillgen", "wiki:ideas/skillgen"],
                    "source_mode": "wiki_state",
                }
            ]
        },
        "artifacts": [{"type": "wiki_state_resolver_json", "path": "wiki_state_resolver.json"}],
        "provenance": {
            "operator_id": "test",
            "implementation_package": "test",
            "timestamp": "2026-06-24T00:00:00Z",
        },
        "limitations": [],
    }
    result = evaluate(payload)
    assert result.ok is False
    assert any("closest_prior_work" in reason for reason in result.reasons)
    assert any("review_score" in reason for reason in result.reasons)
    assert any("external_novelty status" in reason for reason in result.reasons)

    evaluation = payload["outputs"]["evaluations"][0]
    evaluation["closest_prior_work"] = [{"source_id": "wiki:papers/skillgen"}]
    evaluation["review_score"] = 0.55
    evaluation["review_mode"] = "local_surrogate"
    evaluation["external_novelty"] = {"status": "unavailable"}
    result = evaluate(payload)
    assert result.ok is True
    assert result.status == "passed"


def test_idea_gate_requires_provenance_status_for_completed_external_novelty() -> None:
    payload = {
        "schema": "idea_evaluation.v1",
        "task_id": "task-evaluate-idea",
        "sprint_id": "sprint-idea",
        "node_id": "node-evaluate",
        "status": "completed",
        "inputs": {},
        "outputs": {
            "evaluations": [
                {
                    "idea_id": "idea-001",
                    "novelty": 0.6,
                    "feasibility": 0.6,
                    "recommendation": "revise",
                    "risks": ["Needs validation."],
                    "evidence_ids": ["idea-001", "external:semantic_scholar:s2-001"],
                    "source_mode": "external",
                    "closest_prior_work": [{"source_id": "external:semantic_scholar:s2-001"}],
                    "review_score": 0.55,
                    "review_mode": "local_surrogate",
                    "external_novelty": {"status": "completed"},
                }
            ]
        },
        "artifacts": [],
        "provenance": {
            "operator_id": "test",
            "implementation_package": "test",
            "timestamp": "2026-06-24T00:00:00Z",
        },
        "limitations": [],
    }
    result = evaluate(payload)
    assert result.ok is False
    assert any("provenance status" in reason for reason in result.reasons)

    payload["outputs"]["evaluations"][0]["external_novelty"]["provenance"] = {"status": "passed"}
    result = evaluate(payload)
    assert result.ok is True
    assert result.status == "passed"


def test_idea_gate_requires_completed_review_llm_when_review_mode_claims_llm() -> None:
    payload = {
        "schema": "idea_evaluation.v1",
        "task_id": "task-evaluate-idea",
        "sprint_id": "sprint-idea",
        "node_id": "node-evaluate",
        "status": "completed",
        "inputs": {},
        "outputs": {
            "evaluations": [
                {
                    "idea_id": "idea-001",
                    "novelty": 0.6,
                    "feasibility": 0.6,
                    "recommendation": "revise",
                    "risks": ["Needs validation."],
                    "evidence_ids": ["idea-001", "wiki:papers/source"],
                    "source_mode": "wiki",
                    "closest_prior_work": [{"source_id": "wiki:papers/source"}],
                    "review_score": 0.55,
                    "review_mode": "review_llm",
                    "review_available": False,
                    "external_novelty": {"status": "unavailable"},
                }
            ]
        },
        "artifacts": [],
        "provenance": {
            "operator_id": "test",
            "implementation_package": "test",
            "timestamp": "2026-06-24T00:00:00Z",
        },
        "limitations": [],
    }
    result = evaluate(payload)
    assert result.ok is False
    assert any("review_llm mode requires review_available=true" in reason for reason in result.reasons)
    assert any("completed review_llm evidence" in reason for reason in result.reasons)

    payload["outputs"]["evaluations"][0]["review_available"] = True
    payload["outputs"]["evaluations"][0]["review_llm"] = {"status": "completed"}
    result = evaluate(payload)
    assert result.ok is True
    assert result.status == "passed"
