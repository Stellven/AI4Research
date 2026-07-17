from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


HARNESS_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = HARNESS_ROOT / "pane-launcher.sh"
HARNESS_ENTRY = HARNESS_ROOT / "solar-harness.sh"
PROFILE_HELPER = HARNESS_ROOT / "lib" / "codex_trust_profiles.py"


def _owner_id(session: str) -> str:
    return f"/tmp/test-tmux|session-1|{session}"


def _profile_command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROFILE_HELPER), *args],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _create_profile(
    tmp_path: Path,
    *,
    session: str,
    pane: str = "%1",
    persona: str = "pm",
    owner_id: str | None = None,
) -> tuple[Path, Path, Path]:
    harness = tmp_path / "harness"
    codex_home = tmp_path / "codex-home"
    workspace = tmp_path / "workspace"
    harness.mkdir(parents=True)
    codex_home.mkdir(mode=0o700)
    workspace.mkdir()

    completed = _profile_command(
        "create",
        "--harness-dir",
        str(harness),
        "--codex-home",
        str(codex_home),
        "--work-dir",
        str(workspace),
        "--session",
        session,
        "--owner-id",
        owner_id or _owner_id(session),
        "--pane",
        pane,
        "--persona",
        persona,
        "--launcher-pid",
        "4242",
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    lines = completed.stdout.splitlines()
    assert len(lines) == 2
    profile = Path(lines[1])
    assert profile.is_file()
    assert stat.S_IMODE(profile.stat().st_mode) == 0o600
    return harness, codex_home, profile


def _reap(
    harness: Path,
    session: str,
    *,
    owner_id: str | None = None,
) -> subprocess.CompletedProcess[str]:
    args = [
        "reap",
        "--harness-dir",
        str(harness),
        "--session",
        session,
    ]
    args.extend(("--owner-id", owner_id or _owner_id(session)))
    return _profile_command(*args)


def _run_product_stop(
    tmp_path: Path,
    *,
    harness: Path,
    session: str,
) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "product-home"
    fake_bin = tmp_path / "fake-bin"
    (harness / "lib").mkdir(parents=True, exist_ok=True)
    home.mkdir(exist_ok=True)
    fake_bin.mkdir()
    shutil.copy2(PROFILE_HELPER, harness / "lib" / PROFILE_HELPER.name)
    (harness / "lib" / "run-state.sh").write_text("# test fixture\n", encoding="utf-8")
    fake_tmux = fake_bin / "tmux"
    fake_tmux.write_text(
        "#!/bin/sh\n"
        "case \"${1:-}\" in\n"
        "  list-sessions) exit 0 ;;\n"
        "  display-message)\n"
        "    target=''\n"
        "    previous=''\n"
        "    for argument in \"$@\"; do\n"
        "      if [ \"$previous\" = '-t' ]; then target=\"$argument\"; fi\n"
        "      previous=\"$argument\"\n"
        "    done\n"
        "    printf '/tmp/test-tmux|session-1|%s\\n' \"$target\"\n"
        "    exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_tmux.chmod(fake_tmux.stat().st_mode | stat.S_IXUSR)
    env = os.environ.copy()
    env.update(
        {
            "HARNESS_DIR": str(harness),
            "HOME": str(home),
            "PATH": str(fake_bin) + os.pathsep + env.get("PATH", ""),
            "SOLAR_HARNESS_DIR": str(harness),
            "SOLAR_HARNESS_LAB_SESSION": session + "-lab",
            "SOLAR_HARNESS_SESSION": session,
            "SOLAR_PANE_RUNTIME": "codex",
        }
    )
    return subprocess.run(
        ["bash", str(HARNESS_ENTRY), "stop"],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _run_launcher_with_hard_parent_exit(tmp_path: Path) -> tuple[Path, Path, dict]:
    harness = tmp_path / "installed-harness"
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    capture = tmp_path / "codex-argv.json"
    fake_codex = tmp_path / "codex"

    (harness / "lib").mkdir(parents=True)
    (harness / "personas").mkdir()
    (home / ".codex").mkdir(parents=True)
    workspace.mkdir()

    for relative in (
        "lib/persona-config.sh",
        "lib/capability-prefix.sh",
        "personas/pm.md",
    ):
        source = HARNESS_ROOT / relative
        destination = harness / relative
        shutil.copy2(source, destination)
    if PROFILE_HELPER.exists():
        shutil.copy2(PROFILE_HELPER, harness / "lib" / PROFILE_HELPER.name)

    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, signal, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "name = args[args.index('--profile') + 1]\n"
        "profile = Path(os.environ['CODEX_HOME']) / f'{name}.config.toml'\n"
        "Path(os.environ['CODEX_ARGV_CAPTURE']).write_text(\n"
        "    json.dumps({'profile': str(profile), 'contents': profile.read_text()}),\n"
        "    encoding='utf-8',\n"
        ")\n"
        "os.kill(os.getppid(), signal.SIGKILL)\n",
        encoding="utf-8",
    )
    fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env.update(
        {
            "CODEX_ARGV_CAPTURE": str(capture),
            "CODEX_HOME": str(home / ".codex"),
            "HARNESS_DIR": str(harness),
            "HOME": str(home),
            "SHELL": "/bin/true",
            "SOLAR_CODEX_BIN": str(fake_codex),
            "SOLAR_CODEX_BYPASS": "1",
            "SOLAR_CODEX_TRUST_WORKSPACE": "1",
            "SOLAR_HARNESS_DIR": str(harness),
            "SOLAR_HARNESS_SESSION": "solar-lifecycle-test",
            "SOLAR_PANE_RUNTIME": "codex",
            "TERM": "xterm",
            "TMUX_PANE": "%9",
        }
    )
    completed = subprocess.run(
        ["bash", str(LAUNCHER), "pm", str(workspace)],
        cwd=workspace,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode != 0
    payload = json.loads(capture.read_text(encoding="utf-8"))
    records = list((harness / "run" / "codex-trust-profiles").glob("*.json"))
    assert len(records) == 1
    payload["owner_id"] = json.loads(records[0].read_text(encoding="utf-8"))[
        "owner_id"
    ]
    return harness, home / ".codex", payload


def test_product_reaper_removes_profile_after_launcher_sigkill(tmp_path: Path) -> None:
    harness, _codex_home, payload = _run_launcher_with_hard_parent_exit(tmp_path)
    profile = Path(payload["profile"])

    assert profile.is_file(), "SIGKILL must reproduce the missed EXIT trap"
    assert "OpenSolar managed Codex trust profile" in payload["contents"]

    completed = _reap(
        harness,
        "solar-lifecycle-test",
        owner_id=payload["owner_id"],
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert not profile.exists()


def test_reaper_handles_codex_appended_profile_content(tmp_path: Path) -> None:
    harness, _codex_home, profile = _create_profile(
        tmp_path, session="solar-owned"
    )
    with profile.open("a", encoding="utf-8") as handle:
        handle.write('\n[tui.model_availability_nux]\n"gpt-test" = 1\n')

    completed = _reap(harness, "solar-owned")

    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert not profile.exists()


def test_reaper_preserves_profile_owned_by_another_session(tmp_path: Path) -> None:
    harness, _codex_home, profile = _create_profile(
        tmp_path, session="solar-foreign"
    )

    completed = _reap(harness, "solar-owned")

    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert profile.is_file()


def test_reaper_preserves_same_named_session_on_another_tmux_owner(
    tmp_path: Path,
) -> None:
    harness = tmp_path / "harness"
    codex_home = tmp_path / "codex-home"
    workspace = tmp_path / "workspace"
    harness.mkdir()
    codex_home.mkdir(mode=0o700)
    workspace.mkdir()
    create = _profile_command(
        "create",
        "--harness-dir",
        str(harness),
        "--codex-home",
        str(codex_home),
        "--work-dir",
        str(workspace),
        "--session",
        "same-name",
        "--owner-id",
        "/tmp/tmux-a|session-1|same-name",
        "--pane",
        "%1",
        "--persona",
        "pm",
        "--launcher-pid",
        "4242",
    )
    assert create.returncode == 0, create.stderr + create.stdout
    profile = Path(create.stdout.splitlines()[1])

    wrong_owner = _profile_command(
        "reap",
        "--harness-dir",
        str(harness),
        "--session",
        "same-name",
        "--owner-id",
        "/tmp/tmux-b|session-1|same-name",
    )

    assert wrong_owner.returncode == 0, wrong_owner.stderr + wrong_owner.stdout
    assert profile.is_file()
    right_owner = _profile_command(
        "reap",
        "--harness-dir",
        str(harness),
        "--session",
        "same-name",
        "--owner-id",
        "/tmp/tmux-a|session-1|same-name",
    )
    assert right_owner.returncode == 0, right_owner.stderr + right_owner.stdout
    assert not profile.exists()


def test_reaper_without_exact_tmux_owner_fails_and_preserves_profile(
    tmp_path: Path,
) -> None:
    harness, _codex_home, profile = _create_profile(
        tmp_path, session="solar-orphan"
    )

    completed = _profile_command(
        "reap",
        "--harness-dir",
        str(harness),
        "--session",
        "solar-orphan",
    )

    assert completed.returncode != 0
    assert "exact tmux owner unavailable" in completed.stdout
    assert profile.is_file()


def test_reaper_refuses_profile_symlink_without_touching_target(tmp_path: Path) -> None:
    harness, _codex_home, profile = _create_profile(
        tmp_path, session="solar-owned"
    )
    foreign = tmp_path / "foreign.config.toml"
    foreign.write_text("foreign\n", encoding="utf-8")
    profile.unlink()
    profile.symlink_to(foreign)

    completed = _reap(harness, "solar-owned")

    assert completed.returncode != 0
    assert profile.is_symlink()
    assert foreign.read_text(encoding="utf-8") == "foreign\n"


def test_reaper_refuses_regular_profile_when_owner_marker_changed(tmp_path: Path) -> None:
    harness, _codex_home, profile = _create_profile(
        tmp_path, session="solar-owned"
    )
    profile.write_text("foreign regular profile\n", encoding="utf-8")

    completed = _reap(harness, "solar-owned")

    assert completed.returncode != 0
    assert profile.read_text(encoding="utf-8") == "foreign regular profile\n"


def test_parallel_panes_create_distinct_profiles_without_registry_race(
    tmp_path: Path,
) -> None:
    harness = tmp_path / "harness"
    codex_home = tmp_path / "codex-home"
    workspace = tmp_path / "workspace"
    harness.mkdir()
    codex_home.mkdir(mode=0o700)
    workspace.mkdir()

    def create(index: int) -> subprocess.CompletedProcess[str]:
        return _profile_command(
            "create",
            "--harness-dir",
            str(harness),
            "--codex-home",
            str(codex_home),
            "--work-dir",
            str(workspace),
            "--session",
            "solar-parallel",
            "--owner-id",
            _owner_id("solar-parallel"),
            "--pane",
            f"%{index}",
            "--persona",
            "builder",
            "--launcher-pid",
            str(5000 + index),
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        completed = list(pool.map(create, range(12)))

    failures = [item.stderr + item.stdout for item in completed if item.returncode]
    assert not failures, "\n".join(failures)
    profiles = sorted(codex_home.glob("solar-managed-*.config.toml"))
    assert len(profiles) == 12
    assert len({path.name for path in profiles}) == 12
    assert _reap(harness, "solar-parallel").returncode == 0
    assert not list(codex_home.glob("solar-managed-*.config.toml"))


def test_product_stop_reaps_both_owned_cockpit_sessions() -> None:
    source = HARNESS_ENTRY.read_text(encoding="utf-8")
    kill_block = source.split("kill_harness()", 1)[1].split("\n}", 1)[0]

    assert '"$SESSION_NAME" "$session_owner_id"' in kill_block
    assert '"$LAB_SESSION_NAME" "$lab_owner_id"' in kill_block
    assert "cleanup_failed=1" in kill_block
    assert 'return "$cleanup_failed"' in kill_block


def test_real_product_stop_reaps_registered_profile(tmp_path: Path) -> None:
    harness, _codex_home, profile = _create_profile(
        tmp_path, session="solar-product-stop"
    )

    completed = _run_product_stop(
        tmp_path, harness=harness, session="solar-product-stop"
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert not profile.exists()


def test_real_product_stop_fails_truthfully_on_unsafe_profile(tmp_path: Path) -> None:
    harness, _codex_home, profile = _create_profile(
        tmp_path, session="solar-product-stop"
    )
    foreign = tmp_path / "must-survive"
    foreign.write_text("foreign\n", encoding="utf-8")
    profile.unlink()
    profile.symlink_to(foreign)

    completed = _run_product_stop(
        tmp_path, harness=harness, session="solar-product-stop"
    )

    assert completed.returncode != 0
    assert "require manual inspection" in completed.stdout
    assert profile.is_symlink()
    assert foreign.read_text(encoding="utf-8") == "foreign\n"
