"""Workflow selection helpers for Solar-owned research orchestration."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class WorkflowSelectionError(ValueError):
    """Raised when workflow selection cannot be resolved safely."""


REQUIRED_NORMALIZED_FIELDS = {
    "node_id",
    "depends_on",
    "required_for_completion",
    "logical_operator",
    "required_capabilities",
    "read_scope",
    "write_scope",
    "gate",
}


def load_workflow_selection(path: Path) -> dict:
    """Load and minimally validate a research workflow selection config."""

    payload = _load_json_object(path)
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        raise WorkflowSelectionError("workflow selection config requires non-empty routes")
    seen: set[str] = set()
    for route in routes:
        if not isinstance(route, dict):
            raise WorkflowSelectionError("workflow selection routes must be objects")
        workflow_kind = _required_text(route, "workflow_kind")
        _required_text(route, "workflow_id")
        _required_text(route, "workflow_path")
        _required_text(route, "start_node")
        if workflow_kind in seen:
            raise WorkflowSelectionError(f"duplicate workflow_kind route: {workflow_kind}")
        seen.add(workflow_kind)
    return payload


def select_research_workflow(
    classification: dict,
    selection: dict,
    harness_root: Path,
) -> dict:
    """Select a workflow route for a classified research task."""

    if not isinstance(classification, dict):
        raise WorkflowSelectionError("classification must be an object")
    workflow_kind = _required_text(classification, "workflow_kind")
    routes = selection.get("routes")
    if not isinstance(routes, list):
        raise WorkflowSelectionError("selection routes must be a list")

    route = next(
        (item for item in routes if isinstance(item, dict) and item.get("workflow_kind") == workflow_kind),
        None,
    )
    if route is None:
        raise WorkflowSelectionError(f"no workflow route for workflow_kind: {workflow_kind}")

    root = harness_root.resolve()
    workflow_path = _resolve_under(root, str(route["workflow_path"]))
    return {
        "workflow_kind": workflow_kind,
        "workflow_id": str(route["workflow_id"]),
        "workflow_path": str(workflow_path),
        "start_node": str(route["start_node"]),
        "classification": deepcopy(classification),
    }


def load_and_normalize_workflow(
    selection_result: dict,
    harness_root: Path,
    *,
    preserve_all_nodes: bool = False,
) -> dict:
    """Load and normalize a workflow, optionally retaining every entry root."""

    if not isinstance(selection_result, dict):
        raise WorkflowSelectionError("selection_result must be an object")
    root = harness_root.resolve()
    workflow_path = _resolve_under(root, _required_text(selection_result, "workflow_path"))
    payload = _load_json_object(workflow_path)
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise WorkflowSelectionError("selected workflow must contain non-empty nodes")

    normalized_all = [_normalize_node(node) for node in raw_nodes]
    by_id: dict[str, dict[str, Any]] = {}
    for node in normalized_all:
        node_id = node["node_id"]
        if node_id in by_id:
            raise WorkflowSelectionError(f"duplicate workflow node: {node_id}")
        by_id[node_id] = node
    for node in normalized_all:
        for dep in node["depends_on"]:
            if dep not in by_id:
                raise WorkflowSelectionError(f"{node['node_id']} depends on missing node {dep}")

    start_node = _required_text(selection_result, "start_node")
    if start_node not in by_id:
        raise WorkflowSelectionError(f"unknown start node: {start_node}")
    _assert_acyclic(by_id)

    selected_ids = set(by_id) if preserve_all_nodes else _descendants_from(start_node, by_id)
    selected_nodes: list[dict[str, Any]] = []
    for node in normalized_all:
        if node["node_id"] not in selected_ids:
            continue
        item = deepcopy(node)
        item["depends_on"] = [dep for dep in item["depends_on"] if dep in selected_ids]
        selected_nodes.append(item)

    return {
        "workflow_id": str(selection_result.get("workflow_id") or payload.get("workflow_id") or workflow_path.stem),
        "version": payload.get("version") or payload.get("schema_version") or "unavailable",
        "workflow_kind": str(selection_result.get("workflow_kind") or payload.get("workflow_kind") or ""),
        "workflow_path": str(workflow_path),
        "start_node": start_node,
        "nodes": selected_nodes,
    }


def _load_json_object(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkflowSelectionError(f"invalid JSON at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise WorkflowSelectionError(f"JSON object expected at {path}")
    return payload


def _required_text(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WorkflowSelectionError(f"{key} must be a non-empty string")
    return value.strip()


def _resolve_under(root: Path, raw: str) -> Path:
    path = Path(raw)
    resolved = (path if path.is_absolute() else root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkflowSelectionError(f"path escapes harness root: {raw}") from exc
    return resolved


def _normalize_node(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise WorkflowSelectionError("workflow nodes must be objects")
    node_id = raw.get("node_id") or raw.get("id")
    if not isinstance(node_id, str) or not node_id.strip():
        raise WorkflowSelectionError("workflow node requires id or node_id")
    node_id = node_id.strip()
    depends_on = raw.get("depends_on") or []
    if not isinstance(depends_on, list):
        raise WorkflowSelectionError(f"{node_id}.depends_on must be a list")

    permission = raw.get("permission_profile") if isinstance(raw.get("permission_profile"), dict) else {}
    gate_contract = raw.get("gate_contract") if isinstance(raw.get("gate_contract"), dict) else {}
    retry_policy = raw.get("retry_policy") if isinstance(raw.get("retry_policy"), dict) else {}
    read_scope = raw.get("read_scope", permission.get("read_scope", raw.get("input_artifacts", [])))
    write_scope = raw.get("write_scope", permission.get("write_scope", raw.get("output_artifacts", [])))
    gate = raw.get("gate") or gate_contract.get("gate") or f"G_{node_id.upper()}"

    node = {
        "node_id": node_id,
        "depends_on": [str(dep).strip() for dep in depends_on if str(dep).strip()],
        "required_for_completion": bool(raw.get("required_for_completion", True)),
        "logical_operator": str(raw.get("logical_operator") or node_id),
        "required_capabilities": _string_list(raw.get("required_capabilities", [])),
        "read_scope": _string_list(read_scope),
        "write_scope": _string_list(write_scope),
        "expected_output_artifacts": _string_list(raw.get("output_artifacts", [])),
        "gate_deliverable": str(gate_contract.get("deliverable") or ""),
        "gate": str(gate),
        "physical_operator": str(_first(permission.get("approved_operators")) or raw.get("physical_operator") or f"{node_id}_worker"),
        "allow_network": bool((permission.get("network") or {}).get("enabled", False)) if isinstance(permission.get("network"), dict) else False,
        "allow_live_provider": bool(permission.get("provider_execution", False)),
        "approval_gate": bool(raw.get("approval_gate", False)),
        "timeout_seconds": int(raw.get("timeout_seconds") or retry_policy.get("timeout_seconds") or 60),
        "max_attempts": int(raw.get("max_attempts") or retry_policy.get("max_attempts") or 1),
    }
    missing = REQUIRED_NORMALIZED_FIELDS - set(node)
    if missing:
        raise WorkflowSelectionError(f"{node_id} missing normalized fields: {sorted(missing)}")
    return node


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _first(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return ""


def _assert_acyclic(nodes: dict[str, dict[str, Any]]) -> None:
    indegree = {node_id: 0 for node_id in nodes}
    outgoing = {node_id: [] for node_id in nodes}
    for node_id, node in nodes.items():
        for dep in node["depends_on"]:
            indegree[node_id] += 1
            outgoing[dep].append(node_id)
    queue = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    seen: list[str] = []
    while queue:
        node_id = queue.pop(0)
        seen.append(node_id)
        for child in sorted(outgoing[node_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
                queue.sort()
    if len(seen) != len(nodes):
        cycle_nodes = sorted(node_id for node_id, degree in indegree.items() if degree > 0)
        raise WorkflowSelectionError("cycle detected: " + ", ".join(cycle_nodes))


def _descendants_from(start_node: str, nodes: dict[str, dict[str, Any]]) -> set[str]:
    outgoing = {node_id: [] for node_id in nodes}
    for node_id, node in nodes.items():
        for dep in node["depends_on"]:
            outgoing[dep].append(node_id)
    selected = {start_node}
    queue = [start_node]
    while queue:
        node_id = queue.pop(0)
        for child in sorted(outgoing[node_id]):
            if child not in selected:
                selected.add(child)
                queue.append(child)
    return selected
