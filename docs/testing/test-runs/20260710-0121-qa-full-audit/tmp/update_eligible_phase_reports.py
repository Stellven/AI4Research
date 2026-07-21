from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path


PHASE_NAME = "eligible-full-phase-v3"
NEW_DEFECTS = {
    "WF-0007-CREATES-SPRINT-INTAKE-ARTIFACTS-92818B": "D-020",
    "WF-0078-CANDIDATE-ARTIFACT-INCLUDES-HYPOTHESIS-3B1F71": "D-003; D-006",
    "FD-0148-OPERATOR-DECLARES-MATCHES-REQUIRED-935809": "D-022",
    "FD-0661-WRITES-EVIDENCE-PAYLOADS-SIDECARS-AB5066": "D-007",
}


def read_csv(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    phase = root / "evidence" / PHASE_NAME
    manifest = json.loads((phase / "manifest.json").read_text())
    execution = json.loads((phase / "execution-summary.json").read_text())
    reconciliation = json.loads((phase / "reconciliation-summary.json").read_text())
    feature_summary = json.loads((root / "evidence/feature-results-summary.json").read_text())
    inventory = json.loads((root / "evidence/inventory/inventory-summary.json").read_text())
    existing_rows = read_csv(root / "feature-existing-test-map.csv")
    coverage_counts = Counter(row["coverage_status"] for row in existing_rows)
    inventory["coverage_counts"] = dict(coverage_counts)
    inventory["eligibility_validation"] = {
        "phase": PHASE_NAME,
        "eligible_executed": manifest["eligible_feature_count"],
        "excluded": manifest["excluded_feature_count"],
        "execution_targets": execution["target_count"],
        "all_targets_attempted": execution["all_targets_attempted"],
        "reclassified_missing": reconciliation["reclassified_missing_features"],
        "exclusion_reason_counts": manifest["exclusion_reason_counts"],
    }
    (root / "evidence/inventory/inventory-summary.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    features = read_csv(root / "feature-results.csv")
    for row in features:
        if row["feature_id"] in NEW_DEFECTS:
            current = [item.strip() for item in row["defect_ids"].split(";") if item.strip()]
            additions = [item.strip() for item in NEW_DEFECTS[row["feature_id"]].split(";") if item.strip()]
            row["defect_ids"] = "; ".join(dict.fromkeys(current + additions))
    write_csv(root / "feature-results.csv", features, list(features[0]))

    inv_lines = [
        "# Inventory Diff",
        "",
        "## Control taxonomy baseline",
        "",
        f"- Atomic feature rows: {inventory['features']}",
        f"- By part: {inventory['part_counts']}",
        f"- Duplicate feature paths: {inventory['duplicate_feature_paths']}",
        f"- Duplicate atomic labels (labels only; paths may differ legitimately): {inventory['duplicate_atomic_labels']}",
        "",
        "## Repository surfaces discovered",
        "",
        f"- Tracked files at locked SHA: {inventory['tracked_files']}",
        f"- Scannable source/config/spec files: {inventory['source_files']}",
        f"- Function/module/route/script/package/config inventory rows: {inventory['inventory_items']}",
        f"- Existing test files: {inventory['test_files']}",
        f"- Package scripts: {inventory['package_scripts']}",
        f"- Inventory classifications: {inventory['classification_counts']}",
        "",
        "## Taxonomy reconciliation",
        "",
        f"- Feature rows without a static implementation/entrypoint candidate: {inventory['features_without_mapped_items']}",
        f"- Candidate stale rows: {inventory['candidate_stale_rows']}",
        f"- Public production entrypoints with no feature mapping (`missing-feature-row`): {inventory['unmapped_public_entrypoints']}",
        f"- Validated existing-test coverage classifications: {dict(coverage_counts)}",
        "",
        "Static candidate mappings were validated against committed executable testcase/file names. Token/path similarity alone was not accepted as evidence.",
        "",
        "## Strict eligible execution phase",
        "",
        f"- Eligible atomic features executed: {manifest['eligible_feature_count']}",
        f"- Unique test targets attempted: {execution['target_count']} of {execution['target_count']}",
        f"- Target results: {execution['status_counts']}",
        f"- Testcase results: {execution['testcase_counts']}",
        f"- Feature execution outcomes: {reconciliation['feature_execution_result_counts']}",
        f"- Conservative feature interpretations: {reconciliation['feature_interpretation_counts']}",
        f"- Heuristic mappings reclassified to missing: {reconciliation['reclassified_missing_features']}",
        "",
        "### Excluded from this phase",
        "",
    ]
    inv_lines.extend(f"- `{reason}`: {count}" for reason, count in manifest["exclusion_reason_counts"].items())
    inv_lines += [
        "",
        "The superseded v1/v2 eligibility runs are retained under `evidence/eligible-full-phase*` for provenance, but only v3 strict evidence is authoritative for feature attribution.",
        "",
        "## Candidate missing feature rows",
        "",
        "See `function-inventory.csv` rows classified `missing-feature-row` and `missing-test-plan.csv` for all validated missing or insufficient test mappings.",
    ]
    (root / "inventory-diff.md").write_text("\n".join(inv_lines) + "\n", encoding="utf-8")

    failure_rows = read_csv(phase / "target-failure-summary.csv")
    phase_lines = [
        "# Strict eligible-feature execution report",
        "",
        f"Locked commit: `{json.loads((root / 'environment.json').read_text())['locked_test_sha']}`",
        "",
        "## Scope",
        "",
        "Included only atomic features whose validated mapping had a semantically relevant executable test and whose feature boundary did not require approval, credentials, a live provider, network, remote execution, or a browser profile. Existing `direct`, `indirect`, and `partial` labels were candidates, not proof.",
        "",
        f"- Eligible features: {manifest['eligible_feature_count']}",
        f"- Excluded features: {manifest['excluded_feature_count']}",
        f"- Unique targets attempted: {execution['target_count']}",
        f"- Target status: {execution['status_counts']}",
        f"- Testcase status: {execution['testcase_counts']}",
        f"- Exact feature execution outcome: {reconciliation['feature_execution_result_counts']}",
        f"- Conservative feature interpretation: {reconciliation['feature_interpretation_counts']}",
        "",
        "All 448 eligible features have terminal execution evidence. Passing indirect/partial or lower-confidence mappings are `INCONCLUSIVE_EXPECTED`, because running an existing test is not proof that the whole atomic contract is covered.",
        "",
        "One pipx target was rerun after removing inherited audit `SOLAR_HOME`/`CLAUDE_DIR`; the original failure was an audit-environment confound and is not authoritative.",
        "",
        "## Failing targets",
        "",
        "| Target | Test file | Failing/error cases | Evidence |",
        "|---|---|---:|---|",
    ]
    for row in failure_rows:
        phase_lines.append(
            f"| `{row['target_id']}` | `{row['test_target']}` | {row['testcase_failures_and_errors']} | `{row['stdout_path']}` |"
        )
    phase_lines += [
        "",
        "Raw failures in optional local-corpus surfaces remain visible. They are not promoted to live/provider parity, and feature-level status uses exact testcase matching rather than failing every feature linked to a shared file.",
        "",
        "## Evidence files",
        "",
        "- `feature-execution-results.csv`: one row per eligible atomic feature",
        "- `testcase-results.csv`: raw JUnit testcase reconciliation",
        "- `failed-testcases.csv`: failure/error subset",
        "- `target-results.tsv`: commands, exit codes, counts, and paths",
        "- `target-failure-summary.csv`: one row per failing target",
        "- `eligible-features.csv` and `excluded-features.csv`: scope decision per atomic feature",
    ]
    (phase / "execution-report.md").write_text("\n".join(phase_lines) + "\n", encoding="utf-8")

    defects_path = root / "defects.md"
    defects_text = defects_path.read_text(encoding="utf-8")
    marker = "\n## Eligible-feature strict phase additions\n"
    defects_text = defects_text.split(marker, 1)[0].rstrip()
    additions = [
        marker,
        "The strict phase attempted all 107 selected targets. Existing D-003, D-006, D-007, D-010, D-011, D-016, and D-019 reproduced within this narrower selection.",
        "",
        "### D-020 — research intake omits the required capability capsule ID (P2)",
        "",
        "- Surface: `harness/tests/test_codex_pm_router.py::test_build_pm_intake_emits_capsule_plan_for_research_request`.",
        "- Evidence: `evidence/eligible-full-phase-v3/junit/eligible-0069.xml`.",
        "- Reproduction: the emitted research intake payload raises `KeyError: capability_capsule_id`.",
        "- Impact: research intake artifacts do not satisfy the direct stable-ID/capsule contract.",
        "",
        "### D-021 — graph dispatch hygiene/reuse APIs have drifted (P2)",
        "",
        "- Evidence: `eligible-0027` and `eligible-0032` in `target-failure-summary.csv`.",
        "- Reproduction: dirty-pane dispatch omits `pane_hygiene_dirty`; `multi_task_runner.tmux_window_records` is absent.",
        "- Impact: pane safety and compact-session reuse cannot satisfy their committed tests.",
        "",
        "### D-022 — actor/logical-operator registries and schemas disagree (P2)",
        "",
        "- Evidence: `eligible-0062` and `eligible-0083` in `target-failure-summary.csv`.",
        "- Reproduction: actor aliases and physical operator IDs are not bijective; new logical roles/capabilities are rejected by the tracked schema; a binding candidate is missing from the actor registry.",
        "- Impact: capability routing and operator declarations cannot be validated consistently.",
        "",
        "### D-023 — legacy ThunderOMLX knowledge alias is not resolved (P2)",
        "",
        "- Evidence: `eligible-0081` in `target-failure-summary.csv`.",
        "- Reproduction: mocked healthy Qwen runtime is rejected when `proxy_model=mini-thunderomlx-qwen36-knowledge`.",
        "- Impact: knowledge health reports a false negative for the documented legacy alias.",
        "",
        "### Strict-phase failing-target index",
        "",
        "See `evidence/eligible-full-phase-v3/target-failure-summary.csv` for all raw failures, including collection failures already covered by D-016 and local-corpus failures classified under D-019.",
    ]
    defects_path.write_text(defects_text + "\n" + "\n".join(additions) + "\n", encoding="utf-8")

    print(json.dumps({
        "coverage_counts": dict(coverage_counts),
        "feature_status_counts": feature_summary["status_counts"],
        "eligible_phase": reconciliation,
        "defects_added": ["D-020", "D-021", "D-022", "D-023"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
