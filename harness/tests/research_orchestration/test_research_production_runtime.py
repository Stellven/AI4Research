from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from research_orchestration.evaluator import evaluate_production_result  # noqa: E402
from research_orchestration.resolver import PhysicalOperatorBinding, PhysicalOperatorResolver  # noqa: E402
from research_orchestration.runtime import (  # noqa: E402
    FileWorkflowCatalog,
    SolarResearchRuntime,
    _git_checkout_provenance,
    default_production_resolver,
)


def _workflow_loader(artifact_root: Path):
    def load(decision):
        output = artifact_root / "out"
        return {
            "workflow_id": "general_research_v1",
            "workflow_kind": decision.workflow_kind,
            "start_node": decision.start_stage,
            "nodes": [
                {
                    "node_id": decision.start_stage,
                    "depends_on": [],
                    "required_for_completion": True,
                    "logical_operator": f"logical_{decision.start_stage}",
                    "physical_operator": f"physical_{decision.start_stage}",
                    "required_capabilities": [],
                    "read_scope": [str(artifact_root)],
                    "write_scope": [str(output)],
                    "allow_network": False,
                    "allow_live_provider": False,
                    "timeout_seconds": 30,
                    "max_attempts": 1,
                    "gate": f"G_{decision.start_stage.upper()}",
                }
            ],
        }

    return load


def _resolver(artifact_root: Path) -> PhysicalOperatorResolver:
    def run(request: dict) -> dict:
        output = artifact_root / "out" / f"{request['node_id']}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "schema": "test.output.v1",
                    "task_id": request["task_id"],
                    "prompt": request["typed_inputs"]["payload"]["task_contract"]["user_intent"],
                    "run_id": request["run_id"],
                    "workflow_id": request["workflow_id"],
                    "node_id": request["node_id"],
                    "artifact_id": f"artifact-{request['node_id']}",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        artifact_id = f"artifact-{request['node_id']}"
        return {
            "schema": "research_node_result.v1",
            "task_id": request["task_id"],
            "run_id": request["run_id"],
            "workflow_id": request["workflow_id"],
            "node_id": request["node_id"],
            "status": "completed",
            "status_is_terminal": True,
            "output_artifacts": [
                {"artifact_id": artifact_id, "path": str(output), "schema": "test.output.v1", "sha256": digest}
            ],
            "evidence": [
                {
                    "evidence_id": f"evidence-{request['node_id']}",
                    "kind": "runtime_test",
                    "summary": "The bounded operator wrote verified output.",
                    "artifact_id": artifact_id,
                }
            ],
            "hashes": [{"hash_id": artifact_id, "algorithm": "sha256", "value": digest}],
            "model_provider_usage": [],
            "errors": [],
            "limitations": [],
            "secret_redaction_assertion": {"no_secrets_observed": True, "redaction_review": "passed"},
        }

    stages = ("web_fetch", "paper_ingest", "material_ingest", "source_discovery", "evidence_import")
    return PhysicalOperatorResolver(
        [PhysicalOperatorBinding(f"physical_{stage}", run, version="test.v1") for stage in stages]
    )


def test_runtime_preserves_full_prompt_and_run_id_and_propagates_final_status(tmp_path: Path) -> None:
    prompt = "请深入分析 https://example.test/full article 并保留完整中文输出要求"
    runtime = SolarResearchRuntime(
        artifact_root=tmp_path,
        workflow_loader=_workflow_loader(tmp_path),
        operator_resolver=_resolver(tmp_path),
    )

    result = runtime.run(prompt=prompt, run_id="route-run-001")

    assert result["run_id"] == "route-run-001"
    assert result["prompt"] == prompt
    assert result["route"]["start_stage"] == "web_fetch"
    assert result["start_node"] == "web_fetch"
    assert result["final_status"] == "completed"
    artifact = json.loads((tmp_path / "out" / "web_fetch.json").read_text(encoding="utf-8"))
    assert artifact["prompt"] == prompt
    assert artifact["run_id"] == "route-run-001"


