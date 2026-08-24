from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
SHIM = HARNESS / "plugins" / "autosci" / "bin" / "autosci_skill_shim.py"
if str(SHIM.parent) not in sys.path:
    sys.path.insert(0, str(SHIM.parent))

import autosci_skill_shim  # noqa: E402


def test_shim_loads_through_its_production_entrypoint_context() -> None:
    assert Path(autosci_skill_shim.__file__).resolve() == SHIM.resolve()


def test_research_opt_in_preserves_complete_prompt_run_id_and_uses_solar_route(tmp_path: Path) -> None:
    prompt_parts = [
        "请深入分析",
        "https://example.test/research",
        "并用中文输出完整技术报告",
    ]
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(SHIM),
            "$research",
            *prompt_parts,
            "--solar-orchestrator",
            "--run-id",
            "shim-route-001",
        ],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["run_id"] == "shim-route-001"
    assert payload["prompt"] == " ".join(prompt_parts)
    assert payload["route"]["start_stage"] == "web_fetch"
    assert payload["start_node"] == "seed_fetch"
    assert payload["route"]["workflow_kind"] != "workflow_evolution"
    assert "real_data_research" not in proc.stdout


def test_research_opt_in_forwards_explicit_codex_provider_and_model(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout='{"final_status":"completed"}\n', stderr="")

    monkeypatch.setattr(autosci_skill_shim.subprocess, "run", fake_run)

    exit_code = autosci_skill_shim.main(
        [
            "$research",
            "分析指定网页",
            "--solar-orchestrator",
            "--review-llm-provider",
            "codex",
            "--review-llm-model",
            "gpt-test",
            "--approval-ref",
            "user-approved-test",
        ]
    )

    assert exit_code == 0
    command = captured["command"]
    assert command[command.index("--model-provider") + 1] == "codex"
    assert command[command.index("--model") + 1] == "gpt-test"
    assert "--allow-live-provider" in command
    assert command[command.index("--approval-ref") + 1] == "user-approved-test"
    assert json.loads(capsys.readouterr().out)["final_status"] == "completed"
