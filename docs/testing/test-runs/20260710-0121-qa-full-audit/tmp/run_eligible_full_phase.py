from __future__ import annotations

import csv
import json
import os
import re
import shlex
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path


FIELDS = [
    "target_id", "runner_kind", "test_target", "linked_feature_count", "linked_feature_ids",
    "command", "cwd", "start_time", "end_time", "duration_seconds", "exit_code", "execution_status",
    "testcase_pass", "testcase_fail", "testcase_error", "testcase_skip", "stdout_path", "stderr_path", "junit_path",
]


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def junit_counts(path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not path.is_file():
        return counts
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        counts["error"] += 1
        return counts
    for case in root.iter("testcase"):
        if case.find("failure") is not None:
            counts["fail"] += 1
        elif case.find("error") is not None:
            counts["error"] += 1
        elif case.find("skipped") is not None:
            counts["skip"] += 1
        else:
            counts["pass"] += 1
    return counts


def load_completed(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["target_id"]: row for row in csv.DictReader(handle, delimiter="\t")}


def main() -> int:
    run_root = Path(sys.argv[1]).resolve()
    phase_name = sys.argv[2] if len(sys.argv) > 2 else "eligible-full-phase"
    checkout = run_root / "tmp/checkout"
    phase = run_root / "evidence" / phase_name
    logs = phase / "target-logs"
    junit_dir = phase / "junit"
    cache_dir = run_root / "tmp" / phase_name / "cache"
    temp_dir = run_root / "tmp" / phase_name / "temp"
    logs.mkdir(parents=True, exist_ok=True)
    junit_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = phase / "target-feature-map.csv"
    targets = list(csv.DictReader(manifest_path.open()))
    result_path = phase / "target-results.tsv"
    completed = load_completed(result_path)
    rows = list(completed.values())
    completed_ids = set(completed)
    base_env = os.environ.copy()
    for key in list(base_env):
        if re.search(r"(API[_-]?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|ACCESS[_-]?KEY)", key, re.I):
            base_env.pop(key, None)
    isolated_home = run_root / "tmp/final-home"
    safe_bin = run_root / "tmp/safe-bin"
    base_env.update(
        {
            "HOME": str(isolated_home),
            "SOLAR_HOME": str(isolated_home / ".solar"),
            "CLAUDE_DIR": str(isolated_home / ".claude"),
            "PATH": os.pathsep.join([str(safe_bin), str(checkout / ".venv/bin"), os.environ.get("PATH", "")]),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "ZHIPU_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "GEMINI_API_KEY": "",
            "AWS_ACCESS_KEY_ID": "",
            "AWS_SECRET_ACCESS_KEY": "",
            "SOLAR_AUTOSCI_PYTHON": str(checkout / ".venv/bin/python"),
            "HARNESS_DIR": str(checkout / "harness"),
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "127.0.0.1,localhost",
        }
    )

    for position, target in enumerate(targets, start=1):
        target_id = target["target_id"]
        if target_id in completed_ids:
            continue
        relative = target["test_target"]
        kind = target["runner_kind"]
        target_path = checkout / relative
        stdout_path = logs / f"{target_id}.stdout.txt"
        stderr_path = logs / f"{target_id}.stderr.txt"
        junit_path = junit_dir / f"{target_id}.xml"
        target_temp = temp_dir / target_id
        target_cache = cache_dir / target_id
        target_temp.mkdir(parents=True, exist_ok=True)
        target_cache.mkdir(parents=True, exist_ok=True)
        env = base_env.copy()
        env["TMPDIR"] = str(target_temp)
        env["XDG_CACHE_HOME"] = str(target_cache)
        python_roots = [
            run_root / "tmp",
            target_path.parent,
            target_path.parent.parent,
            checkout,
            checkout / "harness",
            checkout / "harness/lib",
            checkout / "harness/tools",
            checkout / "harness/tools/youtube",
            checkout / "harness/tools/research",
            checkout / "harness/tools/research/migrations",
            checkout / "harness/lib/research",
            checkout / "harness/lib/research/migrations",
        ]
        env["PYTHONPATH"] = os.pathsep.join(str(path) for path in python_roots)
        if kind == "pytest":
            relevant_names = sorted(
                {name.strip() for name in target.get("relevant_testcases", "").split(";") if name.strip()}
            )
            command = [
                str(checkout / ".venv/bin/python"), "-m", "pytest", relative, "-q", "--tb=short",
                "-o", f"cache_dir={target_cache / 'pytest'}",
                f"--basetemp={target_temp / 'pytest'}",
                f"--junitxml={junit_path}",
            ]
            if relevant_names:
                command.extend(["-k", " or ".join(relevant_names)])
            cwd = checkout
            timeout = 600 if "autosci/tests/test_autosci_skill_shim.py" in relative else 300
        elif kind == "shell":
            command = ["/opt/homebrew/bin/bash", str(target_path)]
            cwd = checkout / "harness"
            timeout = 300
        else:
            command = ["false"]
            cwd = checkout
            timeout = 30
        started = now()
        start_clock = time.monotonic()
        exit_code = 127
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            try:
                proc = subprocess.run(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    timeout=timeout,
                    check=False,
                )
                exit_code = proc.returncode
            except subprocess.TimeoutExpired as error:
                stderr_handle.write(f"COMMAND_TIMEOUT: {error}\n".encode())
                exit_code = 124
            except OSError as error:
                stderr_handle.write(f"COMMAND_ERROR: {error}\n".encode())
                exit_code = 127
        counts = junit_counts(junit_path)
        if exit_code == 124:
            status = "FLAKY"
        elif exit_code == 5:
            status = "NOT_COLLECTED"
        elif exit_code == 0 and kind == "pytest" and counts["pass"] == 0 and counts["skip"] > 0:
            status = "SKIPPED_ENV"
        elif exit_code == 0:
            status = "PASS"
        else:
            status = "FAIL"
        row = {
            "target_id": target_id,
            "runner_kind": kind,
            "test_target": relative,
            "linked_feature_count": target["linked_feature_count"],
            "linked_feature_ids": target["linked_feature_ids"],
            "command": shlex.join(command),
            "cwd": str(cwd),
            "start_time": started,
            "end_time": now(),
            "duration_seconds": f"{time.monotonic() - start_clock:.3f}",
            "exit_code": str(exit_code),
            "execution_status": status,
            "testcase_pass": str(counts["pass"]),
            "testcase_fail": str(counts["fail"]),
            "testcase_error": str(counts["error"]),
            "testcase_skip": str(counts["skip"]),
            "stdout_path": str(stdout_path.relative_to(run_root)),
            "stderr_path": str(stderr_path.relative_to(run_root)),
            "junit_path": str(junit_path.relative_to(run_root)) if junit_path.exists() else "",
        }
        rows.append(row)
        with result_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
        status_counts = Counter(item["execution_status"] for item in rows)
        progress = {
            "schema": "qa.eligible_full_phase_progress.v1",
            "updated_at": now(),
            "completed_targets": len(rows),
            "total_targets": len(targets),
            "remaining_targets": len(targets) - len(rows),
            "status_counts": dict(status_counts),
            "last_target": row,
        }
        (phase / "progress.json").write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "position": position,
                    "total": len(targets),
                    "target_id": target_id,
                    "status": status,
                    "exit_code": exit_code,
                    "duration_seconds": row["duration_seconds"],
                }
            ),
            flush=True,
        )

    status_counts = Counter(item["execution_status"] for item in rows)
    totals = Counter()
    for row in rows:
        for key in ("testcase_pass", "testcase_fail", "testcase_error", "testcase_skip"):
            totals[key] += int(row[key])
    summary = {
        "schema": "qa.eligible_full_phase_execution.v1",
        "phase_name": phase_name,
        "target_count": len(targets),
        "completed_target_count": len(rows),
        "status_counts": dict(status_counts),
        "testcase_counts": dict(totals),
        "all_targets_attempted": len(rows) == len(targets),
    }
    (phase / "execution-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if len(rows) == len(targets) else 2


if __name__ == "__main__":
    raise SystemExit(main())