def test_runtime_resume_reuses_completed_state_without_redispatch(tmp_path: Path) -> None:
    calls = {"count": 0}
    base_resolver = _resolver(tmp_path)

    def counted(request: dict) -> dict:
        calls["count"] += 1
        return base_resolver.execute(request)

    resolver = PhysicalOperatorResolver(
        [PhysicalOperatorBinding("physical_source_discovery", counted)]
    )
    runtime = SolarResearchRuntime(
        artifact_root=tmp_path,
        workflow_loader=_workflow_loader(tmp_path),
        operator_resolver=resolver,
    )
    prompt = "Survey durable workflow recovery"

    first = runtime.run(prompt=prompt, run_id="resume-run")
    resumed = runtime.run(prompt=prompt, run_id="resume-run", run_mode="resume")

    assert first["final_status"] == "completed"
    assert resumed["final_status"] == "completed"
    assert resumed["run_mode"] == "resume"
    assert calls["count"] == 1


def test_runtime_import_evidence_enters_evidence_import_stage(tmp_path: Path) -> None:
    imported = tmp_path / "imported.json"
    imported.write_text('{"schema":"external.test.v1","value":1}', encoding="utf-8")
    evidence_ref = {
        "artifact_id": "external-1",
        "path": str(imported),
        "sha256": hashlib.sha256(imported.read_bytes()).hexdigest(),
        "provenance": {"source": "prior-run", "captured_at": "2026-08-05T00:00:00Z"},
    }
    runtime = SolarResearchRuntime(
        artifact_root=tmp_path,
        workflow_loader=_workflow_loader(tmp_path),
        operator_resolver=_resolver(tmp_path),
    )

    result = runtime.run(
        prompt="Import and evaluate the supplied evidence",
        run_id="import-run",
        run_mode="import_evidence",
        supplied_evidence=[evidence_ref],
    )

    assert result["route"]["start_stage"] == "evidence_import"
    assert result["final_status"] == "completed"


def test_production_evaluator_rejects_empty_or_hash_mismatched_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "empty.json"
    artifact.write_bytes(b"")
    result = {
        "status": "completed",
        "errors": [],
        "limitations": [],
        "evidence": [{"evidence_id": "e1", "artifact_id": "a1"}],
        "output_artifacts": [{"artifact_id": "a1", "path": str(artifact), "sha256": "0" * 64}],
    }

    decision = evaluate_production_result({}, result, {}, artifact_root=tmp_path)

    assert decision["accepted"] is False
    assert decision["status"] == "failed"
    assert "missing or empty" in decision["errors"][0]["message"]


def test_explicit_network_authorization_approves_bounded_non_provider_node(tmp_path: Path) -> None:
    captured: dict = {}

    def workflow_loader(decision):
        return {
            "workflow_id": "network_research_v1",
            "workflow_kind": decision.workflow_kind,
            "start_node": "seed_fetch",
            "nodes": [{
                "node_id": "seed_fetch",
                "depends_on": [],
                "required_for_completion": True,
                "logical_operator": "ResearchSeedFetcher",
                "physical_operator": "seed_fetch_operator",
                "required_capabilities": ["cap.research.seed.fetch"],
                "read_scope": [str(tmp_path)],
                "write_scope": [str(tmp_path / "out")],
                "allow_network": True,
                "allow_live_provider": False,
                "gate": "G_SEED_FETCH",
            }],
        }

    base = _resolver(tmp_path)

    def run(request: dict) -> dict:
        captured.update(request["authorization"])
        forwarded = dict(request)
        forwarded["physical_operator"] = {
            **request["physical_operator"],
            "operator_id": "physical_web_fetch",
        }
        return base.execute(forwarded)

    runtime = SolarResearchRuntime(
        artifact_root=tmp_path,
        workflow_loader=workflow_loader,
        operator_resolver=PhysicalOperatorResolver([
            PhysicalOperatorBinding("seed_fetch_operator", run, version="test.v1")
        ]),
        authorization={"allow_network": True},
    )

    result = runtime.run(
        prompt="Analyze https://example.test/research",
        run_id="network-authorized",
    )

    assert result["final_status"] == "completed"
    assert captured["allow_network"] is True
    assert captured["approved_capabilities"] == ["cap.research.seed.fetch"]


