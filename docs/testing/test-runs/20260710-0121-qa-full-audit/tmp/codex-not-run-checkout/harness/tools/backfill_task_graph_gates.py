#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

import graph_scheduler as gs  # noqa: E402


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _required_gates(graph: dict[str, Any]) -> list[str]:
    return [str(gate) for gate in (graph.get("required_gates") or []) if gate]


def _nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return [node for node in (graph.get("nodes") or []) if isinstance(node, dict)]


def _gate_owners(graph: dict[str, Any]) -> dict[str, list[str]]:
    owners = {gate: [] for gate in _required_gates(graph)}
    for node in _nodes(graph):
        gate = str(node.get("gate") or "")
        node_id = str(node.get("id") or "")
        if gate in owners and node_id:
            owners[gate].append(node_id)
    return owners


def _missing_required_gates(graph: dict[str, Any]) -> list[str]:
    owners = _gate_owners(graph)
    return [gate for gate in _required_gates(graph) if not owners.get(gate)]


def _topo_order_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    ids = {str(node.get("id") or ""): node for node in _nodes(graph)}
    try:
        order = gs.topo_order(graph)
        return [ids[node_id] for node_id in order if node_id in ids]
    except Exception:
        return _nodes(graph)


def _apply_sequential_gate_fill(graph: dict[str, Any]) -> list[dict[str, str]]:
    missing = _missing_required_gates(graph)
    if not missing:
        return []
    ordered_nodes = [node for node in _topo_order_nodes(graph) if not node.get("gate")]
    changes: list[dict[str, str]] = []
    for gate, node in zip(missing, ordered_nodes):
        node["gate"] = gate
        changes.append({
            "node": str(node.get("id") or ""),
            "gate": gate,
            "strategy": "sequential_required_gate_fill",
        })
    return changes


def _desired_gate_result(graph: dict[str, Any], gate: str) -> dict[str, Any] | None:
    owners = _gate_owners(graph).get(gate, [])
    if not owners:
        return None
    statuses = {node_id: gs.node_status(graph, node_id) for node_id in owners}
    updated_at = _now_iso()
    for node_id in owners:
        status = statuses.get(node_id, "")
        if status in {"failed", "cancelled"}:
            return {
                "status": "blocked",
                "node": node_id,
                "reason": f"node_{status}",
                "updated_at": updated_at,
            }
    open_nodes = [node_id for node_id in owners if statuses.get(node_id) != "passed"]
    if open_nodes:
        return {
            "status": "blocked",
            "node": open_nodes[0],
            "reason": "waiting_for_shared_gate_nodes",
            "open_nodes": open_nodes,
            "updated_at": updated_at,
        }
    return {
        "status": "passed",
        "node": owners[-1],
        "updated_at": updated_at,
    }


def _gate_result_needs_update(current: dict[str, Any] | None, desired: dict[str, Any]) -> bool:
    if not isinstance(current, dict):
        return True
    for key in ("status", "node", "reason"):
        if current.get(key) != desired.get(key):
            return True
    current_open = list(current.get("open_nodes") or [])
    desired_open = list(desired.get("open_nodes") or [])
    return current_open != desired_open


def _rebuild_gate_results(graph: dict[str, Any]) -> list[dict[str, Any]]:
    graph.setdefault("gate_results", {})
    changes: list[dict[str, Any]] = []
    for gate in _required_gates(graph):
        desired = _desired_gate_result(graph, gate)
        if desired is None:
            continue
        current = graph["gate_results"].get(gate)
        if not _gate_result_needs_update(current, desired):
            continue
        graph["gate_results"][gate] = desired
        changes.append({"gate": gate, "result": desired["status"], "node": desired.get("node", "")})
    return changes


