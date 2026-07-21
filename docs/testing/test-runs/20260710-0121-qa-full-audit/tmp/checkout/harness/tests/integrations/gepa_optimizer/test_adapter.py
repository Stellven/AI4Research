"""Adapter unit tests (gepa-free)."""

from __future__ import annotations

import pytest

from integrations.gepa_optimizer.adapter import (
    AdapterError,
    GEPAAdapter,
    GEPAConfig,
)


def test_config_default_validates():
    cfg = GEPAConfig()
    assert cfg.max_iterations >= 1
    assert 0.0 <= cfg.temperature <= 2.0


def test_config_rejects_zero_iterations():
    with pytest.raises(ValueError):
        GEPAConfig(max_iterations=0)


def test_config_rejects_negative_temperature():
    with pytest.raises(ValueError):
        GEPAConfig(temperature=-0.1)


def test_config_rejects_negative_refiner_rounds():
    with pytest.raises(ValueError):
        GEPAConfig(refiner_rounds=-1)


def test_adapter_requires_gepaconfig():
    import integrations.gepa_optimizer.adapter as adapter_mod

    # Pretend gepa is available so we exercise the type check rather than the
    # missing-package branch.
    adapter_mod._GEPA_AVAILABLE = True
    try:
        with pytest.raises(TypeError):
            GEPAAdapter("not a config")  # type: ignore[arg-type]
    finally:
        adapter_mod._GEPA_AVAILABLE = False


def test_adapter_when_gepa_absent_raises_adapter_error():
    import integrations.gepa_optimizer.adapter as adapter_mod

    adapter_mod._GEPA_AVAILABLE = False
    try:
        with pytest.raises(AdapterError):
            GEPAAdapter(GEPAConfig())
    finally:
        # Leave the flag as-is; other tests reset it themselves.
        pass


def test_wrap_evaluator_passthrough():
    import integrations.gepa_optimizer.adapter as adapter_mod

    adapter_mod._GEPA_AVAILABLE = True
    try:
        adapter = GEPAAdapter(GEPAConfig())
        fn = lambda c: 1.0  # noqa: E731
        assert adapter.wrap_evaluator(fn) is fn
        with pytest.raises(TypeError):
            adapter.wrap_evaluator(42)  # type: ignore[arg-type]
    finally:
        adapter_mod._GEPA_AVAILABLE = False
