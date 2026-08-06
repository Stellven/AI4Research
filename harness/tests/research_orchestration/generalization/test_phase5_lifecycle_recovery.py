from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest


HARNESS_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = HARNESS_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(HARNESS_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT / "lib"))

from harness.lib.research_orchestration.dispatch import dispatch_research_node  # noqa: E402
from harness.lib.research_orchestration.evaluator import evaluate_production_result  # noqa: E402
from harness.lib.research_orchestration.orchestrator import ResearchOrchestrator  # noqa: E402
from harness.lib.research_orchestration.routing import apply_task_conditions, select_production_route  # noqa: E402
from harness.lib.research_orchestration.runtime import (  # noqa: E402
    _complete_repository_inputs,
    _complete_seed_inputs,
    _git_checkout_provenance,
    build_task_contract,
    default_production_resolver,
)
from harness.lib.research_orchestration.runtime_lease import ResearchLeaseAdapter  # noqa: E402
from harness.lib.research_orchestration.selection import load_and_normalize_workflow  # noqa: E402
from harness.lib.research_orchestration.state_store import ResearchStateStore  # noqa: E402
from harness.plugins.autosci.operators.scientific_lifecycle.registry import registration_entries  # noqa: E402


FIXTURES = HARNESS_ROOT / "tests" / "research_orchestration" / "fixtures" / "phase5" / "lifecycle_recovery"
SAMPLE_PAPER = FIXTURES / "sample_paper.md"
SAMPLE_REPO = FIXTURES / "sample_repo"
IMPORTED_EVIDENCE = FIXTURES / "imported_evidence.json"
EXPERIMENT_SCRIPT = FIXTURES / "run_bounded_experiment.py"
RUN_ID = "phase5-lifecycle-recovery"
APPROVAL_REF = "phase5-test-approval-lifecycle-recovery-001"
SECRET_CANARY = "opaquePhase5LifecycleRecoveryCanary"
REQUEST_SCHEMA = HARNESS_ROOT / "schemas" / "draft" / "research_node_request.v1.schema.json"
RESULT_SCHEMA = HARNESS_ROOT / "schemas" / "evidence" / "research_node_result.v1.schema.json"
EXPERIMENT_RESULT_PATH = (
    "artifacts/scientific/scientific_research_lifecycle_full_v1/07_experiment_result/experiment_result.v1.json"
)
EXPERIMENT_STATUS_PATH = (
    "artifacts/scientific/scientific_research_lifecycle_full_v1/07_experiment_result/experiment_status.v1.json"
)


FULL_STAGE_NODES = [
    "evidence_import",
    "literature_discover",
    "paper_ingest",
    "material_ingest",
    "paper_analyze",
    "memory_update_initial",
    "graph_update",
    "claim_extract",
    "method_extract",
    "code_evidence_map",
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
    "memory_update_final",
    "workflow_evolve",
]


