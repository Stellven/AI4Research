#!/usr/bin/env python3
"""test_operator_persona.py — Unit tests for the shared operator persona resolver."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from operator_persona import (
    EVALUATOR_PROTOCOL_FILENAME,
    PersonaResolution,
    resolve_persona,
)

PERSONAS_DIR = ROOT / "personas"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(*, persona=None, role=None, **extra):
    """Build a minimal operator config dict for testing."""
    cfg = dict(extra)
    if persona is not None:
        cfg["persona"] = persona
    if role is not None:
        cfg["role"] = role
    return cfg


# ---------------------------------------------------------------------------
# Source resolution: persona field vs role fallback
# ---------------------------------------------------------------------------


def test_persona_field_is_authoritative_when_present():
    """``persona`` field takes precedence over ``role``."""
    cfg = _cfg(persona="builder", role="evaluator")
    pr = resolve_persona("op", cfg, PERSONAS_DIR)
    assert pr.persona_name == "builder"
    assert pr.source == "persona"


def test_role_fallback_when_persona_absent():
    """Falls back to ``role`` when ``persona`` field is not set."""
    cfg = _cfg(role="builder")
    pr = resolve_persona("op", cfg, PERSONAS_DIR)
    assert pr.persona_name == "builder"
    assert pr.source == "role"


def test_role_fallback_when_persona_empty_string():
    """Empty ``persona`` string is treated as absent; falls back to ``role``."""
    cfg = _cfg(persona="", role="builder")
    pr = resolve_persona("op", cfg, PERSONAS_DIR)
    assert pr.persona_name == "builder"
    assert pr.source == "role"


def test_persona_field_equal_to_role_reports_persona_source():
    """When persona == role, source is still ``'persona'``."""
    cfg = _cfg(persona="builder", role="builder")
    pr = resolve_persona("op", cfg, PERSONAS_DIR)
    assert pr.source == "persona"


def test_persona_differs_from_role_uses_persona():
    """``persona != role`` — persona field wins, role is ignored."""
    # evaluator.md must exist in the real personas dir
    cfg = _cfg(persona="evaluator", role="builder")
    pr = resolve_persona("op", cfg, PERSONAS_DIR)
    assert pr.persona_name == "evaluator"
    assert pr.source == "persona"
    # Builder persona must NOT have been loaded
    assert "evaluator" in pr.persona_text.lower() or pr.persona_path.name == "evaluator.md"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_raises_when_neither_persona_nor_role():
    """Raises RuntimeError when config has neither ``persona`` nor ``role``."""
    with pytest.raises(RuntimeError, match="no persona binding"):
        resolve_persona("op", {}, PERSONAS_DIR)


def test_raises_when_persona_file_missing(tmp_path):
    """Raises RuntimeError when persona field names a non-existent file."""
    personas = tmp_path / "personas"
    personas.mkdir()
    cfg = _cfg(persona="ghost")
    with pytest.raises(RuntimeError, match="persona file missing"):
        resolve_persona("op", cfg, personas)


def test_raises_when_role_fallback_file_missing(tmp_path):
    """Raises RuntimeError when role fallback file is absent."""
    personas = tmp_path / "personas"
    personas.mkdir()
    cfg = _cfg(role="ghost")
    with pytest.raises(RuntimeError, match="persona file missing"):
        resolve_persona("op", cfg, personas)


def test_error_message_contains_operator_id(tmp_path):
    """Error messages include the operator_id for easy triage."""
    personas = tmp_path / "personas"
    personas.mkdir()
    with pytest.raises(RuntimeError, match="my-op-id"):
        resolve_persona("my-op-id", {}, personas)

    cfg = _cfg(persona="ghost")
    with pytest.raises(RuntimeError, match="my-op-id"):
        resolve_persona("my-op-id", cfg, personas)


# ---------------------------------------------------------------------------
# Evaluator protocol loading
# ---------------------------------------------------------------------------


def test_evaluator_protocol_loaded_for_evaluator_persona():
    """Evaluator protocol is auto-loaded when persona is ``'evaluator'``."""
    cfg = _cfg(persona="evaluator")
    pr = resolve_persona("op", cfg, PERSONAS_DIR)
    assert pr.eval_protocol_loaded
    assert pr.eval_protocol_path is not None
    assert pr.eval_protocol_text


def test_evaluator_protocol_loaded_via_role_fallback():
    """Evaluator protocol is loaded when the role fallback resolves to ``'evaluator'``."""
    cfg = _cfg(role="evaluator")
    pr = resolve_persona("op", cfg, PERSONAS_DIR)
    assert pr.persona_name == "evaluator"
    assert pr.eval_protocol_loaded


def test_evaluator_protocol_not_loaded_for_builder():
    """Non-evaluator persona does not trigger evaluator protocol loading."""
    cfg = _cfg(persona="builder")
    pr = resolve_persona("op", cfg, PERSONAS_DIR)
    assert not pr.eval_protocol_loaded
    assert pr.eval_protocol_path is None
    assert pr.eval_protocol_text is None


def test_evaluator_protocol_missing_does_not_fail(tmp_path):
    """Missing protocol file is tolerated; persona resolution still succeeds."""
    personas = tmp_path / "personas"
    personas.mkdir()
    (personas / "evaluator.md").write_text("# Evaluator\n", encoding="utf-8")
    # Intentionally skip creating evaluator-verification-protocol.md

    cfg = _cfg(persona="evaluator")
    pr = resolve_persona("op", cfg, personas)
    assert pr.persona_name == "evaluator"
    assert not pr.eval_protocol_loaded


def test_persona_differs_from_role_evaluator_persona_loads_protocol():
    """persona=evaluator, role=builder → protocol loaded (persona field wins)."""
    cfg = _cfg(persona="evaluator", role="builder")
    pr = resolve_persona("op", cfg, PERSONAS_DIR)
    assert pr.eval_protocol_loaded


def test_persona_builder_role_evaluator_no_protocol():
    """persona=builder, role=evaluator → NO protocol (persona field wins)."""
    cfg = _cfg(persona="builder", role="evaluator")
    pr = resolve_persona("op", cfg, PERSONAS_DIR)
    assert not pr.eval_protocol_loaded


# ---------------------------------------------------------------------------
# Content loading
# ---------------------------------------------------------------------------


def test_load_content_false_returns_empty_text(tmp_path):
    """``load_content=False`` validates existence only; text fields are empty."""
    personas = tmp_path / "personas"
    personas.mkdir()
    (personas / "builder.md").write_text("# Builder persona\n", encoding="utf-8")

    cfg = _cfg(persona="builder")
    pr = resolve_persona("op", cfg, personas, load_content=False)
    assert pr.persona_name == "builder"
    assert pr.persona_text == ""


def test_load_content_true_populates_text():
    """Default ``load_content=True`` returns the full file content."""
    cfg = _cfg(persona="builder")
    pr = resolve_persona("op", cfg, PERSONAS_DIR)
    assert len(pr.persona_text) > 50


def test_load_content_false_still_raises_on_missing_file(tmp_path):
    """``load_content=False`` still raises when the persona file is absent."""
    personas = tmp_path / "personas"
    personas.mkdir()
    cfg = _cfg(persona="ghost")
    with pytest.raises(RuntimeError, match="persona file missing"):
        resolve_persona("op", cfg, personas, load_content=False)


# ---------------------------------------------------------------------------
# PersonaResolution property
# ---------------------------------------------------------------------------


def test_eval_protocol_loaded_property_mirrors_path():
    """``eval_protocol_loaded`` is True iff ``eval_protocol_path`` is set."""
    cfg_builder = _cfg(persona="builder")
    pr_b = resolve_persona("op", cfg_builder, PERSONAS_DIR)
    assert pr_b.eval_protocol_loaded == (pr_b.eval_protocol_path is not None)

    cfg_eval = _cfg(persona="evaluator")
    pr_e = resolve_persona("op", cfg_eval, PERSONAS_DIR)
    assert pr_e.eval_protocol_loaded == (pr_e.eval_protocol_path is not None)
