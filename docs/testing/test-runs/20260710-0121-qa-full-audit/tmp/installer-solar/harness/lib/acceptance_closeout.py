"""Generic acceptance closeout helpers for sprint graph/status synchronization."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_eval_sidecar(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def existing_graph_node_status(graph_path: Path, node_id: str) -> str:
    graph = load_json(graph_path)
    for node in graph.get("nodes", []):
        if str(node.get("id") or "") == node_id:
            return str(node.get("status") or "")
    return ""


def invoke_node_verdict(
    *,
    graph_path: Path,
    node_id: str,
    eval_json_path: Path,
    reason: str,
    dispatch_downstream: bool = False,
) -> dict[str, Any]:
    from graph_node_dispatcher import node_verdict  # noqa: WPS433

    return node_verdict(
        str(graph_path),
        node_id,
        "pass",
        reason=reason,
        eval_json=str(eval_json_path),
        dispatch_downstream=dispatch_downstream,
    )


def invoke_status_sync(
    *,
    graph_path: Path,
    actor: str,
    event: str,
) -> dict[str, Any]:
    from graph_scheduler import load_graph, sync_status_cache_from_graph  # noqa: WPS433

    graph = load_graph(graph_path)
    return sync_status_cache_from_graph(
        graph,
        graph_path=graph_path,
        actor=actor,
        event=event,
    )


def auto_closeout_graph_nodes(
    *,
    graph_path: Path,
    node_payloads: dict[str, dict[str, Any]],
    eval_json_paths: dict[str, Path],
    reason: str,
    actor: str,
    event: str,
    dispatch_downstream: bool = False,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for node_id, payload in node_payloads.items():
        eval_json_path = write_eval_sidecar(eval_json_paths[node_id], payload)
        current_status = existing_graph_node_status(graph_path, node_id)
        verdict = str(payload.get("verdict") or "").upper()
        if verdict != "PASS":
            results[node_id] = {
                "ok": False,
                "status": current_status or "blocked",
                "eval_json": str(eval_json_path),
                "reason": "eval_verdict_fail",
            }
            continue
        if current_status == "passed":
            results[node_id] = {
                "ok": True,
                "status": "passed",
                "eval_json": str(eval_json_path),
                "reason": "already_passed",
            }
            continue
        results[node_id] = invoke_node_verdict(
            graph_path=graph_path,
            node_id=node_id,
            eval_json_path=eval_json_path,
            reason=reason,
            dispatch_downstream=dispatch_downstream,
        )
        results[node_id]["eval_json"] = str(eval_json_path)
    sync = invoke_status_sync(graph_path=graph_path, actor=actor, event=event)
    return {
        "ok": all(bool(item.get("ok")) for item in results.values()) and bool(sync.get("ok")),
        "graph_path": str(graph_path),
        "node_results": results,
        "status_sync": sync,
    }
