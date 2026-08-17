#!/usr/bin/env python3
"""run-test-shard.py — run one deterministic slice of one test lane.

CI runs the whole suite, not a hand-picked subset, so it has to be split across
matrix jobs.  The split must be deterministic: if shard 3 holds a different set
of files on the base run than on the head run, comparing the two is meaningless.
Files are therefore sorted and dealt round-robin, which depends only on which
files exist.

Lanes come from tests/ci_lanes.json (see scripts/check-test-census.py):

  pytest   every test-named .py not assigned elsewhere, run under pytest
  shell    bash tests
  script   test_*.py written as a program with main(), run by the interpreter
  excluded not run; each entry carries the reason it cannot run in public CI

Every lane writes JUnit XML, because the regression gate consumes one format.

Exit code is the runner's, except pytest's exit 5 ("no tests collected"), which
is translated to 0: an empty shard is a normal outcome of round-robin dealing.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPO_ROOT / "tests"

PY_PATTERNS = ("test_*.py", "*_test.py")
SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "fixtures",
    "quarantine",
    "outputs",
    ".codex-tmp",
}

PYTEST_NO_TESTS_COLLECTED = 5
LOG_TAIL_LINES = 40
USAGE_EXIT = 2

# Per-test ceiling. One hung test must not consume a shard's whole budget: the
# shard would then be killed by the job timeout and write no JUnit at all, and a
# shard that reports nothing is indistinguishable from a shard with nothing to
# report. A timed-out test is recorded as red, which is the honest answer.
DEFAULT_TEST_TIMEOUT = 300

# Same idea for the whole-file lanes, but a shell test is a whole file rather
# than one case, and the release tests legitimately take minutes because they
# clone the repository. Generous, and still bounded.
DEFAULT_FILE_TIMEOUT = 900


def load_assignments(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("assignments", [])


def lane_of(rel: str, assignments: list[dict[str, str]]) -> str:
    """First matching glob wins, so specific exclusions precede broad lanes."""
    for entry in assignments:
        if fnmatch.fnmatch(rel, entry["glob"]):
            return entry["lane"]
    return "pytest" if rel.endswith(".py") else "unassigned"


def discover(lane: str, assignments: list[dict[str, str]]) -> list[str]:
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(TESTS_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            is_py = any(fnmatch.fnmatch(filename, pattern) for pattern in PY_PATTERNS)
            if not is_py and not filename.endswith(".sh"):
                continue
            rel = Path(dirpath, filename).relative_to(REPO_ROOT).as_posix()
            if lane_of(rel, assignments) == lane:
                found.append(rel)
    return sorted(found)


# A shard reports; the gate judges. Exiting non-zero merely because tests are red
# put nine "Process completed with exit code 1" annotations on every pull request
# even when the gate's verdict was clean, which trains people to read a red
# annotation as meaningless. The shard therefore succeeds when it produced
# results and fails only when it did not: no document, an empty one, or one that
# will not parse. A shard that dies without writing is still caught twice, here
# and again by the gate's missing-shard verdict, which keys on the suite name
# inside the document rather than on the artifact's file name.
def _reported(junit: Path) -> int:
    try:
        tree = ET.parse(junit)
    except (OSError, ET.ParseError) as exc:
        print(f"::error::shard produced no readable JUnit at {junit}: {exc}", flush=True)
        return 1
    if not any(tree.getroot().iter("testcase")):
        print(f"::error::shard wrote {junit} but it contains no test cases", flush=True)
        return 1
    return 0


# pytest exit codes: 0 all passed, 1 tests failed, 2 interrupted, 3 internal
# error, 4 usage error, 5 nothing collected. Only 0, 1 and 5 mean the run itself
# worked; the rest mean pytest never got far enough to report, so they stay
# fatal here.
PYTEST_RAN = frozenset({0, 1, PYTEST_NO_TESTS_COLLECTED})


def run_pytest(files: list[str], junit: Path, extra: list[str], suite: str) -> int:
    junit.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit}",
            f"--timeout={DEFAULT_TEST_TIMEOUT}",
            # The gate identifies a shard by the testsuite name inside the
            # document, not by the file name, so a lost or renamed artifact
            # cannot pass itself off as a shard that ran.
            "-o",
            f"junit_suite_name={suite}",
            *extra,
            *files,
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    if result.returncode not in PYTEST_RAN:
        print(f"::error::pytest exited {result.returncode}; the shard did not run", flush=True)
        return result.returncode
    if result.returncode == PYTEST_NO_TESTS_COLLECTED:
        return 0
    return _reported(junit)


# Characters XML 1.0 forbids outright. Shell tests print terminal control codes
# and occasionally raw binary; writing those into JUnit produces a document the
# gate cannot parse, which loses the whole shard rather than one test's log.
_XML_ILLEGAL = re.compile(r"[^\x09\x0a\x0d\x20-퟿-�\U00010000-\U0010ffff]")


def _xml_safe(text: str) -> str:
    return _XML_ILLEGAL.sub("", text)


def run_subprocess_lane(
    files: list[str], junit: Path, argv0: list[str], lane: str, suite: str, timeout: int
) -> int:
    """Run each file as its own process and emit pytest-shaped JUnit.

    One testcase per file: these lanes have no finer-grained identity to report,
    and the regression gate keys on identity, so the identity has to be stable.

    Everything runs from the repository root. Nine shell tests used to need
    harness/ instead, because they self-located with `$0/..` from back when the
    suite lived at harness/tests/; they now resolve harness/ explicitly, and two
    full runs confirmed no file needs a different working directory.
    """
    root = ET.Element("testsuite", name=suite, tests=str(len(files)))
    failures = 0
    for rel in files:
        started = time.monotonic()
        timed_out = False
        # start_new_session puts the test in its own process group so the
        # timeout can kill everything it spawned. Killing only the direct child
        # is not enough: these tests start servers and git clones that inherit
        # the output pipes, and the wait for those pipes to close never returns.
        # That turns a per-file timeout into a hang, which is the exact failure
        # it was added to prevent.
        proc = subprocess.Popen(
            [*argv0, str(REPO_ROOT / rel)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            output, _ = proc.communicate(timeout=timeout)
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            returncode = 124
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
            output, _ = proc.communicate()
        classname = rel.rsplit(".", 1)[0].replace("/", ".")
        case = ET.SubElement(
            root,
            "testcase",
            classname=classname,
            # The lane, not the shard. Test identity must not change when the
            # files are dealt differently, or the baseline stops matching.
            name=lane,
            time=f"{time.monotonic() - started:.3f}",
        )
        if returncode == 0:
            print(f"[PASS] {rel}", flush=True)
            continue
        failures += 1
        label = f"timed out after {timeout}s" if timed_out else f"exit {returncode}"
        print(f"[FAIL {label}] {rel}", flush=True)
        node = ET.SubElement(case, "failure", message=label)
        node.text = _xml_safe("\n".join((output or "").strip().splitlines()[-LOG_TAIL_LINES:]))
    root.set("failures", str(failures))
    junit.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(junit, encoding="utf-8", xml_declaration=True)
    return _reported(junit)


def main() -> int:
    parser = argparse.ArgumentParser(prog="run-test-shard.py")
    parser.add_argument("--shard", type=int, default=0, help="0-based shard index")
    parser.add_argument("--of", type=int, default=1, help="total number of shards")
    parser.add_argument("--lane", choices=("pytest", "shell", "script"), default="pytest")
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--lanes", type=Path, default=TESTS_ROOT / "ci_lanes.json")
    parser.add_argument(
        "--file-timeout",
        type=int,
        default=DEFAULT_FILE_TIMEOUT,
        help="seconds a single shell or script test may run before it is killed and recorded red",
    )
    parser.add_argument("pytest_args", nargs="*", help="extra args passed to pytest")
    args = parser.parse_args()

    if not 0 <= args.shard < args.of:
        print(f"::error::shard {args.shard} is outside 0..{args.of - 1}", file=sys.stderr)
        return USAGE_EXIT

    files = discover(args.lane, load_assignments(args.lanes))
    mine = files[args.shard :: args.of]
    print(f"lane {args.lane} shard {args.shard}/{args.of}: {len(mine)} of {len(files)} files")
    if not mine:
        return 0

    suite = f"{args.lane}-{args.shard}"
    if args.lane == "pytest":
        return run_pytest(mine, args.junit, args.pytest_args, suite)
    argv0 = ["bash"] if args.lane == "shell" else [sys.executable]
    return run_subprocess_lane(mine, args.junit, argv0, args.lane, suite, args.file_timeout)


if __name__ == "__main__":
    raise SystemExit(main())
