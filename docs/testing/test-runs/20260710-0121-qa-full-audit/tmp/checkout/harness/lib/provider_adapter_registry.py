#!/usr/bin/env python3
"""Provider/model adapter registry for Solar Harness routing surfaces."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import re

import model_registry


PROVIDER_ALIASES = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "google": "gemini",
    "gemini": "gemini",
    "deepseek": "deepseek",
    "zhipu": "zhipu",
    "glm": "zhipu",
    "openai": "openai",
    "chatgpt": "openai",
    "browser_agent_chatgpt": "openai",
    "local": "local",
}


@dataclass(frozen=True)
class ProviderAdapter:
    provider: str
    aliases: tuple[str, ...]
    model_aliases: tuple[str, ...] = ()
    backend_aliases: tuple[str, ...] = ()
    supported_backends: tuple[str, ...] = ()
    default_route_model: str = ""
    doctor_kind: str = "none"
    probe_auth_key: str = ""
    probe_base_url_key: str = ""
    probe_model_key: str = ""
    default_base_url: str = ""


ADAPTERS: dict[str, ProviderAdapter] = {
    "anthropic": ProviderAdapter(
        provider="anthropic",
        aliases=("anthropic", "claude"),
        model_aliases=("claude", "sonnet", "opus"),
        backend_aliases=("claude-cli", "claude-sdk"),
        supported_backends=("claude-cli", "claude-sdk"),
        doctor_kind="claude_native",
    ),
    "gemini": ProviderAdapter(
        provider="gemini",
        aliases=("gemini", "google"),
        model_aliases=("gemini",),
        backend_aliases=("gemini-cli", "gemini-sdk"),
        supported_backends=("gemini-cli", "gemini-sdk", "command"),
        doctor_kind="gemini_adapter",
    ),
    "deepseek": ProviderAdapter(
        provider="deepseek",
        aliases=("deepseek",),
        model_aliases=("deepseek", "ds"),
        supported_backends=("claude-cli", "command"),
        default_route_model="deepseek",
        doctor_kind="env_proxy",
        probe_auth_key="deepseek_auth",
        probe_base_url_key="deepseek_base_url",
        default_base_url="https://api.deepseek.com/anthropic",
    ),
    "zhipu": ProviderAdapter(
        provider="zhipu",
        aliases=("zhipu", "glm"),
        model_aliases=("glm", "zhipu"),
        supported_backends=("claude-cli", "command"),
        default_route_model="glm",
        doctor_kind="env_proxy",
        probe_auth_key="zhipu_auth",
        probe_base_url_key="zhipu_base_url",
        probe_model_key="zhipu_model",
    ),
    "openai": ProviderAdapter(
        provider="openai",
        aliases=("openai", "chatgpt", "browser_agent_chatgpt"),
        model_aliases=("chatgpt", "gpt"),
        supported_backends=("command",),
        default_route_model="chatgpt-5.5",
        doctor_kind="browser_wrapper",
    ),
    "local": ProviderAdapter(
        provider="local",
        aliases=("local", "thunderomlx", "omlx"),
        model_aliases=("thunder", "omlx"),
        supported_backends=("local", "command", "claude-cli"),
        default_route_model="thunderomlx",
        doctor_kind="local_proxy",
        probe_base_url_key="thunderomlx_base_url",
        default_base_url="http://127.0.0.1:8002",
    ),
}


def canonical_provider(value: str) -> str:
    raw = str(value or "").strip().lower()
    return PROVIDER_ALIASES.get(raw, raw)


def adapter_for(
    *,
    provider: str = "",
    model: str = "",
    backend: str = "",
    registry_path: Path | None = None,
) -> ProviderAdapter | None:
    canonical = resolve_provider(
        model=model,
        backend=backend,
        provider=provider,
        registry_path=registry_path,
    )
    return ADAPTERS.get(canonical)


def _registry_spec(model: str, registry_path: Path | None = None) -> dict[str, Any] | None:
    alias = str(model or "").strip()
    if not alias:
        return None
    try:
        reg = model_registry.load_registry(registry_path or model_registry.REGISTRY_PATH)
        return model_registry.spec(reg, alias)
    except BaseException:
        return None


def resolve_provider(model: str = "", backend: str = "", provider: str = "", registry_path: Path | None = None) -> str:
    explicit = canonical_provider(provider)
    if explicit:
        return explicit
    raw_backend = str(backend or "").strip().lower()
    raw_model = str(model or "").strip().lower()
    for adapter in ADAPTERS.values():
        if raw_backend in adapter.backend_aliases:
            return adapter.provider
        if any(token and token in raw_model for token in adapter.model_aliases):
            return adapter.provider
    spec = _registry_spec(model, registry_path=registry_path)
    if spec:
        return canonical_provider(str(spec.get("provider") or ""))
    if re.search(r"thunder|omlx", raw_model):
        return "local"
    return "anthropic"


def route_model_alias(provider: str, model: str, registry_path: Path | None = None) -> str:
    canonical = resolve_provider(model=model, provider=provider, registry_path=registry_path)
    spec = _registry_spec(model, registry_path=registry_path)
    if spec:
        model_key = str(spec.get("model_key") or "").strip()
        if model_key:
            return model_key
    adapter = ADAPTERS.get(canonical)
    if canonical == "zhipu":
        value = str(model or "").strip().lower()
        if "4.7" in value or "47" in value:
            return "glm-4.7"
    if canonical == "local":
        return "thunderomlx"
    if canonical == "openai":
        return str(model or "").strip().lower() or "chatgpt-5.5"
    if adapter and adapter.default_route_model:
        return adapter.default_route_model
    return str(model or "").strip().lower()


def probe_hints(
    *,
    provider: str = "",
    model: str = "",
    backend: str = "",
    registry_path: Path | None = None,
) -> dict[str, Any]:
    adapter = adapter_for(provider=provider, model=model, backend=backend, registry_path=registry_path)
    if not adapter:
        return {
            "provider": canonical_provider(provider),
            "doctor_kind": "none",
            "supported_backends": (),
            "probe_auth_key": "",
            "probe_base_url_key": "",
            "probe_model_key": "",
            "default_base_url": "",
        }
    return {
        "provider": adapter.provider,
        "doctor_kind": adapter.doctor_kind,
        "supported_backends": adapter.supported_backends,
        "probe_auth_key": adapter.probe_auth_key,
        "probe_base_url_key": adapter.probe_base_url_key,
        "probe_model_key": adapter.probe_model_key,
        "default_base_url": adapter.default_base_url,
    }


def validate_operator_spec(
    operator_id: str,
    operator_cfg: dict[str, Any],
    *,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    raw_provider = str(operator_cfg.get("provider") or "").strip()
    backend = str(operator_cfg.get("backend") or "").strip().lower()
    model = str(operator_cfg.get("model") or "").strip()
    canonical = resolve_provider(
        model=model,
        backend=backend,
        provider=raw_provider,
        registry_path=registry_path,
    )
    adapter = ADAPTERS.get(canonical)
    if not adapter:
        errors.append(f"unknown provider={raw_provider or canonical or 'N/A'}")
    if not backend:
        errors.append("missing backend")
    elif adapter and adapter.supported_backends and backend not in adapter.supported_backends:
        errors.append(
            f"backend={backend} not supported for provider={adapter.provider} "
            f"(allowed={','.join(adapter.supported_backends)})"
        )
    routed_model = route_model_alias(canonical, model, registry_path=registry_path)
    if not routed_model:
        errors.append("model routing produced empty alias")
    model_binding = operator_cfg.get("model_binding")
    if isinstance(model_binding, dict):
        binding_provider = canonical_provider(str(model_binding.get("provider") or "").strip())
        if binding_provider and canonical and binding_provider != canonical:
            errors.append(
                f"model_binding.provider={binding_provider} mismatches provider={canonical}"
            )
        binding_alias = str(model_binding.get("alias") or "").strip().lower()
        if binding_alias and routed_model and binding_alias != routed_model.lower():
            warnings.append(
                f"model_binding.alias={binding_alias} differs from routed_model={routed_model}"
            )
    return {
        "operator_id": operator_id,
        "provider": canonical,
        "backend": backend,
        "model": model,
        "routed_model": routed_model,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def validate_physical_operator_registry(
    registry: dict[str, Any] | None = None,
    *,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    payload = registry if registry is not None else {}
    if not payload:
        path = registry_path or (model_registry.REGISTRY_PATH.parent / "physical-operators.json")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    operators = payload.get("operators") if isinstance(payload.get("operators"), dict) else {}
    by_operator: dict[str, Any] = {}
    errors: list[str] = []
    warnings: list[str] = []
    provider_counts: dict[str, int] = {}
    for operator_id, operator_cfg in operators.items():
        if not isinstance(operator_cfg, dict):
            errors.append(f"{operator_id}: operator spec must be an object")
            continue
        result = validate_operator_spec(operator_id, operator_cfg, registry_path=registry_path)
        by_operator[operator_id] = result
        provider = str(result.get("provider") or "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        errors.extend(f"{operator_id}: {msg}" for msg in result["errors"])
        warnings.extend(f"{operator_id}: {msg}" for msg in result["warnings"])
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "by_operator": by_operator,
        "summary": {
            "operator_count": len(operators),
            "provider_counts": provider_counts,
            "error_count": len(errors),
            "warning_count": len(warnings),
        },
    }
