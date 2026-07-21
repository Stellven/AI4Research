#!/usr/bin/env python3
"""Backlog-aware autoscaling helpers for Solar Harness concurrency surfaces."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
THIS_HARNESS_DIR = Path(__file__).resolve().parents[1]
SPRINTS_DIR = Path(os.environ.get("HARNESS_SPRINTS_DIR", HARNESS_DIR / "sprints"))
PHYSICAL_OPERATORS_PATH = Path(os.environ.get("SOLAR_MULTI_TASK_OPERATORS", HARNESS_DIR / "config" / "physical-operators.json"))


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


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


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
    return {}


def autoscaling_config(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    raw = policy.get("backlog_autoscaling") if isinstance(policy.get("backlog_autoscaling"), dict) else {}
    return dict(raw)


def snapshot_path(config: dict[str, Any] | None = None) -> Path:
    cfg = config or autoscaling_config()
    raw = str(cfg.get("snapshot_path") or "run/backlog-autoscale/latest.json").strip()
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return HARNESS_DIR / path


def _metrics_config(config: dict[str, Any]) -> dict[str, Any]:
    metrics = config.get("metrics") if isinstance(config.get("metrics"), dict) else {}
    return dict(metrics)


def _status_phase_count(status: str, phase: str) -> int:
    count = 0
    for path in SPRINTS_DIR.glob("*.status.json"):
        data = _load_json(path, {})
        if not isinstance(data, dict):
            continue
        if str(data.get("status") or "").strip().lower() != status:
            continue
        if str(data.get("phase") or "").strip().lower() != phase:
            continue
        count += 1
    return count


def backlog_metrics(config: dict[str, Any] | None = None) -> dict[str, int]:
    cfg = config or autoscaling_config()
    metrics = _metrics_config(cfg)
    result: dict[str, int] = {}
    for name, spec in metrics.items():
        if not isinstance(spec, dict):
            continue
        status = str(spec.get("status") or "").strip().lower()
        phase = str(spec.get("phase") or "").strip().lower()
        if not status or not phase:
            continue
        result[str(name)] = _status_phase_count(status, phase)
    return result


def operator_capacity_by_role() -> dict[str, dict[str, int]]:
    registry = _load_json(PHYSICAL_OPERATORS_PATH, {"operators": {}})
    operators = registry.get("operators") if isinstance(registry.get("operators"), dict) else {}
    result: dict[str, dict[str, int]] = {}
    for op_id, spec in operators.items():
        if not isinstance(spec, dict):
            continue
        role = str(spec.get("role") or "").strip().lower()
        if not role:
            continue
        bucket = result.setdefault(role, {"configured": 0, "enabled": 0, "available": 0})
        bucket["configured"] += 1
        if bool(spec.get("enabled", False)):
            bucket["enabled"] += 1
        if bool(spec.get("enabled", False)) and bool(spec.get("available", False)):
            bucket["available"] += 1
    return result


def _scaled_target(metric_value: int, spec: dict[str, Any]) -> int:
    try:
        base = int(spec.get("base", 1))
    except Exception:
        base = 1
    try:
        minimum = int(spec.get("min", base))
    except Exception:
        minimum = base
    try:
        maximum = int(spec.get("max", max(base, minimum)))
    except Exception:
        maximum = max(base, minimum)
    try:
        step = int(spec.get("step", 1))
    except Exception:
        step = 1
    try:
        backlog_per_step = int(spec.get("backlog_per_step", 0))
    except Exception:
        backlog_per_step = 0
    try:
        trigger = int(spec.get("trigger_backlog", 1))
    except Exception:
        trigger = 1

    value = base
    if backlog_per_step > 0 and metric_value >= trigger:
        increments = ((metric_value - trigger) // backlog_per_step) + 1
        value = base + increments * step
    value = max(minimum, value)
    value = min(maximum, value)
    return value


def _profile_targets(config: dict[str, Any], metrics: dict[str, int]) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
    raw_targets = config.get("profile_targets") if isinstance(config.get("profile_targets"), dict) else {}
    targets: dict[str, int] = {}
    reasoning: dict[str, dict[str, Any]] = {}
    for name, spec in raw_targets.items():
        if not isinstance(spec, dict):
            continue
        metric_name = str(spec.get("metric") or "").strip()
        metric_value = int(metrics.get(metric_name, 0))
        target = _scaled_target(metric_value, spec)
        targets[str(name)] = target
        reasoning[str(name)] = {
            "metric": metric_name,
            "metric_value": metric_value,
            "base": spec.get("base"),
            "max": spec.get("max"),
            "target": target,
        }
    return targets, reasoning


def _logical_targets(config: dict[str, Any], metrics: dict[str, int]) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
    raw_targets = config.get("logical_operator_targets") if isinstance(config.get("logical_operator_targets"), dict) else {}
    targets: dict[str, int] = {}
    reasoning: dict[str, dict[str, Any]] = {}
    for name, spec in raw_targets.items():
        if not isinstance(spec, dict):
            continue
        metric_name = str(spec.get("metric") or "").strip()
        metric_value = int(metrics.get(metric_name, 0))
        target = _scaled_target(metric_value, spec)
        targets[str(name)] = target
        reasoning[str(name)] = {
            "metric": metric_name,
            "metric_value": metric_value,
            "base": spec.get("base"),
            "max": spec.get("max"),
            "target": target,
        }
    return targets, reasoning


def _builder_pool_targets(config: dict[str, Any], metrics: dict[str, int]) -> dict[str, Any]:
    raw = config.get("builder_pool_targets") if isinstance(config.get("builder_pool_targets"), dict) else {}
    result: dict[str, Any] = {"desired_total": None, "groups": {}, "reasoning": {}}
    desired_total = raw.get("desired_total") if isinstance(raw.get("desired_total"), dict) else None
    if desired_total:
        metric_name = str(desired_total.get("metric") or "").strip()
        metric_value = int(metrics.get(metric_name, 0))
        target = _scaled_target(metric_value, desired_total)
        result["desired_total"] = target
        result["reasoning"]["desired_total"] = {
            "metric": metric_name,
            "metric_value": metric_value,
            "base": desired_total.get("base"),
            "max": desired_total.get("max"),
            "target": target,
        }
    groups = raw.get("groups") if isinstance(raw.get("groups"), dict) else {}
    for name, spec in groups.items():
        if not isinstance(spec, dict):
            continue
        metric_name = str(spec.get("metric") or "").strip()
        metric_value = int(metrics.get(metric_name, 0))
        target = _scaled_target(metric_value, spec)
        result["groups"][str(name)] = target
        result["reasoning"][str(name)] = {
            "metric": metric_name,
            "metric_value": metric_value,
            "base": spec.get("base"),
            "max": spec.get("max"),
            "target": target,
        }
    return result


def _global_targets(config: dict[str, Any], profile_targets: dict[str, int]) -> dict[str, int]:
    raw = config.get("global_limits") if isinstance(config.get("global_limits"), dict) else {}
    result: dict[str, int] = {}
    max_workers = raw.get("max_workers") if isinstance(raw.get("max_workers"), dict) else None
    if max_workers:
        names = [str(item) for item in (max_workers.get("profile_names") or []) if str(item).strip()]
        base = int(max_workers.get("base", 0) or 0)
        cap = int(max_workers.get("cap", 0) or 0)
        total = sum(int(profile_targets.get(name, 0)) for name in names)
        value = max(base, total)
        if cap > 0:
            value = min(value, cap)
        result["max_workers"] = max(1, value)
    return result


def build_snapshot(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    config = autoscaling_config(policy)
    metrics = backlog_metrics(config)
    capacities = operator_capacity_by_role()
    profile_targets, profile_reasoning = _profile_targets(config, metrics)
    logical_targets, logical_reasoning = _logical_targets(config, metrics)
    pool_targets = _builder_pool_targets(config, metrics)
    global_targets = _global_targets(config, profile_targets)
    return {
        "ok": True,
        "generated_at": _now(),
        "metrics": metrics,
        "role_capacity": capacities,
        "profile_limits": profile_targets,
        "profile_reasoning": profile_reasoning,
        "logical_operator_limits": logical_targets,
        "logical_operator_reasoning": logical_reasoning,
        "builder_pool": pool_targets,
        "global_limits": global_targets,
    }


def refresh_snapshot(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    config = autoscaling_config(policy)
    payload = build_snapshot(policy)
    path = snapshot_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return payload

