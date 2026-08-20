"""rc.10 A4b — human escalation is an absorbing, generation-fenced state.

The published rc.9 ordinary-prompt audit recorded 28 automatic
``needs_human_review -> pending`` transitions for one node.  A terminal
operator result remained visible after escalation, so ordinary reconciliation
requeued it, the retry counter escalated it again, and the cycle repeated.

These tests lock the class-level contract:

* automatic writers cannot leave ``needs_human_review``;
* a stale inline/result disagreement cannot project a blocked node as active;
* reconcile and doctor are observers while a human decision is outstanding;
* the one resume seam requires the exact block generation, actor, and reason;
* resume archives old review evidence and starts a fresh evidence generation;
* monitoring does not count the blocked node as active work.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
LIB = HARNESS / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import graph_node_dispatcher as gnd  # noqa: E402
import graph_scheduler as gs  # noqa: E402
from task_lifecycle import activate_execution_attempt  # noqa: E402


SID = "sprint-human-review-authority"
NODE_ID = "S3"
OPERATOR_ID = "codex-evaluator"
TASK_ID = f"pm-{SID}-{NODE_ID}-failed"


def _graph(node: dict) -> dict:
    return {
        "sprint_id": SID,
        "workflow_contract_id": "pm.generic.v1",
        "workflow_contract_version": "1.0",
        "nodes": [node],
        "node_results": {
            NODE_ID: {
                "status": str(node.get("status") or ""),
                "updated_at": str(node.get("updated_at") or "2026-07-15T00:00:00Z"),
            }
        },
        "gate_results": {},
        "required_gates": [],
    }


def _blocked_node() -> dict:
    return {
        "id": NODE_ID,
        "status": "needs_human_review",
        "updated_at": "2026-07-15T00:00:00Z",
        "depends_on": [],
        "dispatch_failure_streak": 8,
        "dispatch_blocked_reason": "dispatch_starvation:operator_result_failed",
        "next_action": "inspect the failed attempt and resume deliberately",
    }


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    sprints.mkdir(parents=True)
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gs, "HARNESS_DIR", harness)
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)
    return harness, sprints


def _write_failed_operator_result(harness: Path) -> Path:
    result = harness / "run" / "operator-results" / OPERATOR_ID / TASK_ID / "result.json"
    result.parent.mkdir(parents=True)
    result.write_text(
        json.dumps(
            {
                "task_id": TASK_ID,
                "operator_id": OPERATOR_ID,
                "sprint_id": SID,
                "node_id": NODE_ID,
                "status": "failed",
                "exit_code": 1,
                "started_at": "2026-07-15T00:00:01Z",
                "finished_at": "2026-07-15T00:00:02Z",
            }
        ),
        encoding="utf-8",
    )
    return result


def _stage_blocked_failed_attempt(harness: Path, sprints: Path) -> tuple[dict, Path]:
    node = _blocked_node()
    activate_execution_attempt(
        node,
        task_id=TASK_ID,
        dispatch_id="graph-S3-failed",
        operator_id=OPERATOR_ID,
        source="operator_pool",
        logical_role="evaluator",
        status="failed",
        requires_operator_result=True,
        sprint_id=SID,
        node_id=NODE_ID,
        result_path=str(_write_failed_operator_result(harness)),
        now="2026-07-15T00:00:01Z",
    )
    graph = _graph(node)
    graph_path = sprints / f"{SID}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    (sprints / f"{SID}.{NODE_ID}-handoff.md").write_text(
        "# stale handoff\n\nThis belongs to the failed attempt.\n",
        encoding="utf-8",
    )
    return graph, graph_path


def _literal_set(path: Path, variable: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == variable for target in targets):
            continue
        value = node.value
        if isinstance(value, ast.Set):
            return {
                str(item.value)
                for item in value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
    raise AssertionError(f"{variable} literal set not found in {path}")


def test_low_level_scheduler_writers_cannot_reopen_human_review() -> None:
    graph = _graph(_blocked_node())

    with pytest.raises(ValueError, match="explicit_human_resume"):
        gs.set_node_status(graph, NODE_ID, "pending")
    with pytest.raises(ValueError, match="explicit_human_resume"):
        gs.mark_node_result(graph, NODE_ID, "reviewing")

    assert gs.node_status(graph, NODE_ID) == "needs_human_review"


def test_human_review_projection_absorbs_newer_unrecorded_pending_result() -> None:
    node = _blocked_node()
    graph = _graph(node)
    graph["node_results"][NODE_ID] = {
        "status": "pending",
        "updated_at": "2026-07-15T01:00:00Z",
    }

    assert gs.node_status(graph, NODE_ID) == "needs_human_review"


def test_same_generation_human_review_record_conflict_fails_closed() -> None:
    node = {
        "id": NODE_ID,
        "status": "pending",
        "depends_on": [],
        "human_review": {
            "schema_version": "solar.human_review.v1",
            "generation": 1,
            "state": "resumed",
        },
    }
    graph = _graph(node)
    graph["node_results"][NODE_ID].update(
        {
            "status": "pending",
            "human_review": {
                "schema_version": "solar.human_review.v1",
                "generation": 1,
                "state": "blocked",
            },
        }
    )

    assert gs.node_status(graph, NODE_ID) == "needs_human_review"


def test_exact_rc9_failed_result_reconcile_does_not_requeue_blocked_node(sandbox) -> None:
    harness, sprints = sandbox
    graph, graph_path = _stage_blocked_failed_attempt(harness, sprints)

    reconciled = gnd._reconcile_existing_dispatches(graph, graph_path)

    assert gs.node_status(graph, NODE_ID) == "needs_human_review"
    assert graph["nodes"][0]["status"] == "needs_human_review"
    assert not any(row.get("status") == "pending" for row in reconciled)
    assert reconciled == []


def test_doctor_cannot_copy_newer_pending_result_over_human_review(sandbox) -> None:
    _harness, _sprints = sandbox
    node = _blocked_node()
    graph = _graph(node)
    graph["node_results"][NODE_ID] = {
        "status": "pending",
        "updated_at": "2026-07-15T01:00:00Z",
    }

    report = gs.doctor_graph(graph, repair=True)

    assert gs.node_status(graph, NODE_ID) == "needs_human_review"
    assert graph["nodes"][0]["status"] == "needs_human_review"
    assert any(
        row.get("reason") == "needs_human_review_requires_explicit_resume"
        for row in report.get("suppressed", [])
    )


def test_stale_dispatcher_save_preserves_complete_human_review_generation(sandbox) -> None:
    _harness, sprints = sandbox
    node = {"id": NODE_ID, "status": "pending", "depends_on": []}
    current = _graph(node)
    gs.enter_node_human_review(
        current,
        NODE_ID,
        reason="operator result failed repeatedly",
        next_action="inspect and explicitly resume",
        writer="test_fixture",
    )
    graph_path = sprints / f"{SID}.task_graph.json"
    gs.save_graph(graph_path, current)

    stale = _graph(
        {
            "id": NODE_ID,
            "status": "pending",
            "depends_on": [],
            "dispatch_retry_reason": "operator_result_failed",
            "last_operator_closeout_failure": {"reason": "operator_result_failed"},
        }
    )
    gnd._save_graph_preserving_runtime_progress(str(graph_path), stale)

    persisted = gs.load_graph(graph_path)
    assert gs.node_status(persisted, NODE_ID) == "needs_human_review"
    assert persisted["nodes"][0]["human_review"]["state"] == "blocked"
    assert persisted["nodes"][0]["human_review"]["generation"] == 1


def test_explicit_resume_requires_exact_generation_actor_and_reason(sandbox) -> None:
    harness, sprints = sandbox
    graph, graph_path = _stage_blocked_failed_attempt(harness, sprints)
    enter = getattr(gs, "enter_node_human_review", None)
    generation_of = getattr(gs, "human_review_generation", None)
    resume = getattr(gnd, "resume_human_review", None)
    assert callable(enter) and callable(generation_of) and callable(resume)

    enter(
        graph,
        NODE_ID,
        reason="operator_result_failed eight times",
        next_action="inspect and resume",
        writer="test_fixture",
    )
    gs.save_graph(graph_path, graph)
    generation = generation_of(graph, NODE_ID)
    assert generation >= 1

    for kwargs, error in (
        ({"expected_generation": generation + 1, "actor": "owner", "reason": "retry"}, "generation_mismatch"),
        ({"expected_generation": generation, "actor": "", "reason": "retry"}, "actor_required"),
        ({"expected_generation": generation, "actor": "owner", "reason": ""}, "reason_required"),
    ):
        result = resume(str(graph_path), NODE_ID, **kwargs)
        assert result["ok"] is False
        assert error in result["reason"]
        assert gs.node_status(gs.load_graph(graph_path), NODE_ID) == "needs_human_review"


def test_reescalation_uses_a_new_generation_and_rejects_old_resume(sandbox) -> None:
    _harness, sprints = sandbox
    graph = _graph({"id": NODE_ID, "status": "pending", "depends_on": []})
    first_block = gs.enter_node_human_review(
        graph,
        NODE_ID,
        reason="first bounded failure set",
        next_action="inspect and explicitly resume",
        writer="test_fixture",
    )
    graph_path = sprints / f"{SID}.task_graph.json"
    gs.save_graph(graph_path, graph)
    first_resume = gnd.resume_human_review(
        str(graph_path),
        NODE_ID,
        expected_generation=first_block["generation"],
        actor="release-owner",
        reason="first issue corrected",
    )
    assert first_resume["ok"] is True
    assert first_resume["status_sync"]["ok"] is True
    assert first_resume["status_sync"]["status"]["status"] == "active"
    projected = json.loads((sprints / f"{SID}.status.json").read_text(encoding="utf-8"))
    assert projected["status"] == "active"
    assert projected["active_node"] == NODE_ID

    resumed = gs.load_graph(graph_path)
    second_block = gs.enter_node_human_review(
        resumed,
        NODE_ID,
        reason="second bounded failure set",
        next_action="inspect the new failure and explicitly resume",
        writer="test_fixture",
    )
    gs.save_graph(graph_path, resumed)

    assert second_block["generation"] == first_block["generation"] + 1
    replay = gnd.resume_human_review(
        str(graph_path),
        NODE_ID,
        expected_generation=first_block["generation"],
        actor="release-owner",
        reason="stale first-generation action",
    )
    assert replay["ok"] is False
    assert "generation_mismatch" in replay["reason"]
    assert gs.node_status(gs.load_graph(graph_path), NODE_ID) == "needs_human_review"


def test_resume_never_archives_an_eval_path_outside_its_sprint_storage(sandbox) -> None:
    harness, sprints = sandbox
    graph, graph_path = _stage_blocked_failed_attempt(harness, sprints)
    gs.enter_node_human_review(
        graph,
        NODE_ID,
        reason="operator result failed repeatedly",
        next_action="inspect and explicitly resume",
        writer="test_fixture",
    )
    unrelated = harness.parent / "unrelated-user-file.json"
    unrelated.write_text('{"belongs_to": "the user"}\n', encoding="utf-8")
    original = unrelated.read_bytes()
    graph["nodes"][0]["eval_json"] = str(unrelated)
    gs.save_graph(graph_path, graph)

    result = gnd.resume_human_review(
        str(graph_path),
        NODE_ID,
        expected_generation=gs.human_review_generation(graph, NODE_ID),
        actor="release-owner",
        reason="operator capacity restored",
    )

    assert result["ok"] is True
    assert unrelated.is_file()
    assert unrelated.read_bytes() == original
    assert result["archived_sidecars"]["_ignored_unsafe_sidecars"]["eval_json"] == str(unrelated)


def test_resume_rejects_a_sprint_archive_directory_symlinked_outside(sandbox) -> None:
    harness, sprints = sandbox
    graph, graph_path = _stage_blocked_failed_attempt(harness, sprints)
    gs.enter_node_human_review(
        graph,
        NODE_ID,
        reason="operator result failed repeatedly",
        next_action="inspect and explicitly resume",
        writer="test_fixture",
    )
    gs.save_graph(graph_path, graph)
    outside_archive = harness.parent / "outside-archive"
    outside_archive.mkdir()
    (sprints / SID).symlink_to(outside_archive, target_is_directory=True)

    result = gnd.resume_human_review(
        str(graph_path),
        NODE_ID,
        expected_generation=gs.human_review_generation(graph, NODE_ID),
        actor="release-owner",
        reason="operator capacity restored",
    )

    assert result["ok"] is True
    assert not (outside_archive / "attempts").exists()
    assert result["archived_sidecars"].get("_attempt_archive_dir") is None


def test_real_cli_resume_archives_old_evidence_and_is_one_shot(sandbox) -> None:
    harness, sprints = sandbox
    graph, graph_path = _stage_blocked_failed_attempt(harness, sprints)
    enter = getattr(gs, "enter_node_human_review", None)
    generation_of = getattr(gs, "human_review_generation", None)
    assert callable(enter) and callable(generation_of)
    enter(
        graph,
        NODE_ID,
        reason="operator_result_failed eight times",
        next_action="inspect and resume",
        writer="test_fixture",
    )
    old_repair_generation = int(graph["nodes"][0].get("repair_attempts") or 0)
    gs.save_graph(graph_path, graph)
    generation = generation_of(graph, NODE_ID)

    eval_json = sprints / f"{SID}.{NODE_ID}-eval.json"
    eval_md = sprints / f"{SID}.{NODE_ID}-eval.md"
    eval_json.write_text(
        json.dumps({"verdict": "PASS", "eval_generation": old_repair_generation}),
        encoding="utf-8",
    )
    eval_md.write_text("# stale evaluation\n\nPASS\n", encoding="utf-8")

    env = dict(os.environ)
    env.update(
        {
            "HARNESS_DIR": str(harness),
            "SOLAR_HARNESS_DIR": str(harness),
            "HARNESS_SPRINTS_DIR": str(sprints),
            "SOLAR_GATE_LEDGER": "1",
        }
    )
    cmd = [
        sys.executable,
        str(LIB / "graph_node_dispatcher.py"),
        "resume-human-review",
        "--graph",
        str(graph_path),
        "--node",
        NODE_ID,
        "--generation",
        str(generation),
        "--actor",
        "release-owner",
        "--reason",
        "operator capacity restored",
    ]
    first = subprocess.run(cmd, text=True, capture_output=True, env=env, timeout=30)

    assert first.returncode == 0, first.stdout + first.stderr
    payload = json.loads(first.stdout)
    assert payload["ok"] is True
    assert payload["from_status"] == "needs_human_review"
    assert payload["status"] == "pending"
    assert payload["generation"] == generation
    assert not eval_json.exists()
    assert not eval_md.exists()
    assert not (sprints / f"{SID}.{NODE_ID}-handoff.md").exists()
    assert payload["archived_sidecars"]

    persisted = gs.load_graph(graph_path)
    node = persisted["nodes"][0]
    assert gs.node_status(persisted, NODE_ID) == "pending"
    assert int(node["repair_attempts"]) == old_repair_generation + 1
    assert node["repair_context"]["trigger"] == "explicit_human_resume"
    assert node["human_review"]["state"] == "resumed"
    ledger_rows = [
        json.loads(line)
        for line in (sprints / f"{SID}.gate-ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    resume_rows = [row for row in ledger_rows if row.get("writer") == "resume_human_review"]
    assert resume_rows
    assert resume_rows[-1]["author"]["type"] == "human"
    assert resume_rows[-1]["human_review_generation"] == generation

    second = subprocess.run(cmd, text=True, capture_output=True, env=env, timeout=30)
    assert second.returncode == 2
    second_payload = json.loads(second.stdout)
    assert second_payload["ok"] is False
    assert second_payload["reason"] == "node_not_waiting_for_human_review"


def test_monitor_and_status_server_do_not_classify_human_review_as_active() -> None:
    monitor_active = _literal_set(HARNESS / "tools" / "solar-autopilot-monitor.py", "ACTIVE_STATUSES")
    status_active = _literal_set(LIB / "symphony" / "status-server.py", "_ACTIVE_SPRINT_STATUSES")

    assert "needs_human_review" not in monitor_active
    assert "needs_human_review" not in status_active


def test_coordinator_never_delegates_human_decision_to_planner() -> None:
    coordinator = (HARNESS / "coordinator.sh").read_text(encoding="utf-8")
    start = coordinator.index("handle_needs_human() {")
    end = coordinator.index("\n}\n", start) + 3
    handler = coordinator[start:end]

    assert 'dispatch_to_planner "$sid" "needs_human"' not in handler
    assert '"awaiting_human_decision"' in handler
