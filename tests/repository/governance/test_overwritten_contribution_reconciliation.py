from __future__ import annotations

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
    tracked = set(git("ls-files").decode("utf-8", "surrogateescape").splitlines())
    for item in ledger["paths"]:
        classification = item["classification"]
        targets = item["current_corresponding_paths"]
        assert item["evidence"].strip()
        if classification == "RESTORED":
            assert item["original_path"] in tracked
        if classification == "PRESERVED_MOVED":
            assert targets and all(target in tracked for target in targets)
        if classification == "PRESERVED_SEMANTICALLY":
            assert targets and all(target in tracked for target in targets)
        if classification == "SUPERSEDED_BY_NEWER_IMPLEMENTATION":
            assert targets and all(target in tracked for target in targets)
        if classification.startswith("INTENTIONALLY_EXCLUDED"):
            assert item["action"].strip() and item["evidence"].strip()


def test_readme_restores_ai4research_without_stale_install_commands() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert "AI4Research" in readme
    assert "governed local execution" in readme
    assert "solar harness autosci" in readme
    assert f"OpenSolar/v{version}/get-solar.sh" in readme
    assert f"OpenSolar.git@v{version}#subdirectory=distribution/pipx" in readme


def test_no_illegal_paths_or_prohibited_recovered_state() -> None:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    prohibited = re.compile(r"(^|/)(\.env(?:\.|$)|node_modules|__pycache__|cache|outputs|status\.json|events\.jsonl)(/|$)|\.lock$", re.I)
    illegal = re.compile(r'[<>:"|?*]')
    for item in ledger["paths"]:
        path = item["original_path"]
        paths_to_check = list(item["current_corresponding_paths"])
        if item["classification"] == "RESTORED":
            paths_to_check.append(path)
        for checked_path in paths_to_check:
            for component in checked_path.split("/"):
                assert not illegal.search(component)
                assert not component.endswith((".", " "))
        if item["classification"] == "RESTORED":
            assert not prohibited.search(path)
    assert ledger["fixed_revisions"]["final_integration"] == FINAL
