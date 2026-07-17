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
            "workflow_contract_version": 1,
            "contract_bound": True,
            "sprint_id": sprint_id,
            "title": f"AutoSci Research Workflow - {title[:120]}",
            "description": "Contract-bound AutoSci research lifecycle generated by normal Solar intake.",
            "dag_variant": WORKFLOW_CONTRACT_ID,
            "request_type": "research",
            "lane": "research",
            "research_mode": True,
            "source_request_excerpt": str(request_text or "")[:4000],
            "generated_at": _now(),
            "intake_contract": {
                "id": WORKFLOW_CONTRACT_ID,
                "template_workflow_id": WORKFLOW_TEMPLATE_ID,
                "routing": "normal_intake_autosci_contract",
                "planner_bypass_reason": "workflow_contract_already_supplies_scientific_task_graph",
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
        "- Normal Solar intake has selected the AutoSci research workflow by contract.\n"
        "- The workflow is graph-ready; do not send this sprint back through a generic planner.\n"
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
            "Normal intake emits a research.autosci.v1 task graph.",
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
        "handoff_to": "builder_main",
        "request_type": "research",
        "template_variant": "autosci",
        "notes": "Generated by the deterministic AutoSci intake contract.",
    }
