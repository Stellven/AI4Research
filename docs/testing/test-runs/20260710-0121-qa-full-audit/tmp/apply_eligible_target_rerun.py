from __future__ import annotations

import csv
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def junit_counts(path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    for case in ET.parse(path).getroot().iter("testcase"):
        if case.find("failure") is not None:
            counts["fail"] += 1
        elif case.find("error") is not None:
            counts["error"] += 1
        elif case.find("skipped") is not None:
            counts["skip"] += 1
        else:
            counts["pass"] += 1
    return counts


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    phase_name, target_id, command_id, junit_rel = sys.argv[2:6]
    phase = root / "evidence" / phase_name
    result_path = phase / "target-results.tsv"
    with result_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    with (root / "command-log.tsv").open(encoding="utf-8", newline="") as handle:
        command_rows = list(csv.DictReader(handle, delimiter="\t"))
    command_row = next(row for row in command_rows if row["command_id"] == command_id)
    junit_path = root / junit_rel
    counts = junit_counts(junit_path)
    target = next(row for row in rows if row["target_id"] == target_id)
    target.update({
        "command": command_row["command"],
        "cwd": command_row["cwd"],
        "start_time": command_row["start_time"],
        "end_time": command_row["end_time"],
        "duration_seconds": command_row["duration_seconds"],
        "exit_code": command_row["exit_code"],
        "execution_status": "PASS" if command_row["exit_code"] == "0" else "FAIL",
        "testcase_pass": str(counts["pass"]),
        "testcase_fail": str(counts["fail"]),
        "testcase_error": str(counts["error"]),
        "testcase_skip": str(counts["skip"]),
        "stdout_path": command_row["stdout_path"],
        "stderr_path": command_row["stderr_path"],
        "junit_path": junit_rel,
    })
    fields = list(rows[0])
    with result_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    status_counts = Counter(row["execution_status"] for row in rows)
    testcase_totals: Counter[str] = Counter()
    for row in rows:
        for field in ("testcase_pass", "testcase_fail", "testcase_error", "testcase_skip"):
            testcase_totals[field] += int(row[field])
    summary = {
        "schema": "qa.eligible_full_phase_execution.v1",
        "phase_name": phase_name,
        "target_count": len(rows),
        "completed_target_count": len(rows),
        "status_counts": dict(status_counts),
        "testcase_counts": dict(testcase_totals),
        "all_targets_attempted": True,
        "corrected_target_reruns": [
            {
                "target_id": target_id,
                "command_id": command_id,
                "reason": "Removed inherited audit SOLAR_HOME/CLAUDE_DIR that confounded the missing-install test.",
            }
        ],
    }
    (phase / "execution-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
