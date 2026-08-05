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
