#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import understand_anything_operator as uao  # noqa: E402


def test_build_request_reads_runtime_preferences(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    envelope = {
        "task_id": "T1",
        "operator_id": "mini-understand-anything-pane-bridge",
        "repo_path": str(repo),
        "runtime_preferences": {
            "pane_target": "3",
            "semantic_backend": "ThunderOMLX",
            "semantic_operator_id": "mini-thunderomlx-qwen36-knowledge",
        },
    }
    payload = uao.build_request(envelope, task_dir=tmp_path)
    assert payload["pane_target"] == "3"
    assert payload["semantic_backend"] == "ThunderOMLX"
    assert payload["skill_command"] == f"/understand --language zh {repo}"
    assert payload["execution_surface"] == "deterministic_scan_and_thunderomlx_semantic"


def test_build_request_resolves_tmux_inventory_target(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(
        uao,
        "_discover_tmux_panes",
        lambda: [
            {
                "session": "solar-harness-lab",
                "window": "0",
                "pane": "1",
                "target": "solar-harness-lab:0.1",
                "title": "Builder 1 | Opus",
                "command": "claude",
            }
        ],
    )
    payload = uao.build_request({"repo_path": str(repo)}, task_dir=tmp_path)
    assert payload["pane_target"] == "solar-harness-lab:0.1"
    assert payload["pane_resolution"]["strategy"] == "tmux_inventory_selector"


def test_validate_request_rejects_non_thunderomlx_backend(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    request = {
        "repo_path": str(repo),
        "execution_surface": "deterministic_scan_and_thunderomlx_semantic",
        "semantic_backend": "Claude",
    }
    try:
        uao._validate_request(request)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "semantic backend must be ThunderOMLX" in str(exc)


def test_validate_request_requires_repo_placeholder(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    request = {
        "repo_path": str(repo),
        "execution_surface": "deterministic_scan_and_thunderomlx_semantic",
        "pane_target": "0",
        "semantic_backend": "ThunderOMLX",
        "skill_command_template": "/understand --language {language}",
    }
    try:
        uao._validate_request(request)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "skill_command_template must include {repo_path}" in str(exc)


def test_run_request_uses_local_pipeline_by_default(monkeypatch, tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(uao, "_ensure_semantic_backend_ready", lambda request, task_dir: None)
    monkeypatch.setattr(
        uao.ofc,
        "current_block_state",
        lambda operator_id, allow_unregistered=True: None,
    )
    monkeypatch.setattr(
        uao.local_pipeline,
        "run_pipeline",
        lambda repo_path, *, output_dir, language, objective: {
            "ok": True,
            "repo_path": repo_path,
            "output_dir": output_dir,
            "knowledge_graph_path": str(Path(output_dir) / "knowledge-graph.json"),
            "config_path": str(Path(output_dir) / "config.json"),
            "meta_path": str(Path(output_dir) / "meta.json"),
            "scan_path": str(Path(output_dir) / "repo-scan.json"),
            "manifest_path": str(Path(output_dir) / "chunk-manifest.json"),
            "resume_state_path": str(Path(output_dir) / "resume-state.json"),
            "prompt_path": str(Path(output_dir) / "semantic-prompt.md"),
            "summary_path": str(Path(output_dir) / "semantic-summary.md"),
            "usage": {"prompt_tokens": 12},
            "chunks_total": 3,
            "chunks_completed": 3,
            "resumed": False,
            "semantic_backend": "ThunderOMLX",
            "semantic_model": "Qwen3.6-35b-a3b",
            "execution_surface": "deterministic_scan_and_thunderomlx_semantic",
        },
    )

    request = {
        "repo_path": str(repo),
        "pane_target": "0",
        "skill_command": f"/understand --language zh {repo}",
        "skill_command_template": "/understand --language {language} {repo_path}",
        "semantic_backend": "ThunderOMLX",
        "semantic_operator_id": "mini-thunderomlx-qwen36-knowledge",
        "execution_surface": "deterministic_scan_and_thunderomlx_semantic",
        "task_id": "T2",
        "pane_resolution": {"strategy": "explicit_legacy_target"},
    }
    result = uao.run_request(request, task_dir=tmp_path)
    assert result["ok"] is True
    assert result["execution_surface"] == "deterministic_scan_and_thunderomlx_semantic"
    assert result["knowledge_graph_path"].endswith("knowledge-graph.json")
    assert result["chunk_manifest_path"].endswith("chunk-manifest.json")
    assert result["resume_state_path"].endswith("resume-state.json")
    assert result["dispatch_result"]["mode"] == "local_pipeline"
    assert result["dispatch_result"]["chunks_total"] == 3
    assert (tmp_path / "understand-anything-bridge-contract.json").exists()
    assert (tmp_path / "understand-anything-result.json").exists()
    assert (tmp_path / "understand-anything-semantic-proof.json").exists()
    assert (tmp_path / "understand-anything-semantic-phase-request.json").exists()
    assert (tmp_path / "understand-anything-semantic-phase-prompt.md").exists()
    assert "Understand Anything Operator Result" in capsys.readouterr().out


def test_run_request_can_use_legacy_pane_dispatch(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    calls: list[tuple[str, str, str]] = []

    class FakeHand:
        def provision(self, *, capabilities=None, location=None):
            calls.append(("provision", ",".join(capabilities or []), str(location or "")))
            return type("Ref", (), {"location": location, "hand_id": "hand-1"})()

        def execute(self, hand_ref, command_name, input_data, *, idempotency_key, timeout_seconds=None):
            calls.append(("execute", command_name, str(input_data.get("command") or "")))
            return type(
                "Result",
                (),
                {
                    "status": uao.ResultStatus.OK,
                    "output": {"pane": hand_ref.location, "command_sent": input_data.get("command")},
                    "error": "",
                },
            )()

    monkeypatch.setattr(uao, "PaneHand", lambda: FakeHand())
    monkeypatch.setattr(uao, "_ensure_semantic_backend_ready", lambda request, task_dir: None)
    monkeypatch.setattr(uao.ofc, "current_block_state", lambda operator_id, allow_unregistered=True: None)
    request = {
        "repo_path": str(repo),
        "pane_target": "0",
        "skill_command": f"/understand --language zh {repo}",
        "skill_command_template": "/understand --language {language} {repo_path}",
        "semantic_backend": "ThunderOMLX",
        "semantic_operator_id": "mini-thunderomlx-qwen36-knowledge",
        "execution_surface": "tui_pane_skill_command",
        "task_id": "T2-legacy",
        "pane_resolution": {"strategy": "explicit_legacy_target"},
    }
    result = uao.run_request(request, task_dir=tmp_path)
    assert result["ok"] is True
    assert calls[0] == ("provision", "skill.understand-anything,tmux.send-keys", "0")
    assert calls[1] == ("execute", "understand_anything", f"/understand --language zh {repo}")


def test_main_applies_success_cooldown(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    envelope = {
        "task_id": "T3",
        "operator_id": "mini-understand-anything-pane-bridge",
        "repo_path": str(repo),
        "runtime_preferences": {"semantic_backend": "ThunderOMLX"},
    }
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    monkeypatch.setenv("SOLAR_OPERATOR_ENVELOPE_JSON", str(envelope_path))
    monkeypatch.setenv("TASK_DIR", str(tmp_path / "task"))
    monkeypatch.setenv("SOLAR_UNDERSTAND_ANYTHING_SUCCESS_COOLDOWN_SECONDS", "456")
    monkeypatch.setattr(uao.ofc, "ensure_operator_available", lambda operator_id: None)
    monkeypatch.setattr(uao, "run_request", lambda request, task_dir: {"ok": True})
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        uao.ofc,
        "apply_success_cooldown",
        lambda operator_id, *, success_cooldown_seconds: calls.append((operator_id, success_cooldown_seconds)) or {},
    )
    assert uao.main() == 0
    assert calls == [("mini-understand-anything-pane-bridge", 456)]
