"""Solar Phase 0 claim-verification contracts.

These dataclasses mirror the schema names called out in
`AI4Research-B/migration/adapt_to_solar.md`. They preserve the Phase 0
separation between evidence-backed claim verdicts and operational execution
readiness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SCHEMA_VERSION = "solar.phase0.claim_verification.v0"


Phase0VerdictStatus = str
ExecutionReadinessStatus = str


PHASE0_VERDICT_STATUSES = frozenset(
    {
        "reproduced",
        "partially_reproduced",
        "not_reproduced",
        "not_testable",
        "failed_to_run",
        "blocked",
        "out_of_scope",
    }
)

EXECUTION_READINESS_STATUSES = frozenset(
    {
        "ready",
        "partially_ready",
        "not_ready",
        "blocked",
        "unknown",
    }
)

HUMAN_REVIEW_DECISIONS = frozenset(
    {
        "approved",
        "rejected",
        "needs_clarification",
        "pending",
    }
)

EVIDENCE_BACKED_VERDICTS = frozenset(
    {
        "reproduced",
        "partially_reproduced",
        "not_reproduced",
        "failed_to_run",
        "blocked",
        "not_testable",
    }
)

EXECUTED_EVIDENCE_BASES = frozenset(
    {
        "executed_benchmark",
        "executed_reconstructed_smoke",
        "artifact_inspection",
    }
)


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_allowed(value: str, allowed: frozenset[str], field_name: str) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name}={value!r} must be one of {sorted(allowed)}")


def _tuple(value: tuple[str, ...] | list[str], field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{field_name} must be a list or tuple")
    return tuple(str(item) for item in value)


def _require_non_empty_tuple(value: tuple[str, ...] | list[str], field_name: str) -> None:
    items = _tuple(value, field_name)
    if not items or any(not item.strip() for item in items):
        raise ValueError(f"{field_name} must contain at least one non-empty item")


def to_dict(instance: Any) -> dict[str, Any]:
    payload = asdict(instance)
    for key, value in list(payload.items()):
        if isinstance(value, tuple):
            payload[key] = list(value)
    return payload


@dataclass(frozen=True)
class BenchmarkClaim:
    claim_id: str
    paper_location: str
    metric_name: str
    dataset: str
    split: str
    config: str
    expected_value: float | str | None
    expected_direction_or_tolerance: str
    extraction_evidence_ids: tuple[str, ...]
    claim_text: str = ""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.claim_id, "BenchmarkClaim.claim_id")
        _require_non_empty(self.paper_location, "BenchmarkClaim.paper_location")
        _require_non_empty(self.metric_name, "BenchmarkClaim.metric_name")
        _require_non_empty(self.dataset, "BenchmarkClaim.dataset")
        _require_non_empty(self.split, "BenchmarkClaim.split")
        _require_non_empty(self.config, "BenchmarkClaim.config")
        _require_non_empty(self.expected_direction_or_tolerance, "BenchmarkClaim.expected_direction_or_tolerance")
        _require_non_empty_tuple(self.extraction_evidence_ids, "BenchmarkClaim.extraction_evidence_ids")


@dataclass(frozen=True)
class BenchmarkContract:
    contract_id: str
    claim_id: str
    runnable_target: str
    metric_definition: str
    aggregation_rule: str
    tolerance: float | None
    comparison_logic: str
    required_artifacts: tuple[str, ...]
    human_approval_state: str = "pending"
    reconstructed_path: bool = False
    deviation_notes: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.contract_id, "BenchmarkContract.contract_id")
        _require_non_empty(self.claim_id, "BenchmarkContract.claim_id")
        _require_non_empty(self.runnable_target, "BenchmarkContract.runnable_target")
        _require_non_empty(self.metric_definition, "BenchmarkContract.metric_definition")
        _require_non_empty(self.aggregation_rule, "BenchmarkContract.aggregation_rule")
        _require_non_empty(self.comparison_logic, "BenchmarkContract.comparison_logic")
        _require_non_empty_tuple(self.required_artifacts, "BenchmarkContract.required_artifacts")
        _require_allowed(self.human_approval_state, HUMAN_REVIEW_DECISIONS, "BenchmarkContract.human_approval_state")
        if self.tolerance is not None and self.tolerance < 0:
            raise ValueError("BenchmarkContract.tolerance must be non-negative")


@dataclass(frozen=True)
class ObservedMetric:
    observed_metric_id: str
    run_id: str
    metric_name: str
    observed_value: float | str | None
    dataset: str
    split: str
    config: str
    source_artifact_ids: tuple[str, ...]
    parser_confidence: float
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.observed_metric_id, "ObservedMetric.observed_metric_id")
        _require_non_empty(self.run_id, "ObservedMetric.run_id")
        _require_non_empty(self.metric_name, "ObservedMetric.metric_name")
        _require_non_empty(self.dataset, "ObservedMetric.dataset")
        _require_non_empty(self.split, "ObservedMetric.split")
        _require_non_empty(self.config, "ObservedMetric.config")
        _require_non_empty_tuple(self.source_artifact_ids, "ObservedMetric.source_artifact_ids")
        if not 0 <= self.parser_confidence <= 1:
            raise ValueError("ObservedMetric.parser_confidence must be between 0 and 1")


@dataclass(frozen=True)
class ClaimComparison:
    claim_id: str
    contract_id: str
    observed_metric_ids: tuple[str, ...]
    claim_verdict_status: Phase0VerdictStatus
    execution_readiness_status: ExecutionReadinessStatus
    evidence_ids: tuple[str, ...]
    mismatch_summary: str
    limitations: tuple[str, ...]
    comparison_basis: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.claim_id, "ClaimComparison.claim_id")
        _require_non_empty(self.contract_id, "ClaimComparison.contract_id")
        _require_allowed(self.claim_verdict_status, PHASE0_VERDICT_STATUSES, "ClaimComparison.claim_verdict_status")
        _require_allowed(
            self.execution_readiness_status,
            EXECUTION_READINESS_STATUSES,
            "ClaimComparison.execution_readiness_status",
        )
        _require_non_empty(self.comparison_basis, "ClaimComparison.comparison_basis")
        if self.claim_verdict_status in EVIDENCE_BACKED_VERDICTS:
            _require_non_empty_tuple(self.evidence_ids, "ClaimComparison.evidence_ids")
        if self.claim_verdict_status in {"reproduced", "partially_reproduced", "not_reproduced"}:
            if not self.observed_metric_ids:
                raise ValueError(
                    "reproduced/partially_reproduced/not_reproduced verdicts require observed metrics"
                )
            if self.comparison_basis not in EXECUTED_EVIDENCE_BASES:
                raise ValueError(
                    "execution readiness or planning evidence cannot upgrade a claim verdict"
                )


@dataclass(frozen=True)
class HumanReviewDecision:
    review_id: str
    target_artifact_id: str
    target_step: str
    decision: str
    reviewer_id: str
    reviewed_at: str
    rationale: str
    required_changes: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.review_id, "HumanReviewDecision.review_id")
        _require_non_empty(self.target_artifact_id, "HumanReviewDecision.target_artifact_id")
        _require_non_empty(self.target_step, "HumanReviewDecision.target_step")
        _require_allowed(self.decision, HUMAN_REVIEW_DECISIONS, "HumanReviewDecision.decision")
        _require_non_empty(self.reviewer_id, "HumanReviewDecision.reviewer_id")
        _require_non_empty(self.reviewed_at, "HumanReviewDecision.reviewed_at")


@dataclass(frozen=True)
class Phase0RunManifest:
    run_id: str
    benchmark_run_result_path: str
    stdout_path: str | None
    stderr_path: str | None
    artifact_paths: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    deviation_notes: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.run_id, "Phase0RunManifest.run_id")
        _require_non_empty(self.benchmark_run_result_path, "Phase0RunManifest.benchmark_run_result_path")
        _require_non_empty_tuple(self.artifact_paths, "Phase0RunManifest.artifact_paths")
        _require_non_empty_tuple(self.evidence_ids, "Phase0RunManifest.evidence_ids")


@dataclass(frozen=True)
class Phase0EvidenceMap:
    claim_id: str
    contract_id: str
    run_id: str
    observed_metric_ids: tuple[str, ...]
    paper_evidence_ids: tuple[str, ...]
    run_evidence_ids: tuple[str, ...]
    limitation_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.claim_id, "Phase0EvidenceMap.claim_id")
        _require_non_empty(self.contract_id, "Phase0EvidenceMap.contract_id")
        _require_non_empty(self.run_id, "Phase0EvidenceMap.run_id")
        _require_non_empty_tuple(self.paper_evidence_ids, "Phase0EvidenceMap.paper_evidence_ids")
        _require_non_empty_tuple(self.run_evidence_ids, "Phase0EvidenceMap.run_evidence_ids")


@dataclass(frozen=True)
class Phase0VerificationSummary:
    paper_id: str
    run_id: str
    paper_level_status: Phase0VerdictStatus
    full_paper_claim_status: Phase0VerdictStatus
    claim_status_counts: dict[str, int]
    execution_readiness_summary: dict[str, int]
    key_limitations: tuple[str, ...]
    report_path: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.paper_id, "Phase0VerificationSummary.paper_id")
        _require_non_empty(self.run_id, "Phase0VerificationSummary.run_id")
        _require_allowed(self.paper_level_status, PHASE0_VERDICT_STATUSES, "Phase0VerificationSummary.paper_level_status")
        _require_allowed(
            self.full_paper_claim_status,
            PHASE0_VERDICT_STATUSES,
            "Phase0VerificationSummary.full_paper_claim_status",
        )
        for status, count in self.claim_status_counts.items():
            _require_allowed(status, PHASE0_VERDICT_STATUSES, "Phase0VerificationSummary.claim_status_counts key")
            if count < 0:
                raise ValueError("Phase0VerificationSummary claim status counts must be non-negative")
        for status, count in self.execution_readiness_summary.items():
            _require_allowed(status, EXECUTION_READINESS_STATUSES, "Phase0VerificationSummary.execution_readiness_summary key")
            if count < 0:
                raise ValueError("Phase0VerificationSummary readiness counts must be non-negative")
        _require_non_empty_tuple(self.key_limitations, "Phase0VerificationSummary.key_limitations")
        _require_non_empty(self.report_path, "Phase0VerificationSummary.report_path")
