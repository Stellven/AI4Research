from __future__ import annotations

import json

import harness.tools.research_runtime_doctor as doctor


def test_cli_exit_code_ready(monkeypatch, capsys) -> None:
    monkeypatch.setattr(doctor, "check_research_runtime", lambda **_kwargs: {"status": "ready", "blockers": [], "limitations": []})

    assert doctor.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"


def test_cli_exit_code_ready_with_limitations(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        doctor,
        "check_research_runtime",
        lambda **_kwargs: {"status": "ready_with_limitations", "blockers": [], "limitations": ["offline_mode"]},
    )

    assert doctor.main(["--json", "--offline"]) == 0
    assert "offline_mode" in capsys.readouterr().out


def test_cli_exit_code_blocked(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        doctor,
        "check_research_runtime",
        lambda **_kwargs: {"status": "blocked", "blockers": [{"check": "codex_cli", "reason": "missing_codex_cli"}], "limitations": []},
    )

    assert doctor.main(["--json", "--require-tmux"]) == 3
    assert json.loads(capsys.readouterr().out)["blockers"][0]["reason"] == "missing_codex_cli"


def test_cli_exit_code_invalid_invocation(capsys) -> None:
    assert doctor.main(["--does-not-exist"]) == 4
    assert json.loads(capsys.readouterr().err)["status"] == "invalid_invocation"


def test_cli_json_is_deterministic_and_secret_safe(monkeypatch, capsys) -> None:
    secret = "sk-do-not-print"

    def fake_check(**_kwargs):
        return {
            "schema": "research_runtime_readiness.v1",
            "status": "ready",
            "provider_environment": {"OPENAI_API_KEY": "present"},
            "checks": {"provider_environment": {"ok": True, "providers": {"OPENAI_API_KEY": "present"}}},
            "blockers": [],
            "limitations": [],
        }

    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setenv("SOLAR_LIVE_PROVIDER_APPROVAL_REF", "approval-1")
    monkeypatch.setattr(doctor, "check_research_runtime", fake_check)

    assert doctor.main(["--json", "--require-provider", "OPENAI_API_KEY"]) == 0
    first = capsys.readouterr().out
    assert doctor.main(["--json", "--require-provider", "OPENAI_API_KEY"]) == 0
    second = capsys.readouterr().out

    assert first == second
    assert secret not in first


def test_cli_passes_every_repeated_required_provider(monkeypatch, capsys) -> None:
    captured: dict = {}

    def fake_check(**kwargs):
        captured.update(kwargs)
        return {"status": "blocked", "blockers": [], "limitations": []}

    monkeypatch.setattr(doctor, "check_research_runtime", fake_check)
    exit_code = doctor.main(
        [
            "--json",
            "--require-provider",
            "OPENAI_API_KEY",
            "--require-provider",
            "SEMANTIC_SCHOLAR_API_KEY",
        ]
    )

    assert exit_code == 3
    assert captured["require_provider"] == (
        "OPENAI_API_KEY",
        "SEMANTIC_SCHOLAR_API_KEY",
    )
    assert captured["allowed_provider_env_names"] == captured["require_provider"]
    capsys.readouterr()
