#!/usr/bin/env python3
"""graph_scheduler_research.py — DeepResearch DAG template loader and research
node dispatcher.

Loads deepresearch.dag-template.json, substitutes placeholders, and provides
per-section fan-out dispatch for R7/R8 with isolated write_scope.
"""
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness")).expanduser()
SPRINTS_DIR = Path(os.environ.get("HARNESS_SPRINTS_DIR", HARNESS_DIR / "sprints")).expanduser()

_TEMPLATE_GLOB = "*.deepresearch.dag-template.json"


def _find_template(sprints_dir: Path | None = None) -> Path | None:
    root = sprints_dir or SPRINTS_DIR
    for path in sorted(root.glob(_TEMPLATE_GLOB)):
        return path
    return None


def load_deepresearch_template(
    sprint_id: str,
    report_ast: dict[str, Any] | None = None,
    template_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load and instantiate a DeepResearch DAG template.

    Substitutes <research-sid> with sprint_id. If report_ast is provided,
    expands R7/R8 fan-out nodes into per-section instances with isolated
    write_scope.
    """
    if template_path:
        path = Path(template_path)
    else:
        found = _find_template()
        if found is None:
            raise FileNotFoundError("No deepresearch.dag-template.json found")
        path = found

    template = json.loads(path.read_text(encoding="utf-8"))

    # Substitute sprint id
    raw = json.dumps(template, ensure_ascii=False)
    raw = raw.replace("<research-sid>", sprint_id)
    graph = json.loads(raw)
    graph["sprint_id"] = sprint_id

    if report_ast is None:
        return graph

    sections = _extract_sections(report_ast)
    if not sections:
        return graph

    graph = _expand_fan_out_nodes(graph, sections, sprint_id)
    return graph


def _extract_sections(report_ast: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for chapter in report_ast.get("chapters", []):
        chapter_id = chapter.get("chapter_id", "ch00")
        for section in chapter.get("sections", []):
            section["chapter_id"] = chapter_id
            sections.append(section)
    return sections


def _expand_fan_out_nodes(
    graph: dict[str, Any],
    sections: list[dict[str, Any]],
    sprint_id: str,
) -> dict[str, Any]:
    """Expand R7/R8 fan-out into per-section nodes with isolated write_scope."""
    expanded_nodes: list[dict[str, Any]] = []
    fan_out_ids = {"R7_section_writing_batch", "R8_section_fact_check"}

    for node in graph.get("nodes", []):
        if node.get("id") not in fan_out_ids:
            expanded_nodes.append(node)
            continue

        fan_out = node.get("fan_out")
        if not fan_out:
            expanded_nodes.append(node)
            continue

        parent_id = node["id"]
        for section in sections:
            section_id = section.get("section_id", "sec00")
            chapter_id = section.get("chapter_id", "ch00")
            instance = copy.deepcopy(node)
            instance["id"] = f"{parent_id}_{section_id}"
            instance["goal"] = node["goal"].replace("<section_id>", section_id)

            # Isolate write_scope: replace <section_id>/<chapter_id> placeholders
            instance["write_scope"] = [
                ws.replace("<section_id>", section_id).replace("<chapter_id>", chapter_id)
                for ws in (node.get("write_scope") or [])
            ]
            instance["read_scope"] = [
                rs.replace("<section_id>", section_id).replace("<chapter_id>", chapter_id)
                for rs in (node.get("read_scope") or [])
            ]

            # The fan-out instance depends on the parent's deps or parent node
            if parent_id == "R8_section_fact_check":
                # R8 instances depend on the corresponding R7 instance
                instance["depends_on"] = [f"R7_section_writing_batch_{section_id}"]
            else:
                instance["depends_on"] = list(node.get("depends_on", []))

            instance.pop("fan_out", None)
            instance["fan_out_parent"] = parent_id
            instance["section_id"] = section_id
            expanded_nodes.append(instance)

    graph["nodes"] = expanded_nodes
    return graph


def dispatch_research_node(
    graph: dict[str, Any],
    node_id: str,
    workers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Route a research node (R-prefixed) to an appropriate worker.

    Returns assignment dict compatible with graph_scheduler.assign_workers.
    Research nodes with fan-out_parent are routed with section-level isolation
    — two builders cannot write the same file.
    """
    from graph_scheduler import assign_workers, _node_map  # noqa: WPS433

    ids = _node_map(graph)
    if node_id not in ids:
        return {"ok": False, "reason": "unknown_node", "node": node_id}

    node = ids[node_id]
    if not node_id.startswith("R"):
        return {"ok": False, "reason": "not_research_node", "node": node_id}

    result = assign_workers([node], workers)
    assigned = result.get("assigned", [])

    if assigned:
        assigned[0]["research_node"] = True
        if node.get("fan_out_parent"):
            assigned[0]["section_isolation"] = True
            assigned[0]["section_id"] = node.get("section_id", "")

    return result


def validate_write_scope_isolation(graph: dict[str, Any]) -> dict[str, Any]:
    """Verify no two active research nodes share a write_scope path.

    Returns ok=True if all write scopes are isolated, with conflict details
    if any overlap is detected.
    """
    conflicts: list[dict[str, str]] = []
    scope_map: dict[str, str] = {}

    for node in graph.get("nodes", []):
        node_id = node.get("id", "")
        if not node_id.startswith("R"):
            continue
        for scope in node.get("write_scope", []):
            normalized = scope.rstrip("/")
            if normalized in scope_map:
                conflicts.append({
                    "node_a": scope_map[normalized],
                    "node_b": node_id,
                    "conflict_path": scope,
                })
            scope_map[normalized] = node_id

    return {
        "ok": len(conflicts) == 0,
        "checked_nodes": len(scope_map),
        "conflicts": conflicts,
    }
