from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
PYTHON = CHECKOUT / ".venv/bin/python"


SKILLS = [
    "skills/solar/SKILL.md",
    "skills/office/SKILL.md",
    "skills/obsidian-direct/SKILL.md",
    "skills/apple-calendar/SKILL.md",
    "skills/browser-automation/SKILL.md",
]


def safe_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if any(marker in key.upper() for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
            env.pop(key, None)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env.update(
        {
            "HOME": str(home),
            "SOLAR_HOME": str(home / ".solar"),
            "HARNESS_DIR": str(CHECKOUT / "harness"),
            "AUTOSCI_DISABLE_NETWORK_FETCH": "1",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "RAGFLOW_BASE_URL": "",
            "RAGFLOW_API_KEY": "",
            "GEMINI_API_KEY": "",
            "GOOGLE_API_KEY": "",
        }
    )
    return env


@pytest.mark.parametrize("relative", SKILLS, ids=[Path(path).parent.name for path in SKILLS])
def test_skill_manifest_is_discoverable_and_has_portable_frontmatter(relative: str) -> None:
    text = (CHECKOUT / relative).read_text(encoding="utf-8")
    assert text.startswith("---\n")
    frontmatter = text.split("---", 2)[1]
    assert re.search(r"(?m)^name:\s*\S+", frontmatter)
    assert re.search(r"(?m)^description:\s*\S+", frontmatter)
    assert not re.search(r"(?m)(?:/Users/|/home/[^/$\s]+/)", text), (
        "shipped skill contains a developer-specific absolute home path"
    )


def test_ragflow_doctor_reports_missing_live_config_without_network(tmp_path: Path) -> None:
    proc = subprocess.run(
        [str(PYTHON), "harness/tools/ragflow_adapter.py", "doctor"],
        cwd=CHECKOUT,
        env=safe_env(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "status: warn" in proc.stdout
    assert "base_url: N/A" in proc.stdout
    assert "api_key: RAGFLOW_API_KEY" in proc.stdout


def test_gemini_doctor_reports_auth_and_sdk_gaps_without_secret_values(tmp_path: Path) -> None:
    proc = subprocess.run(
        [str(PYTHON), "harness/tools/gemini_adapter.py", "doctor"],
        cwd=CHECKOUT,
        env=safe_env(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["cli"]["ready"] is False
    assert payload["cli"]["api_key_env_present"] is False
    assert "interactive Gemini CLI login" in payload["cli"]["warning"]
    assert payload["sdk"]["ok"] is False


def test_obsidian_indexer_missing_vault_is_explicit_and_does_not_create_vault(tmp_path: Path) -> None:
    vault = tmp_path / "missing-vault"
    proc = subprocess.run(
        [
            str(PYTHON),
            "harness/tools/obsidian-vault-indexer.py",
            "--vault",
            str(vault),
            "--db",
            str(tmp_path / "index.sqlite"),
            "--once",
            "--dry-run",
            "--json",
        ],
        cwd=CHECKOUT,
        env=safe_env(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert payload["error"].startswith("vault not found:")
    assert payload["indexed"] == 0
    assert not vault.exists()


def test_codex_operator_missing_dispatch_fails_without_running_codex(tmp_path: Path) -> None:
    proc = subprocess.run(
        [str(PYTHON), "harness/tools/codex_operator.py"],
        cwd=CHECKOUT,
        env=safe_env(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )
    assert proc.returncode != 0
    assert "empty dispatch" in (proc.stdout + proc.stderr).lower()
    assert not (tmp_path / "home/.codex").exists()
