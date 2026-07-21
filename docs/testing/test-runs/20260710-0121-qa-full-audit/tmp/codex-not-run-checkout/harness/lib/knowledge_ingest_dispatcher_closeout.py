from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acceptance_closeout import auto_closeout_graph_nodes


SPRINT_ID = "sprint-20260524-105859"
NODE_ID = "N2_dispatcher_cli"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(runtime_root: Path, args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        args,
        cwd=str(runtime_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "command": " ".join(args),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ensure_traceability(runtime_root: Path) -> Path:
    traceability_path = runtime_root / "sprints" / f"{SPRINT_ID}.traceability.json"
    if traceability_path.exists():
        return traceability_path
    _write_json(
        traceability_path,
        {
            "sprint_id": SPRINT_ID,
            "generated_at": _now(),
            "nodes": {
                "N1_registry": {
                    "artifacts": ["lib/knowledge_ingest_registry.py", "tests/test-knowledge-ingest-registry.sh"],
                },
                "N2_dispatcher_cli": {
                    "artifacts": [
                        "lib/knowledge_ingest_dispatcher.py",
                        "solar-harness.sh",
                        "tests/test-knowledge-ingest-dispatcher.sh",
                    ],
                    "acceptance": [
                        "solar-harness wiki knowledge-ingest status --json exits 0",
                        "submit-event writes registry row",
                    ],
                },
                "N3_adapters_spans": {"artifacts": ["lib/knowledge_ingest_dispatcher.py", "tests/test-knowledge-spans.sh"]},
                "N4_json_extractor_renderer": {"artifacts": ["lib/knowledge_json_extract.py", "lib/knowledge_dashboard.py"]},
                "N5_validator_repair_quarantine": {"artifacts": ["lib/knowledge_ingest_validate.py", "lib/knowledge_ingest_repair.py"]},
                "N6_qmd_microbatch": {"artifacts": ["lib/qmd_microbatch.py"]},
                "N7_circuit_health": {"artifacts": ["lib/knowledge_ingest_health.py"]},
                "N8_sample_backfill_eval": {"artifacts": ["tests/test_knowledge_v2.py"]},
            },
        },
    )
    return traceability_path


def verify(runtime_root: Path) -> dict[str, Any]:
    shell = runtime_root / "solar-harness.sh"
    dispatcher_test = runtime_root / "tests" / "test-knowledge-ingest-dispatcher.sh"
    traceability = _ensure_traceability(runtime_root)
    status_result = _run(runtime_root, ["bash", str(shell), "wiki", "knowledge-ingest", "status", "--json"])
    dispatcher_result = _run(runtime_root, ["bash", str(dispatcher_test)])
    required_paths = [
        runtime_root / "lib" / "knowledge_ingest_dispatcher.py",
        runtime_root / "solar-harness.sh",
        runtime_root / "tests" / "test-knowledge-ingest-dispatcher.sh",
        traceability,
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    ok = (
        status_result["returncode"] == 0
        and dispatcher_result["returncode"] == 0
        and not missing
    )
    return {
        "ok": ok,
        "summary": "Knowledge ingest dispatcher closeout based on shell routing status check and dispatcher test suite.",
        "status_result": status_result,
        "dispatcher_result": dispatcher_result,
        "missing_paths": missing,
    }


def build_eval_payload(verification: dict[str, Any]) -> dict[str, Any]:
    verdict = "PASS" if verification.get("ok") else "FAIL"
    failed_conditions: list[str] = []
    if verification["status_result"]["returncode"] != 0:
        failed_conditions.append("wiki_shell_routing_failed")
    if verification["dispatcher_result"]["returncode"] != 0:
        failed_conditions.append("dispatcher_test_failed")
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
    eval_json_path = runtime_root / "sprints" / f"{SPRINT_ID}.{NODE_ID}-eval.json"
    graph_path = runtime_root / "sprints" / f"{SPRINT_ID}.task_graph.json"
    return auto_closeout_graph_nodes(
        graph_path=graph_path,
        node_payloads={NODE_ID: build_eval_payload(verification)},
        eval_json_paths={NODE_ID: eval_json_path},
        reason="knowledge ingest dispatcher acceptance auto closeout",
        actor="knowledge_ingest_dispatcher_closeout",
        event="knowledge_ingest_dispatcher_auto_closeout",
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