def test_explicit_live_provider_authorization_approves_provider_capability(tmp_path: Path) -> None:
    captured: dict = {}

    def workflow_loader(decision):
        return {
            "workflow_id": "provider_research_v1",
            "workflow_kind": decision.workflow_kind,
            "start_node": "source_discovery",
            "nodes": [{
                "node_id": "source_discovery",
                "depends_on": [],
                "required_for_completion": True,
                "logical_operator": "ResearchSourceDiscovery",
                "physical_operator": "source_discovery_operator",
                "required_capabilities": ["cap.research.source.discovery"],
                "read_scope": [str(tmp_path)],
                "write_scope": [str(tmp_path / "out")],
                "allow_network": True,
                "allow_live_provider": True,
                "gate": "G_SOURCE_DISCOVERY",
            }],
        }

    base = _resolver(tmp_path)

    def run(request: dict) -> dict:
        captured.update(request["authorization"])
        forwarded = dict(request)
        forwarded["physical_operator"] = {
            **request["physical_operator"],
            "operator_id": "physical_source_discovery",
        }
        return base.execute(forwarded)

    runtime = SolarResearchRuntime(
        artifact_root=tmp_path,
        workflow_loader=workflow_loader,
        operator_resolver=PhysicalOperatorResolver([
            PhysicalOperatorBinding("source_discovery_operator", run, version="test.v1")
        ]),
        authorization={
            "allow_network": True,
            "allow_live_provider": True,
            "approval_ref": "user-approved-live-provider",
        },
    )

    result = runtime.run(prompt="Survey a bounded topic", run_id="provider-authorized")

    assert result["final_status"] == "completed"
    assert captured["allow_network"] is True
    assert captured["allow_live_provider"] is True
    assert captured["approved_capabilities"] == ["cap.research.source.discovery"]


