from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[3]
SMOKE = HARNESS / "plugins" / "autosci" / "bin" / "autosci_operator_smoke.py"
GATE = HARNESS / "evaluators" / "scientific" / "autosci_operator_smoke_gate.py"
PAPER = HARNESS / "plugins" / "autosci" / "tests" / "fixtures" / "skillgen_operator_smoke_paper.md"
ROUTE_CONFIG = HARNESS / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json"
BINDING_CONFIG = HARNESS / "plugins" / "autosci" / "config" / "feature_operator_bindings.v1.json"


def run_smoke(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path)
    return subprocess.run(
        [
            sys.executable,
            str(SMOKE),
            "skillgen",
            "--paper",
            str(PAPER),
            "--out",
            "artifacts/autosci/operator-smoke/skillgen/autosci_operator_smoke.json",
        ],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_skillgen_operator_smoke_binds_every_native_skill_and_runs_core_actions(tmp_path: Path) -> None:
    proc = run_smoke(tmp_path)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["route_count"] == 28
    assert summary["bound_count"] == 28
    assert summary["failed_count"] == 0
    assert summary["unbound_count"] == 0
    assert summary["core_action_count"] == 16

    payload = json.loads((tmp_path / "artifacts/autosci/operator-smoke/skillgen/autosci_operator_smoke.json").read_text(encoding="utf-8"))
    smoke = payload["outputs"]["smoke"]
    assert smoke["completed_count"] == 0
    assert smoke["partial_count"] == 17
    assert smoke["gated_count"] == 11
    core_statuses = {item["action"]: item["status"] for item in smoke["core_actions"]}
    for action in [
        "ingest_paper",
        "extract_claims",
        "extract_methods",
        "map_code_evidence",
        "generate_ideas",
        "evaluate_ideas",
        "design_experiment",
        "run_experiment",
        "monitor_experiment",
        "verify_claim",
        "write_report",
        "evolve_workflow",
        "update_graph",
    ]:
        assert core_statuses[action] == "passed"
    assert core_statuses["discover_literature"] == "passed"

    paper_evidence = json.loads((tmp_path / "artifacts/autosci/operator-smoke/skillgen/research_paper.json").read_text(encoding="utf-8"))
    assert "SKILLGEN" in paper_evidence["outputs"]["paper"]["title"]


def test_phase19_route_and_operator_statuses_stay_in_sync() -> None:
    routes = json.loads(ROUTE_CONFIG.read_text(encoding="utf-8"))["routes"]
    bindings = json.loads(BINDING_CONFIG.read_text(encoding="utf-8"))["bindings"]
    binding_status_by_skill = {binding["native_skill"]: binding["operator_status"] for binding in bindings}

    assert {route["native_skill"] for route in routes} == set(binding_status_by_skill)
    assert {
        route["native_skill"]: (route["coverage_status"], binding_status_by_skill[route["native_skill"]])
        for route in routes
        if route["coverage_status"] != binding_status_by_skill[route["native_skill"]]
    } == {}


def test_skillgen_operator_smoke_gate_accepts_generated_evidence(tmp_path: Path) -> None:
    proc = run_smoke(tmp_path)
    assert proc.returncode == 0, proc.stderr
    evidence_path = tmp_path / "artifacts/autosci/operator-smoke/skillgen/autosci_operator_smoke.json"
    gate = subprocess.run(
        [sys.executable, str(GATE), str(evidence_path)],
        cwd=HARNESS,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert gate.returncode == 0, gate.stdout + gate.stderr
    result = json.loads(gate.stdout)
    assert result["ok"] is True
    assert result["warnings"]
