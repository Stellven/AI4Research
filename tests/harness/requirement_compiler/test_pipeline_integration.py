from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
HARNESS_LIB = REPO / "harness" / "lib"
if str(HARNESS_LIB) not in sys.path:
    sys.path.insert(0, str(HARNESS_LIB))

import intent_compiler  # noqa: E402
import intent_gateway  # noqa: E402
import requirement_compiler  # noqa: E402


FIXTURE = (
    REPO
    / "harness"
    / "metadata"
    / "2-intent compiler output"
    / "requirement-compiler-input-fixtures"
    / "21-kid-sky-and-sunset-colors"
    / "intent_ir.json"
)


def _accepted(intent_ir: dict) -> dict:
    raw_id = intent_ir["raw_intent_ref"]["raw_intent_id"]
    return {
        "schema_version": "solar.intent_acceptance.v1",
        "acceptance_id": f"intent-acceptance-{raw_id}",
        "intent_ir_ref": {
            "intent_ir_id": intent_ir["intent_ir_id"],
            "sha256": intent_compiler.sha256_payload(intent_ir),
        },
        "decision": "accepted",
        "repair": {"attempted": False, "maximum_attempts": 1},
        "clarification_questions": [],
        "requirement_compiler_handoff_allowed": True,
    }


def _install_fake_intent_pipeline(monkeypatch, intent_ir: dict) -> None:
    acceptance = _accepted(intent_ir)
    validation = {"schema_version": "solar.intent_validation.v1", "status": "pass"}
    fidelity = {"schema_version": "solar.intent_fidelity.v1", "status": "pass"}

    def fake_run_pipeline(raw, output_dir, _compiler_model, _reviewer_model):
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, payload in (
            ("input.json", raw),
            ("intent_ir.json", intent_ir),
            ("intent_validation.json", validation),
            ("intent_fidelity.json", fidelity),
            ("intent_acceptance.json", acceptance),
        ):
            intent_compiler.write_json(output_dir / name, payload)
        return {
            "input": raw,
            "intent_ir": intent_ir,
            "intent_validation": validation,
            "intent_fidelity": fidelity,
            "intent_acceptance": acceptance,
        }

    monkeypatch.setattr(intent_compiler, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(intent_compiler, "model_from_environment", lambda _role: object())


def test_semantic_gateway_uses_native_requirement_bundle_and_binds_immutably(
    tmp_path, monkeypatch, capsys
) -> None:
    intent_ir = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _install_fake_intent_pipeline(monkeypatch, intent_ir)
    monkeypatch.setenv("SOLAR_INTENT_COMPILER_PROVIDER", "test")
    intent_gateway.INTENTS_DIR = tmp_path / "intents"
    intent_gateway.SPRINTS_DIR = tmp_path / "sprints"

    result = intent_gateway.main(
        [
            "capture",
            "--text",
            "Why is the sky blue, but sunsets are orange?",
            "--intent-id",
            "intent-native-requirement",
            "--sprint-id",
            "sprint-native-requirement",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    base = intent_gateway.INTENTS_DIR / payload["intent_id"]
    requirement_path = base / "requirement_ir.json"
    evaluation_path = base / "requirement_format_evaluation.json"
    requirement = json.loads(requirement_path.read_text(encoding="utf-8"))
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    trace = json.loads((base / "requirement_trace.json").read_text(encoding="utf-8"))

    assert result == 0
    assert payload["ready"] is True
    assert payload["requirement_evaluation"] == str(evaluation_path)
    assert requirement["schema_version"] == "solar.requirement_ir.v2"
    assert evaluation["status"] == "pass"
    assert not (base / "rewritten_intent.json").exists()
    assert [row["stage"] for row in trace["stages"][-2:]] == [
        "requirement_ir_compile",
        "requirement_format_evaluation",
    ]
    assert (
        intent_gateway.SPRINTS_DIR / "sprint-native-requirement.requirement_ir.json"
    ).read_bytes() == requirement_path.read_bytes()
    assert (
        intent_gateway.SPRINTS_DIR
        / "sprint-native-requirement.requirement_format_evaluation.json"
    ).read_bytes() == evaluation_path.read_bytes()


def test_semantic_gateway_stops_before_binding_when_requirement_evaluator_fails(
    tmp_path, monkeypatch, capsys
) -> None:
    intent_ir = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _install_fake_intent_pipeline(monkeypatch, intent_ir)
    monkeypatch.setenv("SOLAR_INTENT_COMPILER_PROVIDER", "test")
    intent_gateway.INTENTS_DIR = tmp_path / "intents"
    intent_gateway.SPRINTS_DIR = tmp_path / "sprints"
    real_evaluator = requirement_compiler.evaluate_requirement_ir_format

    def failing_evaluator(*args, **kwargs):
        result = real_evaluator(*args, **kwargs)
        result["status"] = "fail"
        result["checks"][0]["status"] = "fail"
        result["defects"].append(
            {"path": "$", "code": "TEST_INJECTED_REQUIREMENT_DEFECT"}
        )
        return result

    monkeypatch.setattr(
        requirement_compiler,
        "evaluate_requirement_ir_format",
        failing_evaluator,
    )

    result = intent_gateway.main(
        [
            "capture",
            "--text",
            "Why is the sky blue, but sunsets are orange?",
            "--intent-id",
            "intent-failed-requirement-gate",
            "--sprint-id",
            "sprint-must-not-bind",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["ready"] is False
    assert payload["readiness_status"] == "requirement_evaluation_failed"
    assert not (
        intent_gateway.SPRINTS_DIR / "sprint-must-not-bind.requirement_ir.json"
    ).exists()