def test_real_markdown_lifecycle_preserves_method_result_and_git_provenance(tmp_path: Path) -> None:
    fixture = ROOT / "plugins" / "autosci" / "tests" / "fixtures" / "sample_paper.md"
    runtime = SolarResearchRuntime(
        artifact_root=tmp_path,
        workflow_loader=FileWorkflowCatalog(harness_root=ROOT).load,
        operator_resolver=default_production_resolver(services={}, workspace_root=tmp_path),
        authorization={
            "allow_network": False,
            "allow_live_provider": False,
            "approval_ref": "unit-test-publication-approval",
        },
    )

    result = runtime.run(
        prompt="Synthesize the Markdown paper, preserving its method, results, and limitations.",
        run_id="markdown-fidelity-e2e",
        seed_inputs=[{"seed_kind": "markdown", "value": str(fixture)}],
        max_steps=40,
    )

    assert result["final_status"] == "completed"
    report_path = (
        tmp_path
        / "artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/final-report.md"
    )
    report = report_path.read_text(encoding="utf-8")
    for expected in (
        "## Methods",
        "deterministic bridge action",
        "Solar Evidence ABI",
        "result.json",
        "evidence.jsonl",
        "monolithic AutoSci workflow owner",
    ):
        assert expected in report
    current_head = subprocess.run(
        ["git", "-C", str(ROOT.parent), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert result["run_provenance"]["repo_head"] == current_head
    assert result["run_provenance"]["workflow_identity"] == {
        "workflow_id": "scientific_research_lifecycle_full_v1",
        "workflow_version": 1,
        "workflow_kind": "paper_ingestion",
    }
    state = json.loads(Path(result["state_path"]).read_text(encoding="utf-8"))
    assert state["run_provenance"] == result["run_provenance"]
    final_evaluation = json.loads(
        (
            tmp_path
            / "artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/research_final_evaluation.v1.json"
        ).read_text(encoding="utf-8")
    )
    evaluation = final_evaluation["outputs"]["evaluation"]
    assert evaluation["accepted"] is True
    assert evaluation["run_provenance"] == result["run_provenance"]
    assert all(item["status"] == "passed" for item in evaluation["criterion_results"])


def test_git_provenance_fails_closed_when_checkout_identity_is_unavailable(tmp_path: Path) -> None:
    provenance = _git_checkout_provenance(tmp_path)

    assert provenance["repo_head"] == "unavailable"
    assert provenance["worktree_status"] == "unavailable"
    assert set(provenance) == {"repo_head", "worktree_status", "captured_at"}


def _revision_discovery(*, seed_snapshot: dict, payload: dict) -> dict:
    del seed_snapshot, payload
    return {
        "trace": "unit:revision-loop",
        "candidates": [
            {
                "source_id": "source-1",
                "title": "Bounded report repair loops",
                "url": "https://example.test/report-repair",
                "metadata": {"kind": "paper"},
                "provenance": {"provider": "unit", "trace": "source-1"},
                "content_summary": "Report repair loops should revise review-identified defects before final acceptance.",
            },
            {
                "source_id": "source-2",
                "title": "Evidence-preserving final gates",
                "url": "https://example.test/final-gates",
                "metadata": {"kind": "paper"},
                "provenance": {"provider": "unit", "trace": "source-2"},
                "content_summary": "Final gates should preserve hash lineage and fail closed after unresolved review defects.",
            },
        ],
        "provider_usage": [],
        "limitations": ["Unit discovery fixture."],
    }


class _RevisionLoopModel:
    def __init__(self, *, revised_review_verdict: str = "accept", revised_review_severity: str = "low") -> None:
        self.calls: list[str] = []
        self.revised_review_verdict = revised_review_verdict
        self.revised_review_severity = revised_review_severity

    def __deepcopy__(self, memo: dict) -> "_RevisionLoopModel":
        del memo
        return self

    def __call__(self, *, node_id: str, **kwargs) -> dict:
        self.calls.append(node_id)
        usage = [{"provider": "unit", "model": "revision-loop", "usage_kind": "llm"}]
        if node_id == "evidence_synthesis":
            return {
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "text": "Report repair loops revise review-identified defects before final acceptance.",
                        "evidence_ids": ["source-1"],
                        "uncertainty": "low",
                        "limitations": [],
                    },
                    {
                        "claim_id": "claim-2",
                        "text": "Final gates preserve hash lineage and fail closed after unresolved review defects.",
                        "evidence_ids": ["source-2"],
                        "uncertainty": "low",
                        "limitations": [],
                    },
                ],
                "provider_usage": usage,
            }
        if node_id == "report_draft":
            return {
                "report": {
                    "title": "Report Repair Loop",
                    "body": "# Report Repair Loop\n\n## Findings\n\nReport repair loops revise review-identified defects before final acceptance.",
                    "conclusions": [
                        {
                            "conclusion_id": "conclusion-1",
                            "text": "Report repair loops revise review-identified defects before final acceptance.",
                            "evidence_ids": ["claim-1"],
                        },
                        {
                            "conclusion_id": "conclusion-2",
                            "text": "Final gates preserve hash lineage and fail closed after unresolved review defects.",
                            "evidence_ids": ["claim-2"],
                        },
                    ],
                },
                "provider_usage": usage,
            }
        if node_id == "report_revision":
            prior_review = kwargs["independent_review"]
            assert prior_review["verdict_suggestion"] == "revise"
            return {
                "report": {
                    "title": "Report Repair Loop",
                    "body": (
                        "# Report Repair Loop\n\n"
                        "## Findings\n\n"
                        "Report repair loops revise review-identified defects before final acceptance.\n\n"
                        "Final gates preserve hash lineage and fail closed after unresolved review defects.\n\n"
                        "## Evidence Method\n\n"
                        "The revision used the source-validation, synthesis, report draft, and independent-review artifacts."
                    ),
                    "conclusions": [
                        {
                            "conclusion_id": "conclusion-1",
                            "text": "Report repair loops revise review-identified defects before final acceptance.",
                            "evidence_ids": ["claim-1"],
                        },
                        {
                            "conclusion_id": "conclusion-2",
                            "text": "Final gates preserve hash lineage and fail closed after unresolved review defects.",
                            "evidence_ids": ["claim-2"],
                        },
                    ],
                },
                "provider_usage": usage,
            }
        if node_id == "independent_review":
            return {
                "findings": [
                    {
                        "finding_id": "review.needs_revision",
                        "severity": "high",
                        "category": "completeness",
                        "message": "The initial report needs revision before final acceptance.",
                    }
                ],
                "verdict_suggestion": "revise",
                "provider_usage": usage,
            }
        if node_id == "report_revision_review":
            return {
                "findings": [
                    {
                        "finding_id": "review.after_revision",
                        "severity": self.revised_review_severity,
                        "category": "completeness",
                        "message": "The revised report was reviewed after the bounded repair attempt.",
                    }
                ],
                "verdict_suggestion": self.revised_review_verdict,
                "provider_usage": usage,
            }
        raise AssertionError(f"unexpected model node: {node_id}")


