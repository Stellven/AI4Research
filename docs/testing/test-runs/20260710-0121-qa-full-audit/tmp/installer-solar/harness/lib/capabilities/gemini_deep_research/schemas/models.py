"""Stage handoff data models for the Gemini Deep Research flow.

Field-level contract source: S02 A2 (interface-contracts.md).
Security invariant (NB1): no object carries cookie/token/session secret.
Stdlib-only (dataclasses/enum) to avoid third-party deps inside harness lib.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# Validation bound for O1 input. A2 defers the exact ceiling to A3; A3 did not
# pin a number, so this is a builder default (chars) — overridable, not a
# business datum. Documented as provisional in the C1 handoff.
MAX_QUESTION_LEN = 8000

_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


class InvalidResearchRequest(ValueError):
    """Deterministic rejection of a malformed O1 input (A1/A2)."""


class Source(str, Enum):
    USER = "user"
    UPSTREAM = "upstream"


class Phase(str, Enum):
    PLANNING = "planning"


class AsyncState(str, Enum):
    """Browser job states owned by the DeepResearchBrowser operator (A1/A2)."""

    SUBMITTED = "submitted"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    REAUTH_REQUIRED = "reauth_required"
    DONE = "done"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ResultStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enum_value(v: Any) -> Any:
    return v.value if isinstance(v, Enum) else v


@dataclass
class Reference:
    """Classified literature item (epic hard requirement: category+title+url)."""

    category: str
    title: str
    url: str

    def validate(self) -> None:
        if not (self.category and self.category.strip()):
            raise InvalidResearchRequest("Reference.category must be non-empty")
        if not (self.title and self.title.strip()):
            raise InvalidResearchRequest("Reference.title must be non-empty")
        if not (self.url and _HTTP_URL_RE.match(self.url.strip())):
            raise InvalidResearchRequest("Reference.url must be an http(s) URL")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Reference":
        return cls(category=d["category"], title=d["title"], url=d["url"])


@dataclass
class ResearchRequest:
    """O1 input. Both user-direct and upstream paths produce this same object."""

    question: str
    source: Source
    request_id: str
    created_at: str
    upstream_ref: str | None = None
    lang_hint: str = "en"

    def __post_init__(self) -> None:
        if isinstance(self.source, str):
            try:
                self.source = Source(self.source)
            except ValueError as e:
                raise InvalidResearchRequest(f"invalid source: {self.source!r}") from e

    def validate(self) -> None:
        q = self.question
        if not isinstance(q, str):
            raise InvalidResearchRequest("question must be a string")
        try:
            q.encode("utf-8")
        except UnicodeError as e:
            raise InvalidResearchRequest("question has invalid encoding") from e
        if len(q.strip()) == 0:
            raise InvalidResearchRequest("question must be non-empty after strip")
        if len(q) > MAX_QUESTION_LEN:
            raise InvalidResearchRequest(
                f"question exceeds MAX_QUESTION_LEN={MAX_QUESTION_LEN}"
            )
        if self.source == Source.UPSTREAM and not self.upstream_ref:
            raise InvalidResearchRequest("upstream source requires upstream_ref")

    @classmethod
    def create(
        cls,
        question: str,
        source: Source | str = Source.USER,
        upstream_ref: str | None = None,
        lang_hint: str = "en",
    ) -> "ResearchRequest":
        req = cls(
            question=question,
            source=Source(source) if isinstance(source, str) else source,
            request_id=str(uuid.uuid4()),
            created_at=_now_iso(),
            upstream_ref=upstream_ref,
            lang_hint=lang_hint,
        )
        req.validate()
        return req

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source"] = _enum_value(self.source)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ResearchRequest":
        return cls(
            question=d["question"],
            source=Source(d["source"]),
            request_id=d["request_id"],
            created_at=d["created_at"],
            upstream_ref=d.get("upstream_ref"),
            lang_hint=d.get("lang_hint", "en"),
        )


@dataclass
class OptimizedPrompt:
    """O2 output -> O3 input. has_reference_directive must be True."""

    request_id: str
    prompt_text: str
    chat_session_ref: str
    has_reference_directive: bool
    optimizer_template_id: str

    def validate(self) -> None:
        if not (self.prompt_text and self.prompt_text.strip()):
            raise InvalidResearchRequest("OptimizedPrompt.prompt_text must be non-empty")
        if not self.has_reference_directive:
            raise InvalidResearchRequest(
                "has_reference_directive must be True (no reference directive -> O2 fails)"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OptimizedPrompt":
        return cls(
            request_id=d["request_id"],
            prompt_text=d["prompt_text"],
            chat_session_ref=d["chat_session_ref"],
            has_reference_directive=d["has_reference_directive"],
            optimizer_template_id=d["optimizer_template_id"],
        )


@dataclass
class DRPlan:
    """O3 planning state -> O4 input."""

    run_ref: str
    plan_detected: bool
    confirm_control_ref: str | None
    phase: Phase = Phase.PLANNING

    def __post_init__(self) -> None:
        if isinstance(self.phase, str):
            self.phase = Phase(self.phase)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["phase"] = _enum_value(self.phase)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DRPlan":
        return cls(
            run_ref=d["run_ref"],
            plan_detected=d["plan_detected"],
            confirm_control_ref=d.get("confirm_control_ref"),
            phase=Phase(d.get("phase", "planning")),
        )


@dataclass
class DRRunHandle:
    """O3/O4 -> O5 monitor handle. Reuses operator async job state."""

    run_ref: str
    async_state: AsyncState
    confirmed: bool
    started_at: str
    attempt: int
    next_poll_at: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.async_state, str):
            self.async_state = AsyncState(self.async_state)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["async_state"] = _enum_value(self.async_state)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DRRunHandle":
        return cls(
            run_ref=d["run_ref"],
            async_state=AsyncState(d["async_state"]),
            confirmed=d["confirmed"],
            started_at=d["started_at"],
            attempt=d["attempt"],
            next_poll_at=d.get("next_poll_at"),
        )


@dataclass
class DRResult:
    """O5 terminal state -> O6 evidence."""

    run_ref: str
    status: ResultStatus
    evidence_refs: list[str] = field(default_factory=list)
    report_text: str | None = None
    references: list[Reference] = field(default_factory=list)
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = ResultStatus(self.status)

    def validate(self) -> None:
        if self.status == ResultStatus.SUCCEEDED:
            if not (self.report_text and self.report_text.strip()):
                raise InvalidResearchRequest("succeeded result requires non-empty report_text")
            if not self.references:
                raise InvalidResearchRequest("succeeded result requires references")
            for r in self.references:
                r.validate()
        else:
            if not (self.failure_reason and self.failure_reason.strip()):
                raise InvalidResearchRequest("failed/timeout result requires failure_reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_ref": self.run_ref,
            "status": _enum_value(self.status),
            "evidence_refs": list(self.evidence_refs),
            "report_text": self.report_text,
            "references": [r.to_dict() for r in self.references],
            "failure_reason": self.failure_reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DRResult":
        return cls(
            run_ref=d["run_ref"],
            status=ResultStatus(d["status"]),
            evidence_refs=list(d.get("evidence_refs", [])),
            report_text=d.get("report_text"),
            references=[Reference.from_dict(x) for x in d.get("references", [])],
            failure_reason=d.get("failure_reason"),
        )
