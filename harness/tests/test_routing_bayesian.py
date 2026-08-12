import json
from pathlib import Path

from harness.lib.routing_bayesian import evaluate


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _rows() -> list[dict]:
    rows = []
    arms = {
        "base": ({"quality": 0.2, "speed": 0.2}, 0.60, 0.30, 900),
        "balanced": ({"quality": 0.7, "speed": 0.8}, 0.82, 0.18, 550),
        "premium": ({"quality": 1.0, "speed": 0.4}, 0.88, 0.80, 450),
    }
    for arm, (config, reward, cost, latency) in arms.items():
        for index in range(3):
            rows.append({"split": "train", "context_id": f"t-{arm}-{index}", "arm": arm, "config": config, "reward": reward + index * .001, "cost_usd": cost, "latency_ms": latency, "success": True})
    for index in range(2):
        for arm, (config, reward, cost, latency) in arms.items():
            rows.append({"split": "holdout", "context_id": f"h-{index}", "arm": arm, "config": config, "reward": reward, "cost_usd": cost, "latency_ms": latency, "success": True})
    return rows


def _evaluate(path: Path, **overrides):
    values = {"cost_weight": 1.0, "latency_weight": .1, "max_cost": .5, "beta": .2, "length_scale": 1.0, "noise": .05, "max_uncertainty": .25}
    values.update(overrides)
    return evaluate(path, "base", **values)


def test_selects_cost_bounded_candidate_with_gp_uncertainty(tmp_path):
    result = _evaluate(_write(tmp_path / "traces.jsonl", _rows()))
    selected = result["policy"]["selected_arm"]
    assert result["status"] == "accepted" and selected == "balanced"
    assert result["algorithm"] == "bounded_gaussian_process_ucb"
    assert 0 < result["training_arm_stats"][selected]["posterior_stddev"] <= .25
    assert result["policy"]["deployment_authorized"] is False


def test_rejects_train_holdout_contamination(tmp_path):
    rows = _rows()
    rows[-1]["context_id"] = rows[0]["context_id"]
    result = _evaluate(_write(tmp_path / "traces.jsonl", rows))
    assert "train_holdout_context_contamination" in result["errors"]


def test_rejects_when_budget_excludes_candidate(tmp_path):
    result = _evaluate(_write(tmp_path / "traces.jsonl", _rows()), max_cost=.1)
    assert result["status"] == "rejected"
    assert "no_budget_and_uncertainty_eligible_candidate" in result["errors"]


def test_rejects_excessive_posterior_uncertainty(tmp_path):
    result = _evaluate(_write(tmp_path / "traces.jsonl", _rows()), max_uncertainty=.001)
    assert result["status"] == "rejected"
    assert "no_budget_and_uncertainty_eligible_candidate" in result["errors"]


def test_rejects_holdout_success_regression(tmp_path):
    rows = _rows()
    for row in rows:
        if row["split"] == "holdout" and row["arm"] == "balanced":
            row["success"] = False
    result = _evaluate(_write(tmp_path / "traces.jsonl", rows))
    assert "holdout_success_regression" in result["errors"]


def test_rejects_inconsistent_config_features(tmp_path):
    rows = _rows()
    rows[3]["config"] = {"quality": .7}
    result = _evaluate(_write(tmp_path / "traces.jsonl", rows))
    assert result["status"] == "rejected"
    assert any(error.startswith("inconsistent_config") for error in result["errors"])


def test_rejects_string_false_instead_of_treating_it_as_success(tmp_path):
    rows = _rows()
    rows[3]["success"] = "false"
    result = _evaluate(_write(tmp_path / "traces.jsonl", rows))
    assert result["status"] == "rejected"
    assert "invalid_success:4" in result["errors"]
    assert result["training_arm_stats"] == {}


def test_rejects_nan_and_infinity_in_metrics_and_config(tmp_path):
    for field, value in [("reward", float("nan")), ("cost_usd", float("inf")), ("latency_ms", float("-inf"))]:
        rows = _rows()
        rows[0][field] = value
        result = _evaluate(_write(tmp_path / f"{field}.jsonl", rows))
        assert result["status"] == "rejected"
        assert any(error.startswith(f"invalid_{field}:") for error in result["errors"])
    rows = _rows()
    rows[0]["config"]["quality"] = float("nan")
    result = _evaluate(_write(tmp_path / "config.jsonl", rows))
    assert "invalid_config_value:1" in result["errors"]


def test_rejects_numeric_strings_and_boolean_config_values(tmp_path):
    rows = _rows()
    rows[0]["reward"] = "0.60"
    rows[1]["config"] = {"quality": True, "speed": .2}
    result = _evaluate(_write(tmp_path / "traces.jsonl", rows))
    assert result["status"] == "rejected"
    assert "invalid_reward:1" in result["errors"]
    assert "invalid_config_value:2" in result["errors"]


def test_rejects_empty_identifiers_and_duplicate_observations(tmp_path):
    rows = _rows()
    rows[0]["arm"] = " "
    rows[1]["context_id"] = ""
    rows.append(dict(rows[2]))
    result = _evaluate(_write(tmp_path / "traces.jsonl", rows))
    assert result["status"] == "rejected"
    assert "invalid_arm:1" in result["errors"]
    assert "invalid_context_id:2" in result["errors"]
    assert any(error.startswith("duplicate_observation:") for error in result["errors"])


def test_rejects_non_finite_hyperparameter(tmp_path):
    result = _evaluate(_write(tmp_path / "traces.jsonl", _rows()), beta=float("nan"))
    assert result["status"] == "rejected"
    assert "non_finite_surrogate_parameters" in result["errors"]
