#!/usr/bin/env python3
"""tmux-backed DAG worker pool for Solar Harness multi-task execution."""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

try:
    import readline  # type: ignore
except Exception:  # pragma: no cover - readline may be unavailable in minimal Python builds
    readline = None  # type: ignore

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
SPRINTS_DIR = Path(os.environ.get("HARNESS_SPRINTS_DIR", HARNESS_DIR / "sprints"))
RUN_DIR = HARNESS_DIR / "run" / "multi-task"
SESSION = os.environ.get("SOLAR_HARNESS_MULTI_TASK_SESSION", "solar-harness-multi-task")
MAIN_SESSION = os.environ.get("SOLAR_HARNESS_MAIN_SESSION", "solar-harness")
LAB_SESSION = os.environ.get("SOLAR_HARNESS_LAB_SESSION", "solar-harness-lab")
PROFILE_PATH = Path(os.environ.get("SOLAR_MULTI_TASK_PROFILES", HARNESS_DIR / "config" / "multi-task-profiles.json"))
PHYSICAL_OPERATORS_PATH = Path(os.environ.get("SOLAR_MULTI_TASK_OPERATORS", HARNESS_DIR / "config" / "physical-operators.json"))
SCREEN_HISTORY_PATH = Path(os.environ.get("SOLAR_MULTI_TASK_SCREEN_HISTORY", RUN_DIR / "screen-history.txt"))
GRAPH_SUMMARY_CACHE_PATH = Path(os.environ.get("SOLAR_MULTI_TASK_GRAPH_SUMMARY_CACHE", RUN_DIR / "graph-summary-cache.json"))
DISPATCH_LEDGER_PATH = Path(os.environ.get("SOLAR_DISPATCH_LEDGER", HARNESS_DIR / "run" / "dispatch-ledger.jsonl"))
DEFAULT_MAX_WORKERS = int(os.environ.get("SOLAR_MULTI_TASK_MAX_WORKERS", "2") or "2")
DEFAULT_INTERVAL = int(os.environ.get("SOLAR_MULTI_TASK_INTERVAL_SEC", "15") or "15")
DEFAULT_COOLDOWN = int(os.environ.get("SOLAR_MULTI_TASK_LAUNCH_COOLDOWN_SEC", "30") or "30")
DEFAULT_MEMORY_RESERVE_GB = float(os.environ.get("SOLAR_MULTI_TASK_MEMORY_RESERVE_GB", "4") or "4")
DEFAULT_QUOTA_BACKOFF = int(os.environ.get("SOLAR_MULTI_TASK_QUOTA_BACKOFF_SEC", "900") or "900")
GRAPH_SUMMARY_CACHE_TTL_SEC = int(os.environ.get("SOLAR_MULTI_TASK_GRAPH_SUMMARY_CACHE_TTL_SEC", "5") or "5")
PROBE_CACHE_PATH = Path(os.environ.get("SOLAR_MULTI_TASK_PROBE_CACHE", RUN_DIR / "capability-probes.json"))

# Normalized fallback ladders for observability surfaces such as
# ``solar_monitor_bridge``. Keep these lightweight and model-agnostic enough
# for health reporting; scheduling logic can still apply richer scoring.
NORM_FALLBACK_LADDERS: dict[str, list[str]] = {
    "CODE_IMPL": [
        "mini-antigravity-gemini35-flash-high",
        "mini-claude-sonnet-builder",
    ],
    "ARCH_DESIGN": [
        "mini-claude-sonnet-builder",
        "mini-antigravity-gemini35-flash-high",
    ],
    "REVIEW": [
        "mini-claude-sonnet-builder",
        "mini-antigravity-gemini35-flash-high",
    ],
}

DEFAULT_PROFILE_CONFIG: dict[str, Any] = {
    "defaults": {"profile": "builder", "backend": "claude-cli", "max_workers": 2},
    "profiles": {
        "builder": {
            "role": "builder",
            "label": "构建者",
            "persona": "builder",
            "backend": "claude-cli",
            "model": "sonnet",
            "approval_mode": "yolo",
            "best_for": ["implementation", "debugging", "tests"],
            "max_parallel": 2,
        },
        "planner": {
            "role": "planner",
            "label": "规划者",
            "persona": "planner",
            "backend": "claude-cli",
            "model": "sonnet",
            "approval_mode": "auto_edit",
            "best_for": ["planning", "architecture"],
            "max_parallel": 1,
        },
        "evaluator": {
            "role": "evaluator",
            "label": "审判者",
            "persona": "evaluator",
            "backend": "claude-cli",
            "model": "opus",
            "approval_mode": "auto_edit",
            "best_for": ["verification", "review"],
            "max_parallel": 1,
        },
        "pm": {
            "role": "pm",
            "label": "PM",
            "persona": "pm",
            "backend": "claude-cli",
            "model": "sonnet",
            "approval_mode": "auto_edit",
            "best_for": ["requirements", "acceptance"],
            "max_parallel": 1,
        },
        "gemini-builder": {
            "role": "builder",
            "label": "Gemini 构建者",
            "persona": "builder",
            "backend": "gemini-cli",
            "model": "gemini",
            "approval_mode": "auto_edit",
            "best_for": ["large-context", "implementation"],
            "max_parallel": 1,
        },
        "gemini-evaluator": {
            "role": "evaluator",
            "label": "Gemini 评审者",
            "persona": "evaluator",
            "backend": "gemini-cli",
            "model": "gemini",
            "approval_mode": "auto_edit",
            "best_for": ["verification", "review", "evidence"],
            "max_parallel": 1,
        },
        "knowledge-extractor": {
            "role": "builder",
            "label": "知识库抽取器",
            "persona": "builder",
            "backend": "command",
            "model": "thunderomlx",
            "approval_mode": "default",
            "best_for": ["knowledge-extraction", "wiki-ingest", "qmd-indexing"],
            "command": "PATH=\"/opt/homebrew/bin:/usr/local/bin:$PATH\" python3 \"$HARNESS_DIR/tools/thunderomlx_knowledge_extract_agent.py\"",
            "max_parallel": 1,
        },
    },
}

sys.path.insert(0, str(HARNESS_DIR / "lib"))
from graph_scheduler import (  # noqa: E402
    load_graph,
    node_status,
    ready_nodes,
    save_graph,
    set_node_status,
    write_scope_conflict,
)

ACTIVE_TASK_STATUSES = {"queued", "dispatched", "running"}
TERMINAL_TASK_STATUSES = {"completed", "failed", "failed_missing_handoff", "failed_stale_handoff", "cancelled"}
EFFECTIVE_TERMINAL_TASK_STATUSES = TERMINAL_TASK_STATUSES | {"completed_aligned", "failed_aligned"}
TASK_STALE_WARN_SEC = int(os.environ.get("SOLAR_MULTI_TASK_STALE_WARN_SEC", "1800") or "1800")
PROFILE_ALIASES = {
    "builder_main": "builder",
    "builder-main": "builder",
    "builder_parallel": "builder",
    "builder-parallel": "builder",
    "implementation": "builder",
    "implementer": "builder",
    "reviewer": "evaluator",
    "verifier": "evaluator",
    "judge": "evaluator",
    "architect": "planner",
    "planning": "planner",
    "product": "pm",
    "product-manager": "pm",
}
QUOTA_RE = re.compile(
    r"(?:api\s+error|error|failed|exception|http)\D{0,40}(?:429|rate[- ]?limit|quota)|"
    r"you(?:'|’)ve hit (?:your |your org(?:anization)?(?:'s)? )?(?:monthly )?(?:usage )?limit|"
    r"resets\s+\d|api usage billing|upgrade your plan|"
    r"(?:rate[- ]?limit|quota)\D{0,40}(?:exceeded|reached|hit|error|failed)",
    re.I,
)
AUTH_RE = re.compile(
    r"not logged in|not authenticated|auth(?:entication)?(?:\\s+)?(?:failed|expired|required)|"
    r"failed to get oauth token|error getting token source|failed to set auth token|"
    r"no active conversation|login required|invalid credentials",
    re.I,
)


def load_profiles() -> dict[str, Any]:
    def _apply_concurrency_knob(data: dict[str, Any]) -> dict[str, Any]:
        try:
            if str(HARNESS_DIR / "lib") not in sys.path:
                sys.path.insert(0, str(HARNESS_DIR / "lib"))
            import concurrency_policy  # type: ignore

            builder_limit = int(concurrency_policy.effective_max_parallel(2, scope="builder"))
            defaults = data.setdefault("defaults", {})
            if isinstance(defaults, dict):
                default_workers = int(defaults.get("max_workers", builder_limit) or builder_limit)
                defaults["max_workers"] = concurrency_policy.effective_global_max_workers(default_workers)
                defaults["concurrency_level"] = concurrency_policy.active_level()
            for name, spec in (data.get("profiles") or {}).items():
                if not isinstance(spec, dict):
                    continue
                role = str(spec.get("role") or "").strip().lower()
                base_limit = int(spec.get("max_parallel", 1) or 1)
                effective_limit = int(concurrency_policy.effective_profile_max_parallel(str(name), base_limit))
                if role == "builder":
                    effective_limit = min(effective_limit, builder_limit)
                spec["max_parallel"] = max(1, effective_limit)
        except Exception:
            pass
        return data

    if PROFILE_PATH.exists():
        try:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            if isinstance(data.get("profiles"), dict):
                return _apply_concurrency_knob(data)
        except Exception:
            pass
    return _apply_concurrency_knob(json.loads(json.dumps(DEFAULT_PROFILE_CONFIG)))


def effective_scheduler_max_workers(default: int) -> int:
    try:
        if str(HARNESS_DIR / "lib") not in sys.path:
            sys.path.insert(0, str(HARNESS_DIR / "lib"))
        import concurrency_policy  # type: ignore

        return max(1, int(concurrency_policy.effective_global_max_workers(default)))
    except Exception:
        return max(1, int(default or 1))


def load_physical_operators() -> dict[str, Any]:
    if PHYSICAL_OPERATORS_PATH.exists():
        try:
            data = json.loads(PHYSICAL_OPERATORS_PATH.read_text(encoding="utf-8"))
            if isinstance(data.get("operators"), dict):
                return data
        except Exception:
            pass
    return {"version": 1, "operators": {}}


def profile_names() -> list[str]:
    return sorted((load_profiles().get("profiles") or {}).keys())


def normalize_profile_name(name: str, profiles: dict[str, Any] | None = None) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    if profiles and raw in profiles:
        return raw
    key = raw.lower().replace(" ", "-")
    return PROFILE_ALIASES.get(key, PROFILE_ALIASES.get(key.replace("-", "_"), raw))


def physical_operator_names() -> list[str]:
    return sorted((load_physical_operators().get("operators") or {}).keys())


def _host_from_url(value: str) -> str:
    m = re.match(r"^[a-z]+://([^/]+)", str(value or ""))
    return m.group(1) if m else str(value or "")


_MODEL_ENV_CACHE: dict[str, Any] | None = None


def model_env_snapshot() -> dict[str, Any]:
    """Return provider config presence without exposing secrets."""
    global _MODEL_ENV_CACHE
    if _MODEL_ENV_CACHE is not None:
        return _MODEL_ENV_CACHE
    script = f"""
HARNESS_DIR={shlex.quote(str(HARNESS_DIR))}
source "$HARNESS_DIR/model-config.sh" 2>/dev/null || true
source "$HOME/.solar/brain-router/.env" 2>/dev/null || true
python3 - <<'PY'
import json, os
payload = {{
  "zhipu_auth": bool(os.environ.get("ZHIPU_AUTH_TOKEN") or os.environ.get("ZHIPU_API_KEY")),
  "zhipu_base_url": os.environ.get("ZHIPU_BASE_URL", ""),
  "zhipu_model": os.environ.get("ZHIPU_MODEL", ""),
  "deepseek_auth": bool(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_AUTH_TOKEN")),
  "deepseek_base_url": os.environ.get("DEEPSEEK_BASE_URL", "") or "https://api.deepseek.com/anthropic",
  "solar_agent_cmd": bool(os.environ.get("SOLAR_MULTI_TASK_AGENT_CMD")),
  "thunderomlx_base_url": os.environ.get("THUNDEROMLX_BASE_URL", ""),
}}
print(json.dumps(payload, ensure_ascii=False))
PY
"""
    try:
        out = subprocess.check_output(["bash", "-lc", script], text=True, stderr=subprocess.DEVNULL, timeout=5)
        _MODEL_ENV_CACHE = json.loads(out.strip() or "{}")
    except Exception:
        _MODEL_ENV_CACHE = {}
    return _MODEL_ENV_CACHE


def model_provider(model: str, backend: str = "") -> str:
    value = str(model or "").strip().lower()
    if str(backend or "").strip().lower() in {"gemini-cli", "gemini-sdk"} or "gemini" in value:
        return "gemini"
    if "deepseek" in value or value.startswith("ds"):
        return "deepseek"
    if "glm" in value or "zhipu" in value:
        return "zhipu"
    if "thunder" in value or "omlx" in value:
        return "local"
    return "anthropic"


