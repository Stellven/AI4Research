"""Offline wire-boundary tests: these are not live model acceptance evidence."""
from __future__ import annotations

import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness/lib"))
sys.path.insert(1, str(ROOT))

import elastic_planner as planner
import intent_compiler
import model_registry
import structured_model as models
from structured_output import OutputContractError, parse_json, project_schema, validate_output


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "harness/schemas"
CALL_SCHEMAS = [
    "compiler/intent-ir.semantic.v1.schema.json",
    "compiler/intent-fidelity.review.v1.schema.json",
    "compiler/requirement-semantics.v1.schema.json",
    "compiler/requirement-semantics.v2.schema.json",
    "compiler/requirement-semantic-review.v1.schema.json",
    "compiler/requirement-semantic-review.v2.schema.json",
    "planning/planning-decision.semantic.v1.schema.json",
    "planning/plan-ir.semantic.v2.schema.json",
    "planning/plan-ir.semantic.structured.v2.schema.json",
    "planning/plan-fidelity.review.v1.schema.json",
    "planning/direct-response.semantic.v1.schema.json",
    "planning/direct-response-review.semantic.v1.schema.json",
    "planning/capsule-selection.semantic.v1.schema.json",
    "planning/capsule-fit-review.semantic.v1.schema.json",
    "planning/composition-selection.semantic.v1.schema.json",
]
REGISTRY = model_registry.load_registry()
MODEL_IDS = list(REGISTRY["models"])
SIMPLE = {"type": "object", "additionalProperties": False, "required": ["answer"],
          "properties": {"answer": {"type": "string", "minLength": 1},
                         "cpu": {"type": "number", "minimum": 0},
                         "nullable": {"type": ["string", "null"]}}}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    for key in list(models.os.environ):
        if key.startswith(("SOLAR_LLM_", "SOLAR_INTENT_", "SOLAR_REQUIREMENT_", "SOLAR_PLANNER_", "SOLAR_DIRECT_ANSWER_")):
            monkeypatch.delenv(key)
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected unmocked provider access")
    monkeypatch.setattr(models.subprocess, "run", forbidden)
    monkeypatch.setattr(models, "_post", forbidden)


def native_check(schema, *, openai):
    """Independent guard for the provider subset, including the reported defect."""
    assert not set(schema) & {"$schema", "$id", "oneOf", "prefixItems", "uniqueItems", "allOf"}
    assert "type" in schema or "$ref" in schema or "anyOf" in schema
    if "properties" in schema:
        assert schema["additionalProperties"] is False
        if openai:
            assert set(schema["required"]) == set(schema["properties"])
        for child in schema["properties"].values():
            native_check(child, openai=openai)
    for key in ("$defs", "definitions"):
        for child in schema.get(key, {}).values():
            native_check(child, openai=openai)
    for child in schema.get("anyOf", []):
        native_check(child, openai=openai)
    if "items" in schema:
        native_check(schema["items"], openai=openai)


def fake_provider(monkeypatch, client, output, observed):
    for key in client.key_envs:
        monkeypatch.setenv(key, "offline-test-token")

    def cli(command, **kwargs):
        assert kwargs["timeout"] == client.timeout_seconds
        assert "source contract" in kwargs["input"]
        if command[0] == "codex":
            wire = json.loads(Path(command[command.index("--output-schema") + 1]).read_text())
            native_check(wire, openai=True)
            Path(command[command.index("--output-last-message") + 1]).write_text(json.dumps(output))
            stdout = ""
        else:
            if client.schema_mode == "native":
                wire = json.loads(command[command.index("--json-schema") + 1])
                native_check(wire, openai=False)
                stdout = json.dumps({"structured_output": output, "result": "", "is_error": False})
            else:
                assert "--json-schema" not in command
                wire = {"mode": "prompt_json"}
                stdout = json.dumps({"result": json.dumps(output), "is_error": False})
        observed.append(wire)
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    def post(endpoint, body, headers, timeout):
        assert timeout == client.timeout_seconds
        observed.append(body)
        if client.transport == "gemini_api":
            assert body["generationConfig"]["responseMimeType"] == "application/json"
            if client.schema_mode == "native":
                native_check(body["generationConfig"]["responseJsonSchema"], openai=False)
            else:
                assert "responseJsonSchema" not in body["generationConfig"]
            assert "response_format" not in body
            return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(output)}]}}]}
        if client.transport == "anthropic_api":
            if client.schema_mode == "native":
                native_check(body["output_config"]["format"]["schema"], openai=False)
            else:
                assert "output_config" not in body
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(output)}]}
        if client.provider in {"zhipu", "deepseek"}:
            assert body["response_format"] == {"type": "json_object"}
        elif client.provider == "local":
            assert "response_format" not in body
        else:
            native_check(body["response_format"]["json_schema"]["schema"], openai=True)
        assert body["model"] == client.model
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}]}

    monkeypatch.setattr(models.subprocess, "run", cli)
    monkeypatch.setattr(models, "_post", post)


