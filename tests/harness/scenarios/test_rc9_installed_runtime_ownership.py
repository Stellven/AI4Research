"""RC9 installed-runtime ownership regressions found by a real dashboard run.

The fresh installed-copy proof used a unique cockpit session while the status
server lived in its path-scoped ``solar-harness-status-server-*`` session.  The
watchdog ignored ``SOLAR_HARNESS_SESSION`` and asked tmux for the prefix
``solar-harness``; tmux resolved that prefix to the status-server session and
the watchdog killed the dashboard as a supposedly unhealthy persona pane.

Afterward, ``status-server start`` treated the surviving tmux server process
as the Python status server merely because its argv still mentioned
``status-server.py``.  These tests pin both ownership boundaries.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_WATCHDOG = _HARNESS / "coordinator-watchdog.sh"
_SOLAR_HARNESS = _HARNESS / "solar-harness.sh"


def _source_watchdog(script: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-c", f'source "$1" help >/dev/null; {script}', "bash", str(_WATCHDOG)],
        env=merged,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_watchdog_honors_configured_cockpit_session_names():
    result = _source_watchdog(
        'printf "%s\\n%s\\n" "$SESSION_NAME" "$LAB_SESSION_NAME"',
        env={
            "SOLAR_HARNESS_SESSION": "solar-rc9-installed-e2e",
            "SOLAR_HARNESS_LAB_SESSION": "solar-rc9-installed-e2e-lab",
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "solar-rc9-installed-e2e",
        "solar-rc9-installed-e2e-lab",
    ]


def test_layout_targets_follow_the_configured_session_name():
    result = _source_watchdog(
        'printf "%s\\n" "${!PERSONA_PANES[@]}" | sort',
        env={
            "SOLAR_HARNESS_SESSION": "solar-rc9-installed-e2e",
            "SOLAR_HARNESS_LAB_SESSION": "solar-rc9-installed-e2e-lab",
        },
    )

    assert result.returncode == 0, result.stderr
    targets = result.stdout.splitlines()
    assert targets
    assert all(not target.startswith("solar-harness:") for target in targets), targets
    assert any(target.startswith("solar-rc9-installed-e2e:") for target in targets), targets


def test_watchdog_session_probe_rejects_tmux_prefix_match(tmp_path: Path):
    tmux_tmp = tmp_path / "tmux"
    tmux_tmp.mkdir()
    env = {**os.environ, "TMUX_TMPDIR": str(tmux_tmp)}
    subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            "solar-harness-status-server-fixture",
            "sleep 60",
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    try:
        result = _source_watchdog(
            'type tmux_has_exact_session >/dev/null 2>&1 || exit 97; '
            'if tmux_has_exact_session "solar-harness"; then echo prefix-accepted; else echo exact-rejected; fi',
            env={"TMUX_TMPDIR": str(tmux_tmp)},
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "exact-rejected"
    finally:
        subprocess.run(
            ["tmux", "kill-server"],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )


def test_harness_status_rejects_tmux_prefix_match(tmp_path: Path):
    """A dashboard session must not impersonate the main cockpit session."""
    tmux_tmp = tmp_path / "tmux"
    tmux_tmp.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "HARNESS_DIR": str(_HARNESS),
        "SOLAR_HARNESS_SESSION": "solar-harness",
        "SOLAR_HARNESS_LAB_SESSION": "solar-harness-lab",
        "TMUX_TMPDIR": str(tmux_tmp),
    }
    subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            "solar-harness-status-server-fixture",
            "sleep 60",
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    try:
        result = subprocess.run(
            ["bash", str(_SOLAR_HARNESS), "status"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "Solar Harness 未运行" in result.stdout, result.stdout
        assert "Product Delivery 运行中" not in result.stdout, result.stdout
    finally:
        subprocess.run(
            ["tmux", "kill-server"],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )


def test_product_mode_watchdog_does_not_launch_intentionally_idle_persona_panes(tmp_path: Path):
    harness = tmp_path / "harness"
    (harness / "run").mkdir(parents=True)
    (harness / "sprints").mkdir()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    tmux_log = tmp_path / "tmux.log"
    fake_tmux = fake_bin / "tmux"
    fake_tmux.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$TMUX_LOG\"\n"
        "if [[ \"${1:-}\" == list-sessions ]]; then\n"
        "  printf '%s\\n' \"$SOLAR_HARNESS_SESSION\"\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_tmux.chmod(0o755)

    result = _source_watchdog(
        'check_panes; cat "$TMUX_LOG"',
        env={
            "HARNESS_DIR": str(harness),
            "SOLAR_PRODUCT_MODE": "1",
            "SOLAR_HARNESS_SESSION": "solar-rc9-installed-e2e",
            "SOLAR_HARNESS_LAB_SESSION": "solar-rc9-installed-e2e-lab",
            "TMUX_LOG": str(tmux_log),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
        },
    )

    assert result.returncode == 0, result.stderr
    calls = result.stdout.splitlines()
    assert calls == ["list-sessions -F #{session_name}"], calls


def _tmp_harness(tmp_path: Path) -> Path:
    harness = tmp_path / "harness"
    (harness / "run").mkdir(parents=True)
    (harness / "lib" / "symphony").mkdir(parents=True)
    for helper in ("run-state.sh", "harness-config.sh"):
        src = _HARNESS / "lib" / helper
        (harness / "lib" / helper).write_bytes(src.read_bytes())
    return harness


def test_status_start_ignores_argv_decoy_that_only_mentions_server_path(tmp_path: Path):
    harness = _tmp_harness(tmp_path)
    server = harness / "lib" / "symphony" / "status-server.py"
    launched = harness / "run" / "actual-server-launched"
    server.write_text(
        "from pathlib import Path\n"
        f"Path({str(launched)!r}).write_text('yes\\n', encoding='utf-8')\n"
        "import time\n"
        "time.sleep(300)\n",
        encoding="utf-8",
    )

    # This is Python, and its argv mentions the exact server path, but it is
    # executing -c rather than the server script.  The old substring matcher
    # falsely adopted it as a live status server.
    decoy = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(300)", str(server)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    env = {**os.environ, "HARNESS_DIR": str(harness)}
    try:
        result = subprocess.run(
            ["bash", str(_SOLAR_HARNESS), "status-server", "start"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        deadline = time.time() + 5
        while time.time() < deadline and not launched.exists():
            time.sleep(0.1)
        assert launched.exists(), (
            "status-server start adopted an argv decoy instead of launching "
            f"the real server: {result.stdout} {result.stderr}"
        )
        assert decoy.poll() is None, "starting the real server killed the unrelated decoy"
    finally:
        subprocess.run(
            ["bash", str(_SOLAR_HARNESS), "status-server", "stop"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if decoy.poll() is None:
            decoy.kill()
        decoy.wait(timeout=10)


def test_status_start_propagates_locked_runtime_settings_into_tmux():
    script = _SOLAR_HARNESS.read_text(encoding="utf-8")
    start = script.index('tmux new-session -d -s "$_SS_TMUX_SESSION"')
    end = script.index("\n          else", start)
    launcher = script[start:end]

    assert "SOLAR_STATUS_PORT_START='$_SS_PORT_START'" in launcher
    assert "SOLAR_STATUS_PORT_END='$_SS_PORT_END'" in launcher
    assert "SOLAR_REQUIRE_TOKEN='${SOLAR_REQUIRE_TOKEN:-0}'" in launcher
    assert "SOLAR_TEST_MODE='${SOLAR_TEST_MODE:-}'" in launcher
    assert "D:\\demo only version\\harness" not in launcher
    assert "172.19.127.84" not in launcher
