from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def main() -> int:
    checkout = Path(sys.argv[1]).resolve()
    evidence = Path(sys.argv[2]).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "ls-files", "harness/tests/test-*.sh", "harness/tests/**/test-*.sh"],
        cwd=checkout, text=True, capture_output=True, check=True,
    )
    tests = sorted(set(line for line in result.stdout.splitlines() if line))
    rows = []
    harness_dir = checkout / "harness"
    child_env = os.environ.copy()
    child_env["HARNESS_DIR"] = str(harness_dir)
    child_env["PYTHONPATH"] = os.pathsep.join(
        [str(checkout), str(harness_dir), str(harness_dir / "lib"), child_env.get("PYTHONPATH", "")]
    )
    for index, relative in enumerate(tests, start=1):
        test_path = checkout / relative
        safe = relative.replace("/", "_").replace(".sh", "")
        stdout_path = evidence / f"{index:03d}-{safe}.stdout.txt"
        stderr_path = evidence / f"{index:03d}-{safe}.stderr.txt"
        start = now()
        started = time.monotonic()
        try:
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                completed = subprocess.run(
                    ["/opt/homebrew/bin/bash", str(test_path)], cwd=harness_dir, env=child_env,
                    stdout=stdout, stderr=stderr, timeout=90, check=False,
                )
            code = completed.returncode
            status = "PASS" if code == 0 else "FAIL"
        except subprocess.TimeoutExpired:
            code = 124
            status = "FLAKY"
            stderr_path.write_text("COMMAND_TIMEOUT: exceeded 90 seconds\n", encoding="utf-8")
        rows.append({
            "test": relative,
            "start_time": start,
            "end_time": now(),
            "duration_seconds": f"{time.monotonic() - started:.3f}",
            "exit_code": code,
            "status": status,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        })
    with (evidence / "shell-sweep.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=list(rows[0]) if rows else ["test"])
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "test_count": len(rows),
        "passed": sum(row["status"] == "PASS" for row in rows),
        "failed": sum(row["status"] == "FAIL" for row in rows),
        "flaky_timeout": sum(row["status"] == "FLAKY" for row in rows),
        "results": rows,
    }
    (evidence / "shell-sweep-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("test_count", "passed", "failed", "flaky_timeout")}))
    return 1 if summary["failed"] or summary["flaky_timeout"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
