"""OperatorRouter selection + multimodal gate tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.gepa_optimizer.operator_router import (
    OperatorRouter,
    OperatorRoutingError,
    OperatorSpec,
)


def _write_config(path: Path, operators: dict[str, dict]) -> None:
    path.write_text(json.dumps({"version": 1, "operators": operators}), encoding="utf-8")


def _operator(
    name: str,
    *,
    role: str = "builder",
    cost_tier: str = "medium",
    enabled: bool = True,
    available: bool = True,
    input_modalities: list[str] | None = None,
) -> dict:
    return {
        "role": role,
        "provider": "test",
        "model": "fake",
        "cost_tier": cost_tier,
        "enabled": enabled,
        "available": available,
        **({"input_modalities": input_modalities} if input_modalities else {}),
    }


def test_load_real_physical_operators_json():
    router = OperatorRouter()
    # The actual file may or may not exist depending on environment; the
    # constructor either succeeds or raises an explicit error.
    usable = router.usable()
    assert isinstance(usable, list)


def test_select_filters_enabled_and_available(tmp_path):
    cfg = tmp_path / "ops.json"
    _write_config(
        cfg,
        {
            "op-a": _operator("op-a", cost_tier="low"),
            "op-b": _operator("op-b", enabled=False),
            "op-c": _operator("op-c", available=False),
        },
    )
    router = OperatorRouter(config_path=cfg)
    usable = [o.name for o in router.usable()]
    assert usable == ["op-a"]


def test_select_respects_cost_ceiling(tmp_path):
    cfg = tmp_path / "ops.json"
    _write_config(
        cfg,
        {
            "low-1": _operator("low-1", cost_tier="low"),
            "med-1": _operator("med-1", cost_tier="medium"),
            "high-1": _operator("high-1", cost_tier="high"),
        },
    )
    router = OperatorRouter(config_path=cfg)
    chosen = router.select(cost_ceiling="low")
    assert chosen.name == "low-1"


def test_select_for_image_task_requires_image_modality(tmp_path):
    cfg = tmp_path / "ops.json"
    _write_config(
        cfg,
        {
            "text-only": _operator("text-only", input_modalities=["text"]),
            "with-image": _operator(
                "with-image", cost_tier="low", input_modalities=["text", "image"]
            ),
        },
    )
    router = OperatorRouter(config_path=cfg)
    chosen = router.select_for_image_task()
    assert chosen.name == "with-image"


def test_select_for_image_task_raises_when_none_available(tmp_path):
    cfg = tmp_path / "ops.json"
    _write_config(
        cfg,
        {
            "text-only": _operator("text-only", input_modalities=["text"]),
        },
    )
    router = OperatorRouter(config_path=cfg)
    with pytest.raises(OperatorRoutingError):
        router.select_for_image_task()


def test_select_preferred_name(tmp_path):
    cfg = tmp_path / "ops.json"
    _write_config(
        cfg,
        {
            "alpha": _operator("alpha", cost_tier="low"),
            "beta": _operator("beta", cost_tier="low"),
        },
    )
    router = OperatorRouter(config_path=cfg)
    assert router.select(preferred_name="beta").name == "beta"


def test_operator_spec_does_not_leak_secret_fields(tmp_path):
    cfg = tmp_path / "ops.json"
    op_with_secret_field = _operator("alpha", cost_tier="low")
    op_with_secret_field["key_ref"] = "shhh"
    op_with_secret_field["auth_mode"] = "subscription"
    _write_config(cfg, {"alpha": op_with_secret_field})
    router = OperatorRouter(config_path=cfg)
    spec = router.select()
    # The dataclass purposely omits credential-shaped fields.
    assert not hasattr(spec, "key_ref")
    assert not hasattr(spec, "auth_mode")
