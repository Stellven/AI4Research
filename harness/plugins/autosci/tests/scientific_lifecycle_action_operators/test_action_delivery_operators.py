from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


HARNESS = Path(__file__).resolve().parents[4]
REPO = HARNESS.parent
sys.path.insert(0, str(REPO))

from harness.plugins.autosci.operators.scientific_lifecycle.action.registry import (  # noqa: E402
    execute_operator,
    registration_entries,
)
from harness.plugins.autosci.operators.scientific_lifecycle.action.common import stable_json_sha256  # noqa: E402


NODE_RESULT_SCHEMA = json.loads(
    (HARNESS / "schemas" / "evidence" / "research_node_result.v1.schema.json").read_text(encoding="utf-8")
)
EXPECTED_NODES = {
    "idea_generate",
    "idea_evaluate",
    "experiment_design",
    "experiment_approval_gate",
    "experiment_run",
    "experiment_monitor",
    "claim_verify",
    "report_plan",
    "report_draft",
    "artifact_review",
    "publication_produce",
    "final_evaluation",
    "workflow_evolve",
}


def _request(
    node_id: str,
    *,
    payload: dict | None = None,
    refs: list[dict] | None = None,
    write_scope: list[str] | None = None,
    approval_ref: str | None = None,
    capabilities: list[str] | None = None,
) -> dict:
    task_contract = {
        "user_intent": "Report bounded treatment scientific results.",
        "deliverable": {
            "required_content": [{
                "requirement_id": "result_claims",
                "description": "Preserve source-grounded result claims.",
                "required": True,
            }],
            "review_requirement": {
                "expected_mode": "local_surrogate",
                "independent_peer_review_required": False,
                "limitation_disclosure_required": True,
            },
        },
        "success_criteria": [
            "Every reported claim is linked to evidence sources",
            "The final report contains non-empty body content",
            "The local structural review is disclosed with its independent-review limitation",
        ],
        "run_provenance": {
            "repo_head": "unavailable",
            "worktree_status": "unavailable",
            "captured_at": "2026-08-05T12:00:00Z",
            "workflow_identity": {
                "workflow_id": "scientific_research_lifecycle_full_v1",
                "workflow_version": 1,
                "workflow_kind": "scientific_lifecycle",
            },
        },
    }
    authorization = {
        "scope_id": "phase3-action-test",
        "approved_capabilities": list(capabilities or ["write_artifact"]),
        "allow_network": False,
        "allow_live_provider": False,
        "secret_refs": [],
    }
    if approval_ref:
        authorization["approval_ref"] = approval_ref
    return {
        "schema": "research_node_request.v1",
        "task_id": "task-action-lifecycle",
        "run_id": "run-action-lifecycle",
        "workflow_id": "scientific_research_lifecycle_full_v1",
        "node_id": node_id,
        "logical_operator": {"operator_id": f"logical-{node_id}", "operator_kind": "logical"},
        "physical_operator": {"operator_id": f"physical-{node_id}", "operator_kind": "physical"},
        "typed_inputs": {
            "input_schema": f"{node_id}.input.v1",
            "payload": {"evidence_timestamp": "2026-08-05T12:00:00Z", "task_contract": task_contract, **(payload or {})},
        },
        "input_artifact_refs": refs or [],
        "authorization": authorization,
        "read_scope": ["out", "inputs"],
        "write_scope": write_scope or [f"out/{node_id}"],
        "timeout_retry_policy": {"timeout_seconds": 30, "max_attempts": 1, "retry_on": []},
    }


def _artifact(tmp_path: Path, result: dict, artifact_id: str | None = None) -> dict:
    ref = next(
        item for item in result["output_artifacts"]
        if artifact_id is None or item["artifact_id"] == artifact_id
    )
    assert hashlib.sha256((tmp_path / ref["path"]).read_bytes()).hexdigest() == ref["sha256"]
    return json.loads((tmp_path / ref["path"]).read_text(encoding="utf-8"))


def _validate_result(result: dict) -> None:
    Draft202012Validator(NODE_RESULT_SCHEMA).validate(result)


def _validate_evidence(tmp_path: Path, result: dict) -> None:
    _validate_result(result)
    for ref in result["output_artifacts"]:
        if not ref.get("schema", "").endswith(".v1") or ref["schema"] == "text/markdown":
            continue
        schema_path = HARNESS / "schemas" / "evidence" / f"{ref['schema']}.schema.json"
        if schema_path.exists():
            Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(
                json.loads((tmp_path / ref["path"]).read_text(encoding="utf-8"))
            )


