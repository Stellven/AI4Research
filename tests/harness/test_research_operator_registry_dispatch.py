from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "harness"
sys.path.insert(0, str(HARNESS / "tools"))
sys.path.insert(0, str(HARNESS / "lib"))

import multi_task_runner as mtr  # noqa: E402
import operator_runtime  # noqa: E402
import operatord  # noqa: E402
import scheduler_input  # noqa: E402


def _load_adapter():
    path = HARNESS / "tools" / "research_operator_registry_adapter.py"
    spec = importlib.util.spec_from_file_location("research_operator_registry_adapter", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_report_registry_payload_preserves_experiment_evidence() -> None:
    adapter = _load_adapter()
    documents = [
        {"schema": "claim_verdict.v1", "outputs": {"verdicts": []}},
        {"schema": "research_method.v1", "outputs": {"methods": []}},
        {"schema": "experiment_plan.v1", "outputs": {"experiment_plan": {}}},
        {"schema": "experiment_result.v1", "outputs": {"result": {}}},
    ]

    plan_payload = adapter._payload_for_documents("report_plan", documents)
    draft_payload = adapter._payload_for_documents(
        "report_draft",
        [
            {"schema": "scientific_report_plan.v1", "outputs": {"report_plan": {}}},
            *documents,
        ],
    )

    assert set(plan_payload) == {
        "verdicts",
        "research_method",
        "experiment_plan",
        "experiment_result",
    }
    assert set(draft_payload) == {
        "report_plan",
        "verdicts",
        "research_method",
        "experiment_plan",
        "experiment_result",
    }


def test_report_registry_payload_admits_capsule_required_discovery_protocol() -> None:
    adapter = _load_adapter()
    discovery = {
        "schema": "literature_discovery.v1",
        "outputs": {
            "candidates": [{"candidate_id": "paper-1"}],
            "study_protocol": {"protocol_status": "partially_resolved"},
        },
    }

    payload = adapter._payload_for_documents("report_plan", [discovery])

    assert payload == {"literature_discovery": discovery}


def test_paper_analyze_registry_payload_preserves_all_frozen_papers() -> None:
    adapter = _load_adapter()
    documents = [
        {"schema": "research_paper.v1", "outputs": {"paper": {"paper_id": "p1"}}},
        {"schema": "research_paper.v1", "outputs": {"paper": {"paper_id": "p2"}}},
    ]

    payload = adapter._payload_for_documents("paper_analyze", documents)

    assert [item["outputs"]["paper"]["paper_id"] for item in payload["paper_evidence"]] == [
        "p1",
        "p2",
    ]


def test_review_and_publication_registry_payloads_preserve_stage_boundaries() -> None:
    adapter = _load_adapter()
    requirement = {"schema_version": "solar.requirement_ir.v2", "semantic_contract": {}}
    report = {"schema": "scientific_report.v1", "outputs": {"report": {}}}
    report_plan = {"schema": "scientific_report_plan.v1", "outputs": {"report_plan": {}}}
    plan_review = {"schema": "scientific_report_plan_review.v1", "outputs": {"review": {}}}

    payload = adapter._payload_for_documents(
        "publication_produce", [requirement, report]
    )

    assert payload == {
        "requirement_ir": requirement,
        "report": report,
    }
    assert adapter._payload_for_documents("artifact_review", [report_plan]) == {
        "report_plan": report_plan,
    }
    assert adapter._payload_for_documents("artifact_review", [report]) == {
        "report": report,
    }
    draft_payload = adapter._payload_for_documents(
        "report_draft", [report_plan, plan_review]
    )
    assert draft_payload["report_plan_review"] == plan_review


def test_publication_runtime_snapshot_reads_scheduler_state_without_mutating_graph(tmp_path: Path) -> None:
    adapter = _load_adapter()
    graph_path = tmp_path / "sprint-1.task_graph.json"
    graph = {
        "sprint_id": "sprint-1",
        "nodes": [
            {"id": "report", "depends_on": []},
            {"id": "publish", "depends_on": ["report"]},
        ],
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    (tmp_path / "sprint-1.task_graph_state.json").write_text(
        json.dumps(
            {
                "sprint_id": "sprint-1",
                "revision": 7,
                "run_status": "running",
                "updated_at": "2026-09-03T00:00:00Z",
                "nodes": {
                    "report": {"status": "passed", "attempt": 1, "blocked_by": []},
                    "publish": {"status": "running", "attempt": 1, "blocked_by": []},
                },
            }
        ),
        encoding="utf-8",
    )

    snapshot = adapter._runtime_execution_snapshot(
        graph, {"graph_path": str(graph_path), "node_id": "publish"}
    )

    assert snapshot["availability"] == "available"
    assert snapshot["state_revision"] == 7
    assert snapshot["closure_status"] == "pending_scheduler_closure"
    assert [(item["node_id"], item["status"]) for item in snapshot["nodes"]] == [
        ("report", "passed"),
        ("publish", "running"),
    ]
    assert snapshot["nodes"][1]["is_current_node"] is True
    assert "status" not in graph["nodes"][0]


def test_memory_registry_payload_preserves_all_pre_report_evidence_classes() -> None:
    adapter = _load_adapter()
    documents = [
        {"schema": "research_paper.v1", "outputs": {"paper": {"paper_id": "p1"}}},
        {"schema": "claim_verdict.v1", "outputs": {"verdicts": []}},
        {"schema": "research_method.v1", "outputs": {"methods": []}},
        {"schema": "research_source_assessment.v1", "outputs": {"assessments": []}},
        {"schema": "scientific_report_plan.v1", "outputs": {"report_plan": {}}},
    ]

    payload = adapter._payload_for_documents("memory_update_initial", documents)

    assert set(payload) == {
        "paper_evidence",
        "verdict_evidence",
        "research_method",
        "source_assessment",
        "report_plan",
    }


def test_existing_publication_worker_is_permanently_bound_to_native_manifest_action() -> None:
    operators = json.loads(
        (HARNESS / "config" / "physical-operators.json").read_text(encoding="utf-8")
    )["operators"]
    worker = operators["autosci-publication-compile-worker"]

    assert worker["backend"] == "research_operator_registry"
    assert worker["runtime_binding"] == {
        "registry": "plugins.autosci.operators.scientific_lifecycle.registry",
        "node_id": "publication_produce",
        "implementation_operator_id": "autosci-publication-production-physical",
    }
    assert set(worker["resource_requirements"]["required_artifact_types"]) == {
        "requirement_ir.v1",
        "schema:schemas/evidence/scientific_report.v1.schema.json",
    }


def test_existing_review_worker_declares_both_typed_review_targets() -> None:
    operators = json.loads(
        (HARNESS / "config" / "physical-operators.json").read_text(encoding="utf-8")
    )["operators"]
    worker = operators["autosci-artifact-review-worker"]

    assert worker["backend"] == "research_operator_registry"
    assert worker["runtime_binding"] == {
        "registry": "plugins.autosci.operators.scientific_lifecycle.registry",
        "node_id": "artifact_review",
        "implementation_operator_id": "autosci-artifact-review-physical",
    }
    assert set(worker["resource_requirements"]["required_artifact_types"]) == {
        "schema:schemas/evidence/scientific_report_plan.v1.schema.json",
        "schema:schemas/evidence/scientific_report.v1.schema.json",
    }


def test_review_registry_payload_rejects_unrelated_artifact_types() -> None:
    adapter = _load_adapter()

    with pytest.raises(adapter.RegistryAdapterError, match="not admitted"):
        adapter._payload_for_documents(
            "artifact_review",
            [{"schema": "research_claims.v1", "outputs": {"claims": []}}],
        )


def test_review_model_route_uses_frozen_envelope_not_daemon_environment(monkeypatch) -> None:
    adapter = _load_adapter()
    monkeypatch.setenv("SOLAR_RESEARCH_MODEL", "deepseek")
    monkeypatch.setenv("SOLAR_RESEARCH_REASONING_EFFORT", "low")
    node = {
        "capsule_binding": {"capsule_ids": ["cap.research-report-plan-review"]},
        "execution_authority": {
            "capsules": {
                "cap.research-report-plan-review": {
                    "default_operator_profile": "codex-evaluator"
                }
            }
        },
    }
    envelope = {
        "profile": "codex-evaluator",
        "model": "gpt-5.5",
        "reasoning_effort": "medium",
    }

    route = adapter._verified_model_service_route(envelope, node)

    assert route == {
        "profile": "codex-evaluator",
        "model": "gpt-5.5",
        "provider": "openai",
        "reasoning_effort": "medium",
    }


def test_review_model_route_rejects_profile_or_model_tampering() -> None:
    adapter = _load_adapter()
    node = {
        "capsule_binding": {"capsule_ids": ["cap.research-report-plan-review"]},
        "execution_authority": {
            "capsules": {
                "cap.research-report-plan-review": {
                    "default_operator_profile": "codex-evaluator"
                }
            }
        },
    }
    with pytest.raises(adapter.RegistryAdapterError, match="frozen capsule"):
        adapter._verified_model_service_route(
            {
                "profile": "codex-builder",
                "model": "gpt-5.5",
                "reasoning_effort": "medium",
            },
            node,
        )
    with pytest.raises(adapter.RegistryAdapterError, match="registered profile"):
        adapter._verified_model_service_route(
            {
                "profile": "codex-evaluator",
                "model": "gpt-5.4",
                "reasoning_effort": "medium",
            },
            node,
        )


def test_native_discovery_requests_the_complete_production_service_bundle(tmp_path: Path) -> None:
    adapter = _load_adapter()

    overrides = adapter._production_service_overrides(
        "literature_discover",
        envelope={},
        node={},
        work_dir=tmp_path,
    )

    assert overrides is None


def test_report_writer_override_remains_explicit(monkeypatch, tmp_path: Path) -> None:
    adapter = _load_adapter()
    sentinel = object()
    monkeypatch.setattr(
        adapter,
        "_verified_model_service_route",
        lambda _envelope, _node: {
            "model": "gpt-5.5",
            "reasoning_effort": "medium",
        },
    )
    monkeypatch.setattr(adapter, "CodexResearchModelService", lambda *_args, **_kwargs: sentinel)

    overrides = adapter._production_service_overrides(
        "report_draft",
        envelope={},
        node={},
        work_dir=tmp_path,
    )

    assert overrides == {"model_generate": sentinel}


def test_registry_adapter_uses_the_action_registry_error_class_identity() -> None:
    adapter = _load_adapter()
    from harness.plugins.autosci.operators.scientific_lifecycle.action import registry

    service_error = adapter.CodexResearchModelService.__call__.__globals__["ResearchOperatorError"]

    assert service_error is registry.ResearchOperatorError


def test_registry_adapter_resolves_only_hash_bound_workspace_sources(tmp_path: Path) -> None:
    adapter = _load_adapter()
    workspace = tmp_path / "workspace"
    source = workspace / "demo_inputs" / "paper.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"paper")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    graph = {"workspace_authority_ref": {"workspace_root": str(workspace)}}
    node = {
        "workspace_reads": [
            {
                "kind": "file",
                "relative_path": "demo_inputs/paper.pdf",
                "sha256": digest,
            }
        ],
        "read_scope": [str(source.resolve())],
    }

    assert adapter._verified_workspace_sources(graph, node) == [
        {
            "path": str(source.resolve()),
            "relative_path": "demo_inputs/paper.pdf",
            "sha256": digest,
        }
    ]

    source.write_bytes(b"tampered")
    with pytest.raises(adapter.RegistryAdapterError, match="hash does not match"):
        adapter._verified_workspace_sources(graph, node)


def test_unified_registry_resolves_shared_node_by_frozen_implementation_id() -> None:
    adapter = _load_adapter()
    binding = {
        "registry": "plugins.autosci.operators.scientific_lifecycle.registry",
        "node_id": "report_draft",
        "implementation_operator_id": "autosci-report-drafting-physical",
    }

    resolved = adapter._validated_binding(
        {
            "operator_id": "autosci-report-worker",
            "runtime_binding": binding,
        }
    )

    assert resolved == {
        "operator_id": "autosci-report-worker",
        **binding,
    }


def test_report_title_is_bound_from_frozen_requirement_ir() -> None:
    adapter = _load_adapter()
    title = "KV Cache Efficiency Landscape for Long-Context LLM Inference"
    requirement_ir = {
        "schema_version": "solar.requirement_ir.v2",
        "requirements": [{
            "requirement_id": "R-title",
            "statement": f"Use the project name: {title}.",
            "acceptance": {"kind": "coverage", "required_values": [title]},
        }],
    }
    node = {
        "goal": f'Produce the final report titled "{title}" with retained evidence.'
    }

    assert adapter._explicit_report_title(node, [requirement_ir]) == title
    assert adapter._explicit_report_title(
        {"goal": 'Produce the final report titled "Invented title".'},
        [requirement_ir],
    ) == ""


def _binding() -> dict:
    return {
        "registry": "plugins.autosci.operators.scientific_lifecycle.evidence.registry",
        "node_id": "discovery_ingest",
        "implementation_operator_id": "autosci-evidence-discovery-ingest",
    }


def _claim_binding() -> dict:
    return {
        "registry": "plugins.autosci.operators.scientific_lifecycle.evidence.registry",
        "node_id": "claim_extract",
        "implementation_operator_id": "autosci-evidence-claim-extract",
    }


def _scheduler_node(
    node_id: str,
    *,
    depends_on: list[str],
    consumes: list[str],
    produces: list[str],
    operator_id: str = "discovery_ingest_worker",
    capsule_id: str = "cap.research-discovery-ingest",
) -> dict:
    output_routes = [
        {
            "artifact_type": artifact_type,
            "route_kind": "sprint_private",
            "relative_path": f"artifacts/{node_id}/output-{index}",
            "materialization_kind": "directory",
        }
        for index, artifact_type in enumerate(produces, start=1)
    ]
    return {
        "id": node_id,
        "goal": f"Complete {node_id}",
        "logical_operator": "ResearchWorker",
        "dispatch_task_type": "research",
        "depends_on": depends_on,
        "requirement_ids": [f"REQ-{node_id}"],
        "capability_capsule_id": capsule_id,
        "capsule_binding": {
            "capsule_ids": [capsule_id],
            "composition_id": None,
            "contract_sha256": "1" * 64,
        },
        "physical_candidates": [
            {
                "operator_id": operator_id,
                "rank": 1,
                "admission_state": "ELIGIBLE",
            }
        ],
        "artifact_contract": {"consumes": consumes, "produces": produces},
        "output_routes": output_routes,
        "workspace_reads": [],
        "evaluation_binding": {
            "deterministic_gate_ids": ["gate.schema.v1"],
            "semantic_evaluator_ids": ["evaluator.fidelity.v1"],
        },
        "resource_requirements": {
            "cpu_cores_min": 1,
            "memory_mb_min": 128,
            "gpu_required": False,
            "network": "optional",
        },
        "effects": ["read", "write"],
        "priority": 10,
        "failure_policy": {"max_attempts": 2, "on_exhausted": "block_dependents"},
    }


def _verified_dispatch_fixture(tmp_path: Path, adapter=None) -> tuple[dict, Path, Path]:
    literature_type = "schema:schemas/evidence/literature_discovery.v1.schema.json"
    paper_type = "schema:schemas/evidence/research_paper.v1.schema.json"
    value = {
        "schema_version": "solar.scheduler_input.v1",
        "artifact_role": "runtime_execution_authority",
        "scheduler_input_id": "scheduler-input-registry-test",
        "sprint_id": "sprint-registry-test",
        "planning_authority": "frozen_execution_plan_v1",
        "graph": {
            "graph_id": "graph-registry-test",
            "nodes": [
                _scheduler_node(
                    "literature_discover",
                    depends_on=[],
                    consumes=["schema:request-envelope.schema.json"],
                    produces=[literature_type],
                ),
                _scheduler_node(
                    "discovery_ingest",
                    depends_on=["literature_discover"],
                    consumes=[literature_type],
                    produces=[paper_type],
                ),
            ],
        },
    }
    source = tmp_path / "scheduler_input.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    sprints_dir = tmp_path / "sprints"
    runtime_root = tmp_path / "scheduler-runtime"
    graph_path = scheduler_input.prepare_runtime_graph(source, runtime_root)
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    work_dir = Path(graph["runtime_work_dir"])
    work_dir.mkdir(parents=True, exist_ok=True)
    node = next(item for item in graph["nodes"] if item["id"] == "discovery_ingest")
    consume_dir = Path(node["artifact_routes"]["consumes"][literature_type])
    consume_dir.mkdir(parents=True, exist_ok=True)
    source_paper = consume_dir / "paper.md"
    source_paper.write_text("# Battery storage\n\nGrid-storage evidence.", encoding="utf-8")
    (consume_dir / "literature.json").write_text(
        json.dumps({
            "schema": "literature_discovery.v1",
            "task_id": "upstream-task",
            "outputs": {
                "candidates": [{
                    "candidate_id": "paper-001",
                    "title": "Battery storage",
                    "source_ref": str(source_paper),
                }]
            },
        }),
        encoding="utf-8",
    )
    handoff = runtime_root / f"{graph['sprint_id']}.{node['id']}-handoff.md"
    envelope = {
        "task_id": "dispatch-task",
        "sprint_id": graph["sprint_id"],
        "node_id": node["id"],
        "operator_id": "discovery_ingest_worker",
        "objective": node["goal"],
        "runtime_binding": _binding(),
        "physical_candidate_rank": 1,
        "work_dir": str(work_dir),
        "graph_path": str(graph_path),
        "handoff_path": str(handoff),
        "write_scope": node["write_scope"],
        "artifact_contract": node["artifact_contract"],
        "artifact_routes": node["artifact_routes"],
        "capsule_binding": node["capsule_binding"],
        "resource_requirements": node["resource_requirements"],
    }
    if adapter is not None:
        adapter.SPRINTS_DIR = sprints_dir
        adapter.RUN_DIR = tmp_path / "multi-task"
        status_dir = adapter.RUN_DIR / envelope["task_id"]
        status_dir.mkdir(parents=True)
        (status_dir / "status.json").write_text(
            json.dumps({
                "id": envelope["task_id"],
                "task_id": envelope["task_id"],
                "sprint_id": envelope["sprint_id"],
                "node_id": envelope["node_id"],
                "operator_id": envelope["operator_id"],
                "graph": envelope["graph_path"],
                "lease_id": f"{envelope['operator_id']}:{envelope['task_id']}:lease",
            }),
            encoding="utf-8",
        )
    return envelope, graph_path, sprints_dir


def _verified_claim_dispatch_fixture(tmp_path: Path, adapter) -> tuple[dict, Path]:
    paper_type = "schema:schemas/evidence/research_paper.v1.schema.json"
    claims_type = "schema:schemas/evidence/research_claims.v1.schema.json"
    value = {
        "schema_version": "solar.scheduler_input.v1",
        "artifact_role": "runtime_execution_authority",
        "scheduler_input_id": "scheduler-input-claim-test",
        "sprint_id": "sprint-claim-test",
        "planning_authority": "frozen_execution_plan_v1",
        "graph": {
            "graph_id": "graph-claim-test",
            "nodes": [
                _scheduler_node(
                    "paper_ingest",
                    depends_on=[],
                    consumes=["schema:request-envelope.schema.json"],
                    produces=[paper_type],
                ),
                _scheduler_node(
                    "claim_extract",
                    depends_on=["paper_ingest"],
                    consumes=[paper_type],
                    produces=[claims_type],
                    operator_id="autosci-claim-extract-worker",
                    capsule_id="cap.research-claim-extract",
                ),
            ],
        },
    }
    source = tmp_path / "scheduler_input.claim.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    runtime_root = tmp_path / "claim-runtime"
    graph_path = scheduler_input.prepare_runtime_graph(source, runtime_root)
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    work_dir = Path(graph["runtime_work_dir"])
    work_dir.mkdir(parents=True, exist_ok=True)
    node = next(item for item in graph["nodes"] if item["id"] == "claim_extract")
    consume_dir = Path(node["artifact_routes"]["consumes"][paper_type])
    consume_dir.mkdir(parents=True, exist_ok=True)
    (consume_dir / "research_paper.v1.json").write_text(
        json.dumps({
            "schema": "research_paper.v1",
            "status": "completed",
            "outputs": {
                "paper": {
                    "paper_id": "paper-battery-001",
                    "title": "Battery grid storage evidence",
                    "source_ref": "paper-battery-001",
                    "parse_status": "parsed",
                    "sections": [{
                        "title": "Results",
                        "text": "The study demonstrates that sodium-ion storage reduced lifecycle cost by 18 percent compared with the lithium-ion baseline.",
                        "source_anchor": "paper-battery-001#results",
                    }],
                }
            },
        }),
        encoding="utf-8",
    )
    handoff = runtime_root / f"{graph['sprint_id']}.{node['id']}-handoff.md"
    envelope = {
        "task_id": "claim-dispatch-task",
        "sprint_id": graph["sprint_id"],
        "node_id": node["id"],
        "operator_id": "autosci-claim-extract-worker",
        "objective": node["goal"],
        "runtime_binding": _claim_binding(),
        "physical_candidate_rank": 1,
        "work_dir": str(work_dir),
        "graph_path": str(graph_path),
        "handoff_path": str(handoff),
        "write_scope": node["write_scope"],
        "artifact_contract": node["artifact_contract"],
        "artifact_routes": node["artifact_routes"],
        "capsule_binding": node["capsule_binding"],
        "resource_requirements": node["resource_requirements"],
    }
    adapter.RUN_DIR = tmp_path / "multi-task"
    status_dir = adapter.RUN_DIR / envelope["task_id"]
    status_dir.mkdir(parents=True)
    (status_dir / "status.json").write_text(
        json.dumps({
            "id": envelope["task_id"],
            "task_id": envelope["task_id"],
            "sprint_id": envelope["sprint_id"],
            "node_id": envelope["node_id"],
            "operator_id": envelope["operator_id"],
            "graph": envelope["graph_path"],
            "lease_id": f"{envelope['operator_id']}:{envelope['task_id']}:lease",
        }),
        encoding="utf-8",
    )
    return envelope, graph_path


def test_registry_backend_capability_is_recognized_and_binding_is_preserved(monkeypatch):
    monkeypatch.setattr(mtr, "HARNESS_DIR", HARNESS)
    operator = {
        "operator_id": "discovery_ingest_worker",
        "backend": "research_operator_registry",
        "runtime_binding": _binding(),
        "enabled": True,
        "available": True,
    }
    profile = mtr.apply_operator_to_profile({"name": "builder", "role": "builder"}, operator)

    assert mtr.capability_for_profile(profile, include_probe=False)["status"] == "ok"
    assert profile["runtime_binding"] == _binding()
    profile["runtime_binding"]["node_id"] = "changed"
    assert operator["runtime_binding"]["node_id"] == "discovery_ingest"


def test_all_current_providerless_registry_operators_are_locally_dispatchable(monkeypatch):
    monkeypatch.setattr(operator_runtime, "get_operator_runtime_state", lambda _operator_id: "idle")
    operators = json.loads((HARNESS / "config" / "physical-operators.json").read_text(encoding="utf-8"))["operators"]
    registry_operators = {
        operator_id: operator
        for operator_id, operator in operators.items()
        if operator.get("backend") == "research_operator_registry"
    }

    assert set(registry_operators) == {
        "autosci-claim-extract-worker",
        "autosci-literature-discover-worker",
        "autosci-method-extract-worker",
        "autosci-paper-analyze-native-worker",
        "dataset_prepare_worker",
        "discovery_ingest_worker",
        "source_assess_worker",
        "idea_evaluate_worker",
        "experiment_design_worker",
        "experiment_run_worker",
        "claim_select_one_worker",
        "claim_verify_worker",
        "experiment_monitor_worker",
        "experiment_approval_gate_worker",
        "autosci-memory-update-worker",
        "autosci-report-plan-worker",
        "autosci-artifact-review-worker",
        "autosci-report-worker",
        "autosci-publication-compile-worker",
    }
    for operator_id, operator in registry_operators.items():
        assert not operator.get("provider") and not operator.get("vendor")
        assert not operator.get("key_ref")
        assert mtr.operator_dispatchable({"operator_id": operator_id, **operator}) == (True, "ready")


def test_all_current_registry_operators_ship_their_declared_persona():
    operators = json.loads((HARNESS / "config" / "physical-operators.json").read_text(encoding="utf-8"))["operators"]

    for operator_id, operator in operators.items():
        if operator.get("backend") != "research_operator_registry":
            continue
        persona = str(operator.get("persona") or operator.get("role") or "").strip()
        assert persona, f"{operator_id} does not declare a persona"
        persona_path = HARNESS / "personas" / f"{persona}.md"
        assert persona_path.is_file(), f"{operator_id} persona file missing: {persona_path}"


def test_provider_backed_registry_operator_still_requires_credential_reference(monkeypatch):
    monkeypatch.setattr(operator_runtime, "get_operator_runtime_state", lambda _operator_id: "idle")
    provider_backed = {
        "operator_id": "provider-registry-worker",
        "backend": "research_operator_registry",
        "provider": "external-provider",
        "enabled": True,
        "available": True,
        "runtime_binding": _binding(),
    }

    assert mtr.operator_dispatchable(provider_backed) == (False, "key_ref_missing")


def test_operator_envelope_forwards_frozen_runtime_binding():
    profile = {"operator_id": "discovery_ingest_worker", "runtime_binding": _binding()}
    envelope = mtr._build_operator_envelope(
        "task-1",
        "sprint-1",
        "graph-node-1",
        {"id": "graph-node-1"},
        profile,
        {"work_dir": "work", "write_scope": ["out"]},
    )

    assert envelope["operator_id"] == "discovery_ingest_worker"
    assert envelope["runtime_binding"] == _binding()


def test_operatord_launches_registry_adapter_or_returns_explicit_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(operatord, "HARNESS_DIR", HARNESS)
    envelope_path = tmp_path / "envelope.json"
    argv = operatord._build_command(
        {"backend": "research_operator_registry", "runtime_binding": _binding()},
        {"task_id": "task-1"},
        {"SOLAR_OPERATOR_ENVELOPE_JSON": str(envelope_path)},
    )

    assert Path(argv[1]).name == "research_operator_registry_adapter.py"
    assert argv[-2:] == ["--envelope", str(envelope_path)]

    missing = operatord._build_command(
        {"backend": "research_operator_registry", "runtime_binding": _binding()},
        {"task_id": "task-1"},
        {},
    )
    assert missing[1:2] == ["-c"]
    assert "unavailable" in missing[2]


def test_registry_adapter_executes_exact_discovery_ingest_entrypoint(tmp_path):
    adapter = _load_adapter()
    envelope, _graph_path, _sprints_dir = _verified_dispatch_fixture(tmp_path, adapter)
    receipt_path = tmp_path / "node_envelope.json"

    receipt = adapter.execute(envelope, receipt_path=receipt_path)

    assert receipt["status"] == "completed"
    assert receipt["operator_id"] == "discovery_ingest_worker"
    assert receipt["node"] == "discovery_ingest"
    assert receipt["artifacts"]
    assert all((Path(envelope["work_dir"]) / item["path"]).is_file() for item in receipt["artifacts"])
    assert receipt_path.is_file()
    assert Path(envelope["handoff_path"]).is_file()


def test_registry_adapter_accepts_direct_graph_dispatch_operator_lease(tmp_path):
    adapter = _load_adapter()
    envelope, _graph_path, _sprints_dir = _verified_dispatch_fixture(tmp_path, adapter)
    status_path = adapter.RUN_DIR / envelope["task_id"] / "status.json"
    status_path.unlink()
    adapter.OPERATOR_LEASE_DIR = tmp_path / "operator-leases"
    adapter.OPERATOR_LEASE_DIR.mkdir()
    (adapter.OPERATOR_LEASE_DIR / f"{envelope['operator_id']}.json").write_text(
        json.dumps(
            {
                "operator_id": envelope["operator_id"],
                "task_id": envelope["task_id"],
                "sprint_id": envelope["sprint_id"],
                "node_id": envelope["node_id"],
                "leased_at": "2026-08-28T18:49:30Z",
                "expires_at": "2099-08-28T19:04:30Z",
                "state": "running",
            }
        ),
        encoding="utf-8",
    )

    receipt = adapter.execute(envelope, receipt_path=tmp_path / "direct_node_envelope.json")

    assert receipt["status"] == "completed"
    assert receipt["operator_id"] == envelope["operator_id"]


def test_registry_adapter_rejects_operator_lease_for_another_task(tmp_path):
    adapter = _load_adapter()
    envelope, _graph_path, _sprints_dir = _verified_dispatch_fixture(tmp_path, adapter)
    status_path = adapter.RUN_DIR / envelope["task_id"] / "status.json"
    status_path.unlink()
    adapter.OPERATOR_LEASE_DIR = tmp_path / "operator-leases"
    adapter.OPERATOR_LEASE_DIR.mkdir()
    (adapter.OPERATOR_LEASE_DIR / f"{envelope['operator_id']}.json").write_text(
        json.dumps(
            {
                "operator_id": envelope["operator_id"],
                "task_id": "another-task",
                "sprint_id": envelope["sprint_id"],
                "node_id": envelope["node_id"],
                "leased_at": "2026-08-28T18:49:30Z",
                "expires_at": "2099-08-28T19:04:30Z",
                "state": "running",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(adapter.RegistryAdapterError, match="task_id does not match"):
        adapter.execute(envelope, receipt_path=tmp_path / "direct_node_envelope.json")


def test_registry_adapter_claim_extract_consumes_frozen_paper_route_and_hands_off_direct_artifact(tmp_path):
    adapter = _load_adapter()
    envelope, _graph_path = _verified_claim_dispatch_fixture(tmp_path, adapter)

    receipt = adapter.execute(envelope, receipt_path=tmp_path / "claim_node_envelope.json")

    assert receipt["status"] == "completed"
    assert receipt["operator_id"] == "autosci-claim-extract-worker"
    assert receipt["node"] == "claim_extract"
    artifact_path = Path(envelope["work_dir"]) / receipt["artifacts"][0]["path"]
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["schema"] == "research_claims.v1"
    assert artifact["outputs"]["claims"][0]["source_anchor"] == "paper-battery-001#results"
    assert "sample_paper.md" not in json.dumps(artifact)
    handoff = Path(envelope["handoff_path"]).read_text(encoding="utf-8")
    assert f"- Result: `{artifact_path.resolve()}`" in handoff


def test_registry_adapter_isolated_subprocess_imports_and_executes_registry(tmp_path):
    envelope, _graph_path, sprints_dir = _verified_dispatch_fixture(tmp_path)
    run_dir = tmp_path / "multi-task"
    status_dir = run_dir / envelope["task_id"]
    status_dir.mkdir(parents=True)
    (status_dir / "status.json").write_text(
        json.dumps({
            "id": envelope["task_id"],
            "task_id": envelope["task_id"],
            "sprint_id": envelope["sprint_id"],
            "node_id": envelope["node_id"],
            "operator_id": envelope["operator_id"],
            "graph": envelope["graph_path"],
            "lease_id": f"{envelope['operator_id']}:{envelope['task_id']}:lease",
        }),
        encoding="utf-8",
    )
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["SPRINTS_DIR"] = str(sprints_dir)
    env["SOLAR_MULTI_TASK_RUN_DIR"] = str(run_dir)

    result = subprocess.run(
        [sys.executable, "-I", str(HARNESS / "tools" / "research_operator_registry_adapter.py"),
         "--envelope", str(envelope_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout)["ok"] is True
    assert (tmp_path / "node_envelope.json").is_file()


@pytest.mark.parametrize(
    ("field", "mutated"),
    [
        ("sprint_id", "other-sprint"),
        ("artifact_contract", {"consumes": [], "produces": []}),
        ("artifact_routes", {"consumes": {}, "produces": {}}),
        ("capsule_binding", {"capsule_ids": ["cap.untrusted"]}),
        ("handoff_path", "outside-handoff.md"),
    ],
)
def test_registry_adapter_rejects_envelope_authority_drift(tmp_path, field, mutated):
    adapter = _load_adapter()
    envelope, _graph_path, _sprints_dir = _verified_dispatch_fixture(tmp_path, adapter)
    envelope[field] = mutated

    with pytest.raises(adapter.RegistryAdapterError):
        adapter.execute(envelope, receipt_path=tmp_path / "node_envelope.json")


def test_registry_adapter_rejects_tampered_graph_route_escape(tmp_path):
    adapter = _load_adapter()
    envelope, graph_path, _sprints_dir = _verified_dispatch_fixture(tmp_path, adapter)
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    node = next(item for item in graph["nodes"] if item["id"] == "discovery_ingest")
    artifact_type = node["artifact_contract"]["consumes"][0]
    node["artifact_routes"]["consumes"][artifact_type] = str(tmp_path / "outside")
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    envelope["artifact_routes"] = node["artifact_routes"]

    with pytest.raises(adapter.RegistryAdapterError, match="runtime graph verification failed"):
        adapter.execute(envelope, receipt_path=tmp_path / "node_envelope.json")


def test_registry_adapter_accepts_exact_hashed_external_runtime_input_read_only(tmp_path):
    adapter = _load_adapter()
    literature_type = "schema:schemas/evidence/literature_discovery.v1.schema.json"
    paper_type = "schema:schemas/evidence/research_paper.v1.schema.json"
    external = tmp_path / "controller-inputs" / "literature.json"
    external.parent.mkdir()
    external.write_text(json.dumps({
        "schema": "literature_discovery.v1",
        "outputs": {"candidates": []},
    }), encoding="utf-8")
    value = {
        "schema_version": "solar.scheduler_input.v1",
        "artifact_role": "runtime_execution_authority",
        "scheduler_input_id": "scheduler-input-external-test",
        "sprint_id": "sprint-external-test",
        "planning_authority": "frozen_execution_plan_v1",
        "graph": {
            "graph_id": "graph-external-test",
            "nodes": [
                _scheduler_node(
                    "discovery_ingest",
                    depends_on=[],
                    consumes=[literature_type],
                    produces=[paper_type],
                )
            ],
        },
    }
    source = tmp_path / "scheduler_input_external.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    runtime_root = tmp_path / "runtime-external"
    graph_path = scheduler_input.prepare_runtime_graph(
        source,
        runtime_root,
        artifact_bindings={literature_type: str(external)},
    )
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    work_dir = Path(graph["runtime_work_dir"])
    work_dir.mkdir(parents=True)
    node = graph["nodes"][0]
    envelope = {
        "task_id": "external-dispatch",
        "sprint_id": graph["sprint_id"],
        "node_id": node["id"],
        "operator_id": "discovery_ingest_worker",
        "runtime_binding": _binding(),
        "physical_candidate_rank": 1,
        "work_dir": str(work_dir),
        "graph_path": str(graph_path),
        "handoff_path": str(runtime_root / f"{graph['sprint_id']}.{node['id']}-handoff.md"),
        "write_scope": node["write_scope"],
        "artifact_contract": node["artifact_contract"],
        "artifact_routes": node["artifact_routes"],
        "capsule_binding": node["capsule_binding"],
        "resource_requirements": node["resource_requirements"],
    }

    verified_graph, verified_node, verified_work_dir, _handoff = adapter._verified_dispatch_authority(
        envelope,
        configured_binding=_binding(),
    )
    documents, paths = adapter._matching_input_documents(
        verified_graph,
        verified_node,
        verified_work_dir,
    )

    assert documents[0]["schema"] == "literature_discovery.v1"
    assert paths == [str(external.resolve())]


def test_registry_adapter_fails_closed_on_binding_drift_with_explicit_reason(tmp_path, capsys):
    adapter = _load_adapter()
    bad = {
        "operator_id": "discovery_ingest_worker",
        "runtime_binding": {**_binding(), "node_id": "wrong"},
    }
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps(bad), encoding="utf-8")

    assert adapter.main(["--envelope", str(envelope_path)]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["reason"] == "research_operator_registry_dispatch_failed"
    assert "runtime_binding does not match configured operator" in failure["error"]


@pytest.mark.parametrize("task_id", ["../other-task", "..\\other-task", ""])
def test_registry_adapter_rejects_unsafe_task_id(tmp_path, task_id):
    adapter = _load_adapter()
    envelope, _graph_path, _sprints_dir = _verified_dispatch_fixture(tmp_path, adapter)
    envelope["task_id"] = task_id

    with pytest.raises(adapter.RegistryAdapterError, match="safe scheduler dispatch identifier"):
        adapter.execute(envelope, receipt_path=tmp_path / "node_envelope.json")


def test_registry_adapter_rejects_wrong_or_missing_scheduler_lease(tmp_path):
    adapter = _load_adapter()
    envelope, _graph_path, _sprints_dir = _verified_dispatch_fixture(tmp_path, adapter)
    status_path = adapter.RUN_DIR / envelope["task_id"] / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["node_id"] = "other-node"
    status_path.write_text(json.dumps(status), encoding="utf-8")

    with pytest.raises(adapter.RegistryAdapterError, match="node_id does not match"):
        adapter.execute(envelope, receipt_path=tmp_path / "node_envelope.json")

    status_path.unlink()
    with pytest.raises(
        adapter.RegistryAdapterError,
        match="neither scheduler task status nor an active operator lease exists",
    ):
        adapter.execute(envelope, receipt_path=tmp_path / "node_envelope.json")
