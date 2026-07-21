from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acceptance_closeout import auto_closeout_graph_nodes


SPRINT_ID = "sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s03-core-runtime"
NODE_IDS = (
    "C1_schema_storage_state",
    "C2_collection_canonical_enrichment",
    "C3_taxonomy_scoring_packet",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_pytest(runtime_root: Path, args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=str(runtime_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "command": " ".join([sys.executable, "-m", "pytest", *args]),
    }


def _verify_node(runtime_root: Path, node_id: str) -> dict[str, Any]:
    harness_root = runtime_root
    base_paths = [
        harness_root / "sprints" / f"{SPRINT_ID}.{node_id}-handoff.md",
    ]
    if node_id == "C1_schema_storage_state":
        pytest_result = _run_pytest(harness_root, ["tests/test_hf_paper_insight_schema.py", "-q"])
        required_paths = base_paths + [
            harness_root / "lib" / "hf_paper_insight" / "schema.py",
            harness_root / "lib" / "hf_paper_insight" / "storage.py",
            harness_root / "lib" / "hf_paper_insight" / "state_machine.py",
            harness_root / "lib" / "hf_paper_insight" / "compat.py",
            harness_root / "tests" / "test_hf_paper_insight_schema.py",
        ]
        summary = "HF S03 C1 closeout based on runtime schema/storage/state-machine pytest."
    elif node_id == "C2_collection_canonical_enrichment":
        pytest_result = _run_pytest(harness_root, ["tests/test_hf_paper_insight_scoring.py", "-q"])
        required_paths = base_paths + [
            harness_root / "lib" / "hf_paper_insight" / "collector.py",
            harness_root / "lib" / "hf_paper_insight" / "canonicalizer.py",
            harness_root / "lib" / "hf_paper_insight" / "providers" / "__init__.py",
            harness_root / "lib" / "hf_paper_insight" / "providers" / "hf_metadata.py",
            harness_root / "lib" / "hf_paper_insight" / "providers" / "arxiv_metadata.py",
            harness_root / "lib" / "hf_paper_insight" / "providers" / "hf_assets.py",
            harness_root / "tests" / "test_hf_paper_insight_scoring.py",
        ]
        summary = "HF S03 C2 closeout based on runtime collection/canonical/enrichment pytest."
    elif node_id == "C3_taxonomy_scoring_packet":
        pytest_result = _run_pytest(harness_root, ["tests/test_hf_paper_insight_scoring.py", "-q"])
        required_paths = base_paths + [
            harness_root / "lib" / "hf_paper_insight" / "taxonomy.py",
            harness_root / "lib" / "hf_paper_insight" / "scoring.py",
            harness_root / "lib" / "hf_paper_insight" / "packet.py",
            harness_root / "tests" / "test_hf_paper_insight_scoring.py",
        ]
        summary = "HF S03 C3 closeout based on runtime taxonomy/scoring/packet pytest."
    else:
        raise ValueError(f"unsupported node: {node_id}")

    missing = [str(path) for path in required_paths if not path.exists()]
    ok = pytest_result["returncode"] == 0 and not missing
    pytest_result.update({"ok": ok, "missing_paths": missing, "summary": summary})
    return pytest_result


def _build_eval_payload(node_id: str, verification: dict[str, Any]) -> dict[str, Any]:
    verdict = "PASS" if verification.get("ok") else "FAIL"
    failed_conditions: list[str] = []
    if verification.get("returncode") != 0:
        failed_conditions.append("pytest_failed")
    if verification.get("missing_paths"):
        failed_conditions.append("required_artifact_missing")
    return {
        "sprint_id": SPRINT_ID,
        "node_id": node_id,
        "round": 1,
        "verdict": verdict,
        "checked_at": _now(),
        "passed_conditions": [
            "runtime_pytest_passed",
            "handoff_and_runtime_artifacts_present",
        ] if verdict == "PASS" else [],
        "failed_conditions": failed_conditions,
        "warnings": [],
        "summary": verification.get("summary"),
        "evidence": {
            "command": verification.get("command"),
            "stdout": verification.get("stdout"),
            "stderr": verification.get("stderr"),
            "missing_paths": verification.get("missing_paths"),
        },
    }


def auto_closeout_hf_s03_nodes(runtime_root: Path, node_ids: tuple[str, ...] = NODE_IDS) -> dict[str, Any]:
    graph_path = runtime_root / "sprints" / f"{SPRINT_ID}.task_graph.json"
    node_payloads: dict[str, dict[str, Any]] = {}
    eval_json_paths: dict[str, Path] = {}
    verification: dict[str, Any] = {}
    for node_id in node_ids:
        verification[node_id] = _verify_node(runtime_root, node_id)
        node_payloads[node_id] = _build_eval_payload(node_id, verification[node_id])
        eval_json_paths[node_id] = runtime_root / "sprints" / f"{SPRINT_ID}.{node_id}-eval.json"
    result = auto_closeout_graph_nodes(
        graph_path=graph_path,
        node_payloads=node_payloads,
        eval_json_paths=eval_json_paths,
        reason="hf_s03_runtime_verified",
        actor="hf_s03_core_runtime_closeout",
        event="hf_s03_core_runtime_closeout",
        dispatch_downstream=False,
    )
    result["verification"] = verification
    return result
