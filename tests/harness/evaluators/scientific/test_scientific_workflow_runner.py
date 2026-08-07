from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


HARNESS = (Path(__file__).resolve().parents[4] / 'harness')
RUNNER = HARNESS / "tools" / "run_scientific_workflow.py"


def _prepare_isolated_harness(tmp_path: Path) -> Path:
    for name in ("config", "personas", "tools", "plugins", "evaluators", "schemas", "lib", "templates"):
        target = HARNESS / name
        link = tmp_path / name
        if not link.exists():
            link.symlink_to(target, target_is_directory=True)
    (tmp_path / "run").mkdir(exist_ok=True)
    (tmp_path / "artifacts").mkdir(exist_ok=True)
    return tmp_path


def test_config_driven_scientific_workflow_runner_dispatches_node_runtime(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    raw_dir = harness_dir / "raw"
    raw_dir.mkdir()
    paper = raw_dir / "paper.md"
    paper.write_text(
        "# Workflow Runtime Paper\n\n"
        "## Abstract\n"
        "This paper evaluates a Solar-native workflow runner with explicit runtime evidence.\n\n"
        "## Results\n"
        "The runner records operator and bridge outputs without using a hidden AutoSci lifecycle runner.\n",
        encoding="utf-8",
    )
    workflow_config = harness_dir / "workflow.one-node.json"
    workflow_config.write_text(
        json.dumps(
            {
                "schema_version": "solar.task_graph.v1",
                "workflow_id": "scientific_workflow_runner_contract_test",
                "nodes": [
                    {
                        "id": "paper_ingest",
                        "logical_operator": "ScientificPaperIngestor",
                        "depends_on": [],
                        "gate": "G_PAPER_INGEST",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["HARNESS_DIR"] = str(harness_dir)
    env["SOLAR_OPERATORD_ONCE_MAX_WAIT_SECONDS"] = "20"

    proc = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--harness-dir",
            str(harness_dir),
            "--workflow-config",
            str(workflow_config),
            "--job-id",
            "job-scientific-workflow-runner-test",
            "--paper",
            str(paper),
            "--timeout-seconds",
            "20",
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
    assert summary["schema"] == "scientific_lifecycle.v1"
    assert summary["workflow_id"] == "scientific_workflow_runner_contract_test"
    assert summary["lifecycle_status"] == "passed"
    assert summary["execution_owner"] == "solar.operator_runtime.generic_scientific_workflow_runner"
    assert summary["required_nodes"] == ["paper_ingest"]
    assert set(summary["node_results"]) == {"paper_ingest"}
    assert summary["node_summaries"]["paper_ingest"]["runtime_mode"] == "solar_scientific_workflow"
    assert summary["node_summaries"]["paper_ingest"]["runner_contract"] == "generic_workflow_runner"

    boundary = summary["dispatch_boundary"]
    assert boundary["status"] == "generic_workflow_runner"
    assert boundary["runner_contract"] == "generic_workflow_runner"
    assert boundary["production_ready"] is True
    assert boundary["smoke_nodes"] == []
    assert boundary["fixture_nodes"] == []

    profile = summary["dispatch_input_profiles"]["paper_ingest"]
    assert profile["uses_fixture_or_smoke_input"] is False
    assert profile["runner_contract"] == "generic_workflow_runner"

    runtime_manifest = harness_dir / summary["runtime_manifest_path"]
    assert runtime_manifest.exists()
    manifest_payload = json.loads(runtime_manifest.read_text(encoding="utf-8"))
    assert manifest_payload["schema"] == "scientific_workflow_runtime_manifest.v1"
    assert manifest_payload["proofs"][0]["native_skill"] == "ingest"

    node_result = summary["node_results"]["paper_ingest"]
    assert (harness_dir / node_result["artifact_path"]).exists()
    assert (harness_dir / node_result["operator_result_path"]).exists()
    assert (harness_dir / node_result["bridge_result_path"]).exists()
    assert summary["lifecycle_gate_result"]["ok"] is True


def test_scientific_workflow_runner_blocked_gate_emits_authorization_continuation(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    workflow_config = harness_dir / "workflow.blocked-literature.json"
    workflow_config.write_text(
        json.dumps(
            {
                "schema_version": "solar.task_graph.v1",
                "workflow_id": "scientific_workflow_runner_blocked_gate_test",
                "nodes": [
                    {
                        "id": "literature_discover",
                        "logical_operator": "ScientificLiteratureDiscoverer",
                        "depends_on": [],
                        "gate": "G_LITERATURE_DISCOVERY",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["HARNESS_DIR"] = str(harness_dir)

    proc = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--harness-dir",
            str(harness_dir),
            "--workflow-config",
            str(workflow_config),
            "--job-id",
            "job-scientific-workflow-blocked-gate-test",
            "--node-id",
            "literature_discover",
            "--require-external-evidence",
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
    assert summary["lifecycle_status"] == "blocked"
    assert summary["authorization_required"] is True
    assert len(summary["authorization_requests"]) == 1
    request = summary["authorization_requests"][0]
    assert request["schema"] == "scientific_workflow_gate_authorization_request.v1"
    assert request["status"] == "awaiting_authorization"
    assert request["node_id"] == "literature_discover"
    assert request["native_skill"] == "daily-arxiv"
    assert "network_fetch" in request["requested_side_effects"]
    continuation = request["continuation"]
    assert continuation["schema"] == "scientific_workflow_gate_continuation.v1"
    assert continuation["retriable"] is True
    assert continuation["resume_strategy"] == "rerun_workflow_with_authorization_patch"
    assert "--source-runtime-evidence" in continuation["resume_args_patch"]
    blocked = summary["blocked_nodes"]["literature_discover"]
    assert blocked["authorization_request"]["continuation"]["request_fingerprint"] == continuation["request_fingerprint"]
