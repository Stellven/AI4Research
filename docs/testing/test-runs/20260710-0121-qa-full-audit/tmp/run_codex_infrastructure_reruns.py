from __future__ import annotations

import csv
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from run_codex_not_run_safe import junit_counts


SELECTED_CATEGORIES = {
    "runner_cwd_or_path",
    "shell_fast_failure",
    "not_a_pytest_test",
    "missing_command",
    "missing_runtime_dependency",
    "collection_or_fixture_error",
}

FIELDS = [
    "target_id", "test_target", "runner_kind", "original_failure_category", "command", "cwd",
    "start_time", "end_time", "duration_seconds", "exit_code", "execution_status", "testcase_pass",
    "testcase_fail", "testcase_error", "testcase_skip", "stdout_path", "stderr_path", "junit_path",
    "linked_feature_ids",
]


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        return
    link.symlink_to(target, target_is_directory=target.is_dir())


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    checkout = Path(sys.argv[2]).resolve()
    only_ids = set(sys.argv[3].split(",")) if len(sys.argv) > 3 and sys.argv[3] else set()
    output_stem = sys.argv[4] if len(sys.argv) > 4 else "infrastructure-rerun"
    phase = root / "evidence/codex-not-run-phase"
    failure_rows = list(csv.DictReader((phase / "target-failure-analysis.csv").open(encoding="utf-8", newline="")))
    selected = [
        row for row in failure_rows
        if row["target_id"] in only_ids or (not only_ids and row["failure_category"] in SELECTED_CATEGORIES)
    ]
    logs = phase / f"{output_stem}-logs"
    junit_dir = phase / f"{output_stem}-junit"
    temp_root = root / "tmp" / f"codex-not-run-{output_stem}"
    logs.mkdir(parents=True, exist_ok=True)
    junit_dir.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)

    base_env = os.environ.copy()
    for key in list(base_env):
        if re.search(r"(API[_-]?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|ACCESS[_-]?KEY|OAUTH)", key, re.I):
            base_env.pop(key, None)
    safe_bin = root / "tmp/safe-bin"
    base_env.update({
        "PATH": os.pathsep.join([str(safe_bin), str(checkout / ".venv/bin"), os.environ.get("PATH", "")]),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HARNESS_TEST": "1",
        "AUTOSCI_LIVE_TESTS": "0",
        "SOLAR_LIVE_TESTS": "0",
        "OPENAI_API_KEY": "", "OPENROUTER_API_KEY": "", "ANTHROPIC_API_KEY": "",
        "CLAUDE_CODE_OAUTH_TOKEN": "", "GOOGLE_API_KEY": "", "GEMINI_API_KEY": "",
        "SERPER_API_KEY": "", "SEMANTIC_SCHOLAR_API_KEY": "", "GITHUB_TOKEN": "", "GH_TOKEN": "",
        "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9", "NO_PROXY": "127.0.0.1,localhost",
        "HARNESS_DIR": str(checkout / "harness"),
        "SOLAR_REPO_ROOT": str(checkout),
        "SOLAR_SOURCE_ROOT": str(checkout),
        "SOLAR_HARNESS_ROOT": str(checkout / "harness"),
        "SOLAR_AUTOSCI_PYTHON": str(checkout / ".venv/bin/python"),
    })
    results = []
    for position, row in enumerate(selected, start=1):
        target_id = row["target_id"]
        relative = row["test_target"]
        target = checkout / relative
        temp = temp_root / target_id
        home = temp / "home"
        cache = temp / "cache"
        home.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        ensure_link(home / "Solar", checkout)
        ensure_link(home / ".solar/harness", checkout / "harness")
        ensure_link(home / ".solar/source", checkout)
        stdout_path = logs / f"{target_id}.stdout.txt"
        stderr_path = logs / f"{target_id}.stderr.txt"
        junit_path = junit_dir / f"{target_id}.xml"
        env = base_env.copy()
        python_roots = [
            root / "tmp", checkout, checkout / "harness", checkout / "harness/lib",
            checkout / "harness/tools", checkout / "harness/tools/youtube", checkout / "harness/tools/research",
            target.parent,
        ]
        if target.parent.parent != checkout / "harness/plugins/autosci":
            python_roots.append(target.parent.parent)
        env.update({
            "HOME": str(home), "SOLAR_HOME": str(home / ".solar"),
            "CLAUDE_DIR": str(home / ".claude"), "CODEX_HOME": str(home / ".codex"),
            "TMPDIR": str(temp / "tmp"), "XDG_CACHE_HOME": str(cache),
            "PYTHONPATH": os.pathsep.join(str(path) for path in python_roots),
        })
        Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)
        category = row["failure_category"]
        kind = row["runner_kind"]
        if category == "not_a_pytest_test":
            command = [str(checkout / ".venv/bin/python"), str(target)]
            cwd = checkout
        elif kind == "pytest":
            command = [
                str(checkout / ".venv/bin/python"), "-m", "pytest", relative, "-q", "--tb=short",
                "-o", f"cache_dir={cache / 'pytest'}", f"--basetemp={temp / 'pytest'}",
                f"--junitxml={junit_path}",
            ]
            cwd = checkout
        elif kind == "shell":
            command = ["/opt/homebrew/bin/bash", str(target)]
            cwd = checkout / "harness"
        else:
            command = ["false"]
            cwd = checkout
        started = now()
        start_clock = time.monotonic()
        exit_code = 127
        with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
            try:
                timeout = 600 if "test_autosci_skill_shim.py" in relative else 180
                proc = subprocess.run(command, cwd=cwd, env=env, stdout=out, stderr=err, timeout=timeout, check=False)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired as error:
                err.write(f"COMMAND_TIMEOUT: {error}\n".encode())
                exit_code = 124
            except OSError as error:
                err.write(f"COMMAND_ERROR: {error}\n".encode())
                exit_code = 127
        counts = junit_counts(junit_path)
        if exit_code == 124:
            status = "FLAKY"
        elif exit_code == 77:
            status = "BLOCKED_EXPECTED"
        elif exit_code == 5:
            status = "NOT_COLLECTED"
        elif exit_code == 0 and kind == "pytest" and counts["pass"] == 0 and counts["skip"]:
            status = "SKIPPED_ENV"
        elif exit_code == 0:
            status = "PASS"
        else:
            status = "FAIL"
        result = {
            "target_id": target_id, "test_target": relative, "runner_kind": kind,
            "original_failure_category": category, "command": shlex.join(command), "cwd": str(cwd),
            "start_time": started, "end_time": now(), "duration_seconds": f"{time.monotonic()-start_clock:.3f}",
            "exit_code": str(exit_code), "execution_status": status,
            "testcase_pass": str(counts["pass"]), "testcase_fail": str(counts["fail"]),
            "testcase_error": str(counts["error"]), "testcase_skip": str(counts["skip"]),
            "stdout_path": str(stdout_path.relative_to(root)), "stderr_path": str(stderr_path.relative_to(root)),
            "junit_path": str(junit_path.relative_to(root)) if junit_path.is_file() else "",
            "linked_feature_ids": row["linked_feature_ids"],
        }
        results.append(result)
        print(json.dumps({"position": position, "total": len(selected), "target_id": target_id, "status": status}), flush=True)

    with (phase / f"{output_stem}-results.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(results)
    counts = Counter(row["execution_status"] for row in results)
    summary = {"schema": "qa.codex_not_run_infra_rerun.v1", "target_count": len(results), "status_counts": dict(counts)}
    (phase / f"{output_stem}-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
