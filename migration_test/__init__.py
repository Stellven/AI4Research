"""Migration scaffold for Solar paper claim verification."""

from .adapter import AI4ResearchPhase0ArtifactAdapter, MigrationBundle
from .comparator import compare_contract_to_observed, summarize_comparisons
from .schemas import (
    BenchmarkClaim,
    BenchmarkContract,
    ClaimComparison,
    ExecutionReadinessStatus,
    HumanReviewDecision,
    ObservedMetric,
    Phase0EvidenceMap,
    Phase0RunManifest,
    Phase0VerdictStatus,
    Phase0VerificationSummary,
)

__all__ = [
    "AI4ResearchPhase0ArtifactAdapter",
    "BenchmarkClaim",
    "BenchmarkContract",
    "ClaimComparison",
    "ExecutionReadinessStatus",
    "HumanReviewDecision",
    "MigrationBundle",
    "ObservedMetric",
    "Phase0EvidenceMap",
    "Phase0RunManifest",
    "Phase0VerdictStatus",
    "Phase0VerificationSummary",
    "compare_contract_to_observed",
    "summarize_comparisons",
]

