"""Production input routing for Solar-owned research runs."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .intent import ResearchIntentError, classify_research_intent


class ResearchRoutingError(ValueError):
    """Raised when a production research entry route cannot be selected safely."""


_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)
_LOCAL_SUFFIXES = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "markdown",
    ".text": "markdown",
}

START_STAGE_BY_SEED_KIND = {
    "url": "web_fetch",
    "pdf": "paper_ingest",
    "markdown": "material_ingest",
    "topic": "source_discovery",
    "research_brief": "source_discovery",
    "external_evidence": "evidence_import",
}

_CODE_ANALYSIS_RE = re.compile(
    r"\b(?:code|repository|repo|source\s+tree|implementation|call\s+site|代码|代码库|仓库|实现分析)\b",
    re.IGNORECASE,
)
_IDEA_OR_EXPERIMENT_RE = re.compile(
    r"\b(?:idea|ideat|hypothesis|novel\s+direction|experiment|benchmark|prototype|poc|实验|假设|创意|原型)\w*\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ResearchRouteDecision:
    """Auditable route metadata selected before workflow execution."""

    seed_kind: str
    workflow_kind: str
    run_mode: str
    start_stage: str
    reason_codes: tuple[str, ...]
    confidence: float
    requires_user_confirmation: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason_codes"] = list(self.reason_codes)
        return payload


def normalize_seed_inputs(seed_inputs: list[dict] | None) -> list[dict]:
    """Normalize local text aliases without weakening the frozen task schema."""

    normalized: list[dict] = []
    for raw in seed_inputs or []:
        if not isinstance(raw, dict):
            raise ResearchRoutingError("seed_inputs must contain objects")
        item = deepcopy(raw)
        value = str(item.get("value") or item.get("path") or item.get("url") or "").strip()
        kind = str(item.get("seed_kind") or item.get("kind") or "").strip().lower().replace("-", "_")
        if kind in {"text", "txt", "local_text", "md"}:
            kind = "markdown"
        if not kind and value:
            kind = seed_kind_for_value(value)
        if not kind:
            kind = "topic"
        item["seed_kind"] = kind
        if value:
            item["value"] = value
        normalized.append(item)
    return normalized


def seed_kind_for_value(value: str) -> str:
    """Classify one explicit source value for the production entrypoint."""

    text = str(value or "").strip()
    if not text:
        raise ResearchRoutingError("seed value must be non-empty")
    if _URL_RE.fullmatch(text):
        return "url"
    suffix = Path(text).suffix.lower()
    return _LOCAL_SUFFIXES.get(suffix, "topic")


def select_production_route(
    prompt: str,
    *,
    seed_inputs: list[dict] | None = None,
    explicit_workflow: str | None = None,
    run_mode: str = "execute",
) -> ResearchRouteDecision:
    """Select a general workflow family and semantic entry stage.

    The stage is selected from input semantics, not from a provider identity or
    a one-off research backend.  Workflow loading must resolve this stage to a
    real node and fails closed when it cannot.
    """

    normalized = normalize_seed_inputs(seed_inputs)
    try:
        classification = classify_research_intent(
            prompt,
            seed_inputs=normalized,
            explicit_workflow=explicit_workflow,
            run_mode=run_mode,
        )
    except ResearchIntentError as exc:
        raise ResearchRoutingError(str(exc)) from exc
    seed_kind = str(classification["seed_kind"])
    if classification["workflow_kind"] == "workflow_evolution":
        start_stage = "workflow_evolve"
    else:
        try:
            start_stage = START_STAGE_BY_SEED_KIND[seed_kind]
        except KeyError as exc:  # defensive against classifier/config drift
            raise ResearchRoutingError(f"no production entry stage for seed_kind: {seed_kind}") from exc
    return ResearchRouteDecision(
        seed_kind=seed_kind,
        workflow_kind=str(classification["workflow_kind"]),
        run_mode=str(classification["run_mode"]),
        start_stage=start_stage,
        reason_codes=tuple(str(item) for item in classification.get("reason_codes") or []),
        confidence=float(classification.get("confidence") or 0.0),
        requires_user_confirmation=bool(classification.get("requires_user_confirmation")),
    )


def workflow_from_entry_stage(
    workflow: dict,
    decision: ResearchRouteDecision,
    *,
    entrypoint_aliases: dict[str, str] | None = None,
) -> dict:
    """Return the reachable workflow subgraph beginning at the selected stage."""

    if not isinstance(workflow, dict):
        raise ResearchRoutingError("workflow must be an object")
    raw_nodes = workflow.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ResearchRoutingError("workflow must contain non-empty nodes")
    nodes: list[dict] = []
    by_id: dict[str, dict] = {}
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            raise ResearchRoutingError("workflow nodes must be objects")
        node = deepcopy(raw)
        node_id = str(node.get("node_id") or node.get("id") or "").strip()
        if not node_id:
            raise ResearchRoutingError("workflow node is missing an identity")
        if node_id in by_id:
            raise ResearchRoutingError(f"duplicate workflow node: {node_id}")
        node["node_id"] = node_id
        node["depends_on"] = [str(item) for item in node.get("depends_on") or []]
        by_id[node_id] = node
        nodes.append(node)

    aliases = dict(entrypoint_aliases or {})
    start_node = aliases.get(decision.start_stage, decision.start_stage)
    if start_node not in by_id:
        raise ResearchRoutingError(
            f"workflow {workflow.get('workflow_id') or '<unknown>'} has no physical entry node "
            f"for stage {decision.start_stage}"
        )

    outgoing = {node_id: [] for node_id in by_id}
    for node_id, node in by_id.items():
        for dependency in node["depends_on"]:
            if dependency not in by_id:
                raise ResearchRoutingError(f"{node_id} depends on missing node {dependency}")
            outgoing[dependency].append(node_id)
    selected = {start_node}
    queue = [start_node]
    while queue:
        current = queue.pop(0)
        for child in outgoing[current]:
            if child not in selected:
                selected.add(child)
                queue.append(child)

    selected_nodes: list[dict] = []
    for node in nodes:
        if node["node_id"] not in selected:
            continue
        item = deepcopy(node)
        removed_dependencies = [dep for dep in item["depends_on"] if dep not in selected]
        item["depends_on"] = [dep for dep in item["depends_on"] if dep in selected]
        if removed_dependencies:
            removed_outputs = {
                str(path)
                for dep in removed_dependencies
                for path in [
                    *(by_id[dep].get("write_scope") or []),
                    *(by_id[dep].get("expected_output_artifacts") or []),
                ]
            }
            item["read_scope"] = [
                scope for scope in item.get("read_scope") or [] if str(scope) not in removed_outputs
            ]
        selected_nodes.append(item)
    result = deepcopy(workflow)
    result["workflow_kind"] = decision.workflow_kind
    result["start_node"] = start_node
    result["start_stage"] = decision.start_stage
    result["nodes"] = selected_nodes
    return result


def apply_task_conditions(workflow: dict, task_contract: dict) -> dict:
    """Remove non-applicable lifecycle nodes and retain explicit skip reasons.

    Conditional routing is deliberately performed before Solar initializes the
    graph.  Solar therefore remains the only owner of the graph that is
    actually executed, while the frozen task contract records every omitted
    node and its reason.
    """

    result = deepcopy(workflow)
    raw_nodes = result.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ResearchRoutingError("workflow must contain non-empty nodes")
    by_id = {str(item.get("node_id") or ""): deepcopy(item) for item in raw_nodes if isinstance(item, dict)}
    if "code_evidence_map" not in by_id:
        result["conditional_skips"] = []
        return result

    constraints = task_contract.get("constraints") if isinstance(task_contract.get("constraints"), dict) else {}
    repository_inputs = [item for item in constraints.get("repository_inputs") or [] if isinstance(item, dict)]
    intent = str(task_contract.get("user_intent") or "")
    code_requested = bool(repository_inputs) or bool(_CODE_ANALYSIS_RE.search(intent))
    idea_or_experiment_requested = bool(_IDEA_OR_EXPERIMENT_RE.search(intent))
    skipped: list[dict[str, str]] = []
    remove: set[str] = set()

    if not code_requested:
        remove.add("code_evidence_map")
        skipped.append(
            {
                "node_id": "code_evidence_map",
                "status": "skipped",
                "reason": "No code, repository path, or explicit code-analysis request was supplied.",
                "condition": "code_input_or_explicit_code_analysis_required",
            }
        )
    if not idea_or_experiment_requested:
        for node_id in (
            "idea_generate",
            "idea_evaluate",
            "experiment_design",
            "experiment_approval_gate",
            "experiment_run",
            "experiment_monitor",
        ):
            if node_id in by_id:
                remove.add(node_id)
                skipped.append(
                    {
                        "node_id": node_id,
                        "status": "skipped",
                        "reason": "The requested deliverable is evidence synthesis, not ideation or experiment execution.",
                        "condition": "explicit_ideation_or_experiment_request_required",
                    }
                )
        for node_id, reason, condition in (
            (
                "memory_update_final",
                "Final memory mutation is not applicable to a report-only synthesis request; earlier evidence memory and graph stages remain active.",
                "explicit_final_memory_update_required",
            ),
            (
                "workflow_evolve",
                "Workflow evolution was not requested by the user.",
                "explicit_workflow_evolution_request_required",
            ),
        ):
            if node_id in by_id:
                remove.add(node_id)
                skipped.append(
                    {
                        "node_id": node_id,
                        "status": "skipped",
                        "reason": reason,
                        "condition": condition,
                    }
                )

    removed_outputs = {
        str(path)
        for node_id in remove
        for path in [
            *(by_id[node_id].get("write_scope") or []),
            *(by_id[node_id].get("expected_output_artifacts") or []),
        ]
    }

    def expanded_dependencies(node_id: str, seen: set[str] | None = None) -> list[str]:
        values: list[str] = []
        active_seen = set(seen or set())
        if node_id in active_seen:
            raise ResearchRoutingError(f"conditional dependency cycle at {node_id}")
        active_seen.add(node_id)
        for dependency in by_id[node_id].get("depends_on") or []:
            dependency = str(dependency)
            if dependency in remove:
                values.extend(expanded_dependencies(dependency, active_seen))
            elif dependency in by_id and dependency not in values:
                values.append(dependency)
        return values

    selected: list[dict[str, Any]] = []
    for original in raw_nodes:
        node_id = str(original.get("node_id") or "")
        if node_id in remove:
            continue
        item = deepcopy(by_id[node_id])
        item["depends_on"] = expanded_dependencies(node_id)
        item["read_scope"] = [
            str(scope) for scope in item.get("read_scope") or [] if str(scope) not in removed_outputs
        ]
        selected.append(item)

    selected_by_id = {item["node_id"]: item for item in selected}
    claims_path = "artifacts/scientific/scientific_research_lifecycle_full_v1/02_claims/research_claims.v1.json"
    methods_path = "artifacts/scientific/scientific_research_lifecycle_full_v1/03_methods/research_method.v1.json"
    code_path = "artifacts/scientific/scientific_research_lifecycle_full_v1/04_code_evidence/code_evidence_map.v1.json"
    verdict_path = "artifacts/scientific/scientific_research_lifecycle_full_v1/08_verdict/claim_verdict.v1.json"
    plan_path = "artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/scientific_report_plan.v1.json"

    if code_requested and "code_evidence_map" in selected_by_id:
        code_node = selected_by_id["code_evidence_map"]
        snapshot = str((repository_inputs[0] if repository_inputs else {}).get("snapshot_path") or "")
        if snapshot:
            code_node["read_scope"] = list(dict.fromkeys([*code_node.get("read_scope", []), snapshot]))
    if "claim_verify" in selected_by_id:
        node = selected_by_id["claim_verify"]
        node["depends_on"] = [
            item for item in ("claim_extract", "method_extract", "code_evidence_map")
            if item in selected_by_id
        ]
        node["read_scope"] = list(dict.fromkeys([claims_path, methods_path, *([code_path] if "code_evidence_map" in selected_by_id else [])]))
    if "report_plan" in selected_by_id:
        node = selected_by_id["report_plan"]
        node["depends_on"] = [item for item in ("claim_verify", "method_extract") if item in selected_by_id]
        node["read_scope"] = [verdict_path, methods_path]
    if "report_draft" in selected_by_id:
        node = selected_by_id["report_draft"]
        node["depends_on"] = [item for item in ("report_plan", "claim_verify", "method_extract") if item in selected_by_id]
        node["read_scope"] = [plan_path, verdict_path, methods_path]

    constraints["conditional_skips"] = deepcopy(skipped)
    task_contract["constraints"] = constraints
    result["nodes"] = selected
    result["conditional_skips"] = skipped
    return result
