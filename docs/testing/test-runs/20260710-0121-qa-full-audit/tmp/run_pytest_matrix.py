from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


SUITES = [
    ("graph", ["harness/tests/graph"]),
    ("code_signal", ["harness/tests/code_signal"]),
    ("influence", ["harness/tests/influence"]),
    ("data_plane", ["harness/tests/data_plane"]),
    ("benchmark", ["harness/tests/benchmark"]),
    ("browser", ["harness/tests/browser"]),
    ("experience", ["harness/tests/experience"]),
    ("livework", ["harness/tests/livework"]),
    ("research_unit", ["harness/tests/research_unit"]),
    ("research_integration", ["harness/tests/research_integration"]),
    ("research_survey", ["harness/tests/research_survey"]),
    ("research", ["harness/tests/research"]),
    ("runtime", ["harness/tests/runtime"]),
    ("integration", ["harness/tests/integration"]),
    ("integrations", ["harness/tests/integrations"]),
    ("orchestration", ["harness/tests/orchestration"]),
    ("config", ["harness/tests/config"]),
    ("root_ui_python", ["tests/ui"]),
    ("pipx_distribution", ["distribution/pipx/tests"]),
]


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def main() -> int:
    checkout = Path(sys.argv[1]).resolve()
    run_root = Path(sys.argv[2]).resolve()
    run_name = sys.argv[3] if len(sys.argv) > 3 else "pytest-matrix"
    evidence = run_root / "evidence" / run_name
    cache_root = run_root / "tmp/pytest-cache" / run_name
    evidence.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    suites = list(SUITES)
    top_level = sorted(str(path.relative_to(checkout)) for path in (checkout / "harness/tests").glob("test_*.py"))
    suites.append(("harness_top_level", top_level))
    rows = []
    for name, targets in suites:
        stdout_path = evidence / f"{name}.stdout.txt"
        stderr_path = evidence / f"{name}.stderr.txt"
        junit_path = evidence / f"{name}.xml"
        command = [
            sys.executable, "-m", "pytest", *targets, "-q", "--tb=short",
            "-o", f"cache_dir={cache_root / name}", f"--junitxml={junit_path}",
        ]
        started_at = now()
        started = time.monotonic()
        try:
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                completed = subprocess.run(
                    command, cwd=checkout, stdout=stdout, stderr=stderr, timeout=600, check=False,
                )
            code = completed.returncode
            status = "PASS" if code == 0 else ("SKIPPED_NA" if code == 5 else "FAIL")
        except subprocess.TimeoutExpired:
            code = 124
            status = "FLAKY"
            stderr_path.write_text("COMMAND_TIMEOUT: suite exceeded 600 seconds\n", encoding="utf-8")
        row = {
            "suite": name,
            "targets": " ".join(targets),
            "command": subprocess.list2cmdline(command),
            "start_time": started_at,
            "end_time": now(),
            "duration_seconds": f"{time.monotonic() - started:.3f}",
            "exit_code": code,
            "status": status,
            "stdout_path": str(stdout_path.relative_to(run_root)),
            "stderr_path": str(stderr_path.relative_to(run_root)),
            "junit_path": str(junit_path.relative_to(run_root)),
        }
        rows.append(row)
        print(json.dumps({"suite": name, "status": status, "exit_code": code, "duration_seconds": row["duration_seconds"]}), flush=True)
    with (evidence / "pytest-matrix.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "suite_count": len(rows),
        "passed": sum(row["status"] == "PASS" for row in rows),
        "failed": sum(row["status"] == "FAIL" for row in rows),
        "skipped_na": sum(row["status"] == "SKIPPED_NA" for row in rows),
        "flaky_timeout": sum(row["status"] == "FLAKY" for row in rows),
        "results": rows,
    }
    (evidence / "pytest-matrix-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("suite_count", "passed", "failed", "skipped_na", "flaky_timeout")}), flush=True)
    return 1 if summary["failed"] or summary["flaky_timeout"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
