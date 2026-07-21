"""DeepResearch data model schemas (8 core + 5 nested types).

Schema Version: solar.deepresearch.schemas.v1
Spec: sprint-20260513-solar-deepresearch-product-line-s02-architecture
      / deepresearch.schemas.md
Author: N1 builder (S03 core-runtime)

All field names and types match S02 schemas.md exactly. Invariants documented
in the spec are enforced via __post_init__ where they can be checked from a
single record's state (cross-record FK checks live in storage.py / evidence/
ledger.py).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Enum-as-frozenset constants (validate against these at __post_init__ time)
# ---------------------------------------------------------------------------

CONNECTOR_TYPES = frozenset({
    "brave", "exa", "tavily", "jina",
    "openalex", "semantic_scholar", "arxiv", "crossref",
    "papers_with_code", "github", "huggingface",
    "lens", "uspto", "ietf", "w3c", "nist", "ieee", "iso",
    "internal_mirage", "internal_qmd", "internal_obsidian", "internal_solar_db",
    "file", "html",
})

SOURCE_TIERS = frozenset({"public_web", "academic", "engineering", "internal"})

CONNECTOR_STATUSES = frozenset({"active", "disabled", "degraded", "error"})

CONNECTOR_CAPABILITIES = frozenset({"search", "fetch", "extract", "normalize", "cite"})

FETCH_STATUSES = frozenset({"pending", "fetched", "failed", "skipped"})

EVIDENCE_SOURCE_TYPES = frozenset({
    "document", "internal_mirage", "internal_qmd",
    "internal_obsidian", "internal_solar_db",
})

EVIDENCE_TYPES = frozenset({
    "direct_quote", "paraphrase", "statistic", "definition",
    "finding", "methodology", "result",
})

SUPPORT_DIRECTIONS = frozenset({"supporting", "contradicting", "neutral", "contextual"})

CLAIM_TYPES = frozenset({
    "factual", "methodological", "definitional", "comparative",
    "predictive", "hedging", "transition",
})

SUPPORT_RATINGS = frozenset({"strong", "moderate", "weak", "unsupported", "unrated"})

CLAIM_SOURCE_METHODS = frozenset({
    "extracted_from_evidence", "synthesized_from_multiple", "author_assertion",
})

LINK_TYPES = frozenset({"supports", "contradicts", "contextualizes", "qualifies"})

VERIFICATION_RESULTS = frozenset({"match", "partial_match", "mismatch"})

REPORT_STATUSES = frozenset({
    "drafting", "section_writing", "fact_checking", "compiling",
    "consistency_check", "final_export", "completed", "failed",
})

CHAPTER_STATUSES = frozenset({
    "planned", "writing", "fact_checking", "compiled", "failed",
})

SECTION_STATUSES = frozenset({
    "planned", "spec_defined", "evidence_packed", "writing",
    "draft_complete", "fact_checked", "final", "failed",
})

# Section budget enforcement (Stop Rule: no single-node 100k report)
SECTION_MAX_CHARS_CEILING = 4000
SECTION_MIN_CHARS_FLOOR = 1500


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1. SourceConnector
# ---------------------------------------------------------------------------


@dataclass
class SourceConnector:
    connector_id: str
    connector_type: str
    source_tier: str
    display_name: str
    base_url: Optional[str] = None
    auth_config: Optional[dict] = None
    rate_limit_rpm: int = 60
    depth_tier: int = 2
    status: str = "active"
    last_health_check: Optional[str] = None
    capabilities: list[str] = field(default_factory=lambda: ["search"])
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        if self.connector_type not in CONNECTOR_TYPES:
            raise ValueError(
                f"SourceConnector.connector_type {self.connector_type!r} "
                f"not in known connector type enum"
            )
        if self.source_tier not in SOURCE_TIERS:
            raise ValueError(
                f"SourceConnector.source_tier {self.source_tier!r} "
                f"not in {sorted(SOURCE_TIERS)}"
            )
        if not 1 <= self.depth_tier <= 4:
            raise ValueError(
                f"SourceConnector.depth_tier must be in [1, 4], got {self.depth_tier}"
            )
        if self.status not in CONNECTOR_STATUSES:
            raise ValueError(
                f"SourceConnector.status {self.status!r} not in {sorted(CONNECTOR_STATUSES)}"
            )
        if not self.capabilities:
            raise ValueError("SourceConnector.capabilities must be non-empty")
        bad_caps = set(self.capabilities) - CONNECTOR_CAPABILITIES
        if bad_caps:
            raise ValueError(
                f"SourceConnector.capabilities has unknown values: {sorted(bad_caps)}"
            )
        if self.auth_config is not None:
            t = self.auth_config.get("type")
            if t not in {"env_var", "oauth", "api_key_file", "none"}:
                raise ValueError(
                    f"SourceConnector.auth_config.type {t!r} invalid"
                )


# ---------------------------------------------------------------------------
# 2. SourceHit
# ---------------------------------------------------------------------------


@dataclass
class SourceHit:
    hit_id: str
    connector_id: str
    query: str
    rank: int
    title: str
    url: Optional[str] = None
    snippet: Optional[str] = None
    metadata: Optional[dict] = None
    fetch_status: str = "pending"
    fetch_error: Optional[str] = None
    created_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        if self.rank < 0:
            raise ValueError(f"SourceHit.rank must be >= 0, got {self.rank}")
        if not self.query:
            raise ValueError("SourceHit.query must be non-empty")
        if len(self.query) > 500:
            raise ValueError(
                f"SourceHit.query must be <= 500 chars, got {len(self.query)}"
            )
        if self.fetch_status not in FETCH_STATUSES:
            raise ValueError(
                f"SourceHit.fetch_status {self.fetch_status!r} "
                f"not in {sorted(FETCH_STATUSES)}"
            )
        if self.fetch_status == "failed" and not self.fetch_error:
            raise ValueError(
                "SourceHit.fetch_error must be non-null when fetch_status='failed'"
            )


# ---------------------------------------------------------------------------
# 3. SourceDocument
# ---------------------------------------------------------------------------


@dataclass
class SourceDocument:
    doc_id: str
    connector_id: str
    title: str
    raw_text: str
    content_hash: str
    content_length: int
    source_hit_id: Optional[str] = None
    source_url: Optional[str] = None
    authors: list[str] = field(default_factory=list)
    published_date: Optional[str] = None
    language: str = "unknown"
    authority_score: Optional[float] = None
    fetch_timestamp: str = field(default_factory=_utc_now_iso)
    metadata: Optional[dict] = None
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.raw_text:
            raise ValueError("SourceDocument.raw_text must be non-empty")
        if self.content_length != len(self.raw_text):
            raise ValueError(
                f"SourceDocument.content_length ({self.content_length}) "
                f"!= len(raw_text) ({len(self.raw_text)})"
            )
        # Content hash integrity — local invariant, cross-checked at storage.
        from . import hashing as _hashing  # local import to avoid cycle
        expected = _hashing.content_hash(self.raw_text)
        if self.content_hash != expected:
            raise ValueError(
                f"SourceDocument.content_hash mismatch: "
                f"declared={self.content_hash[:12]}..., computed={expected[:12]}..."
            )
        if self.authority_score is not None and not 0.0 <= self.authority_score <= 1.0:
            raise ValueError(
                f"SourceDocument.authority_score must be in [0,1], "
                f"got {self.authority_score}"
            )


# ---------------------------------------------------------------------------
# 4. EvidenceItem
# ---------------------------------------------------------------------------


@dataclass
class EvidenceItem:
    evidence_id: str
    source_id: str
    source_type: str
    content_hash: str
    span_start: int
    span_end: int
    span_text: str
    section_path: Optional[str] = None
    evidence_type: str = "direct_quote"
    relevance_score: float = 0.5
    support_direction: str = "supporting"
    created_at: str = field(default_factory=_utc_now_iso)
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError(
                "EvidenceItem.source_id must be non-null (provenance chain)"
            )
        if self.source_type not in EVIDENCE_SOURCE_TYPES:
            raise ValueError(
                f"EvidenceItem.source_type {self.source_type!r} "
                f"not in {sorted(EVIDENCE_SOURCE_TYPES)}"
            )
        if self.span_start < 0:
            raise ValueError(
                f"EvidenceItem.span_start must be >= 0, got {self.span_start}"
            )
        if self.span_end <= self.span_start:
            raise ValueError(
                f"EvidenceItem.span_end ({self.span_end}) must be > span_start "
                f"({self.span_start})"
            )
        if not self.span_text:
            raise ValueError("EvidenceItem.span_text must be non-empty")
        from . import hashing as _hashing
        expected = _hashing.content_hash(self.span_text)
        if self.content_hash != expected:
            raise ValueError(
                f"EvidenceItem.content_hash mismatch (declared vs sha256(span_text)): "
                f"declared={self.content_hash[:12]}..., computed={expected[:12]}..."
            )
        if self.evidence_type not in EVIDENCE_TYPES:
            raise ValueError(
                f"EvidenceItem.evidence_type {self.evidence_type!r} "
                f"not in {sorted(EVIDENCE_TYPES)}"
            )
        if self.support_direction not in SUPPORT_DIRECTIONS:
            raise ValueError(
                f"EvidenceItem.support_direction {self.support_direction!r} "
                f"not in {sorted(SUPPORT_DIRECTIONS)}"
            )
        if not 0.0 <= self.relevance_score <= 1.0:
            raise ValueError(
                f"EvidenceItem.relevance_score must be in [0,1], "
                f"got {self.relevance_score}"
            )


# ---------------------------------------------------------------------------
# 5. Claim
# ---------------------------------------------------------------------------


@dataclass
class Claim:
    claim_id: str
    claim_text: str
    section_path: str
    source_method: str
    is_key: bool = True
    claim_type: str = "factual"
    support_rating: str = "unrated"
    evidence_ids: list[str] = field(default_factory=list)
    contradiction_ids: list[str] = field(default_factory=list)
    confidence: Optional[float] = None
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.claim_text:
            raise ValueError("Claim.claim_text must be non-empty")
        if len(self.claim_text) > 500:
            raise ValueError(
                f"Claim.claim_text must be <= 500 chars, got {len(self.claim_text)}"
            )
        if self.claim_type not in CLAIM_TYPES:
            raise ValueError(
                f"Claim.claim_type {self.claim_type!r} not in {sorted(CLAIM_TYPES)}"
            )
        if self.support_rating not in SUPPORT_RATINGS:
            raise ValueError(
                f"Claim.support_rating {self.support_rating!r} "
                f"not in {sorted(SUPPORT_RATINGS)}"
            )
        if self.source_method not in CLAIM_SOURCE_METHODS:
            raise ValueError(
                f"Claim.source_method {self.source_method!r} "
                f"not in {sorted(CLAIM_SOURCE_METHODS)}"
            )
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Claim.confidence must be in [0,1], got {self.confidence}"
            )


# ---------------------------------------------------------------------------
# 6. ClaimEvidenceLink
# ---------------------------------------------------------------------------


@dataclass
class ClaimEvidenceLink:
    link_id: str
    claim_id: str
    evidence_id: str
    link_type: str = "supports"
    relevance_score: float = 0.5
    is_primary: bool = False
    created_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        if self.link_type not in LINK_TYPES:
            raise ValueError(
                f"ClaimEvidenceLink.link_type {self.link_type!r} "
                f"not in {sorted(LINK_TYPES)}"
            )
        if not 0.0 <= self.relevance_score <= 1.0:
            raise ValueError(
                f"ClaimEvidenceLink.relevance_score must be in [0,1], "
                f"got {self.relevance_score}"
            )


# ---------------------------------------------------------------------------
# 7. CitationSpan
# ---------------------------------------------------------------------------


@dataclass
class CitationSpan:
    citation_id: str
    evidence_id: str
    claim_id: str
    section_path: str
    span_start: int
    span_end: int
    span_text: str
    marker_text: str
    marker_position: int
    verified: bool = False
    verification_result: Optional[str] = None
    created_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        import re
        if not self.span_text:
            raise ValueError("CitationSpan.span_text must be non-empty")
        if self.span_start < 0:
            raise ValueError(
                f"CitationSpan.span_start must be >= 0, got {self.span_start}"
            )
        if self.span_end <= self.span_start:
            raise ValueError(
                f"CitationSpan.span_end ({self.span_end}) must be > span_start "
                f"({self.span_start})"
            )
        if not re.fullmatch(r"\[cite:[a-zA-Z0-9_]+\]", self.marker_text):
            raise ValueError(
                f"CitationSpan.marker_text must match [cite:...]; "
                f"got {self.marker_text!r}"
            )
        if self.marker_position < 0:
            raise ValueError(
                f"CitationSpan.marker_position must be >= 0, got {self.marker_position}"
            )
        if self.verified and self.verification_result is None:
            raise ValueError(
                "CitationSpan.verification_result must be set when verified=True"
            )
        if (
            self.verification_result is not None
            and self.verification_result not in VERIFICATION_RESULTS
        ):
            raise ValueError(
                f"CitationSpan.verification_result {self.verification_result!r} "
                f"not in {sorted(VERIFICATION_RESULTS)}"
            )


# ---------------------------------------------------------------------------
# 8. ReportAST (+ nested Chapter, Section, Bibliography, BibEntry, QualityReport)
# ---------------------------------------------------------------------------


@dataclass
class Section:
    section_id: str
    title: str
    order: int
    target_chars: int = 3000
    min_chars: int = 1500
    max_chars: int = 4000
    evidence_budget: int = 40
    claim_budget: int = 30
    artifacts: Optional[dict] = None
    status: str = "planned"

    def __post_init__(self) -> None:
        if self.order < 1:
            raise ValueError(f"Section.order must be >= 1, got {self.order}")
        if self.max_chars > SECTION_MAX_CHARS_CEILING:
            raise ValueError(
                f"Section.max_chars ({self.max_chars}) exceeds ceiling "
                f"{SECTION_MAX_CHARS_CEILING} (Stop Rule: no single-node 100k report)"
            )
        if self.min_chars < SECTION_MIN_CHARS_FLOOR:
            raise ValueError(
                f"Section.min_chars ({self.min_chars}) below floor "
                f"{SECTION_MIN_CHARS_FLOOR}"
            )
        if self.status not in SECTION_STATUSES:
            raise ValueError(
                f"Section.status {self.status!r} not in {sorted(SECTION_STATUSES)}"
            )


@dataclass
class Chapter:
    chapter_id: str
    title: str
    order: int
    sections: list[Section] = field(default_factory=list)
    status: str = "planned"

    def __post_init__(self) -> None:
        if self.order < 1:
            raise ValueError(f"Chapter.order must be >= 1, got {self.order}")
        if self.status not in CHAPTER_STATUSES:
            raise ValueError(
                f"Chapter.status {self.status!r} not in {sorted(CHAPTER_STATUSES)}"
            )


@dataclass
class BibEntry:
    source_id: str
    title: str
    connector_type: str
    content_hash: str
    authors: list[str] = field(default_factory=list)
    year: Optional[str] = None
    url: Optional[str] = None
    authority_score: Optional[float] = None

    def __post_init__(self) -> None:
        if self.authority_score is not None and not 0.0 <= self.authority_score <= 1.0:
            raise ValueError(
                f"BibEntry.authority_score must be in [0,1], "
                f"got {self.authority_score}"
            )


@dataclass
class Bibliography:
    entries: list[BibEntry] = field(default_factory=list)


@dataclass
class QualityReport:
    unsupported_claim_rate: float
    citation_span_accuracy: float
    source_authority_score: float
    freshness_score: float
    contradiction_coverage: float
    section_repetition_rate: float
    cross_section_consistency: float
    overall_pass: bool = False


@dataclass
class ReportAST:
    ast_id: str
    sprint_id: str
    title: str
    target_chars: int
    target_sections: int
    target_chapters: int
    depth_tier: int = 2
    status: str = "drafting"
    chapters: list[Chapter] = field(default_factory=list)
    bibliography: Optional[Bibliography] = None
    quality_report: Optional[QualityReport] = None
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not 1 <= self.depth_tier <= 4:
            raise ValueError(
                f"ReportAST.depth_tier must be in [1, 4], got {self.depth_tier}"
            )
        if self.status not in REPORT_STATUSES:
            raise ValueError(
                f"ReportAST.status {self.status!r} not in {sorted(REPORT_STATUSES)}"
            )
        if self.chapters:
            # target_chapters must equal len(chapters)
            if self.target_chapters != len(self.chapters):
                raise ValueError(
                    f"ReportAST.target_chapters ({self.target_chapters}) "
                    f"!= len(chapters) ({len(self.chapters)})"
                )
            # target_sections must equal sum(len(c.sections))
            total_sections = sum(len(c.sections) for c in self.chapters)
            if self.target_sections != total_sections:
                raise ValueError(
                    f"ReportAST.target_sections ({self.target_sections}) "
                    f"!= sum(len(chapter.sections)) ({total_sections})"
                )
            # Chapter order uniqueness + contiguity from 1
            orders = sorted(c.order for c in self.chapters)
            if orders != list(range(1, len(orders) + 1)):
                raise ValueError(
                    f"ReportAST chapter orders must be unique+contiguous from 1, "
                    f"got {orders}"
                )
            for ch in self.chapters:
                sec_orders = sorted(s.order for s in ch.sections)
                if sec_orders and sec_orders != list(range(1, len(sec_orders) + 1)):
                    raise ValueError(
                        f"Chapter {ch.chapter_id} section orders must be "
                        f"unique+contiguous from 1, got {sec_orders}"
                    )



# ---------------------------------------------------------------------------
# FigureSpec
# ---------------------------------------------------------------------------


@dataclass
class FigureSpec:
    figure_id: str
    title: str
    figure_type: str  # "architecture_diagram" or "timeline"
    grounding_ids: list[str] = field(default_factory=list)
    spec_data: dict[str, Any] = field(default_factory=dict)
    renderer: str = "mermaid"
    caption: Optional[str] = None
    created_at: str = field(default_factory=_utc_now_iso)
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.figure_id:
            raise ValueError("FigureSpec.figure_id must be non-empty")
        if not self.title:
            raise ValueError("FigureSpec.title must be non-empty")
        if self.figure_type not in {"architecture_diagram", "timeline"}:
            raise ValueError(f"FigureSpec.figure_type {self.figure_type!r} invalid")
        if not isinstance(self.grounding_ids, list):
            raise ValueError("FigureSpec.grounding_ids must be a list of strings")


# ---------------------------------------------------------------------------
# Public registry
# ---------------------------------------------------------------------------

CORE_MODELS: tuple[type, ...] = (
    SourceConnector,
    SourceHit,
    SourceDocument,
    EvidenceItem,
    Claim,
    ClaimEvidenceLink,
    CitationSpan,
    ReportAST,
)

NESTED_MODELS: tuple[type, ...] = (
    Chapter,
    Section,
    Bibliography,
    BibEntry,
    QualityReport,
)


# ---------------------------------------------------------------------------
# Future Platform Seam Models
# ---------------------------------------------------------------------------


@dataclass
class LivingReport:
    report_id: str
    topic: str
    active_ast_id: str
    watch_schedules: list[dict[str, Any]] = field(default_factory=list)
    update_policy: dict[str, Any] = field(default_factory=lambda: {"merge_strategy": "human_review", "auto_promote": False})
    history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.report_id:
            raise ValueError("LivingReport.report_id must be non-empty")
        if not self.topic:
            raise ValueError("LivingReport.topic must be non-empty")
        if not self.active_ast_id:
            raise ValueError("LivingReport.active_ast_id must be non-empty")
        for ws in self.watch_schedules:
            st = ws.get("schedule_type")
            if st not in {"cron", "trigger", "event"}:
                raise ValueError(f"LivingReport schedule_type {st!r} invalid")
            if not ws.get("expression"):
                raise ValueError("LivingReport schedule expression must be non-empty")
        ms = self.update_policy.get("merge_strategy")
        if ms not in {"strict_overwrite", "differential_append", "human_review"}:
            raise ValueError(f"LivingReport merge_strategy {ms!r} invalid")


@dataclass
class ResearchLab:
    lab_id: str
    name: str
    status: str = "active"
    runner_slots: list[str] = field(default_factory=list)
    active_experiments: list[str] = field(default_factory=list)
    allowed_models: list[str] = field(default_factory=list)
    telemetry_config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.lab_id:
            raise ValueError("ResearchLab.lab_id must be non-empty")
        if not self.name:
            raise ValueError("ResearchLab.name must be non-empty")
        if self.status not in {"active", "paused", "maintenance", "depleted"}:
            raise ValueError(f"ResearchLab.status {self.status!r} invalid")
        ll = self.telemetry_config.get("log_level")
        if ll is not None and ll not in {"debug", "info", "warning", "error"}:
            raise ValueError(f"ResearchLab log_level {ll!r} invalid")


@dataclass
class ResearchMemory:
    memory_id: str
    scope: str = "global"
    storage_backend: str = "sqlite"
    read_only: bool = False
    memory_types: list[str] = field(default_factory=list)
    indexing_status: str = "ready"
    embedding_model: Optional[str] = None
    stats: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.memory_id:
            raise ValueError("ResearchMemory.memory_id must be non-empty")
        if self.scope not in {"global", "run-local", "operator-local", "tenant-local"}:
            raise ValueError(f"ResearchMemory.scope {self.scope!r} invalid")
        if self.storage_backend not in {"sqlite", "vector-db", "file-system", "obsidian"}:
            raise ValueError(f"ResearchMemory.storage_backend {self.storage_backend!r} invalid")
        if self.indexing_status not in {"ready", "indexing", "stale", "error"}:
            raise ValueError(f"ResearchMemory.indexing_status {self.indexing_status!r} invalid")
        for mt in self.memory_types:
            if mt not in {"episodic", "semantic", "facts", "feedback"}:
                raise ValueError(f"ResearchMemory memory_type {mt!r} invalid")


@dataclass
class AIInfraPack:
    pack_id: str
    pack_name: str
    version: str
    status: str = "stable"
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    operator_templates: list[dict[str, Any]] = field(default_factory=list)
    common_policies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        import re
        if not self.pack_id:
            raise ValueError("AIInfraPack.pack_id must be non-empty")
        if not self.pack_name:
            raise ValueError("AIInfraPack.pack_name must be non-empty")
        if self.status not in {"stable", "draft", "deprecated"}:
            raise ValueError(f"AIInfraPack.status {self.status!r} invalid")
        if not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$", self.version):
            raise ValueError(f"AIInfraPack.version {self.version!r} invalid (must match semver)")
        for ms in self.mcp_servers:
            if not ms.get("name"):
                raise ValueError("AIInfraPack mcp_server name must be non-empty")
            et = ms.get("endpoint_type")
            if et not in {"mcp_stdio", "mcp_sse", "mcp_http"}:
                raise ValueError(f"AIInfraPack mcp_server endpoint_type {et!r} invalid")
            mss = ms.get("status")
            if mss is not None and mss not in {"active", "disabled", "degraded"}:
                raise ValueError(f"AIInfraPack mcp_server status {mss!r} invalid")
        for ot in self.operator_templates:
            if not ot.get("role"):
                raise ValueError("AIInfraPack operator_template role must be non-empty")
            if not ot.get("vendor"):
                raise ValueError("AIInfraPack operator_template vendor must be non-empty")


@dataclass
class ArtifactDelta:
    delta_id: str
    target_artifact_id: str
    target_artifact_type: str
    changes: list[dict[str, Any]] = field(default_factory=list)
    base_version: Optional[str] = None
    new_version: Optional[str] = None
    timestamp: Optional[str] = None
    author: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.delta_id:
            raise ValueError("ArtifactDelta.delta_id must be non-empty")
        if not self.target_artifact_id:
            raise ValueError("ArtifactDelta.target_artifact_id must be non-empty")
        if self.target_artifact_type not in {"living_report", "research_lab", "research_memory", "ai_infra_pack"}:
            raise ValueError(f"ArtifactDelta.target_artifact_type {self.target_artifact_type!r} invalid")
        for ch in self.changes:
            op = ch.get("op")
            if op not in {"add", "replace", "remove", "append"}:
                raise ValueError(f"ArtifactDelta change op {op!r} invalid")
            if not ch.get("path"):
                raise ValueError("ArtifactDelta change path must be non-empty")


FUTURE_MODELS: tuple[type, ...] = (
    LivingReport,
    ResearchLab,
    ResearchMemory,
    AIInfraPack,
    ArtifactDelta,
)


def model_field_names(model_cls: type) -> tuple[str, ...]:
    """Return the dataclass field names of a model class.

    Useful for introspection in tests and storage layer schema verification.
    """
    return tuple(f.name for f in fields(model_cls))


def to_dict(record: Any) -> dict:
    """Return a JSON-serializable dict for any dataclass record in this module."""
    return asdict(record)