def client_for(model_id, monkeypatch):
    if model_id == "thunderomlx":
        monkeypatch.setenv("SOLAR_LLM_LOCAL_MODEL", "offline-local-model")
        monkeypatch.setenv("SOLAR_LLM_LOCAL_ENDPOINT", "http://127.0.0.1:12345/v1/chat/completions")
    return models.create_model(model=model_id)


@pytest.mark.parametrize("model_id", MODEL_IDS)
@pytest.mark.parametrize("schema_name", CALL_SCHEMAS)
def test_every_registered_model_and_step_reaches_correct_request_boundary(tmp_path, monkeypatch, model_id, schema_name):
    client = client_for(model_id, monkeypatch)
    observed = []
    fake_provider(monkeypatch, client, {"unexpected": True}, observed)
    source = (SCHEMAS / schema_name).read_bytes()
    with pytest.raises(OutputContractError, match="Output violates source contract"):
        client.generate("Offline contract probe", SCHEMAS / schema_name, tmp_path / "call")
    assert len(observed) == 1
    assert source == (SCHEMAS / schema_name).read_bytes()
    receipt = json.loads((tmp_path / "call/model_call_receipt.json").read_text())
    assert receipt["status"] == "failed"
    assert receipt["registry_id"] == model_id


@pytest.mark.parametrize("model_id", MODEL_IDS)
def test_valid_output_round_trip_for_every_registry_entry(tmp_path, monkeypatch, model_id):
    client = client_for(model_id, monkeypatch)
    output = {"answer": "完成", "nullable": None}
    if client.provider == "openai":
        output["cpu"] = None
    fake_provider(monkeypatch, client, output, [])
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps(SIMPLE))
    assert client.generate("Return an answer", source_path, tmp_path / "call") == {"answer": "完成", "nullable": None}
    receipt = json.loads((tmp_path / "call/model_call_receipt.json").read_text())
    assert receipt["status"] == "passed"
    assert "offline-test-token" not in json.dumps(receipt)


def test_last_planner_failure_and_optional_resource_roundtrip():
    source = json.loads((SCHEMAS / "planning/plan-ir.semantic.structured.v2.schema.json").read_text())
    wire = project_schema(source)
    original = source["$defs"]["operator_requirements"]
    projected = wire["$defs"]["operator_requirements"]
    for name in ("cpu_cores_min", "memory_mb_min", "gpu_required"):
        assert name not in original["required"]
        assert name in projected["required"]
        assert Draft202012Validator(projected["properties"][name]).is_valid(None)
    contract = {"type": "object", "additionalProperties": False, "required": ["resources"],
                "properties": {"resources": {"$ref": "#/$defs/operator_requirements"}}, "$defs": source["$defs"]}
    value = {"resources": {"capabilities": [], "network": "optional", "execution_trust": "any",
                           "minimum_context_tokens": 0, "effects": [],
                           "cpu_cores_min": None, "memory_mb_min": 256, "gpu_required": False}}
    decoded = validate_output(value, contract, profile="openai")
    assert "cpu_cores_min" not in decoded["resources"]
    assert decoded["resources"]["memory_mb_min"] == 256
    assert decoded["resources"]["gpu_required"] is False


@pytest.mark.parametrize("value", [{"answer": "", "cpu": None}, {"answer": None}, {"answer": "ok", "cpu": -1}, {"answer": "ok", "extra": 1}])
def test_projection_never_weakens_source_acceptance(value):
    with pytest.raises(OutputContractError):
        validate_output(value, SIMPLE, profile="openai")


def test_tuple_positions_oneof_uniqueness_and_property_keyword_names_preserved():
    schema = {"type": "object", "additionalProperties": False, "required": ["enum", "span"], "properties": {
        "enum": {"type": "string", "enum": ["oneOf", "const"]},
        "span": {"type": "array", "prefixItems": [{"type": "integer", "minimum": 0}, {"type": "integer", "minimum": 1}],
                 "items": False, "minItems": 2, "maxItems": 2, "uniqueItems": True}}}
    before = deepcopy(schema)
    native_check(project_schema(schema), openai=True)
    assert schema == before
    assert validate_output({"enum": "const", "span": [0, 1]}, schema) == {"enum": "const", "span": [0, 1]}
    for span in ([1, 0], [1, 1], [0, 1, 2]):
        with pytest.raises(OutputContractError):
            validate_output({"enum": "const", "span": span}, schema)


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}', '```json\n{}\n```', '{} trailing'])
def test_ambiguous_or_non_json_provider_output_rejected(text):
    with pytest.raises(OutputContractError):
        parse_json(text)


