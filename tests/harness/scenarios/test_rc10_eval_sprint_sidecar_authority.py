"""rc.10 live-red regression: evaluator reads of planner sprint sidecars.

The installed todo_report run produced a certified graph whose P1 read_scope
included ``sprints/<sid>.design.md`` and ``sprints/<sid>.plan.md``.  Those are
planner-owned files under the current sprint namespace, but the A5 evaluator
snapshot resolved them below ``<sid>/workdir/sprints`` and blocked truthful
work with ``DECLARED_EVAL_BYTES_OUTSIDE_ROOT``.

This suite keeps A5 fail-closed: only top-level sidecars belonging to the exact
current sprint may become read authority.  Foreign sprint names, traversal,
and symlinks remain invalid, and accepted sidecar bytes remain digest-bound.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
LIB = HARNESS / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import graph_node_dispatcher as gnd  # noqa: E402
import graph_scheduler as gs  # noqa: E402
import plan_validator as pv  # noqa: E402


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    harness.mkdir()
    sprints.mkdir()
    workflows = harness / "config" / "workflows"
    workflows.mkdir(parents=True)
    contract_name = "pm.generic.v1.workflow.json"
    (workflows / contract_name).write_text(
        (HARNESS / "config" / "workflows" / contract_name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gs, "HARNESS_DIR", harness)
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)
    return harness, sprints


def _graph(sid: str, node: dict) -> dict:
    graph = {
        "sprint_id": sid,
        "workflow_contract_id": "pm.generic.v1",
        "workflow_contract_version": "1.0",
        "plan_certificate": {
            "schema": "solar.plan_certificate.v1",
            "verdict": "PASS",
        },
        "nodes": [node],
        "node_results": {str(node["id"]): {"status": node["status"]}},
        "gate_results": {},
    }
    graph["plan_certificate"]["graph_hash"] = pv.plan_certificate_hash(graph)
    return graph


def _stage_output(sprints: Path, sid: str) -> None:
    output = sprints / sid / "workdir" / "workspace" / "todo_report.py"
    output.parent.mkdir(parents=True)
    output.write_text("print('ok')\n", encoding="utf-8")


def _node(sid: str) -> dict:
    return {
        "id": "P1",
        "status": "reviewing",
        "depends_on": [],
        "read_scope": [
            f"sprints/{sid}.design.md",
            f"sprints/{sid}.plan.md",
        ],
        "write_scope": ["workspace/todo_report.py"],
        "proof_obligations": [],
    }


def test_current_sprint_planner_sidecars_are_exact_read_authority(
    sandbox: tuple[Path, Path],
) -> None:
    _harness, sprints = sandbox
    sid = "sprint-rc10-sidecar-live-shape"
    _stage_output(sprints, sid)
    (sprints / f"{sid}.design.md").write_text("# Design\n", encoding="utf-8")
    (sprints / f"{sid}.plan.md").write_text("# Plan\n", encoding="utf-8")
    node = _node(sid)

    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, _graph(sid, node))

    assert snapshot["ok"] is True, snapshot
    sidecar_rows = [
        row
        for row in snapshot["rows"]
        if row.get("authority") == "sprint_sidecar" and row.get("scope") == "read"
    ]
    assert [row["declared"] for row in sidecar_rows] == [
        f"sprints/{sid}.design.md",
        f"sprints/{sid}.plan.md",
    ]
    assert all(row.get("resolved_root") == "sprint_sidecar" for row in sidecar_rows)
    assert all(row.get("exists") is True and row.get("sha256") for row in sidecar_rows)


def test_snapshot_metadata_is_restored_after_frozen_graph_projection(
    sandbox: tuple[Path, Path],
) -> None:
    """A scheduler projection may drop transient node metadata, but the exact
    retained snapshot sidecar remains the evaluator's byte authority."""
    _harness, sprints = sandbox
    sid = "sprint-rc10-snapshot-projection-restore"
    _stage_output(sprints, sid)
    (sprints / f"{sid}.design.md").write_text("# Design\n", encoding="utf-8")
    (sprints / f"{sid}.plan.md").write_text("# Plan\n", encoding="utf-8")
    node = _node(sid)
    graph = _graph(sid, node)
    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)
    assert snapshot["ok"] is True, snapshot
    eval_payload = {
        "artifact_snapshot_schema": snapshot["schema"],
        "artifact_snapshot_path": snapshot["path"],
        "artifact_snapshot_digest": snapshot["snapshot_digest"],
    }

    node.pop("eval_artifact_snapshot")
    result = gnd._validate_eval_artifact_snapshot(sid, node, graph, eval_payload)

    assert result["ok"] is True, result
    assert node["eval_artifact_snapshot"]["snapshot_digest"] == snapshot["snapshot_digest"]


