from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
LIB_ROOT = REPO_ROOT / "harness"
if str(LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(LIB_ROOT))

from lib import workspace_binding


def _write_sprint_records(
    sprints_dir: Path,
    sprint_id: str,
    *,
    raw_repo: str = "",
    workspace_root: str = "",
    repo_context: list[str] | None = None,
) -> None:
    sprints_dir.mkdir(parents=True, exist_ok=True)
    (sprints_dir / f"{sprint_id}.raw_intent.json").write_text(
        json.dumps({"context": {"repo": raw_repo}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    source_inputs = {}
    if workspace_root:
        source_inputs["workspace_root"] = workspace_root
    if repo_context:
        source_inputs["repo_context"] = repo_context
    (sprints_dir / f"{sprint_id}.requirement_ir.json").write_text(
        json.dumps(
            {
                "source_inputs": source_inputs,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_wf004_02_missing_binding(tmp_path: Path) -> None:
    harness_root = tmp_path / "harness"
    sprints_root = tmp_path / "sprints"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True)

    sprint_id = "wf004-02"
    _write_sprint_records(sprints_root, sprint_id, raw_repo=str(workspace_root))

    assert (
        workspace_binding.sprint_workspace_root(sprints_root, sprint_id, harness_dir=harness_root)
        is None
    )


def test_wf004_03_mismatched_binding(tmp_path: Path) -> None:
    harness_root = tmp_path / "harness"
    sprints_root = tmp_path / "sprints"
    authorized = tmp_path / "authorized"
    captured = tmp_path / "captured"
    authorized.mkdir()
    captured.mkdir()

    sprint_id = "wf004-03"
    workspace_binding.bind_active_workspace(harness_root, authorized)
    _write_sprint_records(sprints_root, sprint_id, raw_repo=str(captured))

    assert (
        workspace_binding.sprint_workspace_root(sprints_root, sprint_id, harness_dir=harness_root)
        is None
    )


def test_wf004_04_repo_context_capture(tmp_path: Path) -> None:
    harness_root = tmp_path / "harness"
    sprints_root = tmp_path / "sprints"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    sprint_id = "wf004-04"
    workspace_binding.bind_active_workspace(harness_root, workspace_root)
    _write_sprint_records(sprints_root, sprint_id, raw_repo=str(workspace_root))

    assert workspace_binding.sprint_workspace_root(
        sprints_root, sprint_id, harness_dir=harness_root
    ) == workspace_root


def test_wf004_05_explicit_prior_artifact_binding(tmp_path: Path) -> None:
    harness_root = tmp_path / "harness"
    sprints_root = tmp_path / "sprints"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    sprint_id = "wf004-05"
    workspace_binding.bind_active_workspace(harness_root, workspace_root)
    _write_sprint_records(sprints_root, sprint_id, workspace_root=str(workspace_root))

    assert workspace_binding.sprint_workspace_root(
        sprints_root, sprint_id, harness_dir=harness_root
    ) == workspace_root


def test_wf004_06_cross_workspace_rejection(tmp_path: Path) -> None:
    harness_root = tmp_path / "harness"
    sprints_root = tmp_path / "sprints"
    authorized = tmp_path / "authorized"
    captured_one = tmp_path / "captured-one"
    captured_two = tmp_path / "captured-two"
    authorized.mkdir()
    captured_one.mkdir()
    captured_two.mkdir()

    sprint_id = "wf004-06"
    workspace_binding.bind_active_workspace(harness_root, authorized)
    _write_sprint_records(
        sprints_root,
        sprint_id,
        raw_repo=str(captured_one),
        workspace_root=str(captured_two),
        repo_context=[str(captured_one), str(captured_two)],
    )

    assert (
        workspace_binding.sprint_workspace_root(sprints_root, sprint_id, harness_dir=harness_root)
        is None
    )
