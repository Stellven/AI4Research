"""JSON-first schema objects for AI Influence YouTube report runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class TranscriptGrade(StrEnum):
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class RunState(StrEnum):
    CREATED = "created"
    GRADED = "graded"
    GROUPED = "grouped"
    PLANNED = "planned"
    CHAPTERED = "chaptered"
    SYNTHESIZED = "synthesized"
    VALIDATED = "validated"
    ARCHIVED = "archived"
    RUN_REJECTED_T3_ONLY = "run_rejected_t3_only"
    RUN_REJECTED_VALIDATOR = "run_rejected_validator"
    RUN_REJECTED_MODEL_UNREACHABLE = "run_rejected_model_unreachable"
    RUN_REJECTED_UPSTREAM_UNREACHABLE = "run_rejected_upstream_unreachable"
    RUN_REJECTED_HIERARCHY = "run_rejected_hierarchy"
    RUN_REJECTED_ARCHIVE_IO = "run_rejected_archive_io"
    RUN_REJECTED_UPSTREAM_DRIFT = "run_rejected_upstream_drift"


def to_json_dict(value: Any) -> dict[str, Any]:
    payload = asdict(value)
    return {
        key: (item.value if isinstance(item, StrEnum) else item)
        for key, item in payload.items()
    }


@dataclass(frozen=True)
class GateDecision:
    video_id: str
    grade: TranscriptGrade
    entity_recall: float
    wer: float
    segment_density: float
    evidence_notes: list[str]
    gated_at: str
    schema_version: str = "gate_decision.v1"

    def to_dict(self) -> dict[str, Any]:
        return to_json_dict(self)


@dataclass(frozen=True)
class T3Exclusions:
    run_id: str
    excluded_video_ids: list[str]
    per_video_reason: dict[str, str]
    generated_at: str
    schema_version: str = "t3_exclusions.v1"

    def to_dict(self) -> dict[str, Any]:
        return to_json_dict(self)


@dataclass
class RunRecord:
    run_id: str
    state: RunState
    phase_artifacts: dict[str, str] = field(default_factory=dict)
    step_log: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = "run_record.v1"

    def to_dict(self) -> dict[str, Any]:
        payload = to_json_dict(self)
        payload["state"] = self.state.value
        return payload


@dataclass(frozen=True)
class SourceMapping:
    channel: str
    title: str
    published_at: str
    trust_level: str
    cited_segment_snippet: str
    schema_version: str = "source_mapping.v1"

    def to_dict(self) -> dict[str, Any]:
        return to_json_dict(self)


@dataclass(frozen=True)
class ModelCallLedgerRow:
    call_id: str
    stage: str
    cost_estimate_usd: float
    sprint_id: str
    browser_session_id: str
    chatgpt_url: str
    latency_ms: int
    run_id: str = ""
    report_id: str = ""
    chapter_id: str = ""
    requested_model: str = ""
    resolved_model: str = ""
    input_token_count: int = 0
    output_token_count: int = 0
    status: str = "succeeded"
    error_message: str = ""
    created_at: str = ""
    schema_version: str = "model_call_ledger.v1"

    def to_dict(self) -> dict[str, Any]:
        return to_json_dict(self)


@dataclass(frozen=True)
class ClassificationDecision:
    video_id: str
    group_type: str
    confidence: float
    signal_breakdown: dict[str, float]
    fallback_used: bool = False
    schema_version: str = "classification_decision.v1"

    def to_dict(self) -> dict[str, Any]:
        return to_json_dict(self)


@dataclass(frozen=True)
class ValidatorCheck:
    id: str
    name: str
    status: str
    evidence: list[str]
    diff: str = ""

    def to_dict(self) -> dict[str, Any]:
        return to_json_dict(self)


@dataclass(frozen=True)
class ValidatorReport:
    run_id: str
    overall: str
    checks: list[ValidatorCheck]
    schema_version: str = "validator_report.v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "overall": self.overall,
            "checks": [check.to_dict() for check in self.checks],
        }
