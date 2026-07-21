from __future__ import annotations

import ast
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


ALLOWED_COVERAGE = {"direct", "indirect", "partial"}
STOP = {
    "test", "tests", "valid", "invalid", "result", "results", "evidence", "status", "feature",
    "output", "outputs", "source", "sources", "action", "actions", "path", "paths", "reports",
    "report", "pass", "fail", "failed", "without", "with", "when", "only", "emits", "produces",
    "returns", "records", "required", "requires", "expected", "existing", "mapped", "native",
    "skill", "shim", "route", "routes", "runtime", "file", "files", "input", "inputs", "behavior",
    "correct", "documented", "applicable", "supported", "actual", "area", "atomic", "level", "using",
    "each", "does", "into", "from", "that", "this", "have", "has", "and", "the", "for", "not",
    "all", "any", "where", "appropriate", "record", "include", "includes", "including", "per",
}
APPROVAL_RE = re.compile(
    r"\b(gate|gated|approval|approved|authorization)\b",
    re.I,
)
EXTERNAL_ENV_RE = re.compile(
    r"\b(provider|provider credential|credentials?|api[_ -]?key|network|remote execution|"
    r"remote machine|browser profile|playwright|chromium|email send|github release|package publish|"
    r"ssh\b|smtp\b)\b",
    re.I,
)
TESTCASE_BOUNDARY_RE = re.compile(
    r"\b(gate|gated|approval|approved|unapproved|authorization|credential|api key|provider|remote|network|online|"
    r"email|ssh|smtp|playwright|chromium|browser profile|runtime proof|side effect access)\b",
    re.I,
)
TEST_TARGET_BOUNDARY_RE = re.compile(r"\b(gates?|gated|approval|live provider|runtime proof)\b", re.I)


def stem(token: str) -> str:
    for suffix in ("ization", "ations", "ation", "ments", "ment", "ingly", "edly", "ing", "ies", "ied", "es", "ed", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)] + ("y" if suffix in {"ies", "ied"} else "")
    return token


def tokens(text: str) -> set[str]:
    return {
        stem(token)
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 3 and token not in STOP
    }


def executable_kind(relative: str) -> str | None:
    path = Path(relative)
    name = path.name.lower()
    lower = relative.lower()
    if lower.endswith(".py") and name != "__init__.py" and (name.startswith("test") or "/tests/" in lower):
        return "pytest"
    if lower.endswith(".sh") and name.startswith("test"):
        return "shell"
    if lower.endswith((".test.js", ".spec.js", ".test.ts", ".spec.ts")):
        return "bun"
    if lower.endswith(".rs") and ("/tests/" in lower or name == "tests.rs"):
        return "cargo"
    return None


def python_test_names(path: Path) -> list[str]:
    names: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            names.append(node.name)
    return sorted(set(names))


