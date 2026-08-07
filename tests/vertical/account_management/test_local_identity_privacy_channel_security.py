from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[3]
SOLAR_CLI = REPO / "bin" / "solar"


def _bash_executable() -> str | None:
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    if git_bash.exists():
        return str(git_bash)
    executable = shutil.which("bash")
    if executable and "WindowsApps" not in executable:
        return executable
    return None


def _bash_path(path: Path) -> str:
    value = path.resolve().as_posix()
    if len(value) >= 3 and value[1:3] == ":/":
        return f"/{value[0].lower()}{value[2:]}"
    return value


def _quote(value: str | Path) -> str:
    text = _bash_path(value) if isinstance(value, Path) else str(value)
    return "'" + text.replace("'", "'\"'\"'") + "'"


def _write_python3_shim(fake_bin: Path) -> None:
    fake_bin.mkdir(parents=True, exist_ok=True)
    shim = fake_bin / "python3"
    shim.write_text(
        f'#!/usr/bin/env bash\nexec "{_bash_path(Path(sys.executable))}" "$@"\n',
        encoding="utf-8",
    )
    os.chmod(shim, 0o755)


def _run_solar(
    tmp_path: Path,
    sandbox_home: Path,
    *args: str,
    stdin: str = "",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    bash = _bash_executable()
    assert bash is not None, "Git Bash or bash is required for solar identity tests"
    fake_bin = tmp_path / "fake-bin"
    _write_python3_shim(fake_bin)
    solar_home = sandbox_home / ".solar"
    claude_dir = sandbox_home / ".claude"
    arg_text = " ".join(_quote(arg) for arg in args)
    command = (
        f"PATH={_quote(fake_bin)}:$PATH "
        f"HOME={_quote(sandbox_home)} "
        f"USERPROFILE={_quote(sandbox_home)} "
        f"SOLAR_HOME={_quote(solar_home)} "
        f"CLAUDE_DIR={_quote(claude_dir)} "
        f"bash {_quote(SOLAR_CLI)} {arg_text}"
    )
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [bash, "-lc", command],
        cwd=REPO,
        input=stdin,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
        env=env,
    )


