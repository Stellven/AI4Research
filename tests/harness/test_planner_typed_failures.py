"""Typed Planner failures, retained-call replay, and shared deadline."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "harness" / "lib"
for value in (LIB,):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import intent_compiler  # noqa: E402
import planner_failure  # noqa: E402
import planner_replay  # noqa: E402


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def _receipt(status: str, error: dict | None = None) -> dict:
    return {
        "schema_version": "solar.model_call_receipt.v1",
        "provider": "codex",
        "model": "configured_default",
        "status": status,
        "exit_code": 0 if status == "succeeded" else None,
        "duration_ms": 1.0,
        "provider_events": {
            "complete": True,
            "event_count": 1,
            "terminal_event_type": "turn.completed",
        },
        "error": error,
    }


def test_failed_model_call_receipt_becomes_typed_stage_and_code(tmp_path: Path) -> None:
    root = tmp_path / "elastic-planner"
    _write(
        root
        / "execution"
        / "composition-generation-1"
        / "composition_selection_call"
        / "model_call_receipt.json",
        _receipt(
            "failed",
            {
                "code": "provider_timeout",
                "detail": "Provider call exceeded the 240s timeout.",
            },
        ),
    )

    failure = planner_failure.summarize_planner_failure(root)

    assert failure is not None
    assert failure["stage"] == "composition_selection"
    assert failure["code"] == "provider_timeout"
    assert failure["retry_safe"] is True
    assert failure["before_execution"] is True
    assert failure["receipt_ref"].endswith("model_call_receipt.json")


def test_reviewer_rejection_becomes_typed_named_node_failure(tmp_path: Path) -> None:
    root = tmp_path / "elastic-planner"
    _write(
        root / "semantic" / "plan_acceptance.json",
        {"decision": "failed", "reasons": ["Independent plan fidelity failed."]},
    )
    _write(
        root / "semantic" / "plan_fidelity.json",
        {
            "status": "fail",
            "errors": [
                {
                    "code": "DISCOVERY_REQUIREMENT_COVERAGE_OMITTED",
                    "message": "Discovery omitted R15.",
                    "path": "plan_ir.nodes[literature_discovery]",
                }
            ],
        },
    )

    failure = planner_failure.summarize_planner_failure(root)

    assert failure is not None
    assert failure["stage"] == "fidelity"
    assert failure["code"] == "DISCOVERY_REQUIREMENT_COVERAGE_OMITTED"
    assert failure["node_id"] == "literature_discovery"
    assert failure["retry_safe"] is False


def test_ensure_prefers_retained_evidence_and_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "elastic-planner"
    _write(
        root / "semantic" / "generation-0" / "plan_call" / "model_call_receipt.json",
        _receipt("failed", {"code": "provider_quota", "detail": "quota"}),
    )

    first = planner_failure.ensure_planner_failure(
        root,
        fallback_stage="operator",
        fallback_code="operator_timeout",
    )
    second = planner_failure.ensure_planner_failure(
        root,
        fallback_stage="operator",
        fallback_code="planner_exit_1",
    )

    assert first["code"] == "provider_quota"
    assert first["stage"] == "plan"
    assert second == first
    assert planner_failure.read_planner_failure(root) == first


def test_newer_deterministic_rejection_replaces_stale_provider_failure(tmp_path: Path) -> None:
    root = tmp_path / "elastic-planner"
    _write(
        root / "semantic" / "generation-0" / "fidelity_call" / "model_call_receipt.json",
        _receipt("failed", {"code": "provider_quota", "detail": "old quota"}),
    )
    first = planner_failure.ensure_planner_failure(
        root,
        fallback_stage="operator",
        fallback_code="planner_exit_1",
    )
    assert first["code"] == "provider_quota"

    time.sleep(0.01)
    _write(
        root / "semantic" / "plan_acceptance.json",
        {"decision": "failed", "reasons": ["Current deterministic plan rejection."]},
    )
    _write(
        root / "semantic" / "plan_fidelity.json",
        {
            "status": "fail",
            "errors": [
                {
                    "code": "REPAIR_DEPENDENCY_WEAKENED",
                    "message": "Current repair removed a required dependency.",
                    "path": "plan_ir.nodes[experiment_run]",
                }
            ],
        },
    )

    current = planner_failure.ensure_planner_failure(
        root,
        fallback_stage="operator",
        fallback_code="planner_exit_1",
    )

    assert current["code"] == "REPAIR_DEPENDENCY_WEAKENED"
    assert current["stage"] == "fidelity"
    assert current["node_id"] == "experiment_run"
    assert current["retry_safe"] is False
    assert planner_failure.read_planner_failure(root) == current


def _retained_call(
    root: Path,
    relative: str,
    *,
    output: dict | None,
    error: dict | None = None,
) -> None:
    call_dir = root / relative
    _write(call_dir / "model_output.schema.json", {"type": "object"})
    if output is not None:
        _write(call_dir / "model_output.json", output)
        _write(call_dir / "model_call_receipt.json", _receipt("succeeded"))
    else:
        _write(call_dir / "model_call_receipt.json", _receipt("failed", error))


def test_replay_answers_success_failure_and_miss_from_retained_run(
    tmp_path: Path,
) -> None:
    retained = tmp_path / "retained"
    _retained_call(
        retained,
        "semantic/generation-0/plan_call",
        output={"decision": "generate"},
    )
    _retained_call(
        retained,
        "semantic/generation-1/plan_call",
        output=None,
        error={"code": "provider_timeout", "detail": "240s"},
    )
    output_root = tmp_path / "out"
    model = planner_replay.ReplayJsonModel(
        replay_root=retained,
        output_root=output_root,
    )
    schema = _write(tmp_path / "schema.json", {"type": "object"})

    answer = model.generate(
        "prompt",
        schema,
        output_root / "semantic" / "generation-0" / "plan_call",
    )
    assert answer == {"decision": "generate"}
    with pytest.raises(intent_compiler.IntentCompilerError, match=r"\[provider_timeout\]"):
        model.generate(
            "prompt",
            schema,
            output_root / "semantic" / "generation-1" / "plan_call",
        )
    with pytest.raises(intent_compiler.IntentCompilerError, match=r"\[replay_miss\]"):
        model.generate(
            "prompt",
            schema,
            output_root / "semantic" / "generation-2" / "plan_call",
        )


def test_replay_uses_live_fallback_only_for_a_missing_retained_call(
    tmp_path: Path,
) -> None:
    retained = tmp_path / "retained"
    _retained_call(
        retained,
        "semantic/generation-0/plan_call",
        output={"decision": "generate"},
    )
    live_calls: list[str] = []

    class LiveModel:
        provider = "codex"
        model = "configured_default"

        def generate(self, prompt, schema_path, work_dir):
            live_calls.append(str(work_dir))
            return {"decision": "live-repair"}

    output_root = tmp_path / "out"
    model = planner_replay.ReplayJsonModel(
        replay_root=retained,
        output_root=output_root,
        fallback=LiveModel(),
    )
    schema = _write(tmp_path / "schema.json", {"type": "object"})

    assert model.generate(
        "prompt",
        schema,
        output_root / "semantic" / "generation-0" / "plan_call",
    ) == {"decision": "generate"}
    assert live_calls == []
    assert model.generate(
        "prompt",
        schema,
        output_root / "semantic" / "generation-2" / "plan_call",
    ) == {"decision": "live-repair"}
    assert len(live_calls) == 1
    assert model.calls[-1].endswith("(live)")


def test_model_call_refuses_to_start_past_shared_deadline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        intent_compiler.MODEL_CALL_DEADLINE_ENV,
        f"{time.time() + 2:.0f}",
    )
    launched: list[dict] = []
    monkeypatch.setattr(
        intent_compiler.subprocess,
        "run",
        lambda *args, **kwargs: launched.append(kwargs),
    )
    schema = _write(tmp_path / "schema.json", {"type": "object"})
    model = intent_compiler.CodexJsonModel(model="", timeout_seconds=240)

    with pytest.raises(
        intent_compiler.IntentCompilerError,
        match=r"\[planner_deadline_exhausted\]",
    ):
        model.generate("prompt", schema, tmp_path / "call")

    receipt = json.loads(
        (tmp_path / "call" / "model_call_receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["error"]["code"] == "planner_deadline_exhausted"
    assert launched == []


def test_model_call_timeout_is_bounded_by_shared_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        intent_compiler.MODEL_CALL_DEADLINE_ENV,
        f"{time.time() + 60:.0f}",
    )
    assert 55 <= intent_compiler.effective_call_timeout(240) <= 61
    monkeypatch.delenv(intent_compiler.MODEL_CALL_DEADLINE_ENV)
    assert intent_compiler.effective_call_timeout(240) == 240.0
