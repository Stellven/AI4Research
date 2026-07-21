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


EXCLUDED_FOR_ACK_OR_FIXED_PATH = {
    "harness/tests/test-coordinator-pidfile.sh",
    "harness/tests/release/test-s7-release.sh",
}


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists() and not link.is_symlink():
        link.symlink_to(target, target_is_directory=True)


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    checkout = Path(sys.argv[2]).resolve()
    phase = root / "evidence/codex-not-run-phase"
    plan = list(csv.DictReader((phase / "execution-plan.csv").open(encoding="utf-8", newline="")))
    targets = [
        row for row in plan
        if row["plan_category"] == "shell_safety_review"
        and row["test_target"] not in EXCLUDED_FOR_ACK_OR_FIXED_PATH
    ]
    logs = phase / "reviewed-shell-logs"
    temp_root = root / "tmp/codex-not-run-reviewed-shells"
    logs.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    base_env = os.environ.copy()
    for key in list(base_env):
        if re.search(r"(API[_-]?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|ACCESS[_-]?KEY|OAUTH)", key, re.I):
            base_env.pop(key, None)
    base_env.update({
        "PATH": os.pathsep.join([str(root / "tmp/safe-bin"), str(checkout / ".venv/bin"), os.environ.get("PATH", "")]),
        "HARNESS_TEST": "1", "AUTOSCI_LIVE_TESTS": "0", "SOLAR_LIVE_TESTS": "0",
        "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "GEMINI_API_KEY": "",
        "GITHUB_TOKEN": "", "GH_TOKEN": "", "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9", "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "127.0.0.1,localhost", "HARNESS_DIR": str(checkout / "harness"),
        "SOLAR_REPO_ROOT": str(checkout), "SOLAR_SOURCE_ROOT": str(checkout),
    })
    results = []
    for position, row in enumerate(targets, start=1):
        target_id = row["target_id"]
        target = checkout / row["test_target"]
        temp = temp_root / target_id
        home = temp / "home"
        home.mkdir(parents=True, exist_ok=True)
        ensure_link(home / "Solar", checkout)
        ensure_link(home / ".solar/harness", checkout / "harness")
        stdout_path = logs / f"{target_id}.stdout.txt"
        stderr_path = logs / f"{target_id}.stderr.txt"
        env = base_env.copy()
        env.update({
            "HOME": str(home), "SOLAR_HOME": str(home / ".solar"), "CODEX_HOME": str(home / ".codex"),
            "CLAUDE_DIR": str(home / ".claude"), "TMPDIR": str(temp / "tmp"),
            "PYTHONPATH": os.pathsep.join([
                str(root / "tmp"), str(checkout), str(checkout / "harness"), str(checkout / "harness/lib"),
                str(checkout / "harness/tools"), str(checkout / "harness/plugins/autosci"),
            ]),
        })
        Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)
        command = ["/opt/homebrew/bin/bash", str(target)]
        started = now()
        start_clock = time.monotonic()
        with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
            try:
                proc = subprocess.run(command, cwd=checkout / "harness", env=env, stdout=out, stderr=err, timeout=240, check=False)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired as error:
                err.write(f"COMMAND_TIMEOUT: {error}\n".encode())
                exit_code = 124
        status = "PASS" if exit_code == 0 else "BLOCKED_EXPECTED" if exit_code == 77 else "FLAKY" if exit_code == 124 else "FAIL"
        results.append({
            "target_id": target_id, "test_target": row["test_target"], "linked_feature_ids": row["linked_feature_ids"],
            "command": shlex.join(command), "cwd": str(checkout / "harness"), "start_time": started, "end_time": now(),
            "duration_seconds": f"{time.monotonic()-start_clock:.3f}", "exit_code": exit_code,
            "execution_status": status, "stdout_path": str(stdout_path.relative_to(root)),
            "stderr_path": str(stderr_path.relative_to(root)),
        })
        print(json.dumps({"position": position, "total": len(targets), "target_id": target_id, "status": status}), flush=True)
    fields = list(results[0])
    with (phase / "reviewed-shell-results.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(results)
    summary = {"schema": "qa.codex_not_run_reviewed_shells.v1", "target_count": len(results), "status_counts": dict(Counter(r["execution_status"] for r in results))}
    (phase / "reviewed-shell-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
