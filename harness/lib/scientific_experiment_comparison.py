#!/usr/bin/env python3
"""Hash-bound paired comparison of completed experiment_result.v1 records."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import statistics
from pathlib import Path
from typing import Any

SCHEMA = "experiment_result.v1"
PLAN = "paired_randomization_test_v1"
HEX = set("0123456789abcdefABCDEF")
T975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


class InvalidComparison(ValueError):
    pass


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidComparison(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidComparison(f"invalid_json:{path}:{exc}") from exc
    _need(isinstance(value, dict), f"result_not_object:{path}")
    return value


def _validate_result(path: Path) -> dict[str, Any]:
    doc = _read(path)
    required = {
        "schema", "task_id", "sprint_id", "node_id", "status", "inputs",
        "outputs", "artifacts", "provenance", "limitations",
    }
    _need(set(doc) == required, f"experiment_result_schema_fields:{path}")
    _need(doc["schema"] == SCHEMA, f"wrong_schema:{path}")
    for key in ("task_id", "sprint_id", "node_id"):
        _need(isinstance(doc[key], str) and doc[key].strip(), f"invalid_{key}:{path}")
    _need(doc["status"] == "completed", f"result_not_completed:{path}")
    _need(isinstance(doc["inputs"], dict), f"inputs_not_object:{path}")
    _need(isinstance(doc["outputs"], dict), f"outputs_not_object:{path}")
    result = doc["outputs"].get("result")
    _need(isinstance(result, dict), f"missing_result:{path}")
    _need(isinstance(result.get("experiment_id"), str) and result["experiment_id"], f"missing_experiment_id:{path}")
    _need(result.get("outcome") in {"supports", "partially_supports", "refutes", "inconclusive"}, f"invalid_outcome:{path}")
    _need(isinstance(result.get("metrics"), list), f"metrics_not_array:{path}")
    _need(isinstance(result.get("evidence_ids"), list) and result["evidence_ids"], f"missing_evidence_ids:{path}")
    _need(all(isinstance(x, str) and x for x in result["evidence_ids"]), f"invalid_evidence_ids:{path}")
    provenance = doc.get("provenance")
    _need(isinstance(provenance, dict), f"provenance_not_object:{path}")
    for key in ("operator_id", "implementation_package", "timestamp"):
        _need(isinstance(provenance.get(key), str) and provenance[key], f"missing_provenance_{key}:{path}")
    _need("T" in provenance["timestamp"] and provenance["timestamp"].endswith("Z"), f"invalid_provenance_timestamp:{path}")
    _need(isinstance(doc["limitations"], list) and all(isinstance(x, str) for x in doc["limitations"]), f"invalid_limitations:{path}")
    artifacts = doc.get("artifacts")
    _need(isinstance(artifacts, list) and artifacts, f"hash_bound_artifact_required:{path}")
    verified = []
    for item in artifacts:
        _need(isinstance(item, dict) and set(item) == {"type", "path", "sha256"}, f"artifact_schema_or_hash:{path}")
        _need(isinstance(item["type"], str) and item["type"], f"artifact_type:{path}")
        _need(isinstance(item["path"], str) and item["path"], f"artifact_path:{path}")
        _need(_is_hash(item["sha256"]), f"artifact_sha256:{path}")
        artifact = Path(item["path"])
        if not artifact.is_absolute():
            artifact = path.parent / artifact
        artifact = artifact.resolve()
        _need(artifact.is_file(), f"artifact_missing:{path}:{artifact}")
        actual = _sha256(artifact)
        _need(actual.lower() == item["sha256"].lower(), f"artifact_hash_mismatch:{path}:{artifact}")
        verified.append({"type": item["type"], "path": str(artifact), "sha256": actual})
    doc["_verified_artifacts"] = verified
    return doc


def _plan(doc: dict[str, Any], path: Path) -> dict[str, Any]:
    plan = doc["inputs"].get("comparison")
    _need(isinstance(plan, dict), f"missing_comparison_plan:{path}")
    required = {
        "analysis_plan", "study_id", "arm", "baseline_arm", "variant_arm",
        "pair_id", "replicate_id", "independence_unit", "independence_value",
        "protocol_sha256", "dataset_sha256", "expected_pair_ids",
        "primary_metric", "metric_unit", "higher_is_better", "alpha", "minimum_pairs",
    }
    _need(set(plan) == required, f"comparison_plan_fields:{path}")
    _need(plan["analysis_plan"] == PLAN, f"unsupported_analysis_plan:{path}")
    for key in (
        "study_id", "arm", "baseline_arm", "variant_arm", "pair_id",
        "replicate_id", "independence_unit", "independence_value",
        "primary_metric", "metric_unit",
    ):
        _need(isinstance(plan[key], str) and plan[key], f"invalid_plan_{key}:{path}")
    _need(plan["baseline_arm"] != plan["variant_arm"], f"identical_arms:{path}")
    _need(plan["arm"] in {plan["baseline_arm"], plan["variant_arm"]}, f"undeclared_arm:{path}")
    _need(_is_hash(plan["protocol_sha256"]), f"invalid_protocol_sha256:{path}")
    _need(_is_hash(plan["dataset_sha256"]), f"invalid_dataset_sha256:{path}")
    verified_by_type = {
        item["type"]: item["sha256"].lower() for item in doc["_verified_artifacts"]
    }
    _need(
        verified_by_type.get("pre_registered_protocol")
        == plan["protocol_sha256"].lower(),
        f"protocol_hash_not_bound_to_artifact:{path}",
    )
    _need(
        verified_by_type.get("labeled_dataset") == plan["dataset_sha256"].lower(),
        f"dataset_hash_not_bound_to_artifact:{path}",
    )
    expected = plan["expected_pair_ids"]
    _need(isinstance(expected, list) and expected and all(isinstance(x, str) and x for x in expected), f"invalid_expected_pairs:{path}")
    _need(len(expected) == len(set(expected)), f"duplicate_expected_pairs:{path}")
    _need(isinstance(plan["higher_is_better"], bool), f"invalid_direction:{path}")
    _need(isinstance(plan["alpha"], (int, float)) and float(plan["alpha"]) == 0.05, f"only_alpha_0.05_supported:{path}")
    _need(isinstance(plan["minimum_pairs"], int) and plan["minimum_pairs"] >= 4, f"minimum_pairs_below_four:{path}")
    _need(len(expected) >= plan["minimum_pairs"], f"pre_registered_sample_insufficient:{path}")
    return plan


def _metric(doc: dict[str, Any], name: str, unit: str, path: Path) -> float:
    metrics = doc["outputs"]["result"]["metrics"]
    matches = [item for item in metrics if isinstance(item, dict) and item.get("name") == name]
    _need(len(matches) == 1, f"primary_metric_not_exactly_once:{path}")
    _need(matches[0].get("unit") == unit, f"metric_unit_mismatch:{path}")
    value = matches[0].get("value")
    _need(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)), f"metric_not_finite_number:{path}")
    return float(value)


def _randomization_p(differences: list[float]) -> tuple[float, int, bool]:
    observed = abs(statistics.fmean(differences))
    n = len(differences)
    if n <= 20:
        extreme = total = 0
        for signs in itertools.product((-1.0, 1.0), repeat=n):
            total += 1
            candidate = abs(statistics.fmean(sign * abs(delta) for sign, delta in zip(signs, differences)))
            extreme += candidate + 1e-15 >= observed
        return extreme / total, total, True
    total = 65536
    state = int.from_bytes(hashlib.sha256(json.dumps(differences).encode()).digest()[:8], "big") or 1
    extreme = 0
    for _ in range(total):
        signed = []
        for delta in differences:
            state ^= (state << 13) & ((1 << 64) - 1)
            state ^= state >> 7
            state ^= (state << 17) & ((1 << 64) - 1)
            signed.append(abs(delta) if state & 1 else -abs(delta))
        extreme += abs(statistics.fmean(signed)) + 1e-15 >= observed
    return (extreme + 1) / (total + 1), total, False


def compare(paths: list[Path]) -> dict[str, Any]:
    _need(len(paths) >= 2, "at_least_two_results_required")
    resolved = [path.resolve() for path in paths]
    _need(len(resolved) == len(set(resolved)), "duplicate_result_path")
    docs = [_validate_result(path) for path in resolved]
    plans = [_plan(doc, path) for doc, path in zip(docs, resolved)]
    common_keys = (
        "analysis_plan", "study_id", "baseline_arm", "variant_arm",
        "independence_unit", "protocol_sha256", "dataset_sha256",
        "expected_pair_ids", "primary_metric", "metric_unit", "higher_is_better",
        "alpha", "minimum_pairs",
    )
    common = {key: plans[0][key] for key in common_keys}
    for plan, path in zip(plans[1:], resolved[1:]):
        _need(all(plan[key] == common[key] for key in common_keys), f"mismatched_pre_registered_plan:{path}")
    experiment_ids = [doc["outputs"]["result"]["experiment_id"] for doc in docs]
    replicate_ids = [plan["replicate_id"] for plan in plans]
    _need(len(experiment_ids) == len(set(experiment_ids)), "duplicate_experiment_id")
    _need(len(replicate_ids) == len(set(replicate_ids)), "duplicate_replicate_id")
    pairs: dict[str, dict[str, tuple[float, str, str]]] = {}
    independence: dict[str, str] = {}
    sources = []
    for path, doc, plan in zip(resolved, docs, plans):
        pair_id = plan["pair_id"]
        _need(pair_id in common["expected_pair_ids"], f"unregistered_pair:{pair_id}")
        _need(pair_id not in independence or independence[pair_id] == plan["independence_value"], f"pair_independence_mismatch:{pair_id}")
        independence[pair_id] = plan["independence_value"]
        arms = pairs.setdefault(pair_id, {})
        _need(plan["arm"] not in arms, f"duplicate_pair_arm:{pair_id}:{plan['arm']}")
        value = _metric(doc, common["primary_metric"], common["metric_unit"], path)
        arms[plan["arm"]] = (value, doc["outputs"]["result"]["experiment_id"], plan["replicate_id"])
        sources.append({
            "path": str(path), "sha256": _sha256(path),
            "experiment_id": doc["outputs"]["result"]["experiment_id"],
            "arm": plan["arm"], "pair_id": pair_id,
            "verified_artifacts": doc["_verified_artifacts"],
        })
    expected = set(common["expected_pair_ids"])
    _need(set(pairs) == expected, f"cherry_picked_or_missing_pairs:expected={len(expected)}:actual={len(pairs)}")
    _need(len(set(independence.values())) == len(expected), "independence_values_not_unique_across_pairs")
    baseline_arm, variant_arm = common["baseline_arm"], common["variant_arm"]
    for pair_id, arms in pairs.items():
        _need(set(arms) == {baseline_arm, variant_arm}, f"unpaired_result:{pair_id}")
    ordered = common["expected_pair_ids"]
    baseline = [pairs[pair][baseline_arm][0] for pair in ordered]
    variant = [pairs[pair][variant_arm][0] for pair in ordered]
    raw = [candidate - control for candidate, control in zip(variant, baseline)]
    oriented = raw if common["higher_is_better"] else [-value for value in raw]
    n = len(oriented)
    baseline_mean, variant_mean = statistics.fmean(baseline), statistics.fmean(variant)
    raw_mean, benefit = statistics.fmean(raw), statistics.fmean(oriented)
    sd = statistics.stdev(oriented)
    se = sd / math.sqrt(n)
    critical = T975.get(n - 1, 1.96)
    ci = [benefit - critical * se, benefit + critical * se]
    p_value, permutations, exact = _randomization_p(oriented)
    significant = p_value < common["alpha"] and (ci[0] > 0 or ci[1] < 0)
    if significant and ci[0] > 0:
        conclusion = "supports_variant_within_declared_study"
    elif significant and ci[1] < 0:
        conclusion = "supports_baseline_within_declared_study"
    else:
        conclusion = "inconclusive_no_bounded_significant_difference"
    return {
        "schema_version": "solar.scientific_experiment_comparison.v1",
        "status": "accepted" if significant else "inconclusive",
        "conclusion": conclusion,
        "scope": {key: common[key] for key in (
            "study_id", "protocol_sha256", "dataset_sha256", "primary_metric",
            "metric_unit", "higher_is_better", "independence_unit",
        )},
        "analysis_plan": {"method": PLAN, "alpha": common["alpha"], "minimum_pairs": common["minimum_pairs"], "pre_registered_pairs": ordered},
        "sample": {"paired_count": n, "baseline_arm": baseline_arm, "variant_arm": variant_arm},
        "effect": {
            "baseline_mean": baseline_mean, "variant_mean": variant_mean,
            "variant_minus_baseline": raw_mean,
            "percent_change_from_baseline": None if baseline_mean == 0 else raw_mean / abs(baseline_mean) * 100.0,
            "oriented_mean_benefit": benefit,
            "paired_cohens_dz": None if sd == 0 else benefit / sd,
            "oriented_95_percent_t_interval": ci,
            "paired_standard_deviation": sd, "standard_error": se,
        },
        "uncertainty": {
            "two_sided_sign_flip_p_value": p_value, "sign_flip_samples": permutations,
            "exact_randomization": exact, "bounded_significant_at_alpha": significant,
        },
        "pairs": [{
            "pair_id": pair, "independence_value": independence[pair],
            "baseline": pairs[pair][baseline_arm][0], "variant": pairs[pair][variant_arm][0],
            "variant_minus_baseline": pairs[pair][variant_arm][0] - pairs[pair][baseline_arm][0],
        } for pair in ordered],
        "sources": sources, "errors": [],
        "limitations": [
            "The conclusion is limited to the hash-bound study protocol, dataset, primary metric, and declared independent units.",
            "The comparator validates recorded evidence and pre-registration consistency; it does not prove random assignment or external validity.",
            "A non-significant result is reported as inconclusive, never as proof of equivalence.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compare", nargs="?")
    parser.add_argument("--results", required=True, nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report, exit_code = compare(args.results), 0
    except (InvalidComparison, OSError, ValueError) as exc:
        report, exit_code = {
            "schema_version": "solar.scientific_experiment_comparison.v1",
            "status": "rejected", "conclusion": "invalid_or_incomplete_comparison",
            "errors": [str(exc)],
            "limitations": ["No scientific effect conclusion was produced from rejected inputs."],
        }, 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