def _external_ref(
    tmp_path: Path,
    name: str,
    schema: str,
    outputs: dict,
    *,
    limitations: list[str] | None = None,
) -> dict:
    path = tmp_path / "inputs" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": schema,
        "task_id": "task-action-lifecycle",
        "sprint_id": "run-action-lifecycle",
        "node_id": name,
        "status": "completed",
        "inputs": {},
        "outputs": outputs,
        "artifacts": [],
        "provenance": {
            "operator_id": "test-upstream",
            "implementation_package": "test",
            "timestamp": "2026-08-05T12:00:00Z",
        },
        "limitations": list(limitations or []),
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return {
        "artifact_id": name,
        "path": str(path.relative_to(tmp_path)).replace("\\", "/"),
        "schema": schema,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _strict_final_contract(*, independent_review: bool = False, extra_criterion: str = "") -> dict:
    criteria = [
        "At least 1 parsed, non-empty local source",
        "Every reported claim is linked to evidence sources",
        "The final report contains non-empty body content",
        "The local structural review is disclosed with its independent-review limitation",
    ]
    if extra_criterion:
        criteria.append(extra_criterion)
    return {
        "user_intent": "Synthesize bounded treatment results, methods, and limitations.",
        "deliverable": {
            "required_content": [
                {"requirement_id": "method_evidence", "description": "Preserve methods.", "required": True},
                {"requirement_id": "result_claims", "description": "Preserve results.", "required": True},
                {"requirement_id": "limitations", "description": "Preserve limitations.", "required": True},
            ],
            "review_requirement": {
                "expected_mode": "independent_model_review" if independent_review else "local_surrogate",
                "independent_peer_review_required": independent_review,
                "limitation_disclosure_required": not independent_review,
            },
        },
        "success_criteria": criteria,
        "run_provenance": {
            "repo_head": "a" * 40,
            "worktree_status": "clean",
            "captured_at": "2026-08-05T12:00:00Z",
            "workflow_identity": {
                "workflow_id": "scientific_research_lifecycle_full_v1",
                "workflow_version": 1,
                "workflow_kind": "scientific_lifecycle",
            },
        },
    }


def _strict_final_refs(
    tmp_path: Path,
    *,
    task_contract: dict,
    markdown: str,
    methods: list[dict] | None = None,
    method_insufficient: bool = False,
) -> list[dict]:
    claim_text = "The bounded treatment improves the primary outcome over baseline."
    method_values = list(methods or [])
    method_limitations = ["The source does not contain enough evidence to identify a method without invention."] if method_insufficient else []
    report = {
        "report_id": "strict-report",
        "title": "Bounded treatment",
        "sections": [
            {"section_id": "summary", "title": "Summary", "body": "Bounded treatment synthesis.", "evidence_ids": ["source:1"]},
            {"section_id": "findings", "title": "Findings", "body": claim_text, "evidence_ids": ["source:1"]},
            {"section_id": "limitations", "title": "Limitations", "body": "Evidence limitations are explicit.", "evidence_ids": ["source:1"]},
        ],
        "evidence_ids": ["source:1"],
        "unsupported_claims": [],
        "methods": method_values,
        "method_evidence_status": "available" if method_values else "insufficient_evidence",
        "markdown": markdown,
    }
    report_ref = _external_ref(tmp_path, "strict_report", "scientific_report.v1", {"report": report})
    method_ref = _external_ref(
        tmp_path,
        "strict_method",
        "research_method.v1",
        {"methods": method_values},
        limitations=method_limitations,
    )
    verdict_ref = _external_ref(tmp_path, "strict_verdict", "claim_verdict.v1", {
        "verdicts": [{
            "claim_id": "claim-001",
            "claim_text": claim_text,
            "support_classification": "supported",
            "verdict": "supported",
            "basis": "Source evidence is present.",
            "evidence_ids": ["source:1"],
        }]
    })
    paper_ref = _external_ref(tmp_path, "strict_paper", "research_paper.v1", {
        "paper": {"paper_id": "paper-001", "sections": [{"title": "Results", "text": claim_text, "source_anchor": "source:1"}]}
    })
    review_ref = _external_ref(
        tmp_path,
        "strict_review",
        "artifact_review.v1",
        {"review": {
            "artifact_id": "strict-report",
            "target": "scientific_report",
            "review_mode": "local_surrogate",
            "review_available": True,
            "difficulty": "standard",
            "focus": "completeness",
            "score": 1.0,
            "recommendation": "pass_with_review_required",
            "evidence_ids": ["source:1"],
            "review_scope": "local_structural_only",
            "independent_peer_review": False,
            "task_contract_sha256": stable_json_sha256(task_contract),
        }, "findings": []},
        limitations=["Local structural review does not replace independent scientific peer review."],
    )
    bundle_ref = _external_ref(tmp_path, "strict_bundle", "publication_bundle.v1", {
        "bundle": {
            "bundle_id": "strict-bundle",
            "publication_type": "paper",
            "files": [{"type": "embedded_markdown", "path": "inputs/strict_bundle.json"}],
            "source_report_id": "strict-report",
            "evidence_ids": ["source:1"],
            "compiled_markdown": markdown,
            "review_score": 1.0,
        }
    })
    return [bundle_ref, review_ref, report_ref, method_ref, verdict_ref, paper_ref]


def _idea_generator(**kwargs) -> dict:
    assert kwargs["evidence"]
    return {
        "provider": "fixture-provider",
        "model": "fixture-model",
        "ideas": [{
            "idea_id": "idea-001",
            "title": "Bounded treatment improves the measured outcome",
            "hypothesis": "The treatment improves the primary outcome over baseline.",
            "approach": "Run a bounded controlled comparison.",
            "origin_evidence_ids": ["claim-source-001"],
            "risks": ["Small sample size"],
            "falsifiability": "Reject when the primary outcome does not improve.",
            "validation_method": "Compare the registered primary metric to baseline.",
            "minimum_experiment": "Run one isolated treatment and one baseline replicate.",
            "novelty_hypothesis": "The bounded configuration has not been tested.",
        }]
    }


def _execute_twice(tmp_path: Path, request: dict, *, services: dict) -> dict:
    first = execute_operator(request, services=services)
    first_bytes = {
        item["artifact_id"]: (tmp_path / item["path"]).read_bytes()
        for item in first["output_artifacts"]
    }
    second = execute_operator(request, services=services)
    second_bytes = {
        item["artifact_id"]: (tmp_path / item["path"]).read_bytes()
        for item in second["output_artifacts"]
    }
    assert first_bytes == second_bytes
    assert first["hashes"] == second["hashes"]
    return second


def _experiment_executor(**kwargs) -> dict:
    assert kwargs["sandbox"]["mode"] == "isolated"
    assert kwargs["sandbox"]["network"] is False
    assert kwargs["timeout_seconds"] <= 30
    return {
        "outcome": "supports",
        "metrics": [{"name": "primary_outcome", "value": 0.91}],
        "evidence_ids": ["experiment:raw:001"],
        "criteria_results": {"primary outcome > baseline": True},
    }


def test_registration_seam_lists_each_operator_once() -> None:
    entries = registration_entries()
    assert {item["node_id"] for item in entries} == EXPECTED_NODES
    assert len(entries) == len(EXPECTED_NODES)
    assert len({item["operator_id"] for item in entries}) == len(EXPECTED_NODES)
    assert all(item["operator_version"] == "1.1.0" for item in entries)


def test_full_action_delivery_chain_produces_traceable_usable_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    results: list[dict] = []

    idea = _execute_twice(
        tmp_path,
        _request("idea_generate", payload={"research_context": {"question": "Does a bounded treatment help?"}}),
        services={"idea_generator": _idea_generator},
    )
    results.append(idea)
    idea_payload = _artifact(tmp_path, idea)
    generated = idea_payload["outputs"]["ideas"][0]
    assert {"risks", "falsifiability", "validation_method", "minimum_experiment"} <= set(generated)

    evaluated = _execute_twice(tmp_path, _request("idea_evaluate", refs=idea["output_artifacts"]), services={})
    results.append(evaluated)
    assert _artifact(tmp_path, evaluated)["outputs"]["evaluations"][0]["recommendation"] == "advance"

    designed = _execute_twice(
        tmp_path,
        _request(
            "experiment_design",
            refs=idea["output_artifacts"],
            payload={"sandbox": {"mode": "isolated", "network": False, "write_scope": ["out/experiment_run"]}},
        ),
        services={},
    )
    results.append(designed)
    plan = _artifact(tmp_path, designed)["outputs"]["experiment_plan"]
    assert plan["approval_required"] is True
    assert plan["sandbox"] == {"mode": "isolated", "network": False, "write_scope": ["out/experiment_run"]}

    approved = _execute_twice(
        tmp_path,
        _request(
            "experiment_approval_gate",
            refs=designed["output_artifacts"],
            write_scope=["out/experiment_approval_gate", "out/experiment_run"],
            approval_ref="human-approval-001",
            capabilities=["write_artifact", "execute_experiment"],
        ),
        services={},
    )
    results.append(approved)
    assert _artifact(tmp_path, approved)["outputs"]["approval"]["decision"] == "approved"

    ran = _execute_twice(
        tmp_path,
        _request(
            "experiment_run",
            refs=[*designed["output_artifacts"], *approved["output_artifacts"]],
            write_scope=["out/experiment_run"],
            approval_ref="human-approval-001",
            capabilities=["write_artifact", "execute_experiment"],
        ),
        services={"experiment_executor": _experiment_executor},
    )
    results.append(ran)
    experiment = _artifact(tmp_path, ran)["outputs"]["result"]
    # The physical executor cannot bypass sandbox or approval metadata.
    assert experiment["sandbox_enforced"] is True
    assert experiment["approval_ref"] == "human-approval-001"

    monitored = _execute_twice(tmp_path, _request("experiment_monitor", refs=ran["output_artifacts"]), services={})
    results.append(monitored)
    assert _artifact(tmp_path, monitored)["outputs"]["status_report"]["state"] == "completed"

    claims_ref = _external_ref(tmp_path, "claim_extract", "research_claims.v1", {
        "claims": [{
            "claim_id": "claim-001",
            "text": "The treatment improves the primary outcome.",
            "acceptance_criteria": ["primary outcome > baseline"],
            "evidence_ids": ["claim-source-001"],
        }]
    })
    verified = _execute_twice(tmp_path, _request("claim_verify", refs=[claims_ref, *ran["output_artifacts"]]), services={})
    results.append(verified)
    verdict = _artifact(tmp_path, verified)["outputs"]["verdicts"][0]
    assert verdict["verdict"] == "supported"
    assert verdict["support_classification"] == "supported"

    planned = _execute_twice(
        tmp_path,
        _request("report_plan", refs=verified["output_artifacts"], payload={"topic": "Bounded treatment outcome"}),
        services={},
    )
    results.append(planned)
    method_ref = _external_ref(tmp_path, "method_extract", "research_method.v1", {
        "methods": [{
            "method_id": "method-001",
            "name": "Bounded controlled comparison",
            "summary": "Compare the treatment with a bounded baseline.",
            "procedure": ["Run one isolated treatment and one baseline replicate."],
            "source_papers": ["paper-001"],
            "evidence_ids": ["claim-source-001"],
            "extraction_basis": "explicit_method_heading",
            "confidence": 1.0,
        }]
    })
    drafted = _execute_twice(
        tmp_path,
        _request("report_draft", refs=[*planned["output_artifacts"], *verified["output_artifacts"], method_ref]),
        services={},
    )
    results.append(drafted)
    report = _artifact(tmp_path, drafted)["outputs"]["report"]
    assert report["markdown"].strip()
    assert len(report["sections"]) == 4
    assert "Bounded treatment outcome" in report["markdown"]
    assert "## Methods" in report["markdown"]
    assert "Bounded controlled comparison" in report["markdown"]

    reviewed = _execute_twice(tmp_path, _request("artifact_review", refs=drafted["output_artifacts"]), services={})
    results.append(reviewed)
    assert _artifact(tmp_path, reviewed)["outputs"]["review"]["recommendation"] == "pass_with_review_required"

    published = _execute_twice(
        tmp_path,
        _request("publication_produce", refs=[*drafted["output_artifacts"], *reviewed["output_artifacts"]]),
        services={},
    )
    results.append(published)
    publication = _artifact(tmp_path, published, "publication_bundle")["outputs"]["bundle"]
    assert publication["compiled_markdown"].strip()
    assert (tmp_path / "out/publication_produce/publication.md").is_file()

    evaluated_final = _execute_twice(
        tmp_path,
        _request("final_evaluation", refs=[
            *published["output_artifacts"],
            *reviewed["output_artifacts"],
            *drafted["output_artifacts"],
            *verified["output_artifacts"],
            method_ref,
        ]),
        services={},
    )
    results.append(evaluated_final)
    final_decision = _artifact(tmp_path, evaluated_final)["outputs"]["evaluation"]
    assert final_decision["decision"] == "accepted_with_limitations"
    assert all(final_decision["checks"].values())
    assert final_decision["does_not_modify_graph_or_run_state"] is True

    evolved = _execute_twice(
        tmp_path,
        _request(
            "workflow_evolve",
            refs=reviewed["output_artifacts"],
            payload={"description": "Require explicit acceptance criteria before supporting a claim."},
        ),
        services={},
    )
    results.append(evolved)
    evolution = _artifact(tmp_path, evolved)["outputs"]["evolution"]
    assert evolution["approval_state"] == "proposed"
    assert evolution["review"]["protected_core_edits_applied"] is False
    assert evolution["proposed_changes"][0]["application_state"] == "proposed_only"

    assert len(results) == 13
    assert all(result["status"] == "completed" for result in results)
    for result in results:
        _validate_evidence(tmp_path, result)
        assert len(result["hashes"]) >= 1
        assert result["evidence"]
        assert all("\\" not in item["path"] for item in result["output_artifacts"])


def _explicit_test_method() -> dict:
    return {
        "method_id": "method-001",
        "name": "Bounded controlled comparison",
        "summary": "Compare the treatment with a bounded baseline.",
        "procedure": ["Run one isolated treatment and one baseline replicate."],
        "source_papers": ["paper-001"],
        "evidence_ids": ["source:1"],
        "extraction_basis": "explicit_method_heading",
        "confidence": 1.0,
    }


def _complete_test_markdown() -> str:
    return """# Bounded treatment

## Summary
This synthesis evaluates bounded treatment results using source-grounded evidence.

## Findings
The bounded treatment improves the primary outcome over baseline.

## Methods
### Bounded controlled comparison
- Summary: Compare the treatment with a bounded baseline.
- Procedure:
  1. Run one isolated treatment and one baseline replicate.
- Evidence IDs: source:1
- Extraction basis: explicit_method_heading

## Limitations
- Local structural review does not replace independent scientific peer review.
"""


@pytest.mark.parametrize(
    ("case", "markdown", "independent_review", "extra_criterion"),
    [
        (
            "method evidence omitted",
            """# Bounded treatment\n\n## Findings\nThe bounded treatment improves the primary outcome over baseline.\n\n## Limitations\n- Review is local.\n""",
            False,
            "",
        ),
        (
            "requested result omitted",
            """# Bounded treatment\n\n## Summary\nThis report discusses the bounded treatment context but omits its result.\n\n## Methods\n### Bounded controlled comparison\n- Summary: Compare the treatment with a bounded baseline.\n- Procedure: Run one isolated treatment and one baseline replicate.\n- Evidence IDs: source:1\n- Extraction basis: explicit_method_heading\n\n## Limitations\n- Review is local.\n""",
            False,
            "",
        ),
        ("local surrogate claimed for independent review", _complete_test_markdown(), True, ""),
        ("success criterion unchecked", _complete_test_markdown(), False, "The report has delightful prose"),
        (
            "nonempty unrelated report",
            """# Gardening notes\n\n## Findings\nTomatoes benefit from regular watering and adequate sunlight throughout the growing season.\n\n## Methods\nNo relevant scientific method is discussed.\n\n## Limitations\nThese are general gardening notes.\n""",
            False,
            "",
        ),
    ],
)
def test_final_evaluation_rejects_contract_or_fidelity_failures(
    tmp_path: Path,
    monkeypatch,
    case: str,
    markdown: str,
    independent_review: bool,
    extra_criterion: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    task_contract = _strict_final_contract(
        independent_review=independent_review,
        extra_criterion=extra_criterion,
    )
    refs = _strict_final_refs(
        tmp_path,
        task_contract=task_contract,
        markdown=markdown,
        methods=[_explicit_test_method()],
    )

    result = execute_operator(
        _request("final_evaluation", payload={"task_contract": task_contract}, refs=refs),
        services={},
    )

    assert result["status"] == "failed", case
    assert result["errors"][0]["error_type"] == "quality_gate_failed"
    assert result["output_artifacts"] == []


def test_final_evaluation_accepts_method_insufficiency_as_explicit_limitation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    task_contract = _strict_final_contract()
    limitation = "The source does not contain enough evidence to identify a method without invention."
    markdown = f"""# Bounded treatment

## Summary
This synthesis evaluates bounded treatment results using source-grounded evidence.

## Findings
The bounded treatment improves the primary outcome over baseline.

## Methods
Method evidence status: insufficient_evidence.
- Method limitation: {limitation}

## Limitations
- Method limitation: {limitation}
"""
    refs = _strict_final_refs(
        tmp_path,
        task_contract=task_contract,
        markdown=markdown,
        methods=[],
        method_insufficient=True,
    )

    result = execute_operator(
        _request("final_evaluation", payload={"task_contract": task_contract}, refs=refs),
        services={},
    )

    assert result["status"] == "completed"
    evaluation = _artifact(tmp_path, result)["outputs"]["evaluation"]
    assert evaluation["accepted"] is True
    assert evaluation["decision"] == "accepted_with_limitations"
    assert evaluation["method_evaluation"] == "insufficient_evidence_disclosed"
    assert all(item["status"] == "passed" for item in evaluation["criterion_results"])
    _validate_evidence(tmp_path, result)


@pytest.mark.parametrize("node_id", sorted(EXPECTED_NODES))
def test_each_operator_rejects_missing_required_input(tmp_path: Path, monkeypatch, node_id: str) -> None:
    monkeypatch.chdir(tmp_path)
    result = execute_operator(_request(node_id), services={})
    assert result["status"] == "failed"
    assert result["errors"][0]["error_type"] in {"missing_input", "provider_unavailable"}
    assert result["output_artifacts"] == []


def test_experiment_run_fails_closed_without_hash_bound_approval(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    plan_ref = _external_ref(tmp_path, "experiment_design", "experiment_plan.v1", {
        "experiment_plan": {
            "experiment_id": "exp-denied",
            "objective": "Bounded test",
            "hypothesis": "Test",
            "variables": ["x"],
            "metrics": ["y"],
            "procedure": ["measure"],
            "approval_required": True,
            "expected_artifacts": ["result"],
            "sandbox": {"mode": "isolated", "network": False, "write_scope": ["out/experiment_run"]},
            "resource_limits": {"timeout_seconds": 10, "max_output_bytes": 1000},
        }
    })
    called = False

    def forbidden_executor(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not execute")

    result = execute_operator(
        _request(
            "experiment_run",
            refs=[plan_ref],
            payload={"approval": {"decision": "approved", "approval_ref": "human-approval"}},
            write_scope=["out/experiment_run"],
            approval_ref="human-approval",
            capabilities=["write_artifact", "execute_experiment"],
        ),
        services={"experiment_executor": forbidden_executor},
    )
    assert result["status"] == "failed"
    assert result["errors"][0]["error_type"] == "approval_required"
    assert called is False
    assert result["output_artifacts"] == []


def test_approval_gate_rejects_unsafe_or_out_of_scope_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    plan_ref = _external_ref(tmp_path, "unsafe_plan", "experiment_plan.v1", {
        "experiment_plan": {
            "experiment_id": "exp-unsafe",
            "objective": "Unsafe test",
            "hypothesis": "Unsafe",
            "variables": ["x"],
            "metrics": ["y"],
            "procedure": ["connect externally"],
            "approval_required": True,
            "expected_artifacts": ["result"],
            "sandbox": {"mode": "none", "network": True, "write_scope": ["outside"]},
            "resource_limits": {"timeout_seconds": 10, "max_output_bytes": 1000},
        }
    })
    result = execute_operator(
        _request(
            "experiment_approval_gate",
            refs=[plan_ref],
            write_scope=["out/approval"],
            approval_ref="unsafe-approval",
            capabilities=["write_artifact", "execute_experiment"],
        ),
        services={},
    )
    assert result["status"] == "blocked"
    assert result["errors"][0]["error_type"] == "safety_violation"
    assert _artifact(tmp_path, result)["outputs"]["approval"]["decision"] == "rejected"


@pytest.mark.parametrize(
    ("outcome", "criteria", "expected"),
    [
        ("supports", {}, "insufficient_evidence"),
        ("refutes", {"criterion": False}, "unsupported"),
        ("inconclusive", {"criterion": True}, "insufficient_evidence"),
    ],
)
def test_claim_verification_never_promotes_incomplete_evidence(
    tmp_path: Path, monkeypatch, outcome: str, criteria: dict, expected: str
) -> None:
    monkeypatch.chdir(tmp_path)
    claim = _external_ref(tmp_path, "claims", "research_claims.v1", {
        "claims": [{"claim_id": "claim", "acceptance_criteria": ["criterion"], "evidence_ids": ["source"]}]
    })
    result = _external_ref(tmp_path, "result", "experiment_result.v1", {
        "result": {
            "experiment_id": "exp",
            "outcome": outcome,
            "metrics": [{"name": "m", "value": 1}],
            "evidence_ids": ["runtime"],
            "criteria_results": criteria,
        }
    })
    verified = execute_operator(_request("claim_verify", refs=[claim, result]), services={})
    assert _artifact(tmp_path, verified)["outputs"]["verdicts"][0]["support_classification"] == expected


def test_report_planning_fails_when_claim_has_no_core_source_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    claim = _external_ref(tmp_path, "claims", "research_claims.v1", {
        "claims": [{
            "claim_id": "claim-without-source",
            "text": "This claim has no source evidence.",
            "acceptance_criteria": [],
            "evidence_ids": [],
        }]
    })

    verified = execute_operator(_request("claim_verify", refs=[claim]), services={})
    verdict = _artifact(tmp_path, verified)["outputs"]["verdicts"][0]
    assert verdict["evidence_ids"] == ["missing-evidence:claim-without-source"]

    planned = execute_operator(
        _request("report_plan", refs=verified["output_artifacts"], payload={"topic": "Core evidence boundary"}),
        services={},
    )
    assert planned["status"] == "failed"
    assert planned["errors"][0]["error_type"] == "insufficient_evidence"
    assert planned["output_artifacts"] == []


def test_provider_failure_is_classified_and_no_artifact_is_written(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    def unavailable(**kwargs):
        raise ConnectionError("provider offline")

    result = execute_operator(
        _request("idea_generate", payload={"research_context": {"question": "test"}}),
        services={"idea_generator": unavailable},
    )
    assert result["status"] == "failed"
    assert result["errors"][0]["error_type"] == "provider_environment_failure"
    assert result["output_artifacts"] == []


def test_same_request_is_byte_idempotent_and_does_not_duplicate_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    request = _request("idea_generate", payload={"research_context": {"question": "repeatable"}})
    first = execute_operator(request, services={"idea_generator": _idea_generator})
    before = (tmp_path / first["output_artifacts"][0]["path"]).read_bytes()
    second = execute_operator(request, services={"idea_generator": _idea_generator})
    after = (tmp_path / second["output_artifacts"][0]["path"]).read_bytes()
    assert before == after
    assert first["hashes"] == second["hashes"]
    assert list((tmp_path / "out/idea_generate").iterdir()) == [tmp_path / "out/idea_generate/idea_candidate.v1.json"]


def test_publication_quality_gate_blocks_unreviewed_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    report = _external_ref(tmp_path, "report", "scientific_report.v1", {
        "report": {
            "report_id": "r",
            "title": "Topic",
            "sections": [{"section_id": "summary", "title": "Summary", "evidence_ids": ["e"]}],
            "evidence_ids": ["e"],
            "unsupported_claims": [],
            "markdown": "# Topic",
        }
    })
    review = _external_ref(tmp_path, "review", "artifact_review.v1", {
        "review": {
            "artifact_id": "r",
            "target": "scientific_report",
            "review_mode": "local_surrogate",
            "review_available": True,
            "difficulty": "standard",
            "focus": "completeness",
            "score": 0.4,
            "recommendation": "revise_required",
            "evidence_ids": ["e"],
        },
        "findings": [{"finding_id": "f", "severity": "high"}],
        "artifact": {},
    })
    result = execute_operator(_request("publication_produce", refs=[report, review]), services={})
    assert result["status"] == "failed"
    assert result["errors"][0]["error_type"] == "quality_gate_failed"
    assert not (tmp_path / "out/publication_produce/publication.md").exists()
