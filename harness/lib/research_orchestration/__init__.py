"""Solar-owned production research orchestration."""

from .intent import ResearchIntentError, classify_research_intent
from .evaluator import evaluate_production_result
from .orchestrator import ResearchOrchestrationError, ResearchOrchestrator
from .resolver import (
    PhysicalOperatorBinding,
    PhysicalOperatorResolutionError,
    PhysicalOperatorResolver,
)
from .routing import (
    ResearchRouteDecision,
    ResearchRoutingError,
    select_production_route,
    workflow_from_entry_stage,
)
from .runtime import (
    FileWorkflowCatalog,
    ResearchRuntimeError,
    SolarResearchRuntime,
    artifact_reference,
    build_task_contract,
    default_synthesis_resolver,
    load_evidence_references,
)

__all__ = [
    "FileWorkflowCatalog",
    "PhysicalOperatorBinding",
    "PhysicalOperatorResolutionError",
    "PhysicalOperatorResolver",
    "ResearchIntentError",
    "ResearchOrchestrationError",
    "ResearchOrchestrator",
    "ResearchRouteDecision",
    "ResearchRoutingError",
    "ResearchRuntimeError",
    "SolarResearchRuntime",
    "artifact_reference",
    "build_task_contract",
    "classify_research_intent",
    "default_synthesis_resolver",
    "evaluate_production_result",
    "load_evidence_references",
    "select_production_route",
    "workflow_from_entry_stage",
]
