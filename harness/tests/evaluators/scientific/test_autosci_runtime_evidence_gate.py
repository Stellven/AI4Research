from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from evaluators.scientific import autosci_runtime_evidence_gate


def payload(tmp_path: Path, *, action: str = "compile_paper") -> dict:
    artifact = tmp_path / "runtime.pdf"
    artifact.write_text("%PDF-1.4\n", encoding="utf-8")
    runtime = {
        "action": action,
        "status": "completed",
        "approval_ref": "approval-123",
        "command_run": "approved-runtime-command",
        "exit_code": 0,
        "evidence_ids": [f"runtime:{action}"],
        "checks": [{"check": "exit_code", "status": "ok", "detail": "exit_code=0"}],
    }
    if action == "compile_paper":
        runtime.update({"pdf_generated": True, "pdf_path": str(artifact)})
    elif action == "build_poster":
        runtime.update({"browser_rendered": True, "png_exported": True, "overflow_probe": "passed"})
    elif action in {"run_experiment", "run_pilot_experiment"}:
        runtime.update({
            "outcome": "supports",
            "result_collected": True,
            "metrics": [{"name": "accuracy", "value": 0.91}],
        })
    elif action in {"daily_arxiv_prepare_finalize", "init_sources", "discover_literature"}:
        runtime.update({
            "candidates": [
                {
                    "candidate_id": "paper-001",
                    "title": "Runtime Verified Discovery",
                    "source_channels": ["arxiv"],
                    "ranking_score": 1.0,
                    "ranking_rationale": "Approved runtime fetch returned this paper.",
                    "dedup_status": "unknown",
                    "fetch_status": "fetched",
                }
            ]
        })
    elif action == "send_email":
        runtime.update({"delivered": True, "provider": "smtp"})
    return {
        "schema": "autosci_runtime_evidence.v1",
        "task_id": "task-runtime",
        "sprint_id": "sprint-runtime",
        "node_id": "node-runtime",
        "status": "completed",
        "inputs": {"approval_ref": "approval-123"},
        "outputs": {"runtime": runtime},
        "artifacts": [{"type": "runtime_artifact", "path": str(artifact)}],
        "provenance": {
            "operator_id": "test",
            "implementation_package": "test",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
        "limitations": ["Runtime evidence was produced by an approved external executor, not by the gate."],
    }


def test_autosci_runtime_evidence_gate_accepts_completed_compile_runtime(tmp_path: Path) -> None:
    result = autosci_runtime_evidence_gate.evaluate(payload(tmp_path), path=tmp_path / "runtime.json")

    assert result.ok is True
    assert result.status == "passed"


def test_autosci_runtime_evidence_gate_accepts_action_specific_completed_runtime(tmp_path: Path) -> None:
    for action in (
        "build_poster",
        "run_experiment",
        "run_pilot_experiment",
        "daily_arxiv_prepare_finalize",
        "init_sources",
        "discover_literature",
        "send_email",
    ):
        result = autosci_runtime_evidence_gate.evaluate(payload(tmp_path, action=action), path=tmp_path / f"{action}.json")

        assert result.ok is True, result.reasons
        assert result.status == "passed"


def test_autosci_runtime_evidence_gate_rejects_completed_poster_without_png(tmp_path: Path) -> None:
    item = payload(tmp_path, action="build_poster")
    item["outputs"]["runtime"]["png_exported"] = False

    result = autosci_runtime_evidence_gate.evaluate(item, path=tmp_path / "runtime.json")

    assert result.ok is False
    assert "png_exported=true" in " ".join(result.reasons)


def test_autosci_runtime_evidence_gate_rejects_missing_approval_ref(tmp_path: Path) -> None:
    item = payload(tmp_path)
    item["inputs"] = {}
    item["outputs"]["runtime"]["approval_ref"] = ""

    result = autosci_runtime_evidence_gate.evaluate(item, path=tmp_path / "runtime.json")

    assert result.ok is False
    assert "approval_ref" in " ".join(result.reasons)
