"""Bounded deliverables must not become five-child Epics because of length."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


_HARNESS = Path(__file__).resolve().parents[2]
_ENTRYPOINT = _HARNESS / "solar-harness.sh"

_BOUNDED_LINE_STATS_REQUEST = (
    "Build a dependency-free Python command-line utility named line_stats.py. "
    "It must read complete UTF-8 text from standard input and print exactly one "
    "newline-terminated JSON object with three integer keys: line_count (Python "
    "splitlines count), word_count (whitespace-delimited tokens), and "
    "character_count (Unicode code points including whitespace). Empty input must "
    "produce all zeros. Add self-contained pytest coverage for empty input, "
    "multiple lines, repeated whitespace, and Unicode through both function and "
    "subprocess CLI behavior. Add a README with a runnable stdin example and the "
    "exact counting definitions. Work only in the current project, run the tests, "
    "and leave the implementation, tests, README, and evidence ready for "
    "independent evaluation."
)

_GENUINE_EPIC_REQUEST = (
    "Redesign the Solar platform across the intake, planner, runtime, dashboard, "
    "and release subsystems. Split the work into multiple PRDs and an explicit "
    "dependency DAG, implement the independent workstreams in parallel, and close "
    "the parent only after end-to-end verification and migration evidence."
)

_MULTILINE_SINGLE_DELIVERABLE = """Build one dependency-free Python file named checksum.py.
Read bytes from standard input and print one SHA-256 digest.
Document the exact input/output contract in one README.
Add subprocess tests for empty, binary, and Unicode-derived byte inputs."""


def _classifier_source() -> str:
    source = _ENTRYPOINT.read_text(encoding="utf-8")
    start = source.index("should_epic_decompose_request() {")
    end = source.index("\n}\n", start) + 2
    return source[start:end]


def _classify(request: str) -> str:
    script = f"""
set -u
HARNESS_DIR="$2"
{_classifier_source()}
if should_epic_decompose_request "$1"; then
  printf epic
else
  printf sprint
fi
"""
    env = os.environ.copy()
    env.update(
        {
            "SOLAR_EPIC_AUTO_DECOMPOSE": "1",
            "SOLAR_EPIC_MIN_CHARS": "420",
            "SOLAR_EPIC_MIN_LINES": "4",
            "SOLAR_EPIC_MIN_SIGNALS": "3",
            "SOLAR_WORKFLOW_ROUTER": "0",
        }
    )
    result = subprocess.run(
        ["bash", "-c", script, "rc9-epic-classifier", request, str(_HARNESS)],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=True,
    )
    return result.stdout


def test_detailed_single_deliverable_remains_one_sprint():
    assert len(_BOUNDED_LINE_STATS_REQUEST) >= 420
    assert _classify(_BOUNDED_LINE_STATS_REQUEST) == "sprint"


def test_multiline_single_deliverable_remains_one_sprint():
    assert len(_MULTILINE_SINGLE_DELIVERABLE.splitlines()) == 4
    assert _classify(_MULTILINE_SINGLE_DELIVERABLE) == "sprint"


def test_multi_workstream_platform_request_remains_an_epic():
    assert _classify(_GENUINE_EPIC_REQUEST) == "epic"
