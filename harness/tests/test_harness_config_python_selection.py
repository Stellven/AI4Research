from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
HARNESS = REPO / "harness"


def _bash_executable() -> str:
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    if git_bash.exists():
        return str(git_bash)
    executable = shutil.which("bash")
    assert executable, "bash is required"
    return executable


def _bash_path(path: Path) -> str:
    value = path.resolve().as_posix()
    if len(value) >= 3 and value[1:3] == ":/":
        return f"/{value[0].lower()}{value[2:]}"
    return value


@pytest.mark.parametrize("config_script", ["lib/harness-config.sh", "harness-config.sh"])
def test_config_uses_explicit_solar_python_without_path_contamination(
    tmp_path: Path, config_script: str
) -> None:
    config = tmp_path / "solar-user-config.json"
    config.write_text(json.dumps({"runtime": "codex"}), encoding="utf-8")

    selected_bin = tmp_path / "selected-bin"
    selected_bin.mkdir()
    selected_python = selected_bin / "selected-python"
    selected_python.write_text(
        f'#!/usr/bin/env bash\nexec "{_bash_path(Path(sys.executable))}" "$@"\n',
        encoding="utf-8",
    )
    os.chmod(selected_python, 0o755)

    contaminated_bin = tmp_path / "contaminated-bin"
    contaminated_bin.mkdir()
    fallback_python = contaminated_bin / "python3"
    fallback_python.write_text(
        "#!/usr/bin/env bash\nprintf 'CONTAMINATED\\n'\nexit 91\n",
        encoding="utf-8",
    )
    os.chmod(fallback_python, 0o755)

    env = {
        **os.environ,
        "HARNESS_DIR": _bash_path(HARNESS),
        "SOLAR_USER_CONFIG": _bash_path(config),
        "SOLAR_PYTHON": _bash_path(selected_python),
        "PATH": f"{_bash_path(contaminated_bin)}:{os.environ['PATH']}",
    }
    proc = subprocess.run(
        [_bash_executable(), "-c", f'source "$HARNESS_DIR/{config_script}"; solar_config_json_get runtime claude'],
        cwd=REPO,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "codex"
    assert "CONTAMINATED" not in proc.stdout + proc.stderr
