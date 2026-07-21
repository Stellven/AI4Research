from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


LOCKED_SHA = "fb3f589b08e4167ac3cb0043fb3d59801a0f110b"


def run(command: list[str], cwd: Path) -> dict[str, object]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout.rstrip(),
        "stderr": result.stderr.rstrip(),
    }


def version(command: list[str], cwd: Path) -> dict[str, object]:
    executable = shutil.which(command[0])
    if not executable:
        return {"available": False, "path": None, "version": None, "exit_code": None}
    result = run(command, cwd)
    output = str(result["stdout"] or result["stderr"])
    return {
        "available": result["exit_code"] == 0,
        "path": executable,
        "version": output.splitlines()[0] if output else "",
        "exit_code": result["exit_code"],
    }


def main() -> None:
    repo = Path(sys.argv[1]).resolve()
    run_root = Path(sys.argv[2]).resolve()
    repo_commands = [
        ["git", "rev-parse", "--show-toplevel"],
        ["git", "branch", "--show-current"],
        ["git", "rev-parse", "HEAD"],
        ["git", "remote", "-v"],
        ["git", "status", "--short", "--branch"],
        ["git", "submodule", "status", "--recursive"],
    ]
    repo_results = [run(command, repo) for command in repo_commands]
    current_sha = str(repo_results[2]["stdout"])
    repo_state_lines = [
        f"audit_started_local={datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"locked_test_sha={LOCKED_SHA}",
        f"current_sha_at_capture={current_sha}",
        f"sha_matches_lock={str(current_sha == LOCKED_SHA).lower()}",
        "",
    ]
    for result in repo_results:
        repo_state_lines.append(f"$ {subprocess.list2cmdline(result['command'])}")
        repo_state_lines.append(str(result["stdout"]))
        if result["stderr"]:
            repo_state_lines.append("[stderr]")
            repo_state_lines.append(str(result["stderr"]))
        repo_state_lines.append(f"[exit_code={result['exit_code']}]")
        repo_state_lines.append("")
    (run_root / "repo-state.txt").write_text("\n".join(repo_state_lines), encoding="utf-8")

    environment = {
        "audit_started_local": datetime.now().astimezone().isoformat(timespec="seconds"),
        "timezone": str(datetime.now().astimezone().tzinfo),
        "repo_root": str(repo),
        "locked_test_sha": LOCKED_SHA,
        "current_sha_at_capture": current_sha,
        "sha_matches_lock": current_sha == LOCKED_SHA,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "shell": os.environ.get("SHELL", ""),
        "tools": {
            "python3": version(["python3", "--version"], repo),
            "node": version(["node", "--version"], repo),
            "bun": version(["bun", "--version"], repo),
            "git": version(["git", "--version"], repo),
            "bash": version(["bash", "--version"], repo),
            "tmux": version(["tmux", "-V"], repo),
            "jq": version(["jq", "--version"], repo),
            "rg": version(["rg", "--version"], repo),
        },
        "network_mode": "disabled_by_audit_policy; no live-provider calls authorized",
        "credential_mode": "no real credentials; credential-bearing env vars not used by test commands",
        "gate_mode": "fixture/static/local deterministic; side effects must block or use isolated paths",
        "isolated_paths": {
            "run_root": str(run_root),
            "fixtures": str(run_root / "fixtures"),
            "temp_home": str(run_root / "tmp" / "home"),
            "solar_home": str(run_root / "tmp" / "solar"),
            "claude_dir": str(run_root / "tmp" / "claude"),
            "pytest_cache": str(run_root / "tmp" / "pytest-cache"),
        },
        "qa_package": {
            "source_path": "/Users/jamesyuan/Downloads/ai4research_qa_agent_package.zip",
            "sha256": "8e33ce371e8fd2d5d39b72fcb3bbb976ef5391a83ccf48d8aee1ec95aa435cdd",
        },
    }
    (run_root / "environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
