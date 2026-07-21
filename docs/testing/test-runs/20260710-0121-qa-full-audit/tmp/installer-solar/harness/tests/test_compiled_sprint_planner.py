import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from compiled_sprint_planner import generate_planner_artifacts


def test_generate_planner_artifacts_for_compiled_sprint(tmp_path):
    runtime_root = tmp_path / "runtime"
    sprint_root = runtime_root / "sprints"
    sprint_root.mkdir(parents=True, exist_ok=True)
    sid = "sprint-20260527-understand-anything-operator-productization"
    (sprint_root / f"{sid}.status.json").write_text(
        json.dumps(
            {
                "id": sid,
                "sprint_id": sid,
                "title": "Understand Anything Productization",
                "status": "drafting",
                "phase": "prd_ready",
                "handoff_to": "planner",
                "target_role": "planner",
                "history": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (sprint_root / f"{sid}.prd.md").write_text(
        "# Understand Anything Productization\n\n## 3. Goals / Non-goals\nGoals:\n- 建立正式 planner/builder/evaluator 主链\n",
        encoding="utf-8",
    )
    (sprint_root / f"{sid}.contract.md").write_text(
        "# Contract\n\n## Product Contract\n- success_metrics:\n  - PRD、contract、TaskDAG 互相对齐。\n\n## Agent Execution Contract\n- stop_conditions:\n  - 缺少可验证 acceptance 不得标记为完成。\n",
        encoding="utf-8",
    )
    (sprint_root / f"{sid}.task_graph.json").write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "nodes": [
                    {
                        "id": "S1",
                        "goal": "Lock implementation approach.",
                        "depends_on": [],
                        "logical_operator": "DeepArchitect",
                        "type": "design",
                        "capability_capsule_id": "cap.requirement-compiler-planner",
                        "dispatch_task_type": "planning",
                        "acceptance": ["Implementation path explicit."],
                        "outputs": ["patch.diff"],
                        "requirement_ids": ["REQ-001"],
                        "acceptance_ids": ["ACC-S1-1"],
                        "write_scope": ["harness/**"],
                        "read_scope": ["requirement_ir.json"],
                        "required_capabilities": ["architecture"],
                    },
                    {
                        "id": "S2",
                        "goal": "Implement.",
                        "depends_on": ["S1"],
                        "logical_operator": "ImplementationWorker",
                        "type": "implementation",
                        "capability_capsule_id": "cap.requirement-compiler-implementation",
                        "dispatch_task_type": "implementation",
                        "acceptance": ["Patch produced."],
                        "outputs": ["test_report.md"],
                        "requirement_ids": ["REQ-001"],
                        "acceptance_ids": ["ACC-S2-1"],
                        "write_scope": ["harness/**"],
                        "read_scope": ["requirement_ir.json"],
                        "required_capabilities": ["python"],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = generate_planner_artifacts(runtime_root=runtime_root, sprint_id=sid)

    assert result["ok"] is True
    status = json.loads((sprint_root / f"{sid}.status.json").read_text(encoding="utf-8"))
    assert status["status"] == "active"
    assert status["phase"] == "planning_complete"
    assert status["handoff_to"] == "builder_main"
    assert (sprint_root / f"{sid}.design.md").exists()
    assert (sprint_root / f"{sid}.plan.md").exists()
    assert (sprint_root / f"{sid}.traceability.json").exists()
