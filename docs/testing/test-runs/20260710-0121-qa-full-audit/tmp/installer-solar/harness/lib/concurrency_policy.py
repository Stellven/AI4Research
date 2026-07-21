#!/usr/bin/env python3
"""Unified Solar concurrency and builder-pool policy helpers."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
THIS_HARNESS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_LEVEL = "normal"
KNOWN_LEVELS = {"low", "normal", "high", "burst"}


def _candidate_policy_paths() -> list[Path]:
    paths: list[Path] = []
    env_path = os.environ.get("SOLAR_CONCURRENCY_POLICY")
    if env_path:
        paths.append(Path(env_path).expanduser())
    paths.append(HARNESS_DIR / "config" / "concurrency-policy.json")
    paths.append(THIS_HARNESS_DIR / "config" / "concurrency-policy.json")

    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def load_policy() -> dict[str, Any]:
    for path in _candidate_policy_paths():
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["_policy_path"] = str(path)
                    return data
        except Exception:
            continue
    return {
        "version": 1,
        "active_level": DEFAULT_LEVEL,
        "levels": {
            DEFAULT_LEVEL: {
                "graph_max_parallel": 4,
                "builder_dispatch_limit": 5,
                "drain_max_items": 4,
            }
        },
        "builder_pool": {"enabled": False, "groups": {}},
        "recovery": {},
        "_policy_path": "builtin",
    }


def active_level(policy: dict[str, Any] | None = None) -> str:
    policy = policy or load_policy()
    override_key = str(policy.get("env_override") or "SOLAR_CONCURRENCY_LEVEL")
    env_value = str(os.environ.get(override_key) or "").strip().lower()
    if env_value:
        return env_value if env_value in KNOWN_LEVELS else DEFAULT_LEVEL
    dynamic = dynamic_concurrency_config(policy)
    if bool(dynamic.get("enabled", False)):
        snapshot_level = _dynamic_snapshot_level(dynamic)
        if snapshot_level in KNOWN_LEVELS:
            return snapshot_level
    value = str(policy.get("active_level") or DEFAULT_LEVEL).strip().lower()
    return value if value in KNOWN_LEVELS else DEFAULT_LEVEL


def level_settings(policy: dict[str, Any] | None = None, level: str | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    selected = (level or active_level(policy)).strip().lower()
    levels = policy.get("levels") if isinstance(policy.get("levels"), dict) else {}
    settings = levels.get(selected) or levels.get(DEFAULT_LEVEL) or {}
    return dict(settings) if isinstance(settings, dict) else {}


def effective_max_parallel(default: int = 8, *, scope: str = "graph") -> int:
    policy = load_policy()
    settings = level_settings(policy)
    key_by_scope = {
        "graph": "graph_max_parallel",
        "builder": "builder_dispatch_limit",
        "drain": "drain_max_items",
    }
    key = key_by_scope.get(scope, scope)
    try:
        value = int(settings.get(key, default))
    except Exception:
        value = default
    return max(1, value)


def recovery_settings(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    recovery = policy.get("recovery") if isinstance(policy.get("recovery"), dict) else {}
    return dict(recovery)


def dynamic_concurrency_config(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    dynamic = policy.get("dynamic_concurrency") if isinstance(policy.get("dynamic_concurrency"), dict) else {}
    return dict(dynamic)


def backlog_autoscaling_config(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    raw = policy.get("backlog_autoscaling") if isinstance(policy.get("backlog_autoscaling"), dict) else {}
    return dict(raw)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _backlog_snapshot_path(config: dict[str, Any]) -> Path:
    raw_path = str(config.get("snapshot_path") or "run/backlog-autoscale/latest.json").strip()
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = HARNESS_DIR / path
    return path


def _backlog_autoscaling_snapshot(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    config = backlog_autoscaling_config(policy)
    if not bool(config.get("enabled", False)):
        return {}
    path = _backlog_snapshot_path(config)
    ttl = int(config.get("snapshot_ttl_seconds", 60) or 60)
    needs_refresh = True
    if path.exists():
        try:
            if ttl <= 0 or time.time() - path.stat().st_mtime <= ttl:
                needs_refresh = False
        except Exception:
            needs_refresh = True
    if needs_refresh:
        try:
            if str(THIS_HARNESS_DIR / "lib") not in sys.path:
                sys.path.insert(0, str(THIS_HARNESS_DIR / "lib"))
            import backlog_autoscaler  # type: ignore

            backlog_autoscaler.refresh_snapshot(policy)
        except Exception:
            pass
    return _load_json(path)


def backlog_autoscaling_snapshot(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    return _backlog_autoscaling_snapshot(policy)


def effective_profile_max_parallel(profile_name: str, default: int, policy: dict[str, Any] | None = None) -> int:
    snapshot = _backlog_autoscaling_snapshot(policy)
    targets = snapshot.get("profile_limits") if isinstance(snapshot.get("profile_limits"), dict) else {}
    try:
        value = int(targets.get(str(profile_name), default))
    except Exception:
        value = default
    return max(1, value)


def effective_logical_max_parallel(operator_type: str, default: int, policy: dict[str, Any] | None = None) -> int:
    snapshot = _backlog_autoscaling_snapshot(policy)
    targets = snapshot.get("logical_operator_limits") if isinstance(snapshot.get("logical_operator_limits"), dict) else {}
    try:
        value = int(targets.get(str(operator_type), default))
    except Exception:
        value = default
    return max(1, value)


def effective_global_max_workers(default: int, policy: dict[str, Any] | None = None) -> int:
    snapshot = _backlog_autoscaling_snapshot(policy)
    targets = snapshot.get("global_limits") if isinstance(snapshot.get("global_limits"), dict) else {}
    try:
        value = int(targets.get("max_workers", default))
    except Exception:
        value = default
    return max(1, value)


def _dynamic_snapshot_level(dynamic: dict[str, Any]) -> str:
    raw_path = str(dynamic.get("snapshot_path") or "").strip()
    if not raw_path:
        return ""
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = HARNESS_DIR / path
    try:
        if not path.exists():
            return ""
        ttl = int(dynamic.get("snapshot_ttl_seconds", 600))
        if ttl > 0 and time.time() - path.stat().st_mtime > ttl:
            return ""
        payload = json.loads(path.read_text(encoding="utf-8"))
        level = str(payload.get("recommended_level") or "").strip().lower()
    except Exception:
        return ""
    return level if level in KNOWN_LEVELS else ""


def role_pool_spillover_config(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    spillover = policy.get("role_pool_spillover") if isinstance(policy.get("role_pool_spillover"), dict) else {}
    return dict(spillover)


def role_spillover_spec(role: str, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    spillover = role_pool_spillover_config(policy)
    roles = spillover.get("roles") if isinstance(spillover.get("roles"), dict) else {}
    spec = roles.get(str(role or "").strip().lower())
    return dict(spec) if isinstance(spec, dict) else {}


def role_spillover_enabled(role: str, policy: dict[str, Any] | None = None) -> bool:
    spillover = role_pool_spillover_config(policy)
    if not bool(spillover.get("enabled", False)):
        return False
    spec = role_spillover_spec(role, policy)
    return bool(spec.get("enabled", False))


def builder_pool_config(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    pool = policy.get("builder_pool") if isinstance(policy.get("builder_pool"), dict) else {}
    return dict(pool)


def infer_builder_group(op: dict[str, Any]) -> str:
    pool = op.get("builder_pool") if isinstance(op.get("builder_pool"), dict) else {}
    explicit = str(pool.get("group") or "").strip().lower()
    if explicit:
        return explicit

    provider = str(op.get("provider") or "").strip().lower()
    model = str(op.get("model") or op.get("model_config") or "").strip().lower()
    op_id = str(op.get("operator_id") or "").strip().lower()
    combined = " ".join([provider, model, op_id])
    if "glm" in combined:
        return "glm-5.1"
    if "sonnet" in combined:
        return "sonnet"
    if "thunderomlx" in combined or "qwen3.6" in combined:
        return "thunderomlx"
    if "deepseek" in combined and "flash" in combined:
        return "deepseek-v4-flash"
    if "spark" in combined and ("codex" in combined or "gpt-5.3" in combined):
        return "codex-gpt-5.3-spark"
    if "codex" in combined or "gpt-5.5" in combined:
        return "codex-gpt-5.5-medium"
    if "antigravity" in combined or "gemini-3.5" in combined:
        return "antigravity-gemini-3.5-flash"
    return ""


def is_pool_member(op: dict[str, Any]) -> bool:
    pool = op.get("builder_pool") if isinstance(op.get("builder_pool"), dict) else {}
    if "enabled" in pool:
        return bool(pool.get("enabled"))
    return False


def pool_group_priority(group: str, policy: dict[str, Any] | None = None) -> int:
    pool = builder_pool_config(policy)
    groups = pool.get("groups") if isinstance(pool.get("groups"), dict) else {}
    spec = groups.get(group) if isinstance(groups.get(group), dict) else {}
    try:
        return int(spec.get("priority", 0))
    except Exception:
        return 0


def pool_group_desired(group: str, policy: dict[str, Any] | None = None) -> int:
    pool = builder_pool_config(policy)
    groups = pool.get("groups") if isinstance(pool.get("groups"), dict) else {}
    spec = groups.get(group) if isinstance(groups.get(group), dict) else {}
    snapshot = _backlog_autoscaling_snapshot(policy)
    dynamic_pool = snapshot.get("builder_pool") if isinstance(snapshot.get("builder_pool"), dict) else {}
    dynamic_groups = dynamic_pool.get("groups") if isinstance(dynamic_pool.get("groups"), dict) else {}
    try:
        return int(dynamic_groups.get(group, spec.get("desired", 0)))
    except Exception:
        return 0


def builder_pool_desired_total(policy: dict[str, Any] | None = None) -> int:
    pool = builder_pool_config(policy)
    snapshot = _backlog_autoscaling_snapshot(policy)
    dynamic_pool = snapshot.get("builder_pool") if isinstance(snapshot.get("builder_pool"), dict) else {}
    try:
        return int(dynamic_pool.get("desired_total", pool.get("desired_total", 0)))
    except Exception:
        return int(pool.get("desired_total", 0) or 0)


def builder_pool_enabled(policy: dict[str, Any] | None = None) -> bool:
    return bool(builder_pool_config(policy).get("enabled", False))


def pool_member_ids(registry: dict[str, Any]) -> list[str]:
    operators = registry.get("operators") if isinstance(registry.get("operators"), dict) else {}
    return [
        str(op_id)
        for op_id, spec in operators.items()
        if isinstance(spec, dict) and is_pool_member({"operator_id": op_id, **spec})
    ]
