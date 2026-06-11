"""Minimal Phase 0 comparison policy for migration replay tests."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from .schemas import BenchmarkContract, ClaimComparison, ObservedMetric, Phase0VerificationSummary


def _numeric(value: float | str | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except ValueError:
        return None


def compare_contract_to_observed(
    contract: BenchmarkContract,
    observed_metrics: Iterable[ObservedMetric],
    *,
    readiness_status: str,
    evidence_ids: tuple[str, ...],
    expected_value: float | str | None = None,
) -> ClaimComparison:
    metrics = tuple(observed_metrics)
    if not metrics:
        return ClaimComparison(
            claim_id=contract.claim_id,
            contract_id=contract.contract_id,
            observed_metric_ids=(),
            claim_verdict_status="blocked" if readiness_status == "blocked" else "not_testable",
            execution_readiness_status=readiness_status,
            evidence_ids=evidence_ids,
            mismatch_summary="No observed metric is available for comparison.",
            limitations=("No executed benchmark evidence.",),
            comparison_basis="planning_only",
        )

    observed = _numeric(metrics[0].observed_value)
    expected = _numeric(expected_value)
    tolerance = contract.tolerance or 0.0
    reproduced = False

    if contract.comparison_logic == "delta_positive":
        reproduced = observed is not None and observed > 0
    elif contract.comparison_logic == "expected_minimum":
        reproduced = observed is not None and expected is not None and observed >= expected - tolerance
    elif contract.comparison_logic == "expected_maximum":
        reproduced = observed is not None and expected is not None and observed <= expected + tolerance
    elif contract.comparison_logic == "exact_match":
        reproduced = observed == expected
    else:
        reproduced = False

    if reproduced and contract.reconstructed_path:
        verdict = "partially_reproduced"
        summary = "Observed result supports a reconstructed path only."
    elif reproduced:
        verdict = "reproduced"
        summary = "Observed result satisfies the contract."
    else:
        verdict = "not_reproduced"
        summary = "Observed result does not satisfy the contract."

    return ClaimComparison(
        claim_id=contract.claim_id,
        contract_id=contract.contract_id,
        observed_metric_ids=tuple(metric.observed_metric_id for metric in metrics),
        claim_verdict_status=verdict,
        execution_readiness_status=readiness_status,
        evidence_ids=evidence_ids,
        mismatch_summary=summary,
        limitations=contract.deviation_notes,
        comparison_basis="executed_reconstructed_smoke" if contract.reconstructed_path else "executed_benchmark",
    )


def summarize_comparisons(
    *,
    paper_id: str,
    run_id: str,
    comparisons: Iterable[ClaimComparison],
    report_path: str,
    key_limitations: tuple[str, ...],
) -> Phase0VerificationSummary:
    comparison_list = tuple(comparisons)
    claim_counts = Counter(item.claim_verdict_status for item in comparison_list)
    readiness_counts = Counter(item.execution_readiness_status for item in comparison_list)

    if claim_counts.get("not_reproduced", 0) > 0:
        paper_status = "not_reproduced"
    elif claim_counts.get("blocked", 0) > 0:
        paper_status = "blocked"
    elif claim_counts.get("partially_reproduced", 0) > 0:
        paper_status = "partially_reproduced"
    else:
        paper_status = "reproduced"

    full_paper_status = "blocked" if claim_counts.get("blocked", 0) > 0 else paper_status

    return Phase0VerificationSummary(
        paper_id=paper_id,
        run_id=run_id,
        paper_level_status=paper_status,
        full_paper_claim_status=full_paper_status,
        claim_status_counts=dict(claim_counts),
        execution_readiness_summary=dict(readiness_counts),
        key_limitations=key_limitations,
        report_path=report_path,
    )

