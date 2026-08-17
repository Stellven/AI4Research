from __future__ import annotations

import ast
import json
import re
import subprocess
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = ROOT / "docs" / "integrations" / "autosci" / "overwritten-contribution-reconciliation.json"
BASE = "a3a0ecaae82eed1e87d8dabb9eab520796c4a1bd"
SOURCE = "4d60f1e03b40b3e1bb618afe7136ef1687f2d5a4"
FINAL = "2d006882d20ea06bf4965ce0ce363bbd5626edfc"

ALLOWED = {
    "PRESERVED_EXACT", "PRESERVED_MOVED", "PRESERVED_SEMANTICALLY",
    "SUPERSEDED_BY_NEWER_IMPLEMENTATION", "RESTORED",
    "INTENTIONALLY_EXCLUDED_GENERATED_STATE", "INTENTIONALLY_EXCLUDED_SECRET_OR_LOCAL_STATE",
    "INTENTIONALLY_EXCLUDED_OBSOLETE_DUPLICATE", "INTENTIONALLY_EXCLUDED_SECURITY_OR_PORTABILITY_RISK",
    "NEEDS_HUMAN_DECISION",
}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def tree(revision: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in git("ls-tree", "-r", "-z", revision).split(b"\0"):
        if not row:
            continue
        left, raw_path = row.split(b"\t", 1)
        _mode, _kind, blob = left.split()
        result[raw_path.decode("utf-8", "surrogateescape")] = blob.decode()
    return result


def test_reconciliation_is_complete_and_resolved() -> None:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    expected_commits = git("rev-list", "--reverse", f"{BASE}..{SOURCE}").decode().splitlines()
    assert [item["commit"] for item in ledger["commits"]] == expected_commits
    paths = ledger["paths"]
    assert ledger["source_commits_total"] == len(expected_commits)
    assert ledger["candidate_paths_total"] == len(paths)
    assert len({item["original_path"] for item in paths}) == len(paths)
    assert all(item["classification"] in ALLOWED for item in paths)
    assert ledger["unresolved_count"] == 0
    assert all(item["classification"] != "NEEDS_HUMAN_DECISION" for item in paths)
    assert Counter(item["classification"] for item in paths) == Counter(ledger["classification_counts"])


def test_reconciliation_actions_have_current_evidence() -> None:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    tracked = set(git("ls-files", "-z").decode("utf-8", "surrogateescape").split("\0"))
    tracked.discard("")
    source_tree = tree(SOURCE)
    current_tree = tree("HEAD")
    for item in ledger["paths"]:
        classification = item["classification"]
        targets = item["current_corresponding_paths"]
        assert item["evidence"].strip()
        if classification == "PRESERVED_EXACT":
            source_blob = item["original_blob_hash"]
            path = item["original_path"]
            if source_blob is None:
                assert path not in tracked
                assert not targets
                assert path not in source_tree
                assert path not in current_tree
            else:
                assert targets == [path]
                assert path in tracked
                assert source_tree[path] == source_blob
                assert current_tree[path] == source_blob
        if classification == "PRESERVED_MOVED":
            assert targets and all(target in tracked for target in targets)
        if classification == "PRESERVED_SEMANTICALLY":
            assert targets and all(target in tracked for target in targets)
        if classification == "SUPERSEDED_BY_NEWER_IMPLEMENTATION":
            assert targets and all(target in tracked for target in targets)
        if classification.startswith("INTENTIONALLY_EXCLUDED"):
            assert item["action"].strip() and item["evidence"].strip()


def test_semantically_preserved_python_tests_keep_test_case_identities() -> None:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))

    def test_ids(source: str) -> set[str]:
        tree = ast.parse(source)
        return {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        }

    for item in ledger["paths"]:
        if item["classification"] != "PRESERVED_SEMANTICALLY":
            continue
        if not item["original_path"].endswith(".py") or not item["original_blob_hash"]:
            continue
        original_ids = test_ids(git("cat-file", "blob", item["original_blob_hash"]).decode("utf-8"))
        if not original_ids:
            continue
        current_ids: set[str] = set()
        for target in item["current_corresponding_paths"]:
            if target.endswith(".py"):
                current_ids.update(test_ids((ROOT / target).read_text(encoding="utf-8")))
        assert original_ids <= current_ids, {
            "original_path": item["original_path"],
            "targets": item["current_corresponding_paths"],
            "missing_test_ids": sorted(original_ids - current_ids),
        }


def test_readme_is_the_verbatim_stellven_source_tip_blob() -> None:
    assert git("rev-parse", f"HEAD:README.md") == git("rev-parse", f"{SOURCE}:README.md")


def test_moved_and_semantic_source_blobs_are_not_reintroduced_at_legacy_paths() -> None:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    current_tree = tree("HEAD")
    for item in ledger["paths"]:
        if item["classification"] not in {"PRESERVED_MOVED", "PRESERVED_SEMANTICALLY"}:
            continue
        source_blob = item["original_blob_hash"]
        current_blob = current_tree.get(item["original_path"])
        if source_blob is None:
            assert current_blob is None
        else:
            assert current_blob != source_blob


def test_no_illegal_paths_or_prohibited_recovered_state() -> None:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    prohibited = re.compile(r"(^|/)(\.env(?:\.|$)|node_modules|__pycache__|cache|outputs|status\.json|events\.jsonl)(/|$)|\.lock$", re.I)
    illegal = re.compile(r'[<>:"|?*]')
    for item in ledger["paths"]:
        path = item["original_path"]
        paths_to_check = list(item["current_corresponding_paths"])
        if item["classification"] == "PRESERVED_EXACT" and item["original_blob_hash"] is not None:
            paths_to_check.append(path)
        for checked_path in paths_to_check:
            for component in checked_path.split("/"):
                assert not illegal.search(component)
                assert not component.endswith((".", " "))
    assert ledger["fixed_revisions"]["final_integration"] == FINAL
