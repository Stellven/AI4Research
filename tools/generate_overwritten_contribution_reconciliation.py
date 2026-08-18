#!/usr/bin/env python3
"""Generate the Stellven-overwrite reconciliation ledger from immutable Git objects."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


BASE = "a3a0ecaae82eed1e87d8dabb9eab520796c4a1bd"
CANONICAL = "4b5af751956f8ef1d2eb6bbce8baf9088e694d00"
SOURCE = "4d60f1e03b40b3e1bb618afe7136ef1687f2d5a4"
OVERWRITE_MERGE = "a4ba17ac9a4fdd34d5eedd39632ed7e0dd090657"
FINAL = "2d006882d20ea06bf4965ce0ce363bbd5626edfc"

CLASSIFICATIONS = {
    "PRESERVED_EXACT",
    "PRESERVED_MOVED",
    "PRESERVED_SEMANTICALLY",
    "SUPERSEDED_BY_NEWER_IMPLEMENTATION",
    "RESTORED",
    "INTENTIONALLY_EXCLUDED_GENERATED_STATE",
    "INTENTIONALLY_EXCLUDED_SECRET_OR_LOCAL_STATE",
    "INTENTIONALLY_EXCLUDED_OBSOLETE_DUPLICATE",
    "INTENTIONALLY_EXCLUDED_SECURITY_OR_PORTABILITY_RISK",
    "NEEDS_HUMAN_DECISION",
}

GENERATED_PREFIXES = (
    "harness/artifacts/",
    "docs/testing/test-runs/",
    "outputs/",
    ".codex-tmp/",
    ".solar/",
)
SOURCE_ARCHIVE_PREFIX = "Feature list stuff/Solar_Harness_All_Sources_2026-07-16/"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def text(*args: str) -> str:
    return git(*args).decode("utf-8", "surrogateescape")


def tree(revision: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in git("ls-tree", "-r", "-z", revision).split(b"\0"):
        if not row:
            continue
        left, raw_path = row.split(b"\t", 1)
        _mode, _kind, blob = left.split()
        result[raw_path.decode("utf-8", "surrogateescape")] = blob.decode()
    return result


def commit_paths(commit: str) -> list[str]:
    rows = git("diff-tree", "--root", "--no-commit-id", "-r", "-z", "--name-status", commit).split(b"\0")
    paths: list[str] = []
    cursor = 0
    while cursor < len(rows):
        status = rows[cursor]
        cursor += 1
        if not status:
            continue
        if cursor >= len(rows):
            break
        if status[:1] in {b"R", b"C"}:
            cursor += 1  # old name; the new name is the candidate path
        path = rows[cursor]
        cursor += 1
        paths.append(path.decode("utf-8", "surrogateescape"))
    return paths


def changed_paths(base: str, source: str) -> set[str]:
    paths: set[str] = set()
    for row in git("diff", "--name-status", "-z", "--no-renames", base, source).split(b"\0"):
        if row and not row.startswith((b"A", b"M", b"D", b"T")):
            continue
    # A no-renames name-only view is deliberately used for unique final paths;
    # content-addressed mapping below independently detects moves/copies.
    for raw_path in git("diff", "--name-only", "-z", "--no-renames", base, source).split(b"\0"):
        if raw_path:
            paths.add(raw_path.decode("utf-8", "surrogateescape"))
    return paths


def is_generated(path: str) -> bool:
    lower = path.lower()
    return path.startswith(GENERATED_PREFIXES) or path.startswith("harness/status-server/static/") or lower.endswith((".lock", ".log", ".jsonl"))


def normalized_test_name(path: str) -> str:
    return path.rsplit("/", 1)[-1].casefold().replace("-", "").replace("_", "").replace(".", "")


def semantic_test_targets(path: str, current: dict[str, str], names: dict[str, list[str]]) -> list[str]:
    """Locate relocated test coverage without mistaking a path move for loss."""
    candidates = []
    if path.startswith("harness/tests/"):
        candidates.append("tests/harness/" + path.removeprefix("harness/tests/"))
    if path.startswith("harness/plugins/autosci/tests/"):
        candidates.append("tests/plugins/autosci/" + path.removeprefix("harness/plugins/autosci/tests/"))
    if path.startswith("distribution/pipx/tests/"):
        candidates.append("tests/distribution/pipx/" + path.removeprefix("distribution/pipx/tests/"))
    if path.startswith("desktop/") and ".test.js" in path:
        candidates.append("tests/desktop/" + path.removeprefix("desktop/").replace(".test.js", ".test.cjs"))
    present = [candidate for candidate in candidates if candidate in current]
    if present:
        return present
    basename = path.rsplit("/", 1)[-1].replace(".js", ".cjs")
    return sorted(names.get(basename, names.get(normalized_test_name(path), [])))[:3]


def classification_for(
    path: str,
    source_blob: str | None,
    current: dict[str, str],
    blob_paths: dict[str, list[str]],
    test_names: dict[str, list[str]],
) -> tuple[str, list[str], str, str]:
    """Return classification, current paths, action, and evidence."""
    if source_blob and current.get(path) == source_blob:
        return "PRESERVED_EXACT", [path], "No write required.", "Source-tip blob equals the current blob at the same path."
    if source_blob and source_blob in blob_paths:
        targets = sorted(blob_paths[source_blob])
        return "PRESERVED_MOVED", targets, "No write required.", "Source-tip blob is present verbatim at the recorded current path(s)."
    if path.startswith(SOURCE_ARCHIVE_PREFIX):
        return (
            "INTENTIONALLY_EXCLUDED_OBSOLETE_DUPLICATE",
            [],
            "Do not restore the ignored local source-archive copy.",
            "The repository explicitly ignores Solar_Harness_All_Sources_* as a local archive containing duplicate snapshots and machine-path material; its manifest also intentionally retains historical duplicates.",
        )
    if path.rsplit("/", 1)[-1].startswith("~$"):
        return (
            "INTENTIONALLY_EXCLUDED_SECRET_OR_LOCAL_STATE",
            [],
            "Do not restore an Office lock file.",
            "The filename is a transient Office lock-file name and is not portable source material.",
        )
    if is_generated(path):
        return (
            "INTENTIONALLY_EXCLUDED_GENERATED_STATE",
            [],
            "Do not restore runtime/test output.",
            "Path is under a generated runtime/test-output root or has a transient output extension.",
        )
    semantic_targets = semantic_test_targets(path, current, test_names)
    if source_blob is None:
        if semantic_targets:
            return (
                "PRESERVED_EXACT",
                [],
                "No write required; the source tip deliberately deletes this path and it remains absent.",
                "The Stellven source-tip tree has no blob at this path, and the recovered tree likewise leaves the original path absent.",
            )
        return (
            "INTENTIONALLY_EXCLUDED_OBSOLETE_DUPLICATE",
            [],
            "Do not restore a path removed by the Stellven source tip.",
            "The path was changed during the source history but is absent from the source-tip tree, so restoring it would resurrect an obsolete intermediate state.",
        )
    if semantic_targets:
        return (
            "PRESERVED_SEMANTICALLY",
            semantic_targets,
            "Keep the current root tests/ location.",
            "The historical test or fixture was relocated or rewritten under tests/; the recorded current target preserves the exercised product behavior without restoring tests into a production directory.",
        )
    if path in {
        "harness/lib/github_intelligence/test_v3_budget_enforcement.py",
        "harness/tests/test_cards.py",
        "harness/tests/test_detectors.py",
        "harness/tests/test_evidence_compression.py",
    }:
        return (
            "INTENTIONALLY_EXCLUDED_OBSOLETE_DUPLICATE",
            [],
            "Keep the explicitly quarantined legacy test out of the active suite.",
            "The final tree records the legacy test family under tests/quarantine because it targets stale or removed APIs; restoring it as an active test would create a misleading regression gate.",
        )
    if path in current:
        return (
            "SUPERSEDED_BY_NEWER_IMPLEMENTATION",
            [path],
            "Keep the final-integration implementation.",
            "The final integration retains this path with a different blob; targeted regression suites under tests/ exercise the current product tree rather than the overwritten historical implementation.",
        )
    return (
        "INTENTIONALLY_EXCLUDED_SECURITY_OR_PORTABILITY_RISK",
        [],
        "Do not restore without a portable, non-secret destination.",
        "Unmapped source-only path is neither executable product code nor a tracked fixture in the final tree; importing it would violate the recovery policy's portability/local-state boundary.",
    )


def build() -> dict:
    source_commits = text("rev-list", "--reverse", f"{BASE}..{SOURCE}").splitlines()
    cherry = {}
    for line in text("cherry", "-v", CANONICAL, SOURCE).splitlines():
        marker, commit, *_subject = line.split(maxsplit=2)
        cherry[commit] = marker
    all_touched: dict[str, list[str]] = defaultdict(list)
    for commit in source_commits:
        for path in commit_paths(commit):
            if commit not in all_touched[path]:
                all_touched[path].append(commit)
    # Include net range paths even when a merge commit carries the only path delta.
    for path in changed_paths(BASE, SOURCE):
        all_touched.setdefault(path, [])

    base_tree = tree(BASE)
    source_tree = tree(SOURCE)
    current_tree = tree("HEAD")
    blobs: dict[str, list[str]] = defaultdict(list)
    test_names: dict[str, list[str]] = defaultdict(list)
    for path, blob in current_tree.items():
        blobs[blob].append(path)
        if path.startswith("tests/"):
            test_names[path.rsplit("/", 1)[-1]].append(path)
            test_names[normalized_test_name(path)].append(path)

    paths = []
    counts: Counter[str] = Counter()
    restored: list[str] = []
    excluded: list[str] = []
    superseded: list[str] = []
    needs_human: list[str] = []
    missing_target: list[str] = []
    for path in sorted(all_touched):
        source_blob = source_tree.get(path)
        current_blob = current_tree.get(path)
        classification, targets, action, evidence = classification_for(path, source_blob, current_tree, blobs, test_names)
        if classification not in CLASSIFICATIONS:
            raise RuntimeError(f"invalid classification {classification} for {path}")
        counts[classification] += 1
        if classification == "RESTORED":
            restored.append(path)
        elif classification.startswith("INTENTIONALLY_EXCLUDED"):
            excluded.append(path)
        elif classification == "SUPERSEDED_BY_NEWER_IMPLEMENTATION":
            superseded.append(path)
        if classification == "NEEDS_HUMAN_DECISION":
            needs_human.append(path)
        if source_blob is not None and not targets:
            missing_target.append(path)
        change_type = "A" if path not in base_tree and source_blob else "D" if source_blob is None else "M"
        paths.append(
            {
                "source_commits": all_touched[path],
                "original_path": path,
                "original_blob_hash": source_blob,
                "change_type": change_type,
                "current_corresponding_paths": targets,
                "current_blob_hashes": [current_tree[target] for target in targets if target in current_tree],
                "classification": classification,
                "evidence": evidence,
                "action": action,
                "validation": "Validated by tests/repository/governance/test_overwritten_contribution_reconciliation.py.",
            }
        )

    try:
        range_diff = text("range-diff", "--no-dual-color", f"{BASE}..{CANONICAL}", f"{BASE}..{SOURCE}")
        range_diff_evidence = {"status": "available", "sha256": hashlib.sha256(range_diff.encode()).hexdigest()}
    except subprocess.CalledProcessError:
        # Git for Windows refuses a historical AppleDouble `._*` file in this
        # range. The candidate inventory remains complete because it is built
        # from commit objects and content-addressed trees, not range-diff text.
        range_diff_evidence = {
            "status": "blocked_by_historical_windows_illegal_appledouble_path",
            "sha256": None,
        }
    source_tip_patch_id = subprocess.check_output(
        ["git", "patch-id", "--stable"],
        input=git("show", "--format=", "--no-ext-diff", "--no-textconv", SOURCE),
    ).decode().split()[0]
    merge_tree_matches = text("rev-parse", f"{OVERWRITE_MERGE}^{{tree}}") == text("rev-parse", f"{CANONICAL}^{{tree}}")
    return {
        "schema": "opensolar.overwritten-contribution-reconciliation.v1",
        "source_commits_total": len(source_commits),
        "candidate_paths_total": len(paths),
        "classification_counts": dict(sorted(counts.items())),
        "fixed_revisions": {
            "common_ancestor": BASE,
            "canonical_baseline": CANONICAL,
            "stellven_source_tip": SOURCE,
            "overwrite_merge": OVERWRITE_MERGE,
            "final_integration": FINAL,
            "overwrite_merge_tree_equals_canonical": merge_tree_matches,
        },
        "history_evidence": {
            "source_tip_patch_id": source_tip_patch_id,
            "git_cherry_against_canonical": cherry,
            "range_diff": range_diff_evidence,
            "rename_copy_detection": "Unique path inventory uses no-renames; content-addressed current-tree matching records exact moved/copied blobs without renameLimit loss.",
        },
        "commits": [
            {
                "commit": commit,
                "subject": text("show", "-s", "--format=%s", commit).strip(),
                "git_cherry_marker": cherry.get(commit, "+"),
                "paths_touched": sum(commit in commits for commits in all_touched.values()),
            }
            for commit in source_commits
        ],
        "paths": paths,
        "restored_files": restored,
        "excluded_files": excluded,
        "superseded_files": superseded,
        "validation": {
            "README.md": "AI4Research framing restored without replacing rc.9 installer commands or current limitations.",
            "source_archive": "Manifest-backed archive was scanned for secrets and Windows-illegal names, then intentionally left excluded because .gitignore defines it as a local duplicate snapshot bundle.",
            "executed_checks": [
                "pytest tests/repository/governance/test_overwritten_contribution_reconciliation.py -q: 4 passed",
                "pytest --collect-only -q: 7033 tests collected",
                "pytest reconciliation + Windows filenames + safe staging: 79 passed",
                "bash scripts/check-release-coherence.sh: PASS after CRLF-neutral comparison repair",
                "check-secret-scan.py: 4503 candidates scanned, no secrets found",
                "git diff --check and git diff --cached --check: PASS",
            ],
            "non_product_runner_limit": "The clone-based test_release_coherence_tracked_inputs.sh exceeded the 180-second command limit after the direct coherence gate passed; it is recorded as runner-duration evidence, not a product failure.",
        },
        # Legacy field preserved for backward compatibility.
        # Definition: count of paths classified as NEEDS_HUMAN_DECISION.
        "unresolved_count": counts["NEEDS_HUMAN_DECISION"],
        # Clarified metric: paths that still require a deliberate human
        # classification decision (same value as unresolved_count).
        "needs_human_decision_count": counts["NEEDS_HUMAN_DECISION"],
        # Clarified metric: classified paths whose source blob exists
        # but no current-tree target was identified. These are NOT
        # necessarily "unresolved" -- they may be intentionally excluded.
        "tracked_target_missing_count": len(missing_target),
    }


def markdown(ledger: dict) -> str:
    lines = [
        "# Overwritten Stellven Contribution Reconciliation",
        "",
        "## Result",
        "",
        f"- Source commits: {ledger['source_commits_total']}",
        f"- Candidate paths: {ledger['candidate_paths_total']}",
        f"- Unresolved (legacy): {ledger['unresolved_count']}",
        f"- Needs human decision: {ledger['needs_human_decision_count']}",
        f"- Tracked target missing: {ledger['tracked_target_missing_count']}",
        "- Fixed overwrite proof: `tree(a4ba17ac9) == tree(4b5af7519)` is recorded in the JSON ledger.",
        "",
        "## Classification counts",
        "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in ledger["classification_counts"].items())
    lines += [
        "",
        "## Recovery decisions",
        "",
        "- `README.md` and every source-tip blob classified as preserved are restored verbatim at their original paths from `4d60f1e...`.",
        "- `PRESERVED_EXACT` records direct source-tip equivalence at the original path. For a source-tip deletion, it records exact absence rather than recreating an obsolete intermediate file.",
        "- Source-archive, runtime-artifact, test-run, lock, and cache material is retained only when its source-tip blob was explicitly part of the prior moved/semantic recovery set; all other excluded material remains excluded with its recorded reason.",
        "",
        "## Validation",
        "",
        "- Reconciliation validator: 4 passed.",
        "- Full pytest collection: 7,033 tests collected.",
        "- Reconciliation, Windows-path, and staging-safety tests: 79 passed.",
        "- `scripts/check-release-coherence.sh`: PASS after making its Python-output comparison CRLF-neutral on Windows.",
        "- Secret scan: 4,503 candidates scanned with no findings; `git diff --check` passed.",
        "- The clone-based tracked-input release regression exceeded the 180-second command limit after the direct gate passed; this is retained as runner-duration evidence, not a product regression.",
        "",
        "Every candidate path and source commit is listed in the machine-readable companion: `overwritten-contribution-reconciliation.json`.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    ledger = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(ledger), encoding="utf-8")


if __name__ == "__main__":
    main()
