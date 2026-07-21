"""Operator seams for future platform integrations.

Defines the Protocols and fallback implementations for Living Report,
Research Lab, Research Memory, AI Infra Pack, and Artifact Delta application.

These seams allow future features to be wired in without modifying
the v1 core codebase or violating runtime invariants.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional, Protocol, runtime_checkable

from .schemas import AIInfraPack, ArtifactDelta, LivingReport, ResearchLab, ResearchMemory


@runtime_checkable
class LivingReportOperator(Protocol):
    """Protocol defining the seam for Living Report lifecycle management."""

    def initialize_report(self, topic: str, initial_ast_id: str, watch_schedules: Optional[list[dict[str, Any]]] = None) -> LivingReport:
        """Create a new Living Report container."""
        ...

    def update_report(self, report_id: str, new_ast_id: str, change_summary: str) -> LivingReport:
        """Apply a new compiled ReportAST version to the Living Report."""
        ...

    def trigger_watch_cycle(self, report_id: str) -> list[str]:
        """Manually trigger a check/compilation run based on active schedules.

        Returns list of spawned research run IDs.
        """
        ...


@runtime_checkable
class ResearchLabOperator(Protocol):
    """Protocol defining the seam for Research Lab computational execution."""

    def register_lab(self, name: str, slots: list[str]) -> ResearchLab:
        """Initialize a new isolated computational Lab environment."""
        ...

    def allocate_slot(self, lab_id: str, task_type: str) -> str:
        """Allocate an available physical operator slot.

        Returns the assigned slot ID/path (e.g. 'lab:0').
        """
        ...

    def submit_experiment(self, lab_id: str, task_spec: dict[str, Any], slot_id: str) -> str:
        """Submit a research task run to a specific runner slot.

        Returns the generated run_id.
        """
        ...

    def check_telemetry_limits(self, lab_id: str, current_run_id: str) -> dict[str, Any]:
        """Verify if the running experiment is within token and budget limits.

        Returns a verdict payload (e.g. {"ok": True, "token_count": 1200}).
        """
        ...


@runtime_checkable
class ResearchMemoryOperator(Protocol):
    """Protocol defining the seam for Research Memory substrate operations."""

    def store_fact(self, memory_id: str, claim_id: str, fact_text: str, confidence: float) -> bool:
        """Store a verified fact in the semantic/fact ledger memory."""
        ...

    def query_similar_facts(self, memory_id: str, query_text: str, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve semantically similar facts from memory."""
        ...

    def append_episodic_log(self, memory_id: str, run_id: str, events: list[dict[str, Any]]) -> None:
        """Append trace events/checkpoints for run-local execution history."""
        ...


@runtime_checkable
class AIInfraPackOperator(Protocol):
    """Protocol defining the seam for AI Infra Pack provisioning."""

    def load_pack(self, pack_id: str) -> AIInfraPack:
        """Fetch and parse a pre-configured infrastructure pack."""
        ...

    def provision_mcp_servers(self, pack: AIInfraPack) -> dict[str, dict[str, Any]]:
        """Launch/bind the MCP servers declared in the pack.

        Returns a dictionary mapping server name to endpoint configuration.
        """
        ...

    def resolve_operator_template(self, pack: AIInfraPack, desired_role: str) -> dict[str, Any]:
        """Resolve a physical operator config matching the requested role template."""
        ...


@runtime_checkable
class ArtifactDeltaApplier(Protocol):
    """Protocol defining the seam for differential artifact updates."""

    def apply_delta(self, target_artifact: Any, delta: ArtifactDelta) -> Any:
        """Apply a differential delta patch set to an existing dataclass artifact.

        Validates the patched output against target schema rules and preserves
        v1 core invariants.
        """
        ...


# ---------------------------------------------------------------------------
# Fallback Default Implementations (Graceful Degradation / Seams)
# ---------------------------------------------------------------------------

class DegradedLivingReportOperator:
    """Fallback LivingReport operator that warns or raises NotImplementedError.

    Used when LivingReport is not supported by the current active runtime.
    """

    def initialize_report(self, topic: str, initial_ast_id: str, watch_schedules: Optional[list[dict[str, Any]]] = None) -> LivingReport:
        import uuid
        return LivingReport(
            report_id=f"lr_{uuid.uuid4().hex[:8]}",
            topic=topic,
            active_ast_id=initial_ast_id,
            watch_schedules=watch_schedules or [],
        )

    def update_report(self, report_id: str, new_ast_id: str, change_summary: str) -> LivingReport:
        raise NotImplementedError("LivingReport updates are disabled in this core execution tier.")

    def trigger_watch_cycle(self, report_id: str) -> list[str]:
        return []  # No-op in degraded mode


class DegradedResearchLabOperator:
    """Fallback ResearchLab operator that maps slots statically.

    Ensures standard tasks bypass complex lab routing and run in-process.
    """

    def register_lab(self, name: str, slots: list[str]) -> ResearchLab:
        return ResearchLab(lab_id="default_lab", name=name, status="active", runner_slots=slots)

    def allocate_slot(self, lab_id: str, task_type: str) -> str:
        # Trivial round-robin or static selection
        return "main:0"

    def submit_experiment(self, lab_id: str, task_spec: dict[str, Any], slot_id: str) -> str:
        raise NotImplementedError("Direct lab execution is unsupported on this node.")

    def check_telemetry_limits(self, lab_id: str, current_run_id: str) -> dict[str, Any]:
        return {"ok": True, "action": "ignored", "reason": "No active telemetry limits."}


class DegradedResearchMemoryOperator:
    """Fallback ResearchMemory operator that falls back to in-memory/no-op storage.

    Prevents failing runs if external vector databases or memories are unreachable.
    """

    def store_fact(self, memory_id: str, claim_id: str, fact_text: str, confidence: float) -> bool:
        return False  # Fact storage omitted

    def query_similar_facts(self, memory_id: str, query_text: str, limit: int = 5) -> list[dict[str, Any]]:
        return []  # No search results available

    def append_episodic_log(self, memory_id: str, run_id: str, events: list[dict[str, Any]]) -> None:
        pass  # Omit logging history


class DegradedAIInfraPackOperator:
    """Fallback AIInfraPack operator that loads default system resources.

    Ensures standard MCP stdio settings are used when packs are unspecified.
    """

    def load_pack(self, pack_id: str) -> AIInfraPack:
        return AIInfraPack(
            pack_id=pack_id,
            pack_name="degraded-default-pack",
            version="1.0.0",
            status="stable"
        )

    def provision_mcp_servers(self, pack: AIInfraPack) -> dict[str, dict[str, Any]]:
        return {}  # No extra servers provisioned

    def resolve_operator_template(self, pack: AIInfraPack, desired_role: str) -> dict[str, Any]:
        return {"role": desired_role, "vendor": "openai", "allowed_models": ["gpt-4o"]}


class DegradedArtifactDeltaApplier:
    """Fallback ArtifactDeltaApplier that raises NotImplementedError.

    Requires full runtime schema loader capability to apply patches safely.
    """

    def apply_delta(self, target_artifact: Any, delta: ArtifactDelta) -> Any:
        raise NotImplementedError("Differential delta patch application is unavailable on N7 runtime.")
