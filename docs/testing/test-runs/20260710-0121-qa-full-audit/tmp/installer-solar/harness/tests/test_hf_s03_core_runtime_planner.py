import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from hf_s03_core_runtime_planner import SPRINT_ID, build_task_graph, generate_planner_artifacts


def test_build_task_graph_has_expected_shape():
    graph = build_task_graph()
    assert graph["sprint_id"] == SPRINT_ID
    assert len(graph["nodes"]) == 5
    assert graph["nodes"][0]["id"] == "C1_schema_storage_state"
    assert graph["nodes"][-1]["depends_on"] == ["C4_reasoning_compiler_store_watch"]


def test_generate_planner_artifacts_promotes_status(tmp_path):
    runtime_root = tmp_path / "runtime"
    sprint_root = runtime_root / "sprints"
    sprint_root.mkdir(parents=True, exist_ok=True)
    (sprint_root / f"{SPRINT_ID}.status.json").write_text(
        json.dumps(
            {
                "id": SPRINT_ID,
                "sprint_id": SPRINT_ID,
                "title": "核心实现与数据模型",
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
    (sprint_root / f"{SPRINT_ID}.prd.md").write_text("# PRD\n", encoding="utf-8")
    (sprint_root / f"{SPRINT_ID}.contract.md").write_text("# Contract\n", encoding="utf-8")

    result = generate_planner_artifacts(runtime_root)

    assert result["ok"] is True
    status = json.loads((sprint_root / f"{SPRINT_ID}.status.json").read_text(encoding="utf-8"))
    assert status["status"] == "active"
    assert status["phase"] == "planning_complete"
    assert status["handoff_to"] == "builder_main"
    assert (sprint_root / f"{SPRINT_ID}.design.md").exists()
    assert (sprint_root / f"{SPRINT_ID}.plan.md").exists()
    assert (sprint_root / f"{SPRINT_ID}.task_graph.json").exists()
