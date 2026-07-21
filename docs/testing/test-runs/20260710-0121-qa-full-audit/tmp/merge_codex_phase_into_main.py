from __future__ import annotations

import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write(path: Path, rows: list[dict[str, str]], fields: list[str] | None = None) -> None:
    columns = fields or list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def backup(path: Path) -> None:
    target = path.with_name(path.stem + ".pre-codex-remediation" + path.suffix)
    if not target.exists():
        shutil.copy2(path, target)


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    phase = root / "evidence/codex-not-run-phase"
    classification = {r["feature_id"]: r for r in read(phase / "not-run-scope-classification.csv")}
    phase_results = {r["feature_id"]: r for r in read(phase / "codex-not-run-feature-results.csv")}
    corrected_map = {r["feature_id"]: r for r in read(phase / "corrected-feature-entrypoint-map.csv")}

    result_path = root / "feature-results.csv"
    result_rows = read(result_path)
    backup(result_path)
    for row in result_rows:
        fid = row["feature_id"]
        scoped = classification.get(fid)
        if not scoped:
            continue
        if scoped["scope_classification"] != "INCLUDED_CODEX_RELEVANT":
            row["final_result_status"] = "SKIPPED_NA"
            row["result_rationale"] = (
                "Outside the user-approved Codex-focused phase: "
                + scoped["scope_classification"].removeprefix("EXCLUDED_").replace("+", "/")
                + ". The feature remains archived in the scope classification evidence."
            )
            row["execution_evidence"] = "evidence/codex-not-run-phase/not-run-scope-classification.csv"
            row["eligible_phase_scope"] = "excluded:user-approved-codex-focus"
            row["eligible_phase_execution_result"] = "SKIPPED_NA"
            continue
        result = phase_results[fid]
        row["final_result_status"] = result["test_result_status"]
        row["result_rationale"] = result["result_rationale"]
        row["execution_evidence"] = result["execution_evidence"]
        row["eligible_phase_scope"] = "included:codex-relevant-not-run-remediation"
        row["eligible_phase_execution_result"] = result["test_result_status"]
        row["eligible_phase_selected_targets"] = result["selected_test_targets"]
        row["eligible_phase_selected_testcases"] = result["selected_testcases"]
        row["eligible_phase_evidence"] = result["execution_evidence"]
        correction = corrected_map[fid]
        row["mapping_confidence"] = correction["mapping_confidence"]
        if correction["mapping_confidence"] == "high":
            row["entrypoints"] = correction["discovered_entrypoints"]
            row["implementation_files_functions"] = correction["implementation_files_functions"]
    write(result_path, result_rows)

    map_path = root / "feature-entrypoint-map.csv"
    map_rows = read(map_path)
    backup(map_path)
    for index, row in enumerate(map_rows):
        correction = corrected_map.get(row["feature_id"])
        if correction:
            map_rows[index] = correction
    write(map_path, map_rows)

    counts = Counter(r["final_result_status"] for r in result_rows)
    summary = {
        "schema": "qa.codex_phase_main_merge.v1",
        "row_count": len(result_rows),
        "status_counts": dict(sorted(counts.items())),
        "scope_rows_merged": len(classification),
        "phase_rows_merged": len(phase_results),
        "excluded_rows_archived_as_skipped_na": sum(
            r["scope_classification"] != "INCLUDED_CODEX_RELEVANT" for r in classification.values()
        ),
    }
    (phase / "main-merge-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
