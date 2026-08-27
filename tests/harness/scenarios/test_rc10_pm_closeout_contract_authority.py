"""rc.10 — PM closeout artifacts must come from the submission contract.

The installed Codex run ``rc10-12894c0b-installed-codex-ui-red`` exposed a
contract contradiction.  S3 was a logical Verifier graph node whose dispatch
allowed the declared product output plus the ordinary node handoff and
explicitly prohibited invented sidecars.  ``pm_dispatch`` nevertheless
inferred evaluator sidecars from the role name alone and rejected the
otherwise successful task at completion.

These tests keep graph-node execution distinct from the independent graph
evaluation phase.  They also require the exact closeout contract to be visible
in the worker dispatch and preserve legacy role-derived records that predate
the explicit contract field.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
for entry in (HARNESS / "tools", HARNESS / "lib"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import pm_dispatch as pmd  # noqa: E402
import graph_scheduler as gs  # noqa: E402


def _load_graph_dispatcher():
    spec = importlib.util.spec_from_file_location(
        "rc10_closeout_graph_node_dispatcher",
        HARNESS / "lib" / "graph_node_dispatcher.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gnd = _load_graph_dispatcher()


SID = "sprint-rc10-closeout-authority"


@pytest.fixture()
def sprints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "sprints"
    root.mkdir()
    monkeypatch.setattr(pmd, "SPRINTS_DIR", root)
    return root


def _names(paths: list[Path]) -> list[str]:
    return [path.name for path in paths]


def test_pm_dispatch_honors_runtime_harness_sprints_dir_without_solar_alias(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    harness_root = tmp_path / "harness"
    env = dict(os.environ)
    env.pop("SOLAR_HARNESS_SPRINTS_DIR", None)
    env["HARNESS_DIR"] = str(harness_root)
    env["HARNESS_SPRINTS_DIR"] = str(runtime_root)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(HARNESS / 'tools')!r}); "
                "import pm_dispatch; print(pm_dispatch.SPRINTS_DIR)"
            ),
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert Path(completed.stdout.strip()) == runtime_root


def test_logical_verifier_graph_node_requires_handoff_not_eval_sidecars(sprints: Path) -> None:
    record = {
        "requested_role": "evaluator",
        "task_type": "review",
        "closeout_kind": "graph_node_execution",
        "sprint_id": SID,
        "node_id": "S3",
    }

    assert _names(pmd._pm_expected_artifacts(record)) == [f"{SID}.S3-handoff.md"]


def test_archived_s3_shape_closes_with_handoff_and_without_invented_eval_sidecars(
    sprints: Path,
) -> None:
    handoff = sprints / f"{SID}.S3-handoff.md"
    handoff.write_text(
        "# S3 verifier handoff\n\nAll declared tests passed; review_decision.md was written.\n",
        encoding="utf-8",
    )
    record = {
        "requested_role": "evaluator",
        "task_type": "review",
        "closeout_kind": "graph_node_execution",
        "expected_artifacts": [str(handoff)],
        "sprint_id": SID,
        "node_id": "S3",
    }

    closeout = pmd._pm_closeout_status(record)

    assert closeout["ok"] is True, closeout
    assert closeout["missing_artifacts"] == []
    assert not (sprints / f"{SID}.S3-eval.md").exists()
    assert not (sprints / f"{SID}.S3-eval.json").exists()


def test_logical_planner_graph_node_also_uses_node_execution_handoff(sprints: Path) -> None:
    record = {
        "requested_role": "planner",
        "task_type": "planning",
        "closeout_kind": "graph_node_execution",
        "sprint_id": SID,
        "node_id": "S1",
    }

    assert _names(pmd._pm_expected_artifacts(record)) == [f"{SID}.S1-handoff.md"]


def test_independent_planner_closeout_authorizes_every_prompted_artifact(sprints: Path) -> None:
    record = {
        "requested_role": "planner",
        "task_type": "planning",
        "closeout_kind": "planner",
        "sprint_id": SID,
        "node_id": "N0",
    }

    assert _names(pmd._pm_expected_artifacts(record)) == [
        f"{SID}.design.md",
        f"{SID}.plan.md",
        f"{SID}.task_graph.json",
    ]


def test_independent_graph_evaluation_still_requires_eval_pair(sprints: Path) -> None:
    record = {
        "requested_role": "evaluator",
        "task_type": "graph_eval",
        "closeout_kind": "graph_eval",
        "sprint_id": SID,
        "node_id": "S3",
    }

    assert _names(pmd._pm_expected_artifacts(record)) == [
        f"{SID}.S3-eval.md",
        f"{SID}.S3-eval.json",
    ]


def test_secondary_graph_evaluator_uses_its_exact_peer_pair(sprints: Path) -> None:
    peer_md = sprints / f"{SID}.S3-eval-q2.md"
    peer_json = sprints / f"{SID}.S3-eval-q2.json"
    record = {
        "requested_role": "evaluator",
        "task_type": "graph_eval",
        "closeout_kind": "graph_eval",
        "expected_artifacts": [str(peer_md), str(peer_json)],
        "sprint_id": SID,
        "node_id": "S3",
    }

    assert pmd._pm_expected_artifacts(record) == [peer_md, peer_json]


def test_explicit_graph_eval_artifacts_cannot_escape_current_sprints_root(
    sprints: Path,
    tmp_path: Path,
) -> None:
    record = {
        "requested_role": "evaluator",
        "task_type": "graph_eval",
        "closeout_kind": "graph_eval",
        "expected_artifacts": [
            str(tmp_path / f"{SID}.S3-eval.md"),
            str(tmp_path / f"{SID}.S3-eval.json"),
        ],
        "sprint_id": SID,
        "node_id": "S3",
    }

    with pytest.raises(ValueError, match="expected_artifact_outside_sprints_root"):
        pmd._pm_expected_artifacts(record)


def test_quorum_evaluators_receive_distinct_pm_result_paths(sprints: Path) -> None:
    primary = pmd._pm_result_path_for_role(
        SID,
        "S3",
        "evaluator",
        "graph_eval",
        expected_artifacts=[str(sprints / f"{SID}.S3-eval.md")],
    )
    secondary = pmd._pm_result_path_for_role(
        SID,
        "S3",
        "evaluator",
        "graph_eval",
        expected_artifacts=[str(sprints / f"{SID}.S3-eval-q2.md")],
    )

    assert primary.name == f"{SID}.S3-eval.pm-result.md"
    assert secondary.name == f"{SID}.S3-eval-q2.pm-result.md"
    assert primary != secondary


def test_legacy_record_without_explicit_kind_preserves_role_contract(sprints: Path) -> None:
    record = {
        "requested_role": "evaluator",
        "sprint_id": SID,
        "node_id": "S3",
    }

    assert _names(pmd._pm_expected_artifacts(record)) == [
        f"{SID}.S3-eval.md",
        f"{SID}.S3-eval.json",
    ]


def test_dispatch_exposes_every_required_contract_artifact(sprints: Path) -> None:
    handoff = sprints / f"{SID}.S3-handoff.md"
    text = pmd.build_pm_dispatch_text(
        task_id="pm-closeout-visible",
        operator_id="operator-test",
        operator={"model": "test", "backend": "command", "persona": "builder"},
        objective="Verify the declared graph-node output.",
        sprint_id=SID,
        node_id="S3",
        result_path=str(sprints / f"{SID}.S3.pm-result.md"),
        expected_artifacts=[str(handoff)],
        closeout_kind="graph_node_execution",
    )

    assert "Closeout contract: `graph_node_execution`" in text
    assert f"- `{handoff}`" in text
    assert f"{SID}.S3-eval.md" not in text
    assert f"{SID}.S3-eval.json" not in text


def test_submit_persists_the_same_contract_shown_to_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "harness"
    sprints = root / "sprints"
    (root / "personas").mkdir(parents=True)
    sprints.mkdir()
    (root / "personas" / "builder.md").write_text("# Builder\n", encoding="utf-8")
    monkeypatch.setattr(pmd, "HARNESS_DIR", root)
    monkeypatch.setattr(pmd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(pmd, "PM_INBOX_DIR", root / "run" / "pm-inbox")
    monkeypatch.setattr(pmd, "OPERATOR_INBOX_DIR", root / "run" / "operator-inbox")
    monkeypatch.setattr(pmd, "OPERATOR_STATUS_DIR", root / "run" / "operator-status")
    monkeypatch.setattr(pmd, "PERSONAS_DIR", root / "personas")
    monkeypatch.setattr(
        pmd,
        "select_operator_by_role",
        lambda **_kwargs: (
            "operator-test",
            {
                "model": "test",
                "backend": "command",
                "provider": "openai",
                "persona": "builder",
            },
            "",
        ),
    )
    fake_runtime = types.ModuleType("operator_runtime")
    fake_runtime.submit = lambda _envelope: {  # type: ignore[attr-defined]
        "lease_id": "lease-test",
        "inbox_path": str(root / "run" / "operator-inbox" / "task.json"),
    }
    monkeypatch.setitem(sys.modules, "operator_runtime", fake_runtime)
    monkeypatch.setenv("SOLAR_PM_DISPATCH_ALLOW_DIRECT", "1")

    rc = pmd.cmd_submit(
        argparse.Namespace(
            role="evaluator",
            objective="Verify the graph node output.",
            operator="",
            sprint=SID,
            node="S3",
            task_type="review",
            closeout_kind="graph_node_execution",
            expected_artifact=[],
            context="",
            work_dir="",
            dry_run=False,
        )
    )

    assert rc == 0
    record_path = next((root / "run" / "pm-inbox").glob("pm-*.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    expected = [str(sprints / f"{SID}.S3-handoff.md")]
    assert record["task_type"] == "review"
    assert record["closeout_kind"] == "graph_node_execution"
    assert record["expected_artifacts"] == expected
    dispatch = Path(record["dispatch_file"]).read_text(encoding="utf-8")
    assert "Closeout contract: `graph_node_execution`" in dispatch
    assert f"- `{expected[0]}`" in dispatch


def test_graph_node_and_graph_eval_submitters_declare_distinct_closeout_kinds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        commands.append(list(cmd))
        return SimpleNamespace(
            returncode=0,
            stdout="task_id = pm-test\noperator = operator-test\ndispatch = dispatch.md\n",
            stderr="",
        )

    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.setattr(gnd, "_builder_operator_pool_enabled", lambda: True)
    monkeypatch.setattr(gnd, "_builder_operator_pool_allowed_for_pane", lambda _pane: True)
    monkeypatch.setattr(gnd, "build_dispatch_text", lambda *_args, **_kwargs: "# graph node\n")
    monkeypatch.setattr(gnd, "_inject_dispatch_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_broker_env", lambda _sid: {})
    monkeypatch.setattr(gnd.subprocess, "run", fake_run)

    node_result = gnd._submit_builder_to_operator_pool(
        item={"payload": {}},
        payload={"dispatch_role": "evaluator"},
        sid=SID,
        node={"id": "S3", "type": "review", "logical_operator": "Verifier"},
        node_id="S3",
        graph_path=str(tmp_path / "sprints" / f"{SID}.task_graph.json"),
        pane="operator-pool:builder.0",
        dispatch_id="dispatch-node",
        dry_run=True,
    )
    assert node_result["ok"] is True

    eval_dispatch = tmp_path / "eval-dispatch.md"
    eval_dispatch.write_text("# independent graph evaluation\n", encoding="utf-8")
    snapshot_path = tmp_path / "sprints" / f"{SID}.S3-eval-snapshot.json"
    published = tmp_path / "published" / "S3-output.json"
    published.parent.mkdir()
    published.write_text("{}\n", encoding="utf-8")
    snapshot = {
        "schema": gnd._EVAL_ARTIFACT_SNAPSHOT_SCHEMA,
        "sid": SID,
        "node_id": "S3",
        "generation": 0,
        "captured_at": "2026-08-17T00:00:00Z",
        "rows": [
            {
                "scope": "read",
                "authority": "published",
                "declared": "published/S3-output.json",
                "path": str(published),
                "exists": True,
                "unsafe": False,
            }
        ],
        "violations": [],
        "ok": True,
        "reason": "",
        "path": str(snapshot_path),
    }
    snapshot["snapshot_digest"] = gnd._eval_snapshot_digest(snapshot)
    snapshot_path.parent.mkdir(exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    eval_result = gnd._submit_eval_to_operator_pool(
        sid=SID,
        node_id="S3",
        graph_path=str(tmp_path / "sprints" / f"{SID}.task_graph.json"),
        pane="operator-pool:evaluator.0",
        dispatch_id="dispatch-eval",
        instruction_file=eval_dispatch,
        dry_run=True,
        eval_generation=3,
        eval_md_path=str(tmp_path / "sprints" / f"{SID}.S3-eval-q2.md"),
        eval_json_path=str(tmp_path / "sprints" / f"{SID}.S3-eval-q2.json"),
        artifact_snapshot=snapshot,
    )
    assert eval_result["ok"] is True

    node_cmd, eval_cmd = commands
    node_index = node_cmd.index("--closeout-kind")
    eval_index = eval_cmd.index("--closeout-kind")
    assert node_cmd[node_index + 1] == "graph_node_execution"
    assert eval_cmd[eval_index + 1] == "graph_eval"
    attempt_index = eval_cmd.index("--attempt-id")
    assert eval_cmd[attempt_index + 1] == "3"
    expected_indexes = [index for index, value in enumerate(eval_cmd) if value == "--expected-artifact"]
    assert [eval_cmd[index + 1] for index in expected_indexes] == [
        str(tmp_path / "sprints" / f"{SID}.S3-eval-q2.md"),
        str(tmp_path / "sprints" / f"{SID}.S3-eval-q2.json"),
    ]
    read_indexes = [index for index, value in enumerate(eval_cmd) if value == "--read-scope"]
    assert [eval_cmd[index + 1] for index in read_indexes] == [
        str(snapshot_path),
        str(published),
    ]


def test_graph_eval_submitter_refuses_tampered_snapshot_read_grants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_run(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("invalid snapshot must not reach pm_dispatch")

    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.setattr(gnd.subprocess, "run", fake_run)
    dispatch = tmp_path / "eval-dispatch.md"
    dispatch.write_text("# eval\n", encoding="utf-8")
    snapshot_path = tmp_path / "sprints" / f"{SID}.S3-eval-snapshot.json"
    snapshot_path.parent.mkdir()
    snapshot = {
        "schema": gnd._EVAL_ARTIFACT_SNAPSHOT_SCHEMA,
        "sid": SID,
        "node_id": "S3",
        "generation": 0,
        "rows": [{"path": str(tmp_path), "exists": True, "unsafe": False}],
        "violations": [],
        "ok": True,
        "path": str(snapshot_path),
    }
    snapshot["snapshot_digest"] = gnd._eval_snapshot_digest(snapshot)
    snapshot_path.write_text(json.dumps({**snapshot, "rows": []}), encoding="utf-8")

    result = gnd._submit_eval_to_operator_pool(
        sid=SID,
        node_id="S3",
        graph_path=str(tmp_path / "graph.json"),
        pane="operator-pool:evaluator.0",
        dispatch_id="dispatch-eval",
        instruction_file=dispatch,
        dry_run=False,
        artifact_snapshot=snapshot,
    )

    assert result["ok"] is False
    assert result["reason"] == "operator_pool_eval_snapshot_scope_invalid"
    assert called is False


def test_terminal_failure_recovery_is_generation_fenced_and_reopens_only_dependency_skips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    sprints.mkdir(parents=True)
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gs, "HARNESS_DIR", harness)
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)
    graph = {
        "sprint_id": SID,
        "nodes": [
            {"id": "S3", "status": "failed", "depends_on": [], "repair_attempts": 1},
            {
                "id": "S4",
                "status": "skipped",
                "depends_on": ["S3"],
                "skip_reason": "blocked_by_failed_dependency",
                "blocked_by_failed_dependency": ["S3"],
            },
            {
                "id": "S5",
                "status": "skipped",
                "depends_on": ["S4"],
                "skip_reason": "blocked_by_failed_dependency",
                "blocked_by_failed_dependency": ["S4"],
            },
            {"id": "manual-skip", "status": "skipped", "depends_on": ["S3"]},
        ],
        "node_results": {
            "S3": {"status": "failed"},
            "S4": {"status": "skipped"},
            "S5": {"status": "skipped"},
            "manual-skip": {"status": "skipped"},
        },
        "gate_results": {},
        "required_gates": [],
    }
    graph_path = sprints / f"{SID}.task_graph.json"
    gs.save_graph(graph_path, graph)

    mismatch = gnd.escalate_terminal_failure_to_human_review(
        graph_path,
        "S3",
        expected_repair_generation=0,
        actor="release-owner",
        reason="fixed evaluator sandbox",
    )
    assert mismatch["ok"] is False
    assert "generation_mismatch" in mismatch["reason"]
    assert gs.node_status(gs.load_graph(graph_path), "S3") == "failed"

    recovered = gnd.escalate_terminal_failure_to_human_review(
        graph_path,
        "S3",
        expected_repair_generation=1,
        actor="release-owner",
        reason="fixed evaluator sandbox",
    )
    assert recovered["ok"] is True
    assert recovered["reopened_descendants"] == ["S4", "S5"]
    saved = gs.load_graph(graph_path)
    assert gs.node_status(saved, "S3") == "needs_human_review"
    assert gs.node_status(saved, "S4") == "pending"
    assert gs.node_status(saved, "S5") == "pending"
    assert gs.node_status(saved, "manual-skip") == "skipped"

    replay = gnd.escalate_terminal_failure_to_human_review(
        graph_path,
        "S3",
        expected_repair_generation=1,
        actor="release-owner",
        reason="replayed owner action",
    )
    assert replay["ok"] is False
    assert "node_not_terminal_failed" in replay["reason"]


def test_human_review_history_keeps_generation_monotonic_after_terminal_projection() -> None:
    prior = {
        "schema_version": gs.HUMAN_REVIEW_SCHEMA_VERSION,
        "generation": 3,
        "state": "blocked",
        "reason": "previous bounded failure",
    }
    graph = {
        "sprint_id": SID,
        "nodes": [
            {
                "id": "S3",
                "status": "failed",
                "depends_on": [],
                "human_review_history": [prior],
            }
        ],
        "node_results": {"S3": {"status": "failed"}},
    }

    assert gs.human_review_generation(graph, "S3") == 3
    current = gs.enter_node_human_review(
        graph,
        "S3",
        reason="new terminal infrastructure failure",
        next_action="inspect and resume",
        writer="test_terminal_recovery",
        author_type="human",
    )

    assert current["generation"] == 4
