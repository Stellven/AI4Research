import copy
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
METADATA_ROOT = ROOT / "harness" / "metadata"
RAW_INTENT_EXAMPLE = (
    METADATA_ROOT / "1-input normalizer output" / "raw_intent" / "raw_intent.json"
)
INTENT_IR_EXAMPLE = (
    METADATA_ROOT / "2-intent compiler output" / "intent_ir" / "intent_ir.json"
)
LIB = ROOT / "harness" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import intent_compiler as compiler


def _raw() -> dict:
    return json.loads(RAW_INTENT_EXAMPLE.read_text())


def _intent() -> dict:
    payload = json.loads(INTENT_IR_EXAMPLE.read_text())
    payload["generation"] = 0
    payload["producer"] = {"method": "model", "provider": "codex", "model": "test-model"}
    return payload


def _validation(intent: dict, status: str = "pass") -> dict:
    return {
        "schema_version": "solar.intent_validation.v1",
        "validation_id": "validation-test",
        "intent_ir_ref": {
            "intent_ir_id": intent["intent_ir_id"],
            "generation": intent["generation"],
            "sha256": compiler.sha256_payload(intent),
        },
        "status": status,
        "errors": [] if status != "fail" else [{"repairable": False}],
        "warnings": [],
    }


def _fidelity(intent: dict, status: str = "pass") -> dict:
    return {
        "schema_version": "solar.intent_fidelity.v1",
        "fidelity_id": "fidelity-test",
        "intent_ir_ref": {
            "intent_ir_id": intent["intent_ir_id"],
            "generation": intent["generation"],
            "sha256": compiler.sha256_payload(intent),
        },
        "status": status,
        "errors": [] if status != "fail" else [{"repairable": False}],
        "warnings": [{"code": "STYLE_ONLY"}] if status == "pass_with_warnings" else [],
    }


def test_existing_metadata_contract_validates_mechanically() -> None:
    raw = compiler.normalize_input(_raw())
    result = compiler.validate_intent(raw, _intent(), generation=0)

    assert result["status"] == "pass"
    assert result["errors"] == []
    assert len(result["checks"]) == 7


def test_codex_schema_projection_preserves_strict_source_schema() -> None:
    source = json.loads(compiler.SEMANTIC_SCHEMA.read_text(encoding="utf-8"))
    projected = compiler.codex_compatible_schema(source)
    serialized = json.dumps(projected)

    assert "prefixItems" not in serialized
    assert "uniqueItems" not in serialized
    assert '"items": false' not in serialized
    assert "prefixItems" in json.dumps(source)
    assert "uniqueItems" in json.dumps(source)


def test_codex_model_uses_absolute_managed_paths_with_relative_work_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(command, **kwargs):
        schema_path = Path(command[command.index("--output-schema") + 1])
        output_path = Path(command[command.index("--output-last-message") + 1])
        assert schema_path.is_absolute()
        assert output_path.is_absolute()
        assert Path(kwargs["cwd"]).is_absolute()
        output_path.write_text('{"ok": true}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(compiler.subprocess, "run", fake_run)
    model = compiler.CodexJsonModel(model="test-model")
    source_path = tmp_path / "path-test.schema.json"
    source_path.write_text(json.dumps({
        "type": "object", "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"], "additionalProperties": False,
    }), encoding="utf-8")

    result = model.generate(
        "Return JSON.",
        source_path,
        Path("relative") / "model-call",
    )

    assert result == {"ok": True}


def test_current_gateway_raw_intent_normalizes_without_losing_identity() -> None:
    raw = {
        "schema_version": "solar.raw_intent.v1",
        "intent_id": "intent-current-gateway",
        "source": {"channel": "dashboard", "actor": "user"},
        "raw": {
            "text": "Explain Raft consensus simply.",
            "received_at": "2026-08-25T12:00:00Z",
            "attachments": [],
        },
    }

    normalized = compiler.normalize_input(raw)

    assert normalized["schema_version"] == "solar.raw_intent.v2"
    assert normalized["raw_intent_id"] == "intent-current-gateway"
    assert normalized["source"] == {"channel": "dashboard", "actor_ref": "user"}
    assert normalized["raw"]["sha256"] == compiler.sha256_text(raw["raw"]["text"])


