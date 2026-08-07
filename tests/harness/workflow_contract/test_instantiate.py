"""Deterministic tests 2/4/7-analog (variant guard + identity, byte-identical
instantiation with committed goldens, demo-artifact coverage) — AC-R1.1
identity stamping per review C1+C2, AC-R3.1 golden-file determinism."""
from __future__ import annotations

from pathlib import Path

import pytest

import workflow_contract as wc

GOLDENS_DIR = (Path(__file__).resolve().parents[3] / 'tests' / 'harness' / 'workflow_contract') / "goldens"

RSI_INPUTS = {"sid": "golden-sid", "sprint_id": "sprint-golden"}
CLI_INPUTS = {"sid": "golden-sid", "sprint_id": "sprint-golden", "tool": "wordfreq"}


@pytest.fixture(scope="module")
def rsi_graph(shipped_contracts):
    return wc.instantiate(shipped_contracts["research.deepdive.rsi_demo"], RSI_INPUTS)


@pytest.fixture(scope="module")
def cli_graph(shipped_contracts):
    return wc.instantiate(shipped_contracts["code.cli_smoke"], CLI_INPUTS)


@pytest.fixture(scope="module")
def cli_anthropic_graph(shipped_contracts):
    return wc.instantiate(shipped_contracts["code.cli_smoke_anthropic"], CLI_INPUTS)


# ---------------------------------------------------------------------------
# R3: byte-identical twice + committed goldens
# ---------------------------------------------------------------------------

def test_instantiation_byte_identical_twice(shipped_contracts):
    for workflow_id, inputs in (
        ("research.deepdive.rsi_demo", RSI_INPUTS),
        ("code.cli_smoke", CLI_INPUTS),
        ("code.cli_smoke_anthropic", CLI_INPUTS),
    ):
        contract = shipped_contracts[workflow_id]
        first = wc.canonical_graph_json(wc.instantiate(contract, dict(inputs)))
        second = wc.canonical_graph_json(wc.instantiate(contract, dict(inputs)))
        assert first == second, workflow_id


@pytest.mark.parametrize(
    "workflow_id,inputs,golden_name",
    [
        ("research.deepdive.rsi_demo", RSI_INPUTS, "research.deepdive.rsi_demo.instantiated.golden.json"),
        ("code.cli_smoke", CLI_INPUTS, "code.cli_smoke.instantiated.golden.json"),
        ("code.cli_smoke_anthropic", CLI_INPUTS, "code.cli_smoke_anthropic.instantiated.golden.json"),
    ],
)
def test_instantiation_matches_committed_golden(shipped_contracts, workflow_id, inputs, golden_name):
    golden_path = GOLDENS_DIR / golden_name
    produced = wc.canonical_graph_json(wc.instantiate(shipped_contracts[workflow_id], dict(inputs)))
    assert golden_path.is_file(), f"golden missing: {golden_path}"
    assert produced == golden_path.read_text(encoding="utf-8"), (
        f"{workflow_id} instantiation drifted from its committed golden — a contract or compiler "
        f"change must update the golden deliberately"
    )


# ---------------------------------------------------------------------------
# Identity + variant guard (C1+C2): identity in workflow_contract_id, closed
# enum preserved in dag_variant, hash detects tampering.
# ---------------------------------------------------------------------------

def test_graph_identity_is_workflow_contract_id_not_dag_variant(rsi_graph, cli_graph, cli_anthropic_graph):
    assert rsi_graph["workflow_contract_id"] == "research.deepdive.rsi_demo"
    assert rsi_graph["workflow_contract_version"] == "1.3"
    assert rsi_graph["dag_variant"] == "research"
    assert cli_graph["workflow_contract_id"] == "code.cli_smoke"
    assert cli_graph["dag_variant"] == "short"
    assert cli_anthropic_graph["workflow_contract_id"] == "code.cli_smoke_anthropic"
    assert cli_anthropic_graph["workflow_contract_version"] == "1.0"
    assert cli_anthropic_graph["dag_variant"] == "short"
    for graph in (rsi_graph, cli_graph, cli_anthropic_graph):
        assert graph["dag_variant"] in wc.DAG_VARIANT_ENUM
        assert graph["dag_variant"] != graph["workflow_contract_id"]


def test_contract_hash_is_stable_and_detects_tampering(shipped_contracts):
    contract = shipped_contracts["research.deepdive.rsi_demo"]
    graph_a = wc.instantiate(contract, dict(RSI_INPUTS))
    graph_b = wc.instantiate(contract, dict(RSI_INPUTS))
    assert graph_a["workflow_contract_hash"] == graph_b["workflow_contract_hash"]
    assert graph_a["workflow_contract_hash"] == wc.graph_contract_hash(graph_a)

    # runtime-mutable fields do not perturb the hash (the guard can re-check a
    # loaded graph mid-run) ...
    graph_b["nodes"][0]["status"] = "passed"
    graph_b["sprint_id"] = "another-run"
    graph_b["node_results"]["D1"] = {"status": "passed"}
    assert wc.graph_contract_hash(graph_b) == graph_a["workflow_contract_hash"]

    # ... but contract-determined fields do (the dispatcher-guard rejection key)
    graph_b["nodes"][0]["capability_capsule_id"] = "cap.requirement-compiler-implementation"
    assert wc.graph_contract_hash(graph_b) != graph_a["workflow_contract_hash"]


