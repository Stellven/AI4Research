import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from compiled_sprint_review_closeout import closeout_compiled_sprint


def test_closeout_compiled_sprint_bootstraps_failed_review(tmp_path):
    runtime_root = tmp_path / "runtime"
    sprint_root = runtime_root / "sprints"
    sprint_root.mkdir(parents=True, exist_ok=True)
    sid = "sprint-20260527-understand-anything-operator-productization"
    (sprint_root / f"{sid}.contract.md").write_text(
        "# Compiled Contract — Understand Anything Operator Productization\n",
        encoding="utf-8",
    )
    (sprint_root / f"{sid}.handoff.md").write_text("# Handoff — Understand Anything\n", encoding="utf-8")
    (sprint_root / f"{sid}.acceptance_verdict.json").write_text(
        json.dumps({"verdict": "FAIL", "reasons": ["task_graph_incomplete"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (sprint_root / f"{sid}.coverage_report.json").write_text(
        json.dumps({"summary": {"coverage_ratio": 0.0}}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = closeout_compiled_sprint(runtime_root, sid)

    assert result["ok"] is True
    status = json.loads((sprint_root / f"{sid}.status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed_review"
    assert status["handoff_to"] == "planner"
    assert status["stage"] == "reviewed_failed"
    eval_payload = json.loads((sprint_root / f"{sid}.eval.json").read_text(encoding="utf-8"))
    assert eval_payload["verdict"] == "FAIL"
    assert "task_graph_incomplete" in eval_payload["failed_conditions"]
