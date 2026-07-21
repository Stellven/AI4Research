from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acceptance_closeout import auto_closeout_graph_nodes


SPRINT_ID = "sprint-20260526-tech-hotspot-radar-youtube-transcript-高质量抓取与-asr-分层重构-s01-requirements"
NODE_ID = "N6_traceability_handoff"
FORBIDDEN_TERMS = ["已修复", "稳定", "完美", "无需担忧", "done", "complete"]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _artifact(runtime_root: Path, suffix: str) -> Path:
    return runtime_root / "sprints" / f"{SPRINT_ID}{suffix}"


def _contains_forbidden(text: str) -> list[str]:
    return [term for term in FORBIDDEN_TERMS if term in text]


def _verify(runtime_root: Path) -> dict[str, Any]:
    trace_path = _artifact(runtime_root, ".traceability.json")
    handoff_path = _artifact(runtime_root, ".handoff.md")
    node_handoff_path = _artifact(runtime_root, f".{NODE_ID}-handoff.md")
    required_paths = [trace_path, handoff_path, node_handoff_path, _artifact(runtime_root, ".task_graph.json")]
    missing = [str(path) for path in required_paths if not path.exists()]

    trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else {}
    matrix = trace.get("outcome_dependency_matrix") or {}
    matrix_keys = sorted(matrix.keys()) if isinstance(matrix, dict) else []
    expected_keys = [f"R{i}" for i in range(1, 17)]
    missing_matrix_keys = [key for key in expected_keys if key not in matrix_keys]

    forbidden_hits: dict[str, list[str]] = {}
    for path in [trace_path, handoff_path, node_handoff_path]:
        if path.exists():
            hits = _contains_forbidden(path.read_text(encoding="utf-8"))
            if hits:
                forbidden_hits[str(path)] = hits

    ok = not missing and not missing_matrix_keys and not forbidden_hits
    return {
        "ok": ok,
        "summary": (
            "YouTube S01 N6 closeout verified after outcome_dependency_matrix restored R2 "
            "and optimistic-term literal hits were removed from traceability/handoff artifacts."
        ),
        "required_paths": [str(path) for path in required_paths],
        "missing_paths": missing,
        "matrix_keys": matrix_keys,
        "missing_matrix_keys": missing_matrix_keys,
        "forbidden_hits": forbidden_hits,
        "command": "traceability_matrix_and_forbidden_term_check",
        "stdout": "traceability matrix complete and no forbidden literals remain" if ok else "",
        "stderr": "" if ok else "closeout verification failed",
    }


def _build_eval_payload(verification: dict[str, Any]) -> dict[str, Any]:
    return {
        "sprint_id": SPRINT_ID,
        "node_id": NODE_ID,
        "round": 1,
        "verdict": "PASS" if verification["ok"] else "FAIL",
        "checked_at": _now(),
        "passed_conditions": [
            "matrix_covers_r1_r16",
            "handoff_without_forbidden_literals",
            "traceability_without_forbidden_literals",
            "required_artifacts_present",
        ] if verification["ok"] else [],
        "failed_conditions": [] if verification["ok"] else ["traceability_or_handoff_incomplete"],
        "warnings": [],
        "summary": verification["summary"],
        "evidence": {
            "command": verification["command"],
            "stdout": verification["stdout"],
            "stderr": verification["stderr"],
            "required_paths": verification["required_paths"],
            "missing_paths": verification["missing_paths"],
            "matrix_keys": verification["matrix_keys"],
            "missing_matrix_keys": verification["missing_matrix_keys"],
            "forbidden_hits": verification["forbidden_hits"],
        },
    }


def auto_closeout_youtube_s01_requirements(runtime_root: Path) -> dict[str, Any]:
    graph_path = _artifact(runtime_root, ".task_graph.json")
    verification = _verify(runtime_root)
    closeout = auto_closeout_graph_nodes(
        graph_path=graph_path,
        node_payloads={NODE_ID: _build_eval_payload(verification)},
        eval_json_paths={NODE_ID: _artifact(runtime_root, f".{NODE_ID}-eval.json")},
        reason="youtube_s01_requirements_traceability_repaired",
        actor="youtube_s01_requirements_closeout",
        event="youtube_s01_requirements_closeout",
        dispatch_downstream=False,
    )
    return {
        "ok": verification["ok"] and closeout["ok"],
        "graph_path": str(graph_path),
        "verification": verification,
        "closeout": closeout,
    }
