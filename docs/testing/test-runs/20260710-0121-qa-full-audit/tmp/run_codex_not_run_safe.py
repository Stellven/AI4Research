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
    "target_id", "runner_kind", "test_target", "plan_category", "linked_feature_count",
    "linked_feature_ids", "mapping_classifications", "command", "cwd", "start_time", "end_time",
    "duration_seconds", "exit_code", "execution_status", "testcase_pass", "testcase_fail",
    "testcase_error", "testcase_skip", "stdout_path", "stderr_path", "junit_path",
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
    audit_root = Path(sys.argv[1]).resolve()
    checkout = Path(sys.argv[2]).resolve()
    phase = audit_root / "evidence/codex-not-run-phase"
    manifest = list(csv.DictReader((phase / "safe-target-feature-map.csv").open(encoding="utf-8", newline="")))
    result_path = phase / "safe-target-results.tsv"
    completed = load_completed(result_path)
    rows = list(completed.values())
    completed_ids = set(completed)
    logs = phase / "target-logs"
    junit_dir = phase / "junit"
    temp_root = audit_root / "tmp/codex-not-run-phase"
    logs.mkdir(parents=True, exist_ok=True)
    junit_dir.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)

    base_env = os.environ.copy()
    for key in list(base_env):
        if re.search(r"(API[_-]?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|ACCESS[_-]?KEY|OAUTH)", key, re.I):
            base_env.pop(key, None)
    safe_bin = audit_root / "tmp/safe-bin"
    base_env.update(
        {
            "PATH": os.pathsep.join([str(safe_bin), str(checkout / ".venv/bin"), os.environ.get("PATH", "")]),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "CLAUDE_CODE_OAUTH_TOKEN": "",
            "ZHIPU_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "GEMINI_API_KEY": "",
            "SERPER_API_KEY": "",
            "SEMANTIC_SCHOLAR_API_KEY": "",
            "GITHUB_TOKEN": "",
            "GH_TOKEN": "",
            "AWS_ACCESS_KEY_ID": "",
            "AWS_SECRET_ACCESS_KEY": "",
            "AUTOSCI_LIVE_TESTS": "0",
            "SOLAR_LIVE_TESTS": "0",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "127.0.0.1,localhost",
            "SOLAR_AUTOSCI_PYTHON": str(checkout / ".venv/bin/python"),
            "HARNESS_DIR": str(checkout / "harness"),
        }
    )

    for position, target in enumerate(manifest, start=1):
        target_id = target["target_id"]
        if target_id in completed_ids:
            continue
        relative = target["test_target"]
        kind = target["runner_kind"]
        target_path = checkout / relative
        target_temp = temp_root / target_id
        home = target_temp / "home"
        cache = target_temp / "cache"
        target_temp.mkdir(parents=True, exist_ok=True)
        home.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        stdout_path = logs / f"{target_id}.stdout.txt"
        stderr_path = logs / f"{target_id}.stderr.txt"
        junit_path = junit_dir / f"{target_id}.xml"
        env = base_env.copy()
        env.update(
            {
                "HOME": str(home),
                "SOLAR_HOME": str(home / ".solar"),
                "CLAUDE_DIR": str(home / ".claude"),
                "CODEX_HOME": str(home / ".codex"),
                "TMPDIR": str(target_temp / "tmp"),
                "XDG_CACHE_HOME": str(cache),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "PYTHONPATH": os.pathsep.join([
                    str(checkout), str(checkout / "harness"), str(checkout / "harness/lib"),
                    str(checkout / "harness/tools"), str(checkout / "harness/tools/research"),
                    str(target_path.parent), str(target_path.parent.parent),
                ]),
            }
        )
        Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)
        if kind == "pytest":
            command = [
                str(checkout / ".venv/bin/python"), "-m", "pytest", relative, "-q", "--tb=short",
                "-o", f"cache_dir={cache / 'pytest'}", f"--basetemp={target_temp / 'pytest'}",
                f"--junitxml={junit_path}",
            ]
            timeout = 300 if "autosci_skill_shim" in relative else 180
        elif kind == "shell":
            command = ["/opt/homebrew/bin/bash", str(target_path)]
            timeout = 180
        elif kind == "node":
            command = ["node", str(target_path)]
            timeout = 180
        elif kind == "bun":
            text = target_path.read_text(encoding="utf-8", errors="replace")
            command = ["bun", "test", relative] if "bun:test" in text else ["bun", "run", relative]
            timeout = 180
        else:
            command = ["false"]
            timeout = 30

        started = now()
        start_clock = time.monotonic()
        exit_code = 127
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            try:
                proc = subprocess.run(
                    command, cwd=checkout, env=env, stdout=stdout_handle, stderr=stderr_handle,
                    timeout=timeout, check=False,
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
        elif exit_code == 77:
            status = "BLOCKED_EXPECTED"
        elif exit_code == 0 and kind == "pytest" and counts["pass"] == 0 and counts["skip"]:
            status = "SKIPPED_ENV"
        elif exit_code == 0:
            status = "PASS"
        else:
            status = "FAIL"
        row = {
            "target_id": target_id,
            "runner_kind": kind,
            "test_target": relative,
            "plan_category": target["plan_category"],
            "linked_feature_count": target["linked_feature_count"],
            "linked_feature_ids": target["linked_feature_ids"],
            "mapping_classifications": target["mapping_classifications"],
            "command": shlex.join(command),
            "cwd": str(checkout),
            "start_time": started,
            "end_time": now(),
            "duration_seconds": f"{time.monotonic() - start_clock:.3f}",
            "exit_code": str(exit_code),
            "execution_status": status,
            "testcase_pass": str(counts["pass"]),
            "testcase_fail": str(counts["fail"]),
            "testcase_error": str(counts["error"]),
            "testcase_skip": str(counts["skip"]),
            "stdout_path": str(stdout_path.relative_to(audit_root)),
            "stderr_path": str(stderr_path.relative_to(audit_root)),
            "junit_path": str(junit_path.relative_to(audit_root)) if junit_path.is_file() else "",
        }
        rows.append(row)
        with result_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
        status_counts = Counter(item["execution_status"] for item in rows)
        progress = {
            "schema": "qa.codex_not_run_progress.v1",
            "updated_at": now(),
            "completed_targets": len(rows),
            "total_targets": len(manifest),
            "remaining_targets": len(manifest) - len(rows),
            "status_counts": dict(status_counts),
            "last_target": row,
        }
        (phase / "execution-progress.json").write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "position": position, "total": len(manifest), "target_id": target_id,
            "status": status, "exit_code": exit_code, "duration_seconds": row["duration_seconds"],
        }), flush=True)

    status_counts = Counter(item["execution_status"] for item in rows)
    totals: Counter[str] = Counter()
    for row in rows:
        for key in ("testcase_pass", "testcase_fail", "testcase_error", "testcase_skip"):
            totals[key] += int(row[key])
    summary = {
        "schema": "qa.codex_not_run_execution.v1",
        "target_count": len(manifest),
        "completed_target_count": len(rows),
        "status_counts": dict(status_counts),
        "testcase_counts": dict(totals),
        "all_targets_attempted": len(rows) == len(manifest),
    }
    (phase / "safe-execution-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if len(rows) == len(manifest) else 2


if __name__ == "__main__":
    raise SystemExit(main())
