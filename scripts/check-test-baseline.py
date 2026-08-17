#!/usr/bin/env python3
"""check-test-baseline.py — regression gate for the repository test suite.

The suite is not green.  Gating on "zero failures" would mean either disabling
CI or disabling most of the suite, and both hide new breakage.  This gate
instead compares the tests that are red NOW against a reviewed baseline of the
tests that were already red, so a pull request is judged on what it changed.

A baseline is only worth anything if it cannot be edited to make a failure go
away.  Every way of doing that is a blocking verdict here:

  NEW_FAILURE        red now, not in the baseline
  BASELINE_ADDITION  an entry this branch added to the baseline; the baseline
                     may only shrink, so adding one is self-whitelisting
  STALE_BASELINE     a baseline entry with no matching test in the run, which
                     is what deleting or renaming a failing test looks like
  UNRECORDED_FIX     a baseline test that now passes; left in the baseline it
                     is a permanent hole the test could regress into
  MISSING_SHARD      an expected shard produced no results
  UNEXPECTED_SHARD   a shard reported that the lane manifest does not declare
  DUPLICATE_IDENTITY the same test reported by more than one shard, which means
                     the sharding is not a partition and counts are unreliable
  UNREADABLE_JUNIT   a shard's XML did not parse

Test identity is `classname::name`, never a count.  Counts are the reason equal
sized red sets look identical when the underlying tests are different.

Exit 0 = clean; exit 1 = at least one blocking verdict; exit 2 = bad invocation.
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

SCHEMA = "solar.tests.baseline.v1"
LANES_SCHEMA = "solar.tests.lanes.v1"

BLOCK_EXIT = 1
USAGE_EXIT = 2

MESSAGE_LIMIT = 200
REPORT_LIMIT = 100

RED = frozenset({"fail", "error"})


@dataclass(frozen=True)
class Case:
    identity: str
    outcome: str  # pass | fail | error | skip
    message: str
    shard: str


def _case_outcome(testcase: ET.Element) -> tuple[str, str]:
    for tag, outcome in (("error", "error"), ("failure", "fail"), ("skipped", "skip")):
        node = testcase.find(tag)
        if node is not None:
            message = (node.get("message") or "").strip()
            return outcome, " ".join(message.split())[:MESSAGE_LIMIT]
    return "pass", ""


def load_junit(paths: list[Path]) -> tuple[dict[str, Case], set[str], list[str], list[str]]:
    """Return (cases, shard names seen, duplicate identities, unreadable files).

    The shard name comes from the JUnit `testsuite name`, not the file name, so
    a renamed or missing artifact cannot impersonate a shard that ran.
    """
    cases: dict[str, Case] = {}
    shards: set[str] = set()
    duplicates: list[str] = []
    unreadable: list[str] = []
    for path in paths:
        try:
            tree = ET.parse(path)
        except (OSError, ET.ParseError) as exc:
            unreadable.append(f"{path}: {exc}")
            continue
        root = tree.getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        for suite in suites:
            name = suite.get("name") or ""
            if name:
                shards.add(name)
            for testcase in suite.iter("testcase"):
                classname = testcase.get("classname") or ""
                case_name = testcase.get("name") or ""
                identity = f"{classname}::{case_name}" if classname else case_name
                outcome, message = _case_outcome(testcase)
                previous = cases.get(identity)
                if previous is not None:
                    if previous.shard != name:
                        duplicates.append(identity)
                    # A test that failed anywhere is not green.
                    if previous.outcome in RED:
                        continue
                cases[identity] = Case(identity, outcome, message, name)
    return cases, shards, sorted(set(duplicates)), unreadable


def load_baseline(path: Path) -> dict[str, str]:
    if not path.is_file():
        print(f"::error::missing baseline {path}", file=sys.stderr)
        raise SystemExit(USAGE_EXIT)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA:
        print(f"::error::{path} is not {SCHEMA}", file=sys.stderr)
        raise SystemExit(USAGE_EXIT)
    return {entry["test"]: entry.get("reason", "") for entry in payload["known_failures"]}


def expected_shards(path: Path) -> set[str]:
    """Shard names the lane manifest declares.

    The workflow matrix and this set have one source, so a matrix that grows a
    shard without the manifest (or the reverse) fails rather than quietly
    dropping or inventing coverage.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != LANES_SCHEMA:
        print(f"::error::{path} is not {LANES_SCHEMA}", file=sys.stderr)
        raise SystemExit(USAGE_EXIT)
    shards = payload.get("shards")
    if not shards:
        print(f"::error::{path} declares no 'shards'", file=sys.stderr)
        raise SystemExit(USAGE_EXIT)
    return {f"{lane}-{index}" for lane, count in shards.items() for index in range(int(count))}