PROMPT = (
    "Run the complete scientific lifecycle for the local Solar Phase 5 study: "
    "discover and import sources, ingest the paper, analyze methods/results/limitations, "
    "map code evidence, generate and evaluate an idea, design and run a bounded experiment, "
    "verify claims, plan/draft/review/publish the report, perform final evaluation, and "
    "propose workflow evolution."
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_phase5_workflow(_decision: Any) -> dict[str, Any]:
    workflow = load_and_normalize_workflow(
        {
            "workflow_kind": "scientific_lifecycle",
            "workflow_id": "scientific_research_lifecycle_full_v1",
            "workflow_path": str(HARNESS_ROOT / "workflows" / "scientific_research_lifecycle_full_v1.json"),
            "start_node": "evidence_import",
        },
        HARNESS_ROOT,
        preserve_all_nodes=True,
    )
    workflow["workflow_kind"] = "scientific_lifecycle"
    workflow["start_node"] = "evidence_import"
    by_id = {node["node_id"]: node for node in workflow["nodes"]}
    idea_path = "artifacts/scientific/scientific_research_lifecycle_full_v1/05_ideas/idea_candidate.v1.json"
    by_id["experiment_design"]["read_scope"] = list(
        dict.fromkeys([*by_id["experiment_design"]["read_scope"], idea_path])
    )
    return workflow


def _authorization(*, approved: bool) -> dict[str, Any]:
    auth = {
        "allow_network": False,
        "allow_live_provider": False,
        "secret_values": [SECRET_CANARY],
    }
    if approved:
        auth["approval_ref"] = APPROVAL_REF
        auth["approved_capabilities"] = ["execute_experiment"]
    return auth


def _write_operator_registry(artifact_root: Path) -> None:
    operators = {
        str(item["physical_operator_id"]): {"enabled": True}
        for item in registration_entries()
    }
    path = artifact_root / "config" / "physical-operators.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "operators": operators}, indent=2, sort_keys=True), encoding="utf-8")


def _services(artifact_root: Path) -> dict[str, Any]:
    def discover_literature(**_kwargs: Any) -> dict[str, Any]:
        return {
            "status": "completed",
            "query": "Solar Phase 5 lifecycle recovery",
            "mode": "topic",
            "candidates": [
                {
                    "candidate_id": "phase5-local-study",
                    "title": "Solar Phase 5 Local Lifecycle Study",
                    "source_channels": ["fixture"],
                    "ranking_score": 1.0,
                    "dedup_status": "unique",
                    "fetch_status": "local_fixture",
                }
            ],
            "source_provider_boundary": "offline_fixture_provider",
        }

    def idea_generator(*, evidence: list[dict[str, Any]], constraints: dict[str, Any]) -> dict[str, Any]:
        evidence_ids = [
            str((item.get("provenance") or {}).get("artifact_id") or item.get("node_id") or "phase5-evidence")
            for item in evidence
        ] or ["phase5-evidence"]
        return {
            "ideas": [
                {
                    "idea_id": "idea-phase5-approval-hash",
                    "title": "Hash-bound approval improves lifecycle recovery",
                    "hypothesis": (
                        "Hash-bound approval and artifact verification reduce unsupported lifecycle claims "
                        "by at least 50 percent."
                    ),
                    "approach": "Run the deterministic local unsupported-claim-count experiment.",
                    "origin_evidence_ids": evidence_ids,
                    "risks": ["Small deterministic fixture limits external generalization."],
                    "falsifiability": "The hypothesis fails if reduction is below 50 percent.",
                    "validation_method": "Compare baseline and intervention unsupported claim counts.",
                    "minimum_experiment": "Run the local Python fixture and verify reduction >= 50 percent.",
                    "novelty_hypothesis": "Lifecycle recovery is evaluated as control-plane evidence.",
                }
            ],
            "limitations": ["Offline deterministic idea generation for lifecycle validation."],
            "provider": "fixture",
            "model": "none",
        }

    def experiment_executor(*, plan: dict[str, Any], sandbox: dict[str, Any], timeout_seconds: int, max_output_bytes: int) -> dict[str, Any]:
        raw_output = artifact_root / "experiment-runtime" / "raw_observations.json"
        completed = subprocess.run(
            [sys.executable, str(EXPERIMENT_SCRIPT), str(raw_output)],
            cwd=artifact_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr or completed.stdout or "local experiment failed")
        payload = _json(raw_output)
        raw_hash = _sha256(raw_output)
        reduction = float(payload["unsupported_claim_reduction_percent"])
        return {
            "outcome": "supports" if reduction >= 50.0 else "refutes",
            "metrics": [
                {"name": "baseline_unsupported_mean", "value": payload["baseline_mean"]},
                {"name": "intervention_unsupported_mean", "value": payload["intervention_mean"]},
                {"name": "unsupported_claim_reduction_percent", "value": reduction},
            ],
            "evidence_ids": [f"local-experiment:raw_observations:{raw_hash}"],
            "criteria_results": {
                "primary_outcome is recorded": True,
                "reduction_at_least_50_percent": reduction >= 50.0,
            },
            "limitations": [
                f"Local bounded experiment command: {Path(sys.executable).name} {EXPERIMENT_SCRIPT.name}",
                f"Raw observation artifact sha256={raw_hash}",
            ],
        }

    return {
        "discover_literature": discover_literature,
        "idea_generator": idea_generator,
        "experiment_executor": experiment_executor,
    }


class Phase5ProbeResolver:
    def __init__(
        self,
        artifact_root: Path,
        *,
        interrupt_node: str | None = None,
        recover_stale: bool = False,
    ) -> None:
        self.artifact_root = artifact_root.resolve()
        self.base = default_production_resolver(services=_services(self.artifact_root), workspace_root=self.artifact_root)
        self.adapter = ResearchLeaseAdapter(self.artifact_root, claim_timeout_seconds=2, abandoned_claim_seconds=1)
        self.interrupt_node = interrupt_node
        self.recover_stale = recover_stale
        self.requests: list[dict[str, Any]] = []
        self.results: list[dict[str, Any]] = []
        _write_operator_registry(self.artifact_root)

    def resolve(self, operator_id: str) -> Any:
        return self.base.resolve(operator_id)

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        request = deepcopy(request)
        node_id = str(request["node_id"])
        operator_id = str((request.get("physical_operator") or {}).get("operator_id") or f"{node_id}_worker")
        lease = self.adapter.acquire(
            request["run_id"],
            node_id,
            operator_id,
            ttl_seconds=1,
            heartbeat_timeout_seconds=1,
            recover_stale=self.recover_stale,
            metadata={"stage": node_id, "trace_id": "phase5-lifecycle-recovery"},
            secret_values=[SECRET_CANARY],
            safe_metadata_fields=["stage", "trace_id"],
        )
        if not lease.get("acquired"):
            raise RuntimeError(f"lease not acquired for {node_id}: {lease.get('blocker')}")
        heartbeat = self.adapter.heartbeat(
            request["run_id"],
            node_id,
            operator_id,
            lease_id=lease["lease"]["lease_id"],
            ttl_seconds=1,
            state="running",
            secret_values=[SECRET_CANARY],
        )
        self.requests.append(deepcopy(request))
        if self.interrupt_node == node_id:
            marker = self.artifact_root / "interrupt-marker.json"
            marker.write_text(
                json.dumps(
                    {
                        "run_id": request["run_id"],
                        "workflow_id": request["workflow_id"],
                        "node_id": node_id,
                        "operator_id": operator_id,
                        "lease": lease["lease"],
                        "heartbeat": heartbeat,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            os._exit(77)
        try:
            self._inject_phase5_inputs(request)
            result = self.base.execute(request)
            self.results.append(deepcopy(result))
            return result
        finally:
            self.adapter.release(
                request["run_id"],
                node_id,
                operator_id,
                lease_id=lease["lease"]["lease_id"],
                reason="completed",
                secret_values=[SECRET_CANARY],
            )

    def _inject_phase5_inputs(self, request: dict[str, Any]) -> None:
        payload = request["typed_inputs"]["payload"]
        task_contract = payload.get("task_contract") if isinstance(payload.get("task_contract"), dict) else {}
        seed = next(
            (
                item
                for item in task_contract.get("seed_inputs") or []
                if isinstance(item, dict) and item.get("seed_kind") == "markdown"
            ),
            {},
        )
        source = str(seed.get("value") or "")
        node_id = request["node_id"]
        if node_id == "evidence_import":
            imported = self.artifact_root / "inputs" / "phase5-imported-evidence.json"
            imported.parent.mkdir(parents=True, exist_ok=True)
            if not imported.exists():
                shutil.copyfile(IMPORTED_EVIDENCE, imported)
            payload.setdefault("task_contract", {})["supplied_evidence"] = [
                {
                    "artifact_id": "phase5-imported-source",
                    "path": imported.relative_to(self.artifact_root).as_posix(),
                    "sha256": _sha256(imported),
                    "provenance": {"source": "phase5-fixture-external-evidence", "captured_at": "2026-08-05T00:00:00Z"},
                }
            ]
        elif node_id == "literature_discover":
            payload["query"] = "Solar Phase 5 lifecycle recovery"
            payload["mode"] = "topic"
            payload["allow_network_fetch"] = False
        elif node_id in {"paper_ingest", "material_ingest"}:
            payload["source"] = source
            payload["material_path"] = source
            payload["allow_network_fetch"] = False


def _prepare_artifact_root(artifact_root: Path) -> None:
    artifact_root.mkdir(parents=True, exist_ok=True)
    dispatch_envelope = artifact_root / "dispatch" / "envelope.json"
    dispatch_envelope.parent.mkdir(parents=True, exist_ok=True)
    dispatch_envelope.write_text(
        json.dumps(
            {
                "schema": "phase5.dispatch_envelope.v1",
                "run_id": RUN_ID,
                "workflow_id": "scientific_research_lifecycle_full_v1",
                "seed": "Solar Phase 5 lifecycle recovery",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _runtime(
    artifact_root: Path,
    *,
    approved: bool,
    interrupt_node: str | None = None,
    recover_stale: bool = False,
) -> tuple[ResearchOrchestrator, Phase5ProbeResolver]:
    _prepare_artifact_root(artifact_root)
    resolver = Phase5ProbeResolver(artifact_root, interrupt_node=interrupt_node, recover_stale=recover_stale)
    return _orchestrator(artifact_root, resolver, approved=approved), resolver


def _run_runtime(artifact_root: Path, *, run_id: str = RUN_ID, approved: bool = True, max_steps: int = 100) -> tuple[dict[str, Any], Phase5ProbeResolver]:
    orchestrator, resolver = _runtime(artifact_root, approved=approved)
    state = orchestrator.run_until_blocked(max_steps=max_steps)
    result = {
        "schema": "solar_research_runtime_result.v1",
        "run_id": run_id,
        "workflow_id": state["workflow_id"],
        "final_status": state["final_status"],
        "node_states": deepcopy(state["node_states"]),
        "current_blockers": deepcopy(state["current_blockers"]),
        "state_path": str(artifact_root / "state" / f"{run_id}.research_run_state.json"),
    }
    return result, resolver


def _task_and_workflow(artifact_root: Path, *, run_id: str = RUN_ID) -> tuple[dict[str, Any], dict[str, Any]]:
    seeds = _complete_seed_inputs(
        PROMPT,
        [{"seed_kind": "markdown", "value": str(SAMPLE_PAPER)}],
        artifact_root=artifact_root,
        run_id=run_id,
    )
    repositories = _complete_repository_inputs([str(SAMPLE_REPO)], artifact_root=artifact_root, run_id=run_id)
    decision = select_production_route(
        PROMPT,
        seed_inputs=seeds,
        explicit_workflow="scientific_lifecycle",
        run_mode="execute",
    )
    configured = _load_phase5_workflow(decision)
    workflow_identity = {
        "workflow_id": configured["workflow_id"],
        "workflow_version": configured.get("version", 1),
        "workflow_kind": "scientific_lifecycle",
    }
    task_contract = build_task_contract(
        prompt=PROMPT,
        run_id=run_id,
        decision=decision,
        seed_inputs=seeds,
        repository_inputs=repositories,
        workflow_identity=workflow_identity,
        run_provenance=_git_checkout_provenance(REPO_ROOT),
    )
    workflow = apply_task_conditions(configured, task_contract)
    return task_contract, workflow


def _orchestrator(
    artifact_root: Path,
    resolver: Phase5ProbeResolver,
    *,
    run_id: str = RUN_ID,
    approved: bool = True,
) -> ResearchOrchestrator:
    task_contract, workflow = _task_and_workflow(artifact_root, run_id=run_id)
    auth = _authorization(approved=approved)
    approved_capabilities = set(auth.get("approved_capabilities") or [])
    approved_capabilities.update(
        capability
        for node in workflow["nodes"]
        for capability in node.get("required_capabilities") or []
        if capability != "execute_experiment"
    )
    auth["approved_capabilities"] = sorted(approved_capabilities)

    def dispatch(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_research_node(
            request,
            runner=resolver.execute,
            request_schema_path=REQUEST_SCHEMA,
            result_schema_path=RESULT_SCHEMA,
            artifact_root=artifact_root,
            operator_resolver=resolver.resolve,
            secret_values=[SECRET_CANARY],
        )

    def evaluator(request: dict[str, Any], result: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return evaluate_production_result(request, result, state, artifact_root=artifact_root)

    return ResearchOrchestrator(
        task_contract=task_contract,
        workflow_selector=workflow,
        state_store=ResearchStateStore(artifact_root / "state"),
        dispatch_callable=dispatch,
        evaluator_callable=evaluator,
        authorization=auth,
        artifact_root=artifact_root,
    )


def _state(artifact_root: Path, run_id: str = RUN_ID) -> dict[str, Any]:
    return _json(artifact_root / "state" / f"{run_id}.research_run_state.json")


def _node_record(state: dict[str, Any], node_id: str) -> dict[str, Any]:
    return _json(Path(state["node_states"][node_id]["result_ref"]))


def _completed_artifact_snapshot(artifact_root: Path, state: dict[str, Any]) -> dict[str, dict[str, str]]:
    snapshot: dict[str, dict[str, str]] = {}
    for node_id, node_state in state["node_states"].items():
        if node_state["status"] != "completed":
            continue
        record = _node_record(state, node_id)
        artifacts = {}
        for artifact in record["result"]["output_artifacts"]:
            path = artifact_root / artifact["path"]
            artifacts[artifact["path"]] = _sha256(path)
            assert artifact["sha256"] == artifacts[artifact["path"]]
        snapshot[node_id] = artifacts
    return snapshot


def _assert_snapshot_unchanged(artifact_root: Path, snapshot: dict[str, dict[str, str]]) -> None:
    for artifacts in snapshot.values():
        for relative_path, expected_hash in artifacts.items():
            assert _sha256(artifact_root / relative_path) == expected_hash


def _assert_no_secret_persisted(artifact_root: Path) -> None:
    for path in artifact_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".json", ".jsonl", ".md", ".txt"}:
            assert SECRET_CANARY not in path.read_text(encoding="utf-8", errors="ignore"), path


def _assert_production_lifecycle_contract(artifact_root: Path) -> None:
    _task_contract, workflow = _task_and_workflow(artifact_root)
    by_id = {node["node_id"]: node for node in workflow["nodes"]}
    claim_node = by_id["claim_verify"]
    approval_node = by_id["experiment_approval_gate"]

    assert "experiment_monitor" in claim_node.get("depends_on", [])
    assert EXPERIMENT_STATUS_PATH in claim_node.get("read_scope", [])
    assert EXPERIMENT_RESULT_PATH in claim_node.get("read_scope", [])
    assert EXPERIMENT_RESULT_PATH in approval_node.get("write_scope", [])


def _copy_run_tree(source_root: Path, target_root: Path) -> None:
    shutil.copytree(source_root, target_root)
    state_path = target_root / "state" / f"{RUN_ID}.research_run_state.json"
    state = _json(state_path)
    source_text = str(source_root.resolve())
    target_text = str(target_root.resolve())
    for node_state in state["node_states"].values():
        ref = str(node_state.get("result_ref") or "")
        if ref:
            node_state["result_ref"] = ref.replace(source_text, target_text)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_phase5_complete_scientific_lifecycle_runs_with_real_experiment_and_final_evaluation(tmp_path: Path) -> None:
    artifact_root = tmp_path / "complete"
    result, resolver = _run_runtime(artifact_root)
    _assert_production_lifecycle_contract(artifact_root)

    assert result["final_status"] == "completed"
    assert result["workflow_id"] == "scientific_research_lifecycle_full_v1"
    dispatched = [request["node_id"] for request in resolver.requests]
    assert sorted(dispatched) == sorted(FULL_STAGE_NODES)
    assert len(dispatched) == len(set(dispatched)) == len(FULL_STAGE_NODES)
    state = _state(artifact_root)
    assert all(state["node_states"][node_id]["status"] == "completed" for node_id in FULL_STAGE_NODES)

    imported = _json(
        artifact_root
        / "artifacts/scientific/scientific_research_lifecycle_full_v1/01_paper/research_evidence_import.v1.json"
    )
    assert imported["outputs"]["imported_count"] == 1
    assert "not accepted without downstream evaluation" in " ".join(imported["limitations"])

    experiment = _json(
        artifact_root
        / "artifacts/scientific/scientific_research_lifecycle_full_v1/07_experiment_result/experiment_result.v1.json"
    )
    plan = _json(
        artifact_root
        / "artifacts/scientific/scientific_research_lifecycle_full_v1/06_experiment_plan/experiment_plan.v1.json"
    )["outputs"]["experiment_plan"]
    approval = _json(
        artifact_root
        / "artifacts/scientific/scientific_research_lifecycle_full_v1/06_experiment_plan/experiment_approval.v1.json"
    )["outputs"]["approval"]
    experiment_result = experiment["outputs"]["result"]
    assert plan["sandbox"]["mode"] == "isolated"
    assert plan["sandbox"]["network"] is False
    assert plan["sandbox"]["write_scope"] == [EXPERIMENT_RESULT_PATH]
    assert approval["decision"] == "approved"
    assert approval["sandbox"]["write_scope"] == plan["sandbox"]["write_scope"]
    assert approval["plan_sha256"] == experiment_result["plan_sha256"]
    assert experiment_result["approval_ref"] == APPROVAL_REF
    assert experiment_result["sandbox_enforced"] is True
    assert any(item["name"] == "unsupported_claim_reduction_percent" and item["value"] >= 50 for item in experiment_result["metrics"])
    raw_observations = artifact_root / "experiment-runtime" / "raw_observations.json"
    assert raw_observations.is_file()
    assert _json(raw_observations)["supports_minimum_reduction"] is True

    verdict = _json(
        artifact_root
        / "artifacts/scientific/scientific_research_lifecycle_full_v1/08_verdict/claim_verdict.v1.json"
    )
    assert any("local-experiment:raw_observations:" in " ".join(item["evidence_ids"]) for item in verdict["outputs"]["verdicts"])

    report = (
        artifact_root
        / "artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/final-report.md"
    ).read_text(encoding="utf-8")
    assert "## Methods" in report
    assert "reduces unsupported claim counts by at least 50 percent" in report
    assert "local-experiment:raw_observations:" in report

    final_evaluation = _json(
        artifact_root
        / "artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/research_final_evaluation.v1.json"
    )
    evaluation = final_evaluation["outputs"]["evaluation"]
    assert evaluation["accepted"] is True
    assert evaluation["source_report_id"] == "scientific-report"
    assert evaluation["checks"]["core_result_claims_present"] is True
    assert evaluation["checks"]["method_evidence_honestly_rendered"] is True

    _completed_artifact_snapshot(artifact_root, state)
    _assert_no_secret_persisted(artifact_root)


def test_phase5_no_approval_does_not_execute_experiment(tmp_path: Path) -> None:
    artifact_root = tmp_path / "no-approval"
    result, resolver = _run_runtime(artifact_root, approved=False, max_steps=30)

    assert result["final_status"] == "awaiting_human"
    assert result["current_blockers"][0]["node_id"] == "experiment_approval_gate"
    dispatched = [request["node_id"] for request in resolver.requests]
    assert "experiment_design" in dispatched
    assert "experiment_approval_gate" not in dispatched
    assert "experiment_run" not in dispatched
    plan = _json(
        artifact_root
        / "artifacts/scientific/scientific_research_lifecycle_full_v1/06_experiment_plan/experiment_plan.v1.json"
    )["outputs"]["experiment_plan"]
    assert plan["sandbox"]["mode"] == "isolated"
    assert plan["sandbox"]["network"] is False
    assert plan["sandbox"]["write_scope"] == [EXPERIMENT_RESULT_PATH]
    assert not (artifact_root / "experiment-runtime" / "raw_observations.json").exists()


def test_phase5_interruption_resume_preserves_artifacts_and_continues_only_unfinished(tmp_path: Path) -> None:
    artifact_root = tmp_path / "interrupted"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT), str(HARNESS_ROOT / "lib"), env.get("PYTHONPATH", "")])
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--phase5-interrupt", str(artifact_root)],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = process.communicate(timeout=60)
    assert process.returncode == 77, (stdout, stderr)

    marker = _json(artifact_root / "interrupt-marker.json")
    interrupted_state = _state(artifact_root)
    assert marker["run_id"] == RUN_ID
    assert marker["workflow_id"] == "scientific_research_lifecycle_full_v1"
    assert marker["node_id"] == "experiment_run"
    assert interrupted_state["final_status"] != "completed"
    assert interrupted_state["node_states"]["experiment_run"]["status"] == "running"
    assert (artifact_root / "run" / "operator-status" / "experiment_run_worker.json").is_file()
    completed_before = {
        node_id
        for node_id, node_state in interrupted_state["node_states"].items()
        if node_state["status"] == "completed"
    }
    snapshot = _completed_artifact_snapshot(artifact_root, interrupted_state)
    assert "experiment_approval_gate" in completed_before
    assert "experiment_run" not in completed_before

    time.sleep(1.2)
    resolver = Phase5ProbeResolver(artifact_root, recover_stale=True)
    orchestrator = _orchestrator(artifact_root, resolver)
    resumed_once = orchestrator.resume(redispatch_node_id="experiment_run")
    final_state = resumed_once if resumed_once["final_status"] == "completed" else orchestrator.run_until_blocked(max_steps=80)

    assert final_state["final_status"] == "completed"
    assert final_state["run_id"] == RUN_ID
    assert final_state["workflow_id"] == "scientific_research_lifecycle_full_v1"
    resumed_nodes = [request["node_id"] for request in resolver.requests]
    assert resumed_nodes[0] == "experiment_run"
    assert completed_before.isdisjoint(resumed_nodes)
    _assert_snapshot_unchanged(artifact_root, snapshot)
    assert not list((artifact_root / "run" / "operator-leases").glob("*.json"))
    assert list((artifact_root / "run" / "operator-leases" / "archive").glob("*.json"))

    repeat_resolver = Phase5ProbeResolver(artifact_root, recover_stale=True)
    repeat = _orchestrator(artifact_root, repeat_resolver).resume()
    assert repeat["final_status"] == "completed"
    assert repeat_resolver.requests == []
    _assert_no_secret_persisted(artifact_root)


def test_phase5_tampered_resume_state_or_foreign_evidence_is_rejected(tmp_path: Path) -> None:
    base_root = tmp_path / "base"
    result, _resolver = _run_runtime(base_root)
    assert result["final_status"] == "completed"

    tampered_root = tmp_path / "tampered-hash"
    _copy_run_tree(base_root, tampered_root)
    report_path = (
        tampered_root
        / "artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/scientific_report.v1.json"
    )
    report_path.write_text(report_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    tampered = _orchestrator(tampered_root, Phase5ProbeResolver(tampered_root)).resume()
    assert tampered["final_status"] == "blocked"
    assert "sha256" in tampered["current_blockers"][0]["reason"]

    foreign_root = tmp_path / "foreign-run"
    _copy_run_tree(base_root, foreign_root)
    store = ResearchStateStore(foreign_root / "state")
    state = _state(foreign_root)
    original = _node_record(state, "paper_analyze")
    foreign_ref = store.store_node_record(
        run_id="foreign-phase5-run",
        node_id="paper_analyze",
        result=original["result"],
        evaluation=original["evaluation"],
    )
    state["node_states"]["paper_analyze"]["result_ref"] = foreign_ref
    (foreign_root / "state" / f"{RUN_ID}.research_run_state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    foreign = _orchestrator(foreign_root, Phase5ProbeResolver(foreign_root)).resume()
    assert foreign["final_status"] == "blocked"
    assert "run_id does not match" in foreign["current_blockers"][0]["reason"]


def _run_interrupting_lifecycle(artifact_root: Path) -> None:
    orchestrator, _resolver = _runtime(artifact_root, approved=True, interrupt_node="experiment_run")
    orchestrator.run_until_blocked(max_steps=80)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--phase5-interrupt":
        _run_interrupting_lifecycle(Path(sys.argv[2]))
        raise SystemExit("interrupt node was not reached")
    raise SystemExit("unsupported direct invocation")
