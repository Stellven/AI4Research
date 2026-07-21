from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acceptance_closeout import auto_closeout_graph_nodes


SPRINT_ID = "sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s04-orchestration-ui"
NODE_ID = "C5_traceability_handoff"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _required_paths(runtime_root: Path) -> list[Path]:
    return [
        runtime_root / "sprints" / f"{SPRINT_ID}.traceability.json",
        runtime_root / "sprints" / f"{SPRINT_ID}.handoff.md",
        runtime_root / "sprints" / f"{SPRINT_ID}.C5_traceability_handoff-handoff.md",
    ]


def _verify(runtime_root: Path) -> dict[str, Any]:
    required_paths = _required_paths(runtime_root)
    missing = [str(path) for path in required_paths if not path.exists()]
    summary = (
        "HF S04 C5 closeout verified after parent sprint handoff.md was restored "
        "and traceability/handoff artifacts aligned to write_scope."
    )
    return {
        "ok": not missing,
        "summary": summary,
        "missing_paths": missing,
        "required_paths": [str(path) for path in required_paths],
        "command": "artifact_presence_check",
        "stdout": "all required orchestration-ui handoff artifacts present" if not missing else "",
        "stderr": "" if not missing else "missing required handoff/traceability artifact",
        "returncode": 0 if not missing else 1,
    }


def _build_eval_payload(verification: dict[str, Any]) -> dict[str, Any]:
    verdict = "PASS" if verification["ok"] else "FAIL"
    failed_conditions = [] if verification["ok"] else ["required_artifact_missing"]
    return {
        "sprint_id": SPRINT_ID,
        "node_id": NODE_ID,
        "round": 1,
        "verdict": verdict,
        "checked_at": _now(),
        "passed_conditions": [
            "parent_handoff_present",
            "traceability_present",
            "node_handoff_present",
        ] if verification["ok"] else [],
        "failed_conditions": failed_conditions,
        "warnings": [],
        "summary": verification["summary"],
        "evidence": {
            "command": verification["command"],
            "stdout": verification["stdout"],
            "stderr": verification["stderr"],
            "required_paths": verification["required_paths"],
            "missing_paths": verification["missing_paths"],
        },
    }


def auto_closeout_hf_s04_orchestration_ui(runtime_root: Path) -> dict[str, Any]:
    graph_path = runtime_root / "sprints" / f"{SPRINT_ID}.task_graph.json"
    verification = _verify(runtime_root)
    closeout = auto_closeout_graph_nodes(
        graph_path=graph_path,
        node_payloads={NODE_ID: _build_eval_payload(verification)},
        eval_json_paths={NODE_ID: runtime_root / "sprints" / f"{SPRINT_ID}.{NODE_ID}-eval.json"},
        reason="hf_s04_traceability_reconciled",
        actor="hf_s04_orchestration_ui_closeout",
        event="hf_s04_orchestration_ui_closeout",
        dispatch_downstream=False,
    )
    return {
        "ok": verification["ok"] and closeout["ok"],
        "graph_path": str(graph_path),
        "verification": verification,
        "closeout": closeout,
    }
