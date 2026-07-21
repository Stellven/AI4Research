from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
SAFE_BIN = AUDIT_ROOT / "tmp" / "safe-bin"

CASES = [
    ("installer-contract", "scripts/check-installer-contract.sh", []),
    ("autosci-install-closure", "scripts/check-autosci-install-closure.sh", []),
    ("mempalace-component", "scripts/mempalace-check.sh", []),
    ("daemons-lifecycle", "scripts/check-daemons-lifecycle.sh", []),
    ("smoke-minimal", "scripts/smoke-install-matrix.sh", ["minimal"]),
    ("smoke-full-non-rust", "scripts/smoke-install-matrix.sh", ["full-non-rust"]),
]


def isolated_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if re.search(r"(API[_-]?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|ACCESS[_-]?KEY|OAUTH)", key, re.I):
            env.pop(key, None)
    home = tmp_path / "home"
    temp = tmp_path / "tmp"
    home.mkdir()
    temp.mkdir()
    env.update(
        {
            "HOME": str(home),
            "CODEX_HOME": str(home / ".codex"),
            "TMPDIR": str(temp),
            "HARNESS_TEST": "1",
            "SOLAR_SKIP_PY_DEPS": "true",
            "PATH": os.pathsep.join([str(SAFE_BIN), str(CHECKOUT / ".venv/bin"), os.environ.get("PATH", "")]),
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "127.0.0.1,localhost",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GEMINI_API_KEY": "",
            "GITHUB_TOKEN": "",
            "GH_TOKEN": "",
        }
    )
    return env


@pytest.mark.parametrize("case,relative,args", CASES, ids=[item[0] for item in CASES])
def test_installer_component_contract(case: str, relative: str, args: list[str], tmp_path: Path) -> None:
    command = ["/opt/homebrew/bin/bash", str(CHECKOUT / relative), *args]
    proc = subprocess.run(
        command,
        cwd=CHECKOUT,
        env=isolated_env(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=360,
        check=False,
    )
    assert proc.returncode == 0, f"{case}\nSTDOUT:\n{proc.stdout[-12000:]}\nSTDERR:\n{proc.stderr[-12000:]}"
