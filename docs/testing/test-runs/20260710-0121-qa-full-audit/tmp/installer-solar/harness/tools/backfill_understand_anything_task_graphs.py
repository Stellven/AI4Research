#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

import capability_capsules as cc  # noqa: E402


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _backfill_node(node: dict[str, Any], *, registry_path: Path) -> bool:
    logical_operator = str(node.get("logical_operator") or "")
    goal = str(node.get("goal") or node.get("title") or node.get("description") or "")
    plan = cc.default_capability_plan_for_logical_operator(
        logical_operator,
        request_type="research" if logical_operator in {"ResearchScout", "ResearchSynthesizer", "ArtifactCurator"} else "implementation",
        lane_hint=str(node.get("lane") or node.get("owner") or ""),
        node=node,
        registry_path=registry_path,
    )
    if plan.get("capability_capsule_id") != "cap.understand-anything-indexer":
        return False

    changed = False
    if node.get("type") != "code-understanding":
        node["type"] = "code-understanding"
        changed = True
    if node.get("dispatch_task_type") != "code-understanding":
        node["dispatch_task_type"] = "code-understanding"
        changed = True
    if node.get("capability_capsule_id") != "cap.understand-anything-indexer":
        node["capability_capsule_id"] = "cap.understand-anything-indexer"
        changed = True
    signals = set(str(x) for x in (node.get("signals") or []))
    desired_signals = {"code-understanding", "knowledge-graph", "onboarding", "architecture-map"}
    if not desired_signals.issubset(signals):
        node["signals"] = sorted(signals | desired_signals)
        changed = True
    desired_outputs = ["knowledge-graph.json", "meta.json", "chunk-manifest.json", "resume-state.json"]
    if node.get("outputs") != desired_outputs:
        node["outputs"] = desired_outputs
        changed = True
    desired_validation = [
        {"kind": "artifact", "target": "knowledge-graph.json", "required": True},
        {"kind": "artifact", "target": "meta.json", "required": True},
        {"kind": "artifact", "target": "chunk-manifest.json", "required": True},
        {"kind": "artifact", "target": "resume-state.json", "required": True},
    ]
    if node.get("validation") != desired_validation:
        node["validation"] = desired_validation
        changed = True
    if goal and node.get("goal") != goal:
        node["goal"] = goal
    return changed


def backfill_graph(path: Path, *, registry_path: Path) -> dict[str, Any]:
    graph = _read_json(path)
    changed_nodes: list[str] = []
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        if _backfill_node(node, registry_path=registry_path):
            changed_nodes.append(str(node.get("id") or ""))
    if changed_nodes:
        _write_json(path, graph)
    return {"graph": str(path), "changed": bool(changed_nodes), "nodes": changed_nodes}


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill understand-anything code-understanding semantics into task_graph nodes.")
    ap.add_argument("--sprints-dir", required=True)
    ap.add_argument("--registry", default=str(ROOT / "config" / "capability-capsules.registry.yaml"))
    args = ap.parse_args()
    sprints_dir = Path(args.sprints_dir).expanduser().resolve()
    registry_path = Path(args.registry).expanduser().resolve()
    results = []
    for graph_path in sorted(sprints_dir.glob("*.task_graph.json")):
        results.append(backfill_graph(graph_path, registry_path=registry_path))
    changed = [item for item in results if item["changed"]]
    print(json.dumps({"ok": True, "graphs_scanned": len(results), "graphs_changed": len(changed), "changed": changed}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
