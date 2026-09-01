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


def test_codex_schema_projection_infers_const_types_without_mutating_plan_schema() -> None:
    import elastic_planner as planner

    source = json.loads(planner.PLAN_BODY_SCHEMA.read_text(encoding="utf-8"))
    original = copy.deepcopy(source)
    projected = compiler.codex_compatible_schema(source)
    projected_kind = projected["$defs"]["node"]["properties"]["workspace_reads"][
        "items"
    ]["properties"]["kind"]

    assert source == original
    assert projected_kind == {"enum": ["file"], "type": "string"}


def test_codex_schema_projection_infers_all_json_const_types() -> None:
    source = {
        "type": "object",
        "additionalProperties": False,
        "required": ["boolean", "null", "string", "integer", "number"],
        "properties": {
            "boolean": {"const": True},
            "null": {"const": None},
            "string": {"const": "value"},
            "integer": {"const": 3},
            "number": {"const": 2.5},
        },
    }

    projected = compiler.codex_compatible_schema(source)

    assert {
        key: value["type"] for key, value in projected["properties"].items()
    } == {
        "boolean": "boolean",
        "null": "null",
        "string": "string",
        "integer": "integer",
        "number": "number",
    }


def test_codex_model_uses_absolute_managed_paths_with_relative_work_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(command, **kwargs):
        assert "--json" in command
        schema_path = Path(command[command.index("--output-schema") + 1])
        output_path = Path(command[command.index("--output-last-message") + 1])
        assert schema_path.is_absolute()
        assert output_path.is_absolute()
        assert Path(kwargs["cwd"]).is_absolute()
        output_path.write_text('{"ok": true}', encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"type":"thread.started"}\n{"type":"turn.started"}\n'
            '{"type":"turn.completed"}\n',
            stderr="",
        )

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
    receipt = json.loads(
        (tmp_path / "relative" / "model-call" / "model_call_receipt.json").read_text()
    )
    assert receipt["status"] == "succeeded"
    assert receipt["exit_code"] == 0
    assert receipt["error"] is None


def test_codex_model_persists_typed_schema_failure_without_prompt_or_raw_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    secret_prompt = "Return JSON. secret-token-must-not-persist"
    provider_output = "\n".join(
        [
            '{"type":"thread.started"}',
            '{"type":"turn.started"}',
            '{"type":"error","message":"400 invalid_json_schema: missing type"}',
            '{"type":"turn.failed","error":{"message":"invalid_json_schema"}}',
        ]
    )

    def fake_run(command, **_kwargs):
        assert "--json" in command
        return subprocess.CompletedProcess(command, 1, stdout=provider_output, stderr="sensitive")

    monkeypatch.setattr(compiler.subprocess, "run", fake_run)
    model = compiler.CodexJsonModel(model="test-model")
    work_dir = tmp_path / "failed-model-call"

    try:
        model.generate(secret_prompt, compiler.SEMANTIC_SCHEMA, work_dir)
    except compiler.IntentCompilerError as error:
        assert "[invalid_json_schema]" in str(error)
    else:
        raise AssertionError("provider schema rejection did not fail")

    receipt_text = (work_dir / "model_call_receipt.json").read_text()
    receipt = json.loads(receipt_text)
    assert receipt["status"] == "failed"
    assert receipt["exit_code"] == 1
    assert receipt["error"] == {
        "code": "invalid_json_schema",
        "detail": "Provider rejected the supplied output JSON schema.",
    }
    assert secret_prompt not in receipt_text
    assert provider_output not in receipt_text
    assert "sensitive" not in receipt_text


def test_codex_model_fails_closed_on_malformed_provider_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout='{"type":"thread.started"}\nnot-json\n{"type":"turn.failed"}',
            stderr="",
        )

    monkeypatch.setattr(compiler.subprocess, "run", fake_run)
    model = compiler.CodexJsonModel(model="test-model")
    work_dir = tmp_path / "malformed-events"

    try:
        model.generate("Return JSON.", compiler.SEMANTIC_SCHEMA, work_dir)
    except compiler.IntentCompilerError as error:
        assert "[malformed_provider_events]" in str(error)
    else:
        raise AssertionError("malformed provider events did not fail closed")

    receipt = json.loads((work_dir / "model_call_receipt.json").read_text())
    assert receipt["error"]["code"] == "malformed_provider_events"
    assert receipt["provider_events"]["complete"] is False


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


