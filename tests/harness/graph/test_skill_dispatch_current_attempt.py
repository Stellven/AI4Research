from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


HARNESS = Path(__file__).resolve().parents[3] / "harness"
LIB = HARNESS / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))
SPEC = importlib.util.spec_from_file_location(
    "graph_node_dispatcher_current_attempt_contract",
    LIB / "graph_node_dispatcher.py",
)
assert SPEC and SPEC.loader
gnd = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gnd
SPEC.loader.exec_module(gnd)


def _write_skill_proof(task_dir: Path) -> None:
    (task_dir / "skill-dispatch-result.json").write_text("{}", encoding="utf-8")
    (task_dir / "skill-dispatch-pane-prompt.md").write_text("# Prompt\n", encoding="utf-8")
    (task_dir / "skill-dispatch-selection-proof.json").write_text("{}", encoding="utf-8")
    (task_dir / "skill-dispatch-bridge-contract.json").write_text(
        json.dumps(
            {
                "command_protocol": {"mode": "workflow_methodology"},
                "workflow_contract": {
                    "phases": ["apply_skill_workflow"],
                    "delivery_expectation": "phase_checklist_and_decision_log",
                },
            }
        ),
        encoding="utf-8",
    )


def test_skill_dispatch_proof_reads_current_execution_attempt_only(tmp_path, monkeypatch):
    sid = "sprint-skill-dispatch-current-attempt"
    operator_root = tmp_path / "run" / "operator-results" / "mini-codex-builder"
    old_dir = operator_root / "old-task"
    current_dir = operator_root / "current-task"
    old_dir.mkdir(parents=True)
    current_dir.mkdir(parents=True)
    for task_dir, task_id in ((old_dir, "old-task"), (current_dir, "current-task")):
        (task_dir / "result.json").write_text(
            json.dumps(
                {
                    "task_id": task_id,
                    "sprint_id": sid,
                    "node_id": "N1",
                    "status": "completed",
                }
            ),
            encoding="utf-8",
        )
    _write_skill_proof(old_dir)
    node = {
        "id": "N1",
        "execution_attempt": {
            "task_id": "current-task",
            "operator_id": "mini-codex-builder",
        },
        "proof_obligations": [
            {
                "kind": "self_check",
                "requirement": "check.skill_dispatch_result_written",
            }
        ],
    }
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)

    before = gnd._proof_artifact_presence(sid, node)
    assert before["skill_dispatch_result"] is False

    _write_skill_proof(current_dir)
    after = gnd._proof_artifact_presence(sid, node)
    assert after["skill_dispatch_result"] is True
    assert after["check.skill_dispatch_delivery_expectation_declared"] is True
    support = gnd._proof_support_artifacts_block(sid, node)
    assert str(current_dir / "skill-dispatch-result.json") in support
    assert str(current_dir / "skill-dispatch-pane-prompt.md") in support
    assert str(current_dir / "skill-dispatch-selection-proof.json") in support
    assert str(current_dir / "skill-dispatch-bridge-contract.json") in support
