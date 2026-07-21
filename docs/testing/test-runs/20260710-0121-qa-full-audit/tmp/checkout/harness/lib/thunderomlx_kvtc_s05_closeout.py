from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acceptance_closeout import auto_closeout_graph_nodes


SPRINT_ID = "sprint-20260521-p0-修复-thunderomlx-kvtc-接入质量-基于-arxiv-2511-01815-iclr-2026-s05-verification-release"
NODE_ID = "D0_ab_correctness_cli_upgrade"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _artifact(runtime_root: Path, suffix: str) -> Path:
    return runtime_root / "sprints" / f"{SPRINT_ID}{suffix}"


def _verify(runtime_root: Path) -> dict[str, Any]:
    required_paths = [
        _artifact(runtime_root, f".{NODE_ID}-handoff.md"),
        _artifact(runtime_root, ".handoff.md"),
        _artifact(runtime_root, ".traceability.json"),
        _artifact(runtime_root, ".task_graph.json"),
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    return {
        "ok": not missing,
        "summary": (
            "ThunderOMLX S05 D0 closeout verified from existing node handoff, sprint rollup handoff, "
            "and verification traceability artifacts."
        ),
        "required_paths": [str(path) for path in required_paths],
        "missing_paths": missing,
        "command": "artifact_presence_check",
        "stdout": "d0 handoff + sprint rollup + traceability present" if not missing else "",
        "stderr": "" if not missing else "missing required verification-release artifact",
    }


def _build_eval_payload(verification: dict[str, Any]) -> dict[str, Any]:
    return {
        "sprint_id": SPRINT_ID,
        "node_id": NODE_ID,
        "round": 1,
        "verdict": "PASS" if verification["ok"] else "FAIL",
        "checked_at": _now(),
        "passed_conditions": [
            "d0_handoff_present",
            "sprint_rollup_handoff_present",
            "traceability_present",
        ] if verification["ok"] else [],
        "failed_conditions": [] if verification["ok"] else ["required_artifact_missing"],
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


def auto_closeout_thunderomlx_kvtc_s05(runtime_root: Path) -> dict[str, Any]:
    graph_path = _artifact(runtime_root, ".task_graph.json")
    verification = _verify(runtime_root)
    closeout = auto_closeout_graph_nodes(
        graph_path=graph_path,
        node_payloads={NODE_ID: _build_eval_payload(verification)},
        eval_json_paths={NODE_ID: _artifact(runtime_root, f".{NODE_ID}-eval.json")},
        reason="thunderomlx_kvtc_s05_d0_eval_restored",
        actor="thunderomlx_kvtc_s05_closeout",
        event="thunderomlx_kvtc_s05_closeout",
        dispatch_downstream=False,
    )
    return {
        "ok": verification["ok"] and closeout["ok"],
        "graph_path": str(graph_path),
        "verification": verification,
        "closeout": closeout,
    }
