from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acceptance_closeout import auto_closeout_graph_nodes


SPRINT_ID = "sprint-20260525-browser-agent-research-operators"
NODE_IDS = ("N2", "N3", "N4", "N8")

NODE_TESTS: dict[str, list[str]] = {
    "N2": [
        "tests/test_logical_operator_schema.py",
        "tests/test_agent_actor_schema.py",
        "tests/test_schemas.py",
        "tests/test_operator_status_observability.py",
    ],
    "N3": [
        "tests/runtime/test_multi_task_runner_submit_path.py",
        "tests/runtime/test_browser_agent_operator.py",
        "tests/runtime/test_browser_fallback_observability.py",
    ],
    "N4": [
        "tests/runtime/test_browser_security_policies.py",
        "tests/runtime/test_browser_agent_operator.py",
    ],
}
NODE_TESTS["N8"] = [
    *NODE_TESTS["N2"],
    *NODE_TESTS["N3"],
    "tests/runtime/test_browser_security_policies.py",
]

NODE_REQUIRED_PATHS: dict[str, list[str]] = {
    "N2": [
        "config/actor-hosts.json",
        "config/actor-hosts.schema.json",
        "config/agent-actors.json",
        "config/logical-operators.json",
        "config/logical-operators.schema.json",
        "config/physical-operators.json",
    ],
    "N3": [
        "lib/multi_task_runner.py",
        "tests/runtime/test_multi_task_runner_submit_path.py",
        "tests/runtime/test_browser_fallback_observability.py",
    ],
    "N4": [
        "lib/capability_token.py",
        "lib/browser_job_runtime.py",
        "tests/runtime/test_browser_security_policies.py",
    ],
    "N8": [
        "monitor-reports/sprint-20260525-browser-agent-research-operators.md",
        "sprints/sprint-20260525-browser-agent-research-operators.N8-handoff.md",
    ],
}

