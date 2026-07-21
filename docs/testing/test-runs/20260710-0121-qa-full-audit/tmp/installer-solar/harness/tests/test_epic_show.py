"""Tests for `solar-harness epic show` (S04 N5)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cli.epic_show_cmd import (
    SCHEMA_VERSION,
    EpicShowError,
    build_payload,
    derive_blocked_by,
    main,
    render_tree,
    validate_payload,
)


EPIC_ID = "epic-test-show-fixture"
SID_PREFIX = "sprint-test-show-fixture"

CHILD_SIDS = [
    f"{SID_PREFIX}-s01-requirements",
    f"{SID_PREFIX}-s02-architecture",
    f"{SID_PREFIX}-s03-core-runtime",
    f"{SID_PREFIX}-s04-orchestration-ui",
    f"{SID_PREFIX}-s05-verification-release",
]


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def epic_dir(tmp_path: Path) -> Path:
    """Build a 5-child fixture epic with realistic shape."""
    sprints = tmp_path / "sprints"
    sprints.mkdir()

    epic_payload = {
        "schema_version": "solar.epic.v1",
        "epic_id": EPIC_ID,
        "title": "# Test Epic",
        "priority": "P0",
        "created_at": "2026-05-20T00:00:00Z",
        "child_sprints": CHILD_SIDS,
        "status": "active",
    }
    _write(sprints / f"{EPIC_ID}.epic.json", epic_payload)

    epic_graph = {
        "schema_version": "solar.epic.task_graph.v1",
        "epic_id": EPIC_ID,
        "nodes": [
            {"id": "S01", "child_sprint_id": CHILD_SIDS[0], "depends_on": []},
            {"id": "S02", "child_sprint_id": CHILD_SIDS[1], "depends_on": ["S01"]},
            {"id": "S03", "child_sprint_id": CHILD_SIDS[2], "depends_on": ["S02"]},
            {"id": "S04", "child_sprint_id": CHILD_SIDS[3], "depends_on": ["S02"]},
            {"id": "S05", "child_sprint_id": CHILD_SIDS[4], "depends_on": ["S03", "S04"]},
        ],
    }
    _write(sprints / f"{EPIC_ID}.task_graph.json", epic_graph)

    _write(sprints / f"{CHILD_SIDS[0]}.status.json", {
        "id": CHILD_SIDS[0], "status": "passed", "phase": "complete",
        "handoff_to": "evaluator", "target_role": "evaluator", "priority": "P0",
        "updated_at": "2026-05-20T01:00:00Z", "history": [],
    })
    _write(sprints / f"{CHILD_SIDS[1]}.status.json", {
        "id": CHILD_SIDS[1], "status": "passed", "phase": "complete",
        "handoff_to": "evaluator", "target_role": "evaluator", "priority": "P0",
        "updated_at": "2026-05-20T02:00:00Z", "history": [],
    })
    _write(sprints / f"{CHILD_SIDS[2]}.status.json", {
        "id": CHILD_SIDS[2], "status": "active", "phase": "implementing",
        "handoff_to": "builder_main", "target_role": "builder_main", "priority": "P0",
        "updated_at": "2026-05-20T03:00:00Z", "history": [],
    })
    _write(sprints / f"{CHILD_SIDS[3]}.status.json", {
        "id": CHILD_SIDS[3], "status": "active", "phase": "planning_complete",
        "handoff_to": "builder_main", "target_role": "builder_main", "priority": "P0",
        "updated_at": "2026-05-20T04:00:00Z", "history": [],
    })
    _write(sprints / f"{CHILD_SIDS[4]}.status.json", {
        "id": CHILD_SIDS[4], "status": "queued", "phase": "epic_waiting_dependency",
        "handoff_to": "planner", "target_role": "planner", "priority": "P0",
        "updated_at": "2026-05-20T05:00:00Z",
        "history": [
            {
                "ts": "2026-05-20T05:00:00Z",
                "event": "autopilot_epic_child_dependency_blocked",
                "blocked_by": [CHILD_SIDS[2], CHILD_SIDS[3]],
            }
        ],
    })

    return sprints


def test_build_payload_lists_all_five_children(epic_dir: Path) -> None:
    payload = build_payload(EPIC_ID, epic_dir)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["epic_id"] == EPIC_ID
    assert payload["child_count"] == 5
    sids = [c["sprint_id"] for c in payload["children"]]
    assert sids == CHILD_SIDS


def test_payload_schema_validation_passes(epic_dir: Path) -> None:
    payload = build_payload(EPIC_ID, epic_dir)
    errors = validate_payload(payload)
    assert errors == [], f"validation errors: {errors}"


def test_blocked_by_surfaces_from_history(epic_dir: Path) -> None:
    payload = build_payload(EPIC_ID, epic_dir)
    s05 = next(c for c in payload["children"] if c["sprint_id"] == CHILD_SIDS[4])
    assert s05["blocked_by"] == [CHILD_SIDS[2], CHILD_SIDS[3]]


def test_blocked_by_empty_for_passed_children(epic_dir: Path) -> None:
    payload = build_payload(EPIC_ID, epic_dir)
    s01 = next(c for c in payload["children"] if c["sprint_id"] == CHILD_SIDS[0])
    assert s01["blocked_by"] == []


def test_blocked_by_from_dependency_policy_takes_priority(epic_dir: Path) -> None:
    """Explicit blocks_until in dependency_policy must override history."""
    sid = CHILD_SIDS[4]
    path = epic_dir / f"{sid}.status.json"
    data = json.loads(path.read_text())
    data["dependency_policy"] = {"blocks_until": ["explicit-dep-a", "explicit-dep-b"]}
    _write(path, data)

    payload = build_payload(EPIC_ID, epic_dir)
    s05 = next(c for c in payload["children"] if c["sprint_id"] == sid)
    assert s05["blocked_by"] == ["explicit-dep-a", "explicit-dep-b"]


def test_blocked_by_falls_back_to_epic_graph(epic_dir: Path) -> None:
    """When no dependency_policy and no history.blocked_by, fall back to graph depends_on."""
    sid = CHILD_SIDS[4]
    path = epic_dir / f"{sid}.status.json"
    data = json.loads(path.read_text())
    data["history"] = []
    data.pop("dependency_policy", None)
    _write(path, data)

    payload = build_payload(EPIC_ID, epic_dir)
    s05 = next(c for c in payload["children"] if c["sprint_id"] == sid)
    assert sorted(s05["blocked_by"]) == sorted([CHILD_SIDS[2], CHILD_SIDS[3]])


def test_render_tree_includes_all_children(epic_dir: Path) -> None:
    payload = build_payload(EPIC_ID, epic_dir)
    tree = render_tree(payload)
    assert "Epic: " + EPIC_ID in tree
    for sid in CHILD_SIDS:
        suffix = sid.replace(SID_PREFIX + "-", "")
        assert suffix in tree
    assert "└─" in tree
    assert "├─" in tree


def test_render_tree_shows_blocked_by_short_form(epic_dir: Path) -> None:
    payload = build_payload(EPIC_ID, epic_dir)
    tree = render_tree(payload)
    s05_line = [line for line in tree.splitlines() if "s05" in line][0]
    assert "s03-core-runtime" in s05_line
    assert "s04-orchestration-ui" in s05_line


def test_missing_epic_raises(tmp_path: Path) -> None:
    with pytest.raises(EpicShowError, match="epic file not found"):
        build_payload("epic-does-not-exist", tmp_path)


def test_main_default_text_mode_exit_zero(epic_dir: Path, capsys) -> None:
    rc = main([EPIC_ID, "--sprints-dir", str(epic_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert EPIC_ID in out
    assert "s05-verification-release" in out


def test_main_json_mode_emits_schema_v1(epic_dir: Path, capsys) -> None:
    rc = main([EPIC_ID, "--json", "--sprints-dir", str(epic_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["child_count"] == 5
    assert validate_payload(payload) == []


def test_main_validate_only(epic_dir: Path, capsys) -> None:
    rc = main([EPIC_ID, "--validate-only", "--sprints-dir", str(epic_dir)])
    assert rc == 0
    assert "schema_ok" in capsys.readouterr().out


def test_main_missing_epic_exits_two(tmp_path: Path, capsys) -> None:
    rc = main(["epic-missing", "--sprints-dir", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "epic file not found" in err


def test_validate_payload_catches_missing_field() -> None:
    bad = {"schema_version": SCHEMA_VERSION, "epic_id": "x"}
    errs = validate_payload(bad)
    assert any("children" in e or "child_count" in e for e in errs)


def test_validate_payload_catches_child_field_type() -> None:
    bad = {
        "schema_version": SCHEMA_VERSION,
        "epic_id": "x",
        "status": "active",
        "child_count": 1,
        "children": [
            {"sprint_id": "x", "status": "active", "blocked_by": "not-a-list"}
        ],
    }
    errs = validate_payload(bad)
    assert any("blocked_by not list" in e for e in errs)


def test_derive_blocked_by_handles_dict_entries() -> None:
    """blocks_until entries can be either strings or {sprint_id: ...} dicts."""
    status = {
        "dependency_policy": {
            "blocks_until": [
                {"sprint_id": "dep-x"},
                "dep-y",
                {"sid": "dep-z"},
            ]
        }
    }
    assert derive_blocked_by(status, None, "self") == ["dep-x", "dep-y", "dep-z"]


def test_real_chain_via_subprocess(epic_dir: Path) -> None:
    """DoD #1 真实调用链: invoke the module exactly as the shell wrapper would."""
    script = Path(__file__).resolve().parents[1] / "lib" / "cli" / "epic_show_cmd.py"
    result = subprocess.run(
        [sys.executable, str(script), EPIC_ID, "--json", "--sprints-dir", str(epic_dir)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["child_count"] == 5
    assert any(c["blocked_by"] for c in payload["children"])
