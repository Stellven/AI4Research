from __future__ import annotations

import csv
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_PHASE_NAME = "eligible-full-phase-v2"
RECLASSIFY_REASONS = {
    "no_semantically_relevant_executable_test",
    "no_tracked_executable_test",
}
STATUS_ORDER = [
    "PASS", "FAIL", "BLOCKED_EXPECTED", "INCONCLUSIVE_EXPECTED",
    "SKIPPED_NA", "SKIPPED_ENV", "FLAKY", "NOT_RUN",
]


def read_csv(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def testcase_status(case: ET.Element) -> tuple[str, str]:
    for tag, status in (("failure", "FAIL"), ("error", "ERROR"), ("skipped", "SKIPPED")):
        node = case.find(tag)
        if node is not None:
            message = node.attrib.get("message", "") or (node.text or "")
            return status, " ".join(message.split())[:1200]
    return "PASS", ""


def base_test_name(name: str) -> str:
    return name.split("[", 1)[0]


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    phase_name = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PHASE_NAME
    phase = root / "evidence" / phase_name
    target_map = {row["target_id"]: row for row in read_csv(phase / "target-feature-map.csv")}
    target_results = {row["target_id"]: row for row in read_csv(phase / "target-results.tsv", "\t")}
    eligible = {row["feature_id"]: row for row in read_csv(phase / "eligible-features.csv")}
    excluded = {row["feature_id"]: row for row in read_csv(phase / "excluded-features.csv")}

    testcase_rows: list[dict[str, object]] = []
    cases_by_target: dict[str, list[dict[str, object]]] = defaultdict(list)
    for target_id, target in target_map.items():
        result = target_results[target_id]
        junit_rel = result.get("junit_path", "")
        if junit_rel and (root / junit_rel).is_file():
            try:
                junit_root = ET.parse(root / junit_rel).getroot()
            except ET.ParseError as error:
                row = {
                    "target_id": target_id,
                    "test_target": target["test_target"],
                    "classname": "",
                    "testcase_name": "<junit-parse-error>",
                    "base_testcase_name": "<junit-parse-error>",
                    "status": "ERROR",
                    "duration_seconds": "",
                    "message": str(error),
                }
                testcase_rows.append(row)
                cases_by_target[target_id].append(row)
                continue
            for case in junit_root.iter("testcase"):
                status, message = testcase_status(case)
                name = case.attrib.get("name", "")
                row = {
                    "target_id": target_id,
                    "test_target": target["test_target"],
                    "classname": case.attrib.get("classname", ""),
                    "testcase_name": name,
                    "base_testcase_name": base_test_name(name),
                    "status": status,
                    "duration_seconds": case.attrib.get("time", ""),
                    "message": message,
                }
                testcase_rows.append(row)
                cases_by_target[target_id].append(row)

    testcase_fields = [
        "target_id", "test_target", "classname", "testcase_name", "base_testcase_name",
        "status", "duration_seconds", "message",
    ]
    write_csv(phase / "testcase-results.csv", testcase_rows, testcase_fields)
    write_csv(
        phase / "failed-testcases.csv",
        [row for row in testcase_rows if row["status"] in {"FAIL", "ERROR"}],
        testcase_fields,
    )

    target_ids_by_path = {row["test_target"]: row["target_id"] for row in target_map.values()}
    feature_execution_rows: list[dict[str, object]] = []
    feature_execution: dict[str, dict[str, object]] = {}
    for feature_id, feature in eligible.items():
        requested = []
        for item in feature["selected_testcases"].split(";"):
            item = item.strip()
            if not item or "::" not in item:
                continue
            test_target, test_name = item.rsplit("::", 1)
            requested.append((test_target, test_name))

        matched: list[dict[str, object]] = []
        target_statuses: list[str] = []
        evidence_paths: set[str] = set()
        for target_path in filter(None, feature["selected_test_targets"].split(";")):
            target_id = target_ids_by_path[target_path]
            target_result = target_results[target_id]
            target_statuses.append(f"{target_id}:{target_result['execution_status']}")
            evidence_paths.update(filter(None, [target_result.get("stdout_path", ""), target_result.get("stderr_path", ""), target_result.get("junit_path", "")]))
        for target_path, selected_name in requested:
            target_id = target_ids_by_path[target_path]
            for case in cases_by_target.get(target_id, []):
                if case["base_testcase_name"] == selected_name or case["testcase_name"] == selected_name:
                    matched.append(case)

        counts = Counter(str(row["status"]) for row in matched)
        shell_results = []
        selected_target_execution_statuses = []
        for target_path in filter(None, feature["selected_test_targets"].split(";")):
            target_id = target_ids_by_path[target_path]
            selected_target_execution_statuses.append(target_results[target_id]["execution_status"])
            if target_map[target_id]["runner_kind"] == "shell":
                shell_results.append(target_results[target_id]["execution_status"])

        expected_count = len(set(requested))
        matched_names = {(str(row["test_target"]), str(row["base_testcase_name"])) for row in matched}
        unmatched_count = len({item for item in requested if item not in matched_names})
        if counts["FAIL"] or counts["ERROR"] or "FAIL" in shell_results:
            executed_result = "FAIL"
        elif counts["PASS"] or "PASS" in shell_results:
            executed_result = "PASS"
        elif counts["SKIPPED"] or "SKIPPED_ENV" in shell_results:
            executed_result = "SKIPPED_ENV"
        elif "FLAKY" in shell_results:
            executed_result = "FLAKY"
        elif "FAIL" in selected_target_execution_statuses:
            executed_result = "FAIL"
        else:
            executed_result = "NOT_RUN"

        coverage = feature["coverage_status_before_validation"]
        confidence = feature["mapping_confidence"]
        if executed_result == "FAIL" and coverage == "direct" and confidence == "high":
            final_interpretation = "FAIL"
            interpretation_reason = "A semantically selected, high-confidence direct testcase failed or errored."
        elif executed_result == "PASS" and coverage == "direct" and confidence == "high":
            final_interpretation = "PASS"
            interpretation_reason = "All selected high-confidence direct testcases passed."
        elif executed_result == "SKIPPED_ENV":
            final_interpretation = "SKIPPED_ENV"
            interpretation_reason = "Selected testcases were collected but skipped for the isolated environment."
        elif executed_result == "FLAKY":
            final_interpretation = "FLAKY"
            interpretation_reason = "The selected target timed out."
        elif executed_result == "NOT_RUN":
            final_interpretation = "NOT_RUN"
            interpretation_reason = "The selected testcase was not collected; execution evidence is incomplete."
        else:
            final_interpretation = "INCONCLUSIVE_EXPECTED"
            interpretation_reason = (
                f"The mapped {coverage} / {confidence}-confidence test was executed ({executed_result}), "
                "but it is not sufficient direct proof of the complete atomic contract."
            )
        row = {
            "feature_id": feature_id,
            "parts": feature["parts"],
            "atomic_feature": feature["atomic_feature"],
            "coverage_status": coverage,
            "mapping_confidence": confidence,
            "selected_test_targets": feature["selected_test_targets"],
            "selected_testcases": feature["selected_testcases"],
            "expected_selected_testcase_count": expected_count,
            "matched_testcase_count": len(matched),
            "unmatched_selected_testcase_count": unmatched_count,
            "testcase_pass": counts["PASS"],
            "testcase_fail": counts["FAIL"],
            "testcase_error": counts["ERROR"],
            "testcase_skip": counts["SKIPPED"],
            "target_statuses": ";".join(sorted(target_statuses)),
            "execution_result": executed_result,
            "final_interpretation": final_interpretation,
            "interpretation_reason": interpretation_reason,
            "evidence_paths": ";".join(sorted(evidence_paths)),
        }
        feature_execution_rows.append(row)
        feature_execution[feature_id] = row

    feature_execution_fields = [
        "feature_id", "parts", "atomic_feature", "coverage_status", "mapping_confidence",
        "selected_test_targets", "selected_testcases", "expected_selected_testcase_count",
        "matched_testcase_count", "unmatched_selected_testcase_count", "testcase_pass",
        "testcase_fail", "testcase_error", "testcase_skip", "target_statuses", "execution_result",
        "final_interpretation", "interpretation_reason", "evidence_paths",
    ]
    write_csv(phase / "feature-execution-results.csv", feature_execution_rows, feature_execution_fields)

    feature_rows = read_csv(root / "feature-results.csv")
    added_feature_fields = [
        "eligible_phase_scope", "eligible_phase_execution_result", "eligible_phase_testcase_counts",
        "eligible_phase_selected_targets", "eligible_phase_selected_testcases", "eligible_phase_evidence",
    ]
    feature_fields = list(feature_rows[0]) + [field for field in added_feature_fields if field not in feature_rows[0]]
    for row in feature_rows:
        feature_id = row["feature_id"]
        if feature_id in feature_execution:
            execution = feature_execution[feature_id]
            row["eligible_phase_scope"] = "eligible_executed"
            row["eligible_phase_execution_result"] = str(execution["execution_result"])
            row["eligible_phase_testcase_counts"] = (
                f"pass={execution['testcase_pass']};fail={execution['testcase_fail']};"
                f"error={execution['testcase_error']};skip={execution['testcase_skip']};"
                f"matched={execution['matched_testcase_count']};unmatched={execution['unmatched_selected_testcase_count']}"
            )
            row["eligible_phase_selected_targets"] = str(execution["selected_test_targets"])
            row["eligible_phase_selected_testcases"] = str(execution["selected_testcases"])
            row["eligible_phase_evidence"] = str(execution["evidence_paths"])
            old_status = row["final_result_status"]
            interpreted = str(execution["final_interpretation"])
            if old_status == "FAIL" or interpreted == "FAIL":
                row["final_result_status"] = "FAIL"
            elif old_status == "PASS":
                row["final_result_status"] = "PASS"
            else:
                row["final_result_status"] = interpreted
            row["execution_evidence"] = ";".join(filter(None, [row["execution_evidence"], f"{phase_name}/feature-execution-results.csv", str(execution["evidence_paths"])]))
            if old_status == "PASS" and interpreted != "FAIL":
                row["result_rationale"] = (
                    row["result_rationale"] + " Eligible-phase mapped tests were executed; prior stronger PASS evidence was retained."
                ).strip()
            else:
                row["result_rationale"] = str(execution["interpretation_reason"])
        else:
            exclusion = excluded[feature_id]
            reason = exclusion["eligibility_reason"]
            row["eligible_phase_scope"] = f"excluded:{reason}"
            row["eligible_phase_execution_result"] = "NOT_APPLICABLE_TO_PHASE"
            row["eligible_phase_testcase_counts"] = ""
            row["eligible_phase_selected_targets"] = ""
            row["eligible_phase_selected_testcases"] = ""
            row["eligible_phase_evidence"] = f"evidence/{phase_name}/excluded-features.csv"
            if reason in RECLASSIFY_REASONS:
                row["coverage_status"] = "missing"
                row["existing_tests"] = ""
                row["missing_test_recommendation"] = (
                    "Add a semantically direct executable test; the prior heuristic candidate mapping was rejected during eligibility validation."
                )
    write_csv(root / "feature-results.csv", feature_rows, feature_fields)

    existing_rows = read_csv(root / "feature-existing-test-map.csv")
    added_existing_fields = [
        "eligibility_validation", "eligibility_reason", "eligible_phase_selected_targets",
        "eligible_phase_selected_testcases", "eligible_phase_execution_result", "eligible_phase_evidence",
    ]
    existing_fields = list(existing_rows[0]) + [field for field in added_existing_fields if field not in existing_rows[0]]
    for row in existing_rows:
        feature_id = row["feature_id"]
        if feature_id in feature_execution:
            execution = feature_execution[feature_id]
            row["eligibility_validation"] = "eligible_executed"
            row["eligibility_reason"] = "mapped_safe_executable_test"
            row["eligible_phase_selected_targets"] = str(execution["selected_test_targets"])
            row["eligible_phase_selected_testcases"] = str(execution["selected_testcases"])
            row["eligible_phase_execution_result"] = str(execution["execution_result"])
            row["eligible_phase_evidence"] = str(execution["evidence_paths"])
        else:
            exclusion = excluded[feature_id]
            reason = exclusion["eligibility_reason"]
            row["eligibility_validation"] = "excluded"
            row["eligibility_reason"] = reason
            row["eligible_phase_selected_targets"] = ""
            row["eligible_phase_selected_testcases"] = ""
            row["eligible_phase_execution_result"] = "NOT_APPLICABLE_TO_PHASE"
            row["eligible_phase_evidence"] = f"evidence/{phase_name}/excluded-features.csv"
            if reason in RECLASSIFY_REASONS:
                row["coverage_status"] = "missing"
                row["direct_test_present"] = "no"
                row["indirect_smoke_present"] = "no"
                row["test_confidence"] = "low"
                row["gap_to_confirm"] = (
                    "Prior heuristic candidates were not semantically relevant executable tests for this atomic feature."
                )
    write_csv(root / "feature-existing-test-map.csv", existing_rows, existing_fields)

    missing_rows = read_csv(root / "missing-test-plan.csv")
    for row in missing_rows:
        feature_id = row["feature_id"]
        if feature_id in feature_execution:
            execution = feature_execution[feature_id]
            if execution["final_interpretation"] == "PASS":
                row["missing_test_status"] = "validated_direct_executed"
                row["recommendation"] = "Existing high-confidence direct test executed successfully; retain and tag it with the feature ID."
            elif execution["execution_result"] == "FAIL":
                row["missing_test_status"] = "existing_test_failed"
                row["recommendation"] = "Fix or intentionally update the selected existing test before adding broader coverage."
            else:
                row["missing_test_status"] = "direct_test_still_recommended"
        elif excluded[feature_id]["eligibility_reason"] in RECLASSIFY_REASONS:
            row["missing_test_status"] = "missing_validated"
            row["recommendation"] = (
                "Add a semantically direct executable test; eligibility validation rejected the prior heuristic mapping."
            )
    write_csv(root / "missing-test-plan.csv", missing_rows, list(missing_rows[0]))

    status_counts = Counter(row["final_result_status"] for row in feature_rows)
    by_part: dict[str, Counter[str]] = defaultdict(Counter)
    for row in feature_rows:
        by_part[row["parts"]][row["final_result_status"]] += 1
    summary = {
        "feature_count": len(feature_rows),
        "status_counts": {status: status_counts[status] for status in STATUS_ORDER if status_counts[status]},
        "by_part": {part: dict(counts) for part, counts in by_part.items()},
        "method": (
            "Eligible-phase exact-testcase reconciliation: all semantically selected safe targets were attempted. "
            "Only high-confidence direct mappings promote PASS/FAIL; indirect/partial or lower-confidence executions are INCONCLUSIVE_EXPECTED unless prior stronger evidence exists."
        ),
        "eligible_phase": {
            "eligible_features": len(eligible),
            "execution_targets": len(target_map),
            "all_targets_attempted": len(target_results) == len(target_map),
            "target_status_counts": dict(Counter(row["execution_status"] for row in target_results.values())),
            "testcase_status_counts": dict(Counter(row["status"] for row in testcase_rows)),
            "feature_execution_result_counts": dict(Counter(str(row["execution_result"]) for row in feature_execution_rows)),
            "feature_interpretation_counts": dict(Counter(str(row["final_interpretation"]) for row in feature_execution_rows)),
            "reclassified_missing_features": sum(1 for row in excluded.values() if row["eligibility_reason"] in RECLASSIFY_REASONS),
        },
    }
    (root / "evidence/feature-results-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (phase / "reconciliation-summary.json").write_text(json.dumps(summary["eligible_phase"], indent=2) + "\n", encoding="utf-8")

    target_failure_rows = []
    for target_id, result in target_results.items():
        if result["execution_status"] != "FAIL":
            continue
        failed = [row for row in cases_by_target.get(target_id, []) if row["status"] in {"FAIL", "ERROR"}]
        target_failure_rows.append({
            "target_id": target_id,
            "test_target": result["test_target"],
            "linked_feature_count": result["linked_feature_count"],
            "testcase_failures_and_errors": len(failed),
            "failed_testcases": ";".join(str(row["testcase_name"]) for row in failed),
            "first_message": str(failed[0]["message"]) if failed else "target exited nonzero without a JUnit failure node",
            "stdout_path": result["stdout_path"],
            "stderr_path": result["stderr_path"],
            "junit_path": result["junit_path"],
        })
    failure_fields = [
        "target_id", "test_target", "linked_feature_count", "testcase_failures_and_errors",
        "failed_testcases", "first_message", "stdout_path", "stderr_path", "junit_path",
    ]
    write_csv(phase / "target-failure-summary.csv", target_failure_rows, failure_fields)

    print(json.dumps(summary["eligible_phase"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