NODE_SUMMARIES = {
    "N2": "Browser Agent registry/schema/logical-operator config verified against runtime schema suites.",
    "N3": "Async Browser Agent submit/poll/collect path verified via runtime submit-path and observability suites.",
    "N4": "Capability-token policy checks, secret scrubbing, and WAITING_HUMAN surfacing verified by runtime security suites.",
    "N8": "Final browser-agent closeout verified after N2/N3/N4 runtime suites passed and status report was regenerated.",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_pytest(runtime_root: Path, args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *args],
        cwd=str(runtime_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "command": " ".join([sys.executable, "-m", "pytest", "-q", *args]),
    }


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _required_paths(runtime_root: Path, node_id: str) -> list[Path]:
    return [runtime_root / rel for rel in NODE_REQUIRED_PATHS[node_id]]


def _rewrite_node_handoff(runtime_root: Path, node_id: str, verification: dict[str, Any]) -> Path:
    handoff_path = runtime_root / "sprints" / f"{SPRINT_ID}.{node_id}-handoff.md"
    content = f"""# Browser Agent Closeout Handoff — {node_id}

- sprint_id: `{SPRINT_ID}`
- node_id: `{node_id}`
- generated_at: `{_now()}`

## Summary
- {NODE_SUMMARIES[node_id]}

## Verification
- command: `{verification.get("command")}`
- returncode: `{verification.get("returncode")}`

## Required Paths
{chr(10).join(f"- `{path}`" for path in verification.get("required_paths", []))}

## Missing Paths
{chr(10).join(f"- `{path}`" for path in verification.get("missing_paths", [])) or "- none"}
"""
    _write_text(handoff_path, content)
    return handoff_path


def _rewrite_final_report(runtime_root: Path, verification: dict[str, dict[str, Any]]) -> tuple[Path, Path]:
    handoff_path = runtime_root / "sprints" / f"{SPRINT_ID}.N8-handoff.md"
    report_path = runtime_root / "monitor-reports" / f"{SPRINT_ID}.md"
    rows = []
    for node_id in ("N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8"):
        if node_id in verification:
            status = "passed" if verification[node_id]["ok"] else "failed"
            note = verification[node_id]["summary"]
        else:
            status = "passed"
            note = "historical passed node retained"
        rows.append(f"| {node_id} | {status} | {note} |")
    table = "\n".join(rows)
    n8_status = "pending"
    if "N8" in verification:
        n8_status = "passed" if verification["N8"]["ok"] else "failed"
    handoff = f"""# Browser Agent Final Review Handoff

- sprint_id: `{SPRINT_ID}`
- generated_at: `{_now()}`

## Final Status
- N2: `{ 'passed' if verification['N2']['ok'] else 'failed' }`
- N3: `{ 'passed' if verification['N3']['ok'] else 'failed' }`
- N4: `{ 'passed' if verification['N4']['ok'] else 'failed' }`
- N8: `{n8_status}`

## Report
- regenerated from current runtime pytest evidence, replacing stale false-positive handoff text
"""
    report = f"""# Browser Agent Research Operators — Final Verification

| Node | Status | Notes |
|------|--------|-------|
{table}

## Commands
- N2: `{verification['N2']['command']}`
- N3: `{verification['N3']['command']}`
- N4: `{verification['N4']['command']}`
{"- N8: `" + verification["N8"]["command"] + "`" if "N8" in verification else "- N8: `pending verification`"}
"""
    _write_text(handoff_path, handoff)
    _write_text(report_path, report)
    return handoff_path, report_path


def _verify_node(runtime_root: Path, node_id: str) -> dict[str, Any]:
    required_paths = _required_paths(runtime_root, node_id)
    pytest_result = _run_pytest(runtime_root, NODE_TESTS[node_id])
    missing_paths = [str(path) for path in required_paths if not path.exists()]
    result = {
        **pytest_result,
        "required_paths": [str(path) for path in required_paths],
        "missing_paths": missing_paths,
        "summary": NODE_SUMMARIES[node_id],
    }
    result["ok"] = result["returncode"] == 0 and not missing_paths
    return result


def _build_eval_payload(node_id: str, verification: dict[str, Any]) -> dict[str, Any]:
    verdict = "PASS" if verification["ok"] else "FAIL"
    failed_conditions: list[str] = []
    if verification["returncode"] != 0:
        failed_conditions.append("pytest_failed")
    if verification["missing_paths"]:
        failed_conditions.append("required_artifact_missing")
    return {
        "sprint_id": SPRINT_ID,
        "node_id": node_id,
        "round": 1,
        "verdict": verdict,
        "checked_at": _now(),
        "passed_conditions": [
            "runtime_pytest_passed",
            "required_paths_present",
            "handoff_regenerated",
        ] if verdict == "PASS" else [],
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


def auto_closeout_browser_agent_research_operators(runtime_root: Path) -> dict[str, Any]:
    graph_path = runtime_root / "sprints" / f"{SPRINT_ID}.task_graph.json"
    verification = {node_id: _verify_node(runtime_root, node_id) for node_id in ("N2", "N3", "N4")}
    for node_id in ("N2", "N3", "N4"):
        _rewrite_node_handoff(runtime_root, node_id, verification[node_id])
    _rewrite_final_report(runtime_root, verification)
    verification["N8"] = _verify_node(runtime_root, "N8")
    _rewrite_node_handoff(runtime_root, "N8", verification["N8"])
    _rewrite_final_report(runtime_root, verification)

    closeout = auto_closeout_graph_nodes(
        graph_path=graph_path,
        node_payloads={node_id: _build_eval_payload(node_id, payload) for node_id, payload in verification.items()},
        eval_json_paths={node_id: runtime_root / "sprints" / f"{SPRINT_ID}.{node_id}-eval.json" for node_id in verification},
        reason="browser_agent_runtime_verified",
        actor="browser_agent_research_operators_closeout",
        event="browser_agent_research_operators_closeout",
        dispatch_downstream=False,
    )
    return {
        "ok": closeout["ok"],
        "graph_path": str(graph_path),
        "verification": verification,
        "closeout": closeout,
    }