def _run_revision_loop(tmp_path: Path, model: _RevisionLoopModel) -> dict:
    runtime = SolarResearchRuntime(
        artifact_root=tmp_path,
        workflow_loader=FileWorkflowCatalog(
            harness_root=ROOT,
            entrypoint_aliases={"research_synthesis": {"web_fetch": "seed_fetch"}},
        ).load,
        operator_resolver=default_production_resolver(
            services={
                "discover_sources": _revision_discovery,
                "model_generate": model,
                "review_model_generate": model,
            },
            workspace_root=tmp_path,
        ),
        authorization={
            "allow_network": True,
            "allow_live_provider": True,
            "approval_ref": "unit-approved-report-revision-loop",
        },
    )
    return runtime.run(
        prompt="Survey Solar report repair loop behavior.",
        run_id="report-revision-loop",
        seed_inputs=[{"seed_kind": "topic", "value": "Solar report repair loop"}],
        max_steps=30,
    )


def test_report_revision_repairs_reviewed_report_before_final_acceptance(tmp_path: Path) -> None:
    model = _RevisionLoopModel()

    result = _run_revision_loop(tmp_path, model)

    assert result["final_status"] == "completed"
    assert model.calls.count("report_revision") == 1
    assert model.calls.count("report_revision_review") == 1
    revision = json.loads(
        (
            tmp_path
            / "artifacts/research_synthesis_v1/revision/report_revision.json"
        ).read_text(encoding="utf-8")
    )
    assert revision["revision_applied"] is True
    assert revision["revision_attempt"] == 1
    assert revision["revision_review"]["verdict_suggestion"] == "accept"
    final_gate = json.loads(
        (
            tmp_path
            / "artifacts/research_synthesis_v1/final/final_acceptance.json"
        ).read_text(encoding="utf-8")
    )
    assert final_gate["accepted"] is True
    assert final_gate["revision_applied"] is True
    assert final_gate["active_report_artifact"] == "report_revision"


def test_report_revision_keeps_final_status_failed_when_re_review_still_blocks(tmp_path: Path) -> None:
    model = _RevisionLoopModel(revised_review_verdict="revise", revised_review_severity="high")

    result = _run_revision_loop(tmp_path, model)

    assert result["final_status"] == "failed"
    assert model.calls.count("report_revision") == 1
    assert model.calls.count("report_revision_review") == 1
    final_gate = json.loads(
        (
            tmp_path
            / "artifacts/research_synthesis_v1/final/final_acceptance.json"
        ).read_text(encoding="utf-8")
    )
    assert final_gate["accepted"] is False
    assert final_gate["revision_applied"] is True
    assert "review verdict suggestion is revise" in final_gate["reasons"]
