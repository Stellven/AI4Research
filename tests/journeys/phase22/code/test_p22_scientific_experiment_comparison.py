from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_p22_scientific_experiment_comparison(
    repo_root: Path, phase22_python: str
) -> None:
    timestamp = datetime.now(timezone.utc)
    run_id = "p22-scientific-comparison-" + timestamp.strftime("%Y%m%dT%H%M%SZ")
    output = repo_root / "outputs" / "phase22-real-journeys" / run_id
    output.mkdir(parents=True)
    fixture = (
        repo_root
        / "tests"
        / "journeys"
        / "phase22"
        / "fixtures"
        / "significant"
        / "scientific_comparison"
    )
    protocol_path = fixture / "protocol.json"
    dataset_path = fixture / "labeled_retrieval.jsonl"
    trust_registry_path = (
        repo_root
        / "tests"
        / "journeys"
        / "phase22"
        / "fixtures"
        / "significant"
        / "trust_registry.json"
    )
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    dataset_hash = _sha256(dataset_path)
    protocol_git_path = protocol_path.relative_to(repo_root).as_posix()
    protocol_commit = "afb253f0f41518737be3338f1ba431968ee10016"
    protocol_blob = subprocess.check_output(
        ["git", "rev-parse", f"{protocol_commit}:{protocol_git_path}"],
        cwd=repo_root,
        text=True,
    ).strip()
    attestation_args = [
        "--protocol-repo", str(repo_root),
        "--protocol-commit", protocol_commit,
        "--protocol-path", protocol_git_path,
        "--protocol-blob", protocol_blob,
        "--trust-registry", str(trust_registry_path),
    ]

    reranker_path = repo_root / "harness" / "lib" / "retrieval_reranker.py"
    observation_path = output / "retrieval-observations.json"
    reranker_command = [
        phase22_python,
        str(reranker_path),
        "train",
        "--dataset",
        str(dataset_path),
        "--k",
        "1",
        "--output",
        str(observation_path),
    ]
    reranker = subprocess.run(
        reranker_command, capture_output=True, text=True, timeout=30
    )
    observations = json.loads(observation_path.read_text(encoding="utf-8"))
    observation_hash = _sha256(observation_path)
    result_dir = output / "experiment-results"
    result_dir.mkdir()
    result_paths: list[Path] = []

    for query in observations["queries"]:
        pair_id = query["query_id"]
        for arm, metric in (
            ("base_score", query["base_ndcg_at_k"]),
            ("linear_reranker", query["rerank_ndcg_at_k"]),
        ):
            observation = {
                "observation_id": f"{pair_id}-{arm}",
                "pair_id": pair_id,
                "arm": arm,
                "replicate_id": f"{pair_id}-{arm}",
                "independence_value": pair_id,
                "source_artifact_sha256": observation_hash,
            }
            document = {
                "schema": "experiment_result.v1",
                "task_id": "phase22.retrieval-ranking-poc",
                "sprint_id": run_id,
                "node_id": "retrieval-ranking-experiment",
                "status": "completed",
                "inputs": {"observation": observation},
                "outputs": {
                    "result": {
                        "experiment_id": f"{run_id}-{pair_id}-{arm}",
                        "outcome": "supports" if metric > 0 else "inconclusive",
                        "metrics": [
                            {
                                "name": protocol["primary_metric"],
                                "value": metric,
                                "unit": protocol["metric_unit"],
                            }
                        ],
                        "evidence_ids": [
                            f"retrieval-observation:{pair_id}",
                            f"sha256:{observation_hash}",
                        ],
                        "execution_mode": "production_local",
                        "command_run": " ".join(map(str, reranker_command)),
                        "logs": ["metric independently derived from the hash-bound production reranker artifact"],
                    }
                },
                "artifacts": [
                    {
                        "type": "labeled_dataset",
                        "path": str(dataset_path),
                        "sha256": dataset_hash,
                    },
                    {
                        "type": "production_metric_observations",
                        "path": str(observation_path),
                        "sha256": observation_hash,
                    },
                ],
                "provenance": {
                    "operator_id": "retrieval_reranker.py",
                    "implementation_package": "harness/lib/retrieval_reranker.py",
                    "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                },
                "limitations": [
                    "One held-out query is the declared independent unit.",
                    "The bounded POC does not establish external validity in other domains.",
                ],
            }
            path = result_dir / f"{pair_id}-{arm}.experiment_result.v1.json"
            path.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result_paths.append(path)

    comparator_path = (
        repo_root / "harness" / "lib" / "scientific_experiment_comparison.py"
    )
    comparison_path = output / "scientific-comparison.json"
    comparison_command = [
        phase22_python,
        str(comparator_path),
        "compare",
        "--results",
        *[str(path) for path in result_paths],
        *attestation_args,
        "--output",
        str(comparison_path),
    ]
    comparison_process = subprocess.run(
        comparison_command, capture_output=True, text=True, timeout=30
    )
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))

    rejected_path = output / "missing-pair-rejection.json"
    rejection_command = [
        phase22_python,
        str(comparator_path),
        "compare",
        "--results",
        *[str(path) for path in result_paths[:-2]],
        *attestation_args,
        "--output",
        str(rejected_path),
    ]
    rejection_process = subprocess.run(
        rejection_command, capture_output=True, text=True, timeout=30
    )
    rejection = json.loads(rejected_path.read_text(encoding="utf-8"))

    metric_attack_dir = output / "metric-attack-results"
    metric_attack_dir.mkdir()
    metric_attack_paths = []
    for source in result_paths:
        copied = metric_attack_dir / source.name
        copied.write_bytes(source.read_bytes())
        metric_attack_paths.append(copied)
    attacked = json.loads(metric_attack_paths[0].read_text(encoding="utf-8"))
    attacked["outputs"]["result"]["metrics"][0]["value"] = 100
    metric_attack_paths[0].write_text(json.dumps(attacked, indent=2) + "\n", encoding="utf-8")
    metric_attack_output = output / "metric-100-attack-rejection.json"
    metric_attack_command = [
        phase22_python, str(comparator_path), "compare", "--results",
        *[str(path) for path in metric_attack_paths], *attestation_args,
        "--output", str(metric_attack_output),
    ]
    metric_attack_process = subprocess.run(metric_attack_command, capture_output=True, text=True, timeout=30)
    metric_attack = json.loads(metric_attack_output.read_text(encoding="utf-8"))

    embedded_attack_dir = output / "embedded-plan-attack-results"
    embedded_attack_dir.mkdir()
    embedded_attack_paths = []
    for source in result_paths:
        copied = embedded_attack_dir / source.name
        copied.write_bytes(source.read_bytes())
        embedded_attack_paths.append(copied)
    attacked = json.loads(embedded_attack_paths[0].read_text(encoding="utf-8"))
    attacked["inputs"]["comparison"] = {
        "alpha": 1.0,
        "expected_pair_ids": protocol["expected_pair_ids"][:4],
    }
    embedded_attack_paths[0].write_text(json.dumps(attacked, indent=2) + "\n", encoding="utf-8")
    embedded_attack_output = output / "embedded-4-pair-attack-comparison.json"
    embedded_attack_command = [
        phase22_python, str(comparator_path), "compare", "--results",
        *[str(path) for path in embedded_attack_paths], *attestation_args,
        "--output", str(embedded_attack_output),
    ]
    embedded_attack_process = subprocess.run(embedded_attack_command, capture_output=True, text=True, timeout=30)
    embedded_attack = json.loads(embedded_attack_output.read_text(encoding="utf-8"))

    untrusted_registry = output / "untrusted-registry.json"
    trusted_payload = json.loads(trust_registry_path.read_text(encoding="utf-8"))
    trusted_payload["trusted_artifacts"] = [
        item
        for item in trusted_payload["trusted_artifacts"]
        if item.get("purpose") != "scientific_preregistration_protocol"
    ]
    untrusted_registry.write_text(json.dumps(trusted_payload, indent=2) + "\n", encoding="utf-8")
    untrusted_protocol_output = output / "untrusted-protocol-rejection.json"
    untrusted_protocol_command = [
        phase22_python, str(comparator_path), "compare", "--results",
        *[str(path) for path in result_paths], "--protocol-repo", str(repo_root),
        "--protocol-commit", protocol_commit, "--protocol-path", protocol_git_path,
        "--protocol-blob", protocol_blob, "--trust-registry", str(untrusted_registry),
        "--output", str(untrusted_protocol_output),
    ]
    untrusted_protocol_process = subprocess.run(
        untrusted_protocol_command, capture_output=True, text=True, timeout=30
    )
    untrusted_protocol = json.loads(untrusted_protocol_output.read_text(encoding="utf-8"))

    assertions = {
        "real_production_reranker_completed": reranker.returncode == 0
        and observations["status"] == "accepted",
        "sixteen_completed_experiment_results": len(result_paths) == 16
        and all(json.loads(path.read_text())["status"] == "completed" for path in result_paths),
        "comparison_cli_accepted": comparison_process.returncode == 0
        and comparison["status"] == "accepted",
        "pre_registered_pairs_complete": comparison["sample"]["paired_count"] == 8
        and comparison["analysis_plan"]["pre_registered_pairs"]
        == protocol["expected_pair_ids"],
        "effect_and_uncertainty_reported": comparison["effect"]["variant_minus_baseline"]
        == 0.75
        and comparison["effect"]["oriented_95_percent_t_interval"][0] > 0
        and comparison["uncertainty"]["two_sided_sign_flip_p_value"] < 0.05,
        "all_inputs_and_artifacts_hash_bound": len(comparison["sources"]) == 16
        and all(source["sha256"] for source in comparison["sources"])
        and all(len(source["verified_artifacts"]) == 2 for source in comparison["sources"]),
        "canonical_result_gate_accepted_every_input": all(
            source["canonical_experiment_result_gate"]["ok"]
            for source in comparison["sources"]
        ),
        "git_attested_protocol_controls_analysis": comparison["protocol_attestation"]["blob"] == protocol_blob
        and comparison["protocol_attestation"]["commit"] == protocol_commit,
        "protocol_matches_out_of_band_trust_registry": comparison["protocol_attestation"]["trusted_artifact"]["anchor_id"]
        == "phase22-protocol-registry"
        and comparison["protocol_attestation"]["content_sha256"]
        == "f6a4653fd6e26ce495f9fd0b06a915b37046da9c86da2fa890a0b17919b0fe11",
        "metric_100_attack_rejected": metric_attack_process.returncode == 2
        and metric_attack["status"] == "rejected"
        and "result_metric_disagrees_with_hashed_observation" in metric_attack["errors"][0],
        "embedded_8_to_4_plan_attack_has_no_authority": embedded_attack_process.returncode == 0
        and embedded_attack["status"] == "accepted"
        and embedded_attack["sample"]["paired_count"] == 8
        and len(embedded_attack["analysis_plan"]["pre_registered_pairs"]) == 8,
        "missing_pair_rejected_without_effect_claim": rejection_process.returncode == 2
        and rejection["status"] == "rejected"
        and "cherry_picked_or_missing_pairs" in rejection["errors"][0],
        "untrusted_protocol_registry_rejected": untrusted_protocol_process.returncode == 2
        and untrusted_protocol["status"] == "rejected"
        and "protocol_not_matched_by_trust_registry" in untrusted_protocol["errors"][0],
    }
    evidence = {
        "schema_version": "phase22.scientific_experiment_comparison_journey.v1",
        "journey_id": "P22-SIGNIFICANT-SCIENTIFIC-COMPARISON",
        "diagnostic_issue": "P22-REPAIR-044",
        "task": "Compare a baseline and variant using completed paired experiment results without overstating scientific significance.",
        "run_id": run_id,
        "repo_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip(),
        "realistic_input": {
            "protocol": str(protocol_path),
            "dataset": str(dataset_path),
            "pair_count": 8,
        },
        "production_entrypoints": [str(reranker_path), str(comparator_path)],
        "exact_commands": [reranker_command, comparison_command, rejection_command, metric_attack_command, embedded_attack_command],
        "environment": {
            "python": phase22_python,
            "network": "not required",
            "provider_credentials": "not required",
        },
        "minimum_observable_success_conditions": list(assertions),
        "level_2_features_exercised": [
            "Data, Benchmarks, Curriculum & Observability",
            "Evaluation & Verification",
        ],
        "exit_codes": {
            "reranker": reranker.returncode,
            "comparison": comparison_process.returncode,
            "intentional_missing_pair_rejection": rejection_process.returncode,
            "metric_100_attack": metric_attack_process.returncode,
            "embedded_8_to_4_plan_attack": embedded_attack_process.returncode,
        },
        "output_tails": {
            "reranker_stdout": reranker.stdout[-500:],
            "comparison_stdout": comparison_process.stdout[-500:],
            "rejection_stderr": rejection_process.stderr[-500:],
        },
        "artifacts": {
            "raw_observations": str(observation_path),
            "experiment_result_directory": str(result_dir),
            "comparison": str(comparison_path),
            "negative_rejection": str(rejected_path),
            "metric_attack_rejection": str(metric_attack_output),
            "embedded_plan_attack_comparison": str(embedded_attack_output),
            "untrusted_protocol_rejection": str(untrusted_protocol_output),
            "trust_registry": str(trust_registry_path),
        },
        "assertions": assertions,
        "status": "PASS_WITH_KNOWN_LIMITATIONS"
        if all(assertions.values())
        else "FAIL",
        "limitations": comparison.get("limitations", [])
        + [
            "This closes a narrow paired retrieval POC path, not broad scientific-domain benchmarking or external validity."
        ],
    }
    evidence_path = output / "journey-result.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    assert all(assertions.values()), evidence_path
