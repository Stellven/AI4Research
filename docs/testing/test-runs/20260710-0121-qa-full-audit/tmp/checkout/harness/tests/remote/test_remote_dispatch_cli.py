#!/usr/bin/env python3
"""Subprocess tests for the solar-remote-dispatch bash CLI.

These tests cover the production surface used by the contract. They use fake
ssh/rsync binaries so they do not require a real Mac mini.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLI = Path.home() / ".solar" / "bin" / "solar-remote-dispatch"


def _fake_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ssh").write_text(
        """#!/usr/bin/env bash
cmd="${*: -1}"
case "$cmd" in
  "echo ok") echo ok ;;
  "which rsync"*) echo /usr/bin/rsync ;;
  *"test -d ~/.solar/harness"*) echo yes ;;
  *"VERSION"*) echo "version: with colon" ;;
  *"tmux has-session"*) echo yes ;;
  *"tmux list-panes"*) printf 'solar-harness:0.0\\nsolar-harness:0.1\\n' ;;
  *"last-remote-sync"*) echo 2026-05-10T12:00:00Z ;;
  *) echo ok ;;
esac
""",
        encoding="utf-8",
    )
    (bin_dir / "rsync").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    for p in bin_dir.iterdir():
        p.chmod(0o755)
    return bin_dir


def test_doctor_json_cli_is_valid_json_and_honors_host_override(tmp_path: Path) -> None:
    fake_bin = _fake_bin(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["HOME"] = str(tmp_path)
    env["HARNESS_DIR"] = str(ROOT)
    result = subprocess.run(
        [str(CLI), "doctor", "--json", "--host", "cliuser@example.local"],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["target"] == "cliuser@example.local"
    assert payload["checks"]["remote_version"]["version"] == "version: with colon"
    assert payload["checks"]["remote_panes"]["count"] == 2


def test_doctor_json_cli_missing_config_is_actionable(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["HARNESS_DIR"] = str(ROOT)
    result = subprocess.run(
        [str(CLI), "doctor", "--json"],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "remote_user and remote_host not configured" in payload["errors"][0]


def test_dispatch_cli_invokes_verify_subcommand_before_wake(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    lib = harness / "lib"
    sprints.mkdir(parents=True)
    lib.mkdir(parents=True)
    shutil.copy2(ROOT / "lib" / "remote_dispatch.py", lib / "remote_dispatch.py")

    sid = "sprint-cli-dispatch-smoke"
    (sprints / f"{sid}.contract.md").write_text("# Contract\n", encoding="utf-8")
    (sprints / f"{sid}.status.json").write_text('{"id":"sprint-cli-dispatch-smoke"}\n', encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "calls.log"
    (fake_bin / "ssh").write_text(
        """#!/usr/bin/env bash
echo "ssh $*" >> "$CALLS_LOG"
cmd="$*"
if [[ "$cmd" == *" echo ok" ]]; then
  echo ok
  exit 0
fi
if [[ "$cmd" == *"shasum -a 256"* ]]; then
  remote="$(printf '%s\n' "$cmd" | sed -n "s/.*shasum -a 256 '\\([^']*\\)'.*/\\1/p")"
  base="$(basename "$remote")"
  cat "$SHA_DIR/$base.sha"
  echo "  $remote"
  exit 0
fi
echo ok
""",
        encoding="utf-8",
    )
    (fake_bin / "rsync").write_text(
        """#!/usr/bin/env bash
echo "rsync $*" >> "$CALLS_LOG"
exit 0
""",
        encoding="utf-8",
    )
    for p in fake_bin.iterdir():
        p.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["HOME"] = str(tmp_path)
    env["HARNESS_DIR"] = str(harness)
    env["CALLS_LOG"] = str(calls)
    env["SHA_DIR"] = str(sprints)
    env["SOLAR_REMOTE_USER"] = "cliuser"
    env["SOLAR_REMOTE_HOST"] = "example.local"
    env["SOLAR_REMOTE_PATH"] = "/tmp/remote-home"

    # Prime manifest and expected remote checksum responses.
    manifest = subprocess.run(
        ["python3", str(lib / "remote_dispatch.py"), "manifest", "--sprint", sid],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=True,
    )
    manifest_payload = json.loads(manifest.stdout)
    for fname, finfo in manifest_payload["files"].items():
        (sprints / f"{fname}.sha").write_text(finfo["sha256"], encoding="utf-8")

    result = subprocess.run(
        [str(CLI), "dispatch", "--force", sid],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Verifying remote checksums" in result.stdout
    assert "Waking sprint on remote" in result.stdout
    assert "solar-harness wake sprint-cli-dispatch-smoke" in calls.read_text(encoding="utf-8")
