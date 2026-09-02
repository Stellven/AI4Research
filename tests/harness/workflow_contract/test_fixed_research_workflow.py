"""Deterministic contract tests for the fixed evidence-to-PoC intake.

The generated source pack is intentionally local test data.  These tests prove
contract, authority, and command-boundary behavior; they do not claim a live
provider or real-world research result.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HARNESS = Path(__file__).resolve().parents[3] / "harness"
LIB = HARNESS / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import fixed_research_workflow as fr  # noqa: E402
import workflow_intake as wi  # noqa: E402


def _symlink_or_skip(link: Path, target: Path, *, target_is_directory: bool = False) -> None:
    """Create a symlink or skip when Windows developer-mode privilege is absent."""
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege is unavailable")
        raise
from apo_plan_compiler import compile_execution_plan_for_node  # noqa: E402
from harness.plugins.autosci.services import codex_research as cr  # noqa: E402
from harness.plugins.autosci.services.codex_research import (  # noqa: E402
    CODEX_RESEARCH_SERVICE_ID,
    CodexResearchModelService,
    _response_schema,
)
from harness.plugins.autosci.services.production_research import ResearchOperatorError  # noqa: E402
from harness.plugins.autosci.bin import fixed_research_node_adapter as fixed_adapter  # noqa: E402
from harness.plugins.autosci.operators.research_synthesis import report_revision as revision_operator  # noqa: E402

_GND_SPEC = importlib.util.spec_from_file_location("fixed_test_graph_node_dispatcher", LIB / "graph_node_dispatcher.py")
assert _GND_SPEC and _GND_SPEC.loader
gnd = importlib.util.module_from_spec(_GND_SPEC)
_GND_SPEC.loader.exec_module(gnd)
gs = sys.modules["graph_scheduler"]
import operator_runtime as opr  # noqa: E402


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_fixed_adapter_api_service_adds_role_and_session_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeApiService:
        service_id = "fake-api-service"
        service_version = "1"
        routes = [SimpleNamespace(provider="openrouter")]

        def __call__(self, **_kwargs: object) -> dict[str, object]:
            return {
                "provider_usage": [{
                    "provider": "openrouter",
                    "request_sha256": "a" * 64,
                    "response_sha256": "b" * 64,
                }]
            }

    monkeypatch.setenv("SOLAR_RESEARCH_MODEL_PROVIDER", "openrouter")
    monkeypatch.setenv("AUTOSCI_RESEARCH_LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(
        fixed_adapter.ResearchModelService,
        "from_environment",
        lambda _root: FakeApiService(),
    )

    services = fixed_adapter._codex_services(node_id="report_draft", stage_dir=tmp_path)
    result = services["model_generate"](node_id="report_draft")
    usage = result["provider_usage"][0]
    assert usage["provider"] == "openrouter"
    assert usage["principal_role"] == "writer"
    assert usage["session_mode"] == "ephemeral"
    assert usage["status"] == "completed"
    fixed_adapter._verify_model_usage(
        node_id="report_draft",
        result={"model_provider_usage": [usage]},
    )


def _pack(root: Path, *, fact: str = "UNIQUE_SENTINEL_FACT_7319") -> Path:
    pack = root / "pack"
    extracts = pack / "extracts"
    extracts.mkdir(parents=True)
    content = f"Method: bounded retrieval. Result: {fact}. Limitation: one local contract source."
    data = content.encode("utf-8")
    (extracts / "s1.txt").write_bytes(data)
    source = {
        "source_id": "s1",
        "title": "Deterministic contract source",
        "url": "https://example.invalid/source/s1",
        "provider": "preselected_test_source",
        "extract_path": "extracts/s1.txt",
        "content_sha256": _sha(data),
    }
    evidence = {
        "evidence_id": "e1",
        "source_id": "s1",
        "content": content,
        "content_hash": _sha(data),
    }
    (pack / "sources.jsonl").write_text(json.dumps(source) + "\n", encoding="utf-8")
    (pack / "evidence.jsonl").write_text(json.dumps(evidence) + "\n", encoding="utf-8")
    return pack


def _graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    execution_profile: str = "part_a_only",
    sid: str = "fixed-contract-test",
    experiment_policy: str = "",
) -> tuple[dict, Path, Path]:
    sprints = tmp_path / "sprints"
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)
    pack = _pack(tmp_path / "authority")
    graph = fr.build_fixed_research_graph(
        sprint_id=sid,
        request="Research a bounded deterministic topic and produce an evidence-linked report.",
        execution_profile=execution_profile,
        acquisition_mode="source_pack",
        source_pack_root=pack,
        authority_root=pack.parent,
        snapshot_root=sprints / sid / "workdir" / "inputs" / "source-pack",
        experiment_policy=experiment_policy,
        experiment_policy_actor="user" if experiment_policy else "",
        experiment_policy_statement="no need to pause at B4 no pauses" if experiment_policy else "",
    )
    intents = tmp_path / "intents"
    binding = intents / "fixed-test-intent" / "binding.json"
    binding.parent.mkdir(parents=True)
    binding.write_text(json.dumps({
        "ok": True,
        "intent_id": "fixed-test-intent",
        "sprint_id": sid,
        "artifacts": {},
    }) + "\n", encoding="utf-8")
    monkeypatch.setenv("SOLAR_INTENT_GATEWAY_DIR", str(intents))
    graph["intent_binding"] = {
        "required": True,
        "status": "bound",
        "intent_id": "fixed-test-intent",
        "manifest": str(binding),
    }
    graph["workflow_contract_hash"] = fr.wc.graph_contract_hash(graph)
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    return graph, graph_path, sprints


def _invoke_adapter(envelope: dict, root: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    envelope_path = root / f"{envelope['node_id']}-envelope.json"
    envelope_path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    run_env = dict(os.environ)
    run_env.update(env or {})
    return subprocess.run(
        [
            sys.executable,
            str(HARNESS / "plugins" / "autosci" / "bin" / "fixed_research_node_adapter.py"),
            "--envelope",
            str(envelope_path),
        ],
        cwd=HARNESS.parent,
        env=run_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _seed_controller_accepted_part_a_precondition(
    graph: dict,
    graph_path: Path,
    sprints: Path,
) -> dict:
    """Seed an evaluator/ledger-accepted Part-A precondition for Part-B tests.

    The payloads are deliberately minimal contract-test inputs.  This helper
    does not claim Part-A research quality; it exercises the real manifest,
    snapshot, evaluator-record, scheduler, and closeout authority that Part B
    is required to consume.
    """
    sid = str(graph["sprint_id"])
    for node_id in fr.PART_A_NODE_IDS:
        node = next(item for item in graph["nodes"] if item["id"] == node_id)
        for index, output in enumerate(node["outputs"]):
            output_path, _relative = gnd._fixed_research_relative_path(
                str(output["path"]), sid, label=f"{node_id} test boundary output"
            )
            if str(output.get("type") or "") == "directory":
                output_path.mkdir(parents=True, exist_ok=True)
                continue
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.suffix == ".json":
                payload = {
                    "schema": fr.EXPECTED_SCHEMA_BY_NODE[node_id],
                    "status": "completed",
                    "node_id": node_id,
                    "limitations": ["Deterministic Part-A authority precondition for a Part-B runtime test."],
                }
                if node_id == "final_acceptance":
                    payload.update({"accepted": True, "decision": "accepted", "gate_outcome": "pass"})
                output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            else:
                output_path.write_text(
                    f"# {node_id}\n\nDeterministic Part-A authority precondition.\n",
                    encoding="utf-8",
                )

    for node_id in fr.PART_A_NODE_IDS:
        node = next(item for item in graph["nodes"] if item["id"] == node_id)
        node["status"] = "reviewing"
        graph.setdefault("node_results", {})[node_id] = {"status": "reviewing"}
        gnd.save_graph(graph_path, graph)
        gnd._emit_node_proof_sidecars(sid, node)
        snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)
        assert snapshot["ok"] is True, snapshot
        eval_path = sprints / f"{sid}.{node_id}-eval.json"
        eval_path.write_text(
            json.dumps(
                {
                    "node_id": node_id,
                    "verdict": "PASS",
                    "generation_mode": "independent_evaluator",
                    "artifact_snapshot_schema": snapshot["schema"],
                    "artifact_snapshot_path": snapshot["path"],
                    "artifact_snapshot_digest": snapshot["snapshot_digest"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        closed = gnd._finalize_node_pass(
            sid,
            node,
            graph,
            eval_json=eval_path,
            reason="deterministic_part_a_authority_precondition",
            verdict_kind="mechanical",
        )
        assert closed["ok"] is True, closed
        assert closed["closeout_receipt"]["eval"]["consumable"] is True
        assert closed["closeout_receipt"]["manifest"]["ok"] is True
        gnd.save_graph(graph_path, graph)
    return graph


def test_source_pack_binds_actual_extract_content_and_rejects_tamper(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    authority = fr.validate_source_pack(pack, authority_root=tmp_path)
    assert "UNIQUE_SENTINEL_FACT_7319" in authority["candidates"][0]["content_summary"]
    (pack / "extracts" / "s1.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(fr.FixedResearchContractError, match="hash mismatch"):
        fr.validate_source_pack(pack, authority_root=tmp_path)


def test_source_pack_rejects_parent_symlink_and_relative_escape(tmp_path: Path) -> None:
    real = _pack(tmp_path / "authority" / "real")
    link = tmp_path / "authority" / "linked"
    _symlink_or_skip(link, real.parent, target_is_directory=True)
    with pytest.raises(fr.FixedResearchContractError, match="symlink"):
        fr.validate_source_pack(link / "pack", authority_root=tmp_path / "authority")
    with pytest.raises(fr.FixedResearchContractError, match="escapes"):
        fr.validate_source_pack("../real/pack", authority_root=tmp_path / "authority")

    index_pack = _pack(tmp_path / "index-link")
    index_target = tmp_path / "index-link" / "sources-real.jsonl"
    (index_pack / "sources.jsonl").replace(index_target)
    _symlink_or_skip(index_pack / "sources.jsonl", index_target)
    with pytest.raises(fr.FixedResearchContractError, match="symlink"):
        fr.validate_source_pack(index_pack, authority_root=index_pack.parent)

    extract_pack = _pack(tmp_path / "extract-link")
    extract_target = tmp_path / "extract-link" / "extract-real.txt"
    (extract_pack / "extracts" / "s1.txt").replace(extract_target)
    _symlink_or_skip(extract_pack / "extracts" / "s1.txt", extract_target)
    with pytest.raises(fr.FixedResearchContractError, match="symlink"):
        fr.validate_source_pack(extract_pack, authority_root=extract_pack.parent)


def test_fixed_benchmark_inputs_accept_canonical_workdir_paths_without_widening_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid = "fixed-benchmark-path-normalization"
    sprints = tmp_path / "sprints"
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    work_dir = sprints / sid / "workdir"
    target = work_dir / "artifacts/research_evidence_to_poc/final/final_acceptance.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"schema":"research_synthesis.final_acceptance.v1"}\n', encoding="utf-8")

    canonical, canonical_relative = gnd._fixed_research_relative_path(
        "artifacts/research_evidence_to_poc/final/final_acceptance.json",
        sid,
        label="benchmark input",
    )
    graph_prefixed, graph_relative = gnd._fixed_research_relative_path(
        f"sprints/{sid}/workdir/artifacts/research_evidence_to_poc/final/final_acceptance.json",
        sid,
        label="benchmark input",
    )
    assert canonical == graph_prefixed == target.resolve()
    assert canonical_relative == graph_relative == (
        "artifacts/research_evidence_to_poc/final/final_acceptance.json"
    )
    assert _sha(canonical.read_bytes()) == _sha(graph_prefixed.read_bytes())

    with pytest.raises(ValueError, match="workdir-relative"):
        gnd._fixed_research_relative_path(target, sid, label="benchmark input")
    with pytest.raises(ValueError, match="contained"):
        gnd._fixed_research_relative_path(
            "artifacts/../../outside.json", sid, label="benchmark input"
        )
    with pytest.raises(ValueError, match="wrong fixed sprint prefix"):
        gnd._fixed_research_relative_path(
            "sprints/another-run/workdir/artifacts/result.json",
            sid,
            label="benchmark input",
        )

    outside = tmp_path / "outside.json"
    outside.write_text("outside\n", encoding="utf-8")
    link = work_dir / "artifacts/external-link.json"
    link.parent.mkdir(parents=True, exist_ok=True)
    _symlink_or_skip(link, outside)
    with pytest.raises(ValueError, match="escapes"):
        gnd._fixed_research_relative_path(
            "artifacts/external-link.json", sid, label="benchmark input"
        )


def test_adapter_consumes_frozen_source_snapshot_and_rejects_snapshot_tamper(tmp_path: Path) -> None:
    sid = "source-pack-toctou"
    work_dir = tmp_path / "workdir"
    work_dir.mkdir()
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text("{}\n", encoding="utf-8")
    external_pack = _pack(tmp_path / "external", fact="FROZEN_SENTINEL_FACT_9821")
    external_authority = fr.validate_source_pack(external_pack, authority_root=external_pack.parent)
    snapshot = fr.snapshot_source_pack(external_authority, work_dir / "inputs" / "source-pack")

    seed_stage = "artifacts/research_evidence_to_poc/seed"
    seed_envelope = {
        "task_id": "toctou-a1",
        "sprint_id": sid,
        "node_id": "seed_fetch",
        "operator_id": fr.PHYSICAL_OPERATOR_BY_NODE["seed_fetch"],
        "runner_contract": fr.WORKFLOW_ID,
        "graph_path": str(graph_path),
        "handoff_path": str(tmp_path / f"{sid}.seed_fetch-handoff.md"),
        "work_dir": str(work_dir),
        "inputs": {
            "logical_operator": "ResearchSeedFetcher",
            "expected_schema": fr.EXPECTED_SCHEMA_BY_NODE["seed_fetch"],
            "declared_outputs": [
                {"path": seed_stage, "type": "directory"},
                {"path": f"{seed_stage}/seed_snapshot.json", "type": "json"},
            ],
            "dependency_artifacts": [],
            "source_pack_manifest": snapshot,
            "operator_payload": {"request": "Research the frozen source-pack fact."},
        },
        "outputs": {"result_path": f"{seed_stage}/research_node_result.json"},
        "lease_ttl_seconds": 30,
    }
    seed_run = _invoke_adapter(seed_envelope, tmp_path)
    assert seed_run.returncode == 0, (seed_run.stdout, seed_run.stderr)
    seed_path = work_dir / seed_stage / "seed_snapshot.json"

    # Changing the mutable external source after import cannot change the
    # adapter's input; A2 consumes only the Solar-owned snapshot manifest.
    (external_pack / "extracts" / "s1.txt").write_text("external mutation", encoding="utf-8")
    discovery_stage = "artifacts/research_evidence_to_poc/discovery"
    discovery_envelope = {
        "task_id": "toctou-a2",
        "sprint_id": sid,
        "node_id": "source_discovery",
        "operator_id": fr.PHYSICAL_OPERATOR_BY_NODE["source_discovery"],
        "runner_contract": fr.WORKFLOW_ID,
        "graph_path": str(graph_path),
        "handoff_path": str(tmp_path / f"{sid}.source_discovery-handoff.md"),
        "work_dir": str(work_dir),
        "inputs": {
            "logical_operator": "ResearchSourceDiscovery",
            "expected_schema": fr.EXPECTED_SCHEMA_BY_NODE["source_discovery"],
            "declared_outputs": [
                {"path": discovery_stage, "type": "directory"},
                {"path": f"{discovery_stage}/source_discovery.json", "type": "json"},
            ],
            "dependency_artifacts": [{
                "artifact_id": "seed_fetch",
                "path": str(seed_path.relative_to(work_dir)),
                "schema": fr.EXPECTED_SCHEMA_BY_NODE["seed_fetch"],
                "sha256": _sha(seed_path.read_bytes()),
            }],
            "source_pack_manifest": snapshot,
            "operator_payload": {"request": "Research the frozen source-pack fact."},
        },
        "outputs": {"result_path": f"{discovery_stage}/research_node_result.json"},
        "lease_ttl_seconds": 30,
    }
    discovery_run = _invoke_adapter(discovery_envelope, tmp_path)
    assert discovery_run.returncode == 0, (discovery_run.stdout, discovery_run.stderr)
    discovery_path = work_dir / discovery_stage / "source_discovery.json"
    discovery_before = discovery_path.read_bytes()
    assert b"FROZEN_SENTINEL_FACT_9821" in discovery_before
    assert b"external mutation" not in discovery_before

    validation_stage = "artifacts/research_evidence_to_poc/validation"
    validation_envelope = {
        "task_id": "toctou-a3",
        "sprint_id": sid,
        "node_id": "source_validation",
        "operator_id": fr.PHYSICAL_OPERATOR_BY_NODE["source_validation"],
        "runner_contract": fr.WORKFLOW_ID,
        "graph_path": str(graph_path),
        "handoff_path": str(tmp_path / f"{sid}.source_validation-handoff.md"),
        "work_dir": str(work_dir),
        "inputs": {
            "logical_operator": "ResearchSourceValidator",
            "expected_schema": fr.EXPECTED_SCHEMA_BY_NODE["source_validation"],
            "declared_outputs": [
                {"path": validation_stage, "type": "directory"},
                {"path": f"{validation_stage}/source_validation.json", "type": "json"},
            ],
            "dependency_artifacts": [{
                "artifact_id": "source_discovery",
                "path": str(discovery_path.relative_to(work_dir)),
                "schema": fr.EXPECTED_SCHEMA_BY_NODE["source_discovery"],
                "sha256": _sha(discovery_before),
            }],
            "source_pack_manifest": snapshot,
            "operator_payload": {"request": "Research the frozen source-pack fact."},
        },
        "outputs": {"result_path": f"{validation_stage}/research_node_result.json"},
        "lease_ttl_seconds": 30,
    }
    validation_run = _invoke_adapter(validation_envelope, tmp_path)
    assert validation_run.returncode == 0, (validation_run.stdout, validation_run.stderr)
    validation_path = work_dir / validation_stage / "source_validation.json"
    assert b"FROZEN_SENTINEL_FACT_9821" in validation_path.read_bytes()

    (work_dir / "inputs/source-pack/extracts/s1.txt").write_text("snapshot mutation", encoding="utf-8")
    tampered = _invoke_adapter(discovery_envelope, tmp_path)
    assert tampered.returncode == 2
    assert "hash mismatch" in json.loads(tampered.stdout)["error"]
    assert discovery_path.read_bytes() == discovery_before


def test_fixed_graph_part_a_only_keeps_part_b_visible_but_not_dispatchable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph, _graph_path, _sprints = _graph(tmp_path, monkeypatch)
    ids = [node["id"] for node in graph["nodes"]]
    assert ids == [*fr.PART_A_NODE_IDS, *fr.PART_B_NODE_IDS]
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert all(nodes[node_id]["status"] == "skipped" for node_id in fr.PART_B_NODE_IDS)
    assert all(nodes[node_id]["condition_status"] == "not_applicable" for node_id in fr.PART_B_NODE_IDS)
    assert not any(nodes[node_id].get("required_operator_id") for node_id in fr.PART_B_NODE_IDS)
    assert all(nodes[node_id]["status"] == "pending" for node_id in fr.PART_A_NODE_IDS)
    assert nodes["evidence_synthesis"]["required_operator_id"] == "codex-research-evidence-synthesis-worker"
    assert nodes["independent_review"]["required_operator_id"] == "codex-research-independent-review-worker"
    assert graph["codex_execution"] == {
        "mode": "fresh_context_per_node",
        "structured_response": True,
        "ambient_api_keys_allowed": False,
        "max_parallel": 1,
    }
    assert gnd._fixed_research_retrieval_policy_valid(graph) is True
    assert {worker["operator_id"] for worker in gnd._fixed_research_operator_workers(graph)} == {
        fr.PHYSICAL_OPERATOR_BY_NODE["seed_fetch"]
    }
    registry = json.loads((HARNESS / "config" / "physical-operators.json").read_text(encoding="utf-8"))
    registered_fixed = {
        operator_id
        for operator_id in registry["operators"]
        if operator_id in set(fr.PHYSICAL_OPERATOR_BY_NODE.values())
    }
    assert registered_fixed == {
        fr.PHYSICAL_OPERATOR_BY_NODE[node_id]
        for node_id in fr.DISPATCHABLE_NODE_IDS
    }


@pytest.mark.parametrize("mode,with_pack", [("live_search", False), ("hybrid", True)])
def test_fixed_graph_binds_controller_public_retrieval_only_to_a2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    with_pack: bool,
) -> None:
    sprints = tmp_path / "sprints"
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    sid = f"fixed-{mode}"
    pack = _pack(tmp_path / "authority") if with_pack else None
    work_dir = sprints / sid / "workdir"
    graph = fr.build_fixed_research_graph(
        sprint_id=sid,
        request="Research retrieval augmented generation evaluation methods.",
        execution_profile="part_a_only",
        acquisition_mode=mode,
        source_pack_root=pack,
        authority_root=pack.parent if pack else None,
        snapshot_root=work_dir / "inputs/source-pack",
        retrieval_policy=fr.PUBLIC_RETRIEVAL_POLICY_ID,
    )
    policy_ref = graph["retrieval_policy"]
    policy_path = work_dir / policy_ref["path"]
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in graph["nodes"]}

    assert graph["acquisition_mode"] == {
        "kind": mode,
        "network_required": True,
        "pack_required": mode == "hybrid",
    }
    assert _sha(policy_path.read_bytes()) == policy_ref["sha256"]
    assert policy["node_id"] == "source_discovery"
    assert policy["providers"] == fr.PUBLIC_RETRIEVAL_PROVIDERS
    assert policy["secret_refs"] == []
    assert policy["credential_mode"] == "public_no_key"
    assert any(policy_ref["path"] in item for item in nodes["source_discovery"]["read_scope"])
    assert all(
        not any(policy_ref["path"] in item for item in nodes[node_id]["read_scope"])
        for node_id in fr.PART_A_NODE_IDS
        if node_id != "source_discovery"
    )
    assert gnd._fixed_research_retrieval_policy_valid(graph) is True

    policy["providers"] = ["unapproved-provider"]
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    assert gnd._fixed_research_retrieval_policy_valid(graph) is False


def test_codex_research_service_uses_fresh_schema_bound_context_and_scrubs_api_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    class FakeProcess:
        pid = 12345
        returncode = 0

        def __init__(self, command: list[str], **kwargs: object) -> None:
            captured["command"] = command
            captured["env"] = dict(kwargs["env"])

        def communicate(self, prompt: str, timeout: int) -> tuple[str, None]:
            captured["prompt"] = prompt
            captured["timeout"] = timeout
            command = captured["command"]
            response_path = Path(command[command.index("--output-last-message") + 1])
            response_path.write_text(json.dumps({
                "node_id": "evidence_synthesis",
                "limitations": [],
                "claims": [{
                    "claim_id": "claim-1",
                    "text": "Bounded result",
                    "evidence_ids": ["e1"],
                    "evidence_quotes": [{"source_id": "s1", "quote": "Evidence e1."}],
                    "uncertainty": "low",
                    "limitations": [],
                }],
            }) + "\n", encoding="utf-8")
            return '{"type":"turn.completed"}\n', None

    monkeypatch.setattr(cr.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(cr.subprocess, "Popen", FakeProcess)
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-api-key-must-not-cross-boundary")
    monkeypatch.setenv("OPENROUTER_API_KEY", "ambient-router-key-must-not-cross-boundary")
    source_home = tmp_path / "source-codex-home"
    source_home.mkdir()
    (source_home / "auth.json").write_text('{"auth_mode":"chatgpt"}\n', encoding="utf-8")
    monkeypatch.setenv("SOLAR_CODEX_SOURCE_HOME", str(source_home))
    service = CodexResearchModelService(tmp_path, model="gpt-test", role="writer", timeout_seconds=17)
    result = service(
        node_id="evidence_synthesis",
        task_contract={"user_intent": "Use only evidence e1."},
        source_validation={"accepted": [{"source_id": "s1", "content_summary": "Evidence e1."}]},
    )
    command = captured["command"]
    assert command[1:4] == ["exec", "--ephemeral", "--ignore-user-config"]
    assert "--ignore-rules" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--output-schema") + 1].endswith("response.schema.json")
    assert captured["timeout"] == 17
    assert "OPENAI_API_KEY" not in captured["env"]
    assert "OPENROUTER_API_KEY" not in captured["env"]
    assert "ambient-api-key-must-not-cross-boundary" not in captured["prompt"]
    assert service.service_id == CODEX_RESEARCH_SERVICE_ID
    assert result["claims"][0]["evidence_ids"] == ["e1"]
    usage = result["provider_usage"][0]
    assert usage["provider"] == "codex_subscription"
    assert usage["principal_role"] == "writer"
    assert usage["session_mode"] == "ephemeral"
    assert (tmp_path / usage["archive_path"]).is_file()


def test_codex_research_service_rejects_schema_invalid_agent_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class InvalidProcess:
        pid = 12346
        returncode = 0

        def __init__(self, command: list[str], **_kwargs: object) -> None:
            self.command = command

        def communicate(self, _prompt: str, timeout: int) -> tuple[str, None]:
            assert timeout == 20
            response_path = Path(self.command[self.command.index("--output-last-message") + 1])
            response_path.write_text('{"node_id":"evidence_synthesis","limitations":[]}\n', encoding="utf-8")
            return '{"type":"turn.completed"}\n', None

    monkeypatch.setattr(cr.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(cr.subprocess, "Popen", InvalidProcess)
    source_home = tmp_path / "source-codex-home"
    source_home.mkdir()
    (source_home / "auth.json").write_text('{"auth_mode":"chatgpt"}\n', encoding="utf-8")
    monkeypatch.setenv("SOLAR_CODEX_SOURCE_HOME", str(source_home))
    service = CodexResearchModelService(tmp_path, model="gpt-test", role="writer", timeout_seconds=20)
    with pytest.raises(ResearchOperatorError, match="violates its schema"):
        service(node_id="evidence_synthesis", task_contract={}, source_validation={})
    assert len(service.invocation_usage) == 1
    failed_usage = service.invocation_usage[0]
    assert failed_usage["status"] == "failed"
    assert len(failed_usage["evidence_paths"]) == 5
    assert {
        Path(path).name for path in failed_usage["evidence_paths"]
    } == {"request.json", "response.schema.json", "response.json", "events.jsonl", "exchange.json"}


def test_report_revision_two_call_evidence_is_aggregated_and_fully_accounted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Boundary injection proves A7 attempt/repair evidence accounting, not model quality."""
    calls = 0

    class TwoCallProcess:
        pid = 12347

        def __init__(self, command: list[str], **_kwargs: object) -> None:
            nonlocal calls
            calls += 1
            self.call_number = calls
            self.command = command
            self.returncode = 0 if calls == 1 else 1

        def communicate(self, _prompt: str, timeout: int) -> tuple[str, None]:
            assert timeout == 20
            if self.call_number == 1:
                response_path = Path(self.command[self.command.index("--output-last-message") + 1])
                response_path.write_text(json.dumps({
                    "node_id": "report_revision",
                    "limitations": ["Bounded limitation."],
                    "report": {
                        "title": "Bounded revision",
                        "body": "## Evidence Method\n\nBounded.\n\n## Limitations\n\nBounded limitation.",
                        "sections": [],
                        "conclusions": [],
                    },
                    "preservation": {
                        "preserved_conclusion_ids": [],
                        "preserved_method_sha256": "a" * 64,
                        "preserved_limitations": ["Bounded limitation."],
                    },
                }) + "\n", encoding="utf-8")
                return '{"type":"turn.completed","call":1}\n', None
            return '{"type":"turn.failed","call":2}\n', None

    monkeypatch.setattr(cr.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(cr.subprocess, "Popen", TwoCallProcess)
    source_home = tmp_path / "source-codex-home"
    source_home.mkdir()
    (source_home / "auth.json").write_text('{"auth_mode":"chatgpt"}\n', encoding="utf-8")
    monkeypatch.setenv("SOLAR_CODEX_SOURCE_HOME", str(source_home))
    work_dir = tmp_path / "workdir"
    stage_dir = work_dir / "artifacts/research_evidence_to_poc/revision"
    service = CodexResearchModelService(
        stage_dir,
        model="gpt-test",
        role="writer",
        timeout_seconds=20,
    )
    kwargs = {
        "node_id": "report_revision",
        "task_contract": {"user_intent": "Repair the bounded report."},
        "original_report": {},
        "evidence_synthesis": {},
        "independent_review": {},
        "preservation_requirements": {
            "preserved_conclusion_ids": [],
            "preserved_method_sha256": "a" * 64,
            "preserved_limitations": ["Bounded limitation."],
        },
    }
    first = service(**kwargs)
    with pytest.raises(ResearchOperatorError, match="failed at node=report_revision"):
        service(**kwargs)

    # Simulate the operator's failed result, which otherwise loses all prior
    # call usage.  The adapter must recover both attempts from the stage journal.
    failed_result = {"model_provider_usage": []}
    merged = fixed_adapter._merge_codex_invocation_usage(
        failed_result,
        {"model_generate": service},
    )
    assert len(merged) == 2
    assert [item["status"] for item in merged] == ["completed", "failed"]
    assert [item["role_call_index"] for item in merged] == [1, 2]
    assert [item["aggregate_call_index"] for item in merged] == [1, 2]
    assert {item["total_calls"] for item in merged} == {2}
    assert first["provider_usage"][0]["invocation_id"] == merged[0]["invocation_id"]
    assert all(len(item["evidence_paths"]) == 5 for item in merged)

    accounted = fixed_adapter._normalize_provider_archives(failed_result, work_dir, stage_dir)
    changed_files = set(fixed_adapter._inventory(work_dir))
    assert changed_files == accounted
    assert len(changed_files) == 10
    for item in merged:
        assert set(item["evidence_paths"]).issubset(accounted)
        assert item["archive_path"] in accounted
        for path, digest in item["evidence_sha256"].items():
            assert _sha((work_dir / path).read_bytes()) == digest


def test_all_codex_stage_schemas_are_closed_and_node_bound() -> None:
    for node_id in ("evidence_synthesis", "report_draft", "independent_review", "report_revision", "publication_produce"):
        schema = _response_schema(node_id)
        assert schema["additionalProperties"] is False
        assert schema["properties"]["node_id"] == {"type": "string", "const": node_id}
        assert set(schema["required"]) == set(schema["properties"])
        assert "uniqueItems" not in json.dumps(schema)


def test_report_revision_omitting_provider_limitations_fails_before_a7_acceptance(
    tmp_path: Path,
) -> None:
    original = {
        "schema": "research_synthesis.report_draft.v1",
        "report": {
            "title": "Accepted draft",
            "body": (
                "# Accepted draft\n\n## Evidence Method\n\n"
                "Only the supplied validated source claims were used.\n\n"
                "## Conclusions\n\nBounded conclusion.\n\n"
                "## Limitations\n\nProvider-recorded limitation."
            ),
            "sections": [],
            "conclusions": [{
                "conclusion_id": "conclusion-001",
                "text": "Bounded conclusion.",
                "evidence_ids": ["claim-001"],
            }],
        },
        "limitations": ["Provider-recorded limitation."],
    }
    required = revision_operator.revision_preservation_requirements(original)
    declaration = {
        key: required[key]
        for key in (
            "preserved_conclusion_ids",
            "preserved_method_sha256",
            "preserved_limitations",
        )
    }
    omitted = {
        "report": {
            "title": "Revised report",
            "body": (
                "# Revised report\n\n## Evidence Method\n\n"
                "Only the supplied validated source claims were used.\n\n"
                "## Conclusions\n\nBounded conclusion."
            ),
            "sections": [],
            "conclusions": original["report"]["conclusions"],
        },
        "limitations": [],
        "preservation": declaration,
    }
    with pytest.raises(ResearchOperatorError, match="provider-recorded limitation"):
        revision_operator.verify_revision_response_preservation(original, omitted)

    work_dir = tmp_path / "workdir"
    base_path = work_dir / "draft/report_draft.json"
    revision_path = work_dir / "revision/report_revision.json"
    base_path.parent.mkdir(parents=True)
    revision_path.parent.mkdir(parents=True)
    base_path.write_text(json.dumps(original) + "\n", encoding="utf-8")
    revision_path.write_text(json.dumps({
        "revision_applied": True,
        "revised_report": omitted["report"],
        "limitations": [],
        "preservation": {
            "verified": True,
            "model_declaration": declaration,
            "original_report_sha256": revision_operator.stable_json_sha256(original),
        },
    }) + "\n", encoding="utf-8")
    with pytest.raises(ResearchOperatorError, match="provider-recorded limitation"):
        fixed_adapter._verify_report_revision_artifact(
            revision_path,
            work_dir,
            [{
                "artifact_id": "report_draft",
                "path": str(base_path.relative_to(work_dir)),
                "schema": original["schema"],
                "sha256": _sha(base_path.read_bytes()),
            }],
        )

    paired_usage = [
        {
            "provider": "codex_subscription",
            "session_mode": "ephemeral",
            "principal_role": role,
        }
        for role in ("writer", "reviewer", "writer", "reviewer")
    ]
    fixed_adapter._verify_model_usage(
        node_id="report_revision",
        result={"model_provider_usage": paired_usage},
    )
    with pytest.raises(fixed_adapter.AdapterError, match="pair each writer attempt"):
        fixed_adapter._verify_model_usage(
            node_id="report_revision",
            result={"model_provider_usage": paired_usage[:-1]},
        )

    rendered = json.loads(json.dumps(omitted))
    rendered["report"]["body"] += "\n\n## Limitations\n\nProvider-recorded limitation."
    rendered["limitations"] = ["Provider-recorded limitation."]
    proof = revision_operator.verify_revision_response_preservation(original, rendered)
    revision_path.write_text(json.dumps({
        "revision_applied": True,
        "revised_report": rendered["report"],
        "limitations": [
            "Provider-recorded limitation.",
            "Reviewer and writer used the same provider/model identity; independence is limited.",
        ],
        "preservation": proof,
    }) + "\n", encoding="utf-8")
    with pytest.raises(ResearchOperatorError, match="exact original conclusion, method, and limitation"):
        fixed_adapter._verify_report_revision_artifact(
            revision_path,
            work_dir,
            [{
                "artifact_id": "report_draft",
                "path": str(base_path.relative_to(work_dir)),
                "schema": original["schema"],
                "sha256": _sha(base_path.read_bytes()),
            }],
        )


def test_same_normalized_request_has_identical_fixed_topology_across_independent_intakes(
    tmp_path: Path,
) -> None:
    request = "Research a bounded deterministic topic and produce an evidence-linked report."

    def create(root: Path) -> dict:
        result = wi.create_contract_sprint(
            workflow_id=fr.WORKFLOW_ID,
            request=request,
            workspace_root=str(root / "workspace"),
            inputs={"execution_profile": "part_a_only", "acquisition_mode": "source_pack"},
            sprints_dir=root / "sprints",
        )
        return json.loads(
            (root / "sprints" / f"{result['sprint_id']}.task_graph.json").read_text(encoding="utf-8")
        )

    first = create(tmp_path / "first")
    second = create(tmp_path / "second")

    def topology(graph: dict) -> list[dict]:
        sid = str(graph["sprint_id"])

        def normalize(value: object) -> object:
            if isinstance(value, str):
                return value.replace(sid, "<sid>")
            if isinstance(value, list):
                return [normalize(item) for item in value]
            if isinstance(value, dict):
                return {key: normalize(item) for key, item in value.items()}
            return value

        return [
            normalize({
                "id": node["id"],
                "depends_on": node.get("depends_on") or [],
                "gate": node.get("evaluator_gate") or {},
                "required_operator_id": node.get("required_operator_id"),
                "research_physical_operator_id": node.get("research_physical_operator_id"),
                "status": node.get("status"),
                "condition_status": node.get("condition_status"),
                "condition_reason": node.get("condition_reason"),
                "read_scope": node.get("read_scope") or [],
                "outputs": node.get("outputs") or [],
            })
            for node in graph["nodes"]
        ]

    assert topology(first) == topology(second)


def test_raw_router_instantiation_is_rejected() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(LIB / "workflow_router.py"),
            "instantiate",
            "--workflow-id",
            fr.WORKFLOW_ID,
            "--input",
            "sprint_id=unsafe",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "typed workflow_intake boundary" in result.stderr
    assert '"nodes"' not in result.stdout


def test_composed_fixed_dispatch_envelope_adapter_and_solar_a1_closeout_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, graph_path, _sprints = _graph(tmp_path, monkeypatch)
    node = next(item for item in graph["nodes"] if item["id"] == "seed_fetch")
    operator_id = fr.PHYSICAL_OPERATOR_BY_NODE["seed_fetch"]
    item = {
        "id": "q-fixed-a1",
        "intent": "graph_node|node_id=seed_fetch",
        "payload": {
            "sprint_id": graph["sprint_id"],
            "graph": str(graph_path),
            "node": node,
            "assignment": {"pane": f"operator:{operator_id}"},
            "dispatch_id": "fixed-a1-dispatch",
        },
    }
    dry = gnd.dispatch_queue_item(item, dry_run=True)
    assert dry["ok"] is True, dry
    assert dry["dispatch_mode"] == "fixed_research_operator_direct"
    envelope = dry["operator_envelope"]
    assert envelope["runner_contract"] == fr.WORKFLOW_ID
    assert envelope["operator_id"] == operator_id
    envelope_path = tmp_path / "fixed-a1-envelope.json"
    envelope_path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    env = dict(os.environ)
    env.pop("OPENAI_API_KEY", None)
    env.pop("OPENROUTER_API_KEY", None)
    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS / "plugins" / "autosci" / "bin" / "fixed_research_node_adapter.py"),
            "--envelope",
            str(envelope_path),
        ],
        cwd=HARNESS.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    payload = json.loads(result.stdout)
    assert payload["result"]["status"] == "completed"
    primary = Path(envelope["work_dir"]) / "artifacts/research_evidence_to_poc/seed/seed_snapshot.json"
    assert primary.is_file()
    monkeypatch.setattr(gnd, "_workspace_binding", None)
    saved = gnd.load_graph(graph_path)
    reconciled = gnd._reconcile_existing_dispatches(saved, str(graph_path))
    assert next(item for item in saved["nodes"] if item["id"] == "seed_fetch")["status"] == "reviewing", reconciled
    gnd.save_graph(graph_path, saved)
    evaluation = gnd.dispatch_node_evals(str(graph_path), dry_run=False)
    assert any(item.get("dispatch_mode") == "deterministic_gate" for item in evaluation.get("dispatched", [])), evaluation
    saved = gnd.load_graph(graph_path)
    reconciled = gnd._reconcile_existing_dispatches(saved, str(graph_path))
    assert next(item for item in saved["nodes"] if item["id"] == "seed_fetch")["status"] == "passed", reconciled
    gnd.save_graph(graph_path, saved)
    durable = gnd.load_graph(graph_path)
    assert next(item for item in durable["nodes"] if item["id"] == "seed_fetch")["status"] == "passed"
    assert durable["node_results"]["seed_fetch"]["status"] == "passed"
    closeout = durable["node_results"]["seed_fetch"]["closeout_receipt"]
    assert closeout["eval"]["consumable"] is True
    assert closeout["eval"]["artifact_snapshot"]["ok"] is True
    assert closeout["manifest"]["ok"] is True
    assert closeout["proof"]["ok"] is True
    transitions = gnd._gate_ledger.read_records(
        gnd.SPRINTS_DIR,
        graph["sprint_id"],
        node_id="seed_fetch",
        kind="status_transition",
    )
    assert any(
        record.get("to_status") == "passed" and record.get("applied") is not False
        for record in transitions
    )
    assert gnd._gate_ledger.project_node_status(
        gnd.SPRINTS_DIR, graph["sprint_id"], "seed_fetch"
    ) == "passed"
    discovery = next(item for item in durable["nodes"] if item["id"] == "source_discovery")
    discovery_operator = fr.PHYSICAL_OPERATOR_BY_NODE["source_discovery"]
    discovery_item = {
        "intent": "graph_node|node_id=source_discovery",
        "payload": {
            "sprint_id": graph["sprint_id"],
            "graph": str(graph_path),
            "node": discovery,
            "assignment": {"pane": f"operator:{discovery_operator}"},
            "dispatch_id": "fixed-a2-after-closeout",
        },
    }
    accepted = gnd.dispatch_queue_item(discovery_item, dry_run=True)
    assert accepted["ok"] is True, accepted
    manifest_path = Path(closeout["manifest"]["path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["content_digest"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    rejected = gnd.dispatch_queue_item(discovery_item, dry_run=True)
    assert rejected["ok"] is False
    assert rejected["reason"] == "fixed_research_envelope_rejected"
    assert "controller closeout" in rejected["error"]


def test_non_dry_registered_a1_to_a3_operator_runtime_daemon_and_solar_closeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_codex = os.environ.get("SOLAR_LIVE_CODEX_RESEARCH") == "1"
    live_full_poc = os.environ.get("SOLAR_LIVE_FIXED_RESEARCH_FULL") == "1"
    graph, graph_path, sprints = _graph(
        tmp_path,
        monkeypatch,
        execution_profile="part_a_plus_poc" if live_full_poc else "part_a_only",
    )

    runtime_harness = tmp_path / "operator-harness"
    runtime_harness.mkdir()
    _symlink_or_skip(runtime_harness / "plugins", HARNESS / "plugins", target_is_directory=True)
    _symlink_or_skip(runtime_harness / "personas", HARNESS / "personas", target_is_directory=True)
    monkeypatch.setenv("HARNESS_DIR", str(runtime_harness))
    monkeypatch.setenv("SOLAR_HARNESS_DIR", str(runtime_harness))
    monkeypatch.setenv("HARNESS_SPRINTS_DIR", str(sprints))
    monkeypatch.setenv(
        "SOLAR_MULTI_TASK_OPERATORS", str(HARNESS / "config" / "physical-operators.json")
    )
    monkeypatch.setenv("SOLAR_OPERATORD_AUTO_KICK", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(opr, "HARNESS_DIR", runtime_harness)
    monkeypatch.setattr(opr, "OPERATOR_LEASE_DIR", runtime_harness / "run/operator-leases")
    monkeypatch.setattr(opr, "OPERATOR_STATUS_DIR", runtime_harness / "run/operator-status")
    monkeypatch.setattr(opr, "OPERATOR_INBOX_DIR", runtime_harness / "run/operator-inbox")
    monkeypatch.setattr(opr, "OPERATOR_RESULTS_DIR", runtime_harness / "run/operator-results")
    monkeypatch.setattr(opr, "OPERATOR_PERSONAS_DIR", HARNESS / "personas")
    monkeypatch.setattr(
        opr, "PHYSICAL_OPERATORS_PATH", HARNESS / "config" / "physical-operators.json"
    )

    monkeypatch.setattr(gnd, "_workspace_binding", None)
    env = dict(os.environ)
    env.update({
        "HARNESS_DIR": str(runtime_harness),
        "SOLAR_HARNESS_DIR": str(runtime_harness),
        "HARNESS_SPRINTS_DIR": str(sprints),
        "SOLAR_MULTI_TASK_OPERATORS": str(HARNESS / "config" / "physical-operators.json"),
        "SOLAR_OPERATORD_AUTO_KICK": "0",
    })
    env.pop("OPENAI_API_KEY", None)
    env.pop("OPENROUTER_API_KEY", None)

    def run_and_close(node_id: str, sequence: int) -> dict:
        current = gnd.load_graph(graph_path)
        node = next(item for item in current["nodes"] if item["id"] == node_id)
        operator_id = fr.PHYSICAL_OPERATOR_BY_NODE[node_id]
        dispatch_id = f"fixed-{sequence}-{node_id}-nondry"
        submitted = gnd.dispatch_queue_item({
            "id": f"q-{dispatch_id}",
            "intent": f"graph_node|node_id={node_id}",
            "payload": {
                "sprint_id": graph["sprint_id"],
                "graph": str(graph_path),
                "node": node,
                "assignment": {"pane": f"operator:{operator_id}"},
                "dispatch_id": dispatch_id,
            },
        }, dry_run=False)
        assert submitted["ok"] is True, submitted
        assert submitted["dispatch_mode"] == "fixed_research_operator_direct"
        assert submitted["operator_submit"]["task_id"] == dispatch_id
        inbox = Path(submitted["operator_submit"]["inbox_path"])
        assert inbox.is_file()
        daemon = subprocess.run(
            [
                sys.executable,
                str(HARNESS / "tools" / "operatord.py"),
                "daemon",
                "--operator",
                operator_id,
                "--once",
                "--poll-interval",
                "0.05",
                "--once-max-wait-seconds",
                "10",
            ],
            cwd=HARNESS.parent,
            env=env,
            capture_output=True,
            text=True,
            check=False,
                timeout=360 if live_codex else 60,
        )
        assert daemon.returncode == 0, (daemon.stdout, daemon.stderr)
        operator_result_path = (
            runtime_harness / "run/operator-results" / operator_id / dispatch_id / "result.json"
        )
        operator_result = json.loads(operator_result_path.read_text(encoding="utf-8"))
        assert operator_result["status"] == "completed"
        assert operator_result["exit_code"] == 0
        assert not inbox.exists()
        assert (sprints / f"{graph['sprint_id']}.{node_id}-handoff.md").is_file()

        saved = gnd.load_graph(graph_path)
        reconciled = gnd._reconcile_existing_dispatches(saved, str(graph_path))
        assert next(item for item in saved["nodes"] if item["id"] == node_id)["status"] == "reviewing", reconciled
        gnd.save_graph(graph_path, saved)
        evaluation = gnd.dispatch_node_evals(str(graph_path), dry_run=False)
        assert any(
            item.get("dispatch_mode") == "deterministic_gate"
            and item.get("node") == node_id
            for item in evaluation.get("dispatched", [])
        ), evaluation
        saved = gnd.load_graph(graph_path)
        reconciled = gnd._reconcile_existing_dispatches(saved, str(graph_path))
        assert next(item for item in saved["nodes"] if item["id"] == node_id)["status"] == "passed", reconciled
        gnd.save_graph(graph_path, saved)
        durable = gnd.load_graph(graph_path)
        closeout = durable["node_results"][node_id]["closeout_receipt"]
        assert closeout["eval"]["consumable"] is True
        assert closeout["manifest"]["ok"] is True
        assert closeout["proof"]["ok"] is True
        return durable

    durable = run_and_close("seed_fetch", 1)
    durable = run_and_close("source_discovery", 2)
    durable = run_and_close("source_validation", 3)
    validation = (
        sprints
        / graph["sprint_id"]
        / "workdir/artifacts/research_evidence_to_poc/validation/source_validation.json"
    )
    assert validation.is_file()
    assert b"UNIQUE_SENTINEL_FACT_7319" in validation.read_bytes()
    synthesis = next(node for node in durable["nodes"] if node["id"] == "evidence_synthesis")
    assert synthesis.get("status", "pending") == "pending"
    assert synthesis["required_operator_id"] == fr.PHYSICAL_OPERATOR_BY_NODE["evidence_synthesis"]
    pending_descendants = {
        node["id"]: node
        for node in durable["nodes"]
        if node["id"] in {"report_draft", "independent_review", "report_revision", "final_acceptance"}
    }
    assert all(node.get("status", "pending") == "pending" for node in pending_descendants.values())
    assert all(node.get("required_operator_id") for node in pending_descendants.values())
    if live_codex:
        for sequence, node_id in enumerate(
            ("evidence_synthesis", "report_draft", "independent_review", "report_revision", "final_acceptance"),
            start=4,
        ):
            durable = run_and_close(node_id, sequence)
        assert all(
            next(item for item in durable["nodes"] if item["id"] == node_id)["status"] == "passed"
            for node_id in fr.PART_A_NODE_IDS
        )
        final_path = (
                sprints
                / graph["sprint_id"]
                / "workdir/artifacts/research_evidence_to_poc/final/final_acceptance.json"
        )
        assert final_path.is_file()
        final_payload = json.loads(final_path.read_text(encoding="utf-8"))
        assert final_payload["schema"] == fr.EXPECTED_SCHEMA_BY_NODE["final_acceptance"]
        if live_full_poc:
            for sequence, node_id in enumerate(
                ("poc_handoff", "idea_evaluation", "experiment_design"),
                start=9,
            ):
                durable = run_and_close(node_id, sequence)
            paused = gnd.dispatch_ready(str(graph_path), dry_run=False, max_parallel=1)
            assert paused["ok"] is True, paused
            assert paused["status"] == "needs_human_review", paused
            approval_gate = paused["approval_gate"]
            assert approval_gate["status"] == "awaiting_human"
            request_path = (
                sprints
                / graph["sprint_id"]
                / "workdir/artifacts/research_evidence_to_poc/poc/approval/approval_request.json"
            )
            assert request_path.is_file()
            approval_request = json.loads(request_path.read_text(encoding="utf-8"))
            assert approval_request["plan_sha256"] == approval_gate["plan_sha256"]
            durable = gnd.load_graph(graph_path)
            assert gs.node_status(durable, "experiment_approval") == "needs_human_review"
            assert all(
                gs.node_status(durable, node_id) == "pending"
                for node_id in ("experiment_run", "claim_verification", "final_delivery")
            )


@pytest.mark.parametrize(
    "preauthorized",
    [False, True],
    ids=["interactive-exact-plan", "one-shot-fixed-policy"],
)
def test_non_dry_fixed_part_b_b1_to_b7_with_seeded_controller_accepted_part_a_precondition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, preauthorized: bool
) -> None:
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    assert gnd._gate_ledger is not None
    assert gnd._ledger_enabled() is True
    monkeypatch.setattr(gnd, "_workspace_binding", None)
    graph, graph_path, sprints = _graph(
        tmp_path,
        monkeypatch,
        execution_profile="part_a_plus_poc",
        sid="fixed-part-b-nondry",
        experiment_policy=fr.EXPERIMENT_POLICY_ID if preauthorized else "",
    )
    graph = _seed_controller_accepted_part_a_precondition(graph, graph_path, sprints)

    runtime_harness = tmp_path / "operator-harness"
    runtime_harness.mkdir()
    for name, target in (
        ("plugins", HARNESS / "plugins"),
        ("personas", HARNESS / "personas"),
        ("config", HARNESS / "config"),
        ("schemas", HARNESS / "schemas"),
    ):
        _symlink_or_skip(runtime_harness / name, target, target_is_directory=True)
    monkeypatch.setenv("HARNESS_DIR", str(runtime_harness))
    monkeypatch.setenv("SOLAR_HARNESS_DIR", str(runtime_harness))
    monkeypatch.setenv("HARNESS_SPRINTS_DIR", str(sprints))
    monkeypatch.setenv("SOLAR_MULTI_TASK_OPERATORS", str(HARNESS / "config" / "physical-operators.json"))
    monkeypatch.setenv("SOLAR_OPERATORD_AUTO_KICK", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(opr, "HARNESS_DIR", runtime_harness)
    monkeypatch.setattr(opr, "OPERATOR_LEASE_DIR", runtime_harness / "run/operator-leases")
    monkeypatch.setattr(opr, "OPERATOR_STATUS_DIR", runtime_harness / "run/operator-status")
    monkeypatch.setattr(opr, "OPERATOR_INBOX_DIR", runtime_harness / "run/operator-inbox")
    monkeypatch.setattr(opr, "OPERATOR_RESULTS_DIR", runtime_harness / "run/operator-results")
    monkeypatch.setattr(opr, "OPERATOR_PERSONAS_DIR", HARNESS / "personas")
    monkeypatch.setattr(opr, "PHYSICAL_OPERATORS_PATH", HARNESS / "config" / "physical-operators.json")
    env = dict(os.environ)
    env.update(
        {
            "HARNESS_DIR": str(runtime_harness),
            "SOLAR_HARNESS_DIR": str(runtime_harness),
            "HARNESS_SPRINTS_DIR": str(sprints),
            "SOLAR_MULTI_TASK_OPERATORS": str(HARNESS / "config" / "physical-operators.json"),
            "SOLAR_OPERATORD_AUTO_KICK": "0",
        }
    )
    env.pop("OPENAI_API_KEY", None)
    env.pop("OPENROUTER_API_KEY", None)

    def run_and_close(node_id: str, sequence: int) -> dict:
        current = gnd.load_graph(graph_path)
        node = next(item for item in current["nodes"] if item["id"] == node_id)
        operator_id = fr.PHYSICAL_OPERATOR_BY_NODE[node_id]
        dispatch_id = f"fixed-part-b-{sequence}-{node_id}"
        submitted = gnd.dispatch_queue_item(
            {
                "id": f"q-{dispatch_id}",
                "intent": f"graph_node|node_id={node_id}",
                "payload": {
                    "sprint_id": graph["sprint_id"],
                    "graph": str(graph_path),
                    "node": node,
                    "assignment": {"pane": f"operator:{operator_id}"},
                    "dispatch_id": dispatch_id,
                },
            },
            dry_run=False,
        )
        assert submitted["ok"] is True, submitted
        assert submitted["dispatch_mode"] == "fixed_research_operator_direct"
        inbox = Path(submitted["operator_submit"]["inbox_path"])
        assert inbox.is_file()
        daemon = subprocess.run(
            [
                sys.executable,
                str(HARNESS / "tools" / "operatord.py"),
                "daemon",
                "--operator",
                operator_id,
                "--once",
                "--poll-interval",
                "0.05",
                "--once-max-wait-seconds",
                "10",
            ],
            cwd=HARNESS.parent,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
        assert daemon.returncode == 0, (daemon.stdout, daemon.stderr)
        operator_result = json.loads(
            (
                runtime_harness
                / "run/operator-results"
                / operator_id
                / dispatch_id
                / "result.json"
            ).read_text(encoding="utf-8")
        )
        assert operator_result["status"] == "completed", operator_result
        assert operator_result["exit_code"] == 0, operator_result
        assert not inbox.exists()

        saved = gnd.load_graph(graph_path)
        first = gnd._reconcile_existing_dispatches(saved, str(graph_path))
        assert gs.node_status(saved, node_id) == "reviewing", first
        gnd.save_graph(graph_path, saved)
        evaluation = gnd.dispatch_node_evals(str(graph_path), dry_run=False)
        assert any(
            item.get("dispatch_mode") == "deterministic_gate" and item.get("node") == node_id
            for item in evaluation.get("dispatched", [])
        ), evaluation
        saved = gnd.load_graph(graph_path)
        second = gnd._reconcile_existing_dispatches(saved, str(graph_path))
        assert gs.node_status(saved, node_id) == "passed", second
        gnd.save_graph(graph_path, saved)
        durable = gnd.load_graph(graph_path)
        closeout = durable["node_results"][node_id]["closeout_receipt"]
        assert closeout["eval"]["consumable"] is True
        assert closeout["manifest"]["ok"] is True
        assert closeout["proof"]["ok"] is True
        return durable

    for sequence, node_id in enumerate(("poc_handoff", "idea_evaluation", "experiment_design"), start=9):
        graph = run_and_close(node_id, sequence)

    request_path = gnd._fixed_research_approval_paths(graph["sprint_id"])[1]
    approval_path = gnd._fixed_research_approval_paths(graph["sprint_id"])[2]
    if preauthorized:
        current = gnd.load_graph(graph_path)
        design = next(item for item in current["nodes"] if item["id"] == "experiment_design")
        plan_path = gnd._fixed_research_relative_path(
            str(design["outputs"][1]["path"]), current["sprint_id"], label="preauthorized plan"
        )[0]
        pristine = plan_path.read_bytes()
        base_plan = json.loads(pristine)
        mutations = {
            "runner": lambda payload: payload["benchmark"].__setitem__("runner", "harness/tools/other.py"),
            "network": lambda payload: payload["benchmark"].__setitem__("network", "enabled"),
            "timeout": lambda payload: payload["benchmark"].__setitem__("timeout_seconds", 61),
            "capability": lambda payload: payload["approval_scope"].__setitem__("capabilities", ["network:any"]),
            "input_set": lambda payload: payload["benchmark"].__setitem__("inputs", []),
        }
        for label, mutate in mutations.items():
            changed = json.loads(json.dumps(base_plan))
            mutate(changed)
            plan_path.write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")
            with pytest.raises(ValueError, match="hash|manifest|controller|preauthorized|snapshot"):
                gnd._prepare_fixed_research_experiment_approval(
                    gnd.load_graph(graph_path), str(graph_path), current["sprint_id"], dry_run=False
                )
            assert not request_path.exists(), label
            assert not approval_path.exists(), label
            plan_path.write_bytes(pristine)
        gate = gnd._prepare_fixed_research_experiment_approval(
            gnd.load_graph(graph_path), str(graph_path), current["sprint_id"], dry_run=False
        )
        assert gate["status"] == "approval_received", gate
        approval_payload = json.loads(approval_path.read_text(encoding="utf-8"))
        assert approval_payload["approval_mode"] == "policy_preauthorized"
        assert approval_payload["actor"] == "user"
        assert approval_payload["statement"] == "no need to pause at B4 no pauses"
        assert approval_payload["preauthorization"]["policy_id"] == fr.EXPERIMENT_POLICY_ID
        assert (gs.node_status(gnd.load_graph(graph_path), "experiment_approval") or "pending") == "pending"
    else:
        paused = gnd.dispatch_ready(str(graph_path), dry_run=False, max_parallel=1)
        assert paused["ok"] is True, paused
        assert paused["status"] == "needs_human_review", paused
        approval_request = json.loads(request_path.read_text(encoding="utf-8"))
        approval = gnd.approve_fixed_experiment(
            str(graph_path),
            expected_generation=int(approval_request["generation"]),
            actor="human-reviewer@example.test",
            statement="I approve this exact no-network evidence-lineage benchmark for the deterministic Part-B runtime test.",
            plan_sha256=str(approval_request["plan_sha256"]),
            approved_scope=dict(approval_request["approved_scope"]),
            approved_capabilities=list(approval_request["approved_capabilities"]),
        )
        assert approval["ok"] is True, approval

    for sequence, node_id in enumerate(("experiment_approval", "experiment_run"), start=12):
        graph = run_and_close(node_id, sequence)

    # B6 must receive the complete controller-accepted B5 evidence set, not
    # merely the summary and raw JSON.  Each ref carries a per-file binding to
    # the accepted manifest row+directory entry and evaluator snapshot.
    graph = gnd.load_graph(graph_path)
    b6_node = next(item for item in graph["nodes"] if item["id"] == "claim_verification")
    b6_dependencies = gnd._fixed_research_dependency_artifacts(graph, graph["sprint_id"], b6_node)
    b5_ids = {
        "experiment_run",
        "experiment_run:benchmark_raw.json",
        "experiment_run:stdout.txt",
        "experiment_run:stderr.json",
    }
    b5_refs = {item["artifact_id"]: item for item in b6_dependencies if item["artifact_id"] in b5_ids}
    assert set(b5_refs) == b5_ids
    for artifact_id, ref in b5_refs.items():
        binding = ref["controller_closeout"]["artifact_binding"]
        assert binding["artifact_id"] == artifact_id
        assert binding["path"] == ref["path"]
        assert binding["schema"] == ref["schema"]
        assert binding["sha256"] == ref["sha256"]
        assert binding["manifest"]["sha256"] == ref["sha256"]
        assert binding["manifest"]["entry_sha256"] == ref["sha256"]
        assert binding["eval_snapshot"]["sha256"] == ref["sha256"]
        assert binding["eval_snapshot"]["entry_sha256"] == ref["sha256"]

    for sequence, node_id in enumerate(("claim_verification", "final_delivery"), start=14):
        graph = run_and_close(node_id, sequence)

    # Only B1-B7 executed in this test. Part A is a separately labelled,
    # controller-accepted seeded precondition; it is not a Part-A execution
    # success claim.
    assert all(
        gs.node_status(graph, node_id) == "passed"
        for node_id in fr.PART_B_NODE_IDS
    )
    assert all(
        gs.node_status(graph, node_id) == "passed"
        for node_id in fr.PART_A_NODE_IDS
    )
    work_dir = sprints / graph["sprint_id"] / "workdir"
    result = json.loads(
        (work_dir / "artifacts/research_evidence_to_poc/poc/run/experiment_result.json").read_text(encoding="utf-8")
    )
    raw = json.loads(
        (work_dir / "artifacts/research_evidence_to_poc/poc/run/benchmark_raw.json").read_text(encoding="utf-8")
    )
    delivery = json.loads(
        (work_dir / "artifacts/research_evidence_to_poc/delivery/final_delivery.json").read_text(encoding="utf-8")
    )
    verification = json.loads(
        (work_dir / "artifacts/research_evidence_to_poc/poc/verification/claim_verification.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "completed"
    assert result["sandbox"]["network"] == "disabled"
    assert result["execution"]["exit_code"] == 0
    assert result["metrics"]["integrity_rate"] == 1.0
    assert raw["passed"] is True
    assert len(raw["checks"]) == len(fr.PART_A_NODE_IDS)
    assert {item["artifact_id"] for item in verification["experiment_evidence"]} == b5_ids
    assert delivery["status"] == "completed"
    assert delivery["claim_verdict"] == "verified"
    markdown_path = work_dir / "artifacts/research_evidence_to_poc/delivery/final_delivery.md"
    markdown = markdown_path.read_text(encoding="utf-8")
    assert delivery["limitations"]
    assert [item["limitation"] for item in delivery["limitation_sources"]] == delivery["limitations"]
    assert all(item["sources"] for item in delivery["limitation_sources"])
    assert all(
        {"artifact_id", "path", "schema", "sha256"}.issubset(source)
        for item in delivery["limitation_sources"]
        for source in item["sources"]
    )
    markdown_limitations = markdown.split("## Limitations\n\n", 1)[1].splitlines()
    assert [line[2:] for line in markdown_limitations if line.startswith("- ")] == delivery["limitations"]

    durable = gnd.load_graph(graph_path)
    b6_node = next(item for item in durable["nodes"] if item["id"] == "claim_verification")

    def dependency_rejected_after_tamper(path: Path, body: bytes) -> None:
        original = path.read_bytes()
        path.write_bytes(body)
        with pytest.raises(ValueError, match="snapshot|manifest|consumable|controller"):
            gnd._fixed_research_dependency_artifacts(durable, durable["sprint_id"], b6_node)
        path.write_bytes(original)
        assert gnd._fixed_research_dependency_artifacts(durable, durable["sprint_id"], b6_node)

    run_stage = work_dir / "artifacts/research_evidence_to_poc/poc/run"
    dependency_rejected_after_tamper(run_stage / "stdout.txt", b"tampered stdout\n")
    dependency_rejected_after_tamper(
        run_stage / "stderr.json",
        json.dumps({"schema": "solar.fixed_research.command_stream.v1", "stream": "stderr", "bytes": 8, "content": "tampered"}).encode("utf-8"),
    )
    noncompleted = json.loads((run_stage / "experiment_result.json").read_text(encoding="utf-8"))
    noncompleted["status"] = "failed"
    dependency_rejected_after_tamper(
        run_stage / "experiment_result.json",
        (json.dumps(noncompleted) + "\n").encode("utf-8"),
    )

    b5_closeout = durable["node_results"]["experiment_run"]["closeout_receipt"]
    for control_path, field in (
        (Path(b5_closeout["manifest"]["path"]), "rows"),
        (Path(b5_closeout["eval"]["artifact_snapshot"]["path"]), "rows"),
    ):
        original = control_path.read_bytes()
        control = json.loads(original)
        file_row = next(
            item
            for item in control[field]
            if item.get("kind") == "file" and str(item.get("declared") or "").endswith("/stdout.txt")
        )
        file_row["sha256"] = "0" * 64
        control_path.write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="snapshot|closeout|consumable"):
            gnd._fixed_research_dependency_artifacts(durable, durable["sprint_id"], b6_node)
        control_path.write_bytes(original)

    b7_node = next(item for item in durable["nodes"] if item["id"] == "final_delivery")
    b7_dependencies = gnd._fixed_research_dependency_artifacts(durable, durable["sprint_id"], b7_node)
    final_path = work_dir / "artifacts/research_evidence_to_poc/delivery/final_delivery.json"
    verification_request = {"read_scope": sorted({item["path"] for item in b7_dependencies})}
    fixed_adapter.verify_final_delivery_artifact(
        request=verification_request,
        work_dir=work_dir,
        primary=final_path,
        markdown_path=markdown_path,
        dependencies=b7_dependencies,
    )
    final_before = final_path.read_bytes()
    omitted = json.loads(final_before)
    omitted["limitations"] = omitted["limitations"][:-1]
    final_path.write_text(json.dumps(omitted, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ResearchOperatorError, match="does not preserve"):
        fixed_adapter.verify_final_delivery_artifact(
            request=verification_request,
            work_dir=work_dir,
            primary=final_path,
            markdown_path=markdown_path,
            dependencies=b7_dependencies,
        )
    final_path.write_bytes(final_before)

    claim_path = work_dir / "artifacts/research_evidence_to_poc/poc/verification/claim_verification.json"
    claim_before = claim_path.read_bytes()
    claim_tampered = json.loads(claim_before)
    claim_tampered["limitations"].append("Tampered downstream limitation.")
    claim_path.write_text(json.dumps(claim_tampered) + "\n", encoding="utf-8")
    with pytest.raises(ResearchOperatorError, match="not bound|hash does not match"):
        fixed_adapter.verify_final_delivery_artifact(
            request=verification_request,
            work_dir=work_dir,
            primary=final_path,
            markdown_path=markdown_path,
            dependencies=b7_dependencies,
        )
    claim_path.write_bytes(claim_before)


def test_fixed_operator_id_rejects_wrong_or_unreadable_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path / "sprints")
    operator_id = fr.PHYSICAL_OPERATOR_BY_NODE["seed_fetch"]
    item = {
        "intent": "graph_node|node_id=seed_fetch",
        "payload": {
            "sprint_id": "missing",
            "graph": str(tmp_path / "missing.task_graph.json"),
            "node": {"id": "seed_fetch"},
            "assignment": {"pane": f"operator:{operator_id}"},
        },
    }
    result = gnd.dispatch_queue_item(item, dry_run=True)
    assert result["ok"] is False
    assert result["reason"] == "fixed_research_operator_requires_exact_contract"

    graph, graph_path, _sprints = _graph(
        tmp_path / "wrong-part-b-worker",
        monkeypatch,
        execution_profile="part_a_plus_poc",
        sid="wrong-part-b-worker",
    )
    handoff = next(node for node in graph["nodes"] if node["id"] == "poc_handoff")
    wrong_operator = fr.PHYSICAL_OPERATOR_BY_NODE["experiment_run"]
    mismatch = gnd.dispatch_queue_item({
        "intent": "graph_node|node_id=poc_handoff",
        "payload": {
            "sprint_id": graph["sprint_id"],
            "graph": str(graph_path),
            "node": handoff,
            "assignment": {"pane": f"operator:{wrong_operator}"},
        },
    }, dry_run=True)
    assert mismatch["ok"] is False
    assert mismatch["reason"] == "fixed_research_operator_identity_mismatch"
    assert mismatch["expected_operator_id"] == fr.PHYSICAL_OPERATOR_BY_NODE["poc_handoff"]


def test_manual_pass_metadata_cannot_authorize_a2_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, graph_path, _sprints = _graph(tmp_path, monkeypatch)
    seed = next(item for item in graph["nodes"] if item["id"] == "seed_fetch")
    seed_path = Path(seed["outputs"][1]["path"])
    seed_path = gnd._fixed_research_relative_path(seed_path, graph["sprint_id"], label="test seed")[0]
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_text(json.dumps({
        "schema": fr.EXPECTED_SCHEMA_BY_NODE["seed_fetch"],
        "artifact_id": "seed_snapshot",
        "task_id": f"{graph['sprint_id']}:research-evidence-to-poc",
        "run_id": graph["sprint_id"],
        "workflow_id": fr.WORKFLOW_ID,
        "node_id": "seed_fetch",
    }) + "\n", encoding="utf-8")
    seed["status"] = "passed"
    graph["node_results"]["seed_fetch"] = {"status": "passed", "verdict": "PASS"}
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    discovery = next(item for item in graph["nodes"] if item["id"] == "source_discovery")
    operator_id = fr.PHYSICAL_OPERATOR_BY_NODE["source_discovery"]
    result = gnd.dispatch_queue_item({
        "intent": "graph_node|node_id=source_discovery",
        "payload": {
            "sprint_id": graph["sprint_id"],
            "graph": str(graph_path),
            "node": discovery,
            "assignment": {"pane": f"operator:{operator_id}"},
        },
    }, dry_run=True)
    assert result["ok"] is False
    assert result["reason"] == "fixed_research_envelope_rejected"
    assert "controller evaluator receipt" in result["error"]


def test_forged_intent_binding_is_not_dispatchable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph, _graph_path, _sprints = _graph(tmp_path, monkeypatch)
    monkeypatch.setenv("SOLAR_INTENT_GATEWAY_DIR", str(tmp_path / "intents"))
    graph["intent_binding"] = {
        "required": True,
        "status": "bound",
        "intent_id": "forged",
        "manifest": str(tmp_path / "intents/forged/binding.json"),
    }
    guard = gnd._fixed_research_specialization_guard(graph)
    assert guard is not None
    assert "fixed_research_intent_binding_evidence_invalid" in guard["errors"]

    gateway = tmp_path / "intents"
    outside = tmp_path.parent / "outside-intent" / "binding.json"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text(json.dumps({
        "intent_id": "../../outside-intent",
        "sprint_id": graph["sprint_id"],
    }) + "\n", encoding="utf-8")
    graph["intent_binding"] = {
        "required": True,
        "status": "bound",
        "intent_id": "../../outside-intent",
        "manifest": str(outside),
    }
    monkeypatch.setenv("SOLAR_INTENT_GATEWAY_DIR", str(gateway))
    traversal_guard = gnd._fixed_research_specialization_guard(graph)
    assert traversal_guard is not None
    assert "fixed_research_intent_binding_evidence_invalid" in traversal_guard["errors"]


def test_part_b_requested_builds_exact_visible_single_threaded_topology(tmp_path: Path) -> None:
    pack = _pack(tmp_path / "authority")
    snapshot = tmp_path / "sprints" / "never" / "workdir" / "inputs" / "source-pack"
    graph = fr.build_fixed_research_graph(
        sprint_id="never",
        request="research plus poc",
        execution_profile="part_a_plus_poc",
        acquisition_mode="source_pack",
        source_pack_root=pack,
        authority_root=pack.parent,
        snapshot_root=snapshot,
    )
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert snapshot.is_dir()
    assert graph["execution_profile"] == {"kind": "part_a_plus_poc", "part_b": "enabled"}
    assert graph["part_b"]["status"] == "pending"
    assert graph["codex_execution"]["max_parallel"] == 1
    assert all(nodes[node_id]["status"] == "pending" for node_id in fr.PART_B_NODE_IDS)
    assert all(nodes[node_id]["condition_status"] == "enabled" for node_id in fr.PART_B_NODE_IDS)
    assert all(
        nodes[node_id]["required_operator_id"] == fr.PHYSICAL_OPERATOR_BY_NODE[node_id]
        for node_id in fr.PART_B_NODE_IDS
    )


@pytest.mark.parametrize(
    ("field", "mutate"),
    [
        ("runner", lambda payload: payload["benchmark"].__setitem__("runner", "harness/tools/other.py")),
        ("network", lambda payload: payload["benchmark"].__setitem__("network", "enabled")),
        ("timeout", lambda payload: payload["benchmark"].__setitem__("timeout_seconds", 61)),
        ("scope", lambda payload: payload["approval_scope"].__setitem__("capabilities", ["network:any"])),
        ("input_set", lambda payload: payload["benchmark"].__setitem__("inputs", [])),
    ],
)
def test_fixed_experiment_policy_semantics_reject_every_plan_expansion(
    field: str, mutate
) -> None:
    artifact = {
        "path": "artifacts/research_evidence_to_poc/final/final_acceptance.json",
        "sha256": "a" * 64,
        "schema": "research_synthesis.final_acceptance.v1",
    }
    policy = {
        "benchmark_policy": {
            "benchmark_id": "evidence-lineage-integrity-v1",
            "runner": "harness/tools/fixed_research_benchmark.py",
            "runner_sha256": "b" * 64,
            "sandbox": "linux_user_and_network_namespace",
            "network": "none",
            "timeout_max_seconds": 60,
            "capabilities": ["execute:fixed_evidence_lineage_benchmark", "network:none"],
        }
    }
    plan = {
        "benchmark": {
            "benchmark_id": "evidence-lineage-integrity-v1",
            "runner": "harness/tools/fixed_research_benchmark.py",
            "sandbox": "linux_user_and_network_namespace",
            "network": "disabled",
            "timeout_seconds": 60,
            "inputs": [dict(artifact)],
        },
        "approval_scope": {
            "capabilities": ["execute:fixed_evidence_lineage_benchmark", "network:none"],
            "benchmark_id": "evidence-lineage-integrity-v1",
            "input_sha256": ["a" * 64],
        },
    }
    handoff = {"artifacts": [dict(artifact)]}
    assert all(gnd._fixed_research_policy_plan_checks(policy, plan, handoff, "b" * 64).values())
    mutate(plan)
    checks = gnd._fixed_research_policy_plan_checks(policy, plan, handoff, "b" * 64)
    assert checks[field] is False


def _approval_waiting_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict, dict]:
    graph, graph_path, _sprints = _graph(
        tmp_path,
        monkeypatch,
        execution_profile="part_a_plus_poc",
        sid="fixed-approval-contract-test",
    )
    plan_path = (
        tmp_path
        / "sprints/fixed-approval-contract-test/workdir/artifacts/research_evidence_to_poc/poc/design/experiment_plan.json"
    )
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    scope = {
        "capabilities": ["execute:fixed_evidence_lineage_benchmark", "network:none"],
        "benchmark_id": "evidence-lineage-integrity-v1",
        "input_sha256": ["a" * 64],
    }
    plan = {
        "schema": "solar.fixed_research.experiment_plan.v1",
        "status": "awaiting_human_approval",
        "experiment_id": "evidence-lineage-integrity-v1",
        "idea": {"path": "artifacts/research_evidence_to_poc/poc/idea/idea_evaluation.json", "sha256": "b" * 64},
        "benchmark": {
            "benchmark_id": "evidence-lineage-integrity-v1",
            "runner": "harness/tools/fixed_research_benchmark.py",
            "sandbox": "linux_user_and_network_namespace",
            "network": "disabled",
            "timeout_seconds": 60,
            "inputs": [{"path": "artifacts/example.json", "sha256": "a" * 64, "schema": "example.v1"}],
            "success_criteria": {"integrity_rate": 1.0, "exit_code": 0},
        },
        "approval_scope": scope,
        "limitations": ["Deterministic approval contract test only."],
    }
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    plan_sha = _sha(plan_path.read_bytes())
    human_review = gnd.enter_node_human_review(
        graph,
        "experiment_approval",
        reason="exact_experiment_plan_human_approval_required",
        next_action="Provide exact human approval.",
        writer="deterministic_contract_test",
    )
    request = {
        "schema": "solar.fixed_research.approval_request.v1",
        "sprint_id": "fixed-approval-contract-test",
        "node_id": "experiment_approval",
        "generation": int(human_review["generation"]),
        "plan_path": "artifacts/research_evidence_to_poc/poc/design/experiment_plan.json",
        "plan_sha256": plan_sha,
        "approved_scope": scope,
        "approved_capabilities": ["execute:fixed_evidence_lineage_benchmark", "network:none"],
        "requested_at": "2026-08-17T12:00:00Z",
        "requested_by": "graph_node_dispatcher",
    }
    gnd._validate_fixed_research_approval_payload(request)
    _stage, request_path, _approval_path = gnd._fixed_research_approval_paths(
        "fixed-approval-contract-test"
    )
    gnd._write_json_atomic(request_path, request)
    gnd.save_graph(graph_path, graph)
    return graph_path, request, scope


@pytest.mark.parametrize(
    ("generation_delta", "actor", "plan_digest", "scope_mutation", "capabilities", "reason"),
    [
        (1, "human@example.test", None, None, None, "mismatch"),
        (0, "system", None, None, None, "actor"),
        (0, "human@example.test", "f" * 64, None, None, "mismatch"),
        (0, "human@example.test", None, {"benchmark_id": "other"}, None, "mismatch"),
        (0, "human@example.test", None, None, ["network:any"], "mismatch"),
    ],
)
def test_fixed_experiment_approval_rejects_stale_self_wrong_plan_scope_or_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    generation_delta: int,
    actor: str,
    plan_digest: str | None,
    scope_mutation: dict | None,
    capabilities: list[str] | None,
    reason: str,
) -> None:
    graph_path, request, scope = _approval_waiting_graph(tmp_path, monkeypatch)
    supplied_scope = dict(scope)
    supplied_scope.update(scope_mutation or {})
    result = gnd.approve_fixed_experiment(
        str(graph_path),
        expected_generation=int(request["generation"]) + generation_delta,
        actor=actor,
        statement="I approve only this exact fixed benchmark plan.",
        plan_sha256=plan_digest or request["plan_sha256"],
        approved_scope=supplied_scope,
        approved_capabilities=capabilities or request["approved_capabilities"],
    )
    assert result["ok"] is False
    assert reason in result["reason"]
    assert not gnd._fixed_research_approval_paths("fixed-approval-contract-test")[2].exists()


def test_fixed_experiment_approval_exact_human_input_resumes_but_does_not_pass_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph_path, request, scope = _approval_waiting_graph(tmp_path, monkeypatch)
    result = gnd.approve_fixed_experiment(
        str(graph_path),
        expected_generation=int(request["generation"]),
        actor="human-reviewer@example.test",
        statement="I approve only the exact evidence-lineage benchmark plan and no network access.",
        plan_sha256=request["plan_sha256"],
        approved_scope=scope,
        approved_capabilities=request["approved_capabilities"],
    )
    assert result["ok"] is True, result
    saved = gnd.load_graph(graph_path)
    node = next(item for item in saved["nodes"] if item["id"] == "experiment_approval")
    assert node["status"] == "pending"
    assert saved["node_results"]["experiment_approval"]["human_review"]["state"] == "resumed"
    approval = json.loads(Path(result["approval_path"]).read_text(encoding="utf-8"))
    assert approval["author"] == {"type": "human", "id": "human-reviewer@example.test"}
    assert approval["plan_sha256"] == request["plan_sha256"]
    assert approval["approved_scope"] == scope
    replay = gnd.approve_fixed_experiment(
        str(graph_path),
        expected_generation=int(request["generation"]),
        actor="human-reviewer@example.test",
        statement="Replay should fail.",
        plan_sha256=request["plan_sha256"],
        approved_scope=scope,
        approved_capabilities=request["approved_capabilities"],
    )
    assert replay == {"ok": False, "reason": "node_not_waiting_for_human_review"}


def test_shipped_approval_cli_resolves_fixed_contract_from_shipped_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph_path, request, scope = _approval_waiting_graph(tmp_path, monkeypatch)
    env = dict(os.environ)
    env.update(
        {
            "HARNESS_DIR": str(HARNESS),
            "SOLAR_HARNESS_DIR": str(HARNESS),
            "HARNESS_SPRINTS_DIR": str(tmp_path / "sprints"),
            "SOLAR_INTENT_GATEWAY_DIR": os.environ["SOLAR_INTENT_GATEWAY_DIR"],
        }
    )
    run = subprocess.run(
        [
            sys.executable,
            str(HARNESS / "lib" / "graph_node_dispatcher.py"),
            "approve-fixed-experiment",
            "--graph",
            str(graph_path),
            "--generation",
            str(request["generation"]),
            "--actor",
            "human-reviewer@example.test",
            "--statement",
            "I approve only this exact fixed benchmark plan.",
            "--plan-sha256",
            request["plan_sha256"],
            "--scope-json",
            json.dumps(scope, sort_keys=True),
            "--capability",
            "execute:fixed_evidence_lineage_benchmark",
            "--capability",
            "network:none",
        ],
        cwd=HARNESS.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert run.returncode == 0, (run.stdout, run.stderr)
    payload = json.loads(run.stdout)
    assert payload["ok"] is True
    assert payload["status"] == "pending"
    assert "WORKFLOW_CONTRACT_UNREGISTERED" not in run.stdout + run.stderr
    saved = gnd.load_graph(graph_path)
    assert saved["workflow_contract_id"] == fr.WORKFLOW_ID
    assert saved["node_results"]["experiment_approval"]["human_review"]["state"] == "resumed"


def test_research_experiment_approval_capsule_requires_exact_fixed_b4_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, _graph_path, _sprints = _graph(
        tmp_path,
        monkeypatch,
        execution_profile="part_a_plus_poc",
        sid="fixed-approval-capsule-authority",
    )
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setattr(gnd, "HARNESS_DIR", HARNESS)
    monkeypatch.setattr(gnd, "WORKFLOWS_DIR", HARNESS / "config" / "workflows", raising=False)
    approval = next(item for item in graph["nodes"] if item["id"] == "experiment_approval")
    assert approval["capability_capsule_id"] == "cap.research-experiment-approval"
    assert approval["allowed_capsules"] == ["cap.research-experiment-approval"]
    exact_plan = compile_execution_plan_for_node(
        approval,
        request_type="verification",
        registry_path=HARNESS / "config" / "capability-capsules.registry.yaml",
        operators_path=HARNESS / "config" / "physical-operators.json",
    )["capsule_plan"]
    assert exact_plan["capability_capsule_id"] == "cap.research-experiment-approval"
    assert exact_plan["required_resource_capsules"] == []
    assert not any(
        str(item.get("source_capsule_id") or "").startswith("resource.")
        for item in exact_plan["proof_obligations"]
    )
    assert gnd._workflow_contract_guard(graph) is None

    wrong_contract = json.loads(json.dumps(graph))
    wrong_contract["workflow_contract_id"] = "research.autosci.v1"
    wrong_contract_guard = gnd._workflow_contract_guard(wrong_contract)
    assert wrong_contract_guard is not None
    assert wrong_contract_guard["reason"] == "workflow_contract_guard_failed"

    wrong_node = json.loads(json.dumps(graph))
    mutated = next(item for item in wrong_node["nodes"] if item["id"] == "experiment_approval")
    mutated["id"] = "generic_experiment_approval"
    wrong_node_guard = gnd._workflow_contract_guard(wrong_node)
    assert wrong_node_guard is not None
    assert wrong_node_guard["reason"] == "workflow_contract_guard_failed"
    assert any("STRUCTURE_MISMATCH" in error for error in wrong_node_guard["errors"])


def test_fixed_experiment_approval_worker_validates_separate_request_and_human_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sid = "approval-worker-contract-test"
    work_dir = tmp_path / "workdir"
    work_dir.mkdir()
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text("{}\n", encoding="utf-8")
    design = work_dir / "artifacts/research_evidence_to_poc/poc/design/experiment_plan.json"
    design.parent.mkdir(parents=True)
    scope = {
        "capabilities": ["execute:fixed_evidence_lineage_benchmark", "network:none"],
        "benchmark_id": "evidence-lineage-integrity-v1",
        "input_sha256": ["a" * 64],
    }
    design.write_text(json.dumps({
        "schema": "solar.fixed_research.experiment_plan.v1",
        "status": "awaiting_human_approval",
        "experiment_id": "evidence-lineage-integrity-v1",
        "approval_scope": scope,
    }) + "\n", encoding="utf-8")
    plan_sha = _sha(design.read_bytes())
    stage = work_dir / "artifacts/research_evidence_to_poc/poc/approval"
    stage.mkdir(parents=True)
    request_path = stage / "approval_request.json"
    approval_path = stage / "human_approval.json"
    request = {
        "schema": "solar.fixed_research.approval_request.v1",
        "sprint_id": sid,
        "node_id": "experiment_approval",
        "generation": 1,
        "plan_path": str(design.relative_to(work_dir)),
        "plan_sha256": plan_sha,
        "approved_scope": scope,
        "approved_capabilities": ["execute:fixed_evidence_lineage_benchmark", "network:none"],
        "requested_at": "2026-08-17T12:00:00Z",
        "requested_by": "graph_node_dispatcher",
    }
    request_path.write_text(json.dumps(request) + "\n", encoding="utf-8")
    approval = {
        "schema": "solar.fixed_research.human_approval.v1",
        "decision": "approved",
        "sprint_id": sid,
        "node_id": "experiment_approval",
        "generation": 1,
        "actor": "human-reviewer@example.test",
        "author": {"type": "human", "id": "human-reviewer@example.test"},
        "statement": "I approve only this exact benchmark.",
        "plan_path": str(design.relative_to(work_dir)),
        "plan_sha256": plan_sha,
        "approved_scope": scope,
        "approved_capabilities": ["execute:fixed_evidence_lineage_benchmark", "network:none"],
        "approval_request_sha256": _sha(request_path.read_bytes()),
        "approved_at": "2026-08-17T12:01:00Z",
    }
    approval_path.write_text(json.dumps(approval) + "\n", encoding="utf-8")
    envelope = {
        "task_id": "approval-worker",
        "sprint_id": sid,
        "node_id": "experiment_approval",
        "operator_id": fr.PHYSICAL_OPERATOR_BY_NODE["experiment_approval"],
        "runner_contract": fr.WORKFLOW_ID,
        "graph_path": str(graph_path),
        "handoff_path": str(tmp_path / f"{sid}.experiment_approval-handoff.md"),
        "work_dir": str(work_dir),
        "inputs": {
            "logical_operator": "ScientificExperimentApprovalValidator",
            "expected_schema": fr.EXPECTED_SCHEMA_BY_NODE["experiment_approval"],
            "declared_outputs": [
                {"path": str(stage.relative_to(work_dir)), "type": "directory"},
                {"path": str((stage / "experiment_approval.json").relative_to(work_dir)), "type": "json"},
            ],
            "dependency_artifacts": [{
                "artifact_id": "experiment_design",
                "path": str(design.relative_to(work_dir)),
                "schema": "solar.fixed_research.experiment_plan.v1",
                "sha256": plan_sha,
            }],
            "approval_controls": {
                "request": {"path": str(request_path.relative_to(work_dir)), "schema": request["schema"], "sha256": _sha(request_path.read_bytes())},
                "approval": {"path": str(approval_path.relative_to(work_dir)), "schema": approval["schema"], "sha256": _sha(approval_path.read_bytes())},
            },
            "operator_payload": {"request": "Approve the exact benchmark.", "execution_profile": "part_a_plus_poc"},
        },
        "outputs": {"result_path": str((stage / "research_node_result.json").relative_to(work_dir))},
        "lease_ttl_seconds": 30,
    }
    run = _invoke_adapter(envelope, tmp_path)
    assert run.returncode == 0, (run.stdout, run.stderr)
    artifact = json.loads((stage / "experiment_approval.json").read_text(encoding="utf-8"))
    assert artifact["status"] == "approved"
    assert artifact["human_approval"]["actor"] == "human-reviewer@example.test"

    # B4 is a controller-evidence gate, not repository work.  Its capsule must
    # therefore prove the exact approval artifact without inventing a GitHub or
    # repo-workspace authority requirement.  Exercise the normal proof/PASS
    # seam with no workspace binding and retain the generic verification
    # capsule as the fail-closed control.
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "_workspace_binding", None)
    approval_node = {
        "id": "experiment_approval",
        "goal": "Validate the exact controller request and attributable human approval.",
        "type": "verification",
        "task_type": "verification",
        "logical_operator": "ScientificExperimentApprovalValidator",
        "capability_capsule_id": "cap.research-experiment-approval",
        "allowed_capsules": ["cap.research-experiment-approval"],
        "depends_on": [],
        "write_scope": [str(stage), str(stage / "experiment_approval.json")],
        "artifacts": {"experiment_approval_json": str(stage / "experiment_approval.json")},
        "status": "reviewing",
    }
    compiled = compile_execution_plan_for_node(
        approval_node,
        request_type="verification",
        registry_path=HARNESS / "config" / "capability-capsules.registry.yaml",
        operators_path=HARNESS / "config" / "physical-operators.json",
    )
    capsule_plan = compiled["capsule_plan"]
    assert capsule_plan["capability_capsule_id"] == "cap.research-experiment-approval"
    assert capsule_plan["required_resource_capsules"] == []
    assert not any(
        str(item.get("source_capsule_id") or "").startswith("resource.")
        or str(item.get("field") or "") == "resource_binding"
        for item in capsule_plan["proof_obligations"]
    )
    assert any(
        item.get("requirement") == "output_present"
        and item.get("field") == "experiment_approval_json"
        for item in capsule_plan["proof_obligations"]
    )
    assert not any(item.get("stage_kind") == "adapter" for item in capsule_plan["stages"])
    approval_node["proof_obligations"] = capsule_plan["proof_obligations"]
    graph = {
        "sprint_id": sid,
        "nodes": [approval_node],
        "node_results": {"experiment_approval": {"status": "reviewing"}},
    }
    proof_handoff = tmp_path / f"{sid}.experiment_approval-handoff.md"
    proof_handoff.write_text("# Experiment approval\n\nExact controller approval validated.\n", encoding="utf-8")
    eval_path = tmp_path / f"{sid}.experiment_approval-eval.json"
    eval_path.write_text(
        json.dumps({"node_id": "experiment_approval", "verdict": "PASS"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / f"{sid}.experiment_approval-eval.md").write_text(
        "# Deterministic evaluation\n\nPASS\n",
        encoding="utf-8",
    )
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    passed = gnd.node_verdict(
        str(graph_path),
        "experiment_approval",
        "pass",
        eval_json=str(eval_path),
        dry_run=True,
        dispatch_downstream=False,
    )
    assert passed["ok"] is True, passed
    assert passed["status"] == "passed"
    resource = json.loads(
        (tmp_path / f"{sid}.experiment_approval-resource_binding.json").read_text(encoding="utf-8")
    )
    assert resource["bound"] is False
    assert passed["proof_gate"]["ok"] is True

    generic_node = dict(approval_node)
    generic_node["status"] = "reviewing"
    generic_node["capability_capsule_id"] = "cap.requirement-compiler-verification"
    generic_node["allowed_capsules"] = ["cap.requirement-compiler-verification"]
    generic_plan = compile_execution_plan_for_node(
        generic_node,
        request_type="verification",
        registry_path=HARNESS / "config" / "capability-capsules.registry.yaml",
        operators_path=HARNESS / "config" / "physical-operators.json",
    )["capsule_plan"]
    assert "resource.github-readonly" in generic_plan["required_resource_capsules"]


    assert any(
        item.get("field") == "resource_binding"
        or item.get("requirement") in {"check.resource_binding_written", "resource_binding exists"}
        for item in generic_plan["proof_obligations"]
    )
    generic_node["proof_obligations"] = generic_plan["proof_obligations"]
    generic_graph = {
        "sprint_id": sid,
        "nodes": [generic_node],
        "node_results": {"experiment_approval": {"status": "reviewing"}},
    }
    graph_path.write_text(json.dumps(generic_graph, indent=2) + "\n", encoding="utf-8")
    blocked = gnd.node_verdict(
        str(graph_path),
        "experiment_approval",
        "pass",
        eval_json=str(eval_path),
        dry_run=True,
        dispatch_downstream=False,
    )
    assert blocked["ok"] is False
    assert blocked["reason"] == "proof_obligations_failed"
    assert blocked["proof_gate"]["ok"] is False

    artifact_before = (stage / "experiment_approval.json").read_bytes()
    request_before = request_path.read_bytes()
    handoff_path = Path(envelope["handoff_path"])
    handoff_before = handoff_path.read_bytes()
    stage_before = {
        str(path.relative_to(stage)): path.read_bytes()
        for path in stage.rglob("*")
        if path.is_file() and path != request_path
    }
    request["requested_at"] = "2026-08-17T12:00:01Z"
    request_path.write_text(json.dumps(request) + "\n", encoding="utf-8")
    envelope["inputs"]["approval_controls"]["request"]["sha256"] = _sha(request_path.read_bytes())
    request_tamper = _invoke_adapter(envelope, tmp_path)
    assert request_tamper.returncode == 2
    assert "does not match" in json.loads(request_tamper.stdout)["error"]
    assert (stage / "experiment_approval.json").read_bytes() == artifact_before
    assert handoff_path.read_bytes() == handoff_before
    assert {
        str(path.relative_to(stage)): path.read_bytes()
        for path in stage.rglob("*")
        if path.is_file() and path != request_path
    } == stage_before

    request_path.write_bytes(request_before)
    envelope["inputs"]["approval_controls"]["request"]["sha256"] = _sha(request_before)
    approval["plan_sha256"] = "f" * 64
    approval_path.write_text(json.dumps(approval) + "\n", encoding="utf-8")
    envelope["inputs"]["approval_controls"]["approval"]["sha256"] = _sha(approval_path.read_bytes())
    rejected = _invoke_adapter(envelope, tmp_path)
    assert rejected.returncode == 2
    assert "does not match" in json.loads(rejected.stdout)["error"]
    assert (stage / "experiment_approval.json").read_bytes() == artifact_before


def test_fixed_part_b_capsules_are_exact_and_have_no_repository_resource_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, _graph_path, _sprints = _graph(
        tmp_path,
        monkeypatch,
        execution_profile="part_a_plus_poc",
        sid="fixed-part-b-capsule-authority",
    )
    # Part B's science stages now bind the AutoSci capsules so they run through
    # the AutoSci bridge instead of the Solar reimplementation. The
    # no-repository-resource requirement is unchanged and still asserted below.
    expected = {
        "experiment_run": "cap.research-external-experiment-run",
        "claim_verification": "cap.research-external-claim-verification",
        "final_delivery": "cap.research-external-report-delivery",
    }
    for node_id, capsule_id in expected.items():
        node = next(item for item in graph["nodes"] if item["id"] == node_id)
        assert node["capability_capsule_id"] == capsule_id
        assert node["allowed_capsules"] == [capsule_id]
        compiled = compile_execution_plan_for_node(
            node,
            request_type=str(node.get("task_type") or ""),
            registry_path=HARNESS / "config" / "capability-capsules.registry.yaml",
            operators_path=HARNESS / "config" / "physical-operators.json",
        )["capsule_plan"]
        assert compiled["capability_capsule_id"] == capsule_id
        assert compiled["required_resource_capsules"] == []
        assert not any(
            str(item.get("source_capsule_id") or "").startswith("resource.")
            for item in compiled["proof_obligations"]
        )
        assert not any(item.get("stage_kind") == "adapter" for item in compiled["stages"])

    run_node = next(item for item in graph["nodes"] if item["id"] == "experiment_run")
    evidence_outputs = {
        Path(str(item["path"])).name: str(item.get("evidence_schema") or "")
        for item in run_node["outputs"]
        if item.get("evidence_schema")
    }
    assert evidence_outputs == {
        "benchmark_raw.json": "solar.fixed_research.benchmark_raw.v1",
        "stderr.json": "solar.fixed_research.command_stream.v1",
        "stdout.txt": "text/plain",
    }

    generic = dict(next(item for item in graph["nodes"] if item["id"] == "experiment_run"))
    generic["id"] = "generic_repo_verification"
    generic["capability_capsule_id"] = "cap.requirement-compiler-verification"
    generic["allowed_capsules"] = ["cap.requirement-compiler-verification"]
    generic_plan = compile_execution_plan_for_node(
        generic,
        request_type="verification",
        registry_path=HARNESS / "config" / "capability-capsules.registry.yaml",
        operators_path=HARNESS / "config" / "physical-operators.json",
    )["capsule_plan"]
    assert "resource.github-readonly" in generic_plan["required_resource_capsules"]


def test_fixed_part_a_source_capsules_match_exact_stage_workers_and_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, _graph_path, _sprints = _graph(tmp_path, monkeypatch)
    expected = {
        "seed_fetch": "cap.research-seed-snapshot",
        "source_discovery": "cap.research-public-source-discovery",
        "source_validation": "cap.research-source-validation",
    }
    for node_id, capsule_id in expected.items():
        node = next(item for item in graph["nodes"] if item["id"] == node_id)
        assert node["capability_capsule_id"] == capsule_id
        assert node["allowed_capsules"] == [capsule_id]
        assert node["required_operator_id"] == fr.PHYSICAL_OPERATOR_BY_NODE[node_id]
        compiled = compile_execution_plan_for_node(
            node,
            request_type="research",
            registry_path=HARNESS / "config" / "capability-capsules.registry.yaml",
            operators_path=HARNESS / "config" / "physical-operators.json",
        )["capsule_plan"]
        assert compiled["capability_capsule_id"] == capsule_id
        assert compiled["required_resource_capsules"] == []

    manifests = {
        item["capability_capsule_id"]: item
        for item in fr.wc.load_capsule_registry(HARNESS / "config").values()
        if isinstance(item, dict) and item.get("capability_capsule_id")
    }
    assert manifests[expected["seed_fetch"]]["task_type_in"] == ["research"]
    assert manifests[expected["source_discovery"]]["task_type_in"] == ["research"]
    assert manifests[expected["source_validation"]]["task_type_in"] == ["research"]


def test_live_search_intake_is_ready_without_a_source_pack(tmp_path: Path) -> None:
    sprints = tmp_path / "sprints"
    result = wi.create_contract_sprint(
        workflow_id=fr.WORKFLOW_ID,
        request="Research retrieval augmented generation evaluation methods.",
        inputs={
            "execution_profile": "part_a_only",
            "acquisition_mode": "live_search",
            "retrieval_policy": fr.PUBLIC_RETRIEVAL_POLICY_ID,
        },
        sprints_dir=sprints,
        workflows_dir=HARNESS / "config" / "workflows",
    )
    sid = result["sprint_id"]
    status = json.loads((sprints / f"{sid}.status.json").read_text(encoding="utf-8"))
    graph = json.loads((sprints / f"{sid}.task_graph.json").read_text(encoding="utf-8"))
    assert graph["acquisition_mode"]["kind"] == "live_search"
    assert graph["source_pack_authority"]["status"] == "not_available"
    assert graph["retrieval_policy"]["policy_id"] == fr.PUBLIC_RETRIEVAL_POLICY_ID
    assert status["status"] == "active"
    assert status["phase"] == "planning_complete"
    assert status["handoff_to"] == "builder_main"


def test_direct_adapter_runs_real_fixed_no_network_benchmark_without_controller_closeout_claim(
    tmp_path: Path,
) -> None:
    sid = "real-fixed-benchmark-test"
    work_dir = tmp_path / "workdir"
    work_dir.mkdir()
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text("{}\n", encoding="utf-8")
    accepted = work_dir / "artifacts/research_evidence_to_poc/final/final_acceptance.json"
    accepted.parent.mkdir(parents=True)
    accepted.write_text(json.dumps({
        "schema": "research_synthesis.final_acceptance.v1",
        "accepted": True,
        "decision": "accepted",
        "gate_outcome": "pass",
    }) + "\n", encoding="utf-8")
    accepted_sha = _sha(accepted.read_bytes())
    handoff_path = work_dir / "artifacts/research_evidence_to_poc/poc/handoff/poc_handoff.json"
    handoff_path.parent.mkdir(parents=True)
    handoff = {
        "schema": "solar.fixed_research.poc_handoff.v1",
        "status": "accepted",
        "artifacts": [{
            "node_id": "final_acceptance",
            "artifact_id": "final_acceptance",
            "path": str(accepted.relative_to(work_dir)),
            "schema": "research_synthesis.final_acceptance.v1",
            "sha256": accepted_sha,
            "bytes": accepted.stat().st_size,
        }],
    }
    handoff_path.write_text(json.dumps(handoff) + "\n", encoding="utf-8")
    plan_path = work_dir / "artifacts/research_evidence_to_poc/poc/design/experiment_plan.json"
    plan_path.parent.mkdir(parents=True)
    plan = {
        "schema": "solar.fixed_research.experiment_plan.v1",
        "status": "awaiting_human_approval",
        "experiment_id": "evidence-lineage-integrity-v1",
        "benchmark": {
            "benchmark_id": "evidence-lineage-integrity-v1",
            "runner": "harness/tools/fixed_research_benchmark.py",
            "sandbox": "linux_user_and_network_namespace",
            "network": "disabled",
            "timeout_seconds": 60,
            "inputs": [{"path": str(accepted.relative_to(work_dir)), "sha256": accepted_sha, "schema": "research_synthesis.final_acceptance.v1"}],
            "success_criteria": {"integrity_rate": 1.0, "exit_code": 0},
        },
    }
    plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
    approval_path = work_dir / "artifacts/research_evidence_to_poc/poc/approval/experiment_approval.json"
    approval_path.parent.mkdir(parents=True)
    approval = {
        "schema": "solar.fixed_research.experiment_approval.v1",
        "status": "approved",
        "plan": {"path": str(plan_path.relative_to(work_dir)), "sha256": _sha(plan_path.read_bytes())},
    }
    approval_path.write_text(json.dumps(approval) + "\n", encoding="utf-8")
    run_stage = work_dir / "artifacts/research_evidence_to_poc/poc/run"
    dependencies = [
        {"artifact_id": "poc_handoff", "path": str(handoff_path.relative_to(work_dir)), "schema": handoff["schema"], "sha256": _sha(handoff_path.read_bytes())},
        {"artifact_id": "experiment_design", "path": str(plan_path.relative_to(work_dir)), "schema": plan["schema"], "sha256": _sha(plan_path.read_bytes())},
        {"artifact_id": "experiment_approval", "path": str(approval_path.relative_to(work_dir)), "schema": approval["schema"], "sha256": _sha(approval_path.read_bytes())},
        {"artifact_id": "benchmark-input-001", "path": str(accepted.relative_to(work_dir)), "schema": "research_synthesis.final_acceptance.v1", "sha256": accepted_sha},
    ]
    run_envelope = {
        "task_id": "real-fixed-benchmark",
        "sprint_id": sid,
        "node_id": "experiment_run",
        "operator_id": fr.PHYSICAL_OPERATOR_BY_NODE["experiment_run"],
        "runner_contract": fr.WORKFLOW_ID,
        "graph_path": str(graph_path),
        "handoff_path": str(tmp_path / f"{sid}.experiment_run-handoff.md"),
        "work_dir": str(work_dir),
        "inputs": {
            "logical_operator": "ScientificExperimentRunner",
            "expected_schema": fr.EXPECTED_SCHEMA_BY_NODE["experiment_run"],
            "declared_outputs": [
                {"path": str(run_stage.relative_to(work_dir)), "type": "directory"},
                {"path": str((run_stage / "experiment_result.json").relative_to(work_dir)), "type": "json"},
                {"path": str((run_stage / "benchmark_raw.json").relative_to(work_dir)), "type": "json"},
                {"path": str((run_stage / "stdout.txt").relative_to(work_dir)), "type": "text"},
                {"path": str((run_stage / "stderr.json").relative_to(work_dir)), "type": "json"},
            ],
            "dependency_artifacts": dependencies,
            "operator_payload": {"request": "Run the exact approved integrity benchmark.", "execution_profile": "part_a_plus_poc"},
        },
        "outputs": {"result_path": str((run_stage / "research_node_result.json").relative_to(work_dir))},
        "lease_ttl_seconds": 60,
    }
    run = _invoke_adapter(run_envelope, tmp_path)
    assert run.returncode == 0, (run.stdout, run.stderr)
    result = json.loads((run_stage / "experiment_result.json").read_text(encoding="utf-8"))
    raw_path = run_stage / "benchmark_raw.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    assert result["status"] == "completed"
    assert result["sandbox"] == {"kind": "linux_user_and_network_namespace", "network": "disabled", "command_allowlisted": True}
    assert result["execution"]["exit_code"] == 0
    assert result["metrics"]["integrity_rate"] == 1.0
    assert result["raw_result_sha256"] == _sha(raw_path.read_bytes())
    assert raw["network_namespace"] == "isolated_by_unshare"
    assert (run_stage / "stdout.txt").is_file()
    stderr_record = json.loads((run_stage / "stderr.json").read_text(encoding="utf-8"))
    assert stderr_record["stream"] == "stderr"
    assert stderr_record["bytes"] == 0


def test_workflow_intake_ignores_caller_authority_override_and_leaves_no_sprint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    policy_root = tmp_path / "policy-sources"
    policy_root.mkdir()
    outside_pack = _pack(tmp_path / "caller-selected")
    sprints = tmp_path / "sprints"
    monkeypatch.setenv("SOLAR_RESEARCH_SOURCE_PACK_ROOT", str(policy_root))
    with pytest.raises(wi.WorkflowIntakeError, match="escapes authority_root"):
        wi.create_contract_sprint(
            workflow_id=fr.WORKFLOW_ID,
            request="Research a bounded topic.",
            workspace_root=str(outside_pack.parent),
            inputs={
                "execution_profile": "part_a_only",
                "acquisition_mode": "source_pack",
                "source_pack_root": str(outside_pack),
                "authority_root": "/",
            },
            sprints_dir=sprints,
            intent_id="authority-override-test",
        )
    assert not sprints.exists() or not list(sprints.iterdir())


def test_failed_real_intent_binding_removes_new_graph_and_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    policy_root = tmp_path / "policy-sources"
    pack = _pack(policy_root)
    sprints = tmp_path / "sprints"
    intents = tmp_path / "intents"
    monkeypatch.setenv("SOLAR_RESEARCH_SOURCE_PACK_ROOT", str(policy_root))
    monkeypatch.setenv("SOLAR_INTENT_GATEWAY_DIR", str(intents))
    # Force a fresh import so intent_gateway observes this test-owned directory.
    sys.modules.pop("intent_gateway", None)
    with pytest.raises(wi.WorkflowIntakeError, match="INTENT_BIND_FAILED"):
        wi.create_contract_sprint(
            workflow_id=fr.WORKFLOW_ID,
            request="Research a bounded topic.",
            inputs={
                "execution_profile": "part_a_only",
                "acquisition_mode": "source_pack",
                "source_pack_root": str(pack),
            },
            sprints_dir=sprints,
            intent_id="intent-does-not-exist",
        )
    assert not list(sprints.glob("sprint-*"))


def test_shipped_shell_routes_research_before_planner_and_binds_intent(tmp_path: Path) -> None:
    policy_root = tmp_path / "sources"
    pack = _pack(policy_root)
    sprints = tmp_path / "sprints"
    intents = tmp_path / "intents"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = dict(os.environ)
    env.update({
        "HARNESS_DIR": str(HARNESS),
        "HARNESS_SPRINTS_DIR": str(sprints),
        "SOLAR_INTENT_GATEWAY_DIR": str(intents),
        "SOLAR_RESEARCH_SOURCE_PACK_ROOT": str(policy_root),
        "SOLAR_RESEARCH_SOURCE_PACK": str(pack),
        "SOLAR_RESEARCH_EXECUTION_PROFILE": "part_a_plus_poc",
        "SOLAR_INTAKE_WORKSPACE_ROOT": str(workspace),
        "SOLAR_WORKFLOW_ROUTER": "1",
        "SOLAR_PRODUCT_MODE": "0",
        "SOLAR_INTENT_REWRITE_CMD": "",
    })
    result = subprocess.run(
        [
            "bash",
            str(HARNESS / "solar-harness.sh"),
            "intake",
            "--no-dispatch",
            "--request",
            "Research retrieval evaluation methods and produce a source-backed report.",
        ],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert fr.WORKFLOW_ID in result.stdout
    graphs = list(sprints.glob("*.task_graph.json"))
    assert len(graphs) == 1
    graph = json.loads(graphs[0].read_text(encoding="utf-8"))
    assert graph["workflow_contract_id"] == fr.WORKFLOW_ID
    assert graph["execution_profile"] == {"kind": "part_a_plus_poc", "part_b": "enabled"}
    assert graph["experiment_policy"] == {"mode": "interactive_exact_plan", "policy_id": ""}
    assert all(
        next(node for node in graph["nodes"] if node["id"] == node_id)["status"] == "pending"
        for node_id in fr.PART_B_NODE_IDS
    )
    assert graph["plan_compile_required"] is False
    assert graph["intent_binding"]["status"] == "bound"
    sid = graph["sprint_id"]
    status = json.loads((sprints / f"{sid}.status.json").read_text(encoding="utf-8"))
    assert status["handoff_to"] == "builder_main"
    assert status["target_role"] == "builder_main"
    assert (sprints / f"{sid}.raw_intent.json").exists()
    assert not list(sprints.glob("*.epic.json"))


def test_shipped_shell_one_command_persists_exact_one_shot_experiment_policy(tmp_path: Path) -> None:
    policy_root = tmp_path / "sources"
    pack = _pack(policy_root)
    sprints = tmp_path / "sprints"
    intents = tmp_path / "intents"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    request = "Research retrieval evaluation methods and produce a source-backed report."
    env = dict(os.environ)
    env.update({
        "HARNESS_DIR": str(HARNESS),
        "HARNESS_SPRINTS_DIR": str(sprints),
        "SOLAR_INTENT_GATEWAY_DIR": str(intents),
        "SOLAR_RESEARCH_SOURCE_PACK_ROOT": str(policy_root),
        "SOLAR_RESEARCH_SOURCE_PACK": str(pack),
        "SOLAR_RESEARCH_EXECUTION_PROFILE": "part_a_plus_poc",
        "SOLAR_RESEARCH_EXPERIMENT_POLICY": fr.EXPERIMENT_POLICY_ID,
        "SOLAR_RESEARCH_EXPERIMENT_POLICY_ACTOR": "user",
        "SOLAR_RESEARCH_EXPERIMENT_POLICY_STATEMENT": "no need to pause at B4 no pauses",
        "SOLAR_INTAKE_WORKSPACE_ROOT": str(workspace),
        "SOLAR_WORKFLOW_ROUTER": "1",
        "SOLAR_PRODUCT_MODE": "0",
        "SOLAR_INTENT_REWRITE_CMD": "",
    })
    result = subprocess.run(
        [
            "bash",
            str(HARNESS / "solar-harness.sh"),
            "intake",
            "--no-dispatch",
            "--request",
            request,
        ],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    graph_path = next(sprints.glob("*.task_graph.json"))
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    assert graph["workflow_contract_id"] == fr.WORKFLOW_ID
    assert graph["experiment_policy"]["mode"] == "policy_preauthorized"
    assert graph["experiment_policy"]["policy_id"] == fr.EXPERIMENT_POLICY_ID
    sid = graph["sprint_id"]
    policy_path = sprints / sid / "workdir" / graph["experiment_policy"]["path"]
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    assert _sha(policy_path.read_bytes()) == graph["experiment_policy"]["sha256"]
    assert policy["actor"] == "user"
    assert policy["statement"] == "no need to pause at B4 no pauses"
    assert policy["request_sha256"] == _sha(request.encode("utf-8"))
    assert policy["benchmark_policy"] == {
        "benchmark_id": "evidence-lineage-integrity-v1",
        "runner": "harness/tools/fixed_research_benchmark.py",
        "runner_sha256": _sha((HARNESS / "tools/fixed_research_benchmark.py").read_bytes()),
        "sandbox": "linux_user_and_network_namespace",
        "network": "none",
        "timeout_max_seconds": 60,
        "capabilities": ["execute:fixed_evidence_lineage_benchmark", "network:none"],
    }
    assert not list(sprints.glob("*.epic.json"))


def test_planner_selected_intake_submits_fixed_a1_to_real_operator_inbox(
    tmp_path: Path,
) -> None:
    policy_root = tmp_path / "sources"
    pack = _pack(policy_root)
    runtime_harness = tmp_path / "installed-harness"
    runtime_harness.mkdir()
    for name in ("lib", "plugins", "personas", "config"):
        _symlink_or_skip(runtime_harness / name, HARNESS / name, target_is_directory=True)
    sprints = runtime_harness / "sprints"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = dict(os.environ)
    env.update({
        "HARNESS_DIR": str(runtime_harness),
        "SOLAR_HARNESS_DIR": str(runtime_harness),
        "HARNESS_SPRINTS_DIR": str(sprints),
        "SOLAR_INTENT_GATEWAY_DIR": str(runtime_harness / "intents"),
        "SOLAR_RESEARCH_SOURCE_PACK_ROOT": str(policy_root),
        "SOLAR_RESEARCH_SOURCE_PACK": str(pack),
        "SOLAR_INTAKE_WORKSPACE_ROOT": str(workspace),
        "SOLAR_KNOWLEDGE_RAW_DIR": str(tmp_path / "knowledge-raw"),
        "SOLAR_MULTI_TASK_OPERATORS": str(HARNESS / "config" / "physical-operators.json"),
        "SOLAR_OPERATORD_AUTO_KICK": "0",
        "SOLAR_WORKFLOW_ROUTER": "1",
        "SOLAR_PLANNER_SELECTED_WORKFLOW_ID": fr.WORKFLOW_ID,
        "SOLAR_PRODUCT_MODE": "0",
        "SOLAR_INTENT_REWRITE_CMD": "",
    })
    result = subprocess.run(
        [
            "bash",
            str(HARNESS / "solar-harness.sh"),
            "intake",
            "--json",
            "--request",
            "Research retrieval evaluation methods and produce a source-backed report.",
        ],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    receipt = json.loads(result.stdout)
    assert receipt["ok"] is True
    assert receipt["dispatch_requested"] is True
    assert receipt["autopilot_returncode"] == 0
    graph_path = next(sprints.glob("*.task_graph.json"))
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    state = json.loads(
        (sprints / f"{graph['sprint_id']}.task_dag.state.json").read_text(encoding="utf-8")
    )
    seed_state = state["node_results"]["seed_fetch"]
    assert seed_state["status"] == "dispatched"
    assert seed_state["assigned_to"] == (
        "operator:" + fr.PHYSICAL_OPERATOR_BY_NODE["seed_fetch"]
    )
    operator_id = fr.PHYSICAL_OPERATOR_BY_NODE["seed_fetch"]
    inbox = runtime_harness / "run/operator-inbox" / operator_id
    tasks = list(inbox.glob("*.json"))
    assert len(tasks) == 1
    queued = json.loads(tasks[0].read_text(encoding="utf-8"))
    assert queued["operator_id"] == operator_id
    assert queued["runner_contract"] == fr.WORKFLOW_ID


def test_long_research_reaches_planner_with_fixed_template_candidate(tmp_path: Path) -> None:
    policy_root = tmp_path / "sources"
    pack = _pack(policy_root)

    def run(prompt: str, name: str) -> tuple[subprocess.CompletedProcess[str], Path]:
        root = tmp_path / name
        sprints = root / "sprints"
        workspace = root / "workspace"
        workspace.mkdir(parents=True)
        env = dict(os.environ)
        env.update({
            "HARNESS_DIR": str(HARNESS),
            "HARNESS_SPRINTS_DIR": str(sprints),
            "SOLAR_INTENT_GATEWAY_DIR": str(root / "intents"),
            "SOLAR_RESEARCH_SOURCE_PACK_ROOT": str(policy_root),
            "SOLAR_RESEARCH_SOURCE_PACK": str(pack),
            "SOLAR_INTAKE_WORKSPACE_ROOT": str(workspace),
            "SOLAR_WORKFLOW_ROUTER": "1",
            "SOLAR_PRODUCT_MODE": "0",
            "SOLAR_INTENT_REWRITE_CMD": "",
        })
        completed = subprocess.run(
            ["bash", str(HARNESS / "solar-harness.sh"), "intake", "--no-dispatch", "--request", prompt],
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        return completed, sprints

    long_research = "Research and compare retrieval evaluation methods across public evidence. " + (
        "Explain methods, results, limitations, disagreements, and evidence gaps with source-linked support. " * 12
    )
    result, sprints = run(long_research, "long-research")
    assert result.returncode == 0, result.stdout + result.stderr
    graphs = [json.loads(path.read_text(encoding="utf-8")) for path in sprints.glob("*.task_graph.json")]
    assert len(graphs) == 1
    assert graphs[0].get("workflow_contract_id") != fr.WORKFLOW_ID
    assert not list(sprints.glob("*.epic.json"))
    requirement_ir = json.loads(next(sprints.glob("*.requirement_ir.json")).read_text(encoding="utf-8"))
    candidates = requirement_ir["planner_hints"]["workflow_candidates"]
    assert candidates[0]["workflow_id"] == fr.WORKFLOW_ID
    assert candidates[0]["selection_authority"] == "planner"
    assert candidates[0]["auto_instantiate"] is False
    status = json.loads(next(sprints.glob("*.status.json")).read_text(encoding="utf-8"))
    assert status["handoff_to"] == "planner"

    for name, prompt, expected_request_type in (
        ("software", "Implement a Python CLI command and add regression tests for its parser.", "implementation"),
        ("debug", "Debug the scheduler exception and fix the failing stack trace in graph dispatch.", "full_prd"),
    ):
        result, sprints = run(prompt, name)
        assert result.returncode == 0, (name, result.stdout, result.stderr)
        fixed_graphs = []
        for path in sprints.glob("*.task_graph.json"):
            try:
                if json.loads(path.read_text(encoding="utf-8")).get("workflow_contract_id") == fr.WORKFLOW_ID:
                    fixed_graphs.append(path)
            except Exception:
                pass
        assert not fixed_graphs, (name, result.stdout, result.stderr)
        generic_graphs = list(sprints.glob("*.task_graph.json"))
        requirement_irs = list(sprints.glob("*.requirement_ir.json"))
        statuses = list(sprints.glob("*.status.json"))
        assert len(generic_graphs) == len(requirement_irs) == len(statuses) == 1
        requirement_ir = json.loads(requirement_irs[0].read_text(encoding="utf-8"))
        status = json.loads(statuses[0].read_text(encoding="utf-8"))
        assert requirement_ir["request_type"] == expected_request_type
        assert requirement_ir["lane_hint"] == "delivery"
        assert status["handoff_to"] == "planner"
        assert status["target_role"] == "planner"


def test_legacy_autosci_contract_and_24_node_limit_are_unchanged() -> None:
    path = HARNESS / "config/workflows/research.autosci.v1.workflow.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    assert contract["workflow_id"] == "research.autosci.v1"
    assert contract["plan_limits"]["max_nodes"] == 24


def test_exactly_bound_acquisition_node_is_not_diverted_to_human_search() -> None:
    """A2 declares source.search / research.source.web / research.source.academic
    because its command worker queries those public providers.  Those strings are
    also in HUMAN_SEARCH_CAPABILITIES, so before this guard the generic
    human-in-the-loop lane preempted the exact worker: the node parked at
    waiting_human_search with a `general` profile and the node label
    ("A2 · Source acquisition") as the search query, which is precisely the
    generic fallback this workflow forbids.
    """
    node = {
        "id": "source_discovery",
        "goal": "A2 · Source acquisition",
        "required_operator_id": "autosci-research-synthesis-source-discovery-worker",
        "required_capabilities": [
            "source.search",
            "research.source.web",
            "research.source.academic",
            "research.source.internal",
        ],
    }
    assert gnd._node_requires_human_search(node) is False


def test_every_fixed_node_with_search_capabilities_stays_exactly_bound() -> None:
    """Same guarantee stated over the real compiled graph rather than a literal."""
    for node_id, operator_id in fr.PHYSICAL_OPERATOR_BY_NODE.items():
        node = {
            "id": node_id,
            "goal": f"{node_id} goal",
            "required_operator_id": operator_id,
            "required_capabilities": sorted(gnd.HUMAN_SEARCH_CAPABILITIES),
        }
        assert gnd._node_requires_human_search(node) is False, node_id


def test_unbound_research_node_still_uses_the_human_search_lane() -> None:
    """The guard must key on exact binding, not on the capabilities, so a legacy
    planner-generated node keeps the human-in-the-loop lane it depends on."""
    node = {
        "id": "external_search",
        "goal": "find contradicting sources",
        "required_capabilities": ["research.source.academic"],
    }
    assert gnd._node_requires_human_search(node) is True


def _fixed_contract() -> dict:
    return json.loads(
        (HARNESS / "config/workflows/research.evidence_to_poc.v1.workflow.json").read_text(encoding="utf-8")
    )


def _capsule(capsule_id: str) -> dict:
    import yaml

    return yaml.safe_load(
        (HARNESS / "config/capability-capsules" / f"{capsule_id}.yaml").read_text(encoding="utf-8")
    )


def test_every_fixed_stage_binds_exactly_one_dedicated_capsule() -> None:
    """No stage may fall back to a generic requirement-compiler capsule.

    A4-A8 and B1-B3 were bound to cap.requirement-research-synthesizer /
    -compiler-verification / -compiler-planner, whose postconditions demand the
    legacy AutoSci bundle (claims_jsonl, report_ast_json, final_md,
    research_eval_json). None of those are produced by this workflow, so the
    proof gate blocked each stage with proof_obligations_failed the moment it
    first reached the gate.
    """
    for stage in _fixed_contract()["stages"]:
        capsules = stage.get("allowed_capsules") or []
        assert len(capsules) == 1, f"{stage['id']} must pin exactly one capsule, got {capsules}"
        capsule_id = capsules[0]
        # Every stage capsule is research-named, per the phase-17 naming cleanup
        # that test_phase17_naming_cleanup.py enforces. Anything else is a
        # generic requirement-compiler capsule, which this workflow forbids.
        assert capsule_id.startswith("cap.research-"), (
            f"{stage['id']} binds generic capsule {capsule_id}; the fixed workflow forbids generic fallback"
        )


def test_each_stage_capsule_postcondition_matches_its_declared_output() -> None:
    """The capsule's output_present field must name an artifact the stage
    actually declares, under the `<name>_json` -> `<name>.json` convention the
    proof gate uses (graph_node_dispatcher._proof_field_presence)."""
    suffix_map = {"_jsonl": ".jsonl", "_json": ".json", "_md": ".md", "_dir": ""}
    for stage in _fixed_contract()["stages"]:
        capsule = _capsule(stage["allowed_capsules"][0])
        declared = {
            str(item.get("path", "")).rsplit("/", 1)[-1]
            for item in stage.get("outputs") or []
        }
        for condition in capsule["contract"].get("postconditions") or []:
            if condition.get("check") != "output_present":
                continue
            field = str(condition.get("field") or "")
            candidates = {field}
            for suffix, extension in suffix_map.items():
                if field.endswith(suffix) and len(field) > len(suffix):
                    candidates.add(field[: -len(suffix)] + extension)
                    break
            assert candidates & declared, (
                f"{stage['id']}: capsule {capsule['capability_capsule_id']} requires "
                f"{field!r} (tried {sorted(candidates)}) but the stage declares {sorted(declared)}"
            )


def test_part_b_science_stages_are_bound_to_autosci() -> None:
    """The Part B science stages must run AutoSci, not a Solar reimplementation.

    autosci_bridge.py and its operators already existed; only the capsule layer
    was missing, so the contract had been pointing at autosci-research-poc-*
    command operators that reimplemented the lifecycle instead.
    """
    bound = {s["id"]: (s.get("allowed_capsules") or [None])[0] for s in _fixed_contract()["stages"]}
    for stage_id in ("idea_evaluation", "experiment_design", "experiment_run",
                     "claim_verification", "final_delivery"):
        assert str(bound[stage_id]).startswith("cap.research-external-"), (
            f"{stage_id} must bind an external science-agent capsule, got {bound[stage_id]}"
        )
    # The boundary and the policy record stay Solar-owned, so they must NOT be
    # the external family.
    assert not bound["poc_handoff"].startswith("cap.research-external-")
    assert not bound["experiment_approval"].startswith("cap.research-external-")
    assert bound["poc_handoff"].startswith("cap.research-")
    assert bound["experiment_approval"].startswith("cap.research-")


def test_fixed_stage_capsules_declare_no_repository_resource() -> None:
    """A repository/GitHub resource capsule makes the generic verification proof
    demand a repo workspace this workflow never binds (the original B4 failure)."""
    for stage in _fixed_contract()["stages"]:
        capsule = _capsule(stage["allowed_capsules"][0])
        assert not (capsule.get("bindings") or {}).get("required_resource_capsules"), (
            f"{stage['id']} capsule must declare no required resource capsule"
        )


def test_empty_matching_heading_does_not_mask_a_populated_method_section() -> None:
    """A5 writers emit a matching heading with no body above another heading.

    Observed in a real run: "## Method and evidence protocol" sat directly above
    "## Evidence scope and processing" with nothing between them, while the
    substantive "## Evidence method" appeared further down. Returning on the
    first heading match let the empty one mask the populated one, so A7 rejected
    a report whose method section was present with lineage_incomplete.
    """
    body = (
        "# Report\n\n"
        "## Summary\n\nsummary text\n\n"
        "## Method and evidence protocol\n"
        "## Evidence scope and processing\n\nsources used\n\n"
        "## Evidence method\n\n1. No external tool calls were used.\n"
    )
    section = revision_operator._markdown_section(
        body, r"methods?\b|evidence\s+method\b|方法|方法论"
    )
    assert "no external tool calls" in section


def test_markdown_section_still_returns_the_first_populated_match() -> None:
    """The scan must not skip past a good first match."""
    body = (
        "# Report\n\n"
        "## Methods\n\nthe real method text\n\n"
        "## Evidence method\n\na later duplicate\n"
    )
    section = revision_operator._markdown_section(body, r"methods?\b|evidence\s+method\b")
    assert "the real method text" in section
    assert "later duplicate" not in section


def test_markdown_section_returns_empty_when_no_match_has_content() -> None:
    body = "# Report\n\n## Methods\n## Conclusions\n\ntext\n"
    assert revision_operator._markdown_section(body, r"methods?\b") == ""


def test_revision_preservation_rejects_a_report_with_no_method_anywhere() -> None:
    """The lineage_incomplete guard must still fire for a genuinely absent
    method section, so the fix does not weaken the preservation contract."""
    original = {
        "report": {
            "body": "# Report\n\n## Summary\n\ntext\n\n## Conclusions\n\ndone\n",
            "conclusions": [{"conclusion_id": "c1", "text": "x", "evidence_ids": ["e1"]}],
        },
        "limitations": [],
    }
    with pytest.raises(ResearchOperatorError, match="no conclusions or substantive method section"):
        revision_operator.revision_preservation_requirements(original)


def test_reviser_receives_the_method_text_it_must_preserve(monkeypatch: pytest.MonkeyPatch) -> None:
    """verify_revision_response_preservation requires the original normalized
    method text to remain a substring of the revised method section. Passing
    only preserved_method_sha256 states that requirement in a form no model can
    act on, so the exact text must accompany the digest."""
    captured: dict = {}

    original = {
        "report": {
            "body": "# R\n\n## Methods\n\nWe used only supplied evidence rows.\n\n## Conclusions\n\ndone\n",
            "conclusions": [{"conclusion_id": "c1", "text": "x", "evidence_ids": ["e1"]}],
        },
        "limitations": ["a limitation"],
    }
    requirements = revision_operator.revision_preservation_requirements(original)
    assert requirements["original_method"], "the extractor must find the method text"

    # The keys the operator forwards must include the text, not just the digest.
    forwarded = {
        key: requirements[key]
        for key in ("preserved_conclusion_ids", "preserved_method_sha256", "preserved_limitations", "original_method")
    }
    assert forwarded["original_method"] == requirements["original_method"]
    assert "only supplied evidence rows" in forwarded["original_method"]

    source = (
        HARNESS / "plugins/autosci/operators/research_synthesis/report_revision.py"
    ).read_text(encoding="utf-8")
    forwarding_block = source.split("preservation_requirements={", 1)[1][:500]
    for key in ('"original_method"', '"original_conclusions"'):
        assert key in forwarding_block, (
            f"the reviser request must forward {key} alongside the ids and digest; "
            "verify_revision_response_preservation rejects any reworded conclusion "
            "or method text, so the exact text has to be supplied"
        )


def test_document_title_is_not_mistaken_for_a_method_section() -> None:
    """The level-1 heading is the document title, not a section.

    A real A5 draft was titled "Research-Linked Comparison of RAG Reliability
    Evaluation Methods and No-Network Evidence-Lineage PoC". Matching that title
    captured everything up to the next level-<=1 heading -- of which there was
    none -- so the "method section" came back as 17,189 of the body's 17,471
    characters. A7 then required the reviser to reproduce the whole report
    verbatim, which no revision can satisfy. The revision in that run had in
    fact preserved the real method section exactly.
    """
    body = (
        "# Comparison of RAG Reliability Evaluation Methods and Lineage PoC\n\n"
        "## Summary\n\nsummary text\n\n"
        "## Evidence method\n\nonly supplied evidence rows were used\n\n"
        "## Conclusions\n\ndone\n"
    )
    section = revision_operator._markdown_section(
        body, r"methods?\b|evidence\s+method\b|方法|方法论"
    )
    assert "only supplied evidence rows were used" in section
    assert "summary text" not in section, "must not swallow unrelated sections"
    assert len(section) < len(body) / 2, "must not capture the whole document"


def test_title_match_does_not_break_the_limitations_extractor_either() -> None:
    """_markdown_section is shared with the limitations check, which has the
    same exposure to a title containing the pattern word."""
    body = (
        "# Known Limitations of RAG Benchmarks\n\n"
        "## Summary\n\nsummary text\n\n"
        "## Limitations\n\n- benchmark comparability is unstable\n"
    )
    section = revision_operator._markdown_section(body, r"limitations?\b|局限|限制|不足")
    assert "benchmark comparability is unstable" in section
    assert "summary text" not in section


def test_revision_limitation_rendering_is_still_required(tmp_path: Path) -> None:
    """Accumulating limitations into the response must NOT make the guarantee
    vacuous: a revision that fails to RENDER a recorded limitation in its
    limitations section is still rejected."""
    original = {
        "report": {
            "body": "# R\n\n## Methods\n\nm text\n\n## Conclusions\n\nc\n\n## Limitations\n\n- kept one\n",
            "conclusions": [{"conclusion_id": "c1", "text": "c", "evidence_ids": ["e1"]}],
        },
        "limitations": ["kept one"],
    }
    response = {
        "preservation": {
            "preserved_conclusion_ids": ["c1"],
            "preserved_method_sha256": revision_operator.revision_preservation_requirements(
                original, required_limitations=["kept one"]
            )["preserved_method_sha256"],
            "preserved_limitations": ["kept one"],
        },
        # limitation present in the array but NOT rendered in the body
        "limitations": ["kept one"],
        "report": {
            "body": "# R\n\n## Methods\n\nm text\n\n## Conclusions\n\nc\n\n## Limitations\n\n- something else\n",
            "conclusions": [{"conclusion_id": "c1", "text": "c", "evidence_ids": ["e1"]}],
        },
    }
    with pytest.raises(ResearchOperatorError, match="omitted a provider-recorded limitation"):
        revision_operator.verify_revision_response_preservation(
            original, response, required_limitations=["kept one"]
        )


def test_operator_accumulates_required_limitations_into_the_response() -> None:
    """A5 accumulates its upstream synthesis limitations rather than demanding
    the model echo them. A7 must do the same, or a revision that rendered every
    limitation correctly is rejected purely for returning an empty JSON array
    (observed: 10/10 rendered, array empty, run failed)."""
    source = (
        HARNESS / "plugins/autosci/operators/research_synthesis/report_revision.py"
    ).read_text(encoding="utf-8")
    block = source.split("model_generate service must return a JSON object", 1)[1][:900]
    assert 'response["limitations"] = list(dict.fromkeys(' in block, (
        "report_revision must accumulate required limitations into the response "
        "before preservation verification, mirroring report_draft"
    )


def test_preservation_failure_consumes_the_declared_retry_budget() -> None:
    """MAX_REVISION_ATTEMPTS = 2, but a raising preservation check aborted the
    loop on attempt 1, so the budget was never used for the failure mode it
    exists for. Observed: one Codex call, then terminal failure.

    The retry must not weaken preservation -- the same check still has to pass
    on the final attempt -- so this asserts the loop catches, feeds back, and
    re-raises on the last attempt.
    """
    source = (
        HARNESS / "plugins/autosci/operators/research_synthesis/report_revision.py"
    ).read_text(encoding="utf-8")
    loop = source.split("for attempt in range(1, MAX_REVISION_ATTEMPTS + 1):", 1)[1]
    assert "except ResearchOperatorError as exc:" in loop, "preservation failure must be catchable"
    assert "if attempt >= MAX_REVISION_ATTEMPTS:" in loop, "last attempt must still fail closed"
    assert "raise" in loop, "the final attempt must re-raise, not swallow"
    assert "preservation_feedback = str(exc)" in loop, "the retry must carry the reason"


def test_retry_feedback_reaches_the_reviser_prompt() -> None:
    """A retry that does not tell the model what it dropped is just a re-roll."""
    prompt_source = (
        HARNESS / "plugins/autosci/services/production_research.py"
    ).read_text(encoding="utf-8")
    block = prompt_source.split('elif node_id == "report_revision":', 1)[1][:2500]
    assert "preservation_feedback" in block, (
        "the report_revision prompt must forward preservation_feedback; the "
        "builder constructs its user payload explicitly and drops unknown kwargs"
    )
