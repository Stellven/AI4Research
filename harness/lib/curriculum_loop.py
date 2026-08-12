#!/usr/bin/env python3
"""Evaluate a bounded curriculum candidate against isolated holdout cases."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _rows(path: Path) -> list[dict[str, Any]]:
    out = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{number}: row must be an object")
        out.append(item)
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(events_path: Path, cases_path: Path, candidate_id: str) -> dict[str, Any]:
    events, cases = _rows(events_path), _rows(cases_path)
    errors: list[str] = []
    event_ids = [str(row.get("event_id") or "") for row in events]
    case_ids = [str(row.get("case_id") or "") for row in cases]
    if not event_ids or any(not x for x in event_ids) or len(set(event_ids)) != len(event_ids):
        errors.append("event_ids_missing_or_duplicate")
    if not case_ids or any(not x for x in case_ids) or len(set(case_ids)) != len(case_ids):
        errors.append("case_ids_missing_or_duplicate")
    failures = [row for row in events if str(row.get("outcome")) == "failed"]
    clusters = Counter(str(row.get("failure_cluster") or "") for row in failures)
    if not failures or "" in clusters:
        errors.append("failure_events_missing_cluster")
    train = [row for row in cases if row.get("split") == "train"]
    holdout = [row for row in cases if row.get("split") == "holdout"]
    if not train or not holdout or len(train) + len(holdout) != len(cases):
        errors.append("train_and_holdout_splits_required")
    train_ids = {str(row.get("case_id")) for row in train}
    holdout_ids = {str(row.get("case_id")) for row in holdout}
    train_sources = {str(x) for row in train for x in row.get("source_event_ids", [])}
    holdout_sources = {str(x) for row in holdout for x in row.get("source_event_ids", [])}
    if train_ids & holdout_ids or train_sources & holdout_sources:
        errors.append("train_holdout_contamination")
    if not train_sources or not train_sources <= set(event_ids):
        errors.append("training_cases_not_bound_to_failure_events")
    if any(str(row.get("failure_cluster") or "") not in clusters for row in train):
        errors.append("training_case_cluster_not_mined")
    changed, regressions = [], []
    baseline_passes = candidate_passes = 0
    for row in holdout:
        before, after = row.get("baseline_passed"), row.get("candidate_passed")
        if not isinstance(before, bool) or not isinstance(after, bool):
            errors.append(f"non_boolean_outcome:{row.get('case_id')}")
            continue
        baseline_passes += int(before)
        candidate_passes += int(after)
        if before != after:
            changed.append(str(row.get("case_id")))
            if row.get("intervention_ids") != [candidate_id]:
                errors.append(f"ambiguous_credit_assignment:{row.get('case_id')}")
        if before and not after:
            regressions.append(str(row.get("case_id")))
    if regressions:
        errors.append("holdout_regression")
    if candidate_passes <= baseline_passes:
        errors.append("no_holdout_improvement")
    total, promoted = len(holdout), not errors
    return {
        "schema_version": "solar.curriculum_evaluation.v1",
        "status": "promoted" if promoted else "rejected",
        "candidate": {"candidate_id": candidate_id, "prioritized_clusters": [{"failure_cluster": k, "failure_count": v} for k, v in clusters.most_common()], "training_case_ids": sorted(train_ids)},
        "source_inputs": {"events": {"path": str(events_path), "sha256": _sha(events_path), "rows": len(events)}, "cases": {"path": str(cases_path), "sha256": _sha(cases_path), "rows": len(cases)}},
        "contamination": {"case_id_overlap": sorted(train_ids & holdout_ids), "source_event_id_overlap": sorted(train_sources & holdout_sources), "passed": not bool(train_ids & holdout_ids or train_sources & holdout_sources)},
        "holdout_ablation": {"case_count": total, "baseline_passed": baseline_passes, "candidate_passed": candidate_passes, "baseline_rate": baseline_passes / total if total else 0.0, "candidate_rate": candidate_passes / total if total else 0.0, "absolute_improvement": (candidate_passes - baseline_passes) / total if total else 0.0, "changed_case_ids": changed, "regression_case_ids": regressions},
        "credit_assignment": {"method": "single_intervention_holdout_ablation", "candidate_id": candidate_id, "changed_case_ids": changed, "unambiguous": not any(x.startswith("ambiguous_credit_assignment") for x in errors)},
        "promotion": {"promoted": promoted, "guardrails": ["no_train_holdout_overlap", "no_holdout_regression", "positive_holdout_delta", "single_intervention_credit"], "rollback": f"disable curriculum candidate {candidate_id} and restore the previous case sampler"},
        "errors": errors,
        "limitations": ["This evaluates a deterministic curriculum/data-policy candidate; it does not train or modify model weights.", "The result applies only to the supplied hash-bound holdout and does not imply out-of-domain improvement."],
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="curriculum_loop.py")
    ap.add_argument("evaluate", nargs="?")
    ap.add_argument("--events", required=True, type=Path)
    ap.add_argument("--cases", required=True, type=Path)
    ap.add_argument("--candidate-id", required=True)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    try:
        result = evaluate(args.events.resolve(), args.cases.resolve(), args.candidate_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"schema_version": "solar.curriculum_evaluation.v1", "status": "rejected", "errors": [str(exc)]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "promoted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
