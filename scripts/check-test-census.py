#!/usr/bin/env python3
"""check-test-census.py — every test file must be accounted for by CI.

The failure mode this exists to prevent: the repository accumulated hundreds of
test files while CI ran a handful of hand-named ones, so most of the suite was
neither green nor red, just unobserved.  Nothing detected that, because a
workflow that runs seven files and passes looks exactly like a workflow that
runs everything and passes.

The rule is therefore not "all tests pass" but "no test file is invisible".
Every file under tests/ whose name says it is a test must resolve to one of:

  pytest     collected by pytest, so the regression gate already sees it
  shell      a bash test, run by the shell shard
  script     a test_*.py with a main() and no pytest test functions, run
             directly by the interpreter
  excluded   listed with a reason it cannot run in public CI

Anything else blocks.  Adding a test file is then a decision with a recorded
outcome: it runs, or someone wrote down why it cannot.

Exit 0 = every file accounted for; exit 1 = unclassified files; exit 2 = bad
invocation.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

SCHEMA = "solar.tests.lanes.v1"

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPO_ROOT / "tests"

# Mirrors pytest.ini: python_files and norecursedirs.
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

BLOCK_EXIT = 1
USAGE_EXIT = 2


def discover() -> list[str]:
    """Every test-named file under tests/, as repo-relative posix paths."""
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(TESTS_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            is_py = any(fnmatch.fnmatch(filename, pattern) for pattern in PY_PATTERNS)
            if not is_py and not filename.endswith(".sh"):
                continue
            found.append(Path(dirpath, filename).relative_to(REPO_ROOT).as_posix())
    return sorted(found)


def _collect(python: str, targets: list[str], quiet: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            python,
            "-m",
            "pytest",
            "--collect-only",
            *(["-q"] if quiet else []),
            "--no-header",
            "-p",
            "no:cacheprovider",
            *targets,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def collected_by_pytest(python: str, candidates: list[str]) -> set[str]:
    """Files pytest is responsible for, whether or not they yield test items.

    Two passes.  The first collects the whole tree and takes every file that
    produced an item.  The second asks about the leftovers one at a time,
    because a file can be pytest's and still yield nothing: a module-level
    `pytest.importorskip` for an optional dependency is a deliberate skip, not
    an unobserved test, and must not be reported as needing a lane.  A file that
    yields neither an item, a skip, nor an error genuinely is not a pytest test.
    """
    seen: set[str] = set()
    for line in _collect(python, []).stdout.splitlines():
        candidate = line.split("::", 1)[0].strip()
        if candidate.endswith(".py") and (REPO_ROOT / candidate).is_file():
            seen.add(candidate)

    for rel in candidates:
        if rel in seen or not rel.endswith(".py"):
            continue
        # Not -q: the quiet reporter prints "no tests collected" and drops the
        # "1 skipped" that distinguishes a deliberate importorskip from a file
        # pytest does not own.
        summary = _collect(python, [rel], quiet=False).stdout
        if "skipped" in summary or "error" in summary:
            seen.add(rel)
    return seen


def load_assignments(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        print(f"::error::missing lane manifest {path}", file=sys.stderr)
        raise SystemExit(USAGE_EXIT)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA:
        print(f"::error::{path} is not {SCHEMA}", file=sys.stderr)
        raise SystemExit(USAGE_EXIT)
    known = set(payload.get("lanes", {}))
    assignments = payload.get("assignments", [])
    for entry in assignments:
        for key in ("glob", "lane", "reason"):
            if not entry.get(key):
                print(f"::error::lane assignment missing '{key}': {entry}", file=sys.stderr)
                raise SystemExit(USAGE_EXIT)
        if entry["lane"] not in known:
            print(f"::error::unknown lane '{entry['lane']}' in {entry['glob']}", file=sys.stderr)
            raise SystemExit(USAGE_EXIT)
    return assignments


def match(rel: str, assignments: list[dict[str, str]]) -> dict[str, str] | None:
    """First matching glob wins, so specific exclusions precede broad lanes."""
    for entry in assignments:
        if fnmatch.fnmatch(rel, entry["glob"]):
            return entry
    return None


def main() -> int:
    parser = argparse.ArgumentParser(prog="check-test-census.py")
    parser.add_argument("--python", default=sys.executable, help="interpreter used to collect")
    parser.add_argument("--lanes", type=Path, default=TESTS_ROOT / "ci_lanes.json")
    parser.add_argument("--summary", type=Path, help="append a Markdown report to this file")
    args = parser.parse_args()

    files = discover()
    assignments = load_assignments(args.lanes)
    collected = collected_by_pytest(args.python, files)

    unclassified: list[str] = []
    per_lane: dict[str, int] = {}
    hits: dict[int, int] = {index: 0 for index in range(len(assignments))}

    # An explicit assignment wins over pytest collection, and must: an excluded
    # file is usually one pytest collects perfectly well and must not run
    # anyway. scripts/run-test-shard.py resolves lanes in this same order, and
    # the two have to agree or the census would report a file as running that
    # the runner skips.
    for rel in files:
        for index, entry in enumerate(assignments):
            if fnmatch.fnmatch(rel, entry["glob"]):
                hits[index] += 1
                per_lane[entry["lane"]] = per_lane.get(entry["lane"], 0) + 1
                break
        else:
            if rel in collected:
                per_lane["pytest"] = per_lane.get("pytest", 0) + 1
            else:
                unclassified.append(rel)

    unused = [assignments[i]["glob"] for i, count in hits.items() if count == 0]

    lines = [
        "## Test census",
        "",
        f"- test files under `tests/`: **{len(files)}**",
        f"- unclassified: **{len(unclassified)}**",
        "",
        "| lane | files |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {lane} | {count} |" for lane, count in sorted(per_lane.items()))
    lines.append("")
    if unclassified:
        lines.append("### Unclassified test files (blocking)")
        lines.append("")
        lines.append(
            "Each of these is neither collected by pytest nor assigned a lane in "
            "`tests/ci_lanes.json`. Either make it collectable, or assign it a "
            "lane with a reason."
        )
        lines.append("")
        lines.extend(f"- `{rel}`" for rel in unclassified[:100])
        if len(unclassified) > 100:
            lines.append(f"- ...and {len(unclassified) - 100} more")
        lines.append("")
    if unused:
        lines.append("### Lane globs that match nothing")
        lines.append("")
        lines.extend(f"- `{glob}`" for glob in unused)
        lines.append("")

    report = "\n".join(lines)
    print(report)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(report + "\n")

    for rel in unclassified:
        print(
            f"::error file={rel}::test file is not run by CI and has no lane in tests/ci_lanes.json",
            file=sys.stderr,
        )
    if unused:
        print(f"::warning::{len(unused)} lane globs match no file; remove them", file=sys.stderr)

    return BLOCK_EXIT if unclassified else 0


if __name__ == "__main__":
    raise SystemExit(main())