def discovered_test_names(path: Path, kind: str) -> list[str]:
    if kind == "pytest":
        return python_test_names(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    if kind == "bun":
        return sorted(set(re.findall(r"\b(?:test|it)\s*\(\s*[\"'`]([^\"'`]+)", text)))
    if kind == "cargo":
        return sorted(set(re.findall(r"\bfn\s+(test_[A-Za-z0-9_]+)", text)))
    return [path.stem]


def semantically_relevant(entry: dict[str, str], relative: str, names: list[str]) -> list[str]:
    atomic = tokens(entry["atomic_feature"])
    full = tokens(entry["feature_path"])
    path_tokens = tokens(relative)
    selected: list[str] = []
    for name in names or [Path(relative).stem]:
        boundary_name = re.sub(r"[_-]+", " ", name)
        if TESTCASE_BOUNDARY_RE.search(boundary_name):
            continue
        candidate = tokens(name) | path_tokens
        atomic_overlap = atomic & candidate
        full_overlap = full & candidate
        if len(atomic_overlap) >= 2 or any(len(token) >= 10 for token in atomic_overlap):
            selected.append(name)
    return selected


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    phase_name = sys.argv[2] if len(sys.argv) > 2 else "eligible-full-phase"
    checkout = root / "tmp/checkout"
    evidence = root / "evidence" / phase_name
    evidence.mkdir(parents=True, exist_ok=True)
    entry_rows = {row["feature_id"]: row for row in csv.DictReader((root / "feature-entrypoint-map.csv").open())}
    test_rows = {row["feature_id"]: row for row in csv.DictReader((root / "feature-existing-test-map.csv").open())}
    test_name_cache: dict[str, list[str]] = {}
    eligible: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    target_features: dict[str, set[str]] = defaultdict(set)
    target_names: dict[str, set[str]] = defaultdict(set)
    target_kinds: dict[str, str] = {}

    for feature_id, test in test_rows.items():
        entry = entry_rows[feature_id]
        feature_boundary_text = " ".join(
            [entry["atomic_feature"], entry["feature_path"], entry["input_class"], entry["side_effect_policy"]]
        )
        reason = ""
        if test["coverage_status"] not in ALLOWED_COVERAGE:
            reason = f"coverage_{test['coverage_status']}"
        elif APPROVAL_RE.search(feature_boundary_text):
            reason = "approval_or_authorization_gate"
        elif EXTERNAL_ENV_RE.search(feature_boundary_text):
            reason = "external_environment_or_credentials"

        selected_targets: list[str] = []
        selected_names: list[str] = []
        tracked_executable_count = 0
        if not reason:
            for raw in test["existing_test_files"].split(";"):
                relative = raw.strip()
                if not relative:
                    continue
                kind = executable_kind(relative)
                path = checkout / relative
                if not kind or not path.is_file():
                    continue
                tracked_executable_count += 1
                if TEST_TARGET_BOUNDARY_RE.search(re.sub(r"[/_.-]+", " ", relative)):
                    continue
                if relative not in test_name_cache:
                    test_name_cache[relative] = discovered_test_names(path, kind)
                names = test_name_cache[relative]
                relevant_names = semantically_relevant(entry, relative, names)
                if relevant_names:
                    selected_targets.append(relative)
                    selected_names.extend(f"{relative}::{name}" for name in relevant_names)
                    target_features[relative].add(feature_id)
                    target_names[relative].update(relevant_names)
                    target_kinds[relative] = kind

        if not reason and not selected_targets:
            reason = "no_semantically_relevant_executable_test" if tracked_executable_count else "no_tracked_executable_test"

        base = {
            "feature_id": feature_id,
            "parts": entry["parts"],
            "atomic_feature": entry["atomic_feature"],
            "feature_path": entry["feature_path"],
            "coverage_status_before_validation": test["coverage_status"],
            "mapping_confidence": entry["mapping_confidence"],
            "selected_test_targets": ";".join(sorted(set(selected_targets))),
            "selected_testcases": ";".join(sorted(set(selected_names))),
        }
        if reason:
            excluded.append({**base, "eligibility": "excluded", "eligibility_reason": reason})
        else:
            eligible.append({**base, "eligibility": "eligible", "eligibility_reason": "mapped_safe_executable_test"})

    target_rows: list[dict[str, object]] = []
    for index, relative in enumerate(sorted(target_features), start=1):
        target_rows.append(
            {
                "target_id": f"eligible-{index:04d}",
                "runner_kind": target_kinds[relative],
                "test_target": relative,
                "linked_feature_count": len(target_features[relative]),
                "linked_feature_ids": ";".join(sorted(target_features[relative])),
                "relevant_testcases": ";".join(sorted(target_names[relative])),
            }
        )

    feature_fields = [
        "feature_id", "parts", "atomic_feature", "feature_path", "coverage_status_before_validation",
        "mapping_confidence", "selected_test_targets", "selected_testcases", "eligibility", "eligibility_reason",
    ]
    write_csv(evidence / "eligible-features.csv", eligible, feature_fields)
    write_csv(evidence / "excluded-features.csv", excluded, feature_fields)
    write_csv(
        evidence / "target-feature-map.csv",
        target_rows,
        ["target_id", "runner_kind", "test_target", "linked_feature_count", "linked_feature_ids", "relevant_testcases"],
    )
    reason_counts: dict[str, int] = defaultdict(int)
    for row in excluded:
        reason_counts[str(row["eligibility_reason"])] += 1
    kind_counts: dict[str, int] = defaultdict(int)
    for row in target_rows:
        kind_counts[str(row["runner_kind"])] += 1
    summary = {
        "schema": "qa.eligible_full_phase_manifest.v1",
        "phase_name": phase_name,
        "definition": {
            "included_coverage": sorted(ALLOWED_COVERAGE),
            "excluded": [
                "coverage missing/gated/manual-only/not-applicable",
                "approval or authorization gate",
                "external credentials/provider/network/remote/browser-profile environment",
                "no tracked executable test",
                "heuristic mapping not semantically supported by committed testcase/file names",
            ],
        },
        "eligible_feature_count": len(eligible),
        "excluded_feature_count": len(excluded),
        "execution_target_count": len(target_rows),
        "target_kind_counts": dict(sorted(kind_counts.items())),
        "exclusion_reason_counts": dict(sorted(reason_counts.items())),
    }
    (evidence / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
