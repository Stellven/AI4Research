from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = (Path(__file__).resolve().parents[2] / 'harness')
REPO = ROOT.parent
SOLAR_CLI = REPO / "bin" / "solar"
PHYSICAL_OPERATORS = ROOT / "config" / "physical-operators.json"


def _bash_executable() -> str:
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    if git_bash.exists():
        return str(git_bash)
    executable = shutil.which("bash")
    assert executable and "WindowsApps" not in executable, "Git Bash or bash is required"
    return executable


def _bash_path(path: Path) -> str:
    value = path.resolve().as_posix()
    if len(value) >= 3 and value[1:3] == ":/":
        return f"/{value[0].lower()}{value[2:]}"
    return value


def _quote(value: str | Path) -> str:
    text = _bash_path(value) if isinstance(value, Path) else value
    return "'" + text.replace("'", "'\"'\"'") + "'"


def _run_product_entrypoint(tmp_path: Path, envelope: dict) -> tuple[subprocess.CompletedProcess[str], dict]:
    envelope_path = tmp_path / f"{envelope['run_id']}.envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir(exist_ok=True)
    python_shim = fake_bin / "python3"
    python_shim.write_text(
        f'#!/usr/bin/env bash\nexec "{_bash_path(Path(sys.executable))}" "$@"\n',
        encoding="utf-8",
    )
    os.chmod(python_shim, 0o755)
    command = " ".join(
        [
            f"PATH={_quote(fake_bin)}:$PATH",
            f"HOME={_quote(tmp_path / 'home')}",
            f"SOLAR_HOME={_quote(tmp_path / 'home' / '.solar')}",
            "bash",
            _quote(SOLAR_CLI),
            "advanced",
            "--envelope",
            _quote(envelope_path),
            "--sprints-dir",
            _quote(tmp_path / "sprints"),
            "--evidence-dir",
            _quote(tmp_path / "evidence"),
        ]
    )
    proc = subprocess.run(
        [_bash_executable(), "-lc", command],
        cwd=REPO,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
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
    envelope = _base_envelope(
        tmp_path,
        kind="trainer",
        algorithm="future_trainer",
        run_id="future-trainer-cli",
    )

    proc, result = _run_product_entrypoint(tmp_path, envelope)

    assert proc.returncode == 2
    assert result["status"] == "unsupported"
    assert result["result_state"] == "STILL_NOT_AVAILABLE"
    assert result["output_hash"] is None