def test_r13_validator_rejects_all_undefined_outcome_aliases_in_generation_zero() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["outcomes"].append(
        {
            "outcome_id": "D3",
            "class": "artifact",
            "description": "A third requested artifact.",
            "source_spans": [[0, 10]],
        }
    )
    intent["constraints"][0]["expression"] = {
        "op": "all_of",
        "args": [
            {"ref": "O1"},
            {"op": "implies", "args": [{"ref": "O2"}, {"ref": "D3"}]},
        ],
    }

    result = compiler.validate_intent(raw, intent, generation=0)

    reference_errors = [
        error
        for error in result["errors"]
        if error["code"] == "UNKNOWN_EXPRESSION_REFERENCE"
    ]
    assert result["status"] == "fail"
    assert [(error["path"], error["message"]) for error in reference_errors] == [
        ("constraints.0.expression.args.0.ref", "Unknown ref: O1"),
        ("constraints.0.expression.args.1.args.0.ref", "Unknown ref: O2"),
    ]
    assert all(error["repairable"] is True for error in reference_errors)


def test_validator_recursively_checks_nested_typed_expression_references() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["constraints"][0]["expression"] = {
        "op": "all_of",
        "args": [
            {"ref": "O7.content"},
            {
                "op": "implies",
                "args": [{"unknown_ref": "U999"}, {"ref": "D9.content"}],
            },
        ],
    }

    result = compiler.validate_intent(raw, intent, generation=0)

    assert [
        error["path"]
        for error in result["errors"]
        if error["code"] == "UNKNOWN_EXPRESSION_REFERENCE"
    ] == [
        "constraints.0.expression.args.0.ref",
        "constraints.0.expression.args.1.args.0.unknown_ref",
        "constraints.0.expression.args.1.args.1.ref",
    ]


def test_validator_accepts_nested_goal_outcome_constraint_and_unknown_references() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["constraints"][0]["expression"] = {
        "op": "all_of",
        "args": [
            {"ref": "G1"},
            {"op": "implies", "args": [{"ref": "C2"}, {"ref": "D1"}]},
            {"unknown_ref": "U1"},
        ],
    }

    result = compiler.validate_intent(raw, intent, generation=0)

    assert result["status"] == "pass"
    assert result["errors"] == []


def test_validator_rejects_unknown_id_through_ordinary_ref() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["constraints"][0]["expression"] = {"ref": "U1"}

    result = compiler.validate_intent(raw, intent, generation=0)

    assert result["status"] == "fail"
    assert any(
        error["code"] == "UNKNOWN_EXPRESSION_REFERENCE"
        and error["path"] == "constraints.0.expression.ref"
        for error in result["errors"]
    )


def test_validator_fails_closed_for_malformed_semantic_collection_shapes() -> None:
    raw = compiler.normalize_input(_raw())
    malformed_values = (
        ("goals", None),
        ("outcomes", {"outcome_id": "D1"}),
        ("constraints", 7),
        ("unknowns", "U1"),
        ("constraints", [{"constraint_id": "C1", "expression": 7}]),
    )

    for field, value in malformed_values:
        intent = _intent()
        intent[field] = value
        result = compiler.validate_intent(raw, intent, generation=0)
        assert result["status"] == "fail", (field, value)
        assert "SCHEMA_INVALID" in {error["code"] for error in result["errors"]}


def test_validator_preserves_symbolic_data_path_references() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["constraints"][0]["expression"] = {
        "op": "all_of",
        "args": [
            {"ref": "selected_databases"},
            {"ref": "D1.content"},
            {"ref": "experiment.task_set"},
            {"ref": "requested_deliverable.content"},
            {"ref": "user.approval"},
        ],
    }

    result = compiler.validate_intent(raw, intent, generation=0)

    assert result["status"] == "pass"
    assert result["errors"] == []


