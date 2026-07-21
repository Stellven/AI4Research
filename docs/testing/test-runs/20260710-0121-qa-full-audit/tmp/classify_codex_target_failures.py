from __future__ import annotations

import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def compact(value: str, limit: int = 1200) -> str:
    return " ".join(value.split())[:limit]


def junit_messages(path: Path) -> tuple[int, int, list[str]]:
    failures = 0
    errors = 0
    messages = []
    if not path.is_file():
        return failures, errors, messages
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        return 0, 1, [f"junit parse error: {error}"]
    for case in root.iter("testcase"):
        for tag in ("failure", "error"):
            node = case.find(tag)
            if node is None:
                continue
            if tag == "failure":
                failures += 1
            else:
                errors += 1
            message = node.attrib.get("message", "") or (node.text or "")
            messages.append(f"{case.attrib.get('name', '')}: {compact(message, 500)}")
    return failures, errors, messages[:8]


def classify(row: dict[str, str], text: str, jf: int, je: int) -> tuple[str, str, str]:
    lower = text.lower()
    if row["execution_status"] == "NOT_COLLECTED":
        if "collected 0 items" in lower or "no tests ran" in lower:
            return "not_a_pytest_test", "runner used pytest on a script/module with no collected testcases", "rerun with direct Python entrypoint if the file is an executable contract probe"
        return "collection_error", "pytest did not collect the selected target", "inspect collection/import diagnostics and select the correct runner"
    if "qa_audit_blocked" in lower or "qa_audit_blocked_git" in lower:
        return "blocked_by_safety_shim", "the target attempted a command intentionally disabled by the audit sandbox", "retain as blocked evidence or request explicit HITL approval before a positive side-effect branch"
    if "modulenotfounderror" in lower or "cannot find module" in lower or "no module named" in lower:
        return "missing_runtime_dependency", "the target could not import a required module", "reuse an already installed project runtime if available; do not install implicitly"
    if "command not found" in lower or "no such file or directory:" in lower and row["exit_code"] == "127":
        return "missing_command", "the target runner or required command was not found", "select the repository's available runner or classify as SKIPPED_ENV"
    if "error collecting" in lower or je:
        return "collection_or_fixture_error", "pytest collection/setup error prevented a clean feature assertion", "repair the audit invocation/PYTHONPATH/fixture isolation and rerun"
    if "no such file or directory" in lower or "not found" in lower and row["runner_kind"] == "shell":
        return "runner_cwd_or_path", "the shell test appears to assume a different working directory or installed layout", "rerun from the test's expected harness/repo working directory"
    if row["runner_kind"] == "shell" and float(row["duration_seconds"] or 0) < 0.1:
        return "shell_fast_failure", "shell target exited before meaningful assertions likely completed", "inspect trace and rerun with its expected cwd/environment"
    if jf or "assertionerror" in lower or re.search(r"\bfailed\b", lower):
        return "assertion_failure", "one or more product/test contract assertions failed", "review failing testcase relevance before mapping FAIL to an atomic feature"
    return "unclassified_failure", "non-zero exit without a recognized infrastructure signature", "inspect stdout/stderr manually before feature interpretation"


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    rows = read_tsv(root / "evidence/codex-not-run-phase/safe-target-results.tsv")
    output = []
    counts: Counter[str] = Counter()
    for row in rows:
        if row["execution_status"] not in {"FAIL", "NOT_COLLECTED", "FLAKY"}:
            continue
        stdout = (root / row["stdout_path"]).read_text(encoding="utf-8", errors="replace")
        stderr = (root / row["stderr_path"]).read_text(encoding="utf-8", errors="replace")
        jf, je, messages = junit_messages(root / row["junit_path"]) if row["junit_path"] else (0, 0, [])
        category, reason, next_action = classify(row, stdout + "\n" + stderr, jf, je)
        counts[category] += 1
        output.append(
            {
                "target_id": row["target_id"],
                "test_target": row["test_target"],
                "runner_kind": row["runner_kind"],
                "execution_status": row["execution_status"],
                "exit_code": row["exit_code"],
                "duration_seconds": row["duration_seconds"],
                "failure_category": category,
                "failure_reason": reason,
                "junit_failures": jf,
                "junit_errors": je,
                "junit_messages": " || ".join(messages),
                "diagnostic_tail": compact((stdout + "\n" + stderr)[-3000:]),
                "next_action": next_action,
                "linked_feature_ids": row["linked_feature_ids"],
            }
        )
    path = root / "evidence/codex-not-run-phase/target-failure-analysis.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    summary = {
        "schema": "qa.codex_not_run_failure_analysis.v1",
        "failed_or_not_collected_target_count": len(output),
        "category_counts": dict(sorted(counts.items())),
    }
    (root / "evidence/codex-not-run-phase/failure-analysis-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
