#!/usr/bin/env python3
"""The dashboard must route a prompt, not pin every prompt to one workflow.

The research dashboard profile set ``SOLAR_INTAKE_WORKFLOW_ID`` for every
request it accepted, so a trivial question and a full literature review both
entered the fifteen-node research contract and the router was never consulted.
These tests pin the routing decision the intake path now makes.
"""

import importlib.util
from pathlib import Path


MODULE = (Path(__file__).resolve().parents[2] / "harness") / "lib" / "symphony" / "status-server.py"
spec = importlib.util.spec_from_file_location("status_server", MODULE)
status_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(status_server)


PINNED = "research.evidence_to_poc.v1"


def _pinned_env() -> dict:
    """The environment the ``fixed_hybrid_demo_v1`` dashboard profile produces."""
    return {
        "SOLAR_INTAKE_WORKFLOW_ID": PINNED,
        "SOLAR_RESEARCH_EXECUTION_PROFILE": "part_a_plus_poc",
        "SOLAR_RESEARCH_ACQUISITION_MODE": "hybrid",
        "SOLAR_RESEARCH_RETRIEVAL_POLICY": "public_bibliographic_no_key_v1",
        "SOLAR_RESEARCH_EXPERIMENT_POLICY": "evidence_lineage_integrity_v1",
    }


def test_a_prompt_with_no_research_intent_leaves_the_research_contract():
    env = _pinned_env()

    routing = status_server._classify_intake_request(
        "what is 2 + 2", env, explicit_workflow_id=""
    )

    assert routing["applied"] is True
    assert routing["tier"] == "simple"
    # The pin and every profile variable it carried are gone, so the request
    # takes the generic planner path instead of a fifteen-node contract.
    assert "SOLAR_INTAKE_WORKFLOW_ID" not in env
    assert "SOLAR_RESEARCH_EXECUTION_PROFILE" not in env
    assert "SOLAR_RESEARCH_ACQUISITION_MODE" not in env


def test_a_research_request_without_build_intent_runs_part_a_only():
    env = _pinned_env()

    routing = status_server._classify_intake_request(
        "give me a deep research report on state space model architectures",
        env,
        explicit_workflow_id="",
    )

    assert routing["tier"] == "research_report"
    assert env["SOLAR_INTAKE_WORKFLOW_ID"] == PINNED
    # The profile is narrowed from the pinned part_a_plus_poc: nothing in the
    # request asked for an experiment to be built or run.
    assert env["SOLAR_RESEARCH_EXECUTION_PROFILE"] == "part_a_only"


def test_a_research_request_that_asks_to_benchmark_runs_part_b_too():
    env = _pinned_env()

    routing = status_server._classify_intake_request(
        "give me a deep research report and PoC verification and benchmarking for "
        "whether mamba architecture beats transformer architecture or JEPA",
        env,
        explicit_workflow_id="",
    )

    assert routing["tier"] == "research_poc"
    assert routing["poc_markers"]
    assert env["SOLAR_INTAKE_WORKFLOW_ID"] == PINNED
    assert env["SOLAR_RESEARCH_EXECUTION_PROFILE"] == "part_a_plus_poc"


def test_an_explicit_workflow_id_from_the_caller_is_never_overridden():
    env = _pinned_env()

    routing = status_server._classify_intake_request(
        "what is 2 + 2", env, explicit_workflow_id=PINNED
    )

    assert routing["applied"] is False
    assert env["SOLAR_INTAKE_WORKFLOW_ID"] == PINNED


def test_routing_does_not_touch_an_environment_that_was_never_pinned():
    env = {"SOLAR_RESEARCH_EXECUTION_PROFILE": "part_a_plus_poc"}

    routing = status_server._classify_intake_request(
        "give me a deep research report and benchmark it", env, explicit_workflow_id=""
    )

    assert routing["applied"] is False
    assert env == {"SOLAR_RESEARCH_EXECUTION_PROFILE": "part_a_plus_poc"}