def test_current_gateway_context_references_survive_normalization() -> None:
    raw = {
        "intent_id": "intent-with-context",
        "source": {
            "channel": "dashboard",
            "actor": "user",
            "session_id": "session-7",
            "thread_ref": "thread-9",
        },
        "raw": {"text": "Use the second proposal and prepare a plan."},
        "context": {"related_sprints": ["sprint-3", "sprint-3"]},
    }

    normalized = compiler.normalize_input(raw)

    assert normalized["context_refs"] == [
        "session:session-7",
        "thread:thread-9",
        "sprint:sprint-3",
    ]


def test_validator_rejects_bad_spans_duplicates_and_unknown_references() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["goals"][1]["goal_id"] = intent["goals"][0]["goal_id"]
    intent["goals"][0]["source_spans"] = [[0, len(raw["raw"]["text"]) + 1]]
    intent["unknowns"][0]["derived_from"] = ["missing-id"]
    intent["constraints"][0]["expression"] = {"unknown_ref": "U999"}

    result = compiler.validate_intent(raw, intent, generation=0)
    codes = {row["code"] for row in result["errors"]}

    assert result["status"] == "fail"
    assert {
        "DUPLICATE_IDS",
        "INVALID_SOURCE_SPAN",
        "UNKNOWN_DERIVED_REFERENCE",
        "UNKNOWN_EXPRESSION_REFERENCE",
    }.issubset(codes)


def test_expression_language_represents_order_triggers_and_strict_comparisons() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["constraints"][0]["expression"] = {
        "op": "all_of",
        "args": [
            {
                "op": "before",
                "args": [{"ref": "user.approval"}, {"ref": "email.send"}],
            },
            {
                "op": "triggers",
                "args": [
                    {
                        "op": "greater_than",
                        "args": [{"ref": "error_rate.relative_change"}, {"literal": 5}],
                    },
                    {"ref": "deployment.rollback"},
                ],
            },
            {
                "op": "contains_none",
                "args": [
                    {"ref": "report.exposed_fields"},
                    {"set": ["customer emails"]},
                ],
            },
        ],
    }

    result = compiler.validate_intent(raw, intent, generation=0)

    assert result["status"] == "pass"


def test_validator_rejects_expression_operator_with_wrong_arity() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["constraints"][0]["expression"] = {
        "op": "before",
        "args": [{"ref": "user.approval"}],
    }

    result = compiler.validate_intent(raw, intent, generation=0)

    assert result["status"] == "fail"
    assert "INVALID_EXPRESSION_ARITY" in {row["code"] for row in result["errors"]}


def test_reviewer_cannot_override_deterministic_span_validation(tmp_path: Path) -> None:
    class Reviewer:
        provider = "codex"
        model = "test-reviewer"

        def generate(self, _prompt, _schema_path, _work_dir):
            kinds = [
                "goals_supported_by_source",
                "outcomes_supported_by_source",
                "constraints_supported_by_source",
                "no_material_omissions",
                "no_unrequested_execution",
                "ambiguity_unknown_classification",
            ]
            return {
                "checks": [{"kind": kind, "status": "warning"} for kind in kinds],
                "decisions": [],
                "errors": [],
                "warnings": [
                    {
                        "code": "SOURCE_SPAN_OUT_OF_BOUNDS",
                        "path": "intent_ir.constraints[0].source_spans",
                        "message": "The valid span is out of bounds.",
                        "source_spans": [[0, 10]],
                    }
                ],
            }

    raw = compiler.normalize_input(_raw())
    intent = _intent()

    result = compiler.review_fidelity(raw, intent, Reviewer(), tmp_path)

    assert result["status"] == "pass_with_warnings"
    assert result["errors"] == []
    assert [row["code"] for row in result["warnings"]] == [
        "REVIEWER_MECHANICAL_CLAIM_REJECTED"
    ]


def test_warnings_do_not_block_acceptance() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()

    acceptance = compiler.decide_acceptance(
        raw,
        intent,
        _validation(intent),
        _fidelity(intent, "pass_with_warnings"),
        repair_attempted=False,
    )

    assert acceptance["decision"] == "accepted"
    assert acceptance["requirement_compiler_handoff_allowed"] is True


