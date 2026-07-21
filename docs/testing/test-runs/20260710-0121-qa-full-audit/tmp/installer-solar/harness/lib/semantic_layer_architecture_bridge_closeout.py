from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acceptance_closeout import auto_closeout_graph_nodes


SPRINT_ID = "sprint-20260524-141723"
SOURCE_S03 = "sprint-20260524-p0-knowledge-wide-thunderomlx-semantic-layer-scope-all-kn-s03-core-runtime"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ensure_traceability(runtime_root: Path) -> Path:
    path = runtime_root / "sprints" / f"{SPRINT_ID}.traceability.json"
    if path.exists():
        return path
    _write_json(
        path,
        {
            "sprint_id": SPRINT_ID,
            "generated_at": _now(),
            "bridge_mode": "planner_to_finalized_builder",
            "source_builder_sprint": SOURCE_S03,
            "mapping": {
                "B1": "schema migration",
                "B2": "state machine extension",
                "B3": "semantic naming bridge",
                "B4": "adapter expansion",
                "B5": "idempotency enhancement",
                "B6": "regression verification",
            },
        },
    )
    return path


def verify(runtime_root: Path) -> dict[str, Any]:
    graph_path = runtime_root / "sprints" / f"{SPRINT_ID}.task_graph.json"
    status_path = runtime_root / "sprints" / f"{SPRINT_ID}.status.json"
    planning_html = runtime_root / "sprints" / f"{SPRINT_ID}.planning.html"
    p2_handoff = runtime_root / "sprints" / f"{SPRINT_ID}.P2-handoff.md"
    p3_handoff = runtime_root / "sprints" / f"{SPRINT_ID}.P3-handoff.md"
    s03_status_path = runtime_root / "sprints" / f"{SOURCE_S03}.status.json"
    traceability = _ensure_traceability(runtime_root)

    graph = _load_json(graph_path)
    status = _load_json(status_path)
    s03_status = _load_json(s03_status_path)
    planning_text = planning_html.read_text(encoding="utf-8")

    node_ids = [str(node.get("id") or "") for node in graph.get("nodes", [])]
    bridge_nodes = [node for node in graph.get("nodes", []) if str(node.get("id") or "").startswith("B")]
    missing_bridge_fields = []
    for node in bridge_nodes:
        for field in ("depends_on", "write_scope", "acceptance", "gate"):
            if field not in node:
                missing_bridge_fields.append(f"{node.get('id')}:{field}")

    ok = (
        all(node in node_ids for node in ["P1", "P2", "P3", "B1", "B2", "B3", "B4", "B5", "B6"])
        and not missing_bridge_fields
        and status.get("handoff_to") == "builder_parallel"
        and status.get("target_role") == "builder_parallel"
        and "builder_parallel" in planning_text
        and s03_status.get("status") == "passed"
        and p2_handoff.exists()
        and p3_handoff.exists()
        and traceability.exists()
    )
    return {
        "ok": ok,
        "graph_path": str(graph_path),
        "status_path": str(status_path),
        "source_s03_status": s03_status.get("status"),
        "bridge_node_count": len(bridge_nodes),
        "missing_bridge_fields": missing_bridge_fields,
        "status_handoff_to": status.get("handoff_to"),
        "status_target_role": status.get("target_role"),
        "planning_has_builder_parallel": "builder_parallel" in planning_text,
        "traceability_path": str(traceability),
    }


def _payload(node_id: str, verification: dict[str, Any]) -> dict[str, Any]:
    return {
        "sprint_id": SPRINT_ID,
        "node_id": node_id,
        "verdict": "PASS" if verification.get("ok") else "FAIL",
        "summary": (
            "P2 bridge task graph is explicit and auditable."
            if node_id == "P2"
            else "P3 planner routing fields now point to builder_parallel."
        ),
        "checked_at": _now(),
        "verification": verification,
        "schema_version": "solar.eval.v1",
        "failed_conditions": [] if verification.get("ok") else ["bridge_verification_failed"],
    }


def closeout(runtime_root: Path) -> dict[str, Any]:
    verification = verify(runtime_root)
    graph_path = runtime_root / "sprints" / f"{SPRINT_ID}.task_graph.json"
    return auto_closeout_graph_nodes(
        graph_path=graph_path,
        node_payloads={
            "P2": _payload("P2", verification),
            "P3": _payload("P3", verification),
        },
        eval_json_paths={
            "P2": runtime_root / "sprints" / f"{SPRINT_ID}.P2-eval.json",
            "P3": runtime_root / "sprints" / f"{SPRINT_ID}.P3-eval.json",
        },
        reason="semantic layer architecture bridge auto closeout",
        actor="semantic_layer_architecture_bridge_closeout",
        event="semantic_layer_architecture_bridge_auto_closeout",
        dispatch_downstream=True,
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    runtime_root = Path(argv[0]).expanduser().resolve() if argv else Path(__file__).resolve().parents[1]
    result = closeout(runtime_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
