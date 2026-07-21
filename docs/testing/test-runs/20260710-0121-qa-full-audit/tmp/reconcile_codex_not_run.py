from __future__ import annotations

import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


def read_csv(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def junit_cases(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    if not path.is_file():
        return result
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return result
    for case in root.iter("testcase"):
        name = case.attrib.get("name", "")
        base = name.split("[", 1)[0]
        if case.find("failure") is not None:
            status = "FAIL"
        elif case.find("error") is not None:
            status = "ERROR"
        elif case.find("skipped") is not None:
            status = "SKIPPED"
        else:
            status = "PASS"
        result[base].append(status)
    return result


def load_latest_results(root: Path) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, list[str]]]]:
    phase = root / "evidence/codex-not-run-phase"
    by_target: dict[str, dict[str, str]] = {}
    for name in ("safe-target-results.tsv", "infrastructure-rerun-results.tsv", "reviewed-shell-results.tsv"):
        path = phase / name
        if not path.is_file():
            continue
        for row in read_csv(path, "\t"):
            by_target[row["test_target"]] = {**row, "result_source": str(path.relative_to(root))}
    case_maps: dict[str, dict[str, list[str]]] = {}
    for target, row in by_target.items():
        junit = row.get("junit_path", "")
        case_maps[target] = junit_cases(root / junit) if junit else {}
    return by_target, case_maps


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    phase = root / "evidence/codex-not-run-phase"
    remap = read_csv(phase / "feature-test-remap.csv")
    plan = read_csv(phase / "execution-plan.csv")
    plan_by_target = {row["test_target"]: row for row in plan}
    latest, cases_by_target = load_latest_results(root)
    output = []
    status_counts: Counter[str] = Counter()
    mapping_counts: Counter[str] = Counter()
    for feature in remap:
        classification = feature["remap_classification"]
        mapping_counts[classification] += 1
        selected_nodeids = [item for item in feature["selected_testcases"].split(";") if item]
        selected_targets = [item for item in feature["selected_test_targets"].split(";") if item]
        selected_statuses: list[str] = []
        matched_cases: list[str] = []
        unmatched_cases: list[str] = []
        evidence: set[str] = set()
        target_statuses: list[str] = []
        for target in selected_targets:
            result = latest.get(target)
            category = plan_by_target.get(target, {}).get("plan_category", "unplanned")
            if result:
                target_statuses.append(f"{target}:{result['execution_status']}")
                evidence.update(filter(None, [result.get("stdout_path", ""), result.get("stderr_path", ""), result.get("junit_path", ""), result.get("result_source", "")]))
            else:
                target_statuses.append(f"{target}:NOT_RUN({category})")
        for nodeid in selected_nodeids:
            target = nodeid.split("::", 1)[0]
            if "::" not in nodeid:
                continue
            name = nodeid.rsplit("::", 1)[-1].split("[", 1)[0]
            statuses = cases_by_target.get(target, {}).get(name, [])
            if statuses:
                selected_statuses.extend(statuses)
                matched_cases.append(f"{nodeid}:{'/'.join(statuses)}")
            else:
                unmatched_cases.append(nodeid)

        executed_statuses = [latest[target]["execution_status"] for target in selected_targets if target in latest]
        non_py_direct_pass = any(
            latest[target]["execution_status"] == "PASS"
            and latest[target].get("runner_kind") in {"shell", "node", "bun"}
            for target in selected_targets if target in latest
        )
        if classification == "direct_candidate":
            if any(status in {"FAIL", "ERROR"} for status in selected_statuses):
                provisional = "FAIL"
                reason = "A directly mapped selected testcase failed or errored."
                strength = "direct_assertion"
            elif "PASS" in selected_statuses:
                provisional = "PASS"
                reason = "At least one directly mapped selected testcase passed and no selected direct testcase failed."
                strength = "direct_assertion"
            elif non_py_direct_pass:
                provisional = "PASS"
                reason = "A directly mapped shell/Node contract target passed in the isolated audit checkout."
                strength = "direct_target"
            elif "SKIPPED_ENV" in executed_statuses:
                provisional = "SKIPPED_ENV"
                reason = "The directly mapped target was collected but skipped for the isolated environment."
                strength = "direct_environment"
            elif executed_statuses:
                provisional = "INCONCLUSIVE_EXPECTED"
                reason = "Direct candidate target executed, but the selected atomic assertion was not matched or only the broader target failed."
                strength = "direct_unresolved"
            else:
                provisional = "NOT_RUN"
                reason = "No directly mapped target was executed."
                strength = "none"
        elif classification in {"partial_candidate", "indirect_candidate"}:
            if executed_statuses:
                provisional = "INCONCLUSIVE_EXPECTED"
                reason = f"{classification.replace('_', ' ')} target executed, but it is not complete proof of the atomic contract."
                strength = classification.replace("_candidate", "")
            else:
                provisional = "NOT_RUN"
                reason = f"{classification.replace('_', ' ')} exists, but no corresponding target was executed."
                strength = "none"
        else:
            provisional = "NOT_RUN"
            reason = "No semantically acceptable existing test mapping was found."
            strength = "none"
        status_counts[provisional] += 1
        output.append({
            "feature_id": feature["feature_id"],
            "parts": feature["parts"],
            "atomic_feature": feature["atomic_feature"],
            "feature_path": feature["feature_path"],
            "prior_blocker": feature["prior_blocker"],
            "remap_classification": classification,
            "provisional_result_status": provisional,
            "evidence_strength": strength,
            "result_rationale": reason,
            "selected_test_targets": feature["selected_test_targets"],
            "selected_testcases": feature["selected_testcases"],
            "matched_selected_testcases": ";".join(matched_cases),
            "unmatched_selected_testcases": ";".join(unmatched_cases),
            "target_execution_statuses": ";".join(target_statuses),
            "execution_evidence": ";".join(sorted(evidence)),
            "manual_review_required": "yes" if provisional in {"FAIL", "PASS"} or classification != "direct_candidate" else "no",
        })

    fields = list(output[0])
    write_csv(phase / "provisional-feature-results.csv", output, fields)
    summary = {
        "schema": "qa.codex_not_run_reconciliation.v1",
        "feature_count": len(output),
        "mapping_counts": dict(sorted(mapping_counts.items())),
        "provisional_status_counts": dict(sorted(status_counts.items())),
        "warning": "PASS/FAIL are provisional until direct mappings are manually reviewed; partial/indirect execution remains inconclusive.",
    }
    (phase / "provisional-reconciliation-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