def test_validator_rejects_plain_count_that_drops_distinctness() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["constraints"][0]["statement"] = "Compare at least four distinct approaches."
    intent["constraints"][0]["expression"] = {
        "op": "at_least",
        "args": [
            {"ref": "workflow.approaches.count"},
            {"literal": 4},
        ],
    }

    result = compiler.validate_intent(raw, intent, generation=0)

    assert result["status"] == "fail"
    assert any(
        error["code"] == "DISTINCT_CARDINALITY_NOT_REPRESENTABLE"
        and error["path"] == "constraints.0.expression"
        for error in result["errors"]
    )


def test_validator_accepts_literal_distinct_cardinality_condition() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["constraints"][0]["statement"] = "Compare at least four distinct approaches."
    intent["constraints"][0]["expression"] = {
        "literal": "Compare at least four distinct approaches"
    }

    result = compiler.validate_intent(raw, intent, generation=0)

    assert result["status"] == "pass"
    assert result["errors"] == []


def test_pipeline_bundles_reference_and_fidelity_defects_into_its_single_repair(
    tmp_path: Path,
) -> None:
    semantic_keys = ("goals", "outcomes", "constraints", "ambiguities", "conflicts", "unknowns")
    initial = {key: copy.deepcopy(_intent()[key]) for key in semantic_keys}
    repaired = copy.deepcopy(initial)
    initial["constraints"][0]["expression"] = {
        "op": "all_of",
        "args": [{"ref": "O1"}, {"ref": "O2"}],
    }
    repaired["constraints"][0]["expression"] = {
        "op": "all_of",
        "args": [{"ref": "D1"}, {"ref": "D2"}],
    }

    class CompilerModel:
        provider = "codex"
        model = "test-compiler"

        def __init__(self):
            self.prompts = []

        def generate(self, prompt, _schema_path, _work_dir):
            self.prompts.append(json.loads(prompt))
            return copy.deepcopy(initial if len(self.prompts) == 1 else repaired)

    class ReviewerModel:
        provider = "codex"
        model = "test-reviewer"

        def generate(self, prompt, _schema_path, _work_dir):
            generation = json.loads(prompt)["intent_ir"]["generation"]
            kinds = [
                "goals_supported_by_source",
                "outcomes_supported_by_source",
                "constraints_supported_by_source",
                "no_material_omissions",
                "no_unrequested_execution",
                "ambiguity_unknown_classification",
            ]
            error = {
                "code": "OVER_RESTRICTIVE_SCOPE",
                "path": "constraints.0",
                "message": "The constraint narrows the requested scope.",
                "source_spans": [[0, 10]],
                "repairable": True,
                "required_change": "Preserve the requested scope.",
            }
            return {
                "checks": [
                    {
                        "kind": kind,
                        "status": (
                            "fail"
                            if generation == 0 and kind == "constraints_supported_by_source"
                            else "pass"
                        ),
                    }
                    for kind in kinds
                ],
                "decisions": [],
                "errors": [error] if generation == 0 else [],
                "warnings": [],
            }

    compiler_model = CompilerModel()
    result = compiler.run_pipeline(_raw(), tmp_path / "run", compiler_model, ReviewerModel())

    repair_defects = compiler_model.prompts[1]["defects"]
    generation_zero_fidelity = json.loads(
        (tmp_path / "run" / "generation-0" / "intent_fidelity.json").read_text()
    )
    repair_record = json.loads((tmp_path / "run" / "repair_record.json").read_text())
    assert result["intent_acceptance"]["decision"] == "accepted"
    assert result["intent_acceptance"]["repair"] == {
        "attempted": True,
        "maximum_attempts": 1,
    }
    assert [error["message"] for error in repair_defects[:2]] == [
        "Unknown ref: O1",
        "Unknown ref: O2",
    ]
    assert any(error["code"] == "OVER_RESTRICTIVE_SCOPE" for error in repair_defects)
    assert [
        check["kind"]
        for check in generation_zero_fidelity["checks"]
        if check["status"] == "fail"
    ] == ["constraints_supported_by_source"]
    assert {
        error["code"] for error in repair_record["defects"]
    } == {"UNKNOWN_EXPRESSION_REFERENCE", "OVER_RESTRICTIVE_SCOPE"}