@pytest.mark.parametrize("stage", ["intent", "requirement", "planner", "direct_answer"])
@pytest.mark.parametrize("role", ["compiler", "reviewer"])
def test_all_stage_role_overrides_use_registry(stage, role, monkeypatch):
    monkeypatch.setenv(f"SOLAR_{stage.upper()}_{role.upper()}_MODEL", "glm-5.1")
    client = models.stage_model(stage, role)
    assert client.provider == "zhipu"
    assert client.model == "glm-5.1"  # not the proxy's --model opus flag
    assert client.schema_mode == "json_object"


def test_unregistered_or_conflicting_models_fail_without_silent_fallback():
    with pytest.raises(models.StructuredModelError, match="explicit provider"):
        models.create_model(model="made-up-model")
    with pytest.raises(models.StructuredModelError, match="disagree"):
        models.create_model(model="glm", provider="codex")


@pytest.mark.parametrize("model_id,transport", [("openai-gpt-5.5", "chat_completions"), ("claude-opus", "anthropic_api")])
def test_explicit_api_transport_uses_native_provider_format(tmp_path, monkeypatch, model_id, transport):
    provider = REGISTRY["models"][model_id]["provider"]
    monkeypatch.setenv(f"SOLAR_LLM_{provider.upper()}_TRANSPORT", transport)
    monkeypatch.setenv(f"SOLAR_LLM_{provider.upper()}_SCHEMA_MODE", "native")
    client = models.create_model(model=model_id)
    fake_provider(monkeypatch, client, {"answer": "ok", "cpu": None, "nullable": None} if provider == "openai" else {"answer": "ok"}, [])
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(SIMPLE))
    assert client.generate("Answer", path, tmp_path / "call")["answer"] == "ok"


def test_planner_generate_call_inventory_does_not_drift():
    tree = ast.parse(Path(planner.__file__).read_text(encoding="utf-8"))
    known = {str((SCHEMAS / name).resolve()) for name in CALL_SCHEMAS}
    for call in ast.walk(tree):
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "generate":
            schema_arg = call.args[1]
            if isinstance(schema_arg, ast.Name):
                assert str(getattr(planner, schema_arg.id).resolve()) in known
            else:
                assert isinstance(schema_arg, ast.IfExp)
                assert "plan-ir.semantic.structured.v2.schema.json" in ast.unparse(schema_arg)


@pytest.mark.parametrize("node", ["evidence_synthesis", "report_draft", "report_revision", "independent_review", "report_revision_review"])
@pytest.mark.parametrize("profile", ["openai", "anthropic", "gemini"])
def test_research_writer_reviewer_schemas_share_projection(node, profile):
    from harness.plugins.autosci.services.codex_research import _response_schema
    source = _response_schema(node)
    native_check(project_schema(source, profile), openai=profile == "openai")


def test_gemini_required_recursion_uses_json_mode_without_weakening_contract():
    source = json.loads((SCHEMAS / CALL_SCHEMAS[0]).read_text())
    with pytest.raises(OutputContractError, match="recursive"):
        project_schema(source, "gemini")
    assert models.create_model(model="gemini-pro").schema_mode == "json_object"


def test_claude_recursive_contract_uses_explicit_conservative_registry_policy():
    source = json.loads((SCHEMAS / CALL_SCHEMAS[0]).read_text())
    with pytest.raises(OutputContractError, match="recursive"):
        project_schema(source, "anthropic")
    assert models.create_model(model="claude-opus").schema_mode == "prompt_json"


def test_provider_normalization_and_transport_specific_model_ids(monkeypatch):
    assert models.create_model(model="gpt-5.5", provider=" CODEX ").provider == "openai"
    assert models.create_model(model="claude-sonnet").model == "sonnet"
    monkeypatch.setenv("SOLAR_LLM_ANTHROPIC_TRANSPORT", "anthropic_api")
    assert models.create_model(model="claude-sonnet").model == "claude-sonnet-4-6"
    assert models.create_model(model="sonnet").provider == "zhipu"


def test_planner_contract_failure_records_rejection_without_handoff(tmp_path, monkeypatch):
    fixture_spec = importlib.util.spec_from_file_location("structured_planner_fixture", ROOT / "tests/harness/test_elastic_planner.py")
    fixture = importlib.util.module_from_spec(fixture_spec)
    fixture_spec.loader.exec_module(fixture)
    requirement = fixture._requirement_ir()
    client = models.create_model(model="deepseek")
    observed = []
    fake_provider(monkeypatch, client, {"invalid": True}, observed)
    result = planner.run_semantic_planning_pipeline(requirement, tmp_path, client, client)
    acceptance = result["plan_acceptance"]
    assert acceptance["decision"] != "accepted"
    assert acceptance["runtime_handoff_allowed"] is False
    assert (tmp_path / "plan_acceptance.json").is_file()
    assert len(observed) == 1
    assert not (tmp_path / "scheduler_input.json").exists()


