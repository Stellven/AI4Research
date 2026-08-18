"""Adversarial tests for the CI gate itself.

The gate decides whether a pull request may merge, so anything that lets a
failure through it is a hole in every other test at once. These cases are
written from the attacker's side: each one is a way somebody could make a real
failure look like a pass, and each must block.

Every case here corresponds to a bypass that was present and demonstrated
before it was closed. They are regression tests, not hypotheticals.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GATE = REPO_ROOT / "scripts" / "check-test-baseline.py"
LANES = REPO_ROOT / "tests" / "ci_lanes.json"
BASELINE = REPO_ROOT / "tests" / "ci_baseline.json"
CENSUS = REPO_ROOT / "scripts" / "check-test-census.py"
SHARD_RUNNER = REPO_ROOT / "scripts" / "run-test-shard.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "solar-ci.yml"

BLOCK = 1


def write_junit(path: Path, suite: str, cases: list[tuple[str, str, str | None]]) -> Path:
    """cases: (classname, name, failure message or None)."""
    body = []
    for classname, name, failure in cases:
        if failure is None:
            body.append(f'  <testcase classname="{classname}" name="{name}"/>')
        else:
            body.append(
                f'  <testcase classname="{classname}" name="{name}">'
                f'<failure message="{failure}">detail</failure></testcase>'
            )
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<testsuite name="{suite}">\n' + "\n".join(body) + "\n</testsuite>\n",
        encoding="utf-8",
    )
    return path


def write_lanes(path: Path, shards: dict[str, int]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": "solar.tests.lanes.v1",
                "shards": shards,
                "lanes": {},
                "assignments": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def write_baseline(path: Path, entries: list[str]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": "solar.tests.baseline.v1",
                "count": len(entries),
                "known_failures": [{"test": e, "reason": "recorded"} for e in entries],
            }
        ),
        encoding="utf-8",
    )
    return path


def run_gate(junits: list[Path], baseline: Path, lanes: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(GATE), *[str(j) for j in junits],
         "--baseline", str(baseline), "--lanes", str(lanes), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture()
def world(tmp_path: Path):
    """A two-shard run where p.b::t2 is the one known failure."""
    lanes = write_lanes(tmp_path / "lanes.json", {"pytest": 2})
    baseline = write_baseline(tmp_path / "baseline.json", ["p.b::t2"])
    base = write_baseline(tmp_path / "base.json", ["p.b::t2"])
    s0 = write_junit(tmp_path / "s0.xml", "pytest-0",
                     [("p.a", "t1", None), ("p.b", "t2", "known")])
    s1 = write_junit(tmp_path / "s1.xml", "pytest-1", [("p.c", "t3", None)])
    return {"dir": tmp_path, "lanes": lanes, "baseline": baseline, "base": base,
            "s0": s0, "s1": s1}


def test_unchanged_run_passes(world):
    """The control. Without this the other cases prove nothing."""
    result = run_gate([world["s0"], world["s1"]], world["baseline"], world["lanes"],
                      "--base-baseline", str(world["base"]))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_pull_request_cannot_whitelist_the_failure_it_introduced(world):
    """The baseline lives in the branch, so a branch can edit it.

    Breaking a test and adding it to tests/ci_baseline.json in the same commit
    is the cheapest possible way to defeat this gate, and it looks like an
    ordinary baseline update in review.
    """
    write_junit(world["s0"], "pytest-0", [("p.a", "t1", "I broke it"), ("p.b", "t2", "known")])
    write_baseline(world["baseline"], ["p.a::t1", "p.b::t2"])

    result = run_gate([world["s0"], world["s1"]], world["baseline"], world["lanes"],
                      "--base-baseline", str(world["base"]))
    assert result.returncode == BLOCK
    assert "baseline additions: p.a::t1" in result.stderr


def test_deleting_a_failing_test_does_not_pass(world):
    """Removing the test removes the failure, which must not read as a fix."""
    write_junit(world["s0"], "pytest-0", [("p.a", "t1", None)])

    result = run_gate([world["s0"], world["s1"]], world["baseline"], world["lanes"],
                      "--base-baseline", str(world["base"]))
    assert result.returncode == BLOCK
    assert "stale baseline entries: p.b::t2" in result.stderr


def test_renaming_a_failing_test_does_not_pass(world):
    """A rename is a deletion and an addition, and both must surface."""
    write_junit(world["s0"], "pytest-0",
                [("p.a", "t1", None), ("p.b", "t2_renamed", "known")])

    result = run_gate([world["s0"], world["s1"]], world["baseline"], world["lanes"],
                      "--base-baseline", str(world["base"]))
    assert result.returncode == BLOCK
    assert "stale baseline entries: p.b::t2" in result.stderr
    assert "new failures: p.b::t2_renamed" in result.stderr


def test_a_missing_shard_is_not_a_pass(world):
    """A shard that dies writes no JUnit and therefore reports no failures.

    An aggregate case-count floor does not catch this when the lost shard is
    small, so the expected shard set is named, not counted.
    """
    result = run_gate([world["s0"]], world["baseline"], world["lanes"],
                      "--base-baseline", str(world["base"]))
    assert result.returncode == BLOCK
    assert "missing shards: pytest-1" in result.stderr


def test_a_shard_the_manifest_does_not_declare_is_rejected(world):
    """Matrix and manifest drifting apart changes coverage silently."""
    extra = write_junit(world["dir"] / "s9.xml", "pytest-9", [("p.z", "t9", None)])

    result = run_gate([world["s0"], world["s1"], extra], world["baseline"], world["lanes"],
                      "--base-baseline", str(world["base"]))
    assert result.returncode == BLOCK
    assert "unexpected shards: pytest-9" in result.stderr


def test_a_test_that_now_passes_must_leave_the_baseline(world):
    """A green test still recorded as red is a hole it can regress into."""
    write_junit(world["s0"], "pytest-0", [("p.a", "t1", None), ("p.b", "t2", None)])

    result = run_gate([world["s0"], world["s1"]], world["baseline"], world["lanes"],
                      "--base-baseline", str(world["base"]))
    assert result.returncode == BLOCK
    assert "unrecorded fixes: p.b::t2" in result.stderr


def test_malformed_junit_blocks_instead_of_being_skipped(world):
    """Unparseable results are absent results, and absent results are not green."""
    world["s1"].write_text("<testsuite name='pytest-1'><testcase", encoding="utf-8")

    result = run_gate([world["s0"], world["s1"]], world["baseline"], world["lanes"],
                      "--base-baseline", str(world["base"]))
    assert result.returncode == BLOCK
    assert "unreadable JUnit" in result.stderr


def test_the_same_test_reported_by_two_shards_blocks(world):
    """Shards must partition the suite.

    If they overlap, a test can pass in one shard and fail in another, and any
    count taken across them is meaningless.
    """
    write_junit(world["s1"], "pytest-1", [("p.c", "t3", None), ("p.a", "t1", None)])

    result = run_gate([world["s0"], world["s1"]], world["baseline"], world["lanes"],
                      "--base-baseline", str(world["base"]))
    assert result.returncode == BLOCK
    assert "duplicate identities: p.a::t1" in result.stderr


@pytest.mark.parametrize("reverse", [False, True], ids=["red-second", "red-first"])
def test_a_test_failing_in_any_shard_is_not_green(world, reverse):
    """When two shards disagree about a test, red wins.

    Both orderings are exercised on purpose. With the files in one order the
    last record happens to be the failing one and any merge rule at all looks
    correct; only the other order proves the rule is "red wins" rather than
    "last one seen wins". The first version of this test checked one order and
    a mutation that deleted the rule survived it.
    """
    write_junit(world["s1"], "pytest-1",
                [("p.c", "t3", None), ("p.a", "t1", "red over here")])
    junits = [world["s1"], world["s0"]] if reverse else [world["s0"], world["s1"]]

    result = run_gate(junits, world["baseline"], world["lanes"],
                      "--base-baseline", str(world["base"]))
    assert result.returncode == BLOCK
    assert "new failures: p.a::t1" in result.stderr


def test_running_without_a_base_baseline_blocks(world):
    """Omitting the comparison is itself a way to disable the addition check."""
    result = run_gate([world["s0"], world["s1"]], world["baseline"], world["lanes"])
    assert result.returncode == BLOCK
    assert "no base-branch baseline" in result.stderr


def test_bootstrap_escape_hatch_is_explicit(world):
    """The one pull request introducing the baseline has nothing to compare to.

    That case is legitimate exactly once, so it needs a flag a reviewer can see
    in the diff rather than silently degrading to no check.
    """
    result = run_gate([world["s0"], world["s1"]], world["baseline"], world["lanes"],
                      "--allow-baseline-bootstrap")
    assert result.returncode == 0, result.stdout + result.stderr


def test_baseline_entries_may_be_removed(world):
    """The ratchet has to turn. Shrinking the baseline is the point."""
    write_junit(world["s0"], "pytest-0", [("p.a", "t1", None), ("p.b", "t2", None)])
    write_baseline(world["baseline"], [])

    result = run_gate([world["s0"], world["s1"]], world["baseline"], world["lanes"],
                      "--base-baseline", str(world["base"]))
    assert result.returncode == 0, result.stdout + result.stderr


def test_workflow_matrix_matches_the_lane_manifest():
    """The matrix and tests/ci_lanes.json must declare the same shards.

    They are written in different files in different languages, so nothing but
    a check keeps them together, and if they drift the gate either demands a
    shard that never runs or accepts one nobody declared.
    """
    yaml = pytest.importorskip("yaml")
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    matrix = workflow["jobs"]["test-suite"]["strategy"]["matrix"]["include"]
    from_workflow = {f"{entry['lane']}-{entry['shard']}" for entry in matrix}

    shards = json.loads(LANES.read_text(encoding="utf-8"))["shards"]
    from_manifest = {f"{lane}-{i}" for lane, n in shards.items() for i in range(n)}

    assert from_workflow == from_manifest

    for entry in matrix:
        assert entry["of"] == shards[entry["lane"]], entry


def test_every_matrix_entry_declares_its_lane_size():
    """`--of` decides how files are dealt; a wrong value silently drops tests."""
    yaml = pytest.importorskip("yaml")
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for entry in workflow["jobs"]["test-suite"]["strategy"]["matrix"]["include"]:
        assert 0 <= entry["shard"] < entry["of"], entry


def test_shipped_baseline_and_lane_manifest_parse():
    """The files CI depends on must be readable by the tools that read them."""
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert baseline["schema"] == "solar.tests.baseline.v1"
    assert baseline["count"] == len(baseline["known_failures"])
    identities = [entry["test"] for entry in baseline["known_failures"]]
    assert len(identities) == len(set(identities)), "duplicate baseline entries"
    assert all(entry["reason"] for entry in baseline["known_failures"])

    lanes = json.loads(LANES.read_text(encoding="utf-8"))
    assert lanes["schema"] == "solar.tests.lanes.v1"
    assert lanes["shards"]
    for entry in lanes["assignments"]:
        assert entry["glob"] and entry["lane"] and entry["reason"], entry
        assert entry["lane"] in lanes["lanes"], entry


def test_gate_scripts_are_executable_and_compile():
    for script in (GATE, CENSUS, SHARD_RUNNER):
        assert script.is_file(), script
        subprocess.run([sys.executable, "-m", "py_compile", str(script)], check=True)


def _run_shard(tmp_path: Path, lane: str, junit_name: str = "out.xml"):
    junit = tmp_path / junit_name
    proc = subprocess.run(
        [
            sys.executable,
            str(SHARD_RUNNER),
            "--lane",
            lane,
            "--shard",
            "0",
            "--of",
            "1",
            "--junit",
            str(junit),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    return proc, junit


def _load_shard_runner():
    spec = importlib.util.spec_from_file_location("shard_runner", SHARD_RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_subprocess_shard_with_red_tests_still_exits_zero(tmp_path):
    """A shard reports; the gate judges.

    The script lane is red on every current run, so this exercises the real
    thing rather than a fixture. Exiting non-zero here put nine failure
    annotations on every pull request whose gate verdict was clean, which
    teaches people that a red annotation carries no information.
    """
    proc, junit = _run_shard(tmp_path, "script")
    assert junit.is_file(), proc.stderr
    assert 'failures="0"' not in junit.read_text(encoding="utf-8"), (
        "this test only means something while the script lane is red"
    )
    assert proc.returncode == 0, proc.stdout[-2000:]


def test_a_pytest_shard_with_red_tests_still_exits_zero(tmp_path):
    """The pytest lane has its own exit path, and six of the nine shards use it.

    Written after the subprocess-lane version above survived a mutation that
    restored `return result.returncode` in run_pytest: one test covering one of
    two lanes reads as covering both.
    """
    # run_pytest hard-codes --timeout, which is a usage error without this
    # plugin, and a usage error is exit 4 rather than the exit 1 this test is
    # about. requirements/ci.txt pins it, so CI always has it.
    pytest.importorskip("pytest_timeout")
    module = _load_shard_runner()
    red = tmp_path / "test_red.py"
    red.write_text("def test_fails():\n    assert False\n", encoding="utf-8")
    junit = tmp_path / "pytest-0.xml"

    code = module.run_pytest([str(red)], junit, [], "pytest-0")

    assert junit.is_file()
    assert 'failures="1"' in junit.read_text(encoding="utf-8")
    assert code == 0


def test_a_pytest_shard_that_never_ran_fails(tmp_path):
    """Exit 4 is a usage error: pytest never got far enough to report anything.

    Only 0, 1 and 5 mean the run itself worked. Folding every code into success
    would turn a mis-invoked shard into a green job with no results.
    """
    module = _load_shard_runner()
    junit = tmp_path / "pytest-0.xml"

    code = module.run_pytest(["--not-a-real-flag"], junit, [], "pytest-0")

    assert code != 0


def test_a_shard_that_writes_no_cases_fails(tmp_path):
    """The other half of the rule: silence is not success.

    Without this, relaxing the exit code would turn a shard that died before
    writing anything into a green job. The gate's missing-shard verdict is the
    second line of defence, not the first.
    """
    junit = tmp_path / "empty.xml"
    junit.write_text('<?xml version="1.0" ?><testsuite name="script-0" tests="0"/>', "utf-8")
    proc = subprocess.run(
        [sys.executable, "-c", CHECK_REPORTED.format(runner=SHARD_RUNNER, junit=junit)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("1"), proc.stdout


CHECK_REPORTED = (
    "import importlib.util,sys;"
    "s=importlib.util.spec_from_file_location('shard', r'{runner}');"
    "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
    "import pathlib;print(m._reported(pathlib.Path(r'{junit}')))"
)
