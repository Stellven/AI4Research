from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _child_status(sprints_dir: Path, sid: str) -> str:
    path = sprints_dir / f"{sid}.status.json"
    if not path.exists():
        return ""
    try:
        payload = _load_json(path)
    except Exception:
        return ""
    return str(payload.get("status") or "").lower()


def _sync_graph_from_children(sprints_dir: Path, graph: dict[str, Any]) -> bool:
    changed = False
    for node in graph.get("nodes", []) or []:
        sid = str(node.get("child_sprint_id") or "")
        if not sid:
            continue
        child_state = _child_status(sprints_dir, sid)
        before = str(node.get("status") or "")
        after = before
        if child_state in {"passed", "completed", "eval_passed"}:
            after = "passed"
        elif child_state == "active":
            after = "active"
        elif child_state in {"queued", "drafting"}:
            after = "pending"
        if after != before:
            node["status"] = after
            node["updated_at"] = _now()
            changed = True
    return changed


def close_epic_projection(runtime_root: Path, epic_id: str) -> dict[str, Any]:
    sprints_dir = runtime_root / "sprints"
    graph_path = sprints_dir / f"{epic_id}.task_graph.json"
    epic_meta_path = sprints_dir / f"{epic_id}.epic.json"
    status_path = sprints_dir / f"{epic_id}.status.json"
    if not graph_path.exists() or not epic_meta_path.exists():
        return {
            "ok": False,
            "reason": "missing_epic_artifacts",
            "graph_path": str(graph_path),
            "epic_meta_path": str(epic_meta_path),
        }

    graph = _load_json(graph_path)
    changed = _sync_graph_from_children(sprints_dir, graph)
    _write_json(graph_path, graph)

    all_passed = all(str(node.get("status") or "").lower() == "passed" for node in graph.get("nodes", []))
    epic_meta = _load_json(epic_meta_path)
    status_payload = _load_json(status_path) if status_path.exists() else {
        "id": epic_id,
        "sprint_id": epic_id,
        "title": epic_meta.get("title", epic_id),
        "created_at": epic_meta.get("created_at", _now()),
    }

    hist = status_payload.setdefault("history", [])
    if not isinstance(hist, list):
        hist = []
        status_payload["history"] = hist

    status_payload.update(
        {
            "status": "passed" if all_passed else "active",
            "phase": "completed" if all_passed else "planning_complete",
            "stage": "completed" if all_passed else status_payload.get("stage"),
            "handoff_to": "" if all_passed else status_payload.get("handoff_to", ""),
            "target_role": "" if all_passed else status_payload.get("target_role", ""),
            "active_node": None if all_passed else status_payload.get("active_node"),
            "updated_at": _now(),
            "task_graph": str(graph_path),
            "task_graph_status": "passed" if all_passed else "active",
            "graph_parent_ready": {
                "ok": all_passed,
                "epic_id": epic_id,
                "ready": all_passed,
                "node_count": len(graph.get("nodes", [])),
                "open_nodes": [str(node.get("id")) for node in graph.get("nodes", []) if str(node.get("status") or "").lower() != "passed"],
                "failed_nodes": [],
            },
        }
    )
    hist.append(
        {
            "ts": _now(),
            "event": "epic_projection_closeout",
            "by": "epic_projection_closeout",
            "graph_sync": changed,
            "all_passed": all_passed,
            "graph_path": str(graph_path),
        }
    )
    _write_json(status_path, status_payload)

    epic_meta.update(
        {
            "status": "passed" if all_passed else epic_meta.get("status", "active"),
            "phase": "completed" if all_passed else epic_meta.get("phase"),
            "stage": "completed" if all_passed else epic_meta.get("stage"),
            "updated_at": _now(),
        }
    )
    _write_json(epic_meta_path, epic_meta)
    return {
        "ok": all_passed,
        "graph_path": str(graph_path),
        "status_path": str(status_path),
        "epic_meta_path": str(epic_meta_path),
        "graph_synced": changed,
        "all_passed": all_passed,
        "node_statuses": [(str(node.get("id")), str(node.get("status"))) for node in graph.get("nodes", [])],
    }