def _json_stdout(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def _json_stderr(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert proc.returncode != 0, proc.stdout + proc.stderr
    return json.loads(proc.stderr)


def _identity_store(home: Path) -> Path:
    return home / ".solar" / "identity" / "local-accounts.json"


def test_local_identity_register_login_logout_and_expiry_use_secure_store(tmp_path: Path) -> None:
    home = tmp_path / "home"
    password = "CorrectHorseBatteryStaple-Phase22"

    unsupported = _run_solar(
        tmp_path,
        home,
        "identity",
        "register",
        "--username",
        "r6-user",
        "--password-stdin",
        stdin=password,
    )
    assert unsupported.returncode == 2
    assert _json_stderr(unsupported)["error"] == "product_account_unsupported"
    assert not _identity_store(home).exists()

    registered = _json_stdout(
        _run_solar(
            tmp_path,
            home,
            "identity",
            "register",
            "--local-only",
            "--username",
            "r6-user",
            "--display-name",
            "R6 User",
            "--terms-version",
            "local-identity-v1",
            "--session-ttl",
            "60",
            "--password-stdin",
            stdin=password,
        )
    )
    token = registered["session"]["token"]
    store_text = _identity_store(home).read_text(encoding="utf-8")
    store = json.loads(store_text)
    account = store["accounts"]["r6-user"]

    assert registered["account_scope"] == "local_only"
    assert registered["product_account_status"] == "unsupported"
    assert account["password_hash"]["algorithm"] == "pbkdf2_sha256"
    assert account["password_hash"]["iterations"] >= 260_000
    assert password not in store_text
    assert token not in store_text

    active_proc = _run_solar(tmp_path, home, "identity", "session", stdin=token)
    assert token not in str(active_proc.args)
    assert token not in active_proc.stdout
    assert token not in active_proc.stderr
    active = _json_stdout(active_proc)
    assert active["session"]["active"] is True
    assert active["session"]["username"] == "r6-user"
    for artifact in home.rglob("*"):
        if artifact.is_file():
            assert token not in artifact.read_text(encoding="utf-8", errors="replace")

    logged_out = _json_stdout(
        _run_solar(tmp_path, home, "identity", "logout", "--token-stdin", stdin=token)
    )
    assert logged_out["state"] == "logged_out"
    invalid_after_logout = _run_solar(tmp_path, home, "identity", "session", stdin=token)
    assert invalid_after_logout.returncode == 3
    assert _json_stderr(invalid_after_logout)["error"] == "invalid_session"

    login = _json_stdout(
        _run_solar(
            tmp_path,
            home,
            "identity",
            "login",
            "--username",
            "r6-user",
            "--session-ttl",
            "1",
            "--password-stdin",
            stdin=password,
        )
    )
    short_token = login["session"]["token"]
    time.sleep(1.2)
    expired = _run_solar(tmp_path, home, "identity", "session", "--token-stdin", stdin=short_token)
    assert expired.returncode == 3
    assert _json_stderr(expired)["error"] == "invalid_session"


def test_privacy_export_redaction_delete_removes_sensitive_profile_access(tmp_path: Path) -> None:
    home = tmp_path / "privacy-home"
    password = "Phase22-Privacy-Password-Long"
    email = "phase22+owner@example.invalid"
    phone = "13800001111"
    secret = "Bearer J24-SECRET-TOKEN-VALIDATION-CASE-2026"

    registered = _json_stdout(
        _run_solar(
            tmp_path,
            home,
            "identity",
            "register",
            "--local-only",
            "--username",
            "privacy-user",
            "--password-stdin",
            stdin=password,
        )
    )
    token = registered["session"]["token"]
    profile = {"display_name": "Privacy User", "contact_email": email, "phone": phone, "api_token": secret}
    profile_set = _json_stdout(
        _run_solar(
            tmp_path,
            home,
            "identity",
            "profile",
            "set",
            "--token-stdin",
            "--data-json",
            json.dumps(profile),
            stdin=token,
        )
    )
    assert profile_set["profile_updated"] is True
    assert email not in json.dumps(profile_set)
    assert secret not in json.dumps(profile_set)

    export_path = home / "export" / "privacy-export.json"
    exported = _json_stdout(
        _run_solar(
            tmp_path,
            home,
            "privacy",
            "export",
            "--token-stdin",
            "--out",
            str(export_path),
            stdin=token,
        )
    )
    assert exported["redacted"] is True
    export_text = export_path.read_text(encoding="utf-8")
    assert "[EMAIL]" in export_text
    assert "[PHONE]" in export_text
    assert "[REDACTED]" in export_text
    assert email not in export_text
    assert phone not in export_text
    assert secret not in export_text

    raw_path = home / "raw-note.txt"
    redacted_path = home / "redacted-note.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(f"Contact {email} {phone} {secret}", encoding="utf-8")
    redacted = _json_stdout(
        _run_solar(tmp_path, home, "privacy", "redact", "--in", str(raw_path), "--out", str(redacted_path))
    )
    assert redacted["redacted"] is True
    redacted_text = redacted_path.read_text(encoding="utf-8")
    assert email not in redacted_text
    assert phone not in redacted_text
    assert secret not in redacted_text

    deleted = _json_stdout(
        _run_solar(tmp_path, home, "privacy", "delete", "--token-stdin", "--yes", stdin=token)
    )
    assert deleted["state"] == "deleted"
    denied = _run_solar(tmp_path, home, "identity", "profile", "get", stdin=token)
    assert denied.returncode == 3
    assert _json_stderr(denied)["error"] == "invalid_session"

    store_text = _identity_store(home).read_text(encoding="utf-8")
    assert "privacy-user" not in json.loads(store_text)["accounts"]
    assert email not in store_text
    assert phone not in store_text
    assert secret not in store_text


def test_channel_adapter_contract_is_explicitly_provider_gated(tmp_path: Path) -> None:
    home = tmp_path / "channel-home"
    secret = "DISCORD-SUPER-SECRET-TOKEN-2026"

    discord_status = _json_stdout(
        _run_solar(
            tmp_path,
            home,
            "channel",
            "status",
            "--provider",
            "discord",
            extra_env={"DISCORD_BOT_TOKEN": secret},
        )
    )
    status = discord_status["status"]
    assert status["adapter_id"] == "discord.provider_gate.v1"
    assert status["live_status"] == "provider_gated"
    assert "DISCORD_GUILD_ID" in status["missing_prereqs"]
    assert secret not in json.dumps(discord_status)

    discord_route = _run_solar(
        tmp_path,
        home,
        "channel",
        "route",
        "--provider",
        "discord",
        "--input",
        "hello",
        extra_env={"DISCORD_BOT_TOKEN": secret},
    )
    assert discord_route.returncode == 3
    assert _json_stderr(discord_route)["error"] == "provider_gated"
    assert secret not in discord_route.stdout + discord_route.stderr

    wechat_route = _json_stdout(
        _run_solar(
            tmp_path,
            home,
            "channel",
            "route",
            "--provider",
            "wechat",
            "--input",
            "https://mp.weixin.qq.com/s/example",
        )
    )
    assert wechat_route["route"] == "apple_notes_ingest"
    assert wechat_route["live_status"] == "local_bridge_available"

    unsupported_wechat = _run_solar(
        tmp_path,
        home,
        "channel",
        "route",
        "--provider",
        "wechat",
        "--input",
        "wechat://login?code=fake",
    )
    assert unsupported_wechat.returncode == 2
    assert _json_stderr(unsupported_wechat)["error"] == "unsupported_wechat_input"
