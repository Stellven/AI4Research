#!/usr/bin/env python3
"""Deterministic AutoSci workflow contract for Solar intake.

This module is intentionally small and data-oriented. It does not execute
AutoSci. It decides when a normal RawIntent/intake request is asking for the
Solar-native AutoSci research lifecycle, and materializes the existing
scientific task-graph template as a contract-bound workflow.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


WORKFLOW_CONTRACT_ID = "research.autosci.v1"
WORKFLOW_CONTRACT_VERSION = "1.0"
WORKFLOW_TEMPLATE_ID = "scientific_research_lifecycle_full_v1"

SCIENTIFIC_LOGICAL_TO_CAPSULE: dict[str, str] = {
    "ScientificLiteratureDiscoverer": "cap.research-literature-discover",
    "ScientificPaperIngestor": "cap.research-paper-ingest",
    "ScientificPaperAnalyzer": "cap.research-paper-analyze",
    "ScientificMemoryUpdater": "cap.research-memory-update",
    "ScientificGraphUpdater": "cap.research-graph-update",
    "ScientificClaimExtractor": "cap.research-claim-extract",
    "ScientificMethodExtractor": "cap.research-method-extract",
    "ScientificCodeEvidenceMapper": "cap.research-code-evidence-map",
    "ScientificIdeaGenerator": "cap.research-idea-generate",
    "ScientificIdeaEvaluator": "cap.research-idea-evaluate",
    "ScientificExperimentDesigner": "cap.research-experiment-design",
    "ScientificExperimentRunner": "cap.research-experiment-run",
    "ScientificExperimentMonitor": "cap.research-experiment-monitor",
    "ScientificClaimVerifier": "cap.research-claim-verify",
    "ScientificReportPlanner": "cap.research-report-plan",
    "ScientificReportDrafter": "cap.research-report-draft",
    "ScientificArtifactReviewer": "cap.research-artifact-review",
    "ScientificPublicationProducer": "cap.research-publication-produce",
    "ScientificWorkflowEvolver": "cap.research-workflow-evolve",
}

AUTOSCI_SIGNAL_RE = re.compile(
    r"(?i)(\bauto\s*sci\b|\bautosci\b|\$research|\$ingest|\$ideate|"
    r"\$exp-design|\$exp-run|\$exp-eval|scientific_research_lifecycle_full_v1|"
    r"research\.autosci)"
)

WORKFLOW_SIGNAL_RE = re.compile(
    r"(?i)(paper|papers|literature|scientific|research|claim|claims|idea|ideas|"
    r"ingest|ideate|experiment|exp-|eval|report|omega|omegawiki|scheduler-run|"
    r"full-runtime|full run|e2e|end-to-end|intake|autonomous|workflow|lifecycle|"
    r"论文|文献|研究|声明|想法|实验|报告|端到端|全流程|自主|自动)"
)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_autosci_research_intake_text(text: str) -> bool:
    """Return true when a normal intake request should bind to AutoSci.

    The rule is deliberately explicit: the user must name AutoSci, a native
    AutoSci skill, or the scientific lifecycle contract, and also describe a
    research/workflow action. This prevents generic engineering requests from
    being silently converted into research workflows.
    """
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return False
    return bool(AUTOSCI_SIGNAL_RE.search(normalized) and WORKFLOW_SIGNAL_RE.search(normalized))


def _replace_workflow_slug(value: Any, *, old: str, new: str) -> Any:
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [_replace_workflow_slug(item, old=old, new=new) for item in value]
    if isinstance(value, dict):
        return {key: _replace_workflow_slug(item, old=old, new=new) for key, item in value.items()}
    return value


def _load_workflow_template(harness_dir: Path) -> dict[str, Any]:
    path = harness_dir / "workflows" / f"{WORKFLOW_TEMPLATE_ID}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"workflow template must be a JSON object: {path}")
    if not isinstance(payload.get("nodes"), list) or not payload["nodes"]:
        raise ValueError(f"workflow template must contain nodes: {path}")
    return payload


def build_autosci_task_graph(
    *,
    sprint_id: str,
    title: str,
    request_text: str,
    harness_dir: Path,
) -> dict[str, Any]:
    """Instantiate the full scientific lifecycle template for one intake run."""
    template = _load_workflow_template(Path(harness_dir))
    graph = copy.deepcopy(template)
    graph = _replace_workflow_slug(graph, old=WORKFLOW_TEMPLATE_ID, new=sprint_id)
    if not isinstance(graph, dict):
        raise ValueError("workflow template replacement produced non-object graph")

    graph.update(
        {
            "schema_version": "solar.task_graph.v1",
            "workflow_id": WORKFLOW_TEMPLATE_ID,
            "workflow_run_id": sprint_id,
            "workflow_contract": WORKFLOW_CONTRACT_ID,
            "workflow_contract_id": WORKFLOW_CONTRACT_ID,
            "workflow_contract_version": WORKFLOW_CONTRACT_VERSION,
            "contract_bound": True,
            "plan_compile_required": True,
            "strict_role_boundaries": True,
            "strict_filesystem_boundaries": True,
            "planner_stage": {
                "node_id": "N0",
                "role": "planner",
                "status": "required",
                "next_role": "builder",
                "spillover_allowed": False,
            },
            "sprint_id": sprint_id,
            "title": f"AutoSci Research Workflow - {title[:120]}",
            "description": "Contract-bound AutoSci research lifecycle generated by normal Solar intake.",
            "dag_variant": WORKFLOW_CONTRACT_ID,
            "request_type": "research",
            "lane": "research",
            "research_mode": True,
            "artifact_roots": {
                "canonical": f"artifacts/scientific/{sprint_id}/",
                "aliases": [],
                "root_policy": "normalize_then_check",
            },
            "source_request_excerpt": str(request_text or "")[:4000],
            "generated_at": _now(),
            "intake_contract": {
                "id": WORKFLOW_CONTRACT_ID,
                "template_workflow_id": WORKFLOW_TEMPLATE_ID,
                "routing": "normal_intake_autosci_contract",
                "planner_review_required": True,
                "dispatch_rule": "valid_plan_certificate_required_before_builder",
            },
        }
    )
    quality_gates = graph.get("quality_gates") if isinstance(graph.get("quality_gates"), dict) else {}
    parallelism = quality_gates.get("parallelism") if isinstance(quality_gates.get("parallelism"), dict) else {}
    parallelism["min_ready_width"] = 1
    quality_gates["parallelism"] = parallelism
    graph["quality_gates"] = quality_gates

    nodes = []
    for raw_node in graph.get("nodes", []) or []:
        if not isinstance(raw_node, dict):
            continue
        node = dict(raw_node)
        logical_operator = str(node.get("logical_operator") or "")
        capsule_id = SCIENTIFIC_LOGICAL_TO_CAPSULE.get(logical_operator, "")
        architecture_policy = dict(node.get("architecture_policy") or {})
        # Scientific discovery/idea generation explores evidence, not Solar's
        # architecture. The shared architecture guard treats a plugin boundary
        # plus words such as "candidate" as architectural exploration unless
        # the fixed workflow contract states this distinction explicitly.
        architecture_policy.setdefault("online_exploration", False)
        node["architecture_policy"] = architecture_policy
        node["workflow_contract"] = WORKFLOW_CONTRACT_ID
        node.setdefault("status", "pending")
        node["type"] = "scientific-research"
        node["dispatch_task_type"] = "scientific-research"
        if capsule_id:
            node["capability_native"] = True
            node["capability_capsule_id"] = capsule_id
            node["capsule_plan"] = {
                "capability_native": True,
                "capability_capsule_id": capsule_id,
                "dispatch_task_type": "scientific-research",
                "selection_mode": "workflow_contract_research_autosci_v1",
                "fallback_used": False,
                "fallback_reason": None,
                "request_type": "research",
                "lane_hint": "research",
                "logical_operator": logical_operator,
                "node_goal": str(node.get("goal") or ""),
                "selected_skills": [],
                "operator_constraints": {},
            }
        nodes.append(node)
    graph["nodes"] = nodes
    return graph


def validate_autosci_planner_graph(
    graph: dict[str, Any],
    *,
    harness_dir: Path,
    expected_sprint_id: str,
) -> list[dict[str, Any]]:
    """Validate the Planner-reviewed AutoSci proposal against its locked DAG.

    AutoSci uses a planner-generated workflow contract so it participates in
    the same certificate gate as other planned work. Its scientific topology,
    however, is a product contract rather than free-form Planner output. This
    check prevents a Planner from deleting evaluator stages, merging roles, or
    silently swapping capsules before the certificate is stamped.
    """
    errors: list[dict[str, Any]] = []

    def add(code: str, message: str, *, node_id: str = "?") -> None:
        errors.append({"code": code, "node_id": node_id, "message": message})

    sid = str(graph.get("sprint_id") or "")
    if sid != str(expected_sprint_id):
        add("PLAN_SPRINT_ID_MISMATCH", f"graph sprint_id {sid!r} does not match {expected_sprint_id!r}")
    if str(graph.get("workflow_contract_id") or "") != WORKFLOW_CONTRACT_ID:
        add("WORKFLOW_CONTRACT_ID_MISMATCH", "AutoSci graph must retain research.autosci.v1 identity")
    if str(graph.get("workflow_contract_version") or "") != WORKFLOW_CONTRACT_VERSION:
        add("WORKFLOW_CONTRACT_VERSION_MISMATCH", "AutoSci graph contract version must be 1.0")
    if graph.get("plan_compile_required") is not True:
        add("PLAN_COMPILE_MARKER_MISSING", "AutoSci graph must retain plan_compile_required=true")
    if graph.get("strict_role_boundaries") is not True:
        add("AUTOSCI_ROLE_BOUNDARY_MISSING", "AutoSci requires strict_role_boundaries=true")
    if graph.get("strict_filesystem_boundaries") is not True:
        add("AUTOSCI_FILESYSTEM_BOUNDARY_MISSING", "AutoSci requires strict_filesystem_boundaries=true")
    planner_stage = graph.get("planner_stage") if isinstance(graph.get("planner_stage"), dict) else {}
    if (
        planner_stage.get("role") != "planner"
        or planner_stage.get("node_id") != "N0"
        or planner_stage.get("spillover_allowed") is not False
    ):
        add("AUTOSCI_PLANNER_STAGE_MISSING", "AutoSci requires a distinct N0 Planner stage")

    expected = build_autosci_task_graph(
        sprint_id=expected_sprint_id,
        title=str(graph.get("title") or "AutoSci"),
        request_text=str(graph.get("source_request_excerpt") or ""),
        harness_dir=Path(harness_dir),
    )
    for field in (
        "dag_variant",
        "research_mode",
        "artifact_roots",
        "required_gates",
        "evidence_policy",
        "strict_role_boundaries",
        "strict_filesystem_boundaries",
    ):
        if graph.get(field) != expected.get(field):
            add("AUTOSCI_GRAPH_CONTRACT_MISMATCH", f"top-level field {field!r} differs from the AutoSci contract")

    actual_nodes = {
        str(node.get("id") or ""): node
        for node in graph.get("nodes", []) or []
        if isinstance(node, dict) and node.get("id")
    }
    expected_nodes = {
        str(node.get("id") or ""): node
        for node in expected.get("nodes", []) or []
        if isinstance(node, dict) and node.get("id")
    }
    if set(actual_nodes) != set(expected_nodes):
        add(
            "AUTOSCI_GRAPH_NODE_SET_MISMATCH",
            f"AutoSci node ids differ: missing={sorted(set(expected_nodes) - set(actual_nodes))}, "
            f"extra={sorted(set(actual_nodes) - set(expected_nodes))}",
        )
        return errors

    governed_node_fields = (
        "logical_operator",
        "depends_on",
        "required_capabilities",
        "read_scope",
        "write_scope",
        "gate",
        "evidence_policy",
        "architecture_policy",
        "type",
        "dispatch_task_type",
        "capability_capsule_id",
    )
    for node_id in sorted(expected_nodes):
        actual = actual_nodes[node_id]
        canonical = expected_nodes[node_id]
        for field in governed_node_fields:
            if actual.get(field) != canonical.get(field):
                add(
                    "AUTOSCI_GRAPH_NODE_CONTRACT_MISMATCH",
                    f"node {node_id!r} field {field!r} differs from the AutoSci contract",
                    node_id=node_id,
                )
    return errors


def build_autosci_plan_markdown(sprint_id: str, title: str, graph: dict[str, Any]) -> str:
    node_rows = [
        f"| {node.get('id')} | {node.get('logical_operator')} | {', '.join(node.get('depends_on') or []) or '-'} | {node.get('gate') or '-'} |"
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
    ]
    return (
        f"# AutoSci Workflow Plan - {title}\n\n"
        f"sprint_id: `{sprint_id}`\n"
        f"workflow_contract: `{WORKFLOW_CONTRACT_ID}`\n"
        f"workflow_template: `{WORKFLOW_TEMPLATE_ID}`\n\n"
        "## Dispatch Contract\n\n"
        "- Normal Solar intake selected the AutoSci research workflow as a proposed graph.\n"
        "- A distinct Planner must review the proposal and obtain a valid plan certificate before Builder dispatch.\n"
        "- Autopilot should dispatch ready Scientific* DAG nodes through graph_scheduler.\n"
        "- Each node must emit schema-gated scientific evidence or an explicit failed/inconclusive record.\n\n"
        "## Nodes\n\n"
        "| Node | Logical Operator | Depends On | Gate |\n"
        "| --- | --- | --- | --- |\n"
        + "\n".join(node_rows)
        + "\n"
    )


def build_autosci_design_markdown(sprint_id: str, title: str, graph: dict[str, Any]) -> str:
    logical_ops = sorted(
        {
            str(node.get("logical_operator") or "")
            for node in graph.get("nodes", [])
            if isinstance(node, dict) and node.get("logical_operator")
        }
    )
    return (
        f"# AutoSci Workflow Design - {title}\n\n"
        f"sprint_id: `{sprint_id}`\n"
        f"workflow_contract: `{WORKFLOW_CONTRACT_ID}`\n\n"
        "## Architecture\n\n"
        "This sprint is bound to the Solar-native AutoSci lifecycle. The task graph is the design: "
        "each Scientific* logical operator resolves to its research capability capsule and then to "
        "the matching autosci-* physical command worker.\n\n"
        "## Logical Operators\n\n"
        + "\n".join(f"- `{op}` -> `{SCIENTIFIC_LOGICAL_TO_CAPSULE.get(op, 'N/A')}`" for op in logical_ops)
        + "\n"
    )


def build_autosci_product_brief(title: str, request_text: str) -> dict[str, Any]:
    return {
        "title": title,
        "source": "autosci-intake-contract",
        "intent": str(request_text or "")[:400],
        "problem": "Route a normal Solar intake request into the contract-bound AutoSci research lifecycle.",
        "priority": "P1",
        "lane_hint": "research",
        "acceptance": [
            "Normal intake emits a research.autosci.v1 proposed task graph and routes it to Planner.",
            "Builder dispatch is refused until Planner produces a valid plan certificate.",
            "Scientific* nodes resolve to AutoSci research capsules and autosci-* physical operators.",
            "Autopilot can dispatch ready graph nodes without a manual AutoSci shim call.",
        ],
        "non_goals": [
            "Do not run a hidden backend full workflow.",
            "Do not replace AutoSci node evidence with generic planner prose.",
        ],
        "stop_rules": [
            "Missing scientific task_graph blocks dispatch.",
            "Missing schema-gated evidence blocks closeout.",
        ],
        "handoff_to": "planner",
        "request_type": "research",
        "template_variant": "autosci",
        "notes": "Generated as a deterministic AutoSci graph proposal; Planner certification is mandatory.",
    }