def provider_model_alias(provider: str, model: str) -> str:
    value = str(model or "").strip().lower()
    if provider == "zhipu":
        if "4.7" in value or "47" in value:
            return "glm-4.7"
        return "glm"
    if provider == "deepseek":
        return "deepseek"
    if provider == "local":
        return os.environ.get("THUNDEROMLX_ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    return value


def profile_model_with_compatible_override(profile: dict[str, Any], model_override: str = "", node_model: str = "") -> str:
    base_model = str(profile.get("model") or "sonnet")
    backend = str(profile.get("backend") or "claude-cli")
    if model_override:
        return str(model_override)
    if not node_model:
        return base_model
    base_provider = model_provider(base_model, backend)
    node_provider = model_provider(str(node_model), backend)
    if base_provider == node_provider:
        return str(node_model)
    return base_model


def read_probe_cache() -> dict[str, Any]:
    try:
        data = json.loads(PROBE_CACHE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_probe_cache(data: dict[str, Any]) -> None:
    PROBE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    json_write(PROBE_CACHE_PATH, data)


def probe_key(provider: str, model: str, backend: str) -> str:
    return f"{provider}:{backend}:{str(model or '').lower()}"


def capability_for_profile(profile: dict[str, Any], include_probe: bool = True) -> dict[str, Any]:
    backend = str(profile.get("backend") or "claude-cli")
    model = str(profile.get("model") or "")
    provider = model_provider(model, backend)
    status = "ok"
    evidence = "N/A"
    env = model_env_snapshot()

    if backend == "claude-cli":
        claude = shutil.which("claude")
        if not claude:
            status = "error"
            evidence = "claude missing"
        elif provider == "anthropic":
            evidence = f"cli={claude} route=native-empty-mcp"
        elif provider == "zhipu":
            if env.get("zhipu_auth") and env.get("zhipu_base_url"):
                evidence = f"host={_host_from_url(str(env.get('zhipu_base_url')))} auth=set model={env.get('zhipu_model') or 'N/A'}"
            else:
                status = "error"
                evidence = "zhipu auth/base_url missing"
        elif provider == "deepseek":
            if env.get("deepseek_auth"):
                status = "warn"
                evidence = f"host={_host_from_url(str(env.get('deepseek_base_url')))} auth=set live_probe=pending"
            else:
                status = "error"
                evidence = "deepseek key missing"
        elif provider == "local":
            base_url = str(env.get("thunderomlx_base_url") or os.environ.get("THUNDEROMLX_BASE_URL") or "http://127.0.0.1:8002")
            local_model = os.environ.get("THUNDEROMLX_LOCAL_MODEL", "Qwen3.6-35b-a3b")
            evidence = f"host={_host_from_url(base_url)} auth=local proxy_model={provider_model_alias('local', model)} local_model={local_model}"
        else:
            status = "error"
            evidence = f"unsupported claude-cli provider={provider}"
    elif backend in {"gemini-cli", "gemini-sdk"}:
        adapter = HARNESS_DIR / "lib" / "gemini_adapter.py"
        try:
            proc = subprocess.run([sys.executable, str(adapter), "doctor"], text=True, capture_output=True, timeout=10)
            payload = json.loads(proc.stdout or "{}")
            cli = payload.get("cli") or {}
            if proc.returncode == 0 and cli.get("ready", cli.get("ok")):
                evidence = (
                    f"path={cli.get('path') or 'missing'} auth={cli.get('default_auth') or 'N/A'} "
                    f"oauth={cli.get('oauth_creds')}"
                )
            else:
                status = "error"
                evidence = cli.get("warning") or "gemini not ready"
        except Exception as exc:
            status = "error"
            evidence = f"gemini doctor failed:{type(exc).__name__}"
    elif backend == "command":
        if profile.get("command") or os.environ.get("SOLAR_MULTI_TASK_AGENT_CMD") or env.get("solar_agent_cmd"):
            evidence = "command configured"
        else:
            status = "error"
            evidence = "command missing"
    else:
        status = "error"
        evidence = f"unknown backend={backend}"

    if include_probe:
        cache = read_probe_cache().get(probe_key(provider, model, backend))
        if isinstance(cache, dict):
            cached_status = str(cache.get("status") or "")
            if cached_status in {"ok", "warn", "error"}:
                status = cached_status
                evidence = f"{evidence}; probe={cached_status}:{cache.get('evidence') or 'N/A'}"

    return {
        "profile": profile.get("name") or "N/A",
        "role": profile.get("role") or "N/A",
        "backend": backend,
        "model": model,
        "provider": provider,
        "status": status,
        "evidence": evidence,
    }


def capability_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, spec in sorted((load_profiles().get("profiles") or {}).items()):
        profile = dict(spec)
        profile["name"] = name
        rows.append(capability_for_profile(profile))
    return rows


def capability_summary(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = rows if rows is not None else capability_rows()
    counts = {"ok": 0, "warn": 0, "error": 0}
    enabled: list[str] = []
    disabled: list[str] = []
    for row in rows:
        status = str(row.get("status") or "warn")
        if status not in counts:
            status = "warn"
        counts[status] += 1
        label = f"{row.get('profile', 'N/A')}:{row.get('model', 'N/A')}"
        compact_label = str(row.get("profile", "N/A"))
        if status == "ok":
            enabled.append(label)
        else:
            disabled.append(f"{compact_label}({status})")
    return {
        "ok": counts["ok"],
        "warn": counts["warn"],
        "error": counts["error"],
        "enabled": enabled,
        "disabled": disabled,
    }


def format_capability_summary(summary: dict[str, Any], limit: int = 5) -> str:
    enabled = summary.get("enabled") or []
    disabled = summary.get("disabled") or []
    enabled_text = ",".join(enabled[:limit]) if enabled else "N/A"
    disabled_text = ",".join(disabled[:limit]) if disabled else "N/A"
    if len(enabled) > limit:
        enabled_text += f",+{len(enabled) - limit}"
    if len(disabled) > limit:
        disabled_text += f",+{len(disabled) - limit}"
    return (
        f"ok={summary.get('ok', 0)} warn={summary.get('warn', 0)} error={summary.get('error', 0)} "
        f"可派={enabled_text} 禁用={disabled_text}"
    )


def format_capability_summary_compact(summary: dict[str, Any], limit: int = 3) -> str:
    enabled = [str(item).split(":", 1)[0] for item in (summary.get("enabled") or [])]
    disabled = [re.sub(r"\([^)]*\)$", "", str(item)) for item in (summary.get("disabled") or [])]
    enabled_text = ",".join(enabled[:limit]) if enabled else "N/A"
    if len(enabled) > limit:
        enabled_text += f",+{len(enabled) - limit}"
    disabled_text = ",".join(disabled) if disabled else "N/A"
    return (
        f"ok={summary.get('ok', 0)} warn={summary.get('warn', 0)} error={summary.get('error', 0)} "
        f"可派={len(enabled)}({enabled_text}) 禁用={disabled_text}"
    )


def resolve_profile(name: str) -> dict[str, Any]:
    profiles = load_profiles().get("profiles") or {}
    if name not in profiles:
        raise ValueError(f"unknown multi-task profile: {name}")
    profile = dict(profiles[name])
    profile["name"] = name
    profile["role"] = str(profile.get("role") or "builder")
    profile["backend"] = str(profile.get("backend") or "claude-cli")
    profile["model"] = str(profile.get("model") or "sonnet")
    profile["approval_mode"] = str(profile.get("approval_mode") or "auto_edit")
    return profile


def _operator_ref(operator_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    op = dict(spec)
    op["operator_id"] = operator_id
    op["enabled"] = bool(op.get("enabled", True))
    op["available"] = bool(op.get("available", True))
    op["health_status"] = str(op.get("health_status") or ("ok" if op["available"] else "disabled"))
    return op


def resolve_operator(operator_id: str) -> dict[str, Any]:
    operators = load_physical_operators().get("operators") or {}
    if operator_id not in operators:
        raise ValueError(f"unknown physical operator: {operator_id}")
    return _operator_ref(operator_id, dict(operators[operator_id]))


def operator_dispatchable(operator: dict[str, Any]) -> tuple[bool, str]:
    if not operator.get("enabled", True):
        return False, str(operator.get("disabled_reason") or "disabled")
    if not operator.get("available", True):
        return False, str(operator.get("health_status") or "unavailable")
    if str(operator.get("quota_guard_state") or "ok").lower() not in {"", "ok", "ready"}:
        return False, f"quota_guard_state={operator.get('quota_guard_state')}"
    key_ref = str(operator.get("key_ref") or "").strip()
    if str(operator.get("auth_mode") or "").lower() not in {"none", "local", "subscription"} and not key_ref:
        return False, "key_ref_missing"
    
    # Check dynamic status override from operator_runtime if available
    op_id = operator.get("operator_id")
    if op_id:
        try:
            import operator_runtime
            dyn_state = operator_runtime.get_operator_runtime_state(op_id)
            if dyn_state in {"disabled", "quota_exhausted", "auth_expired"}:
                return False, f"dynamic_state_{dyn_state}"
        except Exception:
            pass
            
    return True, "ready"


def _selector_values(selector: Any) -> list[str]:
    def expand(value: str) -> list[str]:
        text = str(value or "").lower()
        parts = [p for p in re.split(r"[^a-z0-9]+", text) if p]
        return [text, *parts]

    if selector is None or selector == "":
        return []
    if isinstance(selector, str):
        return expand(selector)
    if isinstance(selector, list):
        values: list[str] = []
        for v in selector:
            if str(v).strip():
                values.extend(expand(str(v)))
        return values
    if isinstance(selector, dict):
        values: list[str] = []
        for key in ("operator_id", "task_type", "task_class", "role", "provider", "vendor", "model", "cost_tier", "latency_tier"):
            raw = selector.get(key)
            if raw:
                values.extend(expand(str(raw)))
        for key in ("capabilities", "required_capabilities", "best_for", "preferred_for"):
            raw = selector.get(key)
            if isinstance(raw, list):
                for v in raw:
                    if str(v).strip():
                        values.extend(expand(str(v)))
            elif raw:
                values.extend(expand(str(raw)))
        return values
    return expand(str(selector))


def operator_score(operator: dict[str, Any], node: dict[str, Any], selector: Any) -> int:
    values = set(_selector_values(selector))
    role = role_from_node(node)
    values.add(role.lower())
    for item in node.get("required_capabilities") or []:
        values.add(str(item).lower())
    for item in node.get("required_skills") or []:
        values.add(str(item).lower())
    for key in ("goal", "title", "description"):
        text = str(node.get(key) or "").lower()
        for marker in (
            "implementation", "debug", "tests", "planning", "architecture", "review",
            "knowledge", "thunder", "gemini", "image", "vision", "multimodal",
            "screenshot", "ui", "mockup", "diagram", "ocr",
        ):
            if marker in text:
                values.add(marker)

    score = 0
    haystacks = [
        str(operator.get("operator_id") or "").lower(),
        str(operator.get("role") or "").lower(),
        str(operator.get("provider") or "").lower(),
        str(operator.get("vendor") or "").lower(),
        str(operator.get("model") or "").lower(),
        str(operator.get("profile") or "").lower(),
    ]
    for key in ("task_classes", "roles", "strengths", "preferred_for", "capabilities", "input_modalities", "output_modalities", "artifact_types"):
        raw = operator.get(key) or []
        if isinstance(raw, str):
            haystacks.append(raw.lower())
        else:
            haystacks.extend(str(v).lower() for v in raw)
    for value in values:
        if not value:
            continue
        if any(value == h or value in h or h in value for h in haystacks if h):
            score += 10
    if str(operator.get("role") or "").lower() == role.lower():
        score += 8
    tier_bias = {"low": 3, "medium": 2, "high": 1}
    score += tier_bias.get(str(operator.get("cost_tier") or "").lower(), 0)
    score += tier_bias.get(str(operator.get("latency_tier") or "").lower(), 0)
    return score


def operator_has_any(operator: dict[str, Any], needles: set[str]) -> bool:
    values: list[str] = []
    for key in ("task_classes", "strengths", "preferred_for", "capabilities", "input_modalities", "output_modalities", "artifact_types"):
        raw = operator.get(key) or []
        if isinstance(raw, str):
            values.append(raw.lower())
        else:
            values.extend(str(v).lower() for v in raw)
    return any(needle in value or value in needle for needle in needles for value in values if value)


def apply_operator_to_profile(profile: dict[str, Any], operator: dict[str, Any], fallback_reason: str = "") -> dict[str, Any]:
    selected = dict(profile)
    selected["operator_id"] = operator.get("operator_id")
    selected["operator_vendor"] = operator.get("vendor") or operator.get("provider")
    selected["operator_model"] = operator.get("model") or selected.get("model")
    selected["operator_pane"] = operator.get("pane") or operator.get("tmux_pane") or "N/A"
    selected["operator_quota_refresh_at"] = operator.get("quota_refresh_at") or "N/A"
    selected["operator_available"] = operator.get("available", True)
    selected["operator_fallback_reason"] = fallback_reason
    if operator.get("profile"):
        selected["name"] = str(operator.get("profile"))
    if operator.get("role"):
        selected["role"] = str(operator.get("role"))
    if operator.get("persona"):
        selected["persona"] = str(operator.get("persona"))
    if operator.get("backend"):
        selected["backend"] = str(operator.get("backend"))
    if operator.get("model"):
        selected["model"] = str(operator.get("model"))
    if operator.get("approval_mode"):
        selected["approval_mode"] = str(operator.get("approval_mode"))
    if operator.get("command"):
        selected["command"] = str(operator.get("command"))
    if operator.get("base_url"):
        selected["base_url"] = str(operator.get("base_url"))
    if operator.get("key_ref"):
        selected["key_ref"] = str(operator.get("key_ref"))
    return selected


def _is_true(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in {"true", "yes", "1"}
    if isinstance(val, int):
        return val != 0
    return False


def _expand_str(val: str) -> set[str]:
    text = str(val or "").lower()
    parts = [p for p in re.split(r"[^a-z0-9]+", text) if p]
    return {text}.union(parts)


def operator_supports_task_type(operator: dict[str, Any], task_type: str) -> bool:
    if not task_type:
        return True
    task_type_lower = task_type.lower()
    
    # Check avoid lists first
    avoid_list = []
    if "avoid_for" in operator:
        avoid_list.extend([str(x).lower() for x in operator["avoid_for"]])
    if "routing" in operator and isinstance(operator["routing"], dict):
        avoid_list.extend([str(x).lower() for x in operator["routing"].get("avoid_task_types", [])])
    
    task_type_parts = _expand_str(task_type)
    for avoid_item in avoid_list:
        avoid_parts = _expand_str(avoid_item)
        if task_type_parts & avoid_parts:
            return False
            
    # Check allowed lists
    allowed_list = []
    if "task_classes" in operator:
        allowed_list.extend([str(x).lower() for x in operator["task_classes"]])
    if "preferred_for" in operator:
        allowed_list.extend([str(x).lower() for x in operator["preferred_for"]])
    if "routing" in operator and isinstance(operator["routing"], dict):
        allowed_list.extend([str(x).lower() for x in operator["routing"].get("primary_task_types", [])])
    
    if not allowed_list:
        return True
        
    for allowed_item in allowed_list:
        allowed_parts = _expand_str(allowed_item)
        if task_type_parts & allowed_parts:
            return True
            
    for allowed_item in allowed_list:
        if task_type_lower in allowed_item or allowed_item in task_type_lower:
            return True
            
    return False


def get_operator_capability_score(operator: dict[str, Any], capability_name: str) -> float:
    capability_name_lower = capability_name.lower().replace("_", "-")
    
    # Check capability or capabilities dict
    caps = operator.get("capability") or operator.get("capabilities")
    if isinstance(caps, dict):
        for k, v in caps.items():
            kl = str(k).lower().replace("_", "-")
            if kl == capability_name_lower:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
    
    # Fallback to strengths presence
    strengths = [str(x).lower().replace("_", "-") for x in operator.get("strengths") or []]
    if capability_name_lower in strengths:
        return 5.0
        
    preferred = [str(x).lower().replace("_", "-") for x in operator.get("preferred_for") or []]
    if capability_name_lower in preferred:
        return 4.0
        
    task_classes = [str(x).lower().replace("_", "-") for x in operator.get("task_classes") or []]
    if capability_name_lower in task_classes:
        return 4.0

    return 1.0


def check_capability_score(operator_score: float | int, constraint_str_or_val: Any) -> bool:
    if constraint_str_or_val is None:
        return True
    if isinstance(constraint_str_or_val, (int, float)):
        return operator_score >= constraint_str_or_val
    
    val_str = str(constraint_str_or_val).strip()
    if not val_str:
        return True
        
    match = re.match(r"^([><=]=?)\s*([0-9.]+)$", val_str)
    if match:
        op, val_num_str = match.groups()
        val_num = float(val_num_str)
        if op == ">=":
            return operator_score >= val_num
        elif op == ">":
            return operator_score > val_num
        elif op == "<=":
            return operator_score <= val_num
        elif op == "<":
            return operator_score < val_num
        elif op == "==":
            return operator_score == val_num
        elif op == "!=":
            return operator_score != val_num
    else:
        try:
            return operator_score >= float(val_str)
        except ValueError:
            pass
    return True


def operator_satisfies_constraints(operator: dict[str, Any], constraints: dict[str, Any]) -> bool:
    if not constraints or not isinstance(constraints, dict):
        return True
        
    tier_map = {"low": 1, "medium": 2, "high": 3}
    
    for key, val in constraints.items():
        if key == "max_cost_tier":
            op_cost = str(operator.get("cost_tier") or "medium").lower()
            max_cost = str(val).lower()
            if tier_map.get(op_cost, 2) > tier_map.get(max_cost, 2):
                return False
        elif key == "max_latency_tier":
            op_latency = str(operator.get("latency_tier") or "medium").lower()
            max_latency = str(val).lower()
            if tier_map.get(op_latency, 2) > tier_map.get(max_latency, 2):
                return False
        elif key == "min_context_tier":
            context_map = {"low": 1, "medium": 2, "high": 3}
            op_context = str(operator.get("context_tier") or "medium").lower()
            min_context = str(val).lower()
            if context_map.get(op_context, 2) < context_map.get(min_context, 2):
                return False
        else:
            op_val = operator.get(key)
            if op_val is None and "policy" in operator and isinstance(operator["policy"], dict):
                op_val = operator["policy"].get(key)
            if op_val is None and "routing" in operator and isinstance(operator["routing"], dict):
                op_val = operator["routing"].get(key)
                
            if op_val is not None:
                if str(op_val).lower() != str(val).lower():
                    return False
    return True


def check_quota_reserve(operator: dict[str, Any], task_type: str) -> bool:
    quota = operator.get("quota")
    if not quota or not isinstance(quota, dict):
        return True
        
    reserve_for = quota.get("reserve_for")
    if not reserve_for:
        return True
        
    if not isinstance(reserve_for, list):
        reserve_for = [reserve_for]
        
    reserve_for_lower = [str(x).lower() for x in reserve_for]
    if not task_type or task_type.lower() not in reserve_for_lower:
        return False
        
    return True


def operator_matches_class(operator: dict[str, Any], class_name: str) -> bool:
    op_class = operator.get("operator_class")
    if not op_class and "routing" in operator and isinstance(operator["routing"], dict):
        op_class = operator["routing"].get("operator_class")
    
    if not op_class:
        return False
        
    if isinstance(op_class, list):
        return any(str(c).lower() == class_name.lower() for c in op_class)
    return str(op_class).lower() == class_name.lower()


def select_operator(node: dict[str, Any], base_profile: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    preferred = str(node.get("preferred_operator") or "").strip()
    if preferred:
        operator = resolve_operator(preferred)
        ok, reason = operator_dispatchable(operator)
        if ok:
            verifier_required = _is_true(node.get("verifier_required")) or _is_true((node.get("operator_selector") or {}).get("verifier_required"))
            if verifier_required:
                prior = node.get("prior_operator") or node.get("writer_operator") or node.get("writer")
                if prior:
                    prior_clean = str(prior).strip().lower()
                    op_id_clean = str(operator.get("operator_id")).strip().lower()
                    op_prof_clean = str(operator.get("profile") or "").strip().lower()
                    if prior_clean in {op_id_clean, op_prof_clean}:
                        return None, f"verifier_conflict:preferred_operator_is_writer:{prior}"
            return operator, ""
        fallback = str(operator.get("fallback_profile") or base_profile.get("name") or "")
        return None, f"preferred_operator_unavailable:{preferred}:{reason};fallback_profile={fallback or 'N/A'}"

    selector = node.get("operator_selector") or {}
    
    task_type = node.get("task_type") or selector.get("task_type")
    req_caps = node.get("required_capabilities") or selector.get("required_capabilities") or node.get("required_capability_scores") or selector.get("required_capability_scores")
    pref_classes = node.get("preferred_operator_classes") or selector.get("preferred_operator_classes")
    constraints = node.get("constraints") or selector.get("constraints")
    verifier_required = _is_true(node.get("verifier_required")) or _is_true(selector.get("verifier_required"))
    
    has_logical = any([
        "operator_selector" in node,
        task_type,
        req_caps,
        pref_classes,
        constraints,
        verifier_required
    ])
    
    if not has_logical:
        return None, ""
        
    operators = [
        _operator_ref(operator_id, dict(spec))
        for operator_id, spec in (load_physical_operators().get("operators") or {}).items()
        if isinstance(spec, dict)
    ]
    
    scored: list[tuple[int, dict[str, Any]]] = []
    selector_values = set(_selector_values(selector))
    if task_type:
        selector_values.update(_expand_str(task_type))
        
    modality_values = {"image", "vision", "multimodal", "screenshot", "ocr", "diagram", "mockup", "ui"}
    modality_required = bool(selector_values & modality_values)
    
    for operator in operators:
        ok, _reason = operator_dispatchable(operator)
        if not ok:
            continue
            
        if verifier_required:
            prior = node.get("prior_operator") or node.get("writer_operator") or node.get("writer")
            if prior:
                prior_clean = str(prior).strip().lower()
                op_id_clean = str(operator.get("operator_id")).strip().lower()
                op_prof_clean = str(operator.get("profile") or "").strip().lower()
                if prior_clean in {op_id_clean, op_prof_clean}:
                    continue
                    
        if task_type and not operator_supports_task_type(operator, task_type):
            continue
            
        if req_caps and isinstance(req_caps, dict):
            cap_ok = True
            for cap_name, cap_constraint in req_caps.items():
                op_score = get_operator_capability_score(operator, cap_name)
                if not check_capability_score(op_score, cap_constraint):
                    cap_ok = False
                    break
            if not cap_ok:
                continue
                
        if constraints and not operator_satisfies_constraints(operator, constraints):
            continue
            
        if not check_quota_reserve(operator, task_type):
            continue
            
        if modality_required and not operator_has_any(operator, selector_values & modality_values):
            continue
            
        score = operator_score(operator, node, selector)
        
        if pref_classes:
            classes_list = [pref_classes] if isinstance(pref_classes, str) else list(pref_classes)
            for c in classes_list:
                if operator_matches_class(operator, str(c)):
                    score += 100
                    
        scored.append((score, operator))
        
    if not scored:
        return None, "operator_selector_no_match"
        
    scored.sort(key=lambda item: (item[0], str(item[1].get("operator_id") or "")), reverse=True)
    return scored[0][1], ""


def _as_string_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)]


def _profile_provider(profile_name: str, profiles: dict[str, Any]) -> str:
    spec = profiles.get(profile_name) or {}
    return model_provider(str(spec.get("model") or ""), str(spec.get("backend") or ""))


def profile_allowed_for_quota_fallback(profile: dict[str, Any]) -> tuple[bool, str]:
    """Reject profiles that only rename a local model onto the Claude CLI billing surface."""
    backend = str(profile.get("backend") or "claude-cli").strip().lower()
    model = str(profile.get("model") or "")
    provider = model_provider(model, backend)
    if backend == "claude-cli" and provider == "local" and not _is_true(profile.get("allow_claude_local_proxy")):
        return False, "claude_cli_local_proxy_not_allowed"
    return True, "ok"


CODE_TASK_KEYWORDS = {
    "api",
    "backend",
    "builder",
    "code",
    "code-edit",
    "contract",
    "coverage",
    "frontend",
    "implementation",
    "patch",
    "python",
    "runtime",
    "schema",
    "state-machine",
    "test",
    "testing",
    "typescript",
    "unit",
}

CODE_PATH_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".go",
    ".h",
    ".hpp",
    ".js",
    ".jsx",
    ".m",
    ".mm",
    ".py",
    ".rs",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
}

KNOWLEDGE_TASK_KEYWORDS = {
    "dashboard",
    "extract",
    "extraction",
    "ingest",
    "knowledge",
    "knowledge-extraction",
    "monitor-report",
    "qmd",
    "semantic",
    "semantic-layer",
    "thunderomlx",
    "vault",
    "wiki",
    "wiki-ingest",
}


def _node_text_for_profile_match(node: dict[str, Any]) -> str:
    fields = [
        node.get("id"),
        node.get("title"),
        node.get("name"),
        node.get("goal"),
        node.get("objective"),
        node.get("task_type"),
        node.get("role"),
        node.get("target_role"),
        node.get("persona"),
        node.get("acceptance"),
        node.get("description"),
        node.get("expected_output"),
        node.get("read_scope"),
        node.get("write_scope"),
        node.get("required_capabilities"),
        node.get("logical_operator"),
    ]
    return " ".join(json.dumps(v, ensure_ascii=False).lower() for v in fields if v is not None)


def node_looks_like_code_task(node: dict[str, Any]) -> bool:
    text = _node_text_for_profile_match(node)
    if any(keyword in text for keyword in CODE_TASK_KEYWORDS):
        return True
    for path in _as_string_list(node.get("write_scope")) + _as_string_list(node.get("files")):
        lowered = path.lower()
        if any(lowered.endswith(suffix) for suffix in CODE_PATH_SUFFIXES):
            return True
    return False


def node_looks_like_knowledge_task(node: dict[str, Any]) -> bool:
    text = _node_text_for_profile_match(node)
    return any(keyword in text for keyword in KNOWLEDGE_TASK_KEYWORDS)


def profile_suitable_for_node(profile_name: str, profile: dict[str, Any], node: dict[str, Any]) -> tuple[bool, str]:
    """Keep quota fallback from swapping code implementation nodes onto extractor-only profiles."""
    profile_text = " ".join(
        json.dumps(profile.get(key), ensure_ascii=False).lower()
        for key in ("name", "role", "persona", "backend", "model", "best_for", "purpose", "capabilities")
        if profile.get(key) is not None
    )
    name = str(profile_name or profile.get("name") or "").lower()
    is_extractor = (
        name == "knowledge-extractor"
        or "knowledge-extractor" in name
        or "knowledge-extraction" in profile_text
        or "wiki-ingest" in profile_text
        or "qmd-indexing" in profile_text
    )
    is_benchmark_only = name == "thunderomlx-benchmark" or "benchmark/cache-metrics" in profile_text
    code_task = node_looks_like_code_task(node)
    knowledge_task = node_looks_like_knowledge_task(node)
    if code_task and not knowledge_task and is_extractor:
        return False, "extractor_profile_not_allowed_for_code_task"
    if code_task and not knowledge_task and is_benchmark_only:
        return False, "benchmark_profile_not_allowed_for_code_task"
    return True, "ok"


def quota_fallback_candidates(node: dict[str, Any], failed_profile: str, profiles: dict[str, Any]) -> list[str]:
    role = role_from_node(node)
    base = profiles.get(failed_profile) or {}
    candidates: list[str] = []
    candidates.extend(_as_string_list(node.get("fallback_profiles")))
    candidates.extend(_as_string_list(base.get("fallback_profiles")))
    if role == "builder":
        candidates.extend([
            "antigravity-multimodal",
            "gemini-builder",
            "deepseek-builder",
            "thunderomlx-local",
            "builder",
            "knowledge-extractor",
        ])
    elif role == "planner":
        candidates.extend(["glm-planner", "planner", "gemini-builder", "thunderomlx-local"])
    elif role == "evaluator":
        candidates.extend(["gemini-evaluator", "antigravity-multimodal", "evaluator", "thunderomlx-local"])
    else:
        candidates.extend([role, "builder", "thunderomlx-local"])

    seen: set[str] = set()
    normalized: list[str] = []
    for candidate in candidates:
        name = normalize_profile_name(candidate, profiles)
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return normalized




def profile_recent_failure_kind(profile_name: str, kind: str, backoff_seconds: int | None = None) -> bool:
    if not profile_name:
        return False
    window = DEFAULT_QUOTA_BACKOFF if backoff_seconds is None else backoff_seconds
    cutoff = time.time() - max(0, int(window or 0))
    for status_path in RUN_DIR.glob("*/status.json"):
        try:
            if status_path.stat().st_mtime < cutoff:
                continue
            status = read_task_status(status_path) or {}
            if normalize_profile_name(str(status.get("profile") or ""), load_profiles().get("profiles") or {}) != profile_name:
                continue
            if output_log_failure_kind(status_path.parent.name) == kind:
                return True
        except Exception:
            continue
    return False

def select_quota_fallback_profile(node: dict[str, Any], failed_profile: str, profiles: dict[str, Any]) -> str:
    failed = normalize_profile_name(failed_profile, profiles)
    blocked = {normalize_profile_name(v, profiles) for v in _as_string_list(node.get("quota_blocked_profiles"))}
    if failed:
        blocked.add(failed)
    failed_provider = _profile_provider(failed, profiles) if failed else ""
    fallback_order = quota_fallback_candidates(node, failed, profiles)
    healthy: list[str] = []
    degraded: list[str] = []
    for name in fallback_order:
        if name in blocked or name not in profiles:
            continue
        profile = dict(profiles[name])
        profile["name"] = name
        allowed, _reason = profile_allowed_for_quota_fallback(profile)
        if not allowed:
            continue
        suitable, _suitability_reason = profile_suitable_for_node(name, profile, node)
        if not suitable:
            continue
        if profile_recent_failure_kind(name, "auth_expired"):
            continue
        cap = capability_for_profile(profile, include_probe=False)
        status = str(cap.get("status") or "error")
        if status not in {"ok", "warn"}:
            continue
        provider = str(cap.get("provider") or "")
        # For a provider quota failure, prefer a different billing surface.
        if failed_provider and provider == failed_provider:
            degraded.append(name)
        else:
            healthy.append(name)
    return (healthy or degraded or [""])[0]


def select_capability_fallback_profile(node: dict[str, Any], failed_profile: str, profiles: dict[str, Any]) -> str:
    failed = normalize_profile_name(failed_profile, profiles)
    fallback_order = quota_fallback_candidates(node, failed, profiles)
    for name in fallback_order:
        if not name or name == failed or name not in profiles:
            continue
        profile = dict(profiles[name])
        profile["name"] = name
        suitable, _suitability_reason = profile_suitable_for_node(name, profile, node)
        if not suitable:
            continue
        cap = capability_for_profile(profile)
        if str(cap.get("status") or "") == "ok":
            return name
    return ""


def run_capability_probe(profile_name: str, timeout_sec: int) -> dict[str, Any]:
    profile = resolve_profile(profile_name)
    backend = str(profile.get("backend") or "claude-cli")
    model = str(profile.get("model") or "")
    provider = model_provider(model, backend)
    prompt = "Reply exactly: SOLAR_PROBE_OK"
    started = now_iso()
    if backend == "claude-cli":
        if not shutil.which("claude"):
            result = {"status": "error", "evidence": "claude missing", "checked_at": started}
        else:
            script = "\n".join([
                "set -u",
                f"HARNESS_DIR={shlex.quote(str(HARNESS_DIR))}",
                claude_agent_line(model, shlex.quote(prompt)),
            ])
            try:
                proc = subprocess.run(["bash", "-lc", script], text=True, capture_output=True, timeout=timeout_sec)
                output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
                result = {
                    "status": "ok" if proc.returncode == 0 and "SOLAR_PROBE_OK" in output else "error",
                    "evidence": (output[-300:] or f"rc={proc.returncode}").replace("\n", " ")[:300],
                    "checked_at": started,
                    "exit_code": proc.returncode,
                }
            except subprocess.TimeoutExpired:
                result = {"status": "error", "evidence": f"probe_timeout>{timeout_sec}s", "checked_at": started, "exit_code": 124}
    elif backend == "gemini-cli":
        adapter = HARNESS_DIR / "lib" / "gemini_adapter.py"
        prompt_file = RUN_DIR / ".probe-gemini-prompt.txt"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(prompt + "\n", encoding="utf-8")
        try:
            proc = subprocess.run([
                sys.executable, str(adapter), "run", "--backend", "cli", "--model", model,
                "--approval-mode", str(profile.get("approval_mode") or "auto_edit"),
                "--auth", "subscription", "--prompt-file", str(prompt_file),
            ], text=True, capture_output=True, timeout=timeout_sec)
            output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            result = {
                "status": "ok" if proc.returncode == 0 and "SOLAR_PROBE_OK" in output else "error",
                "evidence": (output[-300:] or f"rc={proc.returncode}").replace("\n", " ")[:300],
                "checked_at": started,
                "exit_code": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            result = {"status": "error", "evidence": f"probe_timeout>{timeout_sec}s", "checked_at": started, "exit_code": 124}
    elif backend == "command":
        result = {"status": "warn", "evidence": "command backend probes are user-command specific", "checked_at": started}
    else:
        result = {"status": "error", "evidence": f"unsupported backend={backend}", "checked_at": started}
    cache = read_probe_cache()
    cache[probe_key(provider, model, backend)] = result
    write_probe_cache(cache)
    return {"profile": profile_name, "provider": provider, "backend": backend, "model": model, **result}


def role_from_node(node: dict[str, Any]) -> str:
    raw = (
        node.get("target_role")
        or node.get("role")
        or node.get("owner")
        or node.get("persona")
        or node.get("worker_role")
        or node.get("handoff_to")
        or node.get("logical_operator")
        or ""
    )
    value = str(raw).strip().lower().replace("_", "-")
    aliases = {
        "builder-main": "builder",
        "build": "builder",
        "implementation": "builder",
        "implementer": "builder",
        "judge": "evaluator",
        "reviewer": "evaluator",
        "verifier": "evaluator",
        "critic": "evaluator",
        "artifact-curator": "evaluator",
        "product": "pm",
        "product-manager": "pm",
        "planning": "planner",
        "architect": "planner",
        "deeparchitect": "planner",
        "implementationworker": "builder",
        "testrunner": "evaluator",
    }
    return aliases.get(value, value or "builder")


def select_profile(node: dict[str, Any], profile_override: str = "", model_override: str = "", backend_override: str = "") -> dict[str, Any]:
    config = load_profiles()
    profiles = config.get("profiles") or {}
    requested_profile = profile_override or str(node.get("preferred_profile") or node.get("profile") or "")
    profile_name = normalize_profile_name(requested_profile, profiles)
    if not profile_name:
        role = role_from_node(node)
        for name, spec in profiles.items():
            if str(spec.get("role", "")).lower() == role and not str(name).startswith(("gemini-", "deepseek-", "glm-", "thunder")):
                profile_name = str(name)
                break
    profile_name = normalize_profile_name(profile_name or str((config.get("defaults") or {}).get("profile") or "builder"), profiles)
    quota_fallback_from = ""
    quota_blocked = {normalize_profile_name(v, profiles) for v in _as_string_list(node.get("quota_blocked_profiles"))}
    if not profile_override and profile_name in profiles and node.get("quota_failure_reason"):
        profile = dict(profiles[profile_name])
        profile["name"] = profile_name
        suitable, reason = profile_suitable_for_node(profile_name, profile, node)
        if not suitable:
            node["quota_fallback_unsuitable_profile"] = profile_name
            node["quota_fallback_unsuitable_reason"] = reason
            failed = normalize_profile_name(str(node.get("quota_fallback_from") or ""), profiles)
            quota_blocked.add(profile_name)
            if failed:
                profile_name = failed
            else:
                fallback = select_quota_fallback_profile(node, profile_name, profiles)
                if fallback:
                    quota_fallback_from = profile_name
                    profile_name = fallback
    if not profile_override and profile_name in quota_blocked:
        fallback = select_quota_fallback_profile(node, profile_name, profiles)
        if fallback:
            quota_fallback_from = profile_name
            profile_name = fallback
    if profile_name not in profiles:
        raise ValueError(f"unknown multi-task profile: {profile_name}")
    selected = dict(profiles[profile_name])
    selected["name"] = profile_name
    selected["role"] = str(selected.get("role") or role_from_node(node))
    selected["persona"] = str(selected.get("persona") or selected["role"])
    node_model = "" if quota_fallback_from else str(node.get("preferred_model") or "")
    selected["backend"] = str(backend_override or selected.get("backend") or (config.get("defaults") or {}).get("backend") or "claude-cli")
    selected["model"] = profile_model_with_compatible_override(selected, model_override, node_model)
    selected["approval_mode"] = str(selected.get("approval_mode") or "auto_edit")
    if quota_fallback_from:
        selected["quota_fallback_from"] = quota_fallback_from
        selected["quota_fallback_reason"] = "quota_exhausted"
    if not profile_override and not backend_override and not model_override:
        capability = capability_for_profile(selected)
        if str(capability.get("status") or "") != "ok":
            fallback = select_capability_fallback_profile(node, profile_name, profiles)
            if fallback:
                fallback_profile = dict(profiles[fallback])
                fallback_profile["name"] = fallback
                fallback_profile["role"] = str(fallback_profile.get("role") or role_from_node(node))
                fallback_profile["persona"] = str(fallback_profile.get("persona") or fallback_profile["role"])
                fallback_profile["backend"] = str(fallback_profile.get("backend") or (config.get("defaults") or {}).get("backend") or "claude-cli")
                fallback_profile["model"] = profile_model_with_compatible_override(fallback_profile, "", str(node.get("preferred_model") or ""))
                fallback_profile["approval_mode"] = str(fallback_profile.get("approval_mode") or "auto_edit")
                fallback_profile["capability_fallback_from"] = profile_name
                fallback_profile["capability_fallback_reason"] = str(capability.get("status") or "unavailable")
                selected = fallback_profile
    if not (requested_profile and (node.get("quota_failure_reason") or node.get("auth_failure_reason"))):
        operator, fallback_reason = select_operator(node, selected)
        if operator:
            selected = apply_operator_to_profile(selected, operator, fallback_reason)
        elif node.get("preferred_operator"):
            selected["operator_id"] = str(node.get("preferred_operator") or "")
            selected["operator_fallback_reason"] = fallback_reason or "preferred_operator_unavailable"
        elif node.get("operator_selector"):
            selected["operator_fallback_reason"] = fallback_reason or "operator_selector_no_match"
    return selected


def persona_text(persona: str) -> tuple[str, str]:
    path = HARNESS_DIR / "personas" / f"{persona}.md"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return str(path), text[:12000]
    except Exception:
        return str(path), "N/A"


def claude_model_arg(model: str) -> str:
    value = str(model or "sonnet").lower()
    if "opus" in value:
        return "opus"
    if "sonnet" in value or value in {"claude", "anthropic"}:
        return "sonnet"
    return value


def claude_agent_line(model: str, dispatch_expr: str = '"$(cat "$DISPATCH_FILE")"') -> str:
    permission_prelude = "\n".join([
        "CLAUDE_PERMISSION_FLAGS=()",
        'if [[ "${SOLAR_CLAUDE_SKIP_PERMISSIONS:-1}" == "1" ]]; then '
        'CLAUDE_PERMISSION_FLAGS+=(--dangerously-skip-permissions); fi',
    ])
    permission_flags = '"${CLAUDE_PERMISSION_FLAGS[@]}" --permission-mode bypassPermissions'
    provider = model_provider(model, "claude-cli")
    if provider == "local":
        route_model = provider_model_alias(provider, model)
        base_url = os.environ.get("THUNDEROMLX_BASE_URL", "http://127.0.0.1:8002")
        local_model = os.environ.get("THUNDEROMLX_LOCAL_MODEL", "Qwen3.6-35b-a3b")
        return "\n".join([
            f"export ANTHROPIC_BASE_URL={shlex.quote(base_url)}",
            "export ANTHROPIC_AUTH_TOKEN=${THUNDEROMLX_AUTH_TOKEN:-local-thunderomlx}",
            "export ANTHROPIC_API_KEY=${THUNDEROMLX_AUTH_TOKEN:-local-thunderomlx}",
            f"export ANTHROPIC_DEFAULT_OPUS_MODEL={shlex.quote(route_model)}",
            f"export ANTHROPIC_DEFAULT_SONNET_MODEL={shlex.quote(route_model)}",
            f"export ANTHROPIC_DEFAULT_HAIKU_MODEL={shlex.quote(route_model)}",
            f"export THUNDEROMLX_LOCAL_MODEL={shlex.quote(local_model)}",
            "export API_TIMEOUT_MS=${API_TIMEOUT_MS:-3000000}",
            "export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1",
            "export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1",
            "export DISABLE_NON_ESSENTIAL_MODEL_CALLS=1",
            "export CLAUDE_CODE_MAX_OUTPUT_TOKENS=${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-4096}",
            permission_prelude,
            (
                f"claude {permission_flags} "
                f"--model {shlex.quote(route_model)} "
                "--tools default "
                f"-p {dispatch_expr}"
            ),
        ])
    if provider in {"zhipu", "deepseek"}:
        route_model = provider_model_alias(provider, model)
        return "\n".join([
            f"export SOLAR_LAB_BUILDER_MODEL_MATRIX={shlex.quote(route_model)}",
            "export SOLAR_BUILDER_SLOT=${SOLAR_BUILDER_SLOT:-lab-builder-1}",
            "source \"$HARNESS_DIR/lib/persona-config.sh\"",
            "persona_config=\"$(get_persona_config lab-builder)\"",
            "eval \"$persona_config\"",
            "apply_persona_env lab-builder",
            "if [[ -n \"${LAUNCH_ERROR:-}\" ]]; then echo \"ERROR: $LAUNCH_ERROR\"; exit 66; fi",
            permission_prelude,
            f"claude {permission_flags} $MODEL_FLAG $EXTRA_FLAGS -p {dispatch_expr}",
        ])
    empty_mcp = HARNESS_DIR / "config" / "empty-mcp.json"
    return "\n".join([
        permission_prelude,
        f"claude {permission_flags} "
        f"--model {shlex.quote(claude_model_arg(model))} "
        f"--tools default --strict-mcp-config --mcp-config {shlex.quote(str(empty_mcp))} "
        f"-p {dispatch_expr}"
    ])


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> float | None:
    try:
        return _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def task_id(sid: str, node_id: str) -> str:
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_sid = re.sub(r"[^A-Za-z0-9_.-]+", "-", sid)[:36] or "sprint"
    safe_node = re.sub(r"[^A-Za-z0-9_.-]+", "-", node_id)[:24] or "node"
    return f"mt-{stamp}-{safe_sid}-{safe_node}"


def short_window(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-")
    return (value or "multi-task")[:48]


def status_path(task_dir: Path) -> Path:
    return task_dir / "status.json"


def read_task_status(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def task_age_s(row: dict[str, Any], now_ts: float | None = None) -> int | None:
    updated_ts = parse_iso(str(row.get("updated_at") or row.get("created_at") or ""))
    if updated_ts is None:
        return None
    return max(0, int((time.time() if now_ts is None else now_ts) - updated_ts))


def graph_node_status_for_task(row: dict[str, Any]) -> str:
    graph_path = str(row.get("graph") or "").strip()
    node_id = str(row.get("node_id") or "").strip()
    if not graph_path or not node_id:
        return "N/A"
    try:
        graph = load_graph(Path(graph_path).expanduser())
        return str(node_status(graph, node_id) or "N/A")
    except Exception:
        return "N/A"


def effective_task_status(row: dict[str, Any]) -> str:
    """Classify worker occupancy using graph truth when task status drifted.

    A tmux pane can outlive the runner status write. If the DAG node is already
    passed/failed, or is reviewing with a handoff present, it should not keep
    consuming a worker slot in the scheduler/status view.
    """
    current = str(row.get("status") or "").lower()
    graph_status = str(row.get("graph_status") or "N/A").lower()
    if current in ACTIVE_TASK_STATUSES:
        if graph_status in {"passed", "done", "completed"}:
            return "completed_aligned"
        if graph_status in {"failed", "cancelled", "canceled", "skipped"}:
            return "failed_aligned"
        if graph_status == "reviewing":
            handoff = str(row.get("handoff") or "").strip()
            if handoff and Path(handoff).expanduser().exists():
                return "completed_aligned"
    return current


def format_age_s(age_s: int | None) -> str:
    if age_s is None:
        return "N/A"
    if age_s < 60:
        return f"{age_s}s"
    minutes = age_s // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h{minutes % 60:02d}m"
    days = hours // 24
    return f"{days}d{hours % 24:02d}h"


def task_data_class(row: dict[str, Any], now_ts: float | None = None) -> str:
    status = str(row.get("effective_status") or row.get("status") or "").lower()
    tmux_status = str(row.get("tmux_status") or "").lower()
    age_s = task_age_s(row, now_ts)
    stale = age_s is not None and age_s >= TASK_STALE_WARN_SEC
    if status in ACTIVE_TASK_STATUSES:
        if tmux_status == "live":
            return "live"
        return "stale_active" if stale else "pending"
    if status == "dry_run":
        return "stale" if stale else "dry_run"
    if status in EFFECTIVE_TERMINAL_TASK_STATUSES or status.startswith("reaped"):
        return "historical"
    return "stale" if stale else "observed"


def tmux_session_exists() -> bool:
    try:
        return subprocess.run(
            ["tmux", "has-session", "-t", SESSION],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).returncode == 0
    except Exception:
        return False


def tmux_window_map() -> dict[str, dict[str, str]]:
    try:
        out = subprocess.check_output(
            [
                "tmux",
                "list-windows",
                "-t",
                SESSION,
                "-F",
                "#{window_name}\t#{window_active}\t#{pane_current_command}\t#{pane_dead}\t#{pane_pid}",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        return {}
    windows: dict[str, dict[str, str]] = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        name = parts[0].strip() if parts else ""
        if not name:
            continue
        windows[name] = {
            "window": name,
            "active": parts[1].strip() if len(parts) > 1 else "",
            "command": parts[2].strip() if len(parts) > 2 else "",
            "dead": parts[3].strip() if len(parts) > 3 else "",
            "pane_pid": parts[4].strip() if len(parts) > 4 else "",
        }
    return windows


def pane_role(session: str, pane_index: str, title: str) -> str:
    title_l = title.lower()
    if session == MAIN_SESSION:
        return {
            "0": "pm",
            "1": "planner",
            "2": "builder",
            "3": "evaluator",
        }.get(str(pane_index), "main")
    if session == LAB_SESSION:
        return "lab-builder"
    if "planner" in title_l:
        return "planner"
    if "evaluator" in title_l or "审判" in title:
        return "evaluator"
    if "builder" in title_l or "构建" in title:
        return "builder"
    if "pm" in title_l or "产品" in title:
        return "pm"
    return "unknown"


def pane_model_from_title(title: str) -> str:
    match = re.search(r"模型:([^|]+)", title)
    return match.group(1).strip() if match else "N/A"


def pane_state_from_title(title: str) -> str:
    match = re.search(r"状态:([^|]+)", title)
    if match:
        return match.group(1).strip()
    if "能力:" in title:
        return "ready"
    return "observed"


def list_harness_panes() -> list[dict[str, Any]]:
    try:
        out = subprocess.check_output(
            [
                "tmux",
                "list-panes",
                "-a",
                "-F",
                "#{session_name}\t#{window_name}\t#{pane_index}\t#{pane_title}\t#{pane_current_command}\t#{pane_dead}\t#{pane_pid}",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    wanted = {MAIN_SESSION, LAB_SESSION, SESSION}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        session, window, pane_index, title, command, dead, pane_pid = parts[:7]
        if session not in wanted:
            continue
        pane = f"{session}:{window}" if session == SESSION else f"{session}:0.{pane_index}"
        role = pane_role(session, pane_index, title)
        plane = "four-pane" if session == MAIN_SESSION else ("builder-lab" if session == LAB_SESSION else "multi-task")
        rows.append({
            "plane": plane,
            "pane": pane,
            "role": role,
            "state": "dead" if dead == "1" else pane_state_from_title(title),
            "model": pane_model_from_title(title),
            "command": command or "N/A",
            "pid": pane_pid or "N/A",
            "title": title or "N/A",
        })
    return rows


def node_from_dispatch_record(record: dict[str, Any]) -> str:
    instruction = str(record.get("instruction_file") or "")
    match = re.search(r"\.([A-Za-z0-9_-]+)-(?:eval-)?dispatch\.md$", instruction)
    if match:
        return match.group(1)
    dispatch_id = str(record.get("dispatch_id") or "")
    match = re.search(r"-([A-Za-z]\d+[A-Za-z0-9_-]*)-\d{8}T\d{6}Z$", dispatch_id)
    return match.group(1) if match else "N/A"


def dispatch_role(record: dict[str, Any]) -> str:
    dispatch_id = str(record.get("dispatch_id") or "")
    if dispatch_id.startswith("graph-eval-") or "-eval-" in str(record.get("instruction_file") or ""):
        return "evaluator"
    pane = str(record.get("pane") or "")
    if pane.startswith(f"{LAB_SESSION}:"):
        return "lab-builder"
    if pane.endswith(":0.0"):
        return "pm"
    if pane.endswith(":0.1"):
        return "planner"
    if pane.endswith(":0.2"):
        return "builder"
    if pane.endswith(":0.3"):
        return "evaluator"
    return "unknown"


def recent_dispatch_rows(limit: int = 12) -> list[dict[str, Any]]:
    if not DISPATCH_LEDGER_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = DISPATCH_LEDGER_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    for line in reversed(lines[-500:]):
        try:
            record = json.loads(line)
        except Exception:
            continue
        sid = str(record.get("sid") or "")
        if not sid or (not sid.startswith("sprint-") and not sid.startswith("epic-")):
            continue
        dispatch_id = str(record.get("dispatch_id") or "")
        if dispatch_id.startswith("test-dispatch"):
            continue
        rows.append({
            "time": str(record.get("ts") or "N/A"),
            "pane": str(record.get("pane") or "N/A"),
            "role": dispatch_role(record),
            "sprint": sid,
            "node": node_from_dispatch_record(record),
            "kind": str(record.get("kind") or "N/A"),
            "providers": ",".join(record.get("capability_providers") or []) or "N/A",
            "dispatch_id": dispatch_id,
        })
        if len(rows) >= limit:
            break
    return rows


def pane_type_for_task(row: dict[str, Any]) -> str:
    role = str(row.get("role") or "N/A")
    profile = str(row.get("profile") or "")
    backend = str(row.get("backend") or "")
    if profile and profile != "N/A":
        return f"multi-task/{role}:{profile}"
    if backend:
        return f"multi-task/{role}:{backend}"
    return f"multi-task/{role}"


def enrich_task_row(row: dict[str, Any], windows: dict[str, dict[str, str]]) -> dict[str, Any]:
    enriched = dict(row)
    window = str(enriched.get("window") or "")
    status = str(enriched.get("status") or "").lower()
    info = windows.get(window) if window else None
    if not window:
        tmux_status = "no-window"
    elif info is None:
        tmux_status = "missing"
    elif str(info.get("dead") or "") == "1":
        tmux_status = "dead"
    else:
        tmux_status = "live"
    if status == "dry_run":
        tmux_status = "dry_run"
    enriched["pane_type"] = pane_type_for_task(enriched)
    enriched["tmux_status"] = tmux_status
    enriched["pane_command"] = (info or {}).get("command", "N/A")
    enriched["pane_pid"] = (info or {}).get("pane_pid", "N/A")
    enriched["graph_status"] = graph_node_status_for_task(enriched)
    enriched["effective_status"] = effective_task_status(enriched)
    age_s = task_age_s(enriched)
    enriched["age_s"] = age_s
    enriched["age"] = format_age_s(age_s)
    enriched["data_class"] = task_data_class(enriched)
    return enriched


def list_task_rows() -> list[dict[str, Any]]:
    if not RUN_DIR.exists():
        return []
    windows = tmux_window_map()
    rows: list[dict[str, Any]] = []
    for path in sorted(RUN_DIR.glob("*/status.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        row = read_task_status(path)
        if row:
            rows.append(enrich_task_row(row, windows))
    return rows


def active_tasks() -> list[dict[str, Any]]:
    return [row for row in list_task_rows() if str(row.get("effective_status") or row.get("status", "")).lower() in ACTIVE_TASK_STATUSES]


def active_parallel_counts(tasks: list[dict[str, Any]] | None = None) -> dict[str, dict[str, int]]:
    tasks = tasks if tasks is not None else active_tasks()
    by_profile: dict[str, int] = {}
    by_role: dict[str, int] = {}
    for task in tasks:
        profile = normalize_profile_name(str(task.get("profile") or task.get("name") or ""))
        role = str(task.get("role") or "").strip().lower()
        if profile:
            by_profile[profile] = by_profile.get(profile, 0) + 1
        if role:
            by_role[role] = by_role.get(role, 0) + 1
    return {"profile": by_profile, "role": by_role}


def profile_parallel_limit_reached(profile: dict[str, Any], counts: dict[str, dict[str, int]] | None = None) -> dict[str, Any]:
    counts = counts or active_parallel_counts()
    name = normalize_profile_name(str(profile.get("name") or ""))
    limit = max(1, int(profile.get("max_parallel", 1) or 1))
    active = int((counts.get("profile") or {}).get(name, 0))
    return {
        "ok": active < limit,
        "profile": name or "N/A",
        "active": active,
        "limit": limit,
        "reason": "profile_parallel_limit_reached" if active >= limit else "ready",
    }


def task_inventory(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    latest: dict[str, Any] | None = None
    latest_ts = -1.0
    for task in tasks:
        data_class = str(task.get("data_class") or "observed")
        status = str(task.get("effective_status") or task.get("status") or "N/A").lower()
        counts[data_class] = counts.get(data_class, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1
        updated_ts = parse_iso(str(task.get("updated_at") or task.get("created_at") or ""))
        if updated_ts is not None and updated_ts > latest_ts:
            latest = task
            latest_ts = updated_ts
    live = counts.get("live", 0)
    active = sum(1 for task in tasks if str(task.get("effective_status") or task.get("status", "")).lower() in ACTIVE_TASK_STATUSES)
    stale = counts.get("stale", 0) + counts.get("stale_active", 0)
    historical = counts.get("historical", 0) + counts.get("dry_run", 0) + counts.get("stale", 0)
    return {
        "total": len(tasks),
        "active": active,
        "live": live,
        "historical": historical,
        "stale": stale,
        "classes": counts,
        "statuses": status_counts,
        "latest": latest,
        "latest_age": format_age_s(None if latest is None else task_age_s(latest)),
    }


def last_launch_at() -> float | None:
    path = RUN_DIR / ".last-launch"
    try:
        return float(path.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def set_last_launch() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / ".last-launch").write_text(str(time.time()), encoding="utf-8")


def free_memory_gb() -> float | None:
    if sys.platform == "darwin" and shutil.which("vm_stat"):
        try:
            out = subprocess.check_output(["vm_stat"], text=True, stderr=subprocess.DEVNULL)
            page_size = 4096
            free_pages = 0
            for line in out.splitlines():
                if "page size of" in line:
                    m = re.search(r"page size of (\d+) bytes", line)
                    if m:
                        page_size = int(m.group(1))
                if line.startswith(("Pages free:", "Pages inactive:", "Pages speculative:")):
                    free_pages += int(re.sub(r"[^0-9]", "", line.split(":", 1)[1]) or "0")
            if free_pages:
                return free_pages * page_size / 1024 / 1024 / 1024
        except Exception:
            return None
    return None


def quota_guard(backoff_seconds: int) -> dict[str, Any]:
    cutoff = time.time() - backoff_seconds
    hits: list[dict[str, Any]] = []
    if RUN_DIR.exists():
        for log in RUN_DIR.glob("*/output.log"):
            try:
                if log.stat().st_mtime < cutoff:
                    continue
                tail = log.read_text(encoding="utf-8", errors="replace")[-8000:]
            except Exception:
                continue
            if QUOTA_RE.search(tail):
                if quota_hit_recovered_for_fallback(log):
                    continue
                hits.append({"task": log.parent.name, "log": str(log)})
    if hits:
        return {"ok": False, "reason": "recent_quota_or_rate_limit", "hits": hits[:5]}
    return {"ok": True, "reason": "no_recent_quota_hit"}


def quota_hit_recovered_for_fallback(log: Path) -> bool:
    """Do not let a recovered provider quota hit freeze unrelated fallback work."""
    status = read_task_status(log.parent / "status.json")
    if not status:
        return False
    graph_path = str(status.get("graph") or "").strip()
    node_id = str(status.get("node_id") or "").strip()
    failed_profile = str(status.get("profile") or "").strip()
    if not graph_path or not node_id or not failed_profile:
        return False
    try:
        graph = load_graph(Path(graph_path).expanduser())
    except Exception:
        return False
    node = next((item for item in graph_nodes(graph) if str(item.get("id") or "") == node_id), None)
    if not node:
        return False
    current_profile = str(node.get("preferred_profile") or node.get("profile") or "").strip()
    current_status = str(node_status(graph, node_id) or node.get("status") or "").lower()
    if current_status in {"passed", "done", "completed", "skipped"}:
        return True
    if not current_profile or current_profile == failed_profile:
        return False
    if current_status not in {"active", "pending", "ready"}:
        return False
    recorded_failure = str(node.get("quota_failure_task_id") or "").strip()
    return not recorded_failure or recorded_failure == log.parent.name or bool(node.get("quota_failure_reason"))


def launch_guard(max_workers: int, reserve_gb: float, cooldown: int, quota_backoff: int) -> dict[str, Any]:
    active = active_tasks()
    if len(active) >= max_workers:
        return {"ok": False, "reason": "worker_pool_full", "active": len(active), "max_workers": max_workers}

    mem = free_memory_gb()
    if mem is not None and mem < reserve_gb:
        return {"ok": False, "reason": "low_memory", "free_gb": round(mem, 2), "reserve_gb": reserve_gb}

    last = last_launch_at()
    if last is not None:
        elapsed = time.time() - last
        if elapsed < cooldown:
            return {"ok": False, "reason": "launch_cooldown", "wait_s": int(cooldown - elapsed)}

    quota = quota_guard(quota_backoff)
    if not quota.get("ok"):
        return quota

    return {
        "ok": True,
        "reason": "ready",
        "active": len(active),
        "max_workers": max_workers,
        "free_gb": None if mem is None else round(mem, 2),
    }


def graph_files(explicit: list[str]) -> list[Path]:
    if explicit:
        return [Path(item).expanduser() for item in explicit]
    return sorted(SPRINTS_DIR.glob("*.task_graph.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def output_log_failure_kind(task_id_value: str) -> str:
    if not task_id_value:
        return ""
    log = RUN_DIR / task_id_value / "output.log"
    try:
        tail = log.read_text(encoding="utf-8", errors="replace")[-12000:]
    except Exception:
        return ""
    if AUTH_RE.search(tail):
        return "auth_expired"
    if QUOTA_RE.search(tail):
        return "quota_exhausted"
    return ""


def output_log_has_quota_failure(task_id_value: str) -> bool:
    return output_log_failure_kind(task_id_value) == "quota_exhausted"


def output_log_has_provider_recoverable_failure(task_id_value: str) -> bool:
    return output_log_failure_kind(task_id_value) in {"auth_expired", "quota_exhausted"}


def _recoverable_failure_label(reason: str) -> str:
    if reason == "auth_expired":
        return "auth_expired"
    if reason == "quota_exhausted":
        return "quota_exhausted"
    return "provider_unavailable"


def _recoverable_failure_no_fallback(reason: str) -> str:
    if reason == "auth_expired":
        return "auth_expired_no_fallback_profile"
    if reason == "quota_exhausted":
        return "quota_exhausted_no_fallback_profile"
    return "provider_unavailable_no_fallback_profile"


def _recoverable_failure_limit(reason: str) -> str:
    if reason == "auth_expired":
        return "auth_expired_recovery_limit_reached"
    if reason == "quota_exhausted":
        return "quota_exhausted_recovery_limit_reached"
    return "provider_unavailable_recovery_limit_reached"


def _recoverable_failure_field_prefix(reason: str) -> str:
    if reason == "auth_expired":
        return "auth_failure"
    if reason == "quota_exhausted":
        return "quota_failure"
    return "provider_failure"


def output_log_has_auth_failure(task_id_value: str) -> bool:
    if not task_id_value:
        return False
    return output_log_failure_kind(task_id_value) == "auth_expired"


def recover_quota_failed_nodes(graph_path: Path, graph: dict[str, Any]) -> int:
    profiles = load_profiles().get("profiles") or {}
    changed = 0
    for node in graph_nodes(graph):
        node_id = str(node.get("id") or "")
        try:
            current_status = node_status(graph, node_id) if node_id else str(node.get("status") or "")
        except Exception:
            current_status = str(node.get("status") or "")
        if str(current_status or "").lower() != "failed":
            continue
        dispatch_id = str(node.get("dispatch_id") or node.get("quota_failure_task_id") or "").strip()
        status = read_task_status(RUN_DIR / dispatch_id / "status.json") if dispatch_id else None
        profile_name = normalize_profile_name(
            str((status or {}).get("profile") or node.get("preferred_profile") or node.get("profile") or ""),
            profiles,
        )
        failure_reason = output_log_failure_kind(dispatch_id)
        if failure_reason not in {"auth_expired", "quota_exhausted"}:
            continue
        recovered_ids = set(_as_string_list(node.get("quota_recovery_task_ids")))
        try:
            recovery_count = int(node.get("quota_recovery_count") or 0)
        except Exception:
            recovery_count = 0
        max_recoveries = int(os.environ.get("SOLAR_MULTI_TASK_MAX_QUOTA_RECOVERIES_PER_NODE", "4") or "4")
        if (dispatch_id and dispatch_id in recovered_ids) or recovery_count >= max_recoveries:
            node["monitor_blocker"] = _recoverable_failure_limit(failure_reason)
            field_prefix = _recoverable_failure_field_prefix(failure_reason)
            node[f"{field_prefix}_reason"] = _recoverable_failure_label(failure_reason)
            node[f"{field_prefix}_task_id"] = dispatch_id
            node["updated_at"] = now_iso()
            changed += 1
            continue

        blocked = {normalize_profile_name(v, profiles) for v in _as_string_list(node.get("quota_blocked_profiles"))}
        if profile_name:
            blocked.add(profile_name)
        node["quota_blocked_profiles"] = sorted(v for v in blocked if v)
        field_prefix = _recoverable_failure_field_prefix(failure_reason)
        node[f"{field_prefix}_reason"] = _recoverable_failure_label(failure_reason)
        node[f"{field_prefix}_task_id"] = dispatch_id
        node[f"{field_prefix}_recovered_at"] = now_iso()
        fallback = select_quota_fallback_profile(node, profile_name, profiles)
        if fallback:
            if dispatch_id:
                recovered_ids.add(dispatch_id)
            node["quota_recovery_task_ids"] = sorted(v for v in recovered_ids if v)
            node["quota_recovery_count"] = recovery_count + 1
            node["preferred_profile"] = fallback
            node["quota_fallback_from"] = profile_name
            node["quota_fallback_reason"] = _recoverable_failure_label(failure_reason)
            if isinstance(graph.get("node_results"), dict):
                graph["node_results"].pop(node_id, None)
            node["status"] = "pending"
            node["updated_at"] = now_iso()
            node.pop("assigned_to", None)
            node.pop("dispatch_id", None)
            node.pop("pane", None)
            node.pop("monitor_blocker", None)
        else:
            node["monitor_blocker"] = _recoverable_failure_no_fallback(failure_reason)
        changed += 1
    if changed:
        save_graph(graph_path, graph)
    return changed


def sprint_id_for(graph: dict[str, Any], graph_path: Path) -> str:
    return str(graph.get("sprint_id") or graph_path.name.replace(".task_graph.json", ""))


def iso_from_timestamp(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def graph_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = graph.get("nodes") or []
    if isinstance(nodes, dict):
        return [node for node in nodes.values() if isinstance(node, dict)]
    if isinstance(nodes, list):
        return [node for node in nodes if isinstance(node, dict)]
    return []


def graph_description(graph: dict[str, Any], graph_path: Path) -> str:
    """Return a short human-readable label for a DAG graph row."""
    for key in ("title", "summary", "description", "goal"):
        raw = str(graph.get(key) or "").strip()
        if raw:
            return re.sub(r"\s+", " ", raw.lstrip("# ").strip())

    sid = sprint_id_for(graph, graph_path)
    for prefix in ("sprint-", "epic-"):
        if sid.startswith(prefix):
            tail = sid[len(prefix):]
            parts = tail.split("-", 4)
            if len(parts) >= 5:
                return parts[4].replace("-", " ")

    for node in graph_nodes(graph):
        raw = str(node.get("goal") or node.get("title") or node.get("description") or "").strip()
        if raw:
            return re.sub(r"\s+", " ", raw)
    return "N/A"


def status_summary_for_graph(graph_path: Path) -> dict[str, Any]:
    try:
        graph = load_graph(graph_path)
        nodes = graph_nodes(graph)
        counts: dict[str, int] = {}
        for node in nodes:
            nid = str(node.get("id") or "")
            st = node_status(graph, nid) if nid else "invalid"
            counts[st] = counts.get(st, 0) + 1
        ready = [str(n.get("id") or "") for n in ready_nodes(graph)]
        return {
            "graph": str(graph_path),
            "sid": sprint_id_for(graph, graph_path),
            "description": graph_description(graph, graph_path),
            "graph_updated_at": iso_from_timestamp(graph_path.stat().st_mtime),
            "observed_at": now_iso(),
            "ok": True,
            "counts": counts,
            "ready": ready,
        }
    except Exception as exc:
        return {
            "graph": str(graph_path),
            "sid": graph_path.stem,
            "description": "N/A",
            "graph_updated_at": "N/A",
            "observed_at": now_iso(),
            "ok": False,
            "error": str(exc),
            "counts": {},
            "ready": [],
        }


def load_graph_summary_cache() -> dict[str, Any]:
    try:
        data = json.loads(GRAPH_SUMMARY_CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(data.get("entries"), dict):
            return data
    except Exception:
        pass
    return {"version": 1, "entries": {}}


def save_graph_summary_cache(cache: dict[str, Any]) -> None:
    try:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        tmp = GRAPH_SUMMARY_CACHE_PATH.with_name(f"{GRAPH_SUMMARY_CACHE_PATH.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(GRAPH_SUMMARY_CACHE_PATH)
    except Exception:
        return


def graph_cache_key(graph_path: Path) -> str:
    try:
        return str(graph_path.expanduser().resolve())
    except Exception:
        return str(graph_path)


def graph_signature(graph_path: Path) -> dict[str, int]:
    st = graph_path.stat()
    return {"mtime_ns": int(st.st_mtime_ns), "size": int(st.st_size)}


def cached_status_summaries_for_graphs(paths: list[Path]) -> list[dict[str, Any]]:
    cache = load_graph_summary_cache()
    entries = cache.setdefault("entries", {})
    summaries: list[dict[str, Any]] = []
    dirty = False
    now_ts = time.time()

    for graph_path in paths:
        key = graph_cache_key(graph_path)
        try:
            sig = graph_signature(graph_path)
        except Exception:
            summaries.append(status_summary_for_graph(graph_path))
            continue
        cached = entries.get(key)
        if (
            isinstance(cached, dict)
            and cached.get("mtime_ns") == sig["mtime_ns"]
            and cached.get("size") == sig["size"]
            and isinstance(cached.get("summary"), dict)
            and GRAPH_SUMMARY_CACHE_TTL_SEC > 0
            and now_ts - float(cached.get("cached_at_ts") or 0) <= GRAPH_SUMMARY_CACHE_TTL_SEC
        ):
            summaries.append(cached["summary"])
            continue
        summary = status_summary_for_graph(graph_path)
        entries[key] = {**sig, "summary": summary, "updated_at": now_iso(), "cached_at_ts": now_ts}
        summaries.append(summary)
        dirty = True

    if dirty:
        save_graph_summary_cache(cache)
    return summaries


def fresh_status_summaries_for_graphs(paths: list[Path]) -> list[dict[str, Any]]:
    """Status views should be live; cache is only for repeated screen redraws."""
    return [status_summary_for_graph(path) for path in paths]


def invalidate_graph_summary_cache(graph_path: Path | None = None) -> int:
    """Invalidate cache entries so stale data never appears after a graph edit.

    If graph_path is given, only that entry is purged; otherwise the entire
    cache is cleared.  Returns the number of entries removed.
    """
    cache = load_graph_summary_cache()
    entries = cache.setdefault("entries", {})
    if graph_path is not None:
        key = graph_cache_key(graph_path)
        if key in entries:
            del entries[key]
            save_graph_summary_cache(cache)
            return 1
        return 0
    count = len(entries)
    entries.clear()
    save_graph_summary_cache(cache)
    return count


def epic_child_status_lines(graphs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build per-sprint child-node summary rows for the status surface.

    Each row contains sid, description, node_counts, ready_nodes, and
    quota_blocker (populated from the graph's guard data).
    """
    rows: list[dict[str, Any]] = []
    for g in graphs:
        if not g.get("ok"):
            continue
        sid = str(g.get("sid") or "")
        counts = g.get("counts") or {}
        ready = g.get("ready") or []
        desc = str(g.get("description") or "N/A")
        rows.append({
            "sid": sid,
            "description": desc,
            "node_counts": counts,
            "ready_nodes": ready,
            "quota_blocker": "",
        })
    return rows


def _quota_blocker_text(graphs: list[dict[str, Any]], guard: dict[str, Any]) -> str:
    """Derive a short quota-blocker label for the status surface."""
    if guard.get("ok"):
        return ""
    reason = str(guard.get("reason") or "")
    if "quota" in reason.lower() or "rate_limit" in reason.lower():
        hits = guard.get("hits") or []
        if hits:
            return f"quota_blocked({len(hits)} tasks)"
        return "quota_blocked"
    return reason[:30]


def scope_conflicts_with_active(node: dict[str, Any]) -> bool:
    for task in active_tasks():
        scopes = task.get("write_scope")
        if not scopes:
            continue
        other = {"id": task.get("node_id"), "write_scope": scopes}
        try:
            if write_scope_conflict(node, other):
                return True
        except Exception:
            return True
    return False


def build_dispatch_text(graph_path: Path, graph: dict[str, Any], node: dict[str, Any], dispatch_id: str, window: str,
                        profile: dict[str, Any]) -> str:
    sid = sprint_id_for(graph, graph_path)
    node_id = str(node.get("id") or "")
    handoff = SPRINTS_DIR / f"{sid}.{node_id}-handoff.md"
    harness = HARNESS_DIR / "solar-harness.sh"
    persona_path, persona_body = persona_text(str(profile.get("persona") or "builder"))

    def lines(value: Any) -> str:
        if value is None or value == "":
            return "- N/A"
        if isinstance(value, str):
            return f"- {value}"
        if isinstance(value, list):
            return "\n".join(f"- {item}" for item in value) if value else "- N/A"
        if isinstance(value, dict):
            return "\n".join(f"- {k}: {v}" for k, v in value.items()) if value else "- N/A"
        return f"- {value}"

    return f"""<!-- SOLAR_MULTI_TASK_DISPATCH -->
# Solar Harness Multi-Task DAG Dispatch

Sprint: `{sid}`
Node: `{node_id}`
Dispatch ID: `{dispatch_id}`
Execution plane: `tmux:{SESSION}:{window}`
Role/Profile: `{profile.get("role")}` / `{profile.get("name")}`
Backend/Model: `{profile.get("backend")}` / `{profile.get("model")}`
Graph: `{graph_path}`
Handoff: `{handoff}`

## Definition of Done

任务没有完成，除非同时满足：

1. 真实调用链接入：新增/修改功能必须接入真实调用链。
2. 禁止硬编码：不得硬编码业务数据、路径、token、测试数据、feature flag。
3. 测试必须运行：不能运行时写清原因和风险。
4. 执行证据齐全：列出实际命令和结果摘要。
5. Diff 自审：列出每个改动文件的目的。
6. 禁用乐观词：存在未完成项时禁止报喜。
7. 结构化收尾：已完成 / 已验证 / 未验证 / 风险 / 后续待办。

## Worker Persona

Persona file: `{persona_path}`

```markdown
{persona_body}
```

## Goal

{node.get("goal") or node.get("title") or "N/A"}

## Read Scope

{lines(node.get("read_scope"))}

## Write Scope

{lines(node.get("write_scope"))}

## Required Skills

{lines(node.get("required_skills"))}

## Required Capabilities

{lines(node.get("required_capabilities"))}

## Acceptance

{lines(node.get("acceptance"))}

## Rules

- 只执行本节点，不抢其他 DAG node。
- 只修改 Write Scope；需要扩大范围时在 handoff 里写 Scope Change Request。
- 不要把 parent sprint 标成 passed。
- 交付必须写 handoff。没有 handoff，后台 runner 会把本节点判为失败。

## Required Closeout

1. 写入 handoff：

```bash
cat > "{handoff}" <<'EOF'
# Handoff — {sid} / {node_id}

## 已完成

## 已验证

## 未验证

## 风险

## 后续待办
EOF
```

2. 将节点标记为 reviewing：

```bash
"{harness}" graph-scheduler mark --graph "{graph_path}" --node "{node_id}" --status reviewing --in-place
```
"""


def runner_script(task_dir: Path, payload: dict[str, Any]) -> Path:
    runner = task_dir / "runner.sh"
    dispatch_file = task_dir / "dispatch.md"
    status_file = task_dir / "status.json"
    harness = HARNESS_DIR / "solar-harness.sh"
    graph = Path(str(payload["graph"]))
    handoff = Path(str(payload["handoff"]))
    node_id = str(payload["node_id"])
    sid = str(payload["sprint_id"])
    role = str(payload.get("role") or "N/A")
    profile = str(payload.get("profile") or "N/A")
    backend = str(payload.get("backend") or "claude-cli")
    model = str(payload.get("model") or "sonnet")
    provider = str(payload.get("provider") or model_provider(model, backend))
    capability_status = str(payload.get("capability_status") or "N/A")
    approval_mode = str(payload.get("approval_mode") or "auto_edit")
    review_required = bool(payload.get("review_required"))
    agent_cmd = str(payload.get("command") or os.environ.get("SOLAR_MULTI_TASK_AGENT_CMD", "")).strip()
    work_dir = str(payload.get("work_dir") or os.getcwd())
    adapter = HARNESS_DIR / "lib" / "gemini_adapter.py"
    if backend == "gemini-cli":
        agent_line = f"python3 {shlex.quote(str(adapter))} run --backend cli --model {shlex.quote(model)} --approval-mode {shlex.quote(approval_mode)} --auth subscription --prompt-file \"$DISPATCH_FILE\""
    elif backend == "gemini-sdk":
        agent_line = f"python3 {shlex.quote(str(adapter))} run --backend sdk --model {shlex.quote(model)} --prompt-file \"$DISPATCH_FILE\""
    elif backend == "command":
        agent_line = f"SOLAR_MULTI_TASK_DISPATCH_FILE=\"$DISPATCH_FILE\" bash -lc {shlex.quote(agent_cmd)}"
    else:
        agent_line = claude_agent_line(model)
    script = f"""#!/usr/bin/env bash
set -u
TASK_DIR={shlex.quote(str(task_dir))}
STATUS_FILE={shlex.quote(str(status_file))}
DISPATCH_FILE={shlex.quote(str(dispatch_file))}
OUTPUT_LOG="$TASK_DIR/output.log"
RUN_STARTED_MARKER="$TASK_DIR/run.started"
HARNESS_DIR={shlex.quote(str(HARNESS_DIR))}
HARNESS_BIN="$HARNESS_DIR/bin"
SPRINTS_DIR={shlex.quote(str(SPRINTS_DIR))}
GRAPH={shlex.quote(str(graph))}
NODE_ID={shlex.quote(node_id)}
SID={shlex.quote(sid)}
ROLE={shlex.quote(role)}
PROFILE={shlex.quote(profile)}
BACKEND={shlex.quote(backend)}
MODEL={shlex.quote(model)}
PROVIDER={shlex.quote(provider)}
CAPABILITY_STATUS={shlex.quote(capability_status)}
REVIEW_REQUIRED={"1" if review_required else "0"}
HANDOFF={shlex.quote(str(handoff))}
HARNESS={shlex.quote(str(harness))}
WORK_DIR={shlex.quote(work_dir)}
export TASK_DIR STATUS_FILE DISPATCH_FILE OUTPUT_LOG RUN_STARTED_MARKER HARNESS_DIR HARNESS_BIN SPRINTS_DIR GRAPH NODE_ID SID ROLE PROFILE BACKEND MODEL PROVIDER CAPABILITY_STATUS HANDOFF HARNESS WORK_DIR
export PATH="$HARNESS_BIN:$PATH"
export SOLAR_SAFE_FIND_ROOT="$WORK_DIR"

pane_title() {{
  local title="$1"
  if [[ -n "${{TMUX:-}}" ]]; then
    tmux select-pane -T "$title" >/dev/null 2>&1 || true
  fi
}}

write_status() {{
  local status="$1" exit_code="${{2:-}}"
  python3 - "$STATUS_FILE" "$status" "$exit_code" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
data = {{}}
if p.exists():
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        data = {{}}
data["status"] = sys.argv[2]
data["exit_code"] = None if sys.argv[3] == "" else int(sys.argv[3])
data["updated_at"] = sys.argv[4]
data.setdefault("created_at", sys.argv[4])
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
PY
}}

mkdir -p "$TASK_DIR"
: > "$RUN_STARTED_MARKER"
write_status running
pane_title "MT $ROLE/$PROFILE | 模型:$MODEL | provider:$PROVIDER | 状态:running"

if [[ "${{SOLAR_MULTI_TASK_SANITIZE_ENV:-1}}" != "0" ]]; then
  unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_EXECPATH
  unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY
fi

{{
  echo "[solar-harness multi-task] sid=$SID node=$NODE_ID backend=$BACKEND model=$MODEL start=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[solar-harness multi-task] sid=$SID node=$NODE_ID agent_launch backend=$BACKEND profile=$PROFILE dispatch=$DISPATCH_FILE"
  (
    if [[ "$BACKEND" == "command" && -z {shlex.quote(agent_cmd)} ]]; then
      echo "ERROR: backend=command requires SOLAR_MULTI_TASK_AGENT_CMD"
      exit 127
    elif [[ -n {shlex.quote(agent_cmd)} && "$BACKEND" != "command" ]]; then
      SOLAR_MULTI_TASK_DISPATCH_FILE="$DISPATCH_FILE" bash -lc {shlex.quote(agent_cmd)}
    else
      if [[ "$BACKEND" == "claude-cli" ]] && ! command -v claude >/dev/null 2>&1; then
        echo "ERROR: claude command not found; set SOLAR_MULTI_TASK_AGENT_CMD"
        exit 127
      fi
      {agent_line}
    fi
  ) &
  agent_pid=$!
  echo "$agent_pid" > "$TASK_DIR/agent.pid"
  echo "[solar-harness multi-task] sid=$SID node=$NODE_ID agent_pid=$agent_pid"
  sleep "${{SOLAR_MULTI_TASK_AGENT_START_GRACE_SEC:-2}}"
  if kill -0 "$agent_pid" >/dev/null 2>&1; then
    echo "[solar-harness multi-task] sid=$SID node=$NODE_ID agent_alive_after_grace=true"
  else
    echo "[solar-harness multi-task] sid=$SID node=$NODE_ID agent_alive_after_grace=false"
  fi
  wait "$agent_pid"
  agent_rc=$?
  echo "[solar-harness multi-task] sid=$SID node=$NODE_ID agent_exit=$agent_rc at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}} > >(tee -a "$OUTPUT_LOG") 2>&1
rc=${{agent_rc:-$?}}

graph_node_status() {{
  python3 - "$GRAPH" "$NODE_ID" <<PY 2>/dev/null || true
import json, sys
from pathlib import Path
try:
    graph = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    node_id = sys.argv[2]
    for node in graph.get("nodes", []):
        if str(node.get("id") or "") == node_id:
            print(str(node.get("status") or ""))
            break
except Exception:
    pass
PY
}}

mark_graph_failed_unless_passed() {{
  local current
  current="$(graph_node_status | tail -n 1)"
  if [[ "$current" == "passed" ]]; then
    echo "[solar-harness multi-task] sid=$SID node=$NODE_ID late_failure_ignored_graph_already_passed=true" | tee -a "$OUTPUT_LOG"
    return 2
  fi
  "$HARNESS" graph-scheduler mark --graph "$GRAPH" --node "$NODE_ID" --status failed --in-place >> "$OUTPUT_LOG" 2>&1 || true
  return 0
}}

if [[ "$rc" -eq 0 && -s "$HANDOFF" && "$HANDOFF" -nt "$RUN_STARTED_MARKER" ]]; then
  success_status="${{SOLAR_MULTI_TASK_SUCCESS_STATUS:-passed}}"
  if [[ "$REVIEW_REQUIRED" == "1" ]]; then
    success_status="reviewing"
  fi
  "$HARNESS" graph-scheduler mark --graph "$GRAPH" --node "$NODE_ID" --status "$success_status" --in-place >> "$OUTPUT_LOG" 2>&1 || true
  write_status completed "$rc"
  pane_title "MT $ROLE/$PROFILE | 模型:$MODEL | provider:$PROVIDER | 状态:completed"
elif [[ "$rc" -eq 0 && -s "$HANDOFF" ]]; then
  echo "ERROR: stale handoff predates current run: $HANDOFF" | tee -a "$OUTPUT_LOG"
  if mark_graph_failed_unless_passed; then
    write_status failed_stale_handoff 66
  else
    write_status failed_aligned 66
  fi
  pane_title "MT $ROLE/$PROFILE | 模型:$MODEL | provider:$PROVIDER | 状态:failed_stale_handoff"
  rc=66
elif [[ "$rc" -eq 0 ]]; then
  echo "ERROR: missing handoff: $HANDOFF" | tee -a "$OUTPUT_LOG"
  if mark_graph_failed_unless_passed; then
    write_status failed_missing_handoff 65
  else
    write_status failed_aligned 65
  fi
  pane_title "MT $ROLE/$PROFILE | 模型:$MODEL | provider:$PROVIDER | 状态:failed_missing_handoff"
  rc=65
else
  if mark_graph_failed_unless_passed; then
    write_status failed "$rc"
  else
    write_status failed_aligned "$rc"
  fi
  pane_title "MT $ROLE/$PROFILE | 模型:$MODEL | provider:$PROVIDER | 状态:failed"
fi
echo "[solar-harness multi-task] sid=$SID node=$NODE_ID exit=$rc end=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$OUTPUT_LOG"
exit "$rc"
"""
    runner.write_text(script, encoding="utf-8")
    runner.chmod(0o755)
    return runner


def tmux_start(window: str, runner: Path, cwd: Path, dry_run: bool = False) -> None:
    if dry_run:
        return
    cmd = f"bash {shlex.quote(str(runner))}; exec ${{SHELL:-/bin/zsh}}"
    if subprocess.run(["tmux", "has-session", "-t", SESSION], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        subprocess.check_call(["tmux", "new-window", "-d", "-t", SESSION, "-n", window, "-c", str(cwd), cmd])
    else:
        subprocess.check_call(["tmux", "new-session", "-d", "-s", SESSION, "-n", window, "-c", str(cwd), cmd])
    target = f"{SESSION}:{window}"
    subprocess.run(["tmux", "set-window-option", "-t", target, "pane-border-status", "bottom"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(
        ["tmux", "set-window-option", "-t", target, "pane-border-format", "#[fg=cyan] #T #[default]"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def launch_node(graph_path: Path, graph: dict[str, Any], node: dict[str, Any], args: argparse.Namespace,
                dry_run: bool = False) -> dict[str, Any]:
    sid = sprint_id_for(graph, graph_path)
    node_id = str(node.get("id") or "")
    profile = select_profile(node, getattr(args, "profile", "") or "", getattr(args, "model", "") or "", getattr(args, "backend", "") or "")
    capability = capability_for_profile(profile)
    dispatch_id = task_id(sid, node_id)
    window = short_window(f"{dispatch_id}-{profile.get('role')}-{node_id}")
    task_dir = RUN_DIR / dispatch_id
    handoff = SPRINTS_DIR / f"{sid}.{node_id}-handoff.md"
    task_dir.mkdir(parents=True, exist_ok=True)

    dispatch = build_dispatch_text(graph_path, graph, node, dispatch_id, window, profile)
    (task_dir / "dispatch.md").write_text(dispatch, encoding="utf-8")
    payload = {
        "id": dispatch_id,
        "status": "dry_run" if dry_run else "dispatched",
        "session": SESSION,
        "window": window,
        "profile": profile.get("name"),
        "role": profile.get("role"),
        "persona": profile.get("persona"),
        "backend": profile.get("backend"),
        "model": profile.get("model"),
        "command": profile.get("command"),
        "provider": capability.get("provider"),
        "capability_status": capability.get("status"),
        "approval_mode": profile.get("approval_mode"),
        "operator_id": profile.get("operator_id") or "N/A",
        "operator_vendor": profile.get("operator_vendor") or capability.get("provider") or "N/A",
        "operator_model": profile.get("operator_model") or profile.get("model") or "N/A",
        "operator_pane": profile.get("operator_pane") or "N/A",
        "operator_quota_refresh_at": profile.get("operator_quota_refresh_at") or "N/A",
        "operator_fallback_reason": profile.get("operator_fallback_reason") or "",
        "quota_fallback_from": profile.get("quota_fallback_from") or node.get("quota_fallback_from") or "",
        "quota_fallback_reason": profile.get("quota_fallback_reason") or node.get("quota_fallback_reason") or "",
        "graph": str(graph_path),
        "sprint_id": sid,
        "node_id": node_id,
        "title": str(node.get("goal") or node.get("title") or node_id)[:120],
        "write_scope": node.get("write_scope") or [],
        "handoff": str(handoff),
        "dispatch_file": str(task_dir / "dispatch.md"),
        "work_dir": str(Path.cwd()),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "exit_code": None,
    }
    json_write(status_path(task_dir), payload)
    runner = runner_script(task_dir, payload)

    if not dry_run:
        try:
            tmux_start(window, runner, Path.cwd())
        except Exception as exc:
            payload["status"] = "failed_launch"
            payload["updated_at"] = now_iso()
            payload["error"] = str(exc)
            json_write(status_path(task_dir), payload)
            (task_dir / "output.log").write_text(f"ERROR: tmux launch failed: {exc}\n", encoding="utf-8")
            return payload
        set_node_status(graph, node_id, "dispatched", pane=f"multi-task:{window}", dispatch_id=dispatch_id)
        save_graph(graph_path, graph)
        set_last_launch()

    return payload


def schedule_once(args: argparse.Namespace) -> dict[str, Any]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    max_workers = effective_scheduler_max_workers(max(1, int(args.max_workers)))
    recovered_quota_failures = 0
    for graph_path in graph_files(args.graph):
        try:
            graph = load_graph(graph_path)
            recovered_quota_failures += recover_quota_failed_nodes(graph_path, graph)
        except Exception:
            continue
    guard = launch_guard(max_workers, args.memory_reserve_gb, args.cooldown_sec, args.quota_backoff_sec)
    if (
        recovered_quota_failures
        and guard.get("reason") == "recent_quota_or_rate_limit"
        and os.environ.get("SOLAR_MULTI_TASK_BYPASS_QUOTA_GUARD_FOR_FALLBACK") == "1"
    ):
        guard = dict(guard)
        guard["ok"] = True
        guard["reason"] = "recent_quota_or_rate_limit_bypassed_for_fallback"
        guard["recovered_quota_failures"] = recovered_quota_failures
    active_rows = active_tasks()
    slots = max(0, max_workers - len(active_rows))
    parallel_counts = active_parallel_counts(active_rows)
    launched: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    cap_summary = capability_summary()

    if not guard.get("ok") and not args.dry_run:
        return {
            "guard": guard,
            "launched": launched,
            "skipped": skipped,
            "graphs": cached_status_summaries_for_graphs(graph_files(args.graph)),
            "panes": list_harness_panes(),
            "dispatches": recent_dispatch_rows(),
            "capability": cap_summary,
            "recovered_quota_failures": recovered_quota_failures,
        }

    for graph_path in graph_files(args.graph):
        if slots <= 0 and not args.dry_run:
            break
        try:
            graph = load_graph(graph_path)
            summaries.append(status_summary_for_graph(graph_path))
            candidates = ready_nodes(graph)
        except Exception as exc:
            skipped.append({"graph": str(graph_path), "reason": "graph_error", "error": str(exc)})
            continue
        for node in candidates:
            if slots <= 0 and not args.dry_run:
                break
            if scope_conflicts_with_active(node):
                skipped.append({"graph": str(graph_path), "node": node.get("id"), "reason": "write_scope_conflict_with_active"})
                continue
            try:
                profile = select_profile(node, getattr(args, "profile", "") or "", getattr(args, "model", "") or "", getattr(args, "backend", "") or "")
                capability = capability_for_profile(profile)
            except Exception as exc:
                skipped.append({"graph": str(graph_path), "node": node.get("id"), "reason": "capability_error", "error": str(exc)})
                continue
            parallel_guard = profile_parallel_limit_reached(profile, parallel_counts)
            if not parallel_guard.get("ok"):
                skipped.append({
                    "graph": str(graph_path),
                    "node": node.get("id"),
                    "reason": parallel_guard.get("reason"),
                    "profile": parallel_guard.get("profile"),
                    "active": parallel_guard.get("active"),
                    "limit": parallel_guard.get("limit"),
                })
                continue
            if capability.get("status") != "ok":
                skipped.append({
                    "graph": str(graph_path),
                    "node": node.get("id"),
                    "reason": "capability_unavailable",
                    "profile": capability.get("profile"),
                    "model": capability.get("model"),
                    "backend": capability.get("backend"),
                    "status": capability.get("status"),
                    "evidence": capability.get("evidence"),
                })
                continue
            launched.append(launch_node(graph_path, graph, node, args, dry_run=args.dry_run))
            if not args.dry_run:
                slots -= 1
                profile_name = normalize_profile_name(str(profile.get("name") or ""))
                role = str(profile.get("role") or "").strip().lower()
                if profile_name:
                    parallel_counts.setdefault("profile", {})
                    parallel_counts["profile"][profile_name] = int(parallel_counts["profile"].get(profile_name, 0)) + 1
                if role:
                    parallel_counts.setdefault("role", {})
                    parallel_counts["role"][role] = int(parallel_counts["role"].get(role, 0)) + 1

    if not summaries:
        summaries = cached_status_summaries_for_graphs(graph_files(args.graph))
    return {
        "guard": guard,
        "launched": launched,
        "skipped": skipped,
        "graphs": summaries,
        "panes": list_harness_panes(),
        "dispatches": recent_dispatch_rows(),
        "capability": cap_summary,
        "recovered_quota_failures": recovered_quota_failures,
    }


def status_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    """Read current worker and DAG state without dispatching new work."""
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    max_workers = effective_scheduler_max_workers(max(1, int(getattr(args, "max_workers", DEFAULT_MAX_WORKERS))))
    memory_reserve_gb = float(getattr(args, "memory_reserve_gb", DEFAULT_MEMORY_RESERVE_GB))
    cooldown_sec = int(getattr(args, "cooldown_sec", DEFAULT_COOLDOWN))
    quota_backoff_sec = int(getattr(args, "quota_backoff_sec", DEFAULT_QUOTA_BACKOFF))
    graph_arg = getattr(args, "graph", [])
    return {
        "guard": launch_guard(max_workers, memory_reserve_gb, cooldown_sec, quota_backoff_sec),
        "launched": [],
        "skipped": [],
        "graphs": fresh_status_summaries_for_graphs(graph_files(graph_arg)),
        "panes": list_harness_panes(),
        "dispatches": recent_dispatch_rows(),
        "capability": capability_summary(),
        "observed_at": now_iso(),
        "refresh_mode": "fresh",
    }


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [_display_width(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _display_width(str(cell)))
    top = "┌" + "┬".join("─" * (w + 2) for w in widths) + "┐"
    mid = "├" + "┼".join("─" * (w + 2) for w in widths) + "┤"
    bot = "└" + "┴".join("─" * (w + 2) for w in widths) + "┘"
    print(top)
    print("│ " + " │ ".join(_pad_display(str(h), widths[i]) for i, h in enumerate(headers)) + " │")
    print(mid)
    for row in rows:
        print("│ " + " │ ".join(_pad_display(str(c), widths[i]) for i, c in enumerate(row)) + " │")
    print(bot)


def render_plain(result: dict[str, Any], no_clear: bool = False) -> None:
    if not no_clear and sys.stdout.isatty():
        print("\033[H\033[2J", end="")
    guard = result.get("guard") or {}
    mem = free_memory_gb()
    tasks = list_task_rows()[:20]
    active = [t for t in tasks if str(t.get("effective_status") or t.get("status", "")).lower() in ACTIVE_TASK_STATUSES]
    inventory = task_inventory(tasks)
    cap_summary = result.get("capability") or capability_summary()
    mt_live = tmux_session_exists()
    data_source = "live" if mt_live and inventory["live"] else ("history:no_multi_task_session" if tasks and not mt_live else "no_live_workers")
    print("Solar Harness Multi-Task · tmux DAG worker pool")
    print("模型组合: " + format_capability_summary_compact(cap_summary))
    print_table(
        ["项目", "状态", "值"],
        [
            ["session", "ok", SESSION],
            ["harness_panes", "ok" if result.get("panes") else "warn", str(len([p for p in result.get("panes", []) if p.get("plane") != "multi-task"]))],
            ["multi_task_session", "ok" if mt_live else "warn", "live" if mt_live else "missing"],
            ["active_workers", "ok" if inventory["live"] else "warn", f"{inventory['live']} live / {len(active)} active"],
            ["tracked_tasks", "ok" if tasks and not inventory["stale"] else "warn", f"{inventory['total']} total · history={inventory['historical']} stale={inventory['stale']}"],
            ["data_source", "ok" if data_source == "live" else "warn", data_source],
            ["latest_task_age", "ok" if inventory["latest_age"] not in ("N/A",) and not inventory["stale"] else "warn", str(inventory["latest_age"])],
            ["launch_guard", "ok" if guard.get("ok") else "warn", str(guard.get("reason", "N/A"))],
            ["quota_blocker", "ok" if not _quota_blocker_text(result.get("graphs") or [], guard) else "warn", _quota_blocker_text(result.get("graphs") or [], guard) or "none"],
            ["free_memory_gb", "ok" if mem is None or mem >= DEFAULT_MEMORY_RESERVE_GB else "warn", "N/A" if mem is None else f"{mem:.2f}"],
            ["refresh_mode", "ok", str(result.get("refresh_mode") or "cached")],
            ["checked_at", "ok", str(result.get("observed_at") or now_iso())],
        ],
    )

    pane_rows = [[
        _clip_display(str(p.get("plane", "N/A")), 12),
        _clip_display(str(p.get("pane", "N/A")), 28),
        _clip_display(str(p.get("role", "N/A")), 12),
        _clip_display(str(p.get("state", "N/A")), 28),
        _clip_display(str(p.get("model", "N/A")), 10),
        _clip_display(str(p.get("command", "N/A")), 10),
    ] for p in (result.get("panes") or [])[:16]]
    print()
    print_table(
        ["plane", "pane", "role", "state", "model", "cmd"],
        pane_rows or [["N/A", "N/A", "N/A", "N/A", "N/A", "N/A"]],
    )

    task_rows = [[
        _clip_display(str(t.get("id", "N/A")), 24),
        _clip_display(str(t.get("effective_status") or t.get("status", "N/A")), 18),
        _clip_display(str(t.get("data_class", "N/A")), 12),
        _clip_display(str(t.get("pane_type", "N/A")), 22),
        _clip_display(str(t.get("operator_id") or "N/A"), 18),
        _clip_display(str(t.get("operator_vendor") or t.get("provider") or "N/A"), 12),
        _clip_display(str(t.get("operator_pane") or "N/A"), 16),
        _clip_display(str(t.get("tmux_status", "N/A")), 10),
        _clip_display(f"{t.get('sprint_id', 'N/A')}#{t.get('node_id', 'N/A')}", 32),
        _clip_display(str(t.get("age", "N/A")), 8),
    ] for t in tasks]
    print()
    print_table(
        ["multi_task", "status", "class", "pane_type", "operator", "vendor", "op_pane", "tmux", "sprint#node", "age"],
        task_rows or [["N/A", "pending", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"]],
    )

    dispatch_rows = [[
        _clip_display(str(d.get("time", "N/A")), 20),
        _clip_display(str(d.get("pane", "N/A")), 24),
        _clip_display(str(d.get("role", "N/A")), 12),
        _clip_display(f"{d.get('sprint', 'N/A')}#{d.get('node', 'N/A')}", 38),
        _clip_display(str(d.get("kind", "N/A")), 16),
    ] for d in (result.get("dispatches") or [])[:12]]
    print()
    print_table(
        ["time", "pane", "role", "sprint#node", "kind"],
        dispatch_rows or [["N/A", "N/A", "N/A", "N/A", "N/A"]],
    )

    graph_rows = []
    for graph in result.get("graphs", [])[:12]:
        counts = graph.get("counts") or {}
        graph_rows.append([
            _clip_display(str(graph.get("sid", "N/A")), 28),
            _clip_display(str(graph.get("description", "N/A")), 32),
            "ok" if graph.get("ok") else "error",
            _clip_display(",".join(f"{k}:{v}" for k, v in sorted(counts.items())) or "N/A", 28),
            _clip_display(",".join(graph.get("ready") or []) or "N/A", 18),
            _clip_display(str(graph.get("graph_updated_at", "N/A")), 20),
        ])
    print()
    print_table(
        ["sprint", "说明", "状态", "node_counts", "ready", "graph_updated"],
        graph_rows or [["N/A", "N/A", "pending", "N/A", "N/A", "N/A"]],
    )

    # Epic child-sprint status surface
    child_rows = epic_child_status_lines(result.get("graphs") or [])
    if child_rows:
        print()
        print_table(
            ["child_sprint", "说明", "node_counts", "ready_nodes"],
            [[
                _clip_display(str(r["sid"]), 28),
                _clip_display(str(r["description"]), 32),
                _clip_display(",".join(f"{k}:{v}" for k, v in sorted(r["node_counts"].items())) or "N/A", 28),
                _clip_display(",".join(r["ready_nodes"]) or "N/A", 28),
            ] for r in child_rows],
        )

    launched = result.get("launched") or []
    if launched:
        print()
        print_table("launched status sprint node".split(), [[
            str(x.get("id", "N/A"))[:34],
            str(x.get("status", "N/A")),
            str(x.get("sprint_id", "N/A"))[:20],
            str(x.get("node_id", "N/A"))[:24],
        ] for x in launched])
    skipped = result.get("skipped") or []
    if skipped:
        print()
        print_table(["node", "reason", "status", "evidence"], [[
            str(x.get("node", "N/A"))[:24],
            str(x.get("reason", "N/A"))[:28],
            str(x.get("status", "N/A"))[:10],
            str(x.get("evidence", x.get("error", "N/A")))[:70],
        ] for x in skipped[:12]])


def render_to_lines(result: dict[str, Any]) -> list[str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        render_plain(result, no_clear=True)
    return buf.getvalue().splitlines()


def render_screen_status_lines(view_model: dict[str, Any], width: int, height: int) -> list[str]:
    """Compact plain-text fallback renderer consuming a v1 view_model.

    Backward compat: if view_model lacks schema_version (old result dict passed),
    coerces via screen_view_model() for one release. Deprecated after S05.
    """
    if "schema_version" not in view_model:
        view_model = screen_view_model(view_model, argparse.Namespace(), width)

    content_width = max(40, width)
    health = view_model.get("health") or {}
    panes = view_model.get("panes") or []
    workers = view_model.get("workers") or {}
    last_dispatch = view_model.get("last_dispatch") or {}
    dag = view_model.get("dag") or {}
    degraded = view_model.get("degraded") or []

    def _cap_verdict(label: str) -> str:
        for c in (health.get("capsules") or []):
            if c.get("label") == label:
                return str(c.get("verdict", "N/A"))
        return "N/A"

    def pair(left: str, right: str = "") -> str:
        if content_width < 76:
            return _clip_display(left, content_width)
        left_width = 30
        right_width = max(20, content_width - left_width - 3)
        return _clip_display(
            _pad_display(_clip_display(left, left_width), left_width) + " | " + _clip_display(right, right_width),
            content_width,
        )

    def _vm_pane_row(pane: dict[str, Any] | None, width_: int) -> str:
        if not pane:
            return ""
        label = str(pane.get("label", "N/A"))
        role = str(pane.get("role", "N/A"))
        state = str(pane.get("state", "N/A"))
        model = str(pane.get("model", "N/A")).replace("GLM-5.1", "GLM").replace("Sonnet", "Sonn")
        marker = str(pane.get("marker", " "))
        return _clip_display(
            f"{marker}{role:<5} {_clip_display(label, 7):<7} "
            f"{_clip_display(model, 5):<5} {_clip_display(state, 5):<5}",
            width_,
        )

    lines: list[str] = []

    w_active = int(workers.get("active", 0) or 0)
    w_tracked = int(workers.get("tracked", 0) or 0)
    degrade_tag = f"  degraded={len(degraded)}" if degraded else ""
    lines.append(_clip_display(
        f"Solar Harness Multi-Task  panes={len(panes)}  live={w_active} tracked={w_tracked}{degrade_tag}",
        content_width,
    ))

    mt_v = _cap_verdict("tmux")
    guard_v = _cap_verdict("guard")
    models_v = _cap_verdict("models")
    overall_v = str(health.get("verdict", "N/A"))
    lines.append(_clip_display(
        f"[{mt_v}] tmux  [{guard_v}] guard  [{models_v}] models  verdict={overall_v}",
        content_width,
    ))

    main_panes = [p for p in panes if p.get("plane") == "main"]
    lab_panes = [p for p in panes if p.get("plane") == "lab"]
    lines.append(pair("PANE MAP", "Builder Lab"))
    max_rows = max(len(main_panes[:4]), len(lab_panes[:4]), 1)
    for idx in range(max_rows):
        left = _vm_pane_row(main_panes[idx] if idx < len(main_panes) else None, 30)
        right = _vm_pane_row(lab_panes[idx] if idx < len(lab_panes) else None, 30)
        lines.append(pair(left, right))

    if len(lines) < height:
        counts = workers.get("counts") or {}
        counts_text = ",".join(f"{k}:{v}" for k, v in sorted(counts.items())) or "N/A"
        lines.append(_clip_display(
            f"WORKERS active={w_active} tracked={w_tracked}  {counts_text}",
            content_width,
        ))

    if len(lines) < height:
        d_time = str(last_dispatch.get("time", "N/A"))
        d_role = str(last_dispatch.get("role", "N/A"))
        d_pane = str(last_dispatch.get("pane", "N/A"))
        d_target = str(last_dispatch.get("target", "N/A"))
        lines.append(_clip_display(
            f"LAST {d_time} {d_role} {d_pane} -> {d_target}",
            content_width,
        ))

    if len(lines) < height:
        dag_sprint = str(dag.get("sprint", "N/A"))
        dag_counts = dag.get("counts") or {}
        dag_ready = dag.get("ready") or "N/A"
        if isinstance(dag_ready, list):
            dag_ready = ",".join(dag_ready) or "N/A"
        counts_str = " ".join(f"{k}={v}" for k, v in dag_counts.items())
        qb = str(dag.get("quota_blocker") or "")
        qb_tag = f"  ⚠{qb}" if qb else ""
        children = dag.get("children") or []
        child_tag = f"  children={len(children)}" if children else ""
        lines.append(_clip_display(
            f"DAG {dag_sprint}  {counts_str}  ready={dag_ready}{qb_tag}{child_tag}  用 status 查看完整视图",
            content_width,
        ))
    elif len(lines) < height:
        lines.append(_clip_display("用 status 查看完整视图", content_width))

    if len(lines) > height:
        return lines[: max(0, height - 1)] + [_clip_display(f"... 已省略 {len(lines) - height + 1} 行；用 status 查看完整视图", content_width)]
    return lines


# --- S03 N2: view-model + tvs payload (add-only; existing renderers untouched) ---

SCREEN_VIEW_MODEL_SCHEMA = "multi_task_screen.view_model.v1"


def _screen_short_pane(pane_id: str) -> str:
    text = str(pane_id or "")
    if text.startswith(f"{MAIN_SESSION}:"):
        return "main:" + text.split(":", 1)[1].split(".")[-1]
    if text.startswith(f"{LAB_SESSION}:"):
        return "lab:" + text.split(":", 1)[1].split(".")[-1]
    return text or "N/A"


def _screen_role_label(role: str, pane_short: str) -> str:
    norm = str(role or "").lower()
    if norm == "pm":
        return "PM"
    if norm == "planner":
        return "PLAN"
    if norm == "builder":
        return "BUILD"
    if norm == "evaluator":
        return "EVAL"
    if "lab" in norm or pane_short.startswith("lab:"):
        return "LAB"
    return (norm[:5].upper() if norm else "N/A")


def _screen_state_word(state: str) -> str:
    s = str(state or "").lower()
    if s.startswith("working") or s.startswith("running"):
        return "working"
    if s.startswith("active"):
        return "active"
    if s.startswith("ready"):
        return "ready"
    if s.startswith("idle"):
        return "idle"
    if s.startswith("block"):
        return "blocked"
    if s.startswith("dry"):
        return "dry_run"
    if s.startswith("error") or "fail" in s:
        return "error"
    if s.startswith("warn"):
        return "warn"
    if s.startswith("pend"):
        return "pending"
    if s.startswith("ok") or s.startswith("pass"):
        return "ok"
    return "idle" if not s else s[:8]


def _screen_short_model(model: Any) -> str:
    text = str(model or "N/A")
    return text.replace("GLM-5.1", "GLM").replace("Sonnet", "Sonn")[:8] or "N/A"


def _screen_short_target(sprint: Any, node: Any) -> str:
    sid = str(sprint or "")
    nid = str(node or "")
    s_match = re.search(r"s(\d{2})", sid)
    if s_match and nid:
        return f"S{s_match.group(1)}/{nid}"
    return nid or sid[:12] or "N/A"


def _screen_build_pane(pane: dict[str, Any] | None, plane: str, slot: int) -> dict[str, Any]:
    if not pane:
        return {
            "plane": plane,
            "slot": slot,
            "label": f"{plane}:{slot}",
            "role": "LAB" if plane == "lab" else "N/A",
            "state": "idle",
            "model": "N/A",
            "marker": " ",
            "low_confidence": True,
        }
    short = _screen_short_pane(str(pane.get("pane", "")))
    state = _screen_state_word(str(pane.get("state", "")))
    return {
        "plane": plane,
        "slot": slot,
        "label": short or f"{plane}:{slot}",
        "role": _screen_role_label(str(pane.get("role", "")), short),
        "state": state,
        "model": _screen_short_model(pane.get("model", "")),
        "marker": ">" if state == "working" else " ",
        "low_confidence": bool(pane.get("low_confidence", False)),
    }


def screen_view_model(result: dict[str, Any], args: argparse.Namespace, width: int) -> dict[str, Any]:
    """Build the multi-task screen view model (schema v1).

    Single source of truth consumed by both the TVS payload builder and the
    plain-text fallback renderer. State enum and panes-length=8 are locked
    by S02 architecture; this function is add-only per S03 N2 contract.
    """
    panes_src = result.get("panes") or []
    guard = result.get("guard") or {}
    cap_summary = result.get("capability") or {}
    dispatches = result.get("dispatches") or []
    graphs = result.get("graphs") or []

    cap_err = int(cap_summary.get("error", 0) or 0)
    cap_warn = int(cap_summary.get("warn", 0) or 0)
    guard_ok = bool(guard.get("ok"))
    overall_verdict = "error" if cap_err else ("warn" if (cap_warn or not guard_ok) else "ok")
    tmux_live = tmux_session_exists()
    capsules = [
        {"label": "models", "verdict": "ok" if cap_err == 0 else ("warn" if cap_warn else "error")},
        {"label": "guard", "verdict": "ok" if guard_ok else "warn"},
        {"label": "tmux", "verdict": "ok" if tmux_live else "warn"},
    ]

    main_src = [p for p in panes_src if p.get("plane") == "four-pane"][:4]
    lab_src = [p for p in panes_src if p.get("plane") == "builder-lab"][:4]
    panes_out: list[dict[str, Any]] = []
    for i in range(4):
        panes_out.append(_screen_build_pane(main_src[i] if i < len(main_src) else None, "main", i))
    for i in range(4):
        panes_out.append(_screen_build_pane(lab_src[i] if i < len(lab_src) else None, "lab", i))

    tasks = list_task_rows()
    inventory = task_inventory(tasks)
    statuses = inventory.get("statuses") or {}
    active_tasks = [t for t in tasks if str(t.get("status", "")).lower() in ACTIVE_TASK_STATUSES]
    workers = {
        "active": len(active_tasks),
        "tracked": int(inventory.get("total", 0) or 0),
        "counts": {
            "dry_run": int(statuses.get("dry_run", 0) or 0),
            "live": int(inventory.get("live", 0) or 0),
            "idle": int(statuses.get("idle", 0) or 0),
            "blocked": int(statuses.get("blocked", 0) or 0),
        },
    }

    last_dispatch: dict[str, Any] = {"time": "N/A", "role": "N/A", "pane": "N/A", "target": "N/A"}
    if dispatches:
        d = dispatches[0]
        match = re.search(r"T?(\d{2}:\d{2})", str(d.get("time", "")))
        last_dispatch = {
            "time": match.group(1) if match else "N/A",
            "role": str(d.get("role", "N/A")),
            "pane": _screen_short_pane(str(d.get("pane", "N/A"))),
            "target": _screen_short_target(d.get("sprint"), d.get("node")),
        }

    dag: dict[str, Any] = {"sprint": "N/A", "counts": {"pass": 0, "pending": 0, "reviewing": 0}, "ready": "N/A", "quota_blocker": "", "children": []}
    if graphs:
        g = graphs[0]
        sid = str(g.get("sid", "N/A"))
        s_match = re.search(r"s(\d{2})", sid)
        gc = g.get("counts") or {}
        dag = {
            "sprint": f"S{s_match.group(1)}" if s_match else sid[:12],
            "counts": {
                "pass": int(gc.get("passed", 0) or 0),
                "pending": int(gc.get("pending", 0) or 0),
                "reviewing": int(gc.get("reviewing", 0) or 0),
            },
            "ready": g.get("ready") or "N/A",
            "quota_blocker": _quota_blocker_text(graphs, guard),
            "children": epic_child_status_lines(graphs),
        }

    degraded: list[dict[str, Any]] = []
    if not tmux_live:
        degraded.append({"source": "multi_task_session", "reason": "tmux_not_live"})
    if not panes_src:
        degraded.append({"source": "panes", "reason": "empty"})

    return {
        "schema_version": SCREEN_VIEW_MODEL_SCHEMA,
        "generated_at": now_iso(),
        "health": {"verdict": overall_verdict, "capsules": capsules},
        "panes": panes_out,
        "workers": workers,
        "last_dispatch": last_dispatch,
        "dag": dag,
        "degraded": degraded,
    }


def screen_tvs_payload(view_model: dict[str, Any], args: argparse.Namespace, width: int) -> dict[str, Any]:
    """Build the TVS section payload from a v1 view_model (S03 N2).

    Consumes view_model only; does NOT fetch fresh data. Caller passes a
    view_model produced by screen_view_model so both render paths share a
    single source of truth.
    """
    panes = view_model.get("panes") or []
    pane_rows = [{
        "pane": str(p.get("label", "N/A")),
        "role": str(p.get("role", "N/A")),
        "state": str(p.get("state", "N/A")),
        "model": str(p.get("model", "N/A")),
        "marker": str(p.get("marker", " ")),
    } for p in panes]
    capsules = (view_model.get("health") or {}).get("capsules") or []
    return {
        "kind": "screen.v2",
        "width": int(width),
        "sections": [
            {"id": "header", "type": "capsules", "data": capsules},
            {"id": "pane-map", "type": "table", "data": pane_rows},
            {"id": "workers", "type": "kv", "data": view_model.get("workers") or {}},
            {"id": "dispatch", "type": "kv", "data": view_model.get("last_dispatch") or {}},
            {"id": "dag", "type": "kv", "data": view_model.get("dag") or {}},
        ],
    }


# --- end S03 N2 ---


# --- S03 N3: TVS dispatch stubs + draw_screen reroute ---

def _tvs_available(args: argparse.Namespace) -> bool:
    """Return True when the TVS render backend is loaded and usable. Stub: always False until TVS is wired (post-S03)."""
    return False


def _tvs_render(payload: dict[str, Any], height: int) -> None:
    """Dispatch a screen.v2 TVS payload to the TVS backend. Stub: no-op until TVS is wired (post-S03)."""


# --- end S03 N3 ---


def tvs_payload(result: dict[str, Any], width: int = 100) -> dict[str, Any]:
    guard = result.get("guard") or {}
    mem = free_memory_gb()
    tasks = list_task_rows()[:20]
    active = [t for t in tasks if str(t.get("status", "")).lower() in ACTIVE_TASK_STATUSES]
    inventory = task_inventory(tasks)
    tmux_live = tmux_session_exists()
    cap_summary = result.get("capability") or capability_summary()
    data_source = "live" if tmux_live and inventory["live"] else ("history:no_multi_task_session" if tasks and not tmux_live else "no_live_workers")
    task_rows = [{
        "task": _clip_display(str(t.get("id", "N/A")).replace("mt-", ""), 18),
        "state": _clip_display(f"{t.get('status', 'N/A')}/{t.get('tmux_status', 'N/A')}", 16),
        "class": _clip_display(str(t.get("data_class", "N/A")), 12),
        "pane_type": _clip_display(str(t.get("pane_type", "N/A")), 16),
        "operator": _clip_display(str(t.get("operator_id") or "N/A"), 16),
        "vendor": _clip_display(str(t.get("operator_vendor") or t.get("provider") or "N/A"), 10),
        "sprint_node": _clip_display(f"{t.get('sprint_id', 'N/A')}#{t.get('node_id', 'N/A')}", 28),
        "age": _clip_display(str(t.get("age", "N/A")), 8),
    } for t in tasks] or [{
        "task": "N/A", "state": "pending", "class": "N/A", "pane_type": "N/A", "operator": "N/A", "vendor": "N/A", "sprint_node": "N/A", "age": "N/A",
    }]

    pane_rows = [{
        "plane": _clip_display(str(p.get("plane", "N/A")), 12),
        "pane": _clip_display(str(p.get("pane", "N/A")), 24),
        "role": _clip_display(str(p.get("role", "N/A")), 12),
        "state": _clip_display(str(p.get("state", "N/A")), 24),
        "model": _clip_display(str(p.get("model", "N/A")), 10),
        "cmd": _clip_display(str(p.get("command", "N/A")), 10),
    } for p in (result.get("panes") or [])[:16]] or [{
        "plane": "N/A", "pane": "N/A", "role": "N/A", "state": "N/A", "model": "N/A", "cmd": "N/A",
    }]

    dispatch_rows = [{
        "time": _clip_display(str(d.get("time", "N/A")).replace("2026-", ""), 16),
        "pane": _clip_display(str(d.get("pane", "N/A")), 20),
        "role": _clip_display(str(d.get("role", "N/A")), 10),
        "sprint_node": _clip_display(f"{d.get('sprint', 'N/A')}#{d.get('node', 'N/A')}", 32),
    } for d in (result.get("dispatches") or [])[:12]] or [{
        "time": "N/A", "pane": "N/A", "role": "N/A", "sprint_node": "N/A",
    }]

    graph_rows = []
    for graph in result.get("graphs", [])[:12]:
        counts = graph.get("counts") or {}
        graph_rows.append({
            "sprint": str(graph.get("sid", "N/A"))[:28],
            "desc": str(graph.get("description", "N/A"))[:42],
            "status": "ok" if graph.get("ok") else "error",
            "node_counts": ",".join(f"{k}:{v}" for k, v in sorted(counts.items()))[:40] or "N/A",
            "ready": ",".join(graph.get("ready") or [])[:38] or "N/A",
            "graph_updated": str(graph.get("graph_updated_at", "N/A"))[:20],
        })
    if not graph_rows:
        graph_rows = [{"sprint": "N/A", "desc": "N/A", "status": "pending", "node_counts": "N/A", "ready": "N/A", "graph_updated": "N/A"}]

    sections: list[dict[str, Any]] = [
        {
            "type": "kv",
            "items": [
                {"key": "session", "value": SESSION},
                {"key": "harness_panes", "value": str(len([p for p in result.get("panes", []) if p.get("plane") != "multi-task"])), "status": "success" if result.get("panes") else "warning"},
                {"key": "multi_task_session", "value": "live" if tmux_live else "missing", "status": "success" if tmux_live else "warning"},
                {"key": "active_workers", "value": f"{inventory['live']} live / {len(active)} active", "status": "success" if inventory["live"] else "warning"},
                {"key": "tracked_tasks", "value": f"{inventory['total']} total · history={inventory['historical']} stale={inventory['stale']}", "status": "warning" if inventory["stale"] or not tasks else "success"},
                {"key": "data_source", "value": data_source, "status": "success" if data_source == "live" else "warning"},
                {"key": "latest_task_age", "value": str(inventory["latest_age"]), "status": "warning" if inventory["stale"] or inventory["latest_age"] == "N/A" else "success"},
                {"key": "launch_guard", "value": str(guard.get("reason", "N/A")), "status": "success" if guard.get("ok") else "warning"},
                {"key": "model_matrix", "value": format_capability_summary_compact(cap_summary), "status": "success" if cap_summary.get("error", 0) == 0 else "warning"},
                {"key": "free_memory_gb", "value": "N/A" if mem is None else f"{mem:.2f}", "status": "success" if mem is None or mem >= DEFAULT_MEMORY_RESERVE_GB else "warning"},
                {"key": "refresh_mode", "value": str(result.get("refresh_mode") or "cached")},
                {"key": "checked_at", "value": str(result.get("observed_at") or now_iso())},
            ],
        },
        {
            "type": "table",
            "columns": [
                {"key": "plane", "label": "plane", "width": 12},
                {"key": "pane", "label": "pane", "width": 22},
                {"key": "role", "label": "role", "width": 10},
                {"key": "state", "label": "state", "width": 22},
                {"key": "model", "label": "model", "width": 10},
                {"key": "cmd", "label": "cmd", "width": 9},
            ],
            "rows": pane_rows,
            "border": "minimal",
        },
        {
            "type": "table",
            "columns": [
                {"key": "task", "label": "multi_task", "width": 18},
                {"key": "state", "label": "state", "width": 14},
                {"key": "class", "label": "class", "width": 10},
                {"key": "pane_type", "label": "pane_type", "width": 16},
                {"key": "operator", "label": "operator", "width": 14},
                {"key": "vendor", "label": "vendor", "width": 9},
                {"key": "sprint_node", "label": "sprint#node", "width": 22},
                {"key": "age", "label": "age", "width": 8},
            ],
            "rows": task_rows,
            "border": "minimal",
        },
        {
            "type": "table",
            "columns": [
                {"key": "time", "label": "time", "width": 16},
                {"key": "pane", "label": "pane", "width": 20},
                {"key": "role", "label": "role", "width": 10},
                {"key": "sprint_node", "label": "sprint#node", "width": 30},
            ],
            "rows": dispatch_rows,
            "border": "minimal",
        },
        {
            "type": "table",
            "columns": [
                {"key": "sprint", "label": "sprint", "width": 28},
                {"key": "desc", "label": "说明", "width": 26},
                {"key": "status", "label": "状态", "width": 8},
                {"key": "node_counts", "label": "counts", "width": 20},
                {"key": "ready", "label": "ready", "width": 12},
            ],
            "rows": graph_rows,
            "border": "minimal",
        },
    ]

    launched = result.get("launched") or []
    if launched:
        sections.append({
            "type": "table",
            "columns": [
                {"key": "task", "label": "launched", "width": 28},
                {"key": "status", "label": "status", "width": 10},
                {"key": "sprint", "label": "sprint", "width": 20},
                {"key": "node", "label": "node", "width": 20},
            ],
            "rows": [{
                "task": str(x.get("id", "N/A"))[:28],
                "status": str(x.get("status", "N/A")),
                "sprint": str(x.get("sprint_id", "N/A"))[:20],
                "node": str(x.get("node_id", "N/A"))[:20],
            } for x in launched],
            "border": "minimal",
        })

    return {
        "canvas": {"width": width},
        "style": "solar_default",
        "root": {
            "type": "card",
            "header": "Solar Harness Multi-Task",
            "sections": sections,
        },
    }


def render_tvs(result: dict[str, Any], no_clear: bool = False, width: int = 100) -> None:
    if not no_clear and sys.stdout.isatty():
        print("\033[H\033[2J", end="")
    harness = HARNESS_DIR / "solar-harness.sh"
    proc = subprocess.run(
        [str(harness), "tvs", "render", "--width", str(width), "--colors", "off"],
        input=json.dumps(tvs_payload(result, width), ensure_ascii=False),
        text=True,
        capture_output=True,
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "TVS render failed").strip())
    print(proc.stdout.rstrip())


def render_result(result: dict[str, Any], args: argparse.Namespace) -> None:
    renderer = getattr(args, "renderer", "") or os.environ.get("SOLAR_MULTI_TASK_RENDERER", "tvs")
    width = int(os.environ.get("SOLAR_MULTI_TASK_TVS_WIDTH", "100") or "100")
    if renderer == "plain":
        render_plain(result, no_clear=getattr(args, "no_clear", False))
        return
    try:
        render_tvs(result, no_clear=getattr(args, "no_clear", False), width=width)
    except Exception as exc:
        print(f"[multi-task] TVS render failed, fallback=plain: {exc}", file=sys.stderr)
        render_plain(result, no_clear=getattr(args, "no_clear", False))


def command_log_path() -> Path:
    return RUN_DIR / "screen-commands.jsonl"


def load_screen_history() -> None:
    if readline is None:
        return
    try:
        SCREEN_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        if SCREEN_HISTORY_PATH.exists():
            readline.read_history_file(str(SCREEN_HISTORY_PATH))
        readline.set_history_length(1000)
    except Exception:
        return


def save_screen_history() -> None:
    if readline is None:
        return
    try:
        SCREEN_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        readline.set_history_length(1000)
        readline.write_history_file(str(SCREEN_HISTORY_PATH))
    except Exception:
        return


def remember_screen_input(text: str) -> None:
    raw = text.strip()
    if not raw:
        return
    if readline is not None:
        try:
            last = readline.get_history_item(readline.get_current_history_length()) or ""
            if last != raw:
                readline.add_history(raw)
            save_screen_history()
            return
        except Exception:
            pass
    try:
        SCREEN_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        old = SCREEN_HISTORY_PATH.read_text(encoding="utf-8").splitlines() if SCREEN_HISTORY_PATH.exists() else []
        if not old or old[-1] != raw:
            old.append(raw)
        SCREEN_HISTORY_PATH.write_text("\n".join(old[-1000:]) + "\n", encoding="utf-8")
    except Exception:
        return


def append_screen_command(text: str, intent: dict[str, Any], action: str, status: str, detail: str = "") -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": now_iso(),
        "input": text,
        "intent": intent,
        "action": action,
        "status": status,
        "detail": detail,
    }
    with command_log_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def match_intent(text: str) -> dict[str, Any]:
    try:
        from intent_engine_adapter import match as intent_match  # noqa: WPS433

        return intent_match(text, record=True)
    except Exception as exc:
        return {
            "ok": False,
            "input": text,
            "matched": False,
            "matches": [],
            "error": f"{type(exc).__name__}: {exc}",
            "generated_at": now_iso(),
        }


def local_intent(text: str, intent_type: str) -> dict[str, Any]:
    return {
        "ok": True,
        "input": text,
        "matched": True,
        "matches": [{
            "kind": "intent",
            "type": intent_type,
            "source": "solar-harness-screen",
            "confidence": 1.0,
        }],
        "generated_at": now_iso(),
    }


def _intent_label(intent: dict[str, Any]) -> str:
    labels: list[str] = []
    for item in intent.get("matches") or []:
        label = item.get("skill") or item.get("target") or item.get("type") or item.get("source")
        if label:
            labels.append(str(label))
    return ",".join(labels[:3]) if labels else "N/A"


def _profile_candidate_from_text(text: str) -> dict[str, str] | None:
    lower = text.lower().strip()
    explicit = re.search(r"(?:profile|模型|角色)\s*[:=]\s*([A-Za-z0-9_.-]+)", text, re.I)
    if explicit:
        return {"profile": explicit.group(1), "backend": "", "model": ""}
    for name in sorted(profile_names(), key=len, reverse=True):
        if lower == name.lower() or re.search(rf"\b{re.escape(name.lower())}\b", lower):
            return {"profile": name, "backend": "", "model": ""}
    candidates: list[tuple[tuple[str, ...], dict[str, str]]] = [
        (("gemini",), {"profile": "gemini-builder", "backend": "gemini-cli", "model": "gemini"}),
        (("deepseek",), {"profile": "deepseek-builder", "backend": "", "model": "deepseek"}),
        (("glm", "gml", "智谱"), {"profile": "glm-planner", "backend": "", "model": "glm-5.1"}),
        (("opus",), {"profile": "evaluator", "backend": "claude-cli", "model": "opus"}),
        (("sonnet",), {"profile": "builder", "backend": "claude-cli", "model": "sonnet"}),
        (("thunderomlx", "thunder", "omlx"), {"profile": "thunderomlx-local", "backend": "command", "model": "thunderomlx"}),
        (("planner", "规划者", "规划"), {"profile": "planner", "backend": "claude-cli", "model": "sonnet"}),
        (("builder", "构建者", "建设者", "构建"), {"profile": "builder", "backend": "claude-cli", "model": "sonnet"}),
        (("evaluator", "审判者", "评审"), {"profile": "evaluator", "backend": "claude-cli", "model": "opus"}),
        (("pm", "产品经理"), {"profile": "pm", "backend": "claude-cli", "model": "sonnet"}),
    ]
    for markers, candidate in candidates:
        if any(marker in lower or marker in text for marker in markers):
            return dict(candidate)
    return None


def _looks_like_profile_switch(text: str) -> bool:
    lower = text.lower().strip()
    if re.search(r"(?:profile|模型|角色)\s*[:=]", text, re.I):
        return True
    prefixes = ("switch", "use ", "profile ", "model ", "切换", "使用", "用", "换到", "改成", "选")
    if lower.startswith(prefixes):
        return _profile_candidate_from_text(text) is not None
    candidate = _profile_candidate_from_text(text)
    if not candidate:
        return False
    normalized = re.sub(r"\s+", "", lower)
    names = {name.lower() for name in profile_names()}
    aliases = {
        "gemini", "deepseek", "glm", "gml", "智谱", "opus", "sonnet",
        "thunderomlx", "thunder", "omlx", "planner", "规划", "builder",
        "构建", "evaluator", "审判", "pm", "产品经理",
    }
    return normalized in names or normalized in aliases


def _set_screen_model_preference(text: str, args: argparse.Namespace) -> str:
    candidate = _profile_candidate_from_text(text)
    if not candidate:
        return ""
    try:
        profile = resolve_profile(candidate["profile"])
    except Exception as exc:
        return f"profile_rejected={candidate.get('profile') or 'N/A'} status=error reason={type(exc).__name__}"
    if candidate.get("backend"):
        profile["backend"] = candidate["backend"]
    if candidate.get("model"):
        profile["model"] = candidate["model"]
    capability = capability_for_profile(profile)
    if capability.get("status") != "ok":
        evidence = _clip_display(str(capability.get("evidence") or "N/A"), 120)
        return (
            f"profile_rejected={profile.get('name')} status={capability.get('status')} "
            f"provider={capability.get('provider')} reason={evidence}"
        )
    args.profile = str(profile.get("name") or "")
    args.backend = str(profile.get("backend") or "")
    args.model = str(profile.get("model") or "")
    return (
        f"profile={args.profile} backend={args.backend} model={args.model} "
        f"provider={capability.get('provider')} capability=ok"
    )


def _screen_selection_line(args: argparse.Namespace) -> str:
    profile_name = str(getattr(args, "profile", "") or "")
    backend = str(getattr(args, "backend", "") or "")
    model = str(getattr(args, "model", "") or "")
    if not profile_name and not backend and not model:
        return "profile=auto backend=auto model=auto capability=auto"
    try:
        profile = resolve_profile(profile_name) if profile_name else select_profile({}, "", model, backend)
        if backend:
            profile["backend"] = backend
        if model:
            profile["model"] = model
        capability = capability_for_profile(profile)
        return (
            f"profile={profile.get('name', profile_name or 'auto')} "
            f"backend={profile.get('backend', backend or 'auto')} "
            f"model={profile.get('model', model or 'auto')} "
            f"provider={capability.get('provider', 'N/A')} capability={capability.get('status', 'N/A')}"
        )
    except Exception as exc:
        return (
            f"profile={profile_name or 'auto'} backend={backend or 'auto'} model={model or 'auto'} "
            f"capability=error reason={type(exc).__name__}"
        )


def _selector_from_text(text: str) -> str:
    lower = text.lower()
    for selector in ("planner", "builder", "evaluator", "pm", "gemini-builder", "latest"):
        if selector in lower:
            return selector
    for cn, selector in (("规划", "planner"), ("构建", "builder"), ("建设", "builder"), ("审判", "evaluator"), ("评审", "evaluator")):
        if cn in text:
            return selector
    return "latest"


def _looks_like_task_status_query(text: str) -> bool:
    lower = text.lower()
    query_markers = ("哪些", "哪个", "什么", "多少", "有没有", "是否", "吗", "?", "？", "list", "show", "what", "which", "running")
    task_markers = ("任务", "worker", "pane", "后台", "dag", "task")
    status_markers = ("执行", "运行", "正在", "状态", "进展", "active", "running", "status")
    has_query = any(marker in text or marker in lower for marker in query_markers)
    has_task = any(marker in text or marker in lower for marker in task_markers)
    has_status = any(marker in text or marker in lower for marker in status_markers)
    return has_task and (has_query or has_status)


def _task_status_message() -> str:
    tasks = list_task_rows()
    active = [t for t in tasks if str(t.get("status", "")).lower() in ACTIVE_TASK_STATUSES]
    inventory = task_inventory(tasks)
    graph_summaries = cached_status_summaries_for_graphs(graph_files([])[:12])
    dag_counts: dict[str, int] = {}
    ready_sprints: list[str] = []
    for summary in graph_summaries:
        for status, count in (summary.get("counts") or {}).items():
            dag_counts[str(status)] = dag_counts.get(str(status), 0) + int(count)
        ready = summary.get("ready") or []
        if ready:
            desc = str(summary.get("description") or "N/A")[:28]
            ready_sprints.append(f"{summary.get('sid', 'N/A')}({desc}):{','.join(ready[:5])}")
    dag_working = sum(dag_counts.get(status, 0) for status in ("assigned", "dispatched", "in_progress", "running"))
    dag_review = sum(dag_counts.get(status, 0) for status in ("active", "reviewing"))
    dag_ready = sum(len(summary.get("ready") or []) for summary in graph_summaries)
    bg_summary = f"BG live={inventory['live']} act={len(active)} track={len(tasks)} stale={inventory['stale']} age={inventory['latest_age']}"
    dag_summary = f"DAG working={dag_working} review={dag_review} ready={dag_ready}"
    if not tasks and not dag_working and not dag_review and not dag_ready:
        return f"当前任务: {dag_summary}; {bg_summary}"
    if not active:
        latest = f" latest={tasks[0].get('id', 'N/A')} status={tasks[0].get('status', 'N/A')}" if tasks else ""
        ready_text = f" ready_sprints={' | '.join(ready_sprints[:2])}" if ready_sprints else ""
        return f"当前任务: {dag_summary}; {bg_summary}{ready_text}{latest}"
    parts = []
    for task in active[:5]:
        parts.append(
            f"{task.get('id', 'N/A')}[{task.get('role', 'N/A')}/{task.get('model', 'N/A')}/{task.get('status', 'N/A')}]"
        )
    ready_text = f" ready_sprints={' | '.join(ready_sprints[:2])}" if ready_sprints else ""
    return f"当前任务: {dag_summary}; {bg_summary}{ready_text}; workers=" + "; ".join(parts)


def handle_screen_input(text: str, args: argparse.Namespace) -> tuple[str, str]:
    raw = text.strip()
    if not raw:
        return "noop", "空输入"
    lower = raw.lower()

    if lower in {"q", "quit", "exit", "退出", "关闭"}:
        intent = local_intent(raw, "exit")
        matched = _intent_label(intent)
        append_screen_command(raw, intent, "exit", "ok", matched)
        return "exit", f"intent={matched} action=exit"
    if lower in {"help", "?", "/help", "帮助"}:
        intent = local_intent(raw, "help")
        matched = _intent_label(intent)
        msg = "命令: status/profiles/doctor/start/foreground latest/logs latest/cancel latest；自然语言会先 intent match，再 intake。"
        append_screen_command(raw, intent, "help", "ok", matched)
        return "message", msg
    if lower in {"status", "状态", "显示状态", "看状态"} or _looks_like_task_status_query(raw):
        label = "task_status_query" if _looks_like_task_status_query(raw) else "status"
        intent = local_intent(raw, label)
        matched = _intent_label(intent)
        label = "task_status_query" if _looks_like_task_status_query(raw) else matched
        append_screen_command(raw, intent, "status", "ok", label)
        return "message", f"intent={label} action=status {_task_status_message()}"
    if lower in {"profiles", "profile", "角色", "模型", "选项"}:
        intent = local_intent(raw, "profiles")
        matched = _intent_label(intent)
        append_screen_command(raw, intent, "profiles", "ok", matched)
        return "profiles", "显示 profiles"
    if lower in {"doctor", "检查", "自检"}:
        intent = local_intent(raw, "doctor")
        matched = _intent_label(intent)
        append_screen_command(raw, intent, "doctor", "ok", matched)
        return "doctor", "显示 doctor"
    if _looks_like_profile_switch(raw):
        intent = local_intent(raw, "profile_switch")
        matched = _intent_label(intent)
        pref = _set_screen_model_preference(raw, args)
        status = "error" if pref.startswith("profile_rejected=") else "ok"
        append_screen_command(raw, intent, "profile", status, pref)
        return "message", f"intent={matched} action=profile {pref}".strip()
    if lower.startswith(("foreground", "focus", "fg", "前台", "看输出", "查看输出")):
        intent = local_intent(raw, "foreground")
        selector = raw.split(maxsplit=1)[1] if " " in raw and not raw.startswith(("前台", "看输出", "查看输出")) else _selector_from_text(raw)
        append_screen_command(raw, intent, "foreground", "ok", selector)
        return "foreground", selector
    if lower.startswith(("logs", "log", "日志")):
        intent = local_intent(raw, "logs")
        selector = raw.split(maxsplit=1)[1] if " " in raw else _selector_from_text(raw)
        append_screen_command(raw, intent, "logs", "ok", selector)
        return "logs", selector
    if lower.startswith(("cancel", "取消")):
        intent = local_intent(raw, "cancel")
        selector = raw.split(maxsplit=1)[1] if " " in raw else _selector_from_text(raw)
        append_screen_command(raw, intent, "cancel", "ok", selector)
        return "cancel", selector
    intent = match_intent(raw)
    matched = _intent_label(intent)
    if lower.startswith(("start", "启动调度", "开始调度")) or any((m.get("type") == "execute") for m in intent.get("matches") or []):
        requested_profile = _profile_candidate_from_text(raw) is not None
        pref = _set_screen_model_preference(raw, args)
        if requested_profile and pref.startswith("profile_rejected="):
            append_screen_command(raw, intent, "schedule_once", "error", pref)
            return "message", f"intent={matched} action=schedule_once launched=0 {pref}".strip()
        result = schedule_once(args)
        append_screen_command(raw, intent, "schedule_once", "ok", pref)
        return "message", f"intent={matched} action=schedule_once launched={len(result.get('launched') or [])} {pref}".strip()

    pref = _set_screen_model_preference(raw, args)
    harness = HARNESS_DIR / "solar-harness.sh"
    proc = subprocess.run(
        [str(harness), "intake", "--request", raw],
        text=True,
        capture_output=True,
        timeout=120,
    )
    detail = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = detail[-1] if detail else f"exit={proc.returncode}"
    append_screen_command(raw, intent, "intake", "ok" if proc.returncode == 0 else "error", f"{pref} {summary}".strip())
    return "message", f"intent={matched} action=intake rc={proc.returncode} {pref}".strip()


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)


def _display_width(text: str) -> int:
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
    return width


def _clip_display(text: str, max_width: int) -> str:
    if max_width <= 0:
        return ""
    out: list[str] = []
    width = 0
    for ch in text:
        ch_width = 0 if unicodedata.combining(ch) else (2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1)
        if width + ch_width > max_width:
            break
        out.append(ch)
        width += ch_width
    return "".join(out)


def _pad_display(text: str, width: int, fill: str = " ") -> str:
    clipped = _clip_display(text, width)
    pad = max(0, width - _display_width(clipped))
    return clipped + fill * pad


def _box_lines(title: str, lines: list[str], width: int, height: int) -> list[str]:
    total_width = max(40, width)
    hline_width = max(10, total_width - 2)
    content_width = max(8, total_width - 4)
    title_text = f" {title} "
    top = "┌" + _pad_display(title_text, hline_width, "─") + "┐"
    bottom = "└" + "─" * hline_width + "┘"
    body_height = max(0, height - 2)
    out = [top]
    for line in lines[:body_height]:
        clean = _strip_ansi(line)
        out.append("│ " + _pad_display(clean, content_width) + " │")
    while len(out) < height - 1:
        out.append("│ " + " " * content_width + " │")
    out.append(bottom)
    return out[:height]


def draw_screen(result: dict[str, Any], messages: list[str], args: argparse.Namespace) -> None:
    size = shutil.get_terminal_size((120, 40))
    rows = max(12, size.lines)
    cols = max(60, size.columns)
    available = max(10, rows - 1)
    top_h = max(6, int(available * 0.70))
    bottom_h = max(7, available - top_h)
    if top_h + bottom_h > available:
        top_h = max(6, available - bottom_h)
    if top_h + bottom_h > available:
        bottom_h = max(3, available - top_h)
    if not args.no_clear and sys.stdout.isatty():
        print("\033[H\033[2J", end="")
    content_cols = max(40, cols - 4)
    view_model = screen_view_model(result, args, content_cols)
    if _tvs_available(args):
        payload = screen_tvs_payload(view_model, args, content_cols)
        _tvs_render(payload, top_h)
    else:
        status_lines = render_screen_status_lines(view_model, content_cols, max(1, top_h - 2))
        print("\n".join(_box_lines("后台 pane 状态 / DAG worker 池", status_lines, cols, top_h)))
    fixed_input_lines = [
        _screen_selection_line(args),
        "输入: 自然语言需求 / status / profiles / doctor / foreground latest / logs latest / q",
        f"history: ↑/↓ {SCREEN_HISTORY_PATH.name}; intent_log=screen-commands.jsonl",
    ]
    input_body_height = max(0, bottom_h - 2)
    message_slots = max(1, input_body_height - len(fixed_input_lines))
    input_lines = fixed_input_lines + messages[-message_slots:]
    print("\n".join(_box_lines("自然语言指令 / Intent Engine 输入区", input_lines, cols, bottom_h)))
    print("solar> ", end="", flush=True)


def screen_loop(args: argparse.Namespace) -> int:
    messages: list[str] = ["screen started"]
    load_screen_history()
    if args.command or not sys.stdin.isatty():
        commands = [args.command] if args.command else [line.strip() for line in sys.stdin if line.strip()]
        if not commands:
            draw_screen(status_snapshot(args), messages, args)
            return 0
        for raw in commands:
            remember_screen_input(raw)
            action, detail = handle_screen_input(raw, args)
            messages.append(f"{now_iso()} {raw} -> {detail}")
            if action == "foreground":
                print()
                return attach_or_log(detail, attach=True)
            if action == "logs":
                print()
                return attach_or_log(detail, attach=False)
            if action == "cancel":
                rc = cancel(detail)
                messages.append(f"cancel rc={rc}")
            if action == "profiles":
                config = load_profiles()
                for name, spec in sorted((config.get("profiles") or {}).items()):
                    messages.append(f"{name}: role={spec.get('role')} backend={spec.get('backend')} model={spec.get('model')}")
            if action == "doctor":
                adapter = HARNESS_DIR / "lib" / "gemini_adapter.py"
                gemini = subprocess.run([sys.executable, str(adapter), "doctor"], text=True, capture_output=True)
                messages.append("doctor gemini: " + " ".join((gemini.stdout or gemini.stderr).split())[:160])
            if action == "exit":
                break
        draw_screen(status_snapshot(args), messages, args)
        return 0
    while True:
        result = status_snapshot(args)
        draw_screen(result, messages, args)
        if args.once and not args.command:
            return 0
        try:
            raw = input()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        commands = [raw]
        for raw in commands:
            remember_screen_input(raw)
            action, detail = handle_screen_input(raw, args)
            messages.append(f"{now_iso()} {raw} -> {detail}")
            if action == "exit":
                draw_screen(status_snapshot(args), messages, args)
                return 0
            if action == "foreground":
                print()
                return attach_or_log(detail, attach=True)
            if action == "logs":
                print()
                return attach_or_log(detail, attach=False)
            if action == "cancel":
                rc = cancel(detail)
                messages.append(f"cancel rc={rc}")
            if action == "profiles":
                config = load_profiles()
                for name, spec in sorted((config.get("profiles") or {}).items()):
                    messages.append(f"{name}: role={spec.get('role')} backend={spec.get('backend')} model={spec.get('model')}")
            if action == "doctor":
                adapter = HARNESS_DIR / "lib" / "gemini_adapter.py"
                gemini = subprocess.run([sys.executable, str(adapter), "doctor"], text=True, capture_output=True)
                messages.append("doctor gemini: " + " ".join((gemini.stdout or gemini.stderr).split())[:160])
        if args.command or not sys.stdin.isatty():
            draw_screen(status_snapshot(args), messages, args)
            return 0


def resolve_task(selector: str) -> dict[str, Any] | None:
    rows = list_task_rows()
    if not rows:
        return None
    value = str(selector or "latest").strip()
    if value in {"latest", "last", ""}:
        return rows[0]
    for row in rows:
        task = str(row.get("id") or "")
        if task == value or task.startswith(value):
            return row
    for row in rows:
        if value.lower() in {
            str(row.get("role") or "").lower(),
            str(row.get("profile") or "").lower(),
            str(row.get("node_id") or "").lower(),
        }:
            return row
    return None


def attach_or_log(task_id_value: str, attach: bool) -> int:
    status = resolve_task(task_id_value)
    if not status:
        print(f"status not found: {task_id_value}", file=sys.stderr)
        return 1
    task_id_value = str(status.get("id") or task_id_value)
    if attach:
        window = str(status.get("window") or "")
        if sys.stdout.isatty():
            return subprocess.call(["tmux", "attach", "-t", f"{SESSION}:{window}"])
        print(f"tmux attach -t {SESSION}:{window}")
        return 0
    log = RUN_DIR / task_id_value / "output.log"
    if not log.exists():
        print(f"log not found: {log}", file=sys.stderr)
        return 1
    print(log.read_text(encoding="utf-8", errors="replace")[-20000:])
    return 0


def cancel(task_id_value: str) -> int:
    status = resolve_task(task_id_value)
    if not status:
        print(f"status not found: {task_id_value}", file=sys.stderr)
        return 1
    task_id_value = str(status.get("id") or task_id_value)
    window = str(status.get("window") or "")
    subprocess.run(["tmux", "kill-window", "-t", f"{SESSION}:{window}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    status["status"] = "cancelled"
    status["updated_at"] = now_iso()
    json_write(RUN_DIR / task_id_value / "status.json", status)
    try:
        graph_path = Path(str(status.get("graph")))
        graph = load_graph(graph_path)
        set_node_status(graph, str(status.get("node_id")), "failed", pane=f"multi-task:{window}", dispatch_id=task_id_value)
        save_graph(graph_path, graph)
    except Exception:
        pass
    print(f"cancelled: {task_id_value}")
    return 0


def reap_tasks(ttl_min: int, stale_active_min: int, dry_run: bool) -> dict[str, Any]:
    now = time.time()
    ttl = max(0, ttl_min) * 60
    stale_ttl = max(0, stale_active_min) * 60
    reaped: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for status in list_task_rows():
        task = str(status.get("id") or "")
        current = str(status.get("effective_status") or status.get("status") or "").lower()
        updated_ts = parse_iso(str(status.get("updated_at") or status.get("created_at") or ""))
        age = None if updated_ts is None else now - updated_ts
        terminal_old = current in EFFECTIVE_TERMINAL_TASK_STATUSES and age is not None and age >= ttl
        stale_active = stale_ttl > 0 and current in ACTIVE_TASK_STATUSES and age is not None and age >= stale_ttl
        if not terminal_old and not stale_active:
            kept.append({"id": task, "status": current or "N/A", "age_s": None if age is None else int(age)})
            continue
        window = str(status.get("window") or "")
        action = "dry-run"
        if not dry_run and window:
            subprocess.run(["tmux", "kill-window", "-t", f"{SESSION}:{window}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            action = "killed-window"
        elif not dry_run:
            action = "no-window"
        if not dry_run:
            status["status"] = "reaped_stale_active" if stale_active else "reaped"
            status["reaped_at"] = now_iso()
            status["updated_at"] = status["reaped_at"]
            json_write(RUN_DIR / task / "status.json", status)
        reaped.append({
            "id": task,
            "old_status": current or "N/A",
            "age_s": None if age is None else int(age),
            "window": window or "N/A",
            "action": action,
        })
    return {"reaped": reaped, "kept": kept, "dry_run": dry_run, "ttl_min": ttl_min, "stale_active_min": stale_active_min}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="solar-harness multi-task")
    sub = p.add_subparsers(dest="cmd")
    screen = sub.add_parser("screen", help="interactive split terminal screen with status and natural-language input")
    screen.add_argument("--graph", action="append", default=[], help="task_graph.json path; can repeat")
    screen.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    screen.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    screen.add_argument("--cooldown-sec", type=int, default=DEFAULT_COOLDOWN)
    screen.add_argument("--memory-reserve-gb", type=float, default=DEFAULT_MEMORY_RESERVE_GB)
    screen.add_argument("--quota-backoff-sec", type=int, default=DEFAULT_QUOTA_BACKOFF)
    screen.add_argument("--profile", default="", help=f"worker profile: {','.join(profile_names())}")
    screen.add_argument("--model", default="", help="override selected profile model")
    screen.add_argument("--backend", default="", choices=["", "claude-cli", "gemini-cli", "gemini-sdk", "command"], help="override selected profile backend")
    screen.add_argument("--command", default="", help="process one input command, useful for tests/scripts")
    screen.add_argument("--dry-run", action="store_true")
    screen.add_argument("--once", action="store_true", help="render once and exit")
    screen.add_argument("--no-clear", action="store_true")
    start = sub.add_parser("start", help="start tmux-backed DAG worker scheduler")
    start.add_argument("--graph", action="append", default=[], help="task_graph.json path; can repeat")
    start.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    start.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    start.add_argument("--cooldown-sec", type=int, default=DEFAULT_COOLDOWN)
    start.add_argument("--memory-reserve-gb", type=float, default=DEFAULT_MEMORY_RESERVE_GB)
    start.add_argument("--quota-backoff-sec", type=int, default=DEFAULT_QUOTA_BACKOFF)
    start.add_argument("--profile", default="", help=f"worker profile: {','.join(profile_names())}")
    start.add_argument("--model", default="", help="override selected profile model")
    start.add_argument("--backend", default="", choices=["", "claude-cli", "gemini-cli", "gemini-sdk", "command"], help="override selected profile backend")
    start.add_argument("--once", action="store_true")
    start.add_argument("--dry-run", action="store_true")
    start.add_argument("--no-clear", action="store_true")
    start.add_argument("--renderer", choices=["tvs", "plain"], default=os.environ.get("SOLAR_MULTI_TASK_RENDERER", "tvs"))

    status = sub.add_parser("status", help="show current scheduler summary")
    status.add_argument("--graph", action="append", default=[])
    status.add_argument("--no-clear", action="store_true")
    status.add_argument("--renderer", choices=["tvs", "plain"], default=os.environ.get("SOLAR_MULTI_TASK_RENDERER", "tvs"))

    logs = sub.add_parser("logs", help="show task log")
    logs.add_argument("task_id", help="task id/prefix, latest, role, profile, or node id")
    attach = sub.add_parser("attach", help="attach tmux task window")
    attach.add_argument("task_id", help="task id/prefix, latest, role, profile, or node id")
    for alias in ("foreground", "focus", "fg"):
        fg = sub.add_parser(alias, help="bring a background tmux task to foreground")
        fg.add_argument("task_id", nargs="?", default="latest", help="task id/prefix, latest, role, profile, or node id")
    cancel_p = sub.add_parser("cancel", help="cancel task and mark graph node failed")
    cancel_p.add_argument("task_id")
    reap_p = sub.add_parser("reap", help="kill/archive old terminal or stale tmux task windows")
    reap_p.add_argument("--ttl-min", type=int, default=int(os.environ.get("SOLAR_MULTI_TASK_REAP_TTL_MIN", "120") or "120"))
    reap_p.add_argument("--stale-active-min", type=int, default=int(os.environ.get("SOLAR_MULTI_TASK_STALE_ACTIVE_MIN", "0") or "0"))
    reap_p.add_argument("--dry-run", action="store_true")
    probe_p = sub.add_parser("probe", help="run a minimal real model call for one worker profile")
    probe_p.add_argument("profile", help=f"worker profile: {','.join(profile_names())}")
    probe_p.add_argument("--timeout-sec", type=int, default=90)
    sub.add_parser("matrix", help="show role/model/backend capability matrix")
    sub.add_parser("profiles", help="list worker profiles and model/task affinity")
    sub.add_parser("doctor", help="check multi-task external backends")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["screen"]
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "logs":
        return attach_or_log(args.task_id, attach=False)
    if args.cmd == "attach":
        return attach_or_log(args.task_id, attach=True)
    if args.cmd in {"foreground", "focus", "fg"}:
        return attach_or_log(args.task_id, attach=True)
    if args.cmd == "cancel":
        return cancel(args.task_id)
    if args.cmd == "reap":
        result = reap_tasks(args.ttl_min, args.stale_active_min, args.dry_run)
        rows = [[
            str(row.get("id", "N/A"))[:40],
            str(row.get("old_status", "N/A")),
            str(row.get("age_s", "N/A")),
            str(row.get("window", "N/A"))[:28],
            str(row.get("action", "N/A")),
        ] for row in result.get("reaped", [])]
        if not rows:
            rows = [["N/A", "N/A", "N/A", "N/A", "none"]]
        print_table(["task", "old_status", "age_s", "window", "action"], rows)
        return 0
    if args.cmd == "probe":
        try:
            result = run_capability_probe(args.profile, args.timeout_sec)
        except Exception as exc:
            print_table(["profile", "status", "evidence"], [[args.profile, "error", str(exc)[:120]]])
            return 1
        print_table(
            ["profile", "provider", "backend", "model", "status", "evidence"],
            [[
                str(result.get("profile", "N/A")),
                str(result.get("provider", "N/A")),
                str(result.get("backend", "N/A")),
                str(result.get("model", "N/A")),
                str(result.get("status", "N/A")),
                str(result.get("evidence", "N/A"))[:80],
            ]],
        )
        return 0 if result.get("status") == "ok" else 1
    if args.cmd == "matrix":
        rows = [[
            str(row.get("profile", "N/A")),
            str(row.get("role", "N/A")),
            str(row.get("provider", "N/A")),
            str(row.get("backend", "N/A")),
            str(row.get("model", "N/A")),
            str(row.get("status", "N/A")),
            str(row.get("evidence", "N/A"))[:88],
        ] for row in capability_rows()]
        print_table(["profile", "role", "provider", "backend", "model", "状态", "证据"], rows)
        return 0
    if args.cmd == "profiles":
        config = load_profiles()
        rows = []
        for name, spec in sorted((config.get("profiles") or {}).items()):
            rows.append([
                name,
                str(spec.get("role", "N/A")),
                str(spec.get("backend", "N/A")),
                str(spec.get("model", "N/A")),
                ",".join(spec.get("best_for") or [])[:44] or "N/A",
            ])
        print_table(["profile", "role", "backend", "model", "best_for"], rows)
        return 0
    if args.cmd == "doctor":
        adapter = HARNESS_DIR / "lib" / "gemini_adapter.py"
        gemini = subprocess.run([sys.executable, str(adapter), "doctor"], text=True, capture_output=True)
        gemini_evidence = " ".join((gemini.stdout or gemini.stderr).strip().split())
        gemini_status = "warn"
        try:
            gemini_payload = json.loads(gemini.stdout or "{}")
            cli_payload = gemini_payload.get("cli") or {}
            gemini_status = "ok" if gemini.returncode == 0 and cli_payload.get("ready", cli_payload.get("ok")) else "warn"
            gemini_evidence = (
                f"path={cli_payload.get('path') or 'missing'} "
                f"default_auth={cli_payload.get('default_auth') or 'N/A'} "
                f"ready={cli_payload.get('ready')} "
                f"oauth_creds={cli_payload.get('oauth_creds')} "
                f"warning={cli_payload.get('warning') or 'N/A'}"
            )
        except Exception:
            gemini_status = "ok" if gemini.returncode == 0 else "warn"
        print_table(
            ["backend", "状态", "证据"],
            [
                ["claude-cli", "ok" if shutil.which("claude") else "warn", shutil.which("claude") or "missing"],
                ["gemini", gemini_status, gemini_evidence[:96] or "N/A"],
                ["command", "ok" if os.environ.get("SOLAR_MULTI_TASK_AGENT_CMD") else "warn", "SOLAR_MULTI_TASK_AGENT_CMD set" if os.environ.get("SOLAR_MULTI_TASK_AGENT_CMD") else "env missing"],
            ],
        )
        return 0
    if args.cmd == "status":
        render_result(status_snapshot(args), args)
        return 0
    if args.cmd == "screen":
        return screen_loop(args)

    if args.cmd in {None, "start"}:
        while True:
            result = schedule_once(args)
            render_result(result, args)
            if args.once:
                return 0
            time.sleep(max(1, int(args.interval)))

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
