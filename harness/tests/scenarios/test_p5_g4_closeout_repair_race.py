"""G4 UI-rung run 3 (trigger seam) — repair archival must not fail closeout.

Evidence (p5-g4-ui-rung-20260710T204856Z, also G3 run 12's
failed_contract_closeout): S2's builder DID deliver its handoff — the
deterministic gate consumed it at 21:02:46 and the repair flow ARCHIVED it
to <sid>.S2-handoff.repair1.<ts>.md in the same second — then the
operator's contract closeout ran at 21:02:50, looked for the canonical
handoff, found it "missing", failed the task
(completed_without_required_artifacts, exit 67) and jailed the only
builder for its 900s contract-closeout cooldown. The starved pool then fed
the assign/reset ping-pong (bounded separately at 7a044416). The operator
was punished for work that was already consumed.

Fix under test: _pm_closeout_status accepts a repair-archived copy of the
expected artifact (<stem>.repair*<suffix>, non-empty, not older than the
task's submitted_at) as PROOF OF DELIVERY — acknowledged in
recovered_artifacts, never copied back (the repair flow archived it
deliberately). Shares the SOLAR_PM_CLOSEOUT_RECOVERY kill switch with the
P2 nested-write net.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]


def _load_pm_dispatch(harness_dir: Path):
    lib = str(_HARNESS / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    spec = importlib.util.spec_from_file_location(
        "g4_closeout_pm_dispatch", _HARNESS / "tools" / "pm_dispatch.py"
    )
    mod = importlib.util.module_from_spec(spec)
    old = os.environ.get("HARNESS_DIR")
    os.environ["HARNESS_DIR"] = str(harness_dir)
    try:
        spec.loader.exec_module(mod)
    finally:
        if old is None:
            os.environ.pop("HARNESS_DIR", None)
        else:
            os.environ["HARNESS_DIR"] = old
    mod.SPRINTS_DIR = harness_dir / "sprints"
    return mod


SID = "sprint-g4-closeout-race"


def _record(submitted_at: str = "") -> dict:
    rec = {
        "task_id": f"pm-{SID}-S2-abc",
        "sprint_id": SID,
        "node_id": "S2",
        "requested_role": "builder",
    }
    if submitted_at:
        rec["submitted_at"] = submitted_at
    return rec


@pytest.fixture()
def pm(tmp_path):
    (tmp_path / "sprints").mkdir(parents=True)
    return _load_pm_dispatch(tmp_path), tmp_path / "sprints"


class TestRepairArchivedCloseout:
    def test_repair_archived_handoff_counts_as_delivered(self, pm):
        """The run-3 replay: canonical handoff archived by repair seconds
        before closeout — closeout must pass, artifact acknowledged, and the
        canonical file NOT resurrected."""
        mod, sprints = pm
        archived = sprints / f"{SID}.S2-handoff.repair1.20260710T210246Z.md"
        archived.write_text("# handoff\n\nreal delivered work\n", encoding="utf-8")
        earlier = (datetime.datetime.now(datetime.timezone.utc)
                   - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        closeout = mod._pm_closeout_status(_record(submitted_at=earlier))

        assert closeout["ok"] is True, closeout
        recovered = closeout.get("recovered_artifacts") or []
        assert any("archived_by_repair" in r for r in recovered), closeout
        assert not (sprints / f"{SID}.S2-handoff.md").exists(), (
            "the archived handoff must be acknowledged, never copied back"
        )

    def test_stale_archive_from_before_this_task_does_not_count(self, pm):
        mod, sprints = pm
        archived = sprints / f"{SID}.S2-handoff.repair1.20260101T000000Z.md"
        archived.write_text("# old generation handoff\n", encoding="utf-8")
        old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=6)
        os.utime(archived, (old.timestamp(), old.timestamp()))
        recent = (datetime.datetime.now(datetime.timezone.utc)
                  - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        closeout = mod._pm_closeout_status(_record(submitted_at=recent))

        assert closeout["ok"] is False, closeout

    def test_no_archive_still_fails_closeout(self, pm):
        mod, _sprints = pm
        closeout = mod._pm_closeout_status(_record())
        assert closeout["ok"] is False
        assert closeout["missing_artifacts"], closeout

    def test_kill_switch_disables_archive_acceptance(self, pm, monkeypatch):
        mod, sprints = pm
        (sprints / f"{SID}.S2-handoff.repair1.20260710T210246Z.md").write_text(
            "# handoff\n", encoding="utf-8"
        )
        monkeypatch.setenv("SOLAR_PM_CLOSEOUT_RECOVERY", "0")
        closeout = mod._pm_closeout_status(_record())
        assert closeout["ok"] is False, closeout

    def test_canonical_present_needs_no_recovery(self, pm):
        mod, sprints = pm
        (sprints / f"{SID}.S2-handoff.md").write_text("# handoff\n", encoding="utf-8")
        closeout = mod._pm_closeout_status(_record())
        assert closeout["ok"] is True
        assert "recovered_artifacts" not in closeout, closeout
