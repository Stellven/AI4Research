from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def split_items(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[;,]", value or "") if item.strip()]


STOP_TOKENS = {
    "test", "tests", "valid", "invalid", "result", "results", "evidence", "status", "feature",
    "output", "outputs", "source", "sources", "action", "actions", "path", "paths", "reports",
    "report", "pass", "fail", "failed", "without", "with", "when", "only", "emits", "produces",
    "returns", "records", "required", "requires", "expected", "existing", "mapped", "native",
    "autosci", "skill", "shim", "route", "routes", "runtime", "file", "files", "input", "inputs",
}


def semantic_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) >= 3 and token not in STOP_TOKENS
    }


def semantically_relevant(case_name: str, feature_text: str) -> bool:
    overlap = semantic_tokens(case_name) & semantic_tokens(feature_text)
    return len(overlap) >= 2 or any(len(token) >= 10 for token in overlap)


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    entry_rows = {row["feature_id"]: row for row in csv.DictReader((root / "feature-entrypoint-map.csv").open())}
    test_rows = {row["feature_id"]: row for row in csv.DictReader((root / "feature-existing-test-map.csv").open())}
    missing_rows = {row["feature_id"]: row for row in csv.DictReader((root / "missing-test-plan.csv").open())}
    criteria_rows = {row["feature_id"]: row for row in csv.DictReader((root / "pass-fail-criteria.csv").open())}

    cases_by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
    files: dict[str, Counter[str]] = defaultdict(Counter)
    for row in csv.DictReader((root / "evidence/testcase-results.csv").open()):
        cases_by_name[row["testcase"]].append(row)
        files[row["test_file"]][row["status"]] += 1

    shell_path = root / "evidence/shell-sweep-installed-home/shell-sweep-summary.json"
    shell_status: dict[str, str] = {}
    if shell_path.exists():
        for row in json.loads(shell_path.read_text())["results"]:
            shell_status[row["test"]] = row["status"]

    installer_pass_ids = {
        "WF-0001-INSTALL-COMPLETES-USER-SCOPED-190948",
        "WF-0002-VERIFICATION-REPORTS-DETERMINISTIC-DEPENDENCY-6F3D30",
        "WF-0003-MISSING-DEPENDENCY-YIELDS-EXPLICIT-3493D5",
    }
    explicit_feature_defects = {
        "WF-0057-EXECUTION-READY-ONLY-WHEN-C66D5E": "D-003",
        "WF-0067-NO-CODE-REMOTE-EXECUTION-9BB20A": "D-003",
        "WF-0069-MODE-SPECIFIC-COMMAND-APPROVAL-E7B0E0": "D-003",
        "WF-0070-MISSING-CONTRACT-YIELDS-INCONCLUSIVE-3260D2": "D-003",
        "WF-0135-REPORTS-MISSING-PRESENT-CONFIG-9BF2D6": "D-007",
        "WF-0136-NONINTERACTIVE-MISSING-VALUES-PRODUCE-D7413D": "D-007",
        "WF-0137-WRITES-OCCUR-ONLY-EXPLICIT-2CB04C": "D-007",
        "WF-0138-SETUP-READINESS-DISTINGUISHES-DETERMINISTIC-1BF3FE": "D-007",
        "WF-0151-VALID-PDF-SOURCE-PREPARATION-97CC16": "D-008",
        "WF-0156-SOURCE-FULLY-REGISTERED-ONLY-748617": "D-008",
        "WF-0344-NODE-MAPPED-CORRECT-LOGICAL-9D8FAC": "D-003",
        "WF-0345-NODE-EMITS-VALIDATES-EXPERIMENT-284628": "D-003",
        "WF-0346-GATE-ACCEPTS-VALID-EVIDENCE-83279C": "D-003",
        "WF-0347-COMPLETED-EVIDENCE-REUSED-FAILED-86886E": "D-003",
        "WF-0348-NODE-RUNS-ONLY-WHEN-92AD28": "D-003",
    }

    rows: list[dict[str, str]] = []
    for feature_id, entry in entry_rows.items():
        test = test_rows[feature_id]
        missing = missing_rows[feature_id]
        criteria = criteria_rows[feature_id]
        expected_cases = set(split_items(test.get("existing_test_cases", "")))
        expected_files = split_items(test.get("existing_test_files", ""))
        feature_text = f"{entry['atomic_feature']} {entry['feature_path']}"
        expected_cases = {name for name in expected_cases if semantically_relevant(name, feature_text)}
        matched: list[dict[str, str]] = []
        for case_name in expected_cases:
            matched.extend(cases_by_name.get(case_name, []))
        # Some generated case lists carry parameter suffixes or class prefixes.
        if not matched and expected_cases:
            for actual_name, actual_rows in cases_by_name.items():
                if any(actual_name.startswith(candidate + "[") or candidate.startswith(actual_name + "[") for candidate in expected_cases):
                    matched.extend(actual_rows)
        observed = Counter(row["status"] for row in matched)
        observed_files = [path for path in expected_files if path in files]
        shell_observed = {path: shell_status[path] for path in expected_files if path in shell_status}

        status = "NOT_RUN"
        rationale = "No feature-specific executed evidence was strong enough for a terminal verdict."
        defect_ids: list[str] = []
        evidence_ids: list[str] = []
        coverage = test["coverage_status"]
        high_direct = coverage == "direct" and test["test_confidence"] == "high" and test["direct_test_present"] == "yes"
        combined = " ".join(entry.values()).lower()

        if feature_id in explicit_feature_defects:
            status = "FAIL"
            defect_ids.append(explicit_feature_defects[feature_id])
            rationale = "Directly affected by a reproducible defect in the audited surface."
        elif feature_id in installer_pass_ids:
            status = "PASS"
            evidence_ids.extend(["phase5_install_isolated", "phase5_doctor_json", "phase5_validate_install_doctor_contract"])
            rationale = "Isolated component install succeeded and the doctor/receipt/path/schema contract was validated."
        elif high_direct and (observed["FAIL"] or observed["ERROR"]):
            if any("harness/tests/data_plane/" in row["test_file"] for row in matched):
                status = "SKIPPED_ENV"
                rationale = "Direct test requires a provisioned Knowledge/QMD/MinerU data plane that was intentionally absent."
            else:
                status = "FAIL"
                suites = {row["suite"] for row in matched if row["status"] in {"FAIL", "ERROR"}}
                if "autosci_plugin" in suites:
                    evidence_ids.append("phase4_autosci_plugin_pytest_final")
                if "scientific_evaluators" in suites:
                    evidence_ids.append("phase4_scientific_evaluator_pytest_final")
                if any(name.startswith("pytest_matrix:") for name in suites):
                    evidence_ids.append("phase4_pytest_matrix_installed_home")
                rationale = f"Mapped direct test evidence contains {observed['FAIL']} failure(s) and {observed['ERROR']} collection error(s)."
        elif high_direct and observed["PASS"] and not (observed["FAIL"] or observed["ERROR"]):
            status = "PASS"
            if any(row["suite"] == "autosci_plugin" for row in matched):
                evidence_ids.append("phase4_autosci_plugin_pytest_final")
            if any(row["suite"] == "scientific_evaluators" for row in matched):
                evidence_ids.append("phase4_scientific_evaluator_pytest_final")
            if any(row["suite"].startswith("pytest_matrix:") for row in matched):
                evidence_ids.append("phase4_pytest_matrix_installed_home")
            rationale = f"{observed['PASS']} mapped direct testcase(s) passed with no mapped failure/error."
        elif high_direct and shell_observed:
            if any(value == "FAIL" for value in shell_observed.values()):
                status = "FAIL"
                rationale = "Mapped direct shell test failed in the authoritative isolated installed-home sweep."
            else:
                status = "PASS"
                rationale = "Mapped direct shell test passed in the authoritative isolated installed-home sweep."
            evidence_ids.append("phase4_shell_test_sweep_installed_home")
        elif coverage == "gated" and observed["PASS"] and not (observed["FAIL"] or observed["ERROR"]):
            status = "BLOCKED_EXPECTED"
            evidence_ids.append("phase4_autosci_plugin_pytest_final")
            rationale = "Mapped gate test passed and retained the approval/continuation boundary; no live side effect was executed."
        elif observed["SKIPPED"] and not observed["PASS"]:
            status = "SKIPPED_ENV"
            rationale = "Mapped test self-skipped because its optional environment/provider was unavailable."
        elif any(token in combined for token in ("live provider", "email send", "remote execution", "real browser", "playwright", "network source")):
            status = "SKIPPED_ENV"
            rationale = "Live/provider/network/browser execution is outside the approved first-audit environment."

        if "multi_task_runner.py" in combined and "status" in entry["atomic_feature"].lower():
            if status != "FAIL":
                status = "FAIL"
                rationale = "Graph status suite cannot collect because epic_child_status_lines is absent."
            defect_ids.append("D-002")
        rows.append({
            "feature_id": feature_id,
            "parts": entry["parts"],
            "atomic_feature": entry["atomic_feature"],
            "feature_path": entry["feature_path"],
            "entrypoints": entry["discovered_entrypoints"] or entry["seeded_entrypoint_candidates"],
            "implementation_files_functions": entry["implementation_files_functions"],
            "existing_tests": test["existing_test_files"],
            "coverage_status": coverage,
            "missing_test_recommendation": missing["recommendation"],
            "happy_path_pass_criteria": criteria["happy_path_pass_criteria"],
            "negative_failure_pass_criteria": criteria["negative_failure_pass_criteria"],
            "fail_criteria": criteria["fail_criteria"],
            "execution_evidence": ";".join(dict.fromkeys(evidence_ids)),
            "final_result_status": status,
            "result_rationale": rationale,
            "defect_ids": ";".join(dict.fromkeys(defect_ids)),
            "mapping_confidence": entry["mapping_confidence"],
        })

    with (root / "feature-results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "feature_count": len(rows),
        "status_counts": dict(Counter(row["final_result_status"] for row in rows)),
        "by_part": {
            part: dict(Counter(row["final_result_status"] for row in rows if row["parts"] == part))
            for part in ("workflow", "foundations", "misc.")
        },
        "method": "Conservative executed-evidence join: only high-confidence direct mappings can PASS/FAIL automatically; indirect/partial evidence remains NOT_RUN unless explicitly classified.",
    }
    (root / "evidence/feature-results-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
