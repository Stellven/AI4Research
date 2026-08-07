"""Real user-entrypoint journeys for the shared OpenSolar control plane.

These tests deliberately invoke production scripts and the production HTTP handler.
They never replace the intake command, tmux binary, or status-server routes with a
fixture.  ``SOLAR_ENTRYPOINT_E2E=1`` is required because the journey creates a
temporary harness and opens loopback listeners in the reserved 18300--18349 range.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest


REPO = Path(__file__).resolve().parents[3]
PORT_START, PORT_STOP = 18300, 18350


def _enabled() -> None:
    if os.environ.get("SOLAR_ENTRYPOINT_E2E") != "1":
        pytest.skip("set SOLAR_ENTRYPOINT_E2E=1 to run the real entrypoint journeys")
    if os.name == "nt":
        pytest.skip("run this journey in WSL/Linux; Windows-native tmux is not available")


def _run(argv: list[str], *, env: dict[str, str], cwd: Path, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout, check=False)


def _wait_port(port_file: Path, proc: subprocess.Popen[str]) -> int:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"status-server exited early: {proc.returncode}")
        try:
            port = int(port_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            time.sleep(0.1)
            continue
        if PORT_START <= port < PORT_STOP:
            return port
        raise AssertionError(f"status-server used non-reserved port {port}")
    raise AssertionError("status-server did not publish a port")


def _json_request(base: str, path: str, payload: dict[str, object] | None = None, token: str = "") -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Solar-Token"] = token
    if body is not None:
        headers["Content-Type"] = "application/json"
    with urlopen(Request(base + path, data=body, headers=headers), timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


@pytest.fixture()
def isolated_runtime(tmp_path: Path):
    _enabled()
    harness = tmp_path / "solar" / "harness"
    harness.mkdir(parents=True)
    # Keep all executable product code in place and place only mutable runtime
    # state in the sandbox.  Copying the whole harness is slow on /mnt/c and
    # makes a test timeout look like an entrypoint failure.
    for name in ("config", "lib", "status-server", "templates", "tools"):
        (harness / name).symlink_to(REPO / "harness" / name, target_is_directory=True)
    (harness / "solar-harness.sh").symlink_to(REPO / "harness" / "solar-harness.sh")
    (harness / "session.sh").symlink_to(REPO / "harness" / "session.sh")
    solar_bin = tmp_path / "solar" / "bin"
    solar_bin.mkdir(parents=True)
    shutil.copy2(REPO / "bin" / "solar", solar_bin / "solar")
    (solar_bin / "solar").chmod(0o755)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    for name in ("config", "run", "sprints", "events", "sessions", "reports", "state"):
        (harness / name).mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "SOLAR_HOME": str(tmp_path / "solar"),
        "HARNESS_DIR": str(harness),
        "SOLAR_HARNESS_DIR": str(harness),
        "SOLAR_INTAKE_WORKSPACE_ROOT": str(workspace),
        "SOLAR_KNOWLEDGE_RAW_DIR": str(tmp_path / "knowledge" / "intake"),
        "SOLAR_PRODUCT_MODE": "0",
        "PATH": f"{solar_bin}:{env['PATH']}",
    })
    # The handler is exactly the production module.  Its port constant is not
    # configurable in production, so inject only the test reservation before
    # calling main; the report records this as an outstanding product limit.
    launcher = (
        "import importlib.util,sys; "
        "spec=importlib.util.spec_from_file_location('entrypoint_status_server',sys.argv[1]); "
        "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); "
        f"module.PORT_RANGE=range({PORT_START},{PORT_STOP}); module.main()"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", launcher, str(harness / "lib" / "symphony" / "status-server.py")],
        cwd=workspace,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    port_file = harness / "run" / "status-server.port"
    try:
        port = _wait_port(port_file, proc)
        token = (harness / "run" / "status-server.token").read_text(encoding="utf-8").strip()
        yield {"env": env, "harness": harness, "workspace": workspace, "base": f"http://127.0.0.1:{port}", "token": token, "proc": proc}
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=8)
        assert not port_file.exists(), "status-server left its port file behind"


def _sprint_from(text: str) -> str:
    match = re.search(r"Sprint created:\s*(\S+)", text)
    assert match, text
    return match.group(1)


def test_cli_tui_and_gui_http_share_the_real_intake_control_plane(isolated_runtime: dict) -> None:
    env, harness, workspace, base, token = (isolated_runtime[key] for key in ("env", "harness", "workspace", "base", "token"))
    cli_task = "Create a production intake contract for CLI entrypoint verification."
    cli = _run([str(Path(env["SOLAR_HOME"]) / "bin" / "solar"), "harness", "intake", "--no-dispatch", "--request", cli_task], env=env, cwd=workspace)
    assert cli.returncode == 0, cli.stderr + cli.stdout
    cli_sprint = _sprint_from(cli.stdout)
    assert cli_task in (harness / "sprints" / f"{cli_sprint}.contract.md").read_text(encoding="utf-8")

    request_id = "gui-control-plane-run-18300"
    gui_task = "Create a production intake contract submitted through the GUI control plane."
    gui = _json_request(base, "/intake", {"task": gui_task, "request_id": request_id}, token)
    assert gui["ok"] is True, gui
    gui_sprint = str(gui["sprint_id"])
    assert gui_sprint and gui_sprint != cli_sprint
    assert gui["request_id"] == request_id
    assert gui_task in (harness / "sprints" / f"{gui_sprint}.contract.md").read_text(encoding="utf-8")
    request_record = json.loads((harness / "run" / "intake-requests" / f"{request_id}.json").read_text(encoding="utf-8"))
    assert request_record["request_id"] == request_id

    indexed = _json_request(base, "/sprints?limit=20", token=token)
    ids = {row["sprint_id"] for row in indexed["data"]["sprints"]}
    assert {cli_sprint, gui_sprint}.issubset(ids)

    tui = _run([str(Path(env["SOLAR_HOME"]) / "bin" / "solar"), "ui", "--once", "--no-color"], env=env, cwd=workspace)
    assert tui.returncode == 0, tui.stderr + tui.stdout
    assert "Solar UI-lite" in tui.stdout
    assert f"{gui_sprint}.status.json" in tui.stdout


def test_tmux_single_and_dual_session_input_output_recovery_and_exit(tmp_path: Path) -> None:
    _enabled()
    tmux = shutil.which("tmux")
    assert tmux, "tmux is required for the production TMUX journey"
    socket_dir = tmp_path / "tmux-socket"
    socket_dir.mkdir()
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    env = os.environ.copy()
    env["TMUX_TMPDIR"] = str(socket_dir)
    sessions = ("entrypoint-one", "entrypoint-two")
    try:
        for session in sessions:
            artifact = artifact_dir / f"{session}.txt"
            command = f"read value; printf '%s' \"$value\" > {artifact}; echo received:$value; exec bash"
            result = _run([tmux, "new-session", "-d", "-s", session, command], env=env, cwd=tmp_path)
            assert result.returncode == 0, result.stderr
        for session, value in zip(sessions, ("alpha-only", "beta-only")):
            assert _run([tmux, "send-keys", "-t", f"{session}:0.0", "-l", value], env=env, cwd=tmp_path).returncode == 0
            assert _run([tmux, "send-keys", "-t", f"{session}:0.0", "Enter"], env=env, cwd=tmp_path).returncode == 0
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not all((artifact_dir / f"{session}.txt").exists() for session in sessions):
            time.sleep(0.1)
        assert (artifact_dir / "entrypoint-one.txt").read_text() == "alpha-only"
        assert (artifact_dir / "entrypoint-two.txt").read_text() == "beta-only"
        capture_one = _run([tmux, "capture-pane", "-p", "-t", "entrypoint-one:0.0"], env=env, cwd=tmp_path)
        capture_two = _run([tmux, "capture-pane", "-p", "-t", "entrypoint-two:0.0"], env=env, cwd=tmp_path)
        assert "alpha-only" in capture_one.stdout and "beta-only" not in capture_one.stdout
        assert "beta-only" in capture_two.stdout and "alpha-only" not in capture_two.stdout

        recovery = artifact_dir / "recovered.txt"
        result = _run([tmux, "respawn-pane", "-k", "-t", "entrypoint-one:0.0", f"printf recovered > {recovery}; echo recovered; exec bash"], env=env, cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not recovery.exists():
            time.sleep(0.1)
        assert recovery.read_text() == "recovered"
    finally:
        for session in sessions:
            _run([tmux, "kill-session", "-t", session], env=env, cwd=tmp_path)
        for session in sessions:
            assert _run([tmux, "has-session", "-t", session], env=env, cwd=tmp_path).returncode != 0


def test_cmux_remote_plan_is_escaped_and_multitab_launch_fails_closed(tmp_path: Path) -> None:
    _enabled()
    config = tmp_path / "workspace.yaml"
    config.write_text(
        """workspace_name: controlled-transport\nssh_profiles:\n  loop:\n    user: runner\n    host: loopback;not-a-shell-command\ntabs:\n  - id: remote\n    panes:\n      - title: remote-view\n        source: remote\n        ssh_profile: loop\n        mode: capture\n        tmux_target: entrypoint-one:0.0;echo unsafe\n  - id: second\n    panes:\n      - title: local-tail\n        source: local\n        mode: tail\n        log_path: /tmp/entrypoint.log\n""",
        encoding="utf-8",
    )
    renderer = REPO / "harness" / "scripts" / "cmux" / "render-cmux-workspace"
    plan = _run([sys.executable, str(renderer), str(config), "--json"], env=os.environ.copy(), cwd=tmp_path)
    assert plan.returncode == 0, plan.stderr
    command = json.loads(plan.stdout)["tabs"][0]["panes"][0]["command"]
    assert "'runner@loopback;not-a-shell-command'" in command
    assert "echo unsafe" in command and "'" in command

    monitor = REPO / "harness" / "scripts" / "cmux" / "cmux-monitor-up"
    launch = _run([sys.executable, str(monitor), str(config)], env=os.environ.copy(), cwd=tmp_path)
    assert launch.returncode == 2
    assert "multi-tab cmux workspaces are not supported" in launch.stderr