def test_both_live_generic_control_plane_read_shapes_are_authorized(
    sandbox: tuple[Path, Path],
) -> None:
    _harness, sprints = sandbox
    sid = "sprint-rc10-control-plane-live-shapes"
    _stage_output(sprints, sid)
    suffixes = (
        "requirement_ir.json",
        "product-brief.md",
        "contract.md",
        "design.md",
        "plan.md",
        "task_graph.json",
    )
    for suffix in suffixes:
        if suffix == "task_graph.json":
            continue
        (sprints / f"{sid}.{suffix}").write_text(f"{suffix}\n", encoding="utf-8")
    node = _node(sid)
    node["read_scope"] = [f"sprints/{sid}.{suffix}" for suffix in suffixes]
    graph = _graph(sid, node)
    (sprints / f"{sid}.task_graph.json").write_text(
        json.dumps(graph, indent=2) + "\n",
        encoding="utf-8",
    )

    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)

    assert snapshot["ok"] is True, snapshot
    control_rows = [
        row
        for row in snapshot["rows"]
        if row.get("scope") == "read" and row.get("declared") in node["read_scope"]
    ]
    assert [row["declared"] for row in control_rows] == node["read_scope"]
    assert all(row.get("exists") is True and row.get("sha256") for row in control_rows)
    graph_row = next(
        row for row in control_rows if row["declared"].endswith(".task_graph.json")
    )
    assert graph_row["authority"] == "plan_certificate"
    assert graph_row["kind"] == "governed_graph"


def test_task_graph_runtime_mutation_does_not_invalidate_governed_snapshot(
    sandbox: tuple[Path, Path],
) -> None:
    _harness, sprints = sandbox
    sid = "sprint-rc10-governed-graph-runtime-drift"
    _stage_output(sprints, sid)
    node = _node(sid)
    node["read_scope"] = [f"sprints/{sid}.task_graph.json"]
    graph = _graph(sid, node)
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)
    eval_payload = {
        "artifact_snapshot_schema": snapshot["schema"],
        "artifact_snapshot_path": snapshot["path"],
        "artifact_snapshot_digest": snapshot["snapshot_digest"],
    }

    node["status"] = "reviewing"
    node["dispatch_id"] = "runtime-only-eval-dispatch"
    graph["node_results"][node["id"]]["status"] = "reviewing"
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    result = gnd._validate_eval_artifact_snapshot(sid, node, graph, eval_payload)

    assert result["ok"] is True, result


def test_task_graph_governed_mutation_invalidates_snapshot(
    sandbox: tuple[Path, Path],
) -> None:
    _harness, sprints = sandbox
    sid = "sprint-rc10-governed-graph-policy-drift"
    _stage_output(sprints, sid)
    node = _node(sid)
    node["read_scope"] = [f"sprints/{sid}.task_graph.json"]
    graph = _graph(sid, node)
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)
    eval_payload = {
        "artifact_snapshot_schema": snapshot["schema"],
        "artifact_snapshot_path": snapshot["path"],
        "artifact_snapshot_digest": snapshot["snapshot_digest"],
    }

    node["write_scope"] = ["workspace/changed.py"]
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    result = gnd._validate_eval_artifact_snapshot(sid, node, graph, eval_payload)

    assert result["ok"] is False, result
    assert result["reason"] == "eval_artifact_snapshot_changed"


def test_current_sprint_sidecar_mutation_invalidates_snapshot(
    sandbox: tuple[Path, Path],
) -> None:
    _harness, sprints = sandbox
    sid = "sprint-rc10-sidecar-byte-drift"
    _stage_output(sprints, sid)
    design = sprints / f"{sid}.design.md"
    design.write_text("# Design A\n", encoding="utf-8")
    (sprints / f"{sid}.plan.md").write_text("# Plan\n", encoding="utf-8")
    node = _node(sid)
    graph = _graph(sid, node)
    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)
    assert snapshot["ok"] is True, snapshot
    eval_payload = {
        "artifact_snapshot_schema": snapshot["schema"],
        "artifact_snapshot_path": snapshot["path"],
        "artifact_snapshot_digest": snapshot["snapshot_digest"],
    }

    design.write_text("# Design B\n", encoding="utf-8")
    result = gnd._validate_eval_artifact_snapshot(sid, node, graph, eval_payload)

    assert result["ok"] is False, result
    assert result["reason"] == "eval_artifact_snapshot_changed"


