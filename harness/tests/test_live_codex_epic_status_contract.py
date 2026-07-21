from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT.parent / "scripts" / "live_codex_epic_status.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("live_codex_epic_status_contract_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contract_path(workflow_id: str) -> Path:
    return ROOT / "config" / "workflows" / f"{workflow_id}.workflow.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_contract_options_derive_artifacts_roots_terminal_states_and_validator():
    mod = _load_module()

    rsi = mod.contract_artifact_options(_contract_path("research.deepdive.rsi_demo"), sid="sprint-rsi")
    assert rsi["workflow_id"] == "research.deepdive.rsi_demo"
    assert rsi["expected_artifacts"] == [
        "report.html",
        "report.md",
        "sources.json",
        "claims.json",
        "evaluation-checklist.md",
    ]
    assert rsi["terminal_states"]["D5"] == ["passed", "failed", "skipped", "cancelled", "skipped_parent_passed"]
    assert rsi["validator_command"] == "python3 scripts/validate_rsi_demo_report.py --workspace <resolved_root>"
    assert rsi["roots"][0]["type"] == "contract_canonical"
    assert rsi["roots"][0]["root"].as_posix().endswith("workspace/rsi-deep-research-report")
    assert rsi["roots"][1]["type"] == "contract_alias"
    assert rsi["roots"][1]["root"].as_posix().endswith("sprints/sprint-rsi/workdir/rsi-deep-research-report")

    code = mod.contract_artifact_options(_contract_path("code.cli_smoke"), sid="sprint-code", substitutions={"tool": "hello"})
    assert code["expected_artifacts"] == ["hello.py", "tests/test_hello.py", "sprint-code.review_decision.yaml"]
    assert code["validator_command"] == "python3 -m pytest sprints/sprint-code/workdir/tests -q"

    generic = mod.contract_artifact_options(_contract_path("pm.generic.v1"), sid="sprint-generic")
    assert generic["expected_artifacts"] == []
    assert generic["roots"][0]["root"].as_posix().endswith("workspace")
    assert [row["type"] for row in generic["roots"]] == ["contract_canonical", "contract_alias", "contract_alias"]


def test_contract_options_reject_unregistered_contract(tmp_path):
    mod = _load_module()
    contract = json.loads(_contract_path("code.cli_smoke").read_text(encoding="utf-8"))
    contract["workflow_id"] = "evil.unregistered.contract"
    contract["version"] = "666"
    path = tmp_path / "fake.workflow.json"
    path.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(ValueError, match="unregistered"):
        mod.contract_artifact_options(path, sid="sprint-fake-contract")


def test_contract_options_reject_malformed_contract(tmp_path):
    mod = _load_module()
    path = tmp_path / "malformed.workflow.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="schema|unreadable|invalid"):
        mod.contract_artifact_options(path, sid="sprint-fake-contract")


def test_artifact_check_contract_load_failure_exits_distinctly(tmp_path):
    harness_dir = tmp_path / "harness"
    workspace = tmp_path / "workspace"
    evidence_dir = tmp_path / "evidence"
    for path in (harness_dir, workspace, evidence_dir):
        path.mkdir()
    contract_path = tmp_path / "malformed.workflow.json"
    contract_path.write_text("{not-json", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "artifact-check",
            "--harness-dir",
            str(harness_dir),
            "--id",
            "sprint-fake-contract",
            "--evidence-dir",
            str(evidence_dir),
            "--workspace",
            str(workspace),
            "--contract",
            str(contract_path),
            "--marker-mode",
            "terminal",
        ],
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 2
    summary = json.loads((evidence_dir / "artifact-validation-summary.json").read_text(encoding="utf-8"))
    assert summary["state"] == "failed"
    assert summary["reason"] == "contract_load_failed"
    assert summary["failure_class"] == "contract_load_failed"
    assert summary["test_result"]["ran"] is False


def test_artifact_validation_uses_harness_sprints_dir(monkeypatch, tmp_path):
    mod = _load_module()
    sid = "sprint-custom-sprints"
    harness_dir = tmp_path / "harness"
    custom_sprints = tmp_path / "custom-sprints"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "ok.txt").write_text("ok\n", encoding="utf-8")
    _write_json(custom_sprints / f"{sid}.status.json", {"sprint_id": sid, "status": "passed"})
    _write_json(
        custom_sprints / f"{sid}.route-proof.json",
        {
            "ok": True,
            "selected_runtime": "codex",
            "allowed_providers": ["openai"],
            "stage_count": 1,
            "stages": [{"id": "S1", "provider": "openai"}],
            "violations": [],
        },
    )
    _write_json(
        custom_sprints / f"{sid}.task_graph.json",
        {"nodes": [{"id": "S1", "status": "passed", "write_scope": ["ok.txt"]}]},
    )
    monkeypatch.setenv("HARNESS_SPRINTS_DIR", str(custom_sprints))

    summary = mod.summarize_artifact_validation(
        harness_dir,
        sid,
        workspace=workspace,
        task="",
        expected_artifacts=["ok.txt"],
        test_command=f"{sys.executable} -c \"from pathlib import Path; assert Path('ok.txt').is_file()\"",
        terminal=True,
        stability_state_path=tmp_path / "stability.json",
        min_stable_polls=1,
        min_stable_seconds=0,
    )

    assert summary["state"] == "passed", summary
    assert summary["route_proof"]["runs"][0]["status_path"].startswith(str(custom_sprints))


def test_no_contract_artifact_validation_omits_contract_key(tmp_path):
    mod = _load_module()
    sid = "sprint-no-contract-shape"
    harness_dir = tmp_path / "harness"
    sprints_dir = harness_dir / "sprints"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "ok.txt").write_text("ok\n", encoding="utf-8")
    _write_json(sprints_dir / f"{sid}.status.json", {"sprint_id": sid, "status": "passed"})
    _write_json(
        sprints_dir / f"{sid}.route-proof.json",
        {
            "ok": True,
            "selected_runtime": "codex",
            "allowed_providers": ["openai"],
            "stage_count": 1,
            "stages": [{"id": "S1", "provider": "openai"}],
            "violations": [],
        },
    )

    summary = mod.summarize_artifact_validation(
        harness_dir,
        sid,
        workspace=workspace,
        task="",
        expected_artifacts=["ok.txt"],
        test_command=f"{sys.executable} -c \"from pathlib import Path; assert Path('ok.txt').is_file()\"",
        terminal=True,
        stability_state_path=tmp_path / "stability.json",
        min_stable_polls=1,
        min_stable_seconds=0,
    )

    assert summary["state"] == "passed", summary
    assert "contract" not in summary
