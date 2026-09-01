"""rc.9 SPLIT_OUTPUT_ROOT regression coverage.

The live rc.9 fixture wrote byte-identical files both to the user workspace
and to ``sprints/<sid>/workdir/workspace`` because its dispatch named both as
authoritative.  The product contract is now one-way:

    isolated sprint staging -> independent verification -> user workspace

These tests use the real RawIntent compiler, dispatch text helpers, manifest,
and filesystem publisher.  No mocked output is accepted as evidence.
"""
from __future__ import annotations

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

import artifact_manifest  # noqa: E402
import graph_node_dispatcher  # noqa: E402
import graph_scheduler  # noqa: E402


def test_workspace_binding_round_trip_and_sprint_lookup(tmp_path: Path) -> None:
    import workspace_binding

    harness = tmp_path / "harness"
    workspace = tmp_path / "project"
    sprints = harness / "sprints"
    workspace.mkdir()
    sprints.mkdir(parents=True)

    bound = workspace_binding.bind_active_workspace(harness, workspace)
    assert bound == workspace.resolve()
    assert workspace_binding.read_active_workspace(harness) == workspace.resolve()

    sid = "sprint-split-output-root"
    (sprints / f"{sid}.raw_intent.json").write_text(
        json.dumps({"context": {"repo": str(workspace)}}),
        encoding="utf-8",
    )
    assert workspace_binding.sprint_workspace_root(sprints, sid) == workspace.resolve()
    assert (
        workspace_binding.sprint_workspace_root(sprints, sid, harness_dir=harness)
        == workspace.resolve()
    )


