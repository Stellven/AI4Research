"""Deterministic test 5 (is_explicit_deepdive_request semantics, generalized):
the RSI prompt matches, generic words never do (AC-R1.3); explicit-only and
fallback contracts never free-match (R1 resolution order)."""
from __future__ import annotations

import workflow_contract as wc

# The bounded-demo prompt, verbatim from rsi-deepdive-workflow-lock.md
RSI_PROMPT = "Give me a deep research report on Recursive Self-Improving Models in HTML format"


def _contracts(shipped_contracts):
    return list(shipped_contracts.values())


def test_rsi_prompt_matches_the_demo_contract(shipped_contracts, clean_trigger_env):
    assert (
        wc.match_trigger(RSI_PROMPT, env=clean_trigger_env, contracts=_contracts(shipped_contracts))
        == "research.deepdive.rsi_demo"
    )


def test_every_declared_marker_matches(shipped_contracts, clean_trigger_env):
    contract = shipped_contracts["research.deepdive.rsi_demo"]
    for marker in contract["trigger"]["explicit_markers"]:
        text = f"请给我一份 {marker} 关于X的产出"
        assert (
            wc.match_trigger(text, env=clean_trigger_env, contracts=_contracts(shipped_contracts))
            == "research.deepdive.rsi_demo"
        ), marker


def test_generic_words_are_insufficient(shipped_contracts, clean_trigger_env):
    for text in (
        "please research the market for me",
        "run some research on solar panels",
        "帮我研究一下这个市场",
        "做一个调研",
        "研究研究这个问题",
        "",
    ):
        assert (
            wc.match_trigger(text, env=clean_trigger_env, contracts=_contracts(shipped_contracts))
            is None
        ), text


# ---------------------------------------------------------------------------
# F6 (round-2): env_gates may CONSTRAIN a match, never CONSTITUTE one. A trigger
# fires only on an explicit marker OR the requirement-compiler type; an env gate
# is never a standalone match path. The reviewer's ▶EXECUTED probe: a pure code
# request under SOLAR_DEMO_REPORT_MODE=1 routed to the research contract because
# the env gate matched ANY text. It must not — and the demo driver, whose
# prompts carry the markers anyway, must keep working.
# ---------------------------------------------------------------------------

def test_env_gate_alone_does_not_route_unrelated_text_in_demo_mode(shipped_contracts):
    """The corrected F6 behavior: a marker-free prompt in demo mode does NOT
    route (was the bug: env gate matched any text)."""
    env = {"SOLAR_DEMO_REPORT_MODE": "1"}
    assert wc.match_trigger("hello there", env=env, contracts=_contracts(shipped_contracts)) is None


def test_env_gate_does_not_route_pure_code_request_in_demo_mode(shipped_contracts):
    """Reviewer probe verbatim: a pure code request under demo mode must not be
    hijacked to the research contract by the env gate."""
    env = {"SOLAR_DEMO_REPORT_MODE": "1"}
    for code_request in (
        "implement a python CLI that adds two numbers and write tests",
        "fix the failing pytest in workdir/tool.py",
        "refactor the auth module to remove the global",
    ):
        assert (
            wc.match_trigger(code_request, env=env, contracts=_contracts(shipped_contracts))
            is None
        ), code_request


def test_demo_driver_marker_prompt_still_routes_in_demo_mode(shipped_contracts):
    """F6 must NOT break the demo driver: its prompts carry a declared marker,
    so they route with or without demo mode set."""
    env = {"SOLAR_DEMO_REPORT_MODE": "1"}
    assert (
        wc.match_trigger(RSI_PROMPT, env=env, contracts=_contracts(shipped_contracts))
        == "research.deepdive.rsi_demo"
    )


def test_env_gate_unset_or_wrong_value_does_not_route(shipped_contracts):
    for env in ({}, {"SOLAR_DEMO_REPORT_MODE": "0"}, {"SOLAR_DEMO_REPORT_MODE": ""}):
        assert wc.match_trigger("hello there", env=env, contracts=_contracts(shipped_contracts)) is None


def test_requirement_compiler_type_routes(shipped_contracts, clean_trigger_env):
    assert (
        wc.match_trigger(
            "summarize the flashmlx benchmark landscape",
            env=clean_trigger_env,
            requirement_type="RESEARCH",
            contracts=_contracts(shipped_contracts),
        )
        == "research.deepdive.rsi_demo"
    )
    assert (
        wc.match_trigger(
            "summarize the flashmlx benchmark landscape",
            env=clean_trigger_env,
            requirement_type="IMPLEMENTATION",
            contracts=_contracts(shipped_contracts),
        )
        is None
    )


def test_explicit_only_contract_never_free_matches(shipped_contracts, clean_trigger_env):
    assert (
        wc.match_trigger(
            "run the code cli smoke workflow please",
            env=clean_trigger_env,
            contracts=_contracts(shipped_contracts),
        )
        is None
    )


def test_fallback_contract_never_matches(shipped_contracts):
    # even in demo mode, pm.generic.v1 must never be a trigger match — it is
    # the no-match default, applied by the caller, not a route
    result = wc.match_trigger(
        "anything at all", env={"SOLAR_DEMO_REPORT_MODE": "1"}, contracts=_contracts(shipped_contracts)
    )
    assert result != "pm.generic.v1"


def test_longest_marker_wins_across_contracts(shipped_contracts, clean_trigger_env):
    extra = {
        "schema_version": wc.SCHEMA_VERSION,
        "workflow_id": "research.other",
        "version": "1.0",
        "trigger": {"explicit_markers": ["deep"], "env_gates": []},
        "provider_policy": {"allowed_providers": ["openai"]},
        "artifact_roots": {"canonical": "workspace/other/"},
        "stages_mode": "planner_generated",
        "stages": [],
    }
    contracts = _contracts(shipped_contracts) + [extra]
    assert (
        wc.match_trigger(RSI_PROMPT, env=clean_trigger_env, contracts=contracts)
        == "research.deepdive.rsi_demo"
    )
