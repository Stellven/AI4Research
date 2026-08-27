from __future__ import annotations

from pathlib import Path

from harness.plugins.autosci.runtime_env import load_local_provider_env


def test_load_local_provider_env_reads_only_allowlisted_missing_secret(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "SEMANTIC_SCHOLAR_API_KEY=opaque-s2-key\n"
        "OPENAI_API_KEY=must-not-load\n",
        encoding="utf-8",
    )
    env: dict[str, str] = {}

    loaded = load_local_provider_env(dotenv, env=env)

    assert loaded == {"SEMANTIC_SCHOLAR_API_KEY"}
    assert env == {"SEMANTIC_SCHOLAR_API_KEY": "opaque-s2-key"}


def test_load_local_provider_env_never_overwrites_process_secret(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("SEMANTIC_SCHOLAR_API_KEY=file-value\n", encoding="utf-8")
    env = {"SEMANTIC_SCHOLAR_API_KEY": "process-value"}

    loaded = load_local_provider_env(dotenv, env=env)

    assert loaded == set()
    assert env["SEMANTIC_SCHOLAR_API_KEY"] == "process-value"