def backfill_graph(path: Path, *, persist: bool = True) -> dict[str, Any]:
    graph = _read_json(path)
    required = _required_gates(graph)
    if not required:
        return {
            "graph": str(path),
            "changed": False,
            "required_gates": 0,
            "assigned": [],
            "gate_results_repaired": [],
            "missing_before": [],
            "missing_after": [],
            "graph_payload": graph,
        }

    before_missing = _missing_required_gates(graph)
    before_snapshot = json.dumps(graph, ensure_ascii=False, sort_keys=True)
    assigned = gs._ensure_required_gate_node_mapping(graph)  # type: ignore[attr-defined]
    auto_assigned: list[dict[str, str]] = []
    if assigned:
        owners_after_auto = _gate_owners(graph)
        for gate in required:
            for node_id in owners_after_auto.get(gate, []):
                auto_assigned.append({"node": node_id, "gate": gate, "strategy": "default_runtime_mapping"})
    fallback_assigned = _apply_sequential_gate_fill(graph)
    gate_repairs = _rebuild_gate_results(graph)
    after_missing = _missing_required_gates(graph)
    after_snapshot = json.dumps(graph, ensure_ascii=False, sort_keys=True)
    changed = before_snapshot != after_snapshot
    if changed and persist:
        _write_json(path, graph)
    return {
        "graph": str(path),
        "changed": changed,
        "required_gates": len(required),
        "assigned": auto_assigned + fallback_assigned,
        "gate_results_repaired": gate_repairs,
        "missing_before": before_missing,
        "missing_after": after_missing,
        "graph_payload": graph,
    }


def _write_markdown_report(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Task Graph Gate Backfill Audit",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- sprints_dir: {payload['sprints_dir']}",
        f"- graphs_scanned: {payload['graphs_scanned']}",
        f"- graphs_with_required_gates: {payload['graphs_with_required_gates']}",
        f"- graphs_changed: {payload['graphs_changed']}",
        f"- graphs_unresolved: {payload['graphs_unresolved']}",
        f"- backup_dir: {payload['backup_dir'] or 'N/A'}",
        "",
    ]
    if payload["changed_items"]:
        lines.extend([
            "## Changed Graphs",
            "",
            "| graph | assigned | gate_results_repaired | missing_after |",
            "| --- | ---: | ---: | --- |",
        ])
        for item in payload["changed_items"]:
            lines.append(
                f"| {Path(item['graph']).name} | {len(item['assigned'])} | {len(item['gate_results_repaired'])} | "
                f"{', '.join(item['missing_after']) if item['missing_after'] else 'none'} |"
            )
        lines.append("")
    if payload["unresolved_items"]:
        lines.extend([
            "## Unresolved Graphs",
            "",
            "| graph | missing_after |",
            "| --- | --- |",
        ])
        for item in payload["unresolved_items"]:
            lines.append(f"| {Path(item['graph']).name} | {', '.join(item['missing_after'])} |")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit and backfill task_graph gate ownership for legacy sprint graphs.")
    ap.add_argument("--sprints-dir", default=str(Path.home() / ".solar" / "harness" / "sprints"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sprints_dir = Path(args.sprints_dir).expanduser().resolve()
    if not sprints_dir.exists():
        raise SystemExit(f"sprints dir not found: {sprints_dir}")

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reports_dir = sprints_dir.parent / "reports"
    backup_dir = sprints_dir.parent / "state" / "task-graph-gate-backfill-backups" / stamp
    reports_dir.mkdir(parents=True, exist_ok=True)
    if not args.dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for graph_path in sorted(sprints_dir.glob("*.task_graph.json")):
        graph = _read_json(graph_path)
        if not _required_gates(graph):
            continue
        before = graph_path.read_text(encoding="utf-8")
        result = backfill_graph(graph_path, persist=False)
        if result["changed"] and not args.dry_run:
            (backup_dir / graph_path.name).write_text(before, encoding="utf-8")
            _write_json(graph_path, result["graph_payload"])
        result.pop("graph_payload", None)
        results.append(result)

    changed_items = [item for item in results if item["changed"]]
    unresolved_items = [item for item in results if item["missing_after"]]
    payload = {
        "ok": not unresolved_items,
        "generated_at": _now_iso(),
        "sprints_dir": str(sprints_dir),
        "graphs_scanned": len(list(sprints_dir.glob("*.task_graph.json"))),
        "graphs_with_required_gates": len(results),
        "graphs_changed": len(changed_items),
        "graphs_unresolved": len(unresolved_items),
        "backup_dir": "" if args.dry_run or not changed_items else str(backup_dir),
        "dry_run": bool(args.dry_run),
        "changed_items": changed_items,
        "unresolved_items": unresolved_items,
        "results": results,
    }
    json_report = reports_dir / f"task-graph-gate-backfill-audit-{stamp}.json"
    md_report = reports_dir / f"task-graph-gate-backfill-audit-{stamp}.md"
    payload["json_report"] = str(json_report)
    payload["markdown_report"] = str(md_report)
    _write_json(json_report, payload)
    _write_markdown_report(md_report, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
