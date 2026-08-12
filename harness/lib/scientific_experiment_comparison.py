#!/usr/bin/env python3
"""Hash-bound paired comparison of completed experiment_result.v1 records."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(__file__).resolve().parents[1]
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))
from evaluators.scientific import experiment_result_gate  # noqa: E402

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


def _is_git_oid(value: Any) -> bool:
    return isinstance(value, str) and len(value) in {40, 64} and set(value) <= HEX


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidComparison(f"invalid_json:{path}:{exc}") from exc
    _need(isinstance(value, dict), f"result_not_object:{path}")
    return value


def _validate_result(path: Path) -> dict[str, Any]:
    doc = _read(path)
    gate = experiment_result_gate.evaluate(doc, path)
    _need(gate.ok, f"canonical_experiment_result_gate:{path}:{'|'.join(gate.reasons)}")
    _need(doc["status"] == "completed", f"result_not_completed:{path}")
    result = doc["outputs"].get("result")
    _need(result.get("execution_mode") == "production_local", f"non_production_execution_mode:{path}")
    _need(isinstance(result.get("command_run"), str) and result["command_run"], f"missing_command_run:{path}")
    _need(isinstance(result.get("logs"), list) and result["logs"], f"missing_logs:{path}")
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
    doc["_canonical_gate"] = gate.to_dict()
    return doc


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=15
    )


def _protocol(
    repo: Path, commit: str, git_path: str, expected_blob: str
) -> tuple[dict[str, Any], dict[str, Any], datetime]:
    _need(repo.resolve().is_dir(), "protocol_repo_missing")
    _need(bool(commit) and bool(git_path) and _is_git_oid(expected_blob), "protocol_attestation_arguments")
    commit_type = _git(repo, "cat-file", "-t", commit)
    _need(commit_type.returncode == 0 and commit_type.stdout.strip() == "commit", "protocol_commit_not_found")
    ancestor = _git(repo, "merge-base", "--is-ancestor", commit, "HEAD")
    _need(ancestor.returncode == 0, "protocol_commit_not_ancestor_of_current_head")
    blob_proc = _git(repo, "rev-parse", f"{commit}:{git_path}")
    _need(blob_proc.returncode == 0, "protocol_blob_not_found_at_commit")
    actual_blob = blob_proc.stdout.strip().lower()
    _need(actual_blob == expected_blob.lower(), "protocol_blob_attestation_mismatch")
    content_proc = _git(repo, "show", f"{commit}:{git_path}")
    _need(content_proc.returncode == 0, "protocol_content_unreadable")
    try:
        protocol = json.loads(content_proc.stdout)
    except json.JSONDecodeError as exc:
        raise InvalidComparison(f"protocol_invalid_json:{exc}") from exc
    _need(isinstance(protocol, dict), "protocol_not_object")
    required = {
        "schema", "study_id", "question", "analysis_plan", "baseline_arm",
        "variant_arm", "independence_unit", "dataset_sha256", "expected_pair_ids",
        "primary_metric", "metric_unit", "higher_is_better", "alpha", "minimum_pairs",
        "limitations",
    }
    _need(set(protocol) == required, "protocol_schema_fields")
    _need(protocol["schema"] == "solar.scientific_comparison_protocol.v1", "protocol_schema_identity")
    _need(protocol["analysis_plan"] == PLAN, "unsupported_analysis_plan")
    for key in (
        "study_id", "question", "baseline_arm", "variant_arm",
        "independence_unit", "primary_metric", "metric_unit",
    ):
        _need(isinstance(protocol[key], str) and protocol[key], f"invalid_protocol_{key}")
    _need(protocol["baseline_arm"] != protocol["variant_arm"], "identical_arms")
    _need(_is_hash(protocol["dataset_sha256"]), "invalid_dataset_sha256")
    expected = protocol["expected_pair_ids"]
    _need(isinstance(expected, list) and expected and all(isinstance(x, str) and x for x in expected), "invalid_expected_pairs")
    _need(len(expected) == len(set(expected)), "duplicate_expected_pairs")
    _need(isinstance(protocol["higher_is_better"], bool), "invalid_direction")
    _need(isinstance(protocol["alpha"], (int, float)) and float(protocol["alpha"]) == 0.05, "only_alpha_0.05_supported")
    _need(isinstance(protocol["minimum_pairs"], int) and protocol["minimum_pairs"] >= 4, "minimum_pairs_below_four")
    _need(len(expected) >= protocol["minimum_pairs"], "pre_registered_sample_insufficient")
    _need(isinstance(protocol["limitations"], list) and protocol["limitations"], "protocol_limitations_required")
    time_proc = _git(repo, "show", "-s", "--format=%cI", commit)
    _need(time_proc.returncode == 0, "protocol_commit_time_unreadable")
    commit_time = datetime.fromisoformat(time_proc.stdout.strip())
    attestation = {
        "repo": str(repo.resolve()), "commit": commit,
        "git_path": git_path, "blob": actual_blob,
        "commit_time": commit_time.isoformat(),
        "content_sha256": hashlib.sha256(content_proc.stdout.encode()).hexdigest(),
        "ancestor_of_head": True,
    }
    return protocol, attestation, commit_time


def _result_metric(doc: dict[str, Any], name: str, unit: str, path: Path) -> float:
    metrics = doc["outputs"]["result"]["metrics"]
    matches = [item for item in metrics if isinstance(item, dict) and item.get("name") == name]
    _need(len(matches) == 1, f"primary_metric_not_exactly_once:{path}")
    _need(matches[0].get("unit") == unit, f"metric_unit_mismatch:{path}")
    value = matches[0].get("value")
    _need(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)), f"metric_not_finite_number:{path}")
    return float(value)


def _timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidComparison(f"invalid_{label}_timestamp") from exc
    _need(parsed.tzinfo is not None, f"naive_{label}_timestamp")
    return parsed


def _observation(
    doc: dict[str, Any], path: Path, protocol: dict[str, Any], commit_time: datetime
) -> tuple[dict[str, Any], float, dict[str, Any]]:
    reference = doc["inputs"].get("observation")
    _need(isinstance(reference, dict), f"missing_observation_reference:{path}")
    required = {
        "observation_id", "pair_id", "arm", "replicate_id",
        "independence_value", "source_artifact_sha256",
    }
    _need(set(reference) == required, f"observation_reference_fields:{path}")
    for key in required - {"source_artifact_sha256"}:
        _need(isinstance(reference[key], str) and reference[key], f"invalid_observation_{key}:{path}")
    _need(_is_hash(reference["source_artifact_sha256"]), f"invalid_observation_hash:{path}")
    artifact_matches = [
        item for item in doc["_verified_artifacts"]
        if item["type"] == "production_metric_observations"
        and item["sha256"].lower() == reference["source_artifact_sha256"].lower()
    ]
    _need(len(artifact_matches) == 1, f"observation_artifact_not_exactly_once:{path}")
    artifact = artifact_matches[0]
    observation_doc = _read(Path(artifact["path"]))
    _need(
        observation_doc.get("schema_version") == "solar.retrieval_reranker.v1",
        f"observation_schema_identity:{path}",
    )
    _need(observation_doc.get("status") == "accepted", f"observation_run_not_accepted:{path}")
    source = observation_doc.get("source")
    _need(isinstance(source, dict), f"observation_source_missing:{path}")
    _need(
        source.get("sha256") == protocol["dataset_sha256"],
        f"observation_dataset_mismatch:{path}",
    )
    _need(_timestamp(doc["provenance"]["timestamp"], "result") > commit_time, f"result_precedes_protocol_attestation:{path}")
    queries = observation_doc.get("queries")
    _need(isinstance(queries, list) and queries, f"observation_queries_missing:{path}")
    matches = [row for row in queries if isinstance(row, dict) and row.get("query_id") == reference["pair_id"]]
    _need(len(matches) == 1, f"observation_pair_not_exactly_once:{path}")
    row = matches[0]
    _need(reference["pair_id"] == reference["independence_value"], f"observation_independence_mismatch:{path}")
    _need(reference["pair_id"] in protocol["expected_pair_ids"], f"unregistered_pair:{reference['pair_id']}")
    _need(reference["arm"] in {protocol["baseline_arm"], protocol["variant_arm"]}, f"undeclared_arm:{reference['arm']}")
    metric_field = {
        protocol["baseline_arm"]: "base_ndcg_at_k",
        protocol["variant_arm"]: "rerank_ndcg_at_k",
    }[reference["arm"]]
    value = row.get(metric_field)
    _need(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)), f"observation_value_not_finite:{path}")
    recorded = _result_metric(doc, protocol["primary_metric"], protocol["metric_unit"], path)
    _need(recorded == float(value), f"result_metric_disagrees_with_hashed_observation:{path}")
    return reference, float(value), artifact


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


def compare(
    paths: list[Path], *, protocol_repo: Path, protocol_commit: str,
    protocol_path: str, protocol_blob: str,
) -> dict[str, Any]:
    _need(len(paths) >= 2, "at_least_two_results_required")
    protocol, protocol_attestation, commit_time = _protocol(
        protocol_repo, protocol_commit, protocol_path, protocol_blob
    )
    resolved = [path.resolve() for path in paths]
    _need(len(resolved) == len(set(resolved)), "duplicate_result_path")
    docs = [_validate_result(path) for path in resolved]
    experiment_ids = [doc["outputs"]["result"]["experiment_id"] for doc in docs]
    _need(len(experiment_ids) == len(set(experiment_ids)), "duplicate_experiment_id")
    pairs: dict[str, dict[str, tuple[float, str, str]]] = {}
    independence: dict[str, str] = {}
    replicate_ids: list[str] = []
    sources = []
    for path, doc in zip(resolved, docs):
        reference, value, observation_artifact = _observation(
            doc, path, protocol, commit_time
        )
        pair_id = reference["pair_id"]
        _need(pair_id not in independence or independence[pair_id] == reference["independence_value"], f"pair_independence_mismatch:{pair_id}")
        independence[pair_id] = reference["independence_value"]
        arms = pairs.setdefault(pair_id, {})
        arm = reference["arm"]
        _need(arm not in arms, f"duplicate_pair_arm:{pair_id}:{arm}")
        replicate_ids.append(reference["replicate_id"])
        arms[arm] = (value, doc["outputs"]["result"]["experiment_id"], reference["replicate_id"])
        sources.append({
            "path": str(path), "sha256": _sha256(path),
            "experiment_id": doc["outputs"]["result"]["experiment_id"],
            "arm": arm, "pair_id": pair_id,
            "metric_source": observation_artifact,
            "canonical_experiment_result_gate": doc["_canonical_gate"],
            "verified_artifacts": doc["_verified_artifacts"],
        })
    _need(len(replicate_ids) == len(set(replicate_ids)), "duplicate_replicate_id")
    expected = set(protocol["expected_pair_ids"])
    _need(set(pairs) == expected, f"cherry_picked_or_missing_pairs:expected={len(expected)}:actual={len(pairs)}")
    _need(len(set(independence.values())) == len(expected), "independence_values_not_unique_across_pairs")
    baseline_arm, variant_arm = protocol["baseline_arm"], protocol["variant_arm"]
    for pair_id, arms in pairs.items():
        _need(set(arms) == {baseline_arm, variant_arm}, f"unpaired_result:{pair_id}")
    ordered = protocol["expected_pair_ids"]
    baseline = [pairs[pair][baseline_arm][0] for pair in ordered]
    variant = [pairs[pair][variant_arm][0] for pair in ordered]
    raw = [candidate - control for candidate, control in zip(variant, baseline)]
    oriented = raw if protocol["higher_is_better"] else [-value for value in raw]
    n = len(oriented)
    baseline_mean, variant_mean = statistics.fmean(baseline), statistics.fmean(variant)
    raw_mean, benefit = statistics.fmean(raw), statistics.fmean(oriented)
    sd = statistics.stdev(oriented)
    se = sd / math.sqrt(n)
    critical = T975.get(n - 1, 1.96)
    ci = [benefit - critical * se, benefit + critical * se]
    p_value, permutations, exact = _randomization_p(oriented)
    significant = p_value < protocol["alpha"] and (ci[0] > 0 or ci[1] < 0)
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
        "scope": {key: protocol[key] for key in (
            "study_id", "dataset_sha256", "primary_metric",
            "metric_unit", "higher_is_better", "independence_unit",
        )},
        "protocol_attestation": protocol_attestation,
        "analysis_plan": {"method": PLAN, "alpha": protocol["alpha"], "minimum_pairs": protocol["minimum_pairs"], "pre_registered_pairs": ordered},
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
    parser.add_argument("--protocol-repo", required=True, type=Path)
    parser.add_argument("--protocol-commit", required=True)
    parser.add_argument("--protocol-path", required=True)
    parser.add_argument("--protocol-blob", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report, exit_code = compare(
            args.results,
            protocol_repo=args.protocol_repo,
            protocol_commit=args.protocol_commit,
            protocol_path=args.protocol_path,
            protocol_blob=args.protocol_blob,
        ), 0
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
