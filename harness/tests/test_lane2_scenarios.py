#!/usr/bin/env python3
"""test_lane2_scenarios.py — red-before-green gate for the Lane 2 fake-operator catalog.

Independence guard #1: a scenario proves nothing unless it has been demonstrated RED. For every
scenario-backed class (``verified_here`` = the whole class; ``partial`` = the one exercisable
half) this test runs the real hermetic pipeline twice via ``run_scenario.run_scenario``:

* GREEN (real code, guard active)     -> all ``expect`` assertions satisfied -> report.passed
* RED   (scenario's ``fault`` injected) -> the class reproduces -> NOT report.passed

A scenario that passes both, or fails both, is not discriminating and fails this test. The pairing
IS the red-before-green evidence, executed in CI on every run (no network, no quota).

The catalog integrity test keeps every class honest on the INTEGRATED tree (spec-review round 2
F5). A class is one of:

* ``verified_here`` — a scenario in THIS branch's engine red-green proves it (points at a file).
* ``partial``       — a scenario proves one half; the row must name what is NOT covered
                      (``pending_remainder``) so it cannot masquerade as full coverage.
* ``verified_lane_1`` / ``verified_lane_0_5`` — proven by another lane's committed suite; the row
                      must cite the real tests (``verified_by``: ``branch@commit path::fn``). These
                      are NOT runnable from this worktree (the seam lives on the other branch), so
                      they are excluded from the red-green gate but must carry citations.
* ``pending_lane_N``— retiring seam unbuilt; the row must name the missing ``required_seam``.
* ``delegated_lane_6`` — owned by the installability track.

So the 30-class ledger cannot silently claim coverage it does not have.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
SCENARIOS_DIR = TESTS_DIR / "scenarios"
CATALOG = SCENARIOS_DIR / "catalog.json"

sys.path.insert(0, str(TESTS_DIR))
import run_scenario as rs  # noqa: E402 — after path setup

# Statuses that carry a runnable red-green scenario in THIS branch's engine.
SCENARIO_BACKED = ("verified_here", "partial")
# Statuses whose proof lives in another lane's committed suite (cite, don't run here).
CROSS_LANE_VERIFIED = ("verified_lane_1", "verified_lane_0_5", "verified_lane_5")


def _scenario_gated_files() -> list[Path]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    files = []
    for entry in catalog["classes"]:
        if entry["status"] in SCENARIO_BACKED:
            assert entry["scenario"], f"class {entry['class']} is {entry['status']} but has no scenario file"
            files.append(SCENARIOS_DIR / entry["scenario"])
    return files


SCENARIO_GATED = _scenario_gated_files()


@pytest.mark.parametrize("scenario_path", SCENARIO_GATED, ids=[p.name for p in SCENARIO_GATED])
def test_scenario_green_passes(scenario_path: Path):
    scenario = rs.load_scenario(scenario_path)
    report = rs.run_scenario(scenario, red=False)
    assert report["passed"], (
        f"GREEN run of {scenario_path.name} should PASS but did not.\n"
        f"facts={json.dumps(report['facts'], indent=2, default=str)}\n"
        f"checks={json.dumps(report['checks'], indent=2, default=str)}"
    )


@pytest.mark.parametrize("scenario_path", SCENARIO_GATED, ids=[p.name for p in SCENARIO_GATED])
def test_scenario_red_fails(scenario_path: Path):
    scenario = rs.load_scenario(scenario_path)
    assert scenario.get("fault"), f"{scenario_path.name} has no fault block; cannot prove it is red-able"
    report = rs.run_scenario(scenario, red=True)
    assert not report["passed"], (
        f"RED run of {scenario_path.name} should FAIL (the class must reproduce when the fault is "
        f"injected) but every expect still passed — the scenario is not discriminating.\n"
        f"facts={json.dumps(report['facts'], indent=2, default=str)}\n"
        f"checks={json.dumps(report['checks'], indent=2, default=str)}"
    )


def test_catalog_is_complete_and_honest():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    classes = catalog["classes"]
    seen = {c["class"] for c in classes}
    assert seen == set(range(1, 31)), f"catalog must cover classes 1..30, missing/extra: {seen ^ set(range(1,31))}"

    valid_status = {
        "verified_here", "partial", "verified_lane_1", "verified_lane_0_5", "verified_lane_5",
        "pending_lane_0", "pending_lane_1", "pending_lane_3", "pending_lane_5",
        "delegated_lane_6",
    }
    for entry in classes:
        cls, status = entry["class"], entry["status"]
        assert status in valid_status, f"class {cls} bad status {status}"

        if status in SCENARIO_BACKED:
            # A scenario-backed row must point at a real runnable scenario file
            # (the red-green gate above actually executes it).
            path = SCENARIOS_DIR / entry["scenario"]
            assert path.exists(), f"class {cls} scenario missing: {path}"

        if status == "partial":
            # A partial row cannot masquerade as full coverage: it must name the half
            # that is NOT exercisable here.
            assert entry.get("pending_remainder"), f"class {cls} is partial but names no pending_remainder"

        if status in CROSS_LANE_VERIFIED:
            # A cross-lane 'verified' row cannot claim coverage without citing the
            # committed tests that prove it (branch@commit path::fn), and it carries no
            # local scenario (the retiring seam lives on the other branch).
            cites = entry.get("verified_by")
            assert cites and all(isinstance(x, str) and x.strip() for x in cites), (
                f"class {cls} is {status} but cites no verified_by test paths"
            )
            assert entry["scenario"] is None, (
                f"class {cls} is {status}; its scenario must be null (proof is cross-lane, not runnable here)"
            )

        if status.startswith("pending_lane_"):
            # An honest pending row names the missing seam so it cannot masquerade as covered.
            assert entry.get("required_seam"), f"class {cls} is {status} but names no required_seam"


def test_summary_matches_rows():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    summary = catalog["summary"]
    rows_by_status: dict[str, list[int]] = {}
    for c in catalog["classes"]:
        rows_by_status.setdefault(c["status"], []).append(c["class"])

    # Every status that appears in rows must be reflected 1:1 in the summary.
    for status, classes in rows_by_status.items():
        assert status in summary, f"summary is missing the {status} bucket"
        assert sorted(summary[status]) == sorted(classes), (
            f"catalog.summary[{status}]={summary[status]} is out of sync with the rows {sorted(classes)}"
        )

    # pending_lane_0 is a free-form sub-note bucket (the class-19 allowlist half), not a
    # status row; every OTHER summary bucket must correspond to real rows so it cannot go stale.
    non_row_buckets = {"pending_lane_0"}
    for bucket in summary:
        if bucket in non_row_buckets:
            continue
        assert bucket in rows_by_status, f"summary bucket {bucket} has no rows on the integrated tree"
