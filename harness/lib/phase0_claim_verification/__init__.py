"""Solar Phase 0 paper claim verification contracts and replay helpers."""

from .adapter import AI4ResearchPhase0ArtifactAdapter, MigrationBundle
from .comparator import compare_contract_to_observed, summarize_comparisons
from .schemas import (
    BenchmarkClaim,
    BenchmarkContract,
    ClaimComparison,
    HumanReviewDecision,
    ObservedMetric,
    Phase0EvidenceMap,
    Phase0RunManifest,
    Phase0VerificationSummary,
    SCHEMA_VERSION,
    to_dict,
)

__all__ = [
    "AI4ResearchPhase0ArtifactAdapter",
    "BenchmarkClaim",
    "BenchmarkContract",
    "ClaimComparison",
    "HumanReviewDecision",
    "MigrationBundle",
    "ObservedMetric",
    "Phase0EvidenceMap",
    "Phase0RunManifest",
    "Phase0VerificationSummary",
    "SCHEMA_VERSION",
    "compare_contract_to_observed",
    "summarize_comparisons",
    "to_dict",
]