def test_blocking_ambiguity_stops_at_clarification() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["ambiguities"] = [
        {
            "ambiguity_id": "A1",
            "question": "Should the result be a CLI or a web application?",
            "blocking": True,
            "source_spans": [[0, 10]],
        }
    ]

    acceptance = compiler.decide_acceptance(
        raw, intent, _validation(intent), _fidelity(intent), repair_attempted=False
    )

    assert acceptance["decision"] == "needs_clarification"
    assert acceptance["clarification_questions"][0]["item_id"] == "A1"
    assert acceptance["requirement_compiler_handoff_allowed"] is False


def test_rejected_conflict_fails_admission() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["conflicts"] = [
        {
            "conflict_id": "X1",
            "description": "The two requested limits cannot both hold.",
            "resolution": "reject",
            "source_spans": [[0, 10]],
            "derived_from": ["C1", "C2"],
        }
    ]

    acceptance = compiler.decide_acceptance(
        raw, intent, _validation(intent), _fidelity(intent), repair_attempted=False
    )

    assert acceptance["decision"] == "failed"
    assert acceptance["requirement_compiler_handoff_allowed"] is False


def test_only_accepted_intent_reaches_requirement_boundary() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    accepted = compiler.decide_acceptance(
        raw, intent, _validation(intent), _fidelity(intent), repair_attempted=False
    )
    receipt = compiler.requirement_handoff(intent, accepted)

    assert receipt == {
        "status": "received",
        "intent_ir_id": intent["intent_ir_id"],
        "intent_ir_sha256": compiler.sha256_payload(intent),
        "next_component": "requirement_compiler",
        "execution_started": False,
    }

    blocked = copy.deepcopy(accepted)
    blocked["decision"] = "needs_clarification"
    blocked["requirement_compiler_handoff_allowed"] = False
    try:
        compiler.requirement_handoff(intent, blocked)
    except compiler.IntentCompilerError as error:
        assert "only accepted" in str(error)
    else:
        raise AssertionError("blocked intent reached Requirement Compiler boundary")

    wrong_intent = copy.deepcopy(intent)
    wrong_intent["goals"][0]["statement"] = "Different accepted content"
    try:
        compiler.requirement_handoff(wrong_intent, accepted)
    except compiler.IntentCompilerError as error:
        assert "does not match" in str(error)
    else:
        raise AssertionError("mismatched IntentIR reached Requirement Compiler boundary")


def test_legacy_projection_is_explicit_and_hash_bound() -> None:
    intent = _intent()
    raw_text = _raw()["raw"]["text"]

    projected = compiler.project_legacy_rewritten_intent(intent, raw_text)

    assert projected["compatibility_only"] is True
    assert projected["rewrite_method"] == "intent_ir_v3_compatibility_projection"
    assert projected["intent_ir_ref"]["sha256"] == compiler.sha256_payload(intent)
    assert projected["problem"] == raw_text


def test_artifact_chain_detects_tampering(tmp_path: Path) -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    validation = _validation(intent)
    fidelity = _fidelity(intent)
    acceptance = compiler.decide_acceptance(
        raw, intent, validation, fidelity, repair_attempted=False
    )
    compiler.write_json(tmp_path / "input.json", raw)
    compiler.write_json(tmp_path / "intent_ir.json", intent)
    compiler.write_json(tmp_path / "intent_validation.json", validation)
    compiler.write_json(tmp_path / "intent_fidelity.json", fidelity)
    compiler.write_json(tmp_path / "intent_acceptance.json", acceptance)

    assert compiler.verify_artifact_chain(tmp_path) == []

    intent["goals"][0]["statement"] = "Tampered after acceptance"
    compiler.write_json(tmp_path / "intent_ir.json", intent)
    errors = compiler.verify_artifact_chain(tmp_path)
    assert "acceptance.intent_ir_ref.hash_mismatch" in errors
    assert "intent_validation.intent_ir_ref.hash_mismatch" in errors
    assert "intent_fidelity.intent_ir_ref.hash_mismatch" in errors
