"""Solar Harness — Runtime Interface Definitions.

Typed protocols and dataclasses for Session, Harness, Hand, Worker,
ContextProjection, CommandEnvelope, ResultEnvelope, and CapabilityPolicy.

These are the stable ABI that all adapters must implement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class HandType(str, Enum):
    MOCK = "mock"
    SHELL = "shell"
    SANDBOX = "sandbox"
    PANE = "pane"
    REMOTE = "remote"
    MCP = "mcp"


class ResultStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    DUPLICATE_SUPPRESSED = "duplicate_suppressed"


class LeaseStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    RELEASED = "released"
    REVOKED = "revoked"


@dataclass
class EventPage:
    """Paginated event result."""
    events: List[Dict[str, Any]]
    next_cursor: Optional[str]
    has_more: bool
    total_matching: int
    returned_count: int


@dataclass
class CommandEnvelope:
    """Normalized command sent to a hand."""
    command_name: str
    input_data: Dict[str, Any]
    idempotency_key: str
    hand_type: HandType
    hand_ref: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResultEnvelope:
    """Normalized result from a hand execution."""
    status: ResultStatus
    output: Any = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    side_effects: List[str] = field(default_factory=list)
    redacted_secrets: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HandRef:
    """Reference to a provisioned hand instance."""
    hand_id: str
    hand_type: HandType
    provisioned_at: str
    capabilities: List[str] = field(default_factory=list)
    location: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityPolicy:
    """Policy governing what a hand can do."""
    allowed_commands: List[str] = field(default_factory=list)
    denied_commands: List[str] = field(default_factory=lambda: [
        "rm -rf /", "rm -rf /*", "mkfs", "dd if=/dev/zero",
        "chmod -R 777 /", "shutdown", "reboot", "halt",
    ])
    max_duration_seconds: int = 300
    require_lease: bool = False
    secret_patterns: List[str] = field(default_factory=lambda: [
        r"(?i)api[_-]?key\s*[=:]\s*\S+",
        r"(?i)token\s*[=:]\s*\S{8,}",
        r"(?i)password\s*[=:]\s*\S+",
        r"(?i)secret\s*[=:]\s*\S+",
        r"(?i)credential\s*[=:]\s*\S+",
        r"(?i)auth[_-]?token\s*[=:]\s*\S+",
        r"AKIA[0-9A-Z]{16}",
        r"ghp_[0-9a-zA-Z]{36}",
        r"sk-[0-9a-zA-Z]{20,}",
    ])


@dataclass
class ContextView:
    """Model-visible context projection with provenance."""
    session_id: str
    included_event_ids: List[str] = field(default_factory=list)
    summarized_ranges: List[Dict[str, Any]] = field(default_factory=list)
    dropped_ranges: List[Dict[str, Any]] = field(default_factory=list)
    kb_hits: List[Dict[str, Any]] = field(default_factory=list)
    token_estimate: int = 0
    budget_tokens: Optional[int] = None
    policy_name: str = "default"
    built_at: str = ""
    # Redacted event payload snippets for model consumption. This is intentionally
    # not part of the public provenance IDs, but it is still carried by the
    # typed view so context_projection can construct useful context text without
    # leaking raw session facts or secrets.
    _included_event_data: List[str] = field(default_factory=list, repr=False)


@dataclass
class WorkerInfo:
    """Registered worker in the runtime pool."""
    worker_id: str
    capabilities: List[str] = field(default_factory=list)
    location: str = "local"
    registered_at: str = ""
    last_heartbeat: str = ""
    lease: Optional[Dict[str, Any]] = None


@dataclass
class LeaseInfo:
    """Active lease held by a worker."""
    lease_id: str
    worker_id: str
    session_id: str
    activity_id: str
    acquired_at: str
    expires_at: str
    status: LeaseStatus = LeaseStatus.ACTIVE


# ------------------------------------------------------------------
# Protocols (structural typing)
# ------------------------------------------------------------------

class SessionAPI:
    """Stable interface for reading session events."""
    def get_events(
        self,
        session_id: str,
        *,
        cursor: Optional[str] = None,
        start_seq: Optional[int] = None,
        end_seq: Optional[int] = None,
        event_type: Optional[str] = None,
        activity_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> EventPage:
        ...


class HandRuntime:
    """Stable interface for hand provisioning and execution."""
    def provision(
        self,
        hand_type: HandType,
        *,
        capabilities: Optional[List[str]] = None,
        policy: Optional[CapabilityPolicy] = None,
        location: Optional[str] = None,
    ) -> HandRef:
        ...

    def execute(
        self,
        hand_ref: HandRef,
        command_name: str,
        input_data: Dict[str, Any],
        *,
        idempotency_key: str,
        timeout_seconds: Optional[int] = None,
    ) -> ResultEnvelope:
        ...

    def dispose(self, hand_ref: HandRef, *, reason: str = "completed") -> ResultEnvelope:
        ...


class WorkerRuntime:
    """Stable interface for worker pool management."""
    def register(
        self,
        worker_id: str,
        *,
        capabilities: Optional[List[str]] = None,
        location: str = "local",
        lease_ttl_seconds: int = 3600,
    ) -> WorkerInfo:
        ...

    def heartbeat(self, worker_id: str) -> bool:
        ...

    def acquire_lease(
        self,
        worker_id: str,
        session_id: str,
        activity_id: str,
        *,
        ttl_seconds: int = 3600,
    ) -> Optional[LeaseInfo]:
        ...

    def release_lease(self, worker_id: str, activity_id: str, *, reason: str = "completed") -> bool:
        ...


class ContextProjectionAPI:
    """Stable interface for building model-visible context from events."""
    def build_context(
        self,
        session_id: str,
        *,
        policy_name: str = "default",
        query: Optional[str] = None,
        budget_tokens: Optional[int] = None,
    ) -> ContextView:
        ...
