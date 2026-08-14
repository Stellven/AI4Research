from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_p22_curriculum_data_loop(repo_root: Path, tmp_path: Path) -> None:
    run_id = "p22-curriculum-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = repo_root / "outputs" / "phase22-real-journeys" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    events = _jsonl(run_dir / "failure-events.jsonl", [
        {"event_id": "ev-missing-1", "outcome": "failed", "failure_cluster": "missing_provenance"},
        {"event_id": "ev-missing-2", "outcome": "failed", "failure_cluster": "missing_provenance"},
        {"event_id": "ev-scope-1", "outcome": "failed", "failure_cluster": "scope_overreach"},
    ])
    base_cases = [
        {"case_id": "train-prov", "split": "train", "failure_cluster": "missing_provenance", "source_event_ids": ["ev-missing-1"], "baseline_passed": False, "candidate_passed": True},
        {"case_id": "train-scope", "split": "train", "failure_cluster": "scope_overreach", "source_event_ids": ["ev-scope-1"], "baseline_passed": False, "candidate_passed": True},
        {"case_id": "holdout-new", "split": "holdout", "source_event_ids": ["external-holdout-1"], "baseline_passed": False, "candidate_passed": True, "intervention_ids": ["curriculum-evidence-v1"]},
        {"case_id": "holdout-stable", "split": "holdout", "source_event_ids": ["external-holdout-2"], "baseline_passed": True, "candidate_passed": True, "intervention_ids": []},
    ]
    cases = _jsonl(run_dir / "curriculum-cases.jsonl", base_cases)
    tool = repo_root / "harness" / "lib" / "curriculum_loop.py"

    def run(label: str, case_rows: list[dict]) -> dict:
        case_path = _jsonl(run_dir / f"{label}-cases.jsonl", case_rows)
        output = run_dir / f"{label}-evaluation.json"
        proc = subprocess.run([sys.executable, str(tool), "evaluate", "--events", str(events), "--cases", str(case_path), "--candidate-id", "curriculum-evidence-v1", "--output", str(output)], cwd=repo_root, text=True, capture_output=True, timeout=30)
        return {"label": label, "exit_code": proc.returncode, "output": str(output), "payload": json.loads(output.read_text(encoding="utf-8"))}

    positive = run("positive", base_cases)
    contaminated_rows = json.loads(json.dumps(base_cases)); contaminated_rows[2]["source_event_ids"] = ["ev-missing-1"]
    regression_rows = json.loads(json.dumps(base_cases)); regression_rows[3]["candidate_passed"] = False; regression_rows[3]["intervention_ids"] = ["curriculum-evidence-v1"]
    ambiguous_rows = json.loads(json.dumps(base_cases)); ambiguous_rows[2]["intervention_ids"] = ["curriculum-evidence-v1", "other"]
    negatives = [run("contamination", contaminated_rows), run("regression", regression_rows), run("ambiguous-credit", ambiguous_rows)]
    payload = positive["payload"]
    assertions = {
        "production_cli_promoted_clean_candidate": positive["exit_code"] == 0 and payload.get("status") == "promoted",
        "failure_clusters_prioritized": len(payload.get("candidate", {}).get("prioritized_clusters", [])) == 2,
        "holdout_improved_without_regression": payload.get("holdout_ablation", {}).get("absolute_improvement") == 0.5 and not payload.get("holdout_ablation", {}).get("regression_case_ids"),
        "inputs_hash_bound_and_uncontaminated": payload.get("contamination", {}).get("passed") is True and all(payload.get("source_inputs", {}).get(x, {}).get("sha256") for x in ("events", "cases")),
        "credit_and_rollback_explicit": payload.get("credit_assignment", {}).get("unambiguous") is True and bool(payload.get("promotion", {}).get("rollback")),
        "adversarial_variants_rejected": all(row["exit_code"] == 2 and row["payload"].get("status") == "rejected" for row in negatives),
    }
    result = {
        "schema_version": "phase22.curriculum_data_loop.v1", "journey_id": "NT-model-training", "run_id": run_id,
        "repo_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip(),
        "production_entrypoint": str(tool), "inputs": [str(events), str(cases)], "positive": positive, "negatives": negatives,
        "assertions": assertions, "status": "PASS_WITH_KNOWN_LIMITATIONS" if all(assertions.values()) else "FAIL",
        "limitations": ["No model weights were trained; this validates the active-learning/curriculum data-policy loop only.", "The improvement is bounded to the hash-addressed holdout and is not an out-of-domain claim."],
    }
    result_path = run_dir / "journey-result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert all(assertions.values()), result_path
