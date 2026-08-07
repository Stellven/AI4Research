from __future__ import annotations

import json
import re
import socket
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from evidence import JourneyRecorder, redact
from journey_runner import base_env, bash_argv, bash_blocker


def _http_get(url: str, *, token: str = "") -> tuple[int, object]:
    req = Request(url, method="GET")
    if token:
        req.add_header("X-Solar-Token", token)
    with urlopen(req, timeout=5) as response:
        body = response.read().decode("utf-8", errors="replace")
        if not body:
            return response.status, {}
        try:
            return response.status, json.loads(body)
        except json.JSONDecodeError:
            return response.status, body


def _http_post(url: str, payload: dict[str, object], *, token: str = "") -> tuple[int, object]:
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if token:
        req.add_header("X-Solar-Token", token)
    with urlopen(req, timeout=5) as response:
        body = response.read().decode("utf-8", errors="replace")
        return response.status, json.loads(body) if body else {}


def _is_port_open(port: int, *, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_health(base_url: str, *, token: str = "", timeout: float = 8.0) -> bool:
    if not base_url:
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _ = _http_get(f"{base_url}/healthz", token=token)
            if status == 200:
                return True
        except (HTTPError, URLError, ValueError, json.JSONDecodeError):
            time.sleep(0.25)
    return False


def _load_fixture(repo_root: Path) -> dict[str, object]:
    fixture = (
        Path(__file__).resolve().parent.parent
        / "fixtures"
        / "j01_j10"
        / "j01_j10_journey_inputs.json"
    )
    payload = json.loads(fixture.read_text(encoding="utf-8-sig"))
    return payload.get("j01", {}).get("settings_payload", {})


def _port_from_start_output(text: str | None) -> int:
    if not text:
        return -1
    match = re.search(r"port:\s*(\d+)", text, flags=re.IGNORECASE)
    if not match:
        return -1
    return int(match.group(1))


def _read_token(token_file: Path, *, timeout: float = 3.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
            if token:
                return token
        time.sleep(0.1)
    return ""


def test_p22_j01_install_status(repo_root: Path, tmp_path: Path) -> None:
    rec = JourneyRecorder(repo_root, "P22-J01")
    blocker = bash_blocker(repo_root)
    if blocker:
        rec.add_assertion("bash_available_for_install_sh", False, blocker)
        rec.finalize("ENVIRONMENT_BLOCKED", blockers=[blocker])
        return

    fixture_payload = _load_fixture(repo_root)
    sandbox = tmp_path / "p22-j01"
    env = base_env(repo_root, sandbox)
    solar_home = Path(env["SOLAR_HOME"])
    solar = solar_home / "bin" / "solar"
    harness_dir = solar_home / "harness"
    port_file = harness_dir / "run" / "status-server.port"
    pid_file = harness_dir / "run" / "status-server.pid"
    token_file = harness_dir / "run" / "status-server.token"
    receipt = Path(env["SOLAR_HOME"]) / "install-receipt.json"

    install = rec.run(
        "install",
        [
            *bash_argv(
                repo_root,
                str(repo_root / "install.sh"),
                "--yes",
                "--components",
                "kernel,harness",
                "--solar-home",
                env["SOLAR_HOME"],
                "--claude-dir",
                env["CLAUDE_DIR"],
            )
        ],
        env=env,
        timeout=180,
    )
    if install.returncode != 0:
        detail = (install.stderr or install.stdout)[-1000:]
        rec.add_assertion("install_exit_zero", False, install.returncode)
        if "unsupported OS" in detail:
            rec.finalize("ENVIRONMENT_BLOCKED", blockers=[redact(detail).strip()])
            return
        rec.finalize("FAIL")
        return
    env["HARNESS_DIR"] = str(harness_dir)
    env["SOLAR_HARNESS_DIR"] = str(harness_dir)
    rec.add_artifact(receipt, "install_receipt")
    rec.add_artifact(solar, "cli_launcher")

    doctor = rec.run("doctor-json", bash_argv(repo_root, str(solar), "doctor", "--json"), env=env, timeout=60)
    status = rec.run("status-json", bash_argv(repo_root, str(solar), "status", "--json"), env=env, timeout=60)
    ui = rec.run("ui-once", bash_argv(repo_root, str(solar), "ui", "--once"), env=env, timeout=60)

    doctor_payload = {}
    doctor_ok = False
    if doctor.returncode == 0 and doctor.stdout.strip():
        try:
            doctor_payload = json.loads(doctor.stdout)
            doctor_ok = isinstance(doctor_payload, dict) and doctor_payload.get("verdict") == "ok"
        except json.JSONDecodeError:
            doctor_ok = False

    rec.add_assertion("install_exit_zero", install.returncode == 0, install.returncode)
    rec.add_assertion("doctor_verdict_ok", doctor_ok, doctor_payload.get("verdict") if isinstance(doctor_payload, dict) else "")
    rec.add_assertion("status_command_exit_zero", status.returncode == 0, status.returncode)
    rec.add_assertion("ui_once_exit_zero", ui.returncode == 0, ui.returncode)
    rec.add_assertion(
        "home_scoped_to_sandbox",
        str(Path(env["HOME"]).resolve()).startswith(str(sandbox.resolve())),
        env["HOME"],
    )
    rec.add_assertion(
        "solar_home_scoped_to_sandbox",
        str(Path(env["SOLAR_HOME"]).resolve()).startswith(str(sandbox.resolve())),
        env["SOLAR_HOME"],
    )
    rec.add_assertion(
        "claude_dir_scoped_to_sandbox",
        str(Path(env["CLAUDE_DIR"]).resolve()).startswith(str(sandbox.resolve())),
        env["CLAUDE_DIR"],
    )

    start = rec.run(
        "status-server-start",
        [*bash_argv(repo_root, str(solar), "harness", "status-server", "start")],
        env=env,
        timeout=30,
    )
    rec.add_assertion("status_server_start_exit_zero", start.returncode == 0, start.returncode)

    port_text = port_file.read_text(encoding="utf-8").strip() if port_file.exists() else ""
    port = int(port_text) if port_text.isdigit() else _port_from_start_output(start.stdout)
    rec.add_assertion("status_server_port_discovered", isinstance(port, int) and port > 0, port_text or (start.stdout or "")[-240:])
    rec.add_assertion("status_server_port_open_after_start", _is_port_open(port) if isinstance(port, int) and port > 0 else False, port)

    base_url = f"http://127.0.0.1:{port}" if isinstance(port, int) and port > 0 else ""
    token = _read_token(token_file)
    rec.add_assertion("status_server_health_ready", _wait_for_health(base_url, token=token, timeout=8.0), base_url)

    settings_before: object = {}
    settings_after: object = {}
    settings_read_ok = False
    settings_post_ok = False
    settings_reflected = False
    if base_url:
        try:
            settings_code, settings_before = _http_get(f"{base_url}/settings", token=token)
            settings_read_ok = settings_code == 200 and isinstance(settings_before, dict)
        except (HTTPError, URLError, json.JSONDecodeError):
            settings_read_ok = False

        try:
            write_code, write_payload = _http_post(f"{base_url}/settings", fixture_payload, token=token)
            settings_post_ok = write_code == 200 and isinstance(write_payload, dict) and write_payload.get("ok") is True
        except (HTTPError, URLError, json.JSONDecodeError):
            settings_post_ok = False

        try:
            _, settings_after = _http_get(f"{base_url}/settings", token=token)
            planner_expected = (
                fixture_payload.get("role_models", {}).get("planner", {}).get("model")
                if isinstance(fixture_payload.get("role_models"), dict)
                else None
            )
            if isinstance(settings_after, dict) and planner_expected:
                role_models = settings_after.get("role_models", {})
                planner_actual = role_models.get("planner", {}).get("model") if isinstance(role_models, dict) else None
                settings_reflected = bool(planner_actual and planner_expected and (planner_actual == planner_expected or planner_actual.startswith(planner_expected)))
                rec.add_assertion(
                    "settings_read_planner_reflected",
                    settings_reflected,
                    {"expected": planner_expected, "actual": planner_actual},
                )
            else:
                rec.add_assertion("settings_read_planner_reflected", False, settings_after)
        except (HTTPError, URLError, json.JSONDecodeError):
            settings_read_ok = False

    rec.add_assertion("status_settings_get_exit", settings_read_ok, settings_before)
    rec.add_assertion("status_settings_post_exit", settings_post_ok, "status settings post")
    rec.add_assertion("status_settings_re_read_reflects_payload", settings_reflected, settings_after)
    rec.add_assertion("status_endpoint_ready", not status_return_error(base_url, token=token), "status endpoint")

    provider_readiness: bool
    provider_detail: object
    if base_url:
        try:
            provider_code, provider_payload = _http_get(f"{base_url}/auth/login/status?provider=openai", token=token)
            provider_readiness = provider_code == 200 and isinstance(provider_payload, dict)
            provider_detail = provider_payload
        except Exception:
            provider_readiness = False
            provider_detail = "auth login status endpoint raised before provider readiness could be observed"
    else:
        provider_readiness = False
        provider_detail = "status server base URL unavailable"
    rec.add_assertion("provider_not_logged_in_is_readiness_only", provider_readiness, provider_detail)

    status_pid_text = pid_file.read_text(encoding="utf-8").strip() if pid_file.exists() else ""
    stop = rec.run(
        "status-server-stop",
        [*bash_argv(repo_root, str(solar), "harness", "status-server", "stop")],
        env=env,
        timeout=30,
    )
    rec.add_assertion("status_server_stop_exit_zero", stop.returncode == 0, stop.returncode)
    rec.add_assertion("status_server_port_closed", not _is_port_open(port) if isinstance(port, int) and port > 0 else True, port)
    rec.add_assertion("status_server_pid_file_removed", not pid_file.exists(), str(pid_file))
    rec.add_assertion("status_server_port_file_removed", not port_file.exists(), str(port_file))
    if status_pid_text.isdigit():
        scan_command = f"ps -p {status_pid_text} -o pid=,cmd= 2>/dev/null || true"
    else:
        scan_command = "printf ''"
    process_scan = rec.run(
        "status-server-process-scan",
        [*bash_argv(repo_root, "-lc", scan_command)],
        env=env,
        timeout=20,
    )
    rec.add_assertion("status_server_residue_process_scan", process_scan.stdout.strip() == "", process_scan.stdout.strip())

    rec.add_l2(
        "Vertical",
        "Linux Cli",
        "installer and solar CLI were invoked in sandbox paths",
        rec.run_dir / "commands.json",
        True,
    )
    rec.add_l2(
        "Vertical",
        "Workflow & Platform Status Visibility",
        "status-server lifecycle and settings/status HTTP checks",
        rec.run_dir / "commands.json",
        True,
    )

    provider_only_failures = [item["name"] for item in rec.assertions if not item["passed"]]
    if all(item["passed"] for item in rec.assertions):
        rec.finalize("PASS")
    elif provider_only_failures == ["provider_not_logged_in_is_readiness_only"]:
        rec.finalize(
            "PASS_WITH_KNOWN_LIMITATIONS",
            limitations=["Provider login status endpoint was not observable; install/status/settings core journey completed."],
        )
    else:
        rec.finalize("FAIL")


def status_return_error(base_url: str, *, token: str = "") -> bool:
    if not base_url:
        return True
    try:
        _, status_payload = _http_get(f"{base_url}/status", token=token)
        return not isinstance(status_payload, dict) or not status_payload
    except Exception:
        return True
