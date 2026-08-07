from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "lib" / "advanced_ai4rnd_operator.py"
PHYSICAL_OPERATORS = ROOT / "config" / "physical-operators.json"


def _run_product_entrypoint(tmp_path: Path, envelope: dict) -> tuple[subprocess.CompletedProcess[str], dict]:
    envelope_path = tmp_path / f"{envelope['run_id']}.envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(ENTRYPOINT),
            "--envelope",
            str(envelope_path),
            "--sprints-dir",
            str(tmp_path / "sprints"),
            "--evidence-dir",
            str(tmp_path / "evidence"),
        ],
        cwd=ROOT.parent,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    return proc, json.loads(proc.stdout)


def _base_envelope(tmp_path: Path, *, kind: str, algorithm: str, run_id: str) -> dict:
    return {
        "operator_kind": kind,
        "algorithm": algorithm,
        "run_id": run_id,
        "sprint_id": f"sprint-{run_id}",
        "node_id": f"node-{run_id}",
        "task_id": f"task-{run_id}",
        "artifact_root": str(tmp_path / "artifacts"),
        "inputs": {},
        "parameters": {},
    }


def test_physical_registry_binds_advanced_operator_to_production_command() -> None:
    registry = json.loads(PHYSICAL_OPERATORS.read_text(encoding="utf-8"))
    operator = registry["operators"]["autosci-advanced-ai4rnd-worker"]
    assert operator["enabled"] is True
    assert operator["backend"] == "command"
    assert "advanced_ai4rnd_operator.py" in operator["command"]
    assert "$SOLAR_OPERATOR_ENVELOPE_JSON" in operator["command"]
    assert {"bayesian-optimization", "cpu-safe-sft"}.issubset(operator["task_classes"])


def test_bayesian_optimizer_runs_through_production_entrypoint_and_taskgraph(tmp_path: Path) -> None:
    envelope = _base_envelope(tmp_path, kind="optimizer", algorithm="bayesian_optimization", run_id="bo-cli")
    envelope["inputs"] = {
        "search_space": [-3, -2, -1, 0, 1, 2, 3],
        "objective": {"type": "quadratic", "target": 2, "offset": 10, "scale": 1},
    }
    envelope["parameters"] = {"rounds": 5, "initial_points": [-3]}

    proc, result = _run_product_entrypoint(tmp_path, envelope)

    assert proc.returncode == 0, proc.stderr
    assert result["status"] == "passed"
    assert result["metrics"]["score_delta"] > 0
    assert result["output_hash"]
    state = json.loads((tmp_path / "sprints" / "sprint-bo-cli.task_dag.state.json").read_text(encoding="utf-8"))
    assert state["node_results"]["node-bo-cli"]["advanced_ai4rnd"]["output_hash"] == result["output_hash"]
    ledger = (tmp_path / "evidence" / "sprint-bo-cli.jsonl").read_text(encoding="utf-8")
    assert result["output_hash"] in ledger


def test_cpu_sft_runs_through_production_entrypoint_with_lineage(tmp_path: Path) -> None:
    envelope = _base_envelope(tmp_path, kind="trainer", algorithm="sft_linear_adapter", run_id="sft-cli")
    envelope["inputs"] = {
        "base_model_alias": "thunderomlx",
        "dataset_license": "internal-test",
        "train_dataset": [
            {"text": "approve safe reliable plan", "label": "accept"},
            {"text": "approve tested helpful answer", "label": "accept"},
            {"text": "reject unsafe secret leak", "label": "reject"},
            {"text": "reject brittle untested hack", "label": "reject"},
        ],
        "holdout_dataset": [
            {"text": "safe tested plan", "label": "accept"},
            {"text": "unsafe secret hack", "label": "reject"},
        ],
    }
    envelope["parameters"] = {"epochs": 60, "learning_rate": 0.4}

    proc, result = _run_product_entrypoint(tmp_path, envelope)

    assert proc.returncode == 0, proc.stderr
    assert result["status"] == "passed"
    assert result["metrics"]["holdout_delta"] > 0
    manifest = json.loads(Path(result["artifacts"]["manifest"]).read_text(encoding="utf-8"))
    assert manifest["adapter_hash"] == result["output_hash"]
    assert any(edge["relation"] == "adapted_from" for edge in manifest["lineage"])


def test_unsupported_algorithm_remains_explicit_through_product_entrypoint(tmp_path: Path) -> None:
    envelope = _base_envelope(tmp_path, kind="trainer", algorithm="lora", run_id="lora-cli")

    proc, result = _run_product_entrypoint(tmp_path, envelope)

    assert proc.returncode == 2
    assert result["status"] == "unsupported"
    assert result["result_state"] == "STILL_NOT_AVAILABLE"
    assert result["output_hash"] is None
