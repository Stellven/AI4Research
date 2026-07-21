from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acceptance_closeout import auto_closeout_graph_nodes


SPRINT_ID = "sprint-20260510-remote-dispatch-productization"
NODE_ID = "N3"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _run_pytest(runtime_root: Path) -> dict[str, Any]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/graph/test_graph_dispatch_submit.py",
        "tests/graph/test_parent_ready_closeout.py",
        "-q",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(runtime_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "command": " ".join(cmd),
    }


def _ensure_handoff(runtime_root: Path, pytest_result: dict[str, Any]) -> Path:
    handoff_path = runtime_root / "sprints" / f"{SPRINT_ID}.{NODE_ID}-handoff.md"
    content = f"""# Handoff — {SPRINT_ID} / {NODE_ID}

## Summary

Re-verified remote dispatch productization N3 after runtime test drift sync.

- Literal pane input remains in `_send_to_pane`
- Submit ack evidence remains generated
- Send failure still releases lease and requeues node
- Parent closeout still delegates to `parent_ready_check`

## Verification

```text
{pytest_result["command"]}
returncode={pytest_result["returncode"]}
stdout:
{pytest_result["stdout"] or "N/A"}
stderr:
{pytest_result["stderr"] or "N/A"}
```

## Note

This handoff supersedes the earlier false-positive summary that claimed all tests passed before runtime drift was repaired.
"""
    _write_text(handoff_path, content)
    return handoff_path


def _ensure_traceability(runtime_root: Path) -> Path:
    traceability_path = runtime_root / "sprints" / f"{SPRINT_ID}.traceability.json"
    if traceability_path.exists():
        return traceability_path
    traceability_path.write_text(
        json.dumps(
            {
                "sprint_id": SPRINT_ID,
                "generated_at": _now(),
                "nodes": {
                    "N3": {
                        "artifacts": [
                            "lib/graph_node_dispatcher.py",
                            "tests/graph/test_graph_dispatch_submit.py",
                            "tests/graph/test_parent_ready_closeout.py",
                        ],
                        "acceptance": [
                            "literal input and explicit submit timing",
                            "submit ack evidence written",
                            "send failure releases lease and requeues node",
                            "parent sprint closeout gated by parent_ready_check",
                        ],
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return traceability_path


def verify(runtime_root: Path) -> dict[str, Any]:
    pytest_result = _run_pytest(runtime_root)
    handoff_path = _ensure_handoff(runtime_root, pytest_result)
    traceability_path = _ensure_traceability(runtime_root)
    required_paths = [
        runtime_root / "lib" / "graph_node_dispatcher.py",
        runtime_root / "tests" / "graph" / "test_graph_dispatch_submit.py",
        runtime_root / "tests" / "graph" / "test_parent_ready_closeout.py",
        handoff_path,
        traceability_path,
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    ok = pytest_result["returncode"] == 0 and not missing
    return {
        "ok": ok,
        "summary": "Remote dispatch productization N3 closeout based on runtime graph dispatch/parent ready pytest.",
        "pytest": pytest_result,
        "missing_paths": missing,
    }


def _build_eval_payload(verification: dict[str, Any]) -> dict[str, Any]:
    verdict = "PASS" if verification.get("ok") else "FAIL"
    failed_conditions: list[str] = []
    if verification["pytest"]["returncode"] != 0:
        failed_conditions.append("pytest_failed")
    if verification.get("missing_paths"):
        failed_conditions.append("required_artifact_missing")
    return {
        "sprint_id": SPRINT_ID,
        "node_id": NODE_ID,
        "verdict": verdict,
        "summary": verification["summary"],
        "checked_at": _now(),
        "verification": verification,
        "failed_conditions": failed_conditions,
        "schema_version": "solar.eval.v1",
    }


def closeout(runtime_root: Path) -> dict[str, Any]:
    verification = verify(runtime_root)
    graph_path = runtime_root / "sprints" / f"{SPRINT_ID}.task_graph.json"
    eval_json_path = runtime_root / "sprints" / f"{SPRINT_ID}.{NODE_ID}-eval.json"
    return auto_closeout_graph_nodes(
        graph_path=graph_path,
        node_payloads={NODE_ID: _build_eval_payload(verification)},
        eval_json_paths={NODE_ID: eval_json_path},
        reason="remote dispatch productization acceptance auto closeout",
        actor="remote_dispatch_productization_closeout",
        event="remote_dispatch_productization_auto_closeout",
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
