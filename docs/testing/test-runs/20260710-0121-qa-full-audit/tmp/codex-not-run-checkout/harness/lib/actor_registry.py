#!/usr/bin/env python3
"""Actor registry loader with physical-operator derivation."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from harness_paths import resolve_runtime_harness_dir


HARNESS_DIR = resolve_runtime_harness_dir()
ACTORS_PATH = HARNESS_DIR / "config" / "agent-actors.json"
HOSTS_PATH = HARNESS_DIR / "config" / "actor-hosts.json"
PHYSICAL_OPERATORS_PATH = Path(
    os.environ.get(
        "SOLAR_MULTI_TASK_OPERATORS",
        HARNESS_DIR / "config" / "physical-operators.json",
    )
)

VALID_ROLES = {
    "planner",
    "builder",
    "evaluator",
    "knowledge-extractor",
    "router",
    "auditor",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = {k: copy.deepcopy(v) for k, v in base.items()}
        for key, value in override.items():
            merged[key] = _deep_merge(merged.get(key), value) if key in merged else copy.deepcopy(value)
        return merged
    return copy.deepcopy(override)


def _load_hosts(path: Path) -> dict[str, Any]:
    return _read_json(path).get("hosts", {})


def _infer_host_id(operator_id: str, operator_cfg: dict[str, Any], hosts: dict[str, Any]) -> str:
    explicit = str(operator_cfg.get("host_id") or "").strip()
    if explicit:
        return explicit
    pane = str(operator_cfg.get("pane") or "").strip()
    owner = str(operator_cfg.get("owner_host") or "").strip()
    display_name = str(operator_cfg.get("display_name") or "").strip().lower()
    if "mini" in operator_id or "mac mini" in display_name or "mac-mini" in owner or pane.startswith("solar-harness-multi-task:"):
        if "mini" in hosts:
            return "mini"
    return next(iter(hosts.keys()), "mini")


def _infer_tmux_session(operator_cfg: dict[str, Any]) -> str | None:
    pane = str(operator_cfg.get("pane") or "").strip()
    if ":" not in pane:
        return None
    return pane.split(":", 1)[0] or None


def _derive_display_meta(operator_cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "display_name": str(operator_cfg.get("display_name") or "N/A"),
        "tmux_session": _infer_tmux_session(operator_cfg),
        "tmux_window": None,
        "tmux_pane_index": None,
    }


def _derive_capability(role: str, operator_cfg: dict[str, Any]) -> dict[str, int]:
    preferred_for = {str(item).lower() for item in operator_cfg.get("preferred_for") or []}
    task_classes = {str(item).lower() for item in operator_cfg.get("task_classes") or []}
    capability: dict[str, int] = {"reliability": 3}
    if role == "planner":
        capability["planning"] = 5
        capability["research"] = 4
    elif role == "builder":
        capability["coding"] = 5
        capability["debugging"] = 4
        capability["testing"] = 4
    elif role == "evaluator":
        capability["testing"] = 5
        capability["debugging"] = 4
        capability["research"] = 3
    elif role == "knowledge-extractor":
        capability["research"] = 4
    if "browser" in preferred_for or operator_cfg.get("backend") == "browser-agent" or "browser" in task_classes:
        capability["browser"] = 5
    if "multimodal" in preferred_for or "vision" in preferred_for:
        capability["multimodal"] = 4
    if operator_cfg.get("context_tier") == "high" or "long-context" in preferred_for:
        capability["long_context"] = 5
    return capability


def _derive_capability_profile(role: str, operator_cfg: dict[str, Any]) -> dict[str, int]:
    base = {
        "architecture_reasoning": 1,
        "code_impl": 1,
        "root_cause_debug": 1,
        "test_generation": 1,
        "test_execution": 1,
        "research_synthesis": 1,
        "academic_critique": 1,
        "browser_use": 0,
        "gui_use": 0,
        "long_context": 1,
        "multi_agent_coordination": 1,
        "speed": 2,
    }
    if role == "planner":
        base.update({"architecture_reasoning": 5, "research_synthesis": 4, "academic_critique": 4, "multi_agent_coordination": 4})
    elif role == "builder":
        base.update({"code_impl": 5, "root_cause_debug": 4, "test_generation": 4, "test_execution": 3})
    elif role == "evaluator":
        base.update({"root_cause_debug": 4, "test_generation": 3, "test_execution": 4, "academic_critique": 4})
    elif role == "knowledge-extractor":
        base.update({"research_synthesis": 4, "browser_use": 4, "gui_use": 1})
    if operator_cfg.get("context_tier") == "high":
        base["long_context"] = max(base["long_context"], 4)
    preferred_for = [str(x) for x in (operator_cfg.get("preferred_for") or [])]
    task_classes = [str(x) for x in (operator_cfg.get("task_classes") or [])]
    if "browser" in " ".join(preferred_for + task_classes):
        base["browser_use"] = max(base["browser_use"], 5)
    latency = str(operator_cfg.get("latency_tier") or "").lower()
    if latency == "low":
        base["speed"] = 5
    elif latency == "medium":
        base["speed"] = 3
    return base


def _derive_risk_profile(role: str, operator_cfg: dict[str, Any]) -> dict[str, Any]:
    git_commit = "allowed" if role in {"planner", "builder", "evaluator"} and operator_cfg.get("backend") != "command" else "denied"
    return {
        "allowed_write_scope": "harness",
        "allowed_shell_scope": "allowed",
        "allowed_network": "allowed",
        "allowed_secrets": "secret_ref_only",
        "destructive_actions": "denied",
        "git_commit": git_commit,
        "git_push": "denied",
        "payment_or_external_action": "denied",
        "requires_human_for": ["git_push", "payment_or_external_action"] if git_commit == "allowed" else ["git_commit", "git_push", "payment_or_external_action"],
    }


def _derive_cost_profile(operator_cfg: dict[str, Any]) -> dict[str, Any]:
    cost_tier = str(operator_cfg.get("cost_tier") or "medium").lower()
    quota_cycle = str(operator_cfg.get("quota_cycle") or "none").lower()
    context_tier = str(operator_cfg.get("context_tier") or "").lower()
    token_budget = "large" if context_tier == "high" else "medium"
    effort = "heavy" if cost_tier == "high" else "light" if cost_tier == "low" else "medium"
    return {
        "cost_tier": cost_tier if cost_tier in {"low", "medium", "high"} else "medium",
        "token_budget_class": "xlarge" if context_tier == "high" and cost_tier == "high" else token_budget,
        "quota_period": quota_cycle if quota_cycle in {"none", "daily", "weekly", "monthly", "api_balance"} else "none",
        "reserve_ratio": 0.0,
        "effort": effort,
        "prefer_for": list(operator_cfg.get("preferred_for") or []),
        "avoid_for": list(operator_cfg.get("avoid_for") or []),
    }


def _derive_quota(operator_cfg: dict[str, Any]) -> dict[str, Any]:
    quota_cycle = str(operator_cfg.get("quota_cycle") or "none").lower()
    auth_mode = str(operator_cfg.get("auth_mode") or "").strip().lower()
    backend = str(operator_cfg.get("backend") or "").strip().lower()
    quota_type = f"{backend or 'runtime'}-{auth_mode or quota_cycle or 'none'}"
    return {
        "quota_type": quota_type,
        "period": quota_cycle or "none",
        "on_exhausted": "disable_and_fallback",
    }


def _derive_policy(risk_profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "write_files": "allowed" if risk_profile.get("allowed_write_scope") != "denied" else "denied",
        "run_shell": "allowed" if risk_profile.get("allowed_shell_scope") == "allowed" else "denied",
        "network": "allowed" if risk_profile.get("allowed_network") == "allowed" else "denied",
        "secrets_access": risk_profile.get("allowed_secrets") or "secret_ref_only",
        "git_commit": risk_profile.get("git_commit") or "denied",
    }


def _derive_fallback_ladder(operator_cfg: dict[str, Any]) -> list[dict[str, str]]:
    fallback = str(operator_cfg.get("fallback_profile") or "").strip()
    if not fallback:
        return []
    return [{"actor_id": fallback, "condition": "profile_fallback"}]


def derive_actor_from_operator(
    operator_id: str,
    operator_cfg: dict[str, Any],
    *,
    hosts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hosts = hosts or {}
    role = str(operator_cfg.get("role") or "").strip()
    if role not in VALID_ROLES:
        role = "builder"
    host_id = _infer_host_id(operator_id, operator_cfg, hosts)
    risk_profile = _derive_risk_profile(role, operator_cfg)
    capability_profile = _derive_capability_profile(role, operator_cfg)
    mailbox_base = f"actors/{operator_id}"
    renewable = str(operator_cfg.get("launch_cmd_kind") or "").strip().lower() == "interactive_repl"
    return {
        "actor_id": operator_id,
        "host_id": host_id,
        "operator_alias": operator_id,
        "aliases": [operator_id],
        "role": role,
        "display_meta": _derive_display_meta(operator_cfg),
        "lease": {
            "acquired_at": None,
            "expires_at": None,
            "renewable": renewable,
            "preemptible": False,
            "heartbeat_timeout_sec": 120,
            "lease_id": None,
            "holder_sprint": None,
        },
        "mailbox": {
            "inbox": f"{mailbox_base}/inbox",
            "outbox": f"{mailbox_base}/outbox",
            "logs": f"{mailbox_base}/logs",
            "state_json": f"{mailbox_base}/state.json",
            "heartbeat_json": f"{mailbox_base}/heartbeat.json",
        },
        "context_packet_ref": {"path": None, "packet_id": None},
        "evidence_ledger_ref": {"path": f"{mailbox_base}/evidence"},
        "capability": _derive_capability(role, operator_cfg),
        "capability_profile": capability_profile,
        "risk_profile": risk_profile,
        "cost_profile": _derive_cost_profile(operator_cfg),
        "quota": _derive_quota(operator_cfg),
        "policy": _derive_policy(risk_profile),
        "evidence": {
            "last_smoke_at": None,
            "last_smoke_result": None,
            "last_task_at": None,
            "last_task_id": None,
            "last_task_result": None,
            "provenance": f"derived from physical-operators.json:{operator_id}",
        },
        "persona_binding": {
            "persona_id": str(operator_cfg.get("persona") or role),
            "persona_file": f"personas/{str(operator_cfg.get('persona') or role)}.md",
            "knobs_override": {},
        },
        "fallback_ladder": _derive_fallback_ladder(operator_cfg),
    }


def load_actor_registry(
    actors_path: Path = ACTORS_PATH,
    *,
    physical_operators_path: Path | None = None,
    hosts_path: Path | None = None,
) -> dict[str, Any]:
    config_dir = actors_path.parent if actors_path.name.endswith(".json") else actors_path
    if physical_operators_path is None:
        physical_operators_path = config_dir / "physical-operators.json"
    if hosts_path is None:
        hosts_path = config_dir / "actor-hosts.json"
    explicit = _read_json(actors_path)
    physical = _read_json(physical_operators_path)
    hosts = _load_hosts(hosts_path)
    derived: dict[str, Any] = {}
    for operator_id, operator_cfg in (physical.get("operators") or {}).items():
        if not isinstance(operator_cfg, dict):
            continue
        derived[operator_id] = derive_actor_from_operator(operator_id, operator_cfg, hosts=hosts)

    actors: dict[str, Any] = {}
    explicit_actors = explicit.get("actors") if isinstance(explicit.get("actors"), dict) else {}
    all_ids = set(derived.keys()) | set(explicit_actors.keys())
    for actor_id in sorted(all_ids):
        if actor_id in derived and actor_id in explicit_actors:
            actors[actor_id] = _deep_merge(derived[actor_id], explicit_actors[actor_id])
        elif actor_id in derived:
            actors[actor_id] = copy.deepcopy(derived[actor_id])
        else:
            actors[actor_id] = copy.deepcopy(explicit_actors[actor_id])

    return {
        "version": int(explicit.get("version") or physical.get("version") or 1),
        "updated_at": explicit.get("updated_at") or physical.get("updated_at") or "",
        "actors": actors,
        "provenance": {
            "mode": "physical_derived_with_actor_overrides",
            "actors_path": str(actors_path),
            "physical_operators_path": str(physical_operators_path),
        },
    }


def validate_actor_registry(
    actors_path: Path = ACTORS_PATH,
    *,
    physical_operators_path: Path | None = None,
    hosts_path: Path | None = None,
) -> dict[str, Any]:
    config_dir = actors_path.parent if actors_path.name.endswith(".json") else actors_path
    if physical_operators_path is None:
        physical_operators_path = config_dir / "physical-operators.json"
    if hosts_path is None:
        hosts_path = config_dir / "actor-hosts.json"
    explicit = _read_json(actors_path)
    physical = _read_json(physical_operators_path)
    hosts = _load_hosts(hosts_path)
    registry = load_actor_registry(
        actors_path,
        physical_operators_path=physical_operators_path,
        hosts_path=hosts_path,
    )
    actors = registry.get("actors") if isinstance(registry.get("actors"), dict) else {}
    explicit_actors = explicit.get("actors") if isinstance(explicit.get("actors"), dict) else {}
    physical_ops = physical.get("operators") if isinstance(physical.get("operators"), dict) else {}

    errors: list[str] = []
    warnings: list[str] = []
    for actor_id, actor in actors.items():
        if not isinstance(actor, dict):
            errors.append(f"{actor_id}: actor spec must be an object")
            continue
        if actor.get("actor_id") != actor_id:
            errors.append(f"{actor_id}: actor_id mismatch")
        operator_alias = str(actor.get("operator_alias") or "").strip()
        if not operator_alias:
            errors.append(f"{actor_id}: missing operator_alias")
        elif operator_alias not in physical_ops:
            errors.append(f"{actor_id}: operator_alias={operator_alias} missing from physical operators")
        host_id = str(actor.get("host_id") or "").strip()
        if not host_id:
            errors.append(f"{actor_id}: missing host_id")
        elif host_id not in hosts:
            errors.append(f"{actor_id}: host_id={host_id} missing from actor-hosts")
        for index, step in enumerate(actor.get("fallback_ladder") or []):
            target = str((step or {}).get("actor_id") or "").strip()
            if target and target not in actors:
                errors.append(
                    f"{actor_id}: fallback_ladder[{index}] target={target} missing from actor registry"
                )

    for operator_id in physical_ops:
        if operator_id not in actors:
            errors.append(f"{operator_id}: missing derived actor")
    for actor_id in explicit_actors:
        if actor_id not in physical_ops:
            warnings.append(
                f"{actor_id}: explicit actor override has no matching physical operator"
            )

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "actor_count": len(actors),
            "physical_operator_count": len(physical_ops),
            "explicit_override_count": len(explicit_actors),
            "error_count": len(errors),
            "warning_count": len(warnings),
        },
    }
