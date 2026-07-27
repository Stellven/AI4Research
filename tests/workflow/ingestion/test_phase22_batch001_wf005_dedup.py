"""Executable Phase 22 atomic tests for Workflow / Ingestion / Deduplication."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[3]
CONSUMER_PATH = REPO_ROOT / "harness" / "lib" / "intent_consumer.py"
if str(CONSUMER_PATH.parent) not in sys.path:
    sys.path.insert(0, str(CONSUMER_PATH.parent))


def _load_intent_consumer_module(tmp_path: Path, monkeypatch) -> object:
    monkeypatch.setenv("SOLAR_HARNESS_DIR", str(REPO_ROOT / "harness"))
    monkeypatch.setenv("SOLAR_INTENT_GATEWAY_DIR", str(tmp_path / "intents"))
    monkeypatch.setenv("SOLAR_HARNESS_SPRINTS_DIR", str(tmp_path / "sprints"))
    monkeypatch.setenv("SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT", str(tmp_path / "workspace"))

    module_name = "wf005_phase22_intent_consumer"
    spec = importlib.util.spec_from_file_location(module_name, str(CONSUMER_PATH))
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load intent_consumer module for WF005 tests")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_intent_bundle(base: Path, intent_id: str) -> None:
    raw = {
        "schema_version": "solar.raw_intent.v1",
        "intent_id": intent_id,
        "source": {
            "channel": "cli",
            "actor": "workflow",
            "thread_ref": "wf005-02",
        },
        "raw": {
            "text": "Reuse the same intake intent ID for duplicate detection.",
        },
    }
    rewritten = {
        "schema_version": "solar.rewritten_intent.v1",
        "intent_id": intent_id,
        "title": "WF005 Same-ID Replay",
        "objective": "Verify same intent IDs are replay-safe.",
        "problem": "The consumer should keep existing outcomes for already consumed intent IDs.",
    }
    requirement_ir = {
        "schema_version": "solar.requirement_ir.v1",
        "intent_id": intent_id,
        "source_inputs": {},
        "objective": rewritten["objective"],
        "title": rewritten["title"],
        "constraints": [],
        "acceptance": [],
    }
    base.mkdir(parents=True, exist_ok=True)
    (base / "raw_intent.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    (base / "rewritten_intent.json").write_text(json.dumps(rewritten, ensure_ascii=False, indent=2), encoding="utf-8")
    (base / "requirement_ir.json").write_text(json.dumps(requirement_ir, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_fake_subprocess_run(calls: list[tuple[tuple[str, ...], int]]) -> Any:
    def _fake_subprocess_run(cmd: Sequence[object], *args: Any, **kwargs: Any) -> CompletedProcess[str]:
        command = tuple(str(part) for part in cmd)
        calls.append((command, len(command)))
        if any(str(part).endswith("pm_dispatch.py") for part in command):
            if "compile-request" in command:
                return CompletedProcess(command, 0, stdout="compiled", stderr="")
            return CompletedProcess(command, 0, stdout="ok", stderr="")
        if any(str(part).endswith("intent_gateway.py") for part in command):
            return CompletedProcess(command, 0, stdout="{\n  \"ok\": true,\n}", stderr="")
        return CompletedProcess(command, 0, stdout="", stderr="")

    return _fake_subprocess_run


def test_wf005_02_same_id_replay_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    consumer = _load_intent_consumer_module(tmp_path, monkeypatch)
    intent_id = "intent-phase22-wf005-02"
    _write_intent_bundle(consumer.INTENTS_DIR / intent_id, intent_id)

    calls: list[tuple[tuple[str, ...], int]] = []
    monkeypatch.setattr(consumer.subprocess, "run", _build_fake_subprocess_run(calls))

    first = consumer.consume_one(intent_id, dry_run=False)
    second = consumer.consume_one(intent_id, dry_run=False)

    assert first["status"] == "consumed"
    assert second["status"] == "already_consumed"
    assert second["sprint_id"] == first["sprint_id"]
    assert second["ok"] is True
    assert len(calls) == 2
    compile_calls = [invocation for invocation, _ in calls if "pm_dispatch.py" in invocation]
    bind_calls = [invocation for invocation, _ in calls if "intent_gateway.py" in invocation]
    assert len(compile_calls) == 1
    assert len(bind_calls) == 1

    compile_cmd = compile_calls[0]
    bind_cmd = bind_calls[0]
    assert compile_cmd[0] == sys.executable and "compile-request" in compile_cmd
    assert bind_cmd[0] == sys.executable and bind_cmd[1].endswith("intent_gateway.py")
