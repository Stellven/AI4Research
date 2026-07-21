#!/usr/bin/env python3
"""Refresh provider quota/rate snapshots and recommend a concurrency level.

This is intentionally best-effort. Some surfaces expose real quota/balance
APIs, while subscription TUIs often only reveal hard blockers through pane
text. Unknown-but-not-blocked capacity is treated as usable in aggressive
spend-down mode so paid quota is not left idle.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
PHYSICAL_OPERATORS_PATH = Path(os.environ.get("SOLAR_MULTI_TASK_OPERATORS", HARNESS_DIR / "config" / "physical-operators.json"))
SNAPSHOT_DIR = HARNESS_DIR / "run" / "quota-snapshots"
LATEST_SNAPSHOT = SNAPSHOT_DIR / "latest.json"
HISTORY_PATH = SNAPSHOT_DIR / "history.jsonl"

BLOCKED_STATES = {"cooldown", "quota_exhausted", "auth_expired", "disabled"}
LEVEL_ORDER = ["low", "normal", "high", "burst"]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_policy_module() -> Any | None:
    try:
        lib_dir = HARNESS_DIR / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        import concurrency_policy  # type: ignore

        return concurrency_policy
    except Exception:
        return None


def _load_runtime_module() -> Any | None:
    try:
        lib_dir = HARNESS_DIR / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        import operator_runtime  # type: ignore

        return operator_runtime
    except Exception:
        return None


def _model_key(op: dict[str, Any]) -> str:
    provider = str(op.get("provider") or "").lower()
    model = str(op.get("model") or op.get("model_config") or "").lower()
    if provider == "anthropic" or model in {"opus", "sonnet", "haiku"}:
        if "opus" in model:
            return "claude-opus"
        if "sonnet" in model:
            return "claude-sonnet"
        return "anthropic"
    if provider == "deepseek" or "deepseek" in model:
        return "deepseek"
    if provider == "glm" or "glm" in model:
        return "glm-5.1" if "5.1" in model or "51" in model else "glm"
    if provider == "openai" and "spark" in model:
        return "codex-gpt-5.3-spark"
    if provider == "openai" or "gpt" in model or "codex" in model:
        return "codex-gpt-5.5"
    if provider == "google" or "gemini" in model:
        return "antigravity-gemini"
    if provider == "local":
        return "local"
    return re.sub(r"[^a-z0-9._-]+", "-", model or provider or "unknown").strip("-")


def _runtime_state(op_id: str, op: dict[str, Any], runtime: Any | None) -> str:
    if not bool(op.get("enabled", False)):
        return "disabled"
    quota_state = str(op.get("quota_guard_state") or "").strip().lower()
    if quota_state and quota_state not in {"ok", "ready"}:
        return quota_state
    state = op.get("state") if isinstance(op.get("state"), dict) else {}
    state_name = str(state.get("runtime_state") or "").strip().lower()
    if state_name in BLOCKED_STATES:
        return state_name
    if runtime is not None:
        try:
            rt = str(runtime.get_operator_runtime_state(op_id) or "").strip().lower()
            if rt:
                return rt
        except Exception:
            pass
    return state_name or "idle"


def _quota_provider_probe(model_key: str) -> dict[str, Any]:
    script = HARNESS_DIR / "quota-providers.sh"
    if not script.exists():
        return {"status": "warn", "provider": "unknown", "metric": "quota", "value": "N/A", "note": "quota-providers-missing"}
    try:
        proc = subprocess.run(
            ["bash", str(script), model_key, "json"],
            cwd=str(HARNESS_DIR),
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if proc.stdout.strip():
            return json.loads(proc.stdout.strip().splitlines()[-1])
        return {"status": "warn", "provider": model_key, "metric": "quota", "value": "N/A", "note": proc.stderr.strip()[:200] or "empty"}
    except Exception as exc:
        return {"status": "warn", "provider": model_key, "metric": "quota", "value": "N/A", "note": f"probe-failed:{type(exc).__name__}"}


def _provider_probe(model_key: str, ops: list[dict[str, Any]]) -> dict[str, Any]:
    providers = {str(op.get("provider") or "").lower() for op in ops}
    if "local" in providers:
        return {"provider": "local", "status": "ok", "metric": "capacity", "value": "local", "unit": "", "note": "local-runtime"}
    if "google" in providers:
        return {
            "provider": "antigravity",
            "status": "estimated",
            "metric": "quota",
            "value": "N/A",
            "unit": "",
            "note": "agy CLI exposes no quota command; using auth/rate-limit blockers as hard signal",
        }
    if "openai" in providers:
        return {
            "provider": "codex",
            "status": "estimated",
            "metric": "quota",
            "value": "N/A",
            "unit": "",
            "note": "codex CLI exposes no quota command here; using runtime blockers and local logs",
        }
    if "glm" in providers:
        return {
            "provider": "glm",
            "status": "estimated",
            "metric": "quota",
            "value": "N/A",
            "unit": "",
            "note": "GLM coding quota requires web/monitor surface; using runtime blockers",
        }
    return _quota_provider_probe(model_key)


def _pending_pm_backlog_count() -> int:
    root = HARNESS_DIR / "run" / "pm-inbox"
    count = 0
    for path in root.glob("pm-*.json"):
        data = _load_json(path, {})
        status = str(data.get("status") or "").lower()
        if status not in {"completed", "cancelled", "failed"}:
            count += 1
    return count


def _recommend_level(*, policy: dict[str, Any], total: int, usable: int, hard_blocked: int, backlog: int) -> tuple[str, str]:
    dyn = policy.get("dynamic_concurrency") if isinstance(policy.get("dynamic_concurrency"), dict) else {}
    min_level = str(dyn.get("min_level") or "normal").lower()
    max_level = str(dyn.get("max_level") or "burst").lower()
    high_backlog = int(dyn.get("backlog_high_threshold", 6))
    burst_backlog = int(dyn.get("backlog_burst_threshold", 12))
    high_ratio = float(dyn.get("available_ratio_high", 0.45))
    burst_ratio = float(dyn.get("available_ratio_burst", 0.65))
    blocked_low = float(dyn.get("blocked_ratio_low", 0.70))
    usable_ratio = usable / max(total, 1)
    blocked_ratio = hard_blocked / max(total, 1)

    if blocked_ratio >= blocked_low:
        level, reason = "low", f"blocked_ratio={blocked_ratio:.2f}>=threshold"
    elif backlog >= burst_backlog and usable_ratio >= high_ratio:
        level, reason = "burst", f"backlog={backlog} and usable_ratio={usable_ratio:.2f}"
    elif usable_ratio >= burst_ratio and backlog >= high_backlog:
        level, reason = "burst", f"usable capacity healthy and backlog={backlog}"
    elif backlog >= high_backlog or usable_ratio >= high_ratio:
        level, reason = "high", f"spend_down backlog={backlog} usable_ratio={usable_ratio:.2f}"
    else:
        level, reason = "normal", f"steady backlog={backlog} usable_ratio={usable_ratio:.2f}"

    lo = LEVEL_ORDER.index(min_level) if min_level in LEVEL_ORDER else LEVEL_ORDER.index("normal")
    hi = LEVEL_ORDER.index(max_level) if max_level in LEVEL_ORDER else LEVEL_ORDER.index("burst")
    idx = min(max(LEVEL_ORDER.index(level), lo), hi)
    return LEVEL_ORDER[idx], reason


def refresh_snapshot(*, apply: bool = False) -> dict[str, Any]:
    registry = _load_json(PHYSICAL_OPERATORS_PATH, {"operators": {}})
    operators = registry.get("operators") if isinstance(registry.get("operators"), dict) else {}
    runtime = _load_runtime_module()
    policy_mod = _load_policy_module()
    policy = policy_mod.load_policy() if policy_mod else _load_json(HARNESS_DIR / "config" / "concurrency-policy.json", {})

    groups: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    total = usable = hard_blocked = 0
    for op_id, spec in operators.items():
        op = {"operator_id": op_id, **dict(spec)}
        if not bool(op.get("enabled", False)):
            continue
        key = _model_key(op)
        state = _runtime_state(op_id, op, runtime)
        available = bool(op.get("available", False)) and state not in BLOCKED_STATES
        total += 1
        usable += 1 if available else 0
        hard_blocked += 1 if state in {"cooldown", "quota_exhausted", "auth_expired"} else 0
        group = groups.setdefault(
            key,
            {
                "model_key": key,
                "provider": op.get("provider", "unknown"),
                "operators": 0,
                "usable": 0,
                "hard_blocked": 0,
                "states": {},
                "probe": {},
            },
        )
        group["operators"] += 1
        group["usable"] += 1 if available else 0
        group["hard_blocked"] += 1 if state in {"cooldown", "quota_exhausted", "auth_expired"} else 0
        group["states"][state] = int(group["states"].get(state, 0)) + 1
        rows.append({"operator_id": op_id, "model_key": key, "provider": op.get("provider", ""), "model": op.get("model", ""), "state": state, "usable": available})

    by_key: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_key.setdefault(str(row["model_key"]), []).append(row)
    for key, ops in by_key.items():
        groups[key]["probe"] = _provider_probe(key, ops)

    backlog = _pending_pm_backlog_count()
    recommended, reason = _recommend_level(policy=policy, total=total, usable=usable, hard_blocked=hard_blocked, backlog=backlog)
    payload = {
        "ok": True,
        "generated_at": _now(),
        "mode": ((policy.get("dynamic_concurrency") or {}).get("mode") if isinstance(policy.get("dynamic_concurrency"), dict) else "") or "aggressive_spend_down",
        "recommended_level": recommended,
        "recommendation_reason": reason,
        "apply_requested": apply,
        "backlog": backlog,
        "operators_total": total,
        "operators_usable": usable,
        "operators_hard_blocked": hard_blocked,
        "usable_ratio": round(usable / max(total, 1), 3),
        "hard_blocked_ratio": round(hard_blocked / max(total, 1), 3),
        "groups": groups,
        "operators": rows,
    }
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = str(LATEST_SNAPSHOT) + ".tmp"
    LATEST_SNAPSHOT.write_text("", encoding="utf-8") if False else None
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, LATEST_SNAPSHOT)
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Solar quota/rate snapshot and concurrency recommendation.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Kept for launchd semantics; dynamic policy reads latest snapshot automatically.")
    args = parser.parse_args()
    payload = refresh_snapshot(apply=bool(args.apply))
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(
            f"quota_refresh ok={payload['ok']} recommended={payload['recommended_level']} "
            f"usable={payload['operators_usable']}/{payload['operators_total']} backlog={payload['backlog']} "
            f"reason={payload['recommendation_reason']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