@pytest.mark.parametrize(
    "declared",
    [
        "sprints/sprint-foreign.design.md",
        "sprints/../outside.md",
    ],
)
def test_foreign_or_traversing_sprint_sidecar_is_rejected(
    sandbox: tuple[Path, Path], declared: str
) -> None:
    harness, sprints = sandbox
    sid = "sprint-rc10-sidecar-contained"
    _stage_output(sprints, sid)
    (sprints / "sprint-foreign.design.md").write_text("foreign\n", encoding="utf-8")
    (harness / "outside.md").write_text("outside\n", encoding="utf-8")
    node = _node(sid)
    node["read_scope"] = [declared]

    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, _graph(sid, node))

    assert snapshot["ok"] is False, snapshot
    assert any(
        item.get("code") == "DECLARED_EVAL_BYTES_OUTSIDE_ROOT"
        and item.get("declared") == declared
        for item in snapshot["violations"]
    )


def test_current_sprint_sidecar_symlink_is_rejected(
    sandbox: tuple[Path, Path],
) -> None:
    harness, sprints = sandbox
    sid = "sprint-rc10-sidecar-symlink"
    _stage_output(sprints, sid)
    outside = harness.parent / "outside-plan.md"
    outside.write_text("foreign\n", encoding="utf-8")
    (sprints / f"{sid}.plan.md").symlink_to(outside)
    node = _node(sid)
    node["read_scope"] = [f"sprints/{sid}.plan.md"]

    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, _graph(sid, node))

    assert snapshot["ok"] is False, snapshot
    assert snapshot["violations"]
    assert outside.read_text(encoding="utf-8") == "foreign\n"


def test_absolute_current_sprint_sidecar_declaration_is_rejected(
    sandbox: tuple[Path, Path],
) -> None:
    _harness, sprints = sandbox
    sid = "sprint-rc10-sidecar-absolute"
    _stage_output(sprints, sid)
    sidecar = sprints / f"{sid}.plan.md"
    sidecar.write_text("# Plan\n", encoding="utf-8")
    node = _node(sid)
    node["read_scope"] = [str(sidecar)]

    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, _graph(sid, node))

    assert snapshot["ok"] is False, snapshot
    assert any(
        item.get("code") == "DECLARED_EVAL_BYTES_OUTSIDE_ROOT"
        and item.get("declared") == str(sidecar)
        for item in snapshot["violations"]
    )


def test_unknown_current_sprint_sidecar_suffix_is_rejected(
    sandbox: tuple[Path, Path],
) -> None:
    _harness, sprints = sandbox
    sid = "sprint-rc10-sidecar-unknown-kind"
    _stage_output(sprints, sid)
    undeclared_kind = sprints / f"{sid}.private.json"
    undeclared_kind.write_text('{"secret": false}\n', encoding="utf-8")
    node = _node(sid)
    declared = f"sprints/{sid}.private.json"
    node["read_scope"] = [declared]

    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, _graph(sid, node))

    assert snapshot["ok"] is False, snapshot
    assert any(
        item.get("code") == "DECLARED_EVAL_BYTES_OUTSIDE_ROOT"
        and item.get("declared") == declared
        for item in snapshot["violations"]
    )


def test_fixed_contract_graph_does_not_gain_generic_sidecar_authority(
    sandbox: tuple[Path, Path],
) -> None:
    _harness, sprints = sandbox
    sid = "sprint-rc10-sidecar-fixed-contract"
    _stage_output(sprints, sid)
    sidecar = sprints / f"{sid}.plan.md"
    sidecar.write_text("# Plan\n", encoding="utf-8")
    node = _node(sid)
    node["read_scope"] = [f"sprints/{sid}.plan.md"]
    graph = _graph(sid, node)
    graph["workflow_contract_id"] = "fixed.runtime.v1"

    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)

    assert not any(
        row.get("authority") == "sprint_sidecar"
        for row in snapshot["rows"]
    ), snapshot
    assert any(
        item.get("code") == "DECLARED_EVAL_BYTES_OUTSIDE_ROOT"
        and item.get("declared") == f"sprints/{sid}.plan.md"
        for item in snapshot["violations"]
    )


@pytest.mark.parametrize(
    "declared_template",
    [
        "sprints/./{sid}.plan.md",
        "sprints/{sid}.plan.md/",
    ],
)
def test_noncanonical_current_sprint_sidecar_spelling_is_rejected(
    sandbox: tuple[Path, Path], declared_template: str
) -> None:
    _harness, sprints = sandbox
    sid = "sprint-rc10-sidecar-exact-spelling"
    _stage_output(sprints, sid)
    (sprints / f"{sid}.plan.md").write_text("# Plan\n", encoding="utf-8")
    declared = declared_template.format(sid=sid)
    node = _node(sid)
    node["read_scope"] = [declared]

    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, _graph(sid, node))

    assert snapshot["ok"] is False, snapshot
    assert any(
        item.get("code") == "DECLARED_EVAL_BYTES_OUTSIDE_ROOT"
        and item.get("declared") == declared
        for item in snapshot["violations"]
    )
