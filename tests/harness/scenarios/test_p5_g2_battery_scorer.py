"""P5 G2-prep: deterministic planner-quality battery scorer.

The scorer must exercise the real shipped plan_validator path with real
capsule/operator registries. These tests build only planner-output graph files
and then assert the emitted scorecard arithmetic and CLI exit codes.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HARNESS_DIR = (Path(__file__).resolve().parents[3] / 'harness')
LIB_DIR = HARNESS_DIR / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import planner_battery as pb  # noqa: E402
import plan_validator as pv  # noqa: E402


def _node(node_id: str = "N1", **overrides) -> dict:
    node = {
        "id": node_id,
        "goal": f"{node_id} deterministic planner battery fixture",
        "depends_on": [],
        "task_type": "implementation",
        "dispatch_task_type": "implementation",
        "capability_capsule_id": "cap.requirement-compiler-implementation",
        "allowed_operators": {"role": "builder", "providers": ["openai"]},
        "write_scope": ["workspace/tools/example_tool.py", "workspace/tests/test_example_tool.py"],
        "proof_obligations": [],
        "evaluator_gate": {
            "kind": "deterministic_command",
            "command": "python3 -m pytest workspace/tests -q",
            "on_fail": "repair_once_then_fail",
        },
    }
    node.update(overrides)
    return node


def _graph(*nodes: dict) -> dict:
    return {
        "sprint_id": "sprint-p5-g2-battery-fixture",
        "workflow_contract_id": "pm.generic.v1",
        "workflow_contract_version": "1.0",
        "nodes": list(nodes) or [_node()],
    }


def _reject_graph() -> dict:
    return _graph(_node(
        "R1",
        evaluator_gate={"kind": "none", "on_fail": "fail"},
    ))


def _write_graph(directory: Path, case_id: str, graph: dict) -> Path:
    path = directory / f"{case_id}.task_graph.json"
    path.write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_scorecard_rows_and_totals_use_real_validator(tmp_path):
    graphs = tmp_path / "graphs"
    graphs.mkdir()
    _write_graph(graphs, "E1", _graph())
    _write_graph(graphs, "E5", _reject_graph())

    scorecard = pb.score_directory(graphs)

    assert scorecard["schema"] == pb.SCORECARD_SCHEMA
    assert scorecard["workflow_contract_id"] == pv.GENERIC_CONTRACT_ID
    assert list(scorecard["cases"]) == ["E1", "E5"]
    assert scorecard["cases"]["E1"] == {
        "graph_file": "E1.task_graph.json",
        "graph_kind": "planner",
        "compiled": True,
        "error_count": 0,
        "error_codes": [],
        "code_counts": {},
    }
    assert scorecard["cases"]["E5"]["compiled"] is False
    assert scorecard["cases"]["E5"]["error_count"] == 1
    assert scorecard["cases"]["E5"]["error_codes"] == [pv.ERROR_PLAN_GATE_KIND_ILLEGAL]
    assert scorecard["cases"]["E5"]["code_counts"] == {pv.ERROR_PLAN_GATE_KIND_ILLEGAL: 1}
    assert scorecard["totals"] == {
        "case_count": 2,
        "scored_count": 2,
        "pre_planner_templates": 0,
        "unstamped": 0,
        "compiled": 1,
        "rejected": 1,
        "compile_rate": 0.5,
        "top_reject_codes": [{"code": pv.ERROR_PLAN_GATE_KIND_ILLEGAL, "count": 1}],
    }


def test_cli_returns_zero_when_all_graphs_compile(tmp_path):
    graphs = tmp_path / "graphs"
    graphs.mkdir()
    out = tmp_path / "scorecard.json"
    _write_graph(graphs, "E1", _graph())

    result = _run_cli(graphs, out)

    assert result.returncode == 0, result.stderr
    assert "battery scorecard:" in result.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["totals"]["compile_rate"] == 1.0
    assert payload["totals"]["rejected"] == 0


def test_cli_returns_three_when_any_graph_rejects(tmp_path):
    graphs = tmp_path / "graphs"
    graphs.mkdir()
    out = tmp_path / "scorecard.json"
    _write_graph(graphs, "E1", _graph())
    _write_graph(graphs, "E5", _reject_graph())

    result = _run_cli(graphs, out)

    assert result.returncode == 3, result.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["totals"]["rejected"] == 1
    assert payload["totals"]["top_reject_codes"] == [
        {"code": pv.ERROR_PLAN_GATE_KIND_ILLEGAL, "count": 1}
    ]


# --- G2b battery 20260709T144445Z follow-up: pre-planner template snapshots --
#
# The live capture snapshots whatever task_graph.json is on disk when the
# window closes. If the planner is still in flight, that file is the
# requirement-compiler's legacy template (dag_variant/required_gates, no
# workflow_contract_id) — NOT planner output. Scoring it as planner output
# produced both a false reject (E5: PLAN_REPAIR_BUDGET_MISSING x3 from the
# gateless template) and a false compile (E4: a gated template that happens
# to validate offline).


def _template_graph(*, gated: bool) -> dict:
    """The requirement-compiler template shape observed in the E4/E5 captures."""
    node = {
        "id": "S1",
        "goal": "Implement the requested targeted change.",
        "depends_on": [],
        "dispatch_task_type": "implementation",
        "capability_capsule_id": "cap.requirement-compiler-implementation",
        "allowed_operators": {"role": "builder", "providers": ["openai"]},
        "write_scope": ["workspace/out.py"],
        "proof_obligations": [],
    }
    if gated:
        node["task_type"] = "implementation"
        node["evaluator_gate"] = {"kind": "llm_eval", "on_fail": "repair_once_then_fail"}
        node["max_repair_attempts"] = 1
    return {
        "sprint_id": "sprint-p5-template-fixture",
        "dag_variant": "sprint_default",
        "required_gates": ["evidence"],
        "nodes": [node],
    }


def test_gateless_template_snapshot_is_not_a_planner_reject(tmp_path):
    """The E5 shape: compiler template without gates must be classified as a
    pre-planner snapshot, not scored as a planner PLAN_REPAIR_BUDGET_MISSING."""
    graphs = tmp_path / "graphs"
    graphs.mkdir()
    _write_graph(graphs, "E1", _graph())
    _write_graph(graphs, "E5", _template_graph(gated=False))

    scorecard = pb.score_directory(graphs)

    row = scorecard["cases"]["E5"]
    assert row["graph_kind"] == "pre_planner_template", row
    assert row["compiled"] is None
    assert row["error_codes"] == []
    totals = scorecard["totals"]
    assert totals["case_count"] == 2
    assert totals["scored_count"] == 1
    assert totals["pre_planner_templates"] == 1
    assert totals["compiled"] == 1
    assert totals["rejected"] == 0
    assert totals["compile_rate"] == 1.0
    assert totals["top_reject_codes"] == []


def test_gated_template_snapshot_is_not_a_planner_compile(tmp_path):
    """The E4 shape: a gated, marker-carrying, unstamped graph must not count
    as a compiled planner graph (G3 run 4 refined its kind from
    pre_planner_template to unstamped — authorship can't be proven)."""
    graphs = tmp_path / "graphs"
    graphs.mkdir()
    _write_graph(graphs, "E4", _template_graph(gated=True))

    scorecard = pb.score_directory(graphs)

    row = scorecard["cases"]["E4"]
    assert row["graph_kind"] == "unstamped", row
    assert row["compiled"] is None
    totals = scorecard["totals"]
    assert totals["scored_count"] == 0
    assert totals["compiled"] == 0
    assert totals["unstamped"] == 1


def test_planner_graph_without_contract_id_is_still_scored(tmp_path):
    """The G2 baseline shape (raw planner output, no contract id, no template
    markers) must keep scoring as planner output."""
    graphs = tmp_path / "graphs"
    graphs.mkdir()
    raw = _graph()
    raw.pop("workflow_contract_id")
    raw.pop("workflow_contract_version")
    _write_graph(graphs, "E2", raw)

    scorecard = pb.score_directory(graphs)

    assert scorecard["cases"]["E2"]["graph_kind"] == "planner"
    assert scorecard["totals"]["scored_count"] == 1


def test_gated_unstamped_graph_is_not_classified_as_template(tmp_path):
    """G3 run 4: the planner emitted its graph by editing the compiler
    template in place, keeping the legacy top-level markers — the classifier
    called REAL planner output a pre_planner_template. The compiler template
    is all-gateless; a marker-carrying graph whose nodes have evaluator_gate
    is planner-shaped but unstamped, and must be validated and reported as
    'unstamped' (still outside compile_rate — authorship can't be proven)."""
    graphs = tmp_path / "graphs"
    graphs.mkdir()
    planner_shaped = _template_graph(gated=True)
    _write_graph(graphs, "E4", planner_shaped)

    scorecard = pb.score_directory(graphs)

    row = scorecard["cases"]["E4"]
    assert row["graph_kind"] == "unstamped", row
    assert row["compiled"] is None
    assert isinstance(row["error_codes"], list)
    totals = scorecard["totals"]
    assert totals["scored_count"] == 0
    assert totals["unstamped"] == 1
    assert totals["pre_planner_templates"] == 0


def test_gateless_template_still_classified_as_template(tmp_path):
    graphs = tmp_path / "graphs"
    graphs.mkdir()
    _write_graph(graphs, "E5", _template_graph(gated=False))

    scorecard = pb.score_directory(graphs)

    assert scorecard["cases"]["E5"]["graph_kind"] == "pre_planner_template"
    assert scorecard["totals"]["pre_planner_templates"] == 1
    assert scorecard["totals"]["unstamped"] == 0


def test_cli_returns_four_when_capture_holds_template_snapshots(tmp_path):
    """A battery whose capture window closed before the planner responded is
    an incomplete capture, not a pass — the CLI must not exit 0."""
    graphs = tmp_path / "graphs"
    graphs.mkdir()
    out = tmp_path / "scorecard.json"
    _write_graph(graphs, "E1", _graph())
    _write_graph(graphs, "E5", _template_graph(gated=False))

    result = _run_cli(graphs, out)

    assert result.returncode == 4, (result.stdout, result.stderr)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["totals"]["pre_planner_templates"] == 1
    assert payload["totals"]["rejected"] == 0


def _run_cli(graphs_dir: Path, out: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(LIB_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "planner_battery", str(graphs_dir), "--out", str(out)],
        cwd=HARNESS_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
