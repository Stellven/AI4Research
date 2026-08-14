import json
from pathlib import Path
from harness.lib.curriculum_loop import evaluate


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
    return path


def _events(tmp_path: Path) -> Path:
    return _write(tmp_path / "events.jsonl", [{"event_id": "e1", "outcome": "failed", "failure_cluster": "missing_provenance"}, {"event_id": "e2", "outcome": "failed", "failure_cluster": "missing_provenance"}])


def _cases() -> list[dict]:
    return [{"case_id": "t1", "split": "train", "failure_cluster": "missing_provenance", "source_event_ids": ["e1"], "baseline_passed": False, "candidate_passed": True}, {"case_id": "h1", "split": "holdout", "source_event_ids": ["h-e1"], "baseline_passed": False, "candidate_passed": True, "intervention_ids": ["curriculum-1"]}, {"case_id": "h2", "split": "holdout", "source_event_ids": ["h-e2"], "baseline_passed": True, "candidate_passed": True, "intervention_ids": []}]


def test_promotes_clean_improving_holdout(tmp_path: Path) -> None:
    result = evaluate(_events(tmp_path), _write(tmp_path / "cases.jsonl", _cases()), "curriculum-1")
    assert result["status"] == "promoted" and result["holdout_ablation"]["absolute_improvement"] == 0.5


def test_rejects_source_contamination(tmp_path: Path) -> None:
    cases = _cases(); cases[1]["source_event_ids"] = ["e1"]
    result = evaluate(_events(tmp_path), _write(tmp_path / "cases.jsonl", cases), "curriculum-1")
    assert result["status"] == "rejected" and "train_holdout_contamination" in result["errors"]


def test_rejects_regression(tmp_path: Path) -> None:
    cases = _cases(); cases[2]["candidate_passed"] = False; cases[2]["intervention_ids"] = ["curriculum-1"]
    result = evaluate(_events(tmp_path), _write(tmp_path / "cases.jsonl", cases), "curriculum-1")
    assert result["status"] == "rejected" and "holdout_regression" in result["errors"]


def test_rejects_ambiguous_credit(tmp_path: Path) -> None:
    cases = _cases(); cases[1]["intervention_ids"] = ["curriculum-1", "other"]
    result = evaluate(_events(tmp_path), _write(tmp_path / "cases.jsonl", cases), "curriculum-1")
    assert result["status"] == "rejected" and any(x.startswith("ambiguous_credit_assignment") for x in result["errors"])