def test_rawintent_consumer_preserves_the_user_workspace_as_repo_context(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / ".pm").mkdir()
    (workspace / ".pm" / "private-note.txt").write_text(
        "must not enter sprint staging\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.update(
        {
            "SOLAR_HARNESS_DIR": str(HARNESS),
            "HARNESS_DIR": str(HARNESS),
            "SOLAR_INTENT_GATEWAY_DIR": str(tmp_path / "intents"),
            "SOLAR_HARNESS_SPRINTS_DIR": str(tmp_path / "sprints"),
            "SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT": str(workspace),
        }
    )
    captured = subprocess.run(
        [
            sys.executable,
            str(LIB / "intent_gateway.py"),
            "capture",
            "--text",
            "Create tool.py in this workspace and test it.",
            "--source-channel",
            "cli_intake",
            "--repo",
            str(workspace),
            "--json",
        ],
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    intent_id = json.loads(captured.stdout)["intent_id"]
    consumed = subprocess.run(
        [
            sys.executable,
            str(LIB / "intent_consumer.py"),
            "consume",
            "--intent-id",
            intent_id,
            "--json",
        ],
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    sid = json.loads(consumed.stdout)["results"][0]["sprint_id"]
    requirement_ir = json.loads(
        (tmp_path / "sprints" / f"{sid}.requirement_ir.json").read_text(encoding="utf-8")
    )

    assert requirement_ir["source_inputs"]["repo_context"] == [str(workspace.resolve())]
    assert (workspace / ".pm" / "requirement_ir.json").is_file()
    staged_pm = tmp_path / "sprints" / sid / "workdir" / "workspace" / ".pm"
    assert json.loads((staged_pm / "requirement_ir.json").read_text(encoding="utf-8")) == json.loads(
        (workspace / ".pm" / "requirement_ir.json").read_text(encoding="utf-8")
    )
    assert not (staged_pm / "private-note.txt").exists()


def test_generic_dispatch_names_only_the_sprint_staging_root(tmp_path: Path, monkeypatch) -> None:
    sprints = tmp_path / "sprints"
    sid = "sprint-single-output-root"
    monkeypatch.setattr(graph_node_dispatcher, "SPRINTS_DIR", sprints)
    graph = {"workflow_contract_id": "pm.generic.v1"}
    node = {"id": "S1", "write_scope": ["workspace/tool.py"]}

    canonical = graph_node_dispatcher._canonical_output_paths_block(node)
    workdir = graph_node_dispatcher._generic_workdir_block(sid, graph)
    combined = canonical + "\n" + workdir

    assert "current repository/worktree" not in combined
    assert "sole" in combined.lower() or "only" in combined.lower()
    assert "do not mirror" in combined.lower()
    assert str(sprints / sid / "workdir") in combined


def _manifest_with_file_and_directory(tmp_path: Path) -> tuple[dict, Path]:
    staging = tmp_path / "sprints" / "sid" / "workdir"
    workspace_root = staging / "workspace"
    (workspace_root / "pkg").mkdir(parents=True)
    (workspace_root / "assets").mkdir(parents=True)
    (workspace_root / "pkg" / "tool.py").write_text("print('verified')\n", encoding="utf-8")
    (workspace_root / "assets" / "data.txt").write_text("verified data\n", encoding="utf-8")
    manifest = artifact_manifest.write_manifest(
        tmp_path / "sprints",
        "sid",
        {
            "id": "S1",
            "write_scope": ["workspace/pkg/tool.py", "workspace/assets/"],
        },
        generation=0,
        base_dir=staging,
        roots={"canonical": "workspace/"},
    )
    assert manifest is not None
    return manifest, staging


def test_verified_outputs_publish_once_into_the_user_workspace(tmp_path: Path) -> None:
    manifest, staging = _manifest_with_file_and_directory(tmp_path)
    user_workspace = tmp_path / "project"
    user_workspace.mkdir()

    result = artifact_manifest.publish_workspace_outputs(manifest, user_workspace)

    assert result["ok"] is True
    assert (user_workspace / "pkg" / "tool.py").read_text(encoding="utf-8") == "print('verified')\n"
    assert (user_workspace / "assets" / "data.txt").read_text(encoding="utf-8") == "verified data\n"
    assert not (user_workspace / "workspace").exists(), "publisher must not add a second workspace/ level"
    assert (staging / "workspace" / "pkg" / "tool.py").is_file(), "staging evidence remains intact"
    destinations = {Path(row["to"]) for row in result["published"]}
    assert user_workspace / "pkg" / "tool.py" in destinations
    assert user_workspace / "assets" / "data.txt" in destinations


def test_workspace_publish_fails_closed_on_traversal_and_symlinks(tmp_path: Path) -> None:
    user_workspace = tmp_path / "project"
    source_root = tmp_path / "staging"
    user_workspace.mkdir()
    source_root.mkdir()
    source = source_root / "payload.txt"
    source.write_text("do not escape\n", encoding="utf-8")
    traversal_manifest = {
        "rows": [
            {
                "declared": "workspace/../escaped.txt",
                "rel_path": "workspace/../escaped.txt",
                "path": str(source),
                "resolved_root": "canonical",
                "exists": True,
            }
        ]
    }

    traversal = artifact_manifest.publish_workspace_outputs(traversal_manifest, user_workspace)
    assert traversal["ok"] is False
    assert traversal["errors"]
    assert not (tmp_path / "escaped.txt").exists()

    link = source_root / "linked.txt"
    try:
        link.symlink_to(source)
    except OSError as exc:  # Windows CI may not grant symlink privilege.
        pytest.skip(f"symlink unavailable: {exc}")
    symlink_manifest = {
        "rows": [
            {
                "declared": "workspace/linked.txt",
                "rel_path": "workspace/linked.txt",
                "path": str(link),
                "resolved_root": "canonical",
                "exists": True,
            }
        ]
    }
    symlink_result = artifact_manifest.publish_workspace_outputs(symlink_manifest, user_workspace)
    assert symlink_result["ok"] is False
    assert not (user_workspace / "linked.txt").exists()


def test_dispatcher_publishes_only_when_active_and_sprint_workspaces_agree(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import workspace_binding

    _manifest, _staging = _manifest_with_file_and_directory(tmp_path)
    sprints = tmp_path / "sprints"
    harness = tmp_path / "harness"
    intended_workspace = tmp_path / "intended-project"
    foreign_workspace = tmp_path / "foreign-project"
    harness.mkdir()
    intended_workspace.mkdir()
    foreign_workspace.mkdir()
    (sprints / "sid.raw_intent.json").write_text(
        json.dumps({"context": {"repo": str(intended_workspace)}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(graph_node_dispatcher, "HARNESS_DIR", harness)
    monkeypatch.setattr(graph_node_dispatcher, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(graph_scheduler, "SPRINTS_DIR", sprints)
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")

    workspace_binding.bind_active_workspace(harness, foreign_workspace)
    mismatch = graph_node_dispatcher._publish_verified_node_outputs(
        "sid",
        {"id": "S1"},
        {"workflow_contract_id": "pm.generic.v1"},
    )
    assert mismatch["required"] is True
    assert mismatch["ok"] is False
    assert mismatch["reason"] == "workspace_binding_mismatch"
    assert not (foreign_workspace / "pkg" / "tool.py").exists()
    assert not (intended_workspace / "pkg" / "tool.py").exists()

    workspace_binding.bind_active_workspace(harness, intended_workspace)
    node = {
        "id": "S1",
        "status": "reviewing",
        "depends_on": [],
        "write_scope": ["workspace/pkg/tool.py", "workspace/assets/"],
        "proof_obligations": [],
    }
    graph = {
        "sprint_id": "sid",
        "workflow_contract_id": "pm.generic.v1",
        "workflow_contract_version": "1.0",
        "nodes": [node],
        "node_results": {"S1": {"status": "reviewing"}},
        "gate_results": {},
    }
    graph_path = sprints / "sid.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    (sprints / "sid.S1-handoff.md").write_text("verified work\n", encoding="utf-8")
    (sprints / "sid.S1-eval.md").write_text("independent evaluator pass\n", encoding="utf-8")
    (sprints / "sid.S1-eval.json").write_text(
        json.dumps({"node_id": "S1", "verdict": "PASS"}),
        encoding="utf-8",
    )
    graph_node_dispatcher._emit_node_proof_sidecars("sid", node)
    snapshot = graph_node_dispatcher._capture_eval_artifact_snapshot("sid", node, graph)
    assert snapshot["ok"] is True, snapshot
    eval_path = sprints / "sid.S1-eval.json"
    eval_payload = json.loads(eval_path.read_text(encoding="utf-8"))
    eval_payload.update(
        {
            "artifact_snapshot_schema": snapshot["schema"],
            "artifact_snapshot_path": snapshot["path"],
            "artifact_snapshot_digest": snapshot["snapshot_digest"],
        }
    )
    eval_path.write_text(json.dumps(eval_payload), encoding="utf-8")
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    reconciled = graph_node_dispatcher._reconcile_existing_dispatches(graph, graph_path)
    graph_scheduler.save_graph(graph_path, graph)
    (sprints / "sid.status.json").write_text(
        json.dumps({"status": "active", "phase": "running", "history": []}),
        encoding="utf-8",
    )
    graph_node_dispatcher._mark_parent_sprint_passed_if_ready(
        "sid",
        graph_scheduler.parent_ready_check(graph_scheduler.load_graph(graph_path)),
        False,
        graph_path=graph_path,
    )

    assert any(
        row.get("node") == "S1" and row.get("status") == "passed"
        for row in reconciled
    ), reconciled
    assert (intended_workspace / "pkg" / "tool.py").is_file()
    assert (sprints / "sid.S1-publish.json").is_file()
    publish = json.loads((sprints / "sid.S1-publish.json").read_text(encoding="utf-8"))
    assert len(publish["manifest_digest"]) == 64
    assert len(publish["published_digest"]) == 64
    receipt = graph_scheduler.load_graph(graph_path)["nodes"][0]["closeout_receipt"]
    assert receipt["publication"]["manifest_digest"] == receipt["manifest"]["content_digest"]
    assert receipt["publication"]["published_digest"] == publish["published_digest"]
