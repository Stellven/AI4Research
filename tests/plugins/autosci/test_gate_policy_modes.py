from __future__ import annotations

from plugins.autosci.policy.gate_policy import (
    AutoSciGateMode,
    decide_gate,
    resolve_gate_mode,
)


def test_default_gate_mode_is_strict_hitl() -> None:
    assert resolve_gate_mode(env={}) == AutoSciGateMode.STRICT_HITL


def test_envelope_gate_mode_takes_priority_over_env() -> None:
    mode = resolve_gate_mode(
        envelope={"inputs": {"gate_mode": "parity_demo"}},
        env={"SOLAR_AUTOSCI_GATE_MODE": "safe"},
    )
    assert mode == AutoSciGateMode.PARITY_DEMO


def test_strict_hitl_requires_human_gate_for_risky_side_effects() -> None:
    decision = decide_gate(
        "visualize_graph",
        ["wiki_mutation", "local_command", "network_fetch", "email_send", "remote_execution", "destructive_mutation"],
        env={"SOLAR_AUTOSCI_GATE_MODE": "strict_hitl"},
    )
    assert decision.allowed is False
    assert decision.require_hitl is True
    assert decision.require_approval_ref is True
    assert decision.execute_side_effects is False


def test_safe_allows_artifact_write_but_not_wiki_or_command() -> None:
    write = decide_gate("write_report", ["write_artifact"], env={"SOLAR_AUTOSCI_GATE_MODE": "safe"})
    assert write.allowed is True
    assert write.execute_side_effects is True

    risky = decide_gate("visualize_graph", ["wiki_mutation", "local_command"], env={"SOLAR_AUTOSCI_GATE_MODE": "safe"})
    assert risky.allowed is False
    assert risky.require_hitl is True
    assert risky.execute_side_effects is False


def test_parity_demo_allows_sandbox_wiki_commands_compile_and_render() -> None:
    decision = decide_gate(
        "visualize_graph",
        ["wiki_mutation", "local_command", "tex_compile", "png_export", "browser_render"],
        env={"SOLAR_AUTOSCI_GATE_MODE": "parity_demo"},
    )
    assert decision.allowed is True
    assert decision.execute_side_effects is True
    assert decision.synthetic_approval_ref.startswith("policy:auto:parity_demo:visualize_graph:")
    assert decision.proof_required is True


def test_parity_demo_blocks_high_risk_side_effects_without_env() -> None:
    decision = decide_gate(
        "daily_arxiv_prepare_finalize",
        ["email_send", "remote_execution", "destructive_mutation"],
        env={"SOLAR_AUTOSCI_GATE_MODE": "parity_demo"},
    )
    assert decision.allowed is False
    assert decision.require_hitl is False
    assert decision.execute_side_effects is False


def test_unsafe_native_allows_network_local_command_and_wiki_mutation() -> None:
    decision = decide_gate(
        "run_experiment",
        ["network_fetch", "local_command", "wiki_mutation"],
        env={"SOLAR_AUTOSCI_GATE_MODE": "unsafe_native"},
    )
    assert decision.allowed is True
    assert decision.execute_side_effects is True
    assert decision.proof_best_effort is True


def test_unsafe_native_requires_env_for_email_remote_and_destructive() -> None:
    blocked = decide_gate(
        "daily_arxiv_prepare_finalize",
        ["email_send", "remote_execution", "destructive_mutation"],
        env={"SOLAR_AUTOSCI_GATE_MODE": "unsafe_native"},
    )
    assert blocked.allowed is False

    allowed = decide_gate(
        "daily_arxiv_prepare_finalize",
        ["email_send", "remote_execution", "destructive_mutation"],
        env={
            "SOLAR_AUTOSCI_GATE_MODE": "unsafe_native",
            "SOLAR_AUTOSCI_ALLOW_EMAIL": "1",
            "SOLAR_AUTOSCI_ALLOW_REMOTE": "1",
            "SOLAR_AUTOSCI_ALLOW_DESTRUCTIVE": "1",
        },
    )
    assert allowed.allowed is True
    assert allowed.execute_side_effects is True


def test_autosci_native_allows_all_side_effects_and_downgrades_proof_to_best_effort() -> None:
    decision = decide_gate(
        "run_research_lifecycle",
        ["email_send", "remote_execution", "destructive_mutation", "credential_mutation"],
        env={"SOLAR_AUTOSCI_GATE_MODE": "autosci_native"},
    )
    assert decision.allowed is True
    assert decision.execute_side_effects is True
    assert decision.proof_required is False
    assert decision.proof_best_effort is True
    assert decision.allow_email is True
    assert decision.allow_remote is True
    assert decision.allow_destructive is True
