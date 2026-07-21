"""Dataclasses for professor-grade DeepResearch surveys."""

# S03 N1 extensions appended below per S02 architecture specs (markdown, frozen):
#   - source-quality-arch.md         -> SourceQualityDistribution, StuffingAlert
#   - argument-density-arch.md       -> ArgumentDensityProfile, NotApplicableEntry, DimensionIndicator
#   - contradiction-matrix-arch.md   -> ContradictionMatrix, ClaimEvidenceLink
#   - exploration-arch.md            -> EliminationRecord, ExplorationDirection, ExplorationRunResult
#   - gate-report-arch.md            -> GateReport, GateVerdict
# Existing 12 dataclasses above the to_dict() helper remain untouched (append-only).

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "solar.research.survey.v1"


@dataclass
class SurveyRun:
    run_id: str
    brief: str
    target_chars: int = 50000
    audience: str = "technical"
    domain: str = "ai"
    status: str = "planned"
    schema_version: str = SCHEMA_VERSION


@dataclass
class SurveyQuestion:
    question_id: str
    text: str
    parent_id: str | None = None
    depth: int = 0
    required_source_types: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


@dataclass
class SourceMatrix:
    section_id: str
    required_source_types: list[str]
    recommended_source_types: list[str]
    min_sources: int
    min_evidence: int
    contradiction_required: bool = True
    schema_version: str = SCHEMA_VERSION


@dataclass
class ChapterSpec:
    chapter_id: str
    title: str
    order: int
    target_chars: int
    objective: str
    schema_version: str = SCHEMA_VERSION


@dataclass
class SectionSpec:
    section_id: str
    chapter_id: str
    title: str
    order: int
    target_chars: int
    research_question: str
    required_source_types: list[str]
    min_evidence: int
    min_claims: int
    schema_version: str = SCHEMA_VERSION


@dataclass
class SurveyReportAST:
    ast_id: str
    run_id: str
    title: str
    target_chars: int
    chapters: list[ChapterSpec]
    sections: list[SectionSpec]
    status: str = "planned"
    schema_version: str = SCHEMA_VERSION


@dataclass
class EvidencePack:
    pack_id: str
    section_id: str
    evidence_ids: list[str]
    claim_ids: list[str]
    source_ids: list[str]
    source_types: list[str]
    contradiction_slots: list[str]
    status: str
    blockers: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


@dataclass
class SectionReview:
    section_id: str
    verdict: str
    unsupported_claim_rate: float
    citation_span_accuracy: float
    source_diversity_score: float
    repetition_score: float
    issues: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


@dataclass
class SectionRevisionTrace:
    section_id: str
    round_index: int
    verdict: str
    changed: bool
    issues_before: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


@dataclass
class SectionPromptPacket:
    section_id: str
    round_index: int
    writer_backend: str
    role: str
    task: str
    constraints: list[str]
    output_contract: list[str]
    artifact_paths: dict[str, str]
    schema_version: str = SCHEMA_VERSION


@dataclass
class ChapterEditorialReview:
    chapter_id: str
    verdict: str
    finalized_sections: int
    missing_sections: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


@dataclass
class SurveyScorecard:
    verdict: str
    chapter_count: int
    section_count: int
    finalized_sections: int
    blocked_sections: int
    unsupported_claim_rate: float
    citation_span_accuracy: float
    contradiction_coverage: float
    source_diversity_score: float
    taxonomy_depth_score: float
    section_repetition_rate: float
    terminology_consistency_score: float
    cross_section_conflict_count: int
    chapter_coherence_score: float
    issues: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


def to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    return value


# =============================================================================
# S03 N1 schema extensions (APPEND ONLY)
# Each dataclass below mirrors the field table from the cited S02 arch spec.
# =============================================================================


@dataclass
class StuffingAlert:
    """Per source-quality-arch.md §1 nested table (embedded in SourceQualityDistribution).

    Promoted to a top-level dataclass so it can be round-tripped and reused by
    downstream gates without re-declaring the shape.
    """

    domain: str
    count: int
    source_ids: list[str]
    confidence: str = "medium"  # high / medium / low (per FM-4)
    schema_version: str = SCHEMA_VERSION


