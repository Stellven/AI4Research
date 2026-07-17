#!/usr/bin/env python3
"""P2 smoke-5 deterministic replay (fail bundle
p2-sprint-20260708-010049-wf-code-cli-smoke-failed-20260708T011537Z).

Live smoke 5 at 702db0c8 cleared every smoke-4 class (contracted graph, S1
terminal-passed, submitted+completed route records, AC-R5.2 clean) and failed
one rung higher: the S2 builder wrote its handoff with the EXACT expected
basename but nested it inside the sprint's own directory —
``sprints/<sid>/sprint-<sid>.S2-handoff.md`` instead of the flat
``sprints/sprint-<sid>.S2-handoff.md`` the dispatch instruction named (a
worker path-transcription slip; codex-cli-output.log line 6343 vs the correct
instruction at line 355). ``pm_dispatch complete`` then failed the contract
closeout (``completed_without_required_artifacts``, exit 67), S2 never reached
its evaluator, and S3 never dispatched.

The gate was RIGHT to refuse an absent canonical artifact — the fix is
deterministic, auditable recovery at the same seam: when an expected artifact
is missing but EXACTLY ONE non-empty file with the exact expected basename
exists inside the sprint's own tree (``SPRINTS_DIR/<sid>/**``), copy it to the
canonical path and report ``recovered_artifacts``. Zero or multiple matches
keep the failure; files outside the sprint tree (the worker's stray third
copy went to a path missing ``/home``) are never adopted; the recovery can
only fire where the closeout would otherwise FAIL, so no green path changes.
Kill-switch: SOLAR_PM_CLOSEOUT_RECOVERY=0.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
_HARNESS_LIB = str(_HARNESS / "lib")
_HARNESS_TOOLS = str(_HARNESS / "tools")
for entry in (_HARNESS_TOOLS, _HARNESS_LIB):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import pm_dispatch as pmd  # noqa: E402

SID = "sprint-20260708-010049-wf-code-cli-smoke"
HANDOFF = f"{SID}.S2-handoff.md"


def _builder_record() -> dict:
    return {"requested_role": "builder", "sprint_id": SID, "node_id": "S2"}


@pytest.fixture()
def sprints(tmp_path, monkeypatch):
    sprints_dir = tmp_path / "sprints"
    (sprints_dir / SID).mkdir(parents=True)
    monkeypatch.setattr(pmd, "SPRINTS_DIR", sprints_dir)
    monkeypatch.delenv("SOLAR_PM_CLOSEOUT_RECOVERY", raising=False)
    return sprints_dir


def test_nested_handoff_is_recovered_to_canonical_path(sprints):
    nested = sprints / SID / HANDOFF
    nested.write_text("# S2 handoff\nsmoke run + results\n", encoding="utf-8")
    closeout = pmd._pm_closeout_status(_builder_record())
    assert closeout["ok"] is True, closeout
    assert closeout.get("recovered_artifacts"), closeout
    recovery = closeout["recovered_artifacts"][0]
    assert recovery["recovered_from"] == str(nested)
    canonical = sprints / HANDOFF
    assert canonical.exists()
    assert canonical.read_text(encoding="utf-8") == nested.read_text(encoding="utf-8")
    # evidence preserved: the worker's original write is left in place
    assert nested.exists()


def test_canonical_artifact_present_reports_ok_without_recovery(sprints):
    (sprints / HANDOFF).write_text("# S2 handoff\n", encoding="utf-8")
    closeout = pmd._pm_closeout_status(_builder_record())
    assert closeout["ok"] is True
    assert not closeout.get("recovered_artifacts")


def test_missing_everywhere_still_fails(sprints):
    closeout = pmd._pm_closeout_status(_builder_record())
    assert closeout["ok"] is False
    assert closeout["missing_artifacts"] == [str(sprints / HANDOFF)]


def test_ambiguous_matches_keep_the_failure(sprints):
    (sprints / SID / HANDOFF).write_text("candidate one\n", encoding="utf-8")
    deeper = sprints / SID / "workdir"
    deeper.mkdir()
    (deeper / HANDOFF).write_text("candidate two\n", encoding="utf-8")
    closeout = pmd._pm_closeout_status(_builder_record())
    assert closeout["ok"] is False
    assert not (sprints / HANDOFF).exists()


def test_empty_nested_file_is_not_recovered(sprints):
    (sprints / SID / HANDOFF).write_text("", encoding="utf-8")
    closeout = pmd._pm_closeout_status(_builder_record())
    assert closeout["ok"] is False
    assert not (sprints / HANDOFF).exists()


def test_kill_switch_disables_recovery(sprints, monkeypatch):
    monkeypatch.setenv("SOLAR_PM_CLOSEOUT_RECOVERY", "0")
    (sprints / SID / HANDOFF).write_text("# S2 handoff\n", encoding="utf-8")
    closeout = pmd._pm_closeout_status(_builder_record())
    assert closeout["ok"] is False
    assert not (sprints / HANDOFF).exists()


def test_files_outside_the_sprint_tree_are_never_adopted(sprints):
    # the live worker's stray third copy went OUTSIDE the sprint tree
    # (a path missing /home); recovery must not go looking there.
    other = sprints.parent / "elsewhere"
    other.mkdir()
    (other / HANDOFF).write_text("stray copy\n", encoding="utf-8")
    closeout = pmd._pm_closeout_status(_builder_record())
    assert closeout["ok"] is False
    assert not (sprints / HANDOFF).exists()
