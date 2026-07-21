"""Policy-driven gate decisions for AutoSci side effects.

This module keeps the mode matrix centralized so bridge actions can decide
whether a side effect should remain HITL-gated or may be auto-executed for
local AutoSci parity demos.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping


class AutoSciGateMode(str, Enum):
    STRICT_HITL = "strict_hitl"
    SAFE = "safe"
    PARITY_DEMO = "parity_demo"
    UNSAFE_NATIVE = "unsafe_native"
    AUTOSCI_NATIVE = "autosci_native"


class SideEffectType(str, Enum):
    READ_LOCAL = "read_local"
    WRITE_ARTIFACT = "write_artifact"
    WIKI_MUTATION = "wiki_mutation"
    LOCAL_COMMAND = "local_command"
    TEX_COMPILE = "tex_compile"
    BROWSER_RENDER = "browser_render"
    PNG_EXPORT = "png_export"
    NETWORK_FETCH = "network_fetch"
    EMAIL_SEND = "email_send"
    REMOTE_EXECUTION = "remote_execution"
    PROTECTED_CONFIG_MUTATION = "protected_config_mutation"
    CREDENTIAL_MUTATION = "credential_mutation"
    DESTRUCTIVE_MUTATION = "destructive_mutation"


_SIDE_EFFECT_ALIASES: dict[str, SideEffectType] = {
    "artifact_write": SideEffectType.WRITE_ARTIFACT,
    "artifacts_write": SideEffectType.WRITE_ARTIFACT,
    "canvas_write": SideEffectType.WIKI_MUTATION,
    "graph_read": SideEffectType.READ_LOCAL,
    "local_web_server": SideEffectType.LOCAL_COMMAND,
    "obsidian_canvas_write": SideEffectType.WIKI_MUTATION,
    "overflow_probe": SideEffectType.BROWSER_RENDER,
    "provider_fetch": SideEffectType.NETWORK_FETCH,
    "remote_execution": SideEffectType.REMOTE_EXECUTION,
    "render_browser": SideEffectType.BROWSER_RENDER,
    "serve_probe": SideEffectType.BROWSER_RENDER,
    "wiki_write": SideEffectType.WIKI_MUTATION,
}

_RISK_ENV: dict[SideEffectType, str] = {
    SideEffectType.NETWORK_FETCH: "SOLAR_AUTOSCI_ALLOW_NETWORK",
    SideEffectType.EMAIL_SEND: "SOLAR_AUTOSCI_ALLOW_EMAIL",
    SideEffectType.REMOTE_EXECUTION: "SOLAR_AUTOSCI_ALLOW_REMOTE",
    SideEffectType.DESTRUCTIVE_MUTATION: "SOLAR_AUTOSCI_ALLOW_DESTRUCTIVE",
    SideEffectType.PROTECTED_CONFIG_MUTATION: "SOLAR_AUTOSCI_ALLOW_PROTECTED_CONFIG",
    SideEffectType.CREDENTIAL_MUTATION: "SOLAR_AUTOSCI_ALLOW_CREDENTIAL_MUTATION",
}

_ALWAYS_SAFE = {SideEffectType.READ_LOCAL, SideEffectType.WRITE_ARTIFACT}
_PARITY_DEMO_AUTO = {
    SideEffectType.READ_LOCAL,
    SideEffectType.WRITE_ARTIFACT,
    SideEffectType.WIKI_MUTATION,
    SideEffectType.LOCAL_COMMAND,
    SideEffectType.TEX_COMPILE,
    SideEffectType.BROWSER_RENDER,
    SideEffectType.PNG_EXPORT,
}
_UNSAFE_NATIVE_AUTO = {*_PARITY_DEMO_AUTO, SideEffectType.NETWORK_FETCH}


@dataclass(frozen=True)
class GateDecision:
    mode: str
    action: str
    side_effects: list[str]
    allowed: bool
    blocked: bool
    require_hitl: bool
    require_approval_ref: bool
    require_runtime_evidence: bool
    require_before_after_artifacts: bool
    execute_side_effects: bool
    proof_required: bool
    proof_best_effort: bool
    sandbox_required: bool
    allowed_write_roots: list[str]
    allow_network: bool
    allow_email: bool
    allow_remote: bool
    allow_destructive: bool
    synthetic_approval_ref: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _mode_from_raw(raw: str | None) -> AutoSciGateMode | None:
    if not raw:
        return None
    normalized = str(raw).strip().lower().replace("-", "_")
    for mode in AutoSciGateMode:
        if normalized == mode.value:
            return mode
    return None


def _config_mode(config: Mapping[str, Any] | None) -> str:
    if not config:
        return ""
    raw = config.get("gate_mode") or config.get("autosci_mode")
    return str(raw or "")


def resolve_gate_mode(
    envelope: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> AutoSciGateMode:
    """Resolve the configured gate mode.

    Priority is envelope inputs, then environment, then optional config, then
    strict HITL.
    """

    envelope_inputs = envelope.get("inputs") if isinstance(envelope, Mapping) else None
    merged_inputs = inputs if isinstance(inputs, Mapping) else envelope_inputs if isinstance(envelope_inputs, Mapping) else {}
    environ = env if env is not None else os.environ
    candidates = [
        str(merged_inputs.get("gate_mode") or ""),
        str(merged_inputs.get("autosci_mode") or ""),
        str(environ.get("SOLAR_AUTOSCI_GATE_MODE") or ""),
        _config_mode(config),
    ]
    for candidate in candidates:
        mode = _mode_from_raw(candidate)
        if mode:
            return mode
    return AutoSciGateMode.STRICT_HITL


def _normalize_side_effect(effect: str | SideEffectType) -> tuple[SideEffectType | None, str]:
    raw = str(effect.value if isinstance(effect, SideEffectType) else effect).strip()
    normalized = raw.lower().replace("-", "_")
    if normalized in _SIDE_EFFECT_ALIASES:
        return _SIDE_EFFECT_ALIASES[normalized], raw
    for known in SideEffectType:
        if normalized == known.value:
            return known, raw
    return None, raw


def _synthetic_ref(mode: AutoSciGateMode, action: str, enabled: bool) -> str:
    if not enabled:
        return ""
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    safe_action = action.replace(" ", "-").replace("/", "-")
    return f"policy:auto:{mode.value}:{safe_action}:{timestamp}"


def _allowed_by_env(effect: SideEffectType, env: Mapping[str, str]) -> bool:
    var = _RISK_ENV.get(effect)
    return bool(var and _truthy(env.get(var)))


def _effect_allowed(mode: AutoSciGateMode, effect: SideEffectType, env: Mapping[str, str]) -> tuple[bool, str, bool]:
    if mode == AutoSciGateMode.AUTOSCI_NATIVE:
        return True, "autosci_native allows side effects without Solar gate blocking.", False
    if effect in _ALWAYS_SAFE:
        return True, f"{effect.value} is allowed in {mode.value}.", False
    if mode == AutoSciGateMode.STRICT_HITL:
        return False, f"{effect.value} requires HITL approval in strict_hitl.", True
    if mode == AutoSciGateMode.SAFE:
        return False, f"{effect.value} requires HITL approval in safe mode.", True
    if mode == AutoSciGateMode.PARITY_DEMO:
        if effect in _PARITY_DEMO_AUTO:
            return True, f"{effect.value} is auto-allowed in parity_demo.", False
        if effect == SideEffectType.NETWORK_FETCH:
            if _allowed_by_env(effect, env):
                return True, "network_fetch is allowed by SOLAR_AUTOSCI_ALLOW_NETWORK=1.", False
            return False, "network_fetch requires SOLAR_AUTOSCI_ALLOW_NETWORK=1 in parity_demo.", False
        if _allowed_by_env(effect, env):
            return True, f"{effect.value} is allowed by explicit environment opt-in.", False
        return False, f"{effect.value} requires explicit environment opt-in in parity_demo.", False
    if mode == AutoSciGateMode.UNSAFE_NATIVE:
        if effect in _UNSAFE_NATIVE_AUTO:
            return True, f"{effect.value} is auto-allowed in unsafe_native.", False
        if _allowed_by_env(effect, env):
            return True, f"{effect.value} is allowed by explicit environment opt-in.", False
        return False, f"{effect.value} requires explicit environment opt-in in unsafe_native.", False
    return False, f"{effect.value} is not allowed by unknown gate mode {mode.value}.", True


def decide_gate(
    action: str,
    side_effects: list[str | SideEffectType],
    envelope: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> GateDecision:
    environ = env if env is not None else os.environ
    mode = resolve_gate_mode(envelope=envelope, inputs=inputs, env=environ, config=config)
    normalized: list[SideEffectType] = []
    reasons: list[str] = []
    warnings: list[str] = []
    require_hitl = False
    blocked = False
    for raw in side_effects:
        effect, original = _normalize_side_effect(raw)
        if effect is None:
            blocked = True
            warnings.append(f"Unknown side effect `{original}` is blocked until classified.")
            continue
        normalized.append(effect)
        allowed, reason, hitl = _effect_allowed(mode, effect, environ)
        reasons.append(reason)
        if not allowed:
            blocked = True
        if hitl:
            require_hitl = True

    side_effect_names = [effect.value for effect in normalized]
    allowed = not blocked
    proof_required = mode in {AutoSciGateMode.STRICT_HITL, AutoSciGateMode.SAFE, AutoSciGateMode.PARITY_DEMO}
    proof_best_effort = mode in {AutoSciGateMode.UNSAFE_NATIVE, AutoSciGateMode.AUTOSCI_NATIVE}
    has_material_side_effect = any(effect not in _ALWAYS_SAFE for effect in normalized)
    auto_mode = mode in {
        AutoSciGateMode.PARITY_DEMO,
        AutoSciGateMode.UNSAFE_NATIVE,
        AutoSciGateMode.AUTOSCI_NATIVE,
    }
    execute_side_effects = allowed and (auto_mode or not has_material_side_effect)
    synthetic_ref = _synthetic_ref(mode, action, execute_side_effects and has_material_side_effect and auto_mode)
    if synthetic_ref:
        warnings.append(f"Auto-approved by gate policy mode `{mode.value}`; no human approval was requested.")
    if mode == AutoSciGateMode.AUTOSCI_NATIVE:
        warnings.append("Solar gates are bypassed in autosci_native mode; evidence is best-effort only.")

    return GateDecision(
        mode=mode.value,
        action=action,
        side_effects=side_effect_names,
        allowed=allowed,
        blocked=blocked,
        require_hitl=require_hitl,
        require_approval_ref=require_hitl,
        require_runtime_evidence=proof_required and require_hitl,
        require_before_after_artifacts=proof_required and require_hitl,
        execute_side_effects=execute_side_effects,
        proof_required=proof_required,
        proof_best_effort=proof_best_effort,
        sandbox_required=mode in {AutoSciGateMode.SAFE, AutoSciGateMode.PARITY_DEMO},
        allowed_write_roots=["artifacts/autosci", "artifacts/scientific"],
        allow_network=mode in {AutoSciGateMode.UNSAFE_NATIVE, AutoSciGateMode.AUTOSCI_NATIVE}
        or _truthy(environ.get("SOLAR_AUTOSCI_ALLOW_NETWORK")),
        allow_email=mode == AutoSciGateMode.AUTOSCI_NATIVE or _truthy(environ.get("SOLAR_AUTOSCI_ALLOW_EMAIL")),
        allow_remote=mode == AutoSciGateMode.AUTOSCI_NATIVE or _truthy(environ.get("SOLAR_AUTOSCI_ALLOW_REMOTE")),
        allow_destructive=mode == AutoSciGateMode.AUTOSCI_NATIVE
        or _truthy(environ.get("SOLAR_AUTOSCI_ALLOW_DESTRUCTIVE")),
        synthetic_approval_ref=synthetic_ref,
        reasons=reasons,
        warnings=warnings,
    )
