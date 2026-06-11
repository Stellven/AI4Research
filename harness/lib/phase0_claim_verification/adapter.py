"""Adapter from compact AI4Research Phase 0 artifacts into Solar-shaped objects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .comparator import summarize_comparisons
from .schemas import (
    BenchmarkClaim,
    BenchmarkContract,
    ClaimComparison,
    ObservedMetric,
    Phase0EvidenceMap,
    Phase0RunManifest,
    Phase0VerificationSummary,
)


@dataclass(frozen=True)
class MigrationBundle:
    claims: tuple[BenchmarkClaim, ...]
    contracts: tuple[BenchmarkContract, ...]
    observed_metrics: tuple[ObservedMetric, ...]
    comparisons: tuple[ClaimComparison, ...]
    evidence_maps: tuple[Phase0EvidenceMap, ...]
    run_manifest: Phase0RunManifest
    summary: Phase0VerificationSummary
    source_artifacts: dict[str, str]
    benchmark_run_result: dict[str, Any]


class AI4ResearchPhase0ArtifactAdapter:
    """Load a compact fixture that references the previous Phase 0 artifacts.

    The adapter does not execute benchmark commands. It replays recorded claim,
    contract, metric, and verdict data into the Solar migration schemas.
    """

    def load_fixture(self, path: str | Path) -> MigrationBundle:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return self.from_payload(payload)

    def from_payload(self, payload: dict[str, Any]) -> MigrationBundle:
        claims: list[BenchmarkClaim] = []
        contracts: list[BenchmarkContract] = []
        metrics: list[ObservedMetric] = []
        comparisons: list[ClaimComparison] = []
        evidence_maps: list[Phase0EvidenceMap] = []

        run_id = str(payload["run"]["run_id"])
        for item in payload["claims"]:
            claim = BenchmarkClaim(
                claim_id=item["claim_id"],
                paper_location=item["paper_location"],
                metric_name=item["metric_name"],
                dataset=item["dataset"],
                split=item["split"],
                config=item["config"],
                expected_value=item.get("expected_value"),
                expected_direction_or_tolerance=item["expected_direction_or_tolerance"],
                extraction_evidence_ids=tuple(item["extraction_evidence_ids"]),
                claim_text=item.get("claim_text", ""),
            )
            contract_payload = item["contract"]
            contract = BenchmarkContract(
                contract_id=contract_payload["contract_id"],
                claim_id=claim.claim_id,
                runnable_target=contract_payload["runnable_target"],
                metric_definition=contract_payload["metric_definition"],
                aggregation_rule=contract_payload["aggregation_rule"],
                tolerance=contract_payload.get("tolerance"),
                comparison_logic=contract_payload["comparison_logic"],
                required_artifacts=tuple(contract_payload["required_artifacts"]),
                human_approval_state=contract_payload.get("human_approval_state", "approved"),
                reconstructed_path=bool(contract_payload.get("reconstructed_path", False)),
                deviation_notes=tuple(contract_payload.get("deviation_notes", ())),
            )

            item_metrics = tuple(
                ObservedMetric(
                    observed_metric_id=metric["observed_metric_id"],
                    run_id=metric.get("run_id", run_id),
                    metric_name=metric["metric_name"],
                    observed_value=metric.get("observed_value"),
                    dataset=metric.get("dataset", claim.dataset),
                    split=metric.get("split", claim.split),
                    config=metric.get("config", claim.config),
                    source_artifact_ids=tuple(metric["source_artifact_ids"]),
                    parser_confidence=float(metric.get("parser_confidence", 1.0)),
                )
                for metric in item.get("observed_metrics", ())
            )

            comparison_payload = item["comparison"]
            comparison = ClaimComparison(
                claim_id=claim.claim_id,
                contract_id=contract.contract_id,
                observed_metric_ids=tuple(metric.observed_metric_id for metric in item_metrics),
                claim_verdict_status=comparison_payload["claim_verdict_status"],
                execution_readiness_status=comparison_payload["execution_readiness_status"],
                evidence_ids=tuple(comparison_payload["evidence_ids"]),
                mismatch_summary=comparison_payload["mismatch_summary"],
                limitations=tuple(comparison_payload.get("limitations", ())),
                comparison_basis=comparison_payload["comparison_basis"],
            )

            evidence_maps.append(
                Phase0EvidenceMap(
                    claim_id=claim.claim_id,
                    contract_id=contract.contract_id,
                    run_id=run_id,
                    observed_metric_ids=comparison.observed_metric_ids,
                    paper_evidence_ids=claim.extraction_evidence_ids,
                    run_evidence_ids=tuple(comparison.evidence_ids),
                    limitation_evidence_ids=tuple(comparison_payload.get("limitation_evidence_ids", ())),
                )
            )

            claims.append(claim)
            contracts.append(contract)
            metrics.extend(item_metrics)
            comparisons.append(comparison)

        source_artifacts = dict(payload.get("source_artifacts", {}))
        run_manifest = Phase0RunManifest(
            run_id=run_id,
            benchmark_run_result_path=payload["run"]["benchmark_run_result_path"],
            stdout_path=payload["run"].get("stdout_path"),
            stderr_path=payload["run"].get("stderr_path"),
            artifact_paths=tuple(source_artifacts.values()),
            evidence_ids=tuple(payload["run"]["evidence_ids"]),
            deviation_notes=tuple(payload["run"].get("deviation_notes", ())),
        )

        summary = summarize_comparisons(
            paper_id=payload["paper"]["paper_id"],
            run_id=run_id,
            comparisons=tuple(comparisons),
            report_path=payload["expected_summary"]["report_path"],
            key_limitations=tuple(payload["expected_summary"]["key_limitations"]),
        )

        expected = payload["expected_summary"]
        if summary.paper_level_status != expected["paper_level_status"]:
            raise ValueError("fixture replay changed paper_level_status")
        if summary.full_paper_claim_status != expected["full_paper_claim_status"]:
            raise ValueError("fixture replay changed full_paper_claim_status")
        if summary.claim_status_counts != expected["claim_status_counts"]:
            raise ValueError("fixture replay changed claim_status_counts")

        benchmark_run_result = {
            "schema_version": "benchmark.run.v1",
            "run_id": run_id,
            "benchmark": payload["run"]["benchmark"],
            "benchmark_version": payload["run"].get("benchmark_version", "phase0-replay"),
            "dataset": payload["run"].get("dataset", "skillgen-phase0"),
            "adapter": "ai4research-phase0-replay",
            "agent": "solar-migration-test",
            "model": "recorded-artifact",
            "env": "replay",
            "tasks_requested": [claim.claim_id for claim in claims],
            "tasks_completed": [claim.claim_id for claim in claims],
            "score": None,
            "pass_count": summary.claim_status_counts.get("reproduced", 0)
            + summary.claim_status_counts.get("partially_reproduced", 0),
            "fail_count": summary.claim_status_counts.get("not_reproduced", 0),
            "pending_count": summary.claim_status_counts.get("blocked", 0)
            + summary.claim_status_counts.get("not_testable", 0),
            "started_at": payload["run"].get("started_at", "2026-06-10T00:00:00Z"),
            "completed_at": payload["run"].get("completed_at", "2026-06-10T00:00:00Z"),
            "duration_sec": 0.0,
            "command": ["replay-existing-phase0-artifacts"],
            "exit_code": 0,
            "stdout_path": run_manifest.stdout_path,
            "stderr_path": run_manifest.stderr_path,
            "artifacts": list(run_manifest.artifact_paths),
            "verdict": summary.paper_level_status,
            "failure_modes": [],
            "limitations": list(summary.key_limitations),
        }

        return MigrationBundle(
            claims=tuple(claims),
            contracts=tuple(contracts),
            observed_metrics=tuple(metrics),
            comparisons=tuple(comparisons),
            evidence_maps=tuple(evidence_maps),
            run_manifest=run_manifest,
            summary=summary,
            source_artifacts=source_artifacts,
            benchmark_run_result=benchmark_run_result,
        )