def write_baseline(path: Path, cases: dict[str, Case], previous: dict[str, str]) -> int:
    """Rewrite the baseline from a run, preserving reasons already recorded."""
    known = [
        {
            "test": case.identity,
            "reason": previous.get(case.identity) or case.message or "unclassified",
        }
        for case in sorted(cases.values(), key=lambda c: c.identity)
        if case.outcome in RED
    ]
    payload = {
        "schema": SCHEMA,
        "note": (
            "Tests that were already red. This list may only shrink: CI compares "
            "it against the same file on the base branch and blocks any entry "
            "this branch added. Regenerate with scripts/check-test-baseline.py "
            "--update after fixing tests, and review the removals in the diff."
        ),
        "count": len(known),
        "known_failures": known,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return len(known)


def _section(title: str, items: list[str], explain: str) -> list[str]:
    if not items:
        return []
    lines = [f"### {title} ({len(items)})", "", explain, ""]
    lines.extend(f"- `{item}`" for item in items[:REPORT_LIMIT])
    if len(items) > REPORT_LIMIT:
        lines.append(f"- ...and {len(items) - REPORT_LIMIT} more")
    lines.append("")
    return lines


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(prog="check-test-baseline.py")
    parser.add_argument("junit", nargs="+", type=Path, help="JUnit XML file(s) from the run")
    parser.add_argument("--baseline", type=Path, default=repo_root / "tests" / "ci_baseline.json")
    parser.add_argument(
        "--base-baseline",
        type=Path,
        help="the same file as of the base branch; entries added relative to it block",
    )
    parser.add_argument(
        "--allow-baseline-bootstrap",
        action="store_true",
        help="permit a missing --base-baseline, for the one pull request that introduces it",
    )
    parser.add_argument("--lanes", type=Path, default=repo_root / "tests" / "ci_lanes.json")
    parser.add_argument("--update", action="store_true", help="rewrite the baseline from this run")
    parser.add_argument("--summary", type=Path, help="append a Markdown report to this file")
    args = parser.parse_args()

    cases, shards, duplicates, unreadable = load_junit(args.junit)
    baseline = load_baseline(args.baseline)

    if args.update:
        count = write_baseline(args.baseline, cases, baseline)
        print(f"baseline rewritten: {count} known failures ({len(baseline)} before)")
        return 0

    wanted = expected_shards(args.lanes)
    missing_shards = sorted(wanted - shards)
    unexpected_shards = sorted(shards - wanted)

    red = {i: c for i, c in cases.items() if c.outcome in RED}
    new_failures = sorted(i for i in red if i not in baseline)
    unrecorded_fixes = sorted(i for i in baseline if i in cases and cases[i].outcome == "pass")
    stale = sorted(i for i in baseline if i not in cases)

    additions: list[str] = []
    base_missing = False
    if args.base_baseline is not None and args.base_baseline.is_file():
        base_entries = load_baseline(args.base_baseline)
        additions = sorted(set(baseline) - set(base_entries))
    elif not args.allow_baseline_bootstrap:
        base_missing = True

    blocking = {
        "new failures": new_failures,
        "baseline additions": additions,
        "stale baseline entries": stale,
        "unrecorded fixes": unrecorded_fixes,
        "missing shards": missing_shards,
        "unexpected shards": unexpected_shards,
        "duplicate identities": duplicates,
        "unreadable JUnit": unreadable,
    }
    failed = base_missing or any(blocking.values())

    lines = [
        "## Test regression gate",
        "",
        f"- shards reported: **{len(shards)}** of {len(wanted)} expected",
        f"- cases run: **{len(cases)}**",
        f"- red now: **{len(red)}**  (baseline records {len(baseline)})",
        f"- verdict: **{'BLOCKED' if failed else 'clean'}**",
        "",
    ]
    if base_missing:
        lines += [
            "**No base-branch baseline to compare against.** Without it a pull "
            "request can add its own failures to the baseline and pass. Pass "
            "`--base-baseline`, or `--allow-baseline-bootstrap` for the one "
            "pull request that introduces the file.",
            "",
        ]
    lines += _section(
        "New failures", new_failures,
        "Red in this run and not recorded as already red. Fix the test or the product.",
    )
    lines += _section(
        "Baseline additions", additions,
        "Added to tests/ci_baseline.json relative to the base branch. The baseline "
        "may only shrink; adding an entry is whitelisting your own failure.",
    )
    lines += _section(
        "Stale baseline entries", stale,
        "Recorded as red but no test with this identity ran. Deleting or renaming "
        "a failing test looks exactly like this. Restore the test, or remove the "
        "entry in the same change and say why in the pull request.",
    )
    lines += _section(
        "Unrecorded fixes", unrecorded_fixes,
        "These now pass but are still recorded as red, so they could regress "
        "without blocking anything. Run --update and commit the smaller baseline.",
    )
    lines += _section(
        "Missing shards", missing_shards,
        "Declared in tests/ci_lanes.json but produced no results. A shard that "
        "reports nothing is indistinguishable from a shard with nothing to report.",
    )
    lines += _section(
        "Unexpected shards", unexpected_shards,
        "Reported but not declared in tests/ci_lanes.json. The workflow matrix and "
        "the manifest have drifted apart.",
    )
    lines += _section(
        "Duplicate identities", duplicates,
        "Reported by more than one shard, so the shards are not a partition and "
        "every count here is unreliable.",
    )
    lines += _section("Unreadable JUnit", unreadable, "A shard's results could not be parsed.")

    report = "\n".join(lines)
    print(report)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(report + "\n")

    if base_missing:
        print("::error::no base-branch baseline supplied; cannot detect self-whitelisting", file=sys.stderr)
    for label, items in blocking.items():
        for item in items:
            print(f"::error::{label}: {item}", file=sys.stderr)

    return BLOCK_EXIT if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