def test_compiler_owned_identity_wins_and_model_overwrite_gets_one_repair(
    tmp_path: Path,
) -> None:
    semantic_keys = ("goals", "outcomes", "constraints", "ambiguities", "conflicts", "unknowns")
    valid = {key: copy.deepcopy(_intent()[key]) for key in semantic_keys}
    forged = {
        **copy.deepcopy(valid),
        "generation": 99,
        "raw_intent_ref": {"raw_intent_id": "forged", "raw_text_sha256": "0" * 64},
    }

    class CompilerModel:
        provider = "codex"
        model = "test-compiler"

        def __init__(self):
            self.calls = 0

        def generate(self, _prompt, _schema_path, _work_dir):
            self.calls += 1
            return copy.deepcopy(forged if self.calls == 1 else valid)

    class ReviewerModel:
        provider = "codex"
        model = "test-reviewer"

        def __init__(self):
            self.calls = 0

        def generate(self, prompt, _schema_path, _work_dir):
            self.calls += 1
            assert json.loads(prompt)["intent_ir"]["generation"] == 1
            kinds = [
                "goals_supported_by_source",
                "outcomes_supported_by_source",
                "constraints_supported_by_source",
                "no_material_omissions",
                "no_unrequested_execution",
                "ambiguity_unknown_classification",
            ]
            return {
                "checks": [{"kind": kind, "status": "pass"} for kind in kinds],
                "decisions": [],
                "errors": [],
                "warnings": [],
            }

    compiler_model = CompilerModel()
    reviewer_model = ReviewerModel()
    result = compiler.run_pipeline(_raw(), tmp_path / "run", compiler_model, reviewer_model)
    generation_zero = json.loads(
        (tmp_path / "run" / "generation-0" / "intent_ir.json").read_text()
    )
    generation_zero_validation = json.loads(
        (tmp_path / "run" / "generation-0" / "intent_validation.json").read_text()
    )

    assert generation_zero["generation"] == 0
    assert generation_zero["raw_intent_ref"]["raw_intent_id"] == _raw()["raw_intent_id"]
    assert "SCHEMA_INVALID" in {
        error["code"] for error in generation_zero_validation["errors"]
    }
    assert compiler_model.calls == 2
    assert reviewer_model.calls == 1
    assert result["intent_acceptance"]["decision"] == "accepted"


def test_malformed_semantic_body_exhausts_one_repair_without_reviewer_or_exception(
    tmp_path: Path,
) -> None:
    class CompilerModel:
        provider = "codex"
        model = "test-compiler"

        def __init__(self):
            self.calls = 0

        def generate(self, _prompt, _schema_path, _work_dir):
            self.calls += 1
            return {
                "goals": None,
                "outcomes": {"outcome_id": "D1"},
                "constraints": 7,
                "ambiguities": None,
                "conflicts": "not-a-list",
                "unknowns": {"unknown_id": "U1"},
                "raw_intent_ref": "forged-model-authority",
            }

    class ReviewerModel:
        provider = "codex"
        model = "test-reviewer"

        def __init__(self):
            self.calls = 0

        def generate(self, _prompt, _schema_path, _work_dir):
            self.calls += 1
            raise AssertionError("schema-invalid candidate reached semantic reviewer")

    compiler_model = CompilerModel()
    reviewer_model = ReviewerModel()
    result = compiler.run_pipeline(_raw(), tmp_path / "run", compiler_model, reviewer_model)
    repair_record = json.loads((tmp_path / "run" / "repair_record.json").read_text())

    assert compiler_model.calls == 2
    assert reviewer_model.calls == 0
    assert result["intent_acceptance"]["decision"] == "failed"
    assert result["intent_acceptance"]["repair"] == {
        "attempted": True,
        "maximum_attempts": 1,
    }
    assert {error["code"] for error in repair_record["defects"]} == {"SCHEMA_INVALID"}