@dataclass
class SourceQualityDistribution:
    """Per source-quality-arch.md §1 field table (7 fields + taxonomy_version)."""

    section_id: str
    source_type_counts: dict[str, int]
    primary_ratio: float
    stuffing_alerts: list[StuffingAlert]
    canonical_coverage: dict[str, bool]
    verdict: str  # pass / warning / fail
    verdict_reasons: list[str]
    taxonomy_version: str = ""  # FM-5 traceability
    schema_version: str = SCHEMA_VERSION


@dataclass
class NotApplicableEntry:
    """Per argument-density-arch.md §1 sub-type table."""

    dimension: str  # one of the 5 DimensionName values
    reason: str  # non-empty (AC2.2 from S01 O2)
    schema_version: str = SCHEMA_VERSION


@dataclass
class DimensionIndicator:
    """Per argument-density-arch.md §1 sub-type table."""

    dimension: str
    span_text: str
    confidence: str  # high / medium / low
    schema_version: str = SCHEMA_VERSION


@dataclass
class ArgumentDensityProfile:
    """Per argument-density-arch.md §1 field table (per-section density profile)."""

    section_id: str
    dimension_coverages: dict[str, str]  # DimensionName -> CoverageStatus
    density_score: float
    detected_indicators: list[DimensionIndicator]
    not_applicable_entries: list[NotApplicableEntry] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


@dataclass
class ClaimEvidenceLink:
    """Per contradiction-matrix-arch.md §2 sub-schema table."""

    evidence_id: str
    source_id: str
    source_type: str  # paper / code / official / benchmark / web-generic
    relation_strength: str  # strong / moderate / weak
    schema_version: str = SCHEMA_VERSION


@dataclass
class ContradictionMatrix:
    """Per contradiction-matrix-arch.md §2 field table (one row per unique claim)."""

    claim_id: str
    claim_text: str
    supporting_evidence: list[ClaimEvidenceLink]
    contradicting_evidence: list[ClaimEvidenceLink]
    uncertain_evidence: list[ClaimEvidenceLink]
    chapter_ids: list[str]
    synthesis_referenced: bool
    schema_version: str = SCHEMA_VERSION


@dataclass
class EliminationRecord:
    """Per exploration-arch.md §3 field table (one entry per elimination event)."""

    direction_id: str
    direction_name: str
    score: float
    kill_reason: str  # must be non-empty
    evidence_refs: list[str]  # must be non-empty
    decision_ts: str  # ISO 8601 UTC, set at elimination moment
    direction_query: str = ""
    candidate_count: int = 0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION


@dataclass
class ExplorationDirection:
    """Per exploration-arch.md §4 field table (lifecycle: active -> eliminated|selected)."""

    direction_id: str
    direction_name: str
    query: str
    status: str  # active / eliminated / selected
    source_matrix: SourceMatrix | None = None
    elimination_record: EliminationRecord | None = None
    schema_version: str = SCHEMA_VERSION


@dataclass
class ExplorationRunResult:
    """Per exploration-arch.md §6 output schema (exploration_run return type)."""

    run_id: str
    selected_directions: list[ExplorationDirection]
    eliminated_directions: list[ExplorationDirection]
    elimination_log_path: str
    source_matrix_consumed: SourceMatrix | None = None
    schema_version: str = SCHEMA_VERSION


@dataclass
class GateVerdict:
    """Per gate-report-arch.md §2 common contract (one per gate plugin output)."""

    gate_id: str
    verdict: str  # pass / warn / fail / not_applicable
    evidence_refs: list[str]
    report_section: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION


@dataclass
class GateReport:
    """Per gate-report-arch.md §2 top-level field table (aggregation artifact).

    `scorecard_ref` references the frozen SurveyScorecard output via path +
    verdict snapshot rather than duplicating its fields (no rewrite of
    evaluate_survey signature, per S02 gate-report-arch §8).
    """

    report_id: str
    run_metadata: dict[str, Any]
    gate_verdicts: dict[str, GateVerdict]
    artifact_paths: dict[str, str]
    scorecard_ref: dict[str, Any]
    schema_version: str = SCHEMA_VERSION
