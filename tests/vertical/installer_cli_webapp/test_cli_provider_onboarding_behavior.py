from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
BASH = Path(r"C:\Program Files\Git\bin\bash.exe")


def _bash_path(path: Path) -> str:
    value = path.resolve().as_posix()
    if len(value) >= 3 and value[1:3] == ":/":
        return f"/{value[0].lower()}{value[2:]}"
    return value


def test_cli_doctor_reports_selected_codex_runtime(tmp_path: Path) -> None:
    """Exercise the shipped CLI with an isolated home and a portable python3 shim."""
    home = tmp_path / "home"
    solar_home = home / ".solar"
    claude_dir = home / ".claude"
    fake_bin = tmp_path / "bin"
    for path in (
        solar_home / "bin",
        solar_home / "db",
        solar_home / "harness" / "config",
        claude_dir / "solar",
        fake_bin,
    ):
        path.mkdir(parents=True, exist_ok=True)

    (solar_home / "bin" / "solar").touch()
    (solar_home / "db" / "solar.db").touch()
    (solar_home / "install-receipt.json").write_text(
        json.dumps({"components": ["kernel", "harness"], "component_roots": {}}),
        encoding="utf-8",
    )
    (solar_home / "harness" / "config" / "solar-user-config.json").write_text(
        json.dumps({"runtime": "codex", "models": {}}),
        encoding="utf-8",
    )
    (claude_dir / "solar" / "SOLAR.md").write_text("# Solar kernel fixture\n", encoding="utf-8")
    # ``bin/solar`` is launched by Git Bash, but its doctor helper runs under
    # the native Python interpreter.  On Windows, ``shutil.which`` only treats
    # PATHEXT-suffixed files as executables, so the provider fixture must have
    # a Windows executable suffix even though Bash supplies the surrounding
    # test environment.
    codex_cli = fake_bin / ("codex.cmd" if os.name == "nt" else "codex")
    codex_cli.write_text(
        "@exit /b 0\r\n" if os.name == "nt" else "#!/usr/bin/env sh\nexit 0\n",
        encoding="utf-8",
    )
    (fake_bin / "python3").write_text(
        f'#!/usr/bin/env bash\nexec "{Path(sys.executable).as_posix()}" "$@"\n',
        encoding="utf-8",
    )

    command = " ".join(
        [
            f'chmod +x "{_bash_path(codex_cli)}" "{_bash_path(fake_bin / "python3")}";',
            f'HOME="{_bash_path(home)}"',
            f'SOLAR_HOME="{_bash_path(solar_home)}"',
            f'CLAUDE_DIR="{_bash_path(claude_dir)}"',
            f'PATH="{_bash_path(fake_bin)}:/usr/bin:/bin"',
            f'"{_bash_path(REPO / "bin" / "solar")}" doctor --json',
        ]
    )
    completed = subprocess.run(
        [str(BASH), "-lc", command],
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
        check=False,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    assert completed.returncode in {0, 1}, completed.stderr
    payload = json.loads(completed.stdout)
    runtime = payload.get("runtime") or {}
    assert runtime.get("selected") == "codex", runtime
    assert runtime.get("cli") == "present", runtime
    assert "codex login --device-auth" in runtime.get("guidance", ""), runtime