@pytest.mark.parametrize("stage", ["intent", "planner_adapter", "planner_cli", "direct_answer"])
def test_actual_stage_factories_are_not_codex_bound(stage, monkeypatch):
    prefix = {"intent": "INTENT", "planner_adapter": "PLANNER", "planner_cli": "PLANNER", "direct_answer": "DIRECT_ANSWER"}[stage]
    monkeypatch.setenv(f"SOLAR_{prefix}_COMPILER_MODEL", "glm")
    if stage == "intent":
        client = intent_compiler.model_from_environment("compiler")
    elif stage == "direct_answer":
        from direct_answer_runtime import _model
        client = _model("compiler")
    else:
        path = ROOT / "harness/tools" / ("elastic_plan.py" if stage == "planner_cli" else "elastic_planner_adapter.py")
        spec = importlib.util.spec_from_file_location("structured_" + stage, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        client = (module._codex_model if stage == "planner_cli" else module._model)("compiler")
    assert client.provider == "zhipu"
    assert client.model == "glm-5.1"


@pytest.mark.parametrize("provider,model_id", [("gemini", "gemini-pro"), ("zhipu", "glm"), ("deepseek", "deepseek"), ("local", "thunderomlx")])
def test_research_registry_service_preserves_actual_provider_and_declares_every_file(tmp_path, monkeypatch, provider, model_id):
    from harness.plugins.autosci.bin import fixed_research_node_adapter as adapter
    monkeypatch.setenv("SOLAR_RESEARCH_MODEL_PROVIDER", provider)
    monkeypatch.setenv("SOLAR_RESEARCH_MODEL", model_id)
    client_for("thunderomlx" if provider == "local" else model_id, monkeypatch)
    services = adapter._codex_services(node_id="independent_review", stage_dir=tmp_path)
    service = services["review_model_generate"]
    output = {"node_id": "independent_review", "findings": [], "verdict_suggestion": "accept", "limitations": []}
    fake_provider(monkeypatch, service.client, output, [])
    result = service(node_id="independent_review")
    usage = result["provider_usage"]
    assert usage[0]["provider"] == provider
    assert usage[0]["principal_role"] == "reviewer"
    assert set(usage[0]["evidence_paths"]) == {path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file()}
    adapter._verify_model_usage(node_id="independent_review", result={"model_provider_usage": usage})


@pytest.mark.parametrize("finish,refusal", [("length", None), ("stop", "refused"), ("tool_calls", None)])
def test_truncation_refusal_and_tool_calls_do_not_pass(tmp_path, monkeypatch, finish, refusal):
    client = models.create_model(model="deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-never-record")
    monkeypatch.setattr(models, "_post", lambda *a, **k: {"choices": [{"finish_reason": finish, "message": {"content": '{"answer":"ok"}', "refusal": refusal}}]})
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps(SIMPLE))
    with pytest.raises(models.StructuredModelError, match="refused, truncated"):
        client.generate("answer", schema, tmp_path / "call")
    receipt = (tmp_path / "call/model_call_receipt.json").read_text()
    assert '"status": "failed"' in receipt
    assert "test-key-never-record" not in receipt


def test_no_credentials_does_not_call_http(tmp_path, monkeypatch):
    client = models.create_model(model="deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(SIMPLE))
    with pytest.raises(models.StructuredModelError, match="authentication missing"):
        client.generate("answer", path, tmp_path / "call")


def test_requirement_default_factory_honors_provider_and_bounded_structural_repair(tmp_path, monkeypatch):
    from requirement_compiler import compile_requirement_ir
    fixture_spec = importlib.util.spec_from_file_location("structured_requirement_fixture", ROOT / "harness/tests/test_semantic_retrieval_contract.py")
    fixture = importlib.util.module_from_spec(fixture_spec)
    fixture_spec.loader.exec_module(fixture)
    monkeypatch.setenv("SOLAR_REQUIREMENT_MODEL", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-key")
    values = iter([{"invalid": True}, fixture.body(), {"accepted": True, "errors": []}])
    requests = []
    def post(endpoint, body, headers, timeout):
        requests.append(body)
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(next(values))}}]}
    monkeypatch.setattr(models, "_post", post)
    ir = compile_requirement_ir(fixture.intent(), intent_ir_sha256="a" * 64, work_dir=tmp_path)
    assert ir["schema_version"] == "solar.requirement_ir.v2"
    assert len(requests) == 3
    assert all(request["model"] == "deepseek-v4-pro" for request in requests)
