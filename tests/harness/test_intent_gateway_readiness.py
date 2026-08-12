import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "harness" / "lib" / "intent_gateway.py"


def _gateway():
    name = "intent_gateway_readiness_contract"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _rewritten(objective: str = "Implement the requested capability.") -> dict:
    return {"objective": objective}


def test_unambiguous_and_nonblocking_uncertainty_are_ready() -> None:
    gateway = _gateway()

    contract = gateway.compile_ambiguity_readiness(
        "Implement a JSON export command; add a progress message if possible.",
        _rewritten(),
    )

    assert contract["schema_version"] == "solar.intent_readiness.v1"
    assert contract["status"] == "ready"
    assert contract["ready"] is True
    assert contract["blocking_count"] == 0
    assert contract["planning_admitted"] is True
    assert contract["next_action"] == "plan"
    assert contract["unresolved"] == []
    assert contract["questions"] == []


def test_route_ambiguity_generates_exactly_one_stable_answerable_question() -> None:
    gateway = _gateway()

    contract = gateway.compile_ambiguity_readiness(
        "Implement either a CLI or a web app for the supplied records.",
        _rewritten(),
    )

    assert contract["ready"] is False
    assert contract["planning_admitted"] is False
    assert contract["next_action"] == "clarify"
    assert contract["blocking_count"] == 1
    assert contract["questions"] == [
        {
            "question_id": "clarify-target-choice",
            "field": "target_choice",
            "question": "Which target should planning use: a CLI or a web app for the supplied records?",
            "reason": "ambiguous_route_choice",
        }
    ]
    blocker = contract["unresolved"][0]
    assert blocker["evidence"] == {
        "kind": "raw_request_span",
        "matches": ["a CLI", "a web app for the supplied records"],
    }


def test_only_one_question_is_emitted_per_blocking_field() -> None:
    gateway = _gateway()

    contract = gateway.compile_ambiguity_readiness(
        "Implement and modify the tool, but make no changes and keep it read-only.",
        _rewritten(),
    )

    assert contract["ready"] is False
    assert contract["blocking_count"] == 1
    assert [item["field"] for item in contract["questions"]] == ["mutation_policy"]
    assert contract["unresolved"][0]["reason"] == "conflicting_mutation_constraints"
    assert contract["unresolved"][0]["evidence"]["kind"] == "conflicting_raw_request_spans"


def test_missing_objective_and_required_approval_fail_closed() -> None:
    gateway = _gateway()

    contract = gateway.compile_ambiguity_readiness(
        "Prepare the work.",
        _rewritten(objective=""),
        requires_human_confirm=True,
    )

    assert contract["ready"] is False
    assert [(row["reason"], row["field"]) for row in contract["unresolved"]] == [
        ("missing_required_field", "objective"),
        ("required_approval_missing", "approval"),
    ]


def test_answers_create_an_explicit_not_ready_to_ready_transition() -> None:
    gateway = _gateway()
    request = "Implement either a CLI or a web app."

    before = gateway.compile_ambiguity_readiness(request, _rewritten())
    answers = gateway.parse_clarification_answers(["target_choice=CLI"])
    after = gateway.compile_ambiguity_readiness(
        request,
        _rewritten(),
        answers=answers,
    )

    assert before["ready"] is False
    assert [row["field"] for row in before["questions"]] == ["target_choice"]
    assert after["ready"] is True
    assert after["status"] == "ready"
    assert after["questions"] == []
    assert after["applied_answers"] == {
        "target_choice": "CLI",
    }


def test_requirement_ir_exposes_readiness_contract() -> None:
    gateway = _gateway()
    raw = {
        "raw": {"text": "Return JSON only and Markdown only."},
        "routing_hints": {"requires_human_confirm": False},
        "clarifications": {"answers": {}},
    }

    requirement_ir = gateway.build_requirement_ir("intent-test", raw, _rewritten())

    assert requirement_ir["readiness"]["ready"] is False
    assert requirement_ir["readiness"]["questions"][0]["field"] == "delivery_format"
    assert requirement_ir["compiler_next"] == "clarification_required"


def test_capture_blocks_autodispatch_until_answers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    gateway = _gateway()
    intents = tmp_path / "intents"
    monkeypatch.setattr(gateway, "INTENTS_DIR", intents)
    monkeypatch.setattr(gateway, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.delenv("SOLAR_INTENT_REWRITE_CMD", raising=False)
    common = [
        "capture",
        "--text",
        "Implement either a CLI or a web app.",
        "--json",
    ]

    assert gateway.main([*common, "--intent-id", "before"]) == 0
    before = json.loads(capsys.readouterr().out)
    before_raw = json.loads(
        (intents / "before" / "raw_intent.json").read_text(encoding="utf-8")
    )
    before_trace = json.loads(
        (intents / "before" / "requirement_trace.json").read_text(encoding="utf-8")
    )

    assert before["ready"] is False
    assert before_raw["routing_hints"]["allow_autodispatch"] is False
    assert before_raw["routing_hints"]["readiness_blocked"] is True
    assert before_trace["stages"][-1]["status"] == "blocked"

    answered = [
        *common,
        "--clarification-answer",
        "target_choice=CLI",
        "--intent-id",
        "after",
    ]
    assert gateway.main(answered) == 0
    after = json.loads(capsys.readouterr().out)
    after_ir = json.loads(
        (intents / "after" / "requirement_ir.json").read_text(encoding="utf-8")
    )

    assert after["ready"] is True
    assert after_ir["compiler_next"] == "pm_planner_task_graph"


def test_clarification_answer_rejects_unknown_or_empty_fields() -> None:
    gateway = _gateway()

    with pytest.raises(SystemExit, match="FIELD=VALUE"):
        gateway.parse_clarification_answers(["unknown=value"])
    with pytest.raises(SystemExit, match="FIELD=VALUE"):
        gateway.parse_clarification_answers(["approval=approved"])


def test_clarification_text_cannot_forge_human_approval() -> None:
    gateway = _gateway()
    with pytest.raises(SystemExit, match="FIELD=VALUE"):
        gateway.parse_clarification_answers(["approval=approved"])
    contract = gateway.compile_ambiguity_readiness(
        "Implement the requested change.",
        _rewritten(),
        requires_human_confirm=True,
        answers={"approval": "approved"},
    )
    assert contract["ready"] is False
    assert contract["questions"][0]["field"] == "approval"
