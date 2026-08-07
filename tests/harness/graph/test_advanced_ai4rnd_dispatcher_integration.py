"""Real TaskGraph -> dispatcher -> operatord coverage for the R7 operator."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
DISPATCHER = HARNESS / "lib" / "graph_node_dispatcher.py"
OPERATORD = HARNESS / "tools" / "operatord.py"
OPERATOR_ID = "autosci-advanced-ai4rnd-worker"


def _git_bash_dir() -> str:
    candidate = Path(r"C:\Program Files\Git\bin")
    return str(candidate) if candidate.is_dir() else ""


def _prepare_harness(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    sandbox = tmp_path / "harness"
    for name in ("config", "lib", "personas", "run", "sprints"):
        (sandbox / name).mkdir(parents=True, exist_ok=True)
    (sandbox / "run" / "operator-inbox" / OPERATOR_ID).mkdir(parents=True, exist_ok=True)
    (sandbox / "run" / "operator-results" / OPERATOR_ID).mkdir(parents=True, exist_ok=True)
    shutil.copy2(HARNESS / "config" / "physical-operators.json", sandbox / "config")
    shutil.copy2(HARNESS / "personas" / "lab-builder.md", sandbox / "personas")
    for name in (
        "advanced_ai4rnd_operator.py",
        "evidence_ledger.py",
        "model_registry.py",
        "task_graph_state_io.py",
    ):
        shutil.copy2(HARNESS / "lib" / name, sandbox / "lib" / name)
    shutil.copytree(HARNESS / "lib" / "advanced_ai4rnd", sandbox / "lib" / "advanced_ai4rnd")

    bash_dir = _git_bash_dir()
    env = {
        **os.environ,
        "HARNESS_DIR": sandbox.as_posix(),
        "SOLAR_HARNESS_DIR": sandbox.as_posix(),
        "HARNESS_SPRINTS_DIR": (sandbox / "sprints").as_posix(),
        "SOLAR_MULTI_TASK_OPERATORS": (sandbox / "config" / "physical-operators.json").as_posix(),
        "SOLAR_AUTOSCI_PYTHON": Path(sys.executable).as_posix(),
        "SOLAR_OPERATORD_AUTO_KICK": "0",
        "SOLAR_PLAN_VALIDATOR": "0",
        "SOLAR_GATE_LEDGER": "0",
        "SOLAR_GRAPH_BUILDER_OPERATOR_POOL": "0",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    if bash_dir:
        env["PATH"] = bash_dir + os.pathsep + env.get("PATH", "")
    return sandbox, env


def _write_graph(
    sandbox: Path,
    *,
    sid: str,
    kind: str,
    algorithm: str,
    inputs: dict,
    parameters: dict,
) -> Path:
    node_id = "advanced"
    graph = {
        "schema_version": "solar.task_graph.v1",
        "workflow_contract": "research.autosci.v1",
        "research_mode": True,
        "sprint_id": sid,
        "required_gates": [],
        "nodes": [
            {
                "id": node_id,
                "goal": f"Run the {algorithm} advanced AI4RnD reference task.",
                "logical_operator": "ScientificAdvancedAI4RnDExecutor",
                "depends_on": [],
                "acceptance": ["Records an explicit advanced operator result."],
                "workflow_contract": "research.autosci.v1",
                "status": "pending",
                "operator_payload": {
                    "operator_kind": kind,
                    "algorithm": algorithm,
                    "run_id": f"run-{sid}",
                    "artifact_root": str(sandbox / "artifacts"),
                    "inputs": inputs,
                    "parameters": parameters,
                },
            }
        ],
        "node_results": {node_id: {"status": "pending"}},
        "gate_results": {},
    }
    graph_path = sandbox / "sprints" / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    return graph_path


def _dispatch_and_run(sandbox: Path, env: dict[str, str], graph_path: Path) -> tuple[dict, dict]:
    dispatched = subprocess.run(
        [sys.executable, str(DISPATCHER), "dispatch-ready", "--graph", str(graph_path), "--max-parallel", "1"],
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert dispatched.returncode == 0, dispatched.stdout + dispatched.stderr
    dispatch_result = json.loads(dispatched.stdout)
    item = dispatch_result["drain"]["results"][0]
    assert item["operator_id"] == OPERATOR_ID
    assert item["pane"] == f"operator:{OPERATOR_ID}"
    assert item["dispatch_mode"] == "autosci_operator_direct"

    daemon = subprocess.run(
        [
            sys.executable,
            str(OPERATORD),
            "daemon",
            "--operator",
            OPERATOR_ID,
            "--once",
            "--poll-interval",
            "0.1",
        ],
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert daemon.returncode == 0, daemon.stdout + daemon.stderr
    task_id = item["operator_submit"]["task_id"]
    runtime_result_path = sandbox / "run" / "operator-results" / OPERATOR_ID / task_id / "result.json"
    assert runtime_result_path.is_file()
    return dispatch_result, json.loads(runtime_result_path.read_text(encoding="utf-8"))


def test_bayesian_optimizer_runs_through_real_taskgraph_dispatcher_and_operatord(tmp_path: Path) -> None:
    sandbox, env = _prepare_harness(tmp_path)
    sid = "advanced-dispatch-bo"
    graph_path = _write_graph(
        sandbox,
        sid=sid,
        kind="optimizer",
        algorithm="bayesian_optimization",
        inputs={
            "search_space": [-2, -1, 0, 1, 2],
            "objective": {"type": "quadratic", "target": 1, "offset": 5, "scale": 1},
        },
        parameters={"rounds": 4, "initial_points": [-2]},
    )

    dispatch_result, runtime_result = _dispatch_and_run(sandbox, env, graph_path)

    assert dispatch_result["enqueue"]["enqueued"][0]["pane"] == f"operator:{OPERATOR_ID}"
    assert runtime_result["operator_id"] == OPERATOR_ID
    assert runtime_result["status"] == "completed"
    state = json.loads(
        (sandbox / "sprints" / f"{sid}.task_dag.state.json").read_text(encoding="utf-8")
    )
    node_result = state["node_results"]["advanced"]
    output_hash = node_result["advanced_ai4rnd"]["output_hash"]
    assert node_result["assigned_to"] == OPERATOR_ID
    assert node_result["status"] == "passed"
    assert output_hash
    ledger = [
        json.loads(line)
        for line in (sandbox / "run" / "actor-evidence" / f"{sid}.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert ledger[-1]["actor_id"] == OPERATOR_ID
    assert ledger[-1]["verification_results"]["output_hash"] == output_hash


def test_unsupported_algorithm_stays_explicit_through_real_dispatcher(tmp_path: Path) -> None:
    sandbox, env = _prepare_harness(tmp_path)
    sid = "advanced-dispatch-unsupported"
    graph_path = _write_graph(
        sandbox,
        sid=sid,
        kind="trainer",
        algorithm="future_trainer",
        inputs={},
        parameters={},
    )

    _, runtime_result = _dispatch_and_run(sandbox, env, graph_path)

    assert runtime_result["operator_id"] == OPERATOR_ID
    assert runtime_result["status"] == "failed"
    state = json.loads(
        (sandbox / "sprints" / f"{sid}.task_dag.state.json").read_text(encoding="utf-8")
    )
    advanced = state["node_results"]["advanced"]["advanced_ai4rnd"]
    assert advanced["status"] == "unsupported"
    assert advanced["result_state"] == "STILL_NOT_AVAILABLE"
    assert advanced["output_hash"] is None
    ledger = [
        json.loads(line)
        for line in (sandbox / "run" / "actor-evidence" / f"{sid}.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert ledger[-1]["verification_results"]["status"] == "unsupported"
    assert ledger[-1]["verification_results"]["output_hash"] is None