# ---------------------------------------------------------------------------
# Demo-artifact coverage (deterministic test 7's Lane-1 half: every required
# artifact is produced by a stage; the adapter itself is Lane 4)
# ---------------------------------------------------------------------------

def test_required_artifacts_all_produced_by_stages(shipped_contracts, rsi_graph):
    produced = set()
    demo_flagged = set()
    for node in rsi_graph["nodes"]:
        for output in node["outputs"]:
            name = output["path"].rsplit("/", 1)[-1]
            produced.add(name)
            if output.get("demo_artifact"):
                demo_flagged.add(name)
    required = set(rsi_graph["required_artifacts"])
    assert required <= produced, required - produced
    assert demo_flagged == required, (demo_flagged, required)


# ---------------------------------------------------------------------------
# Node shape: the existing task-graph format, contract-determined
# ---------------------------------------------------------------------------

def test_nodes_carry_the_existing_task_graph_fields(rsi_graph):
    canonical_root = "sprints/golden-sid/workdir/rsi-deep-research-report/"
    for node in rsi_graph["nodes"]:
        assert node["status"] == "pending"
        assert node["dispatch_task_type"] == node["task_type"]
        assert node["capability_capsule_id"] == node["allowed_capsules"][0]
        assert node["node_kind"] in wc.NODE_KINDS
        for scope_entry in node["write_scope"]:
            assert scope_entry.startswith(canonical_root), scope_entry
        for obligation in node["proof_obligations"]:
            assert obligation["proof_kind"] in wc.PROOF_KINDS
        assert isinstance(node["timeouts"].get("result_timeout_sec"), int)
    assert rsi_graph["required_gates"] == [
        "DD_SCOPE", "DD_SOURCE", "DD_EVIDENCE", "DD_SYNTHESIS", "DD_PUBLISH",
    ]
    assert rsi_graph["node_results"] == {} and rsi_graph["gate_results"] == {}


def test_on_human_review_policy_carried_per_node(rsi_graph, cli_graph):
    by_id = {node["id"]: node for node in rsi_graph["nodes"]}
    assert by_id["D3"]["on_human_review"] == "warn_and_continue"
    assert by_id["D5"]["on_human_review"] == "warn_and_continue"
    assert "on_human_review" not in by_id["D1"]  # gate kind none => legacy behavior
    cli_by_id = {node["id"]: node for node in cli_graph["nodes"]}
    assert cli_by_id["S1"]["on_human_review"] == "block_dependents"


def test_placeholder_substitution(cli_graph):
    by_id = {node["id"]: node for node in cli_graph["nodes"]}
    assert by_id["S1"]["write_scope"][0] == "sprints/golden-sid/workdir/wordfreq.py"
    assert by_id["S2"]["outputs"][0]["path"] == "sprints/golden-sid/workdir/tests/test_wordfreq.py"
    assert cli_graph["validator_command"] == "python3 -m pytest sprints/golden-sid/workdir/tests -q"
    assert "wordfreq.py" in cli_graph["required_artifacts"]


def test_unknown_placeholders_are_left_verbatim(shipped_contracts):
    # A token nobody supplies stays verbatim (intake's fail-closed
    # UNRESOLVED_PLACEHOLDERS check catches it downstream). NOTE:
    # <resolved_root> is no longer such a token — the original "resolved by
    # the wrapper at run time" design had no wrapper on the contracted intake
    # path (P3 rehearsal: intake failed closed on it), so instantiate() now
    # derives it from artifact_roots.canonical (parent-dir semantics); see
    # test_rsi_demo_p3_intake.py.
    import copy
    contract = copy.deepcopy(shipped_contracts["research.deepdive.rsi_demo"])
    contract["validator_command"] = "echo <never_supplied_token>"
    graph = wc.instantiate(contract, dict(RSI_INPUTS))
    assert "<never_supplied_token>" in graph["validator_command"]


def test_resolved_root_derives_from_canonical_and_caller_input_wins(shipped_contracts):
    graph = wc.instantiate(shipped_contracts["research.deepdive.rsi_demo"], dict(RSI_INPUTS))
    assert graph["validator_command"].endswith("--workspace sprints/golden-sid/workdir")
    overridden = wc.instantiate(
        shipped_contracts["research.deepdive.rsi_demo"],
        {**RSI_INPUTS, "resolved_root": "/custom/ws"},
    )
    assert overridden["validator_command"].endswith("--workspace /custom/ws")


def test_planner_generated_contract_cannot_instantiate(shipped_contracts):
    with pytest.raises(wc.ContractInstantiationError):
        wc.instantiate(shipped_contracts["pm.generic.v1"], {})