def test_validator_handles_malformed_raw_intent_reference_as_schema_failure() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["raw_intent_ref"] = "forged"

    result = compiler.validate_intent(raw, intent, generation=0)

    assert result["status"] == "fail"
    assert {error["code"] for error in result["errors"]} >= {
        "SCHEMA_INVALID",
        "RAW_INTENT_REFERENCE_MISMATCH",
    }


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


def test_r17_validator_rejects_scalar_contains_all_right_operand() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["constraints"][0]["expression"] = {
        "op": "contains_all",
        "args": [
            {"ref": "D1"},
            {"literal": "reproducible evaluation recommendation"},
        ],
    }

    result = compiler.validate_intent(raw, intent, generation=0)

    defect = next(
        row
        for row in result["errors"]
        if row["code"] == "INVALID_EXPRESSION_OPERAND_SHAPE"
    )
    assert result["status"] == "fail"
    assert defect["path"] == "constraints.0.expression.args.1"
    assert defect["repairable"] is True
    assert "['set']" in defect["message"]
    assert "'literal'" in defect["message"]


def test_contains_operators_accept_collection_right_operand() -> None:
    raw = compiler.normalize_input(_raw())
    for operator in ("contains_all", "contains_any", "contains_none"):
        intent = _intent()
        intent["constraints"][0]["expression"] = {
            "op": operator,
            "args": [
                {"ref": "D1.content"},
                {"set": ["reproducible evaluation recommendation"]},
            ],
        }

        result = compiler.validate_intent(raw, intent, generation=0)

        assert result["status"] == "pass", (operator, result["errors"])


def test_contains_operators_reject_non_collection_right_operand_shapes() -> None:
    raw = compiler.normalize_input(_raw())
    wrong_operands = [
        {"literal": "one item"},
        {"ref": "D1.content"},
        {"unknown_ref": "U1"},
        {"op": "equals", "args": [{"literal": 1}, {"literal": 1}]},
    ]
    for operator in ("contains_all", "contains_any", "contains_none"):
        for wrong_operand in wrong_operands:
            intent = _intent()
            intent["constraints"][0]["expression"] = {
                "op": operator,
                "args": [{"ref": "D1.content"}, wrong_operand],
            }

            result = compiler.validate_intent(raw, intent, generation=0)

            assert "INVALID_EXPRESSION_OPERAND_SHAPE" in {
                row["code"] for row in result["errors"]
            }, (operator, wrong_operand, result["errors"])


def test_operator_contract_table_covers_every_schema_operator() -> None:
    schema = json.loads(compiler.SEMANTIC_SCHEMA.read_text(encoding="utf-8"))
    expression_variants = schema["$defs"]["expression"]["oneOf"]
    operator_variant = next(
        row for row in expression_variants if "op" in row.get("required", [])
    )
    schema_operators = set(operator_variant["properties"]["op"]["enum"])

    assert set(compiler._OPERATOR_CONTRACTS) == schema_operators
    for operator, contract in compiler._OPERATOR_CONTRACTS.items():
        assert "arity" in contract, operator
        assert "positional_shapes" in contract, operator


def test_compiler_prompt_and_schema_explain_contains_collection_contract() -> None:
    raw = compiler.normalize_input(_raw())
    prompt = json.loads(
        compiler._compiler_prompt(raw, generation=0, previous=None, defects=[])
    )
    schema = json.loads(compiler.SEMANTIC_SCHEMA.read_text(encoding="utf-8"))

    assert 'right operand must be {"set": [...]}' in prompt["instruction"]
    assert "second arg must be a set expression" in schema["$defs"]["expression"][
        "description"
    ]


def test_validator_rejects_expression_operator_with_wrong_arity() -> None:
    raw = compiler.normalize_input(_raw())
    intent = _intent()
    intent["constraints"][0]["expression"] = {
        "op": "before",
        "args": [{"ref": "G1"}],
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
