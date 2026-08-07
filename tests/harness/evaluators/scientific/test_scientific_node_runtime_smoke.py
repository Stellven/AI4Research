from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


HARNESS = (Path(__file__).resolve().parents[4] / 'harness')
SMOKE = HARNESS / "tools" / "run_scientific_node_smoke.py"


def _prepare_isolated_harness(tmp_path: Path) -> Path:
    for name in ("config", "personas", "tools", "plugins", "evaluators", "schemas", "lib", "templates"):
        target = HARNESS / name
        link = tmp_path / name
        if not link.exists():
            link.symlink_to(target, target_is_directory=True)
    (tmp_path / "run").mkdir(exist_ok=True)
    (tmp_path / "artifacts").mkdir(exist_ok=True)
    return tmp_path


def test_scientific_paper_ingest_node_dispatches_through_operator_runtime(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    env = os.environ.copy()
    env["HARNESS_DIR"] = str(harness_dir)
    env["SOLAR_OPERATORD_ONCE_MAX_WAIT_SECONDS"] = "20"
    proc = subprocess.run(
        [
            sys.executable,
            str(SMOKE),
            "--harness-dir",
            str(harness_dir),
            "--task-id",
            "task-scientific-node-smoke-test",
            "--sprint-id",
            "sprint-scientific-node-smoke-test",
            "--timeout-seconds",
            "20",
            "--out",
            "artifacts/scientific/scheduler-node-smoke/task-scientific-node-smoke-test/summary.json",
        ],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["status"] == "passed"
    assert summary["operator_id"] == "autosci-paper-ingest-worker"
    assert summary["logical_operator"] == "ScientificPaperIngestor"
    assert summary["action"] == "ingest_paper"
    assert {item["status"] for item in summary["checks"]} == {"ok"}

    operator_result = harness_dir / summary["operator_result_path"]
    bridge_result = harness_dir / summary["bridge_result_path"]
    evidence = harness_dir / summary["evidence_path"]
    materialized_envelope = harness_dir / summary["materialized_envelope_path"]
    output_log = harness_dir / summary["output_log_path"]

    assert operator_result.exists()
    assert bridge_result.exists()
    assert evidence.exists()
    assert materialized_envelope.exists()
    assert output_log.exists()

    operator_payload = json.loads(operator_result.read_text(encoding="utf-8"))
    assert operator_payload["status"] == "completed"
    assert operator_payload["exit_code"] == 0
    assert operator_payload["node_id"] == "paper_ingest"

    envelope = json.loads(materialized_envelope.read_text(encoding="utf-8"))
    assert envelope["operator_id"] == "autosci-paper-ingest-worker"
    assert envelope["task_type"] == "scientific-paper-ingest"
    assert envelope["outputs"]["evidence_payload_path"] == summary["evidence_path"]

    evidence_payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert evidence_payload["schema"] == "research_paper.v1"
    assert evidence_payload["task_id"] == "task-scientific-node-smoke-test"
    assert evidence_payload["sprint_id"] == "sprint-scientific-node-smoke-test"
    assert evidence_payload["node_id"] == "paper_ingest"
    assert evidence_payload["status"] == "completed"

    assert summary["gate_result"]["ok"] is True
    assert '"action": "ingest_paper"' in output_log.read_text(encoding="utf-8")
