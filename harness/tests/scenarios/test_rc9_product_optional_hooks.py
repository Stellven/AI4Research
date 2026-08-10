from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path


HARNESS = Path(__file__).resolve().parents[2]
OPTIONAL_HOOKS = HARNESS / "lib" / "optional-hooks.sh"
COORDINATOR = HARNESS / "coordinator.sh"


def _run_hook(home: Path, name: str, *args: str) -> subprocess.CompletedProcess[str]:
    command = " ".join(
        [
            f"source {shlex.quote(str(OPTIONAL_HOOKS))}",
            "&&",
            "solar_run_optional_claude_hook",
            shlex.quote(name),
            *(shlex.quote(arg) for arg in args),
        ]
    )
    env = dict(os.environ)
    env["HOME"] = str(home)
    env.pop("CLAUDE_DIR", None)
    return subprocess.run(
        ["bash", "-c", command],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_missing_optional_hook_is_a_silent_success(tmp_path: Path) -> None:
    result = _run_hook(tmp_path, "not-installed.sh", "sprint-1")

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_namespaced_hook_runs_when_installed(tmp_path: Path) -> None:
    hook = tmp_path / ".claude" / "solar" / "hooks" / "present.sh"
    hook.parent.mkdir(parents=True)
    hook.write_text("#!/usr/bin/env bash\nprintf 'hook:%s\\n' \"$1\"\n", encoding="utf-8")
    hook.chmod(0o755)

    result = _run_hook(tmp_path, "present.sh", "sprint-2")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "hook:sprint-2\n"


def test_coordinator_has_no_unguarded_home_hook_invocations() -> None:
    source = COORDINATOR.read_text(encoding="utf-8")

    assert not re.search(r"bash\s+~/\.claude/hooks/", source)
    for name in (
        "subconscious-learn.sh",
        "self-evolve-postmortem.sh",
        "planner-review-drafting.sh",
        "scan-low-quality-capabilities.sh",
        "auto-boost-capability.sh",
    ):
        assert f'solar_run_optional_claude_hook "{name}"' in source
