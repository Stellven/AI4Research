from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

LIB_DIR = Path(__file__).resolve().parents[3] / "harness" / "lib"
sys.path.insert(0, str(LIB_DIR))

from advanced_ai4rnd.optimization import (  # noqa: E402
    ALGORITHMS,
    CAPABILITY_METADATA,
    OptimizationError,
    dependency_gate,
    run_reference_optimizer,
)


EXPECTED_MECHANISMS = {
    "miprov2": "bootstrapped_prompt_demo_search",
    "textgrad": "textual_gradient_keyword_update",
    "aflow": "workflow_graph_mutation_search",
    "mcts": "uct_tree_search",
    "adas": "agent_design_population_search",
    "cegis": "counterexample_guided_synthesis",
}


def _fixture_problem() -> dict:
    return {
        "dataset": [
            {"text": "safe tested approval path", "label": "accept"},
            {"text": "reliable verified answer", "label": "accept"},
            {"text": "unsafe secret leak", "label": "reject"},
            {"text": "brittle untested hack", "label": "reject"},
        ],
        "max_steps": 4,
        "complexity_weight": 0.001,
    }


def _read(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_algorithm_runs_real_candidate_updates_and_observable_artifacts(tmp_path: Path, algorithm: str) -> None:
    result = run_reference_optimizer(
        algorithm,
        _fixture_problem(),
        run_dir=tmp_path / algorithm,
        seed=7,
        run_id=f"{algorithm}-positive",
    )

    assert result["status"] == "passed"
    assert result["improved"] is True
    assert result["objective_delta"] > 0
    assert result["best_accuracy"] == 1.0
    assert result["baseline_objective"] < result["best_objective"]
    assert result["dependency_gate"]["gate"] == "open"

    for artifact in ("checkpoint", "dataset", "evaluation", "optimizer_graph", "policy", "result", "trace"):
        assert Path(result["artifacts"][artifact]).is_file(), artifact

    trace = _read(result["artifacts"]["trace"])
    events = [item["event"] for item in trace]
    assert "input" in events
    assert "candidate" in events
    assert "evaluation" in events
    assert "update" in events
    assert events[-1] == "termination"
    updates = [item for item in trace if item["event"] == "update"]
    assert any(item["changed"] for item in updates)
    assert {item["mechanism"] for item in updates} == {EXPECTED_MECHANISMS[algorithm]}

    graph = _read(result["artifacts"]["optimizer_graph"])
    assert graph["algorithm"] == algorithm
    assert any(node["kind"] == "algorithm_update" for node in graph["nodes"])
    assert graph["edges"][1]["relation"] == "optimized_into"

    policy = _read(result["artifacts"]["policy"])
    assert policy["candidate_id"] == result["best_candidate"]["candidate_id"]
    assert policy["keyword_rules"] or policy["graph"] or policy["agents"] or policy.get("counterexamples")


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_algorithm_rejects_invalid_dataset_instead_of_fake_pass(tmp_path: Path, algorithm: str) -> None:
    with pytest.raises(OptimizationError, match="at least two labels"):
        run_reference_optimizer(
            algorithm,
            {
                "dataset": [
                    {"text": "only one class", "label": "accept"},
                    {"text": "same class again", "label": "accept"},
                ]
            },
            run_dir=tmp_path / algorithm,
            seed=3,
        )


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_algorithm_interrupt_resume_is_reproducible(tmp_path: Path, algorithm: str) -> None:
    problem = _fixture_problem()
    full = run_reference_optimizer(
        algorithm,
        problem,
        run_dir=tmp_path / "full" / algorithm,
        seed=11,
        run_id=f"{algorithm}-resume",
    )
    interrupted = run_reference_optimizer(
        algorithm,
        problem,
        run_dir=tmp_path / "resume" / algorithm,
        seed=11,
        run_id=f"{algorithm}-resume",
        interrupt_after_steps=1,
    )
    assert interrupted["status"] == "interrupted"

    resumed = run_reference_optimizer(
        algorithm,
        {},
        run_dir=tmp_path / "resume" / algorithm,
        seed=999,
        resume_from=interrupted["artifacts"]["checkpoint"],
    )

    assert resumed["status"] == full["status"] == "passed"
    assert resumed["best_objective"] == full["best_objective"]
    assert resumed["best_candidate"] == full["best_candidate"]
    trace = _read(resumed["artifacts"]["trace"])
    assert any(item["event"] == "resume" for item in trace)


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_algorithm_recovers_from_fail_once_checkpoint(tmp_path: Path, algorithm: str) -> None:
    failed = run_reference_optimizer(
        algorithm,
        _fixture_problem(),
        run_dir=tmp_path / algorithm,
        seed=5,
        run_id=f"{algorithm}-recovery",
        fail_once_steps=[1],
    )
    assert failed["status"] == "recoverable_failed"
    checkpoint = _read(failed["artifacts"]["checkpoint"])
    assert checkpoint["failed_once_steps_seen"] == [1]

    recovered = run_reference_optimizer(
        algorithm,
        {},
        run_dir=tmp_path / algorithm,
        resume_from=failed["artifacts"]["checkpoint"],
        fail_once_steps=[1],
    )
    assert recovered["status"] == "passed"
    trace = _read(recovered["artifacts"]["trace"])
    assert any(item["event"] == "recoverable_failure" for item in trace)
    assert any(item["event"] == "resume" for item in trace)


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_no_improvement_is_not_reported_as_success(tmp_path: Path, algorithm: str) -> None:
    problem = _fixture_problem()
    problem["initial_candidate"] = {
        "keyword_rules": {
            "accept": {"safe": 1.0, "reliable": 1.0},
            "reject": {"unsafe": 1.0, "brittle": 1.0},
        },
        "bias": {},
        "instruction": "Already solves the fixture.",
    }
    result = run_reference_optimizer(
        algorithm,
        problem,
        run_dir=tmp_path / algorithm,
        seed=13,
        max_steps=2,
    )
    assert result["status"] == "completed_no_improvement"
    assert result["improved"] is False
    assert result["objective_delta"] == 0
    assert result["result_state"] == "NOT_SUCCESS"


def test_capability_metadata_and_optional_dependency_gates_are_explicit() -> None:
    assert set(CAPABILITY_METADATA) == set(ALGORITHMS)
    for algorithm, meta in CAPABILITY_METADATA.items():
        assert meta["reference_status"] == "implemented"
        assert meta["production_status"] == "reference_only"
        assert set(meta["l2"]) == {"optimizer_graph", "dataset", "trace", "policy", "evaluation"}
        assert dependency_gate(algorithm, mode="reference")["gate"] == "open"

    production_gate = dependency_gate("textgrad", mode="production")
    assert production_gate["optional_dependency"] == "textgrad"
    assert production_gate["gate"] in {"open", "blocked"}
    assert production_gate["reason"]
