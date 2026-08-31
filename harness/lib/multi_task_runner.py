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
import signal
import subprocess
import sys
import time
import unicodedata
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from codex_cli_runtime import resolve_codex_cli
from executable_node import (
    dispatch_role as executable_dispatch_role,
    logical_operator as executable_logical_operator,
    physical_role as executable_physical_role,
)

_READLINE: Any | None = None
_READLINE_CHECKED = False


def _configure_utf8_console() -> None:
    """Keep the Windows CLI from crashing when the active code page is CP1252."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _screen_readline() -> Any | None:
    """Load readline only for interactive screen history.

    Some packaged Python builds can segfault importing ``readline`` when the
    process inherits an unavailable locale such as ``en_US.UTF-8``. The worker
    scheduler does not need readline, so keep it off the module import path.
    """
    global _READLINE, _READLINE_CHECKED
    if _READLINE_CHECKED:
        return _READLINE
    _READLINE_CHECKED = True
    if not sys.stdin.isatty():
        return None
    try:
        import locale

        locale.setlocale(locale.LC_CTYPE, "")
    except Exception:
        return None
    try:
        import readline as readline_module  # type: ignore
    except Exception:  # pragma: no cover - readline may be unavailable in minimal Python builds
        return None
    _READLINE = readline_module
    return _READLINE

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
DEFAULT_MAX_WORKERS = int(os.environ.get("SOLAR_MULTI_TASK_MAX_WORKERS", "4") or "4")
DEFAULT_INTERVAL = int(os.environ.get("SOLAR_MULTI_TASK_INTERVAL_SEC", "15") or "15")
DEFAULT_COOLDOWN = int(os.environ.get("SOLAR_MULTI_TASK_LAUNCH_COOLDOWN_SEC", "30") or "30")
DEFAULT_MEMORY_RESERVE_GB = float(os.environ.get("SOLAR_MULTI_TASK_MEMORY_RESERVE_GB", "4") or "4")
DEFAULT_QUOTA_BACKOFF = int(os.environ.get("SOLAR_MULTI_TASK_QUOTA_BACKOFF_SEC", "900") or "900")
AUTO_CLOSE_TERMINAL_WINDOWS = str(
    os.environ.get("SOLAR_MULTI_TASK_AUTO_CLOSE_TERMINAL_WINDOWS", "1") or "1"
).lower() not in {"0", "false", "no", "off"}
AUTO_CLOSE_DELAY_SEC = max(
    0, int(os.environ.get("SOLAR_MULTI_TASK_AUTO_CLOSE_DELAY_SEC", "3") or "3")
)
REUSE_TERMINAL_WINDOWS = str(
    os.environ.get("SOLAR_MULTI_TASK_REUSE_TERMINAL_WINDOWS", "1") or "1"
).lower() not in {"0", "false", "no", "off"}
REUSABLE_WINDOW_COMMANDS = {"bash", "zsh", "sh", "fish"}
IDLE_WINDOW_POOL_TARGET = max(
    0, int(os.environ.get("SOLAR_MULTI_TASK_IDLE_WINDOW_POOL_TARGET", "1") or "1")
)
OPERATORD_SUBMIT_ENABLED = os.environ.get("SOLAR_OPERATORD_SUBMIT_ENABLED", "1").lower() not in {"0", "false", "off", "no"}
OPERATORD_RESULT_TIMEOUT_SEC = float(os.environ.get("SOLAR_OPERATORD_RESULT_TIMEOUT_SEC", "0") or "0")
OPERATORD_RESULT_POLL_INTERVAL_SEC = float(os.environ.get("SOLAR_OPERATORD_RESULT_POLL_INTERVAL_SEC", "1") or "1")
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
    "defaults": {"profile": "builder", "backend": "claude-cli", "max_workers": 4},
    "profiles": {
        "builder": {
            "role": "builder",
            "label": "构建者",
            "persona": "builder",
            "backend": "claude-cli",
            "model": "sonnet",
            "approval_mode": "yolo",
            "best_for": ["implementation", "debugging", "tests"],
            "max_parallel": 4,
        },
        "planner": {
            "role": "planner",
            "label": "规划者",
            "persona": "planner",
            "backend": "claude-cli",
            "model": "sonnet",
            "approval_mode": "auto_edit",
            "best_for": ["planning", "architecture"],
            "max_parallel": 2,
        },
        "evaluator": {
            "role": "evaluator",
            "label": "审判者",
            "persona": "evaluator",
            "backend": "claude-cli",
            "model": "opus",
            "approval_mode": "auto_edit",
            "best_for": ["verification", "review"],
            "max_parallel": 2,
        },
        "pm": {
            "role": "pm",
            "label": "PM",
            "persona": "pm",
            "backend": "claude-cli",
            "model": "sonnet",
            "approval_mode": "auto_edit",
            "best_for": ["requirements", "acceptance"],
            "max_parallel": 2,
        },
        "gemini-builder": {
            "role": "builder",
            "label": "Gemini 构建者",
            "persona": "builder",
            "backend": "gemini-cli",
            "model": "gemini",
            "approval_mode": "auto_edit",
            "best_for": ["large-context", "implementation"],
            "max_parallel": 2,
        },
        "gemini-evaluator": {
            "role": "evaluator",
            "label": "Gemini 评审者",
            "persona": "evaluator",
            "backend": "gemini-cli",
            "model": "gemini",
            "approval_mode": "auto_edit",
            "best_for": ["verification", "review", "evidence"],
            "max_parallel": 2,
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
            "max_parallel": 2,
        },
    },
}

sys.path.insert(0, str(HARNESS_DIR / "lib"))
from graph_scheduler import (  # noqa: E402
    enter_node_human_review,
    load_graph,
    node_status,
    ready_nodes,
    save_graph,
    set_node_status,
    write_scope_conflict,
)
from task_lifecycle import (  # noqa: E402
    ACTIVE_TASK_STATUSES,
    EFFECTIVE_TERMINAL_TASK_STATUSES,
    TERMINAL_TASK_STATUSES,
    activate_execution_attempt,
    correlated_terminal_result,
)

try:  # Lane 3 gate ledger seam (round-4 G3): pool-side node-status writes must
    # record like every other C4 writer; guarded so a partial install never
    # breaks the pool. No-op unless SOLAR_GATE_LEDGER=1.
    from graph_scheduler import _ledger_transition as _gs_ledger_transition
except Exception:  # pragma: no cover
    _gs_ledger_transition = None

TASK_STALE_WARN_SEC = int(os.environ.get("SOLAR_MULTI_TASK_STALE_WARN_SEC", "1800") or "1800")
SCHEDULER_PID_DIR = RUN_DIR / "schedulers"
_SCHED_GRAPH_TERMINAL = frozenset({"passed", "failed", "skipped", "done", "completed", "cancelled", "canceled"})


def _display_tmux_status(task_status: str, tmux_status: str) -> str:
    """Translate terminal task rows away from misleading live-window wording."""
    status = str(task_status or "").lower()
    tmux = str(tmux_status or "").lower()
    if status in EFFECTIVE_TERMINAL_TASK_STATUSES and tmux == "live":
        return "idle"
    return tmux or "N/A"
_SCHED_GRAPH_ACTIVE = frozenset({"assigned", "dispatched", "in_progress", "running", "reviewing"})
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

            builder_limit = int(concurrency_policy.effective_max_parallel(4, scope="builder"))
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
    try:
        import operator_flow_control as ofc

        ofc.prune_expired_operator_config_blocks()
    except Exception:
        pass
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
    if "codex" in value or value.startswith("gpt-") or value.startswith("gpt_") or value in {"gpt", "openai"}:
        return "openai"
    if re.match(r"^o[134](?:[-_.].*)?$", value):
        return "openai"
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
        command = str(profile.get("command") or "").strip()
        operator_id = str(profile.get("operator_id") or "").strip()
        if command and operator_id and operator_id != "N/A":
            # A leased physical operator owns its command environment.  Do not
            # reject that remote/daemon-backed command because the Scheduler
            # process itself cannot see an unrelated provider CLI on PATH.
            evidence = f"operator={operator_id} command=configured"
        elif provider == "openai":
            codex, codex_resolution = resolve_codex_cli(
                HARNESS_DIR,
                env=os.environ,
                configured_path=str(os.environ.get("SOLAR_CODEX_CLI") or ""),
            )
            driver = HARNESS_DIR / "tools" / "codex_operator.py"
            if codex and driver.exists():
                evidence = f"cli={codex} resolution={codex_resolution} driver={driver}"
            else:
                status = "error"
                missing = []
                if not codex:
                    missing.append("codex cli")
                if not driver.exists():
                    missing.append(str(driver))
                evidence = "missing " + ", ".join(missing)
        elif provider == "gemini":
            gemini = shutil.which("gemini")
            if gemini:
                evidence = f"cli={gemini}"
            else:
                status = "error"
                evidence = "gemini cli missing"
        elif command or os.environ.get("SOLAR_MULTI_TASK_AGENT_CMD") or env.get("solar_agent_cmd"):
            evidence = "command configured"
        else:
            status = "error"
            evidence = "command missing"
    elif backend == "research_operator_registry":
        binding = profile.get("runtime_binding")
        if not isinstance(binding, dict):
            status = "error"
            evidence = "runtime_binding missing"
        else:
            registry = str(binding.get("registry") or "").strip()
            node_id = str(binding.get("node_id") or "").strip()
            implementation_id = str(binding.get("implementation_operator_id") or "").strip()
            adapter = HARNESS_DIR / "tools" / "research_operator_registry_adapter.py"
            if registry and node_id and implementation_id and adapter.is_file():
                evidence = f"registry={registry} node={node_id} adapter={adapter}"
            else:
                status = "error"
                missing = [
                    name
                    for name, value in (
                        ("registry", registry),
                        ("node_id", node_id),
                        ("implementation_operator_id", implementation_id),
                        ("adapter", str(adapter) if adapter.is_file() else ""),
                    )
                    if not value
                ]
                evidence = "missing " + ", ".join(missing)
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
        expires = str(operator.get("quota_refresh_at") or (operator.get("state") or {}).get("cooldown_until") or "")
        try:
            import operator_flow_control as ofc

            parsed = ofc._parse_time(expires)  # type: ignore[attr-defined]
            if parsed is not None and parsed <= ofc._now():  # type: ignore[attr-defined]
                ofc.clear_expired_operator_config_block(str(operator.get("operator_id") or ""))
                return True, "ready"
        except Exception:
            pass
        return False, f"quota_guard_state={operator.get('quota_guard_state')}"
    key_ref = str(operator.get("key_ref") or "").strip()
    auth_mode = str(operator.get("auth_mode") or "").strip().lower()
    backend = str(operator.get("backend") or "").strip().lower()
    provider = str(operator.get("provider") or operator.get("vendor") or "").strip()
    command = str(operator.get("command") or "").strip()
    # Provider-less command and research-registry operators are local Harness
    # bridges. They may call provider-aware code behind that bridge, but the
    # physical operator itself does not own an API credential. External-provider
    # operators must continue to declare either a credential reference or a
    # credential-free auth mode explicitly.
    if not auth_mode and backend == "command" and command and not provider:
        auth_mode = "local"
    if not auth_mode and backend == "research_operator_registry" and not provider:
        auth_mode = "local"
    if auth_mode not in {"none", "local", "subscription"} and not key_ref:
        return False, "key_ref_missing"
    
    # Check dynamic status override from operator_runtime if available
    op_id = operator.get("operator_id")
    if op_id:
        try:
            import operator_runtime
            dyn_state = operator_runtime.get_operator_runtime_state(op_id)
            if dyn_state in {
                "disabled",
                "leased",
                "running",
                "draining",
                "cooldown",
                "quota_exhausted",
                "auth_expired",
            }:
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
    if operator.get("runtime_binding"):
        selected["runtime_binding"] = deepcopy(operator.get("runtime_binding"))
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

    profile_caps = operator.get("capability_profile")
    if isinstance(profile_caps, dict):
        for k, v in profile_caps.items():
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


# --- Role-compatible operator selection -----------------------------------------------------------
# A node's role-ish fields sometimes hold a backend/model token (e.g. owner="codex") instead of a real
# role. role_from_node() returns that token verbatim, and operator_score() then rewards a planner operator
# whose id contains "codex" -> a planner-role operator wins a builder node (Run G: S1/S2 ran on
# mini-codex-gpt55-medium-planner-2). This is SELECTION-only role resolution: it skips backend/model/
# provider tokens so the real role surfaces, then a hard-role mismatch is heavily penalized. role_from_node
# (and therefore profile selection) is intentionally left unchanged for now.
_HARD_ROLES = frozenset({"builder", "planner", "evaluator", "pm"})
_SELECTION_ROLE_ALIASES = {
    "builder-main": "builder", "build": "builder", "implementation": "builder", "implementer": "builder",
    "implementationworker": "builder",
    "judge": "evaluator", "reviewer": "evaluator", "verifier": "evaluator", "critic": "evaluator",
    "artifact-curator": "evaluator", "testrunner": "evaluator",
    "product": "pm", "product-manager": "pm",
    "planning": "planner", "architect": "planner", "deeparchitect": "planner",
}
_SELECTION_NON_ROLE_TOKENS = frozenset({
    "codex", "claude", "gpt", "gpt-5.5", "gpt5", "sonnet", "opus", "haiku", "gemini", "glm", "deepseek",
    "thunderomlx", "antigravity", "claude-cli", "gemini-cli", "gemini-sdk", "command", "anthropic",
    "openai", "google", "zhipu", "local", "mistral", "qwen",
})
_SELECTION_NON_ROLE_PREFIXES = (
    "gpt-", "gpt5", "gemini-", "gemini3", "glm-", "claude-", "deepseek-", "thunderomlx-", "antigravity-", "codex-",
)


def _is_non_role_token(value: str) -> bool:
    v = str(value or "").strip().lower()
    if not v:
        return False
    if v in _SELECTION_NON_ROLE_TOKENS:
        return True
    return any(v.startswith(p) for p in _SELECTION_NON_ROLE_PREFIXES)


def _normalize_selection_role(value: Any) -> str:
    v = str(value or "").strip().lower().replace("_", "-")
    return _SELECTION_ROLE_ALIASES.get(v, v)


def _selection_node_role(node: dict[str, Any]) -> str:
    """Resolve a node's INTENDED role for operator selection, skipping backend/model/provider tokens.

    Returns the first field that resolves to a recognized HARD role (builder/planner/evaluator/pm), or ""
    when none does -- in which case the mismatch guard does not fire and selection is unchanged. Backend/
    model/provider tokens and other non-role junk (e.g. owner="codex", owner="solar-harness") are skipped so
    the real role (e.g. logical_operator="ImplementationWorker"->builder, "Verifier"->evaluator) surfaces.
    Does NOT touch role_from_node/profile selection."""
    if executable_logical_operator(node):
        role = executable_dispatch_role(node)
        if role in _HARD_ROLES:
            return role
    elif isinstance(node.get("allowed_operators"), dict):
        role = executable_physical_role(node)
        if role in _HARD_ROLES:
            return role

    for field in ("target_role", "role", "owner", "persona", "worker_role", "handoff_to", "logical_operator"):
        raw = node.get(field)
        if raw is None or str(raw).strip() == "":
            continue
        if _is_non_role_token(raw):
            continue
        role = _normalize_selection_role(raw)
        if role in _HARD_ROLES:
            return role
    return ""


# --- Default provider policy: prefer Claude/Anthropic + Codex/OpenAI for normal dispatch ------------
# Non-default providers (gemini/google, glm/zhipu, deepseek, local/thunderomlx, browser, ...) stay fully
# functional but are deprioritized in OPERATOR selection unless the dispatch explicitly wants them:
#   * pinned          -> node.preferred_operator (bypasses scoring entirely; unaffected)
#   * profile/backend -> the base profile already targets a non-default provider (--profile gemini-builder,
#                        --backend gemini-cli, --model gemini, node.preferred_profile=...) -> policy is off
#   * requested       -> the node's operator_selector names that provider/vendor/model/operator id
# Configurable; SOLAR_MULTI_TASK_DEFAULT_PROVIDERS="" disables the policy (all providers equal).
DEFAULT_OPERATOR_PROVIDER_ORDER = tuple(
    p.strip().lower()
    for p in os.environ.get("SOLAR_MULTI_TASK_DEFAULT_PROVIDERS", "anthropic,openai").split(",")
    if p.strip()
)
DEFAULT_OPERATOR_PROVIDERS = frozenset(DEFAULT_OPERATOR_PROVIDER_ORDER)
_NON_DEFAULT_PROVIDER_PROFILE_TOKENS = ("gemini", "glm", "zhipu", "deepseek", "thunder", "omlx", "antigravity")


def _profile_targets_nondefault_provider(profile: dict[str, Any]) -> bool:
    """True when the base profile explicitly targets a non-default provider (explicit override -> don't
    apply the default-provider policy)."""
    backend = str(profile.get("backend") or "").strip().lower()
    if backend in {"gemini-cli", "gemini-sdk"}:
        return True
    blob = f"{backend} {str(profile.get('model') or '').lower()} {str(profile.get('name') or '').lower()}"
    return any(token in blob for token in _NON_DEFAULT_PROVIDER_PROFILE_TOKENS)


def _profile_provider_name(profile: dict[str, Any]) -> str:
    return model_provider(str(profile.get("model") or ""), str(profile.get("backend") or ""))


def _profile_allowed_by_default_provider(profile: dict[str, Any]) -> bool:
    # Default mixed policy ("anthropic,openai") is a preference, not a wall; keep non-default profiles
    # available as fallbacks. A single-provider mode ("openai" or "anthropic") is a product contract and
    # must fail closed rather than silently crossing providers.
    if not DEFAULT_OPERATOR_PROVIDERS or len(DEFAULT_OPERATOR_PROVIDERS) != 1:
        return True
    provider = _profile_provider_name(profile)
    return not provider or provider in DEFAULT_OPERATOR_PROVIDERS


def _select_profile_for_role(role: str, profiles: dict[str, Any], provider_policy_required: bool = False) -> str:
    """Select a role-compatible profile while honoring the default-provider policy.

    This is separate from physical-operator selection. A normal DAG node without an operator_selector used to
    pick the first matching profile (`builder` -> Claude) before provider policy had any chance to apply. In
    Codex-only mode that silently consumed Claude. Here the provider policy is applied at profile selection too.
    """
    role_value = str(role or "").strip().lower()
    if not role_value:
        return ""

    if DEFAULT_OPERATOR_PROVIDER_ORDER:
        for provider in DEFAULT_OPERATOR_PROVIDER_ORDER:
            for name, spec in profiles.items():
                if str((spec or {}).get("role", "")).lower() != role_value:
                    continue
                profile = dict(spec or {})
                profile["name"] = str(name)
                if _profile_provider_name(profile) == provider:
                    return str(name)
        if provider_policy_required:
            return ""

    for name, spec in profiles.items():
        if str((spec or {}).get("role", "")).lower() == role_value and not str(name).startswith(("gemini-", "deepseek-", "glm-", "thunder")):
            return str(name)
    return ""


def _operator_provider_requested(operator: dict[str, Any], selector_values: set[str]) -> bool:
    """True when the node's operator_selector explicitly names this operator's provider/vendor/model/id."""
    if not selector_values:
        return False
    for key in ("provider", "vendor", "model", "operator_id"):
        value = str(operator.get(key) or "").strip().lower()
        if value and value in selector_values:
            return True
    return False


# --- Proactive operator backend health: deprioritize operators whose CLI is not installed ----------
# operator_dispatchable() can't tell a configured operator whose backend CLI is missing (e.g. a
# gemini/antigravity `command` operator on a host with no gemini CLI -> exit 1) from a working one. This
# is the proactive complement to the post-failure cooldown: deprioritize BEFORE the first wasted attempt.
_CLI_AVAILABLE_CACHE: dict[str, bool] = {}


def _cli_available(name: str) -> bool:
    if name not in _CLI_AVAILABLE_CACHE:
        _CLI_AVAILABLE_CACHE[name] = shutil.which(name) is not None
    return _CLI_AVAILABLE_CACHE[name]


def _operator_backend_runnable(operator: dict[str, Any]) -> bool:
    """Best-effort, cheap (cached which()) check that the operator's backend CLI exists. Conservative:
    returns True for backends we cannot cheaply verify, so it only deprioritizes a known-missing CLI."""
    backend = str(operator.get("backend") or "").strip().lower()
    provider = str(operator.get("provider") or operator.get("vendor") or "").strip().lower()
    if backend == "claude-cli":
        return _cli_available("claude")
    if backend in {"gemini-cli", "gemini-sdk"}:
        return _cli_available("gemini")
    if backend == "command":
        if provider == "openai":
            return _cli_available("codex")
        if provider == "google":
            return _cli_available("gemini")
        return True  # deepseek/glm/local/browser command operators: cannot cheaply verify -> don't penalize
    return True


def select_operator(node: dict[str, Any], base_profile: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    frozen_candidates = node.get("physical_candidates")
    if isinstance(frozen_candidates, list) and frozen_candidates:
        observations: list[dict[str, Any]] = []
        selected: dict[str, Any] | None = None
        for candidate in sorted(
            (item for item in frozen_candidates if isinstance(item, dict)),
            key=lambda item: (int(item.get("rank") or 0), str(item.get("operator_id") or "")),
        ):
            operator_id = str(candidate.get("operator_id") or "").strip()
            operator = resolve_operator(operator_id)
            ok, reason = operator_dispatchable(operator)
            if ok and node.get("execution_authority"):
                from execution_authority import check_operator
                from execution_resources import check as check_resources
                try:
                    check_operator(node["execution_authority"], operator_id, operator)
                    resource_errors = check_resources(node.get("resource_requirements") or {}, operator)
                    if resource_errors:
                        ok, reason = False, ";".join(resource_errors)
                except ValueError as exc:
                    ok, reason = False, str(exc)
            if ok and not _operator_backend_runnable(operator):
                ok, reason = False, "backend_cli_unavailable"
            if ok and operator_in_failure_cooldown(operator_id):
                ok, reason = False, "runtime_failure_cooldown"
            observation = {
                "operator_id": operator_id,
                "state": "READY" if ok else "UNAVAILABLE",
                "rank": int(candidate.get("rank") or 0),
            }
            if reason:
                observation["reason"] = reason
            observations.append(observation)
            if ok and selected is None:
                selected = dict(operator)
                selected["scheduler_candidate_rank"] = observation["rank"]
                selected["scheduler_candidate_observations"] = observations
                break
        if selected is not None:
            # Record lower-ranked entries as not evaluated; no scheduler may
            # replace the first ready frozen candidate with a preferred model.
            seen = {item["operator_id"] for item in observations}
            for candidate in sorted(
                (item for item in frozen_candidates if isinstance(item, dict)),
                key=lambda item: (int(item.get("rank") or 0), str(item.get("operator_id") or "")),
            ):
                operator_id = str(candidate.get("operator_id") or "").strip()
                if operator_id not in seen:
                    observations.append({
                        "operator_id": operator_id,
                        "state": "NOT_EVALUATED_AFTER_SELECTION",
                        "rank": int(candidate.get("rank") or 0),
                    })
            selected["scheduler_candidate_observations"] = observations
            return selected, ""
        node["scheduler_candidate_observations"] = observations
        reasons = ",".join(
            f"{item['operator_id']}={item.get('reason', item['state'])}" for item in observations
        )
        return None, f"frozen_physical_candidates_unavailable:{reasons}"

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
    selection_node_role = _selection_node_role(node)
    # Default-provider policy is active only for normal dispatch; an explicitly non-default base profile
    # (e.g. --profile gemini-builder / --backend gemini-cli) turns it off so the override is preserved.
    provider_policy_active = bool(DEFAULT_OPERATOR_PROVIDERS) and not _profile_targets_nondefault_provider(base_profile)
    selector_values = set(_selector_values(selector))
    if task_type:
        selector_values.update(_expand_str(task_type))
        
    modality_values = {"image", "vision", "multimodal", "screenshot", "ocr", "diagram", "mockup", "ui"}
    modality_required = bool(selector_values & modality_values)
    
    for operator in operators:
        if bool(operator.get("deprecated")):
            continue
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

        # Deprioritize operators that recently failed at runtime (e.g. an unconfigured backend CLI that
        # exits non-zero). operator_dispatchable can't see this. Heavy penalty, not a hard exclude, so a
        # cooled-down operator is still a last resort if nothing healthy matches.
        if operator_in_failure_cooldown(str(operator.get("operator_id") or "")):
            score -= 100000

        # Hard role-mismatch guard: a builder node must not prefer a planner/evaluator/pm operator just
        # because of keyword overlap (e.g. node owner="codex" matching a "...codex...planner" operator id).
        # Penalty, not a hard exclude, so a mismatched operator is still a last resort if nothing matches.
        if selection_node_role in _HARD_ROLES:
            op_role = _normalize_selection_role(operator.get("role"))
            if op_role in _HARD_ROLES and op_role != selection_node_role:
                score -= 100000

        # Default-provider policy: deprioritize non-default providers (gemini/glm/deepseek/local/browser/...)
        # for normal dispatch, unless this node explicitly requests this operator's provider/vendor/model/id.
        # Penalty, not a hard exclude, so a provider that is the only viable option (e.g. vision-only) still wins.
        if provider_policy_active:
            op_provider = str(operator.get("provider") or operator.get("vendor") or "").strip().lower()
            if op_provider and op_provider not in DEFAULT_OPERATOR_PROVIDERS and not _operator_provider_requested(operator, selector_values):
                score -= 100000

        # Proactive backend health: an operator whose backend CLI is not installed will fail at runtime;
        # deprioritize it before the first wasted attempt (complements the post-failure cooldown).
        if not _operator_backend_runnable(operator):
            score -= 100000

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
            "codex-builder",
            "antigravity-multimodal",
            "gemini-builder",
            "deepseek-builder",
            "thunderomlx-local",
            "builder",
            "knowledge-extractor",
        ])
    elif role == "planner":
        candidates.extend(["codex-planner", "glm-planner", "planner", "gemini-builder", "thunderomlx-local"])
    elif role == "evaluator":
        candidates.extend(["codex-evaluator", "gemini-evaluator", "antigravity-multimodal", "evaluator", "thunderomlx-local"])
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
        if not _profile_allowed_by_default_provider(profile):
            continue
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
        if not _profile_allowed_by_default_provider(profile):
            continue
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
        command = str(profile.get("command") or "").strip()
        if provider == "openai":
            codex = shutil.which("codex")
            driver = HARNESS_DIR / "tools" / "codex_operator.py"
            if codex and driver.exists():
                result = {"status": "ok", "evidence": f"cli={codex} driver={driver}", "checked_at": started}
            else:
                missing = []
                if not codex:
                    missing.append("codex cli")
                if not driver.exists():
                    missing.append(str(driver))
                result = {"status": "error", "evidence": "missing " + ", ".join(missing), "checked_at": started}
        elif provider == "gemini":
            gemini = shutil.which("gemini")
            if gemini:
                result = {"status": "ok", "evidence": f"cli={gemini}", "checked_at": started}
            else:
                result = {"status": "error", "evidence": "gemini cli missing", "checked_at": started}
        elif command:
            result = {"status": "ok", "evidence": "command configured", "checked_at": started}
        else:
            result = {"status": "error", "evidence": "command missing", "checked_at": started}
    else:
        result = {"status": "error", "evidence": f"unsupported backend={backend}", "checked_at": started}
    cache = read_probe_cache()
    cache[probe_key(provider, model, backend)] = result
    write_probe_cache(cache)
    return {"profile": profile_name, "provider": provider, "backend": backend, "model": model, **result}


def role_from_node(node: dict[str, Any]) -> str:
    if executable_logical_operator(node):
        return executable_dispatch_role(node)
    if isinstance(node.get("allowed_operators"), dict):
        return executable_physical_role(node)
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
    frozen_candidates = isinstance(node.get("physical_candidates"), list)
    # Frozen physical assignments are the execution authority. Legacy profile
    # and quota-recovery hints may remain on a projected node as history, but
    # they must never bypass re-evaluation of the ranked candidate list.
    requested_profile = profile_override or (
        "" if frozen_candidates else str(node.get("preferred_profile") or node.get("profile") or "")
    )
    profile_name = normalize_profile_name(requested_profile, profiles)
    if not profile_name:
        role = role_from_node(node)
        profile_name = _select_profile_for_role(role, profiles, provider_policy_required=role in {"builder", "planner", "evaluator"})
        if not profile_name and DEFAULT_OPERATOR_PROVIDERS and role in {"builder", "planner", "evaluator"}:
            providers = ",".join(DEFAULT_OPERATOR_PROVIDER_ORDER)
            raise ValueError(f"no multi-task profile for role={role} within SOLAR_MULTI_TASK_DEFAULT_PROVIDERS={providers}")
    profile_name = normalize_profile_name(profile_name or str((config.get("defaults") or {}).get("profile") or "builder"), profiles)
    quota_fallback_from = ""
    quota_blocked = set() if frozen_candidates else {
        normalize_profile_name(v, profiles) for v in _as_string_list(node.get("quota_blocked_profiles"))
    }
    if not frozen_candidates and not profile_override and profile_name in profiles and node.get("quota_failure_reason"):
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
    if not frozen_candidates and not profile_override and profile_name in quota_blocked:
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
    node_model = "" if frozen_candidates or quota_fallback_from else str(node.get("preferred_model") or "")
    selected["backend"] = str(backend_override or selected.get("backend") or (config.get("defaults") or {}).get("backend") or "claude-cli")
    selected["model"] = profile_model_with_compatible_override(selected, model_override, node_model)
    selected["approval_mode"] = str(selected.get("approval_mode") or "auto_edit")
    if quota_fallback_from:
        selected["quota_fallback_from"] = quota_fallback_from
        selected["quota_fallback_reason"] = "quota_exhausted"
    if not frozen_candidates and not profile_override and not backend_override and not model_override:
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
    if frozen_candidates or not (requested_profile and (node.get("quota_failure_reason") or node.get("auth_failure_reason"))):
        operator, fallback_reason = select_operator(node, selected)
        if operator:
            selected = apply_operator_to_profile(selected, operator, fallback_reason)
            if operator.get("scheduler_candidate_observations"):
                selected["scheduler_candidate_observations"] = deepcopy(operator["scheduler_candidate_observations"])
                selected["scheduler_candidate_rank"] = operator.get("scheduler_candidate_rank")
        elif frozen_candidates:
            raise ValueError(fallback_reason or "frozen_physical_candidates_unavailable")
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
            "export CLAUDE_CODE_MAX_OUTPUT_TOKENS=${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-12000}",
            (
                "claude --dangerously-skip-permissions "
                "--permission-mode bypassPermissions "
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
            f"claude --dangerously-skip-permissions $MODEL_FLAG $EXTRA_FLAGS -p {dispatch_expr}",
        ])
    empty_mcp = HARNESS_DIR / "config" / "empty-mcp.json"
    return (
        "claude --dangerously-skip-permissions --permission-mode bypassPermissions "
        f"--model {shlex.quote(claude_model_arg(model))} "
        f"--tools default --strict-mcp-config --mcp-config {shlex.quote(str(empty_mcp))} "
        f"-p {dispatch_expr}"
    )


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
    # Two schedulers can legitimately replace the same node within one second.
    # The timestamp keeps ids sortable while the nonce prevents those attempts
    # from sharing a status directory and silently overwriting one another.
    nonce = uuid.uuid4().hex[:10]
    return f"mt-{stamp}-{safe_sid}-{safe_node}-{nonce}"


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


def _scheduler_pid_file(pid: int | None = None) -> Path:
    pid_value = os.getpid() if pid is None else int(pid)
    return SCHEDULER_PID_DIR / f"scheduler-{pid_value}.json"


def _scheduler_log_file(pid: int | None = None) -> Path:
    pid_value = os.getpid() if pid is None else int(pid)
    return SCHEDULER_PID_DIR / f"scheduler-{pid_value}.log"


def _append_scheduler_log(message: str, pid: int | None = None) -> None:
    path = _scheduler_log_file(pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{now_iso()} {message}\n")


def _extract_graph_args(command: str) -> list[str]:
    try:
        parts = shlex.split(str(command or ""))
    except ValueError:
        parts = str(command or "").split()
    values: list[str] = []
    idx = 0
    while idx < len(parts):
        item = parts[idx]
        if item == "--graph" and idx + 1 < len(parts):
            values.append(parts[idx + 1])
            idx += 2
            continue
        if item.startswith("--graph="):
            values.append(item.split("=", 1)[1])
        idx += 1
    return [str(Path(value).expanduser()) for value in values if str(value).strip()]


def _register_scheduler_pid(explicit_graphs: list[str]) -> Path:
    path = _scheduler_pid_file()
    log_path = _scheduler_log_file()
    graphs = [str(Path(item).expanduser()) for item in explicit_graphs if str(item).strip()]
    payload = {
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "started_at": now_iso(),
        "graphs": graphs,
        "graph_count": len(graphs),
        "argv": list(sys.argv),
        "cwd": str(Path.cwd()),
        "log": str(log_path),
        "command": " ".join(shlex.quote(arg) for arg in sys.argv),
    }
    json_write(path, payload)
    _append_scheduler_log(f"register graphs={len(graphs)}", os.getpid())
    return path


def _unregister_scheduler_pid(pid: int | None = None) -> None:
    pid_value = os.getpid() if pid is None else int(pid)
    path = _scheduler_pid_file(pid_value)
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass
    _append_scheduler_log("unregister", pid_value)


def _pid_is_alive(pid: int) -> bool:
    if os.name == "nt":
        # ``os.kill(pid, 0)`` maps to CTRL_C_EVENT on Windows and interrupts
        # the entire console group.  Query the process handle instead.
        import _winapi

        try:
            handle = _winapi.OpenProcess(0x1000, False, int(pid))
        except OSError:
            return False
        try:
            return _winapi.GetExitCodeProcess(handle) == 259
        finally:
            _winapi.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _ps_snapshot_by_pid() -> dict[int, dict[str, Any]]:
    try:
        out = subprocess.check_output(
            ["ps", "-Ao", "pid=,etime=,rss=,command="],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        return {}
    rows: dict[int, dict[str, Any]] = {}
    for line in out.splitlines():
        raw = line.strip()
        if not raw:
            continue
        parts = raw.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
        except Exception:
            continue
        rows[pid] = {
            "pid": pid,
            "elapsed": parts[1],
            "rss_kb": int(parts[2]) if parts[2].isdigit() else 0,
            "command": parts[3],
        }
    return rows


def _scheduler_process_rows() -> list[dict[str, Any]]:
    rows = _ps_snapshot_by_pid()
    found: list[dict[str, Any]] = []
    for record in rows.values():
        command = str(record.get("command") or "")
        if "multi_task_runner.py" not in command or " start " not in f" {command} ":
            continue
        if "--graph" not in command:
            continue
        found.append(record)
    return found


_EVAL_PM_ACTIVE_STATUSES = frozenset({"submitted", "submitted_fallback", "leased", "running", "pending"})
_EVAL_PM_TERMINAL_STATUSES = frozenset({"completed", "failed", "failed_contract_closeout", "cancelled", "canceled"})
_EVAL_PENDING_GRACE_SEC = int(os.environ.get("SOLAR_GRAPH_EVAL_RECOVER_SEC", "600") or "600")


def _node_has_pending_evaluation(node: dict[str, Any]) -> bool:
    """Return true while an evaluator assignment still has live ownership.

    Evaluators submitted through operatord do not appear in ``active_tasks()``,
    which only reads the multi-task/tmux status directory.  The graph's
    evaluator assignment is therefore the durable bridge used by the
    foreground runner.  Exact PM state or pane lease wins; the bounded grace
    window covers the small interval before those runtime records appear.
    """
    assignments = node.get("eval_assignments")
    if not isinstance(assignments, list):
        assignments = []
    if not assignments and str(node.get("eval_dispatch_id") or "").strip():
        assignments = [
            {
                "pane": node.get("eval_assigned_to"),
                "dispatch_id": node.get("eval_dispatch_id"),
                "pm_task_id": node.get("eval_pm_task_id"),
                "dispatched_at": node.get("eval_dispatched_at"),
            }
        ]

    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        pm_task_id = str(assignment.get("pm_task_id") or "").strip()
        pm_status = ""
        if pm_task_id and Path(pm_task_id).name == pm_task_id:
            pm_record = HARNESS_DIR / "run" / "pm-inbox" / f"{pm_task_id}.json"
            try:
                payload = json.loads(pm_record.read_text(encoding="utf-8"))
                pm_status = str(payload.get("status") or "").strip().lower()
            except (OSError, json.JSONDecodeError, AttributeError):
                pm_status = ""
            if pm_status in _EVAL_PM_ACTIVE_STATUSES:
                return True
            if pm_status in _EVAL_PM_TERMINAL_STATUSES:
                continue

        pane = str(assignment.get("pane") or "").strip()
        dispatch_id = str(assignment.get("dispatch_id") or "").strip()
        if pane and dispatch_id and not pane.startswith("operator:"):
            try:
                from pane_lease import read_lease

                lease = read_lease(pane) or {}
                if (
                    str(lease.get("dispatch_id") or "") == dispatch_id
                    and str(lease.get("expires_at") or "") > _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                ):
                    return True
            except Exception:
                pass

        dispatched_at = str(
            assignment.get("dispatched_at") or node.get("eval_dispatched_at") or ""
        )
        dispatched_ts = parse_iso(dispatched_at)
        if dispatched_ts is not None and (time.time() - dispatched_ts) < _EVAL_PENDING_GRACE_SEC:
            return True
    return False


def _graph_runner_state(graph_path: Path) -> dict[str, Any]:
    try:
        graph = load_graph(graph_path.expanduser())
    except Exception as exc:
        return {
            "ok": False,
            "graph": str(graph_path),
            "sid": graph_path.stem,
            "all_terminal": False,
            "has_active": False,
            "ready_nodes": [],
            "reason": f"graph_load_error:{exc}",
        }
    node_ids = [str(node.get("id") or "") for node in graph.get("nodes", [])]
    statuses = [str(node_status(graph, node_id) or "pending").lower() for node_id in node_ids]
    ready = [str(node.get("id") or "") for node in ready_nodes(graph)]
    all_terminal = bool(statuses) and all(status in _SCHED_GRAPH_TERMINAL for status in statuses)
    has_pending_evaluation = any(
        _node_has_pending_evaluation(node)
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
    )
    has_active = any(status in _SCHED_GRAPH_ACTIVE for status in statuses) or has_pending_evaluation
    return {
        "ok": True,
        "graph": str(graph_path.expanduser()),
        "sid": sprint_id_for(graph, graph_path),
        "all_terminal": all_terminal,
        "has_active": has_active,
        "has_pending_evaluation": has_pending_evaluation,
        "ready_nodes": ready,
        "reason": "completed_graph_runner" if (all_terminal and not has_active and not ready) else "graph_not_terminal",
        "statuses": statuses,
    }


def _all_graphs_terminal(explicit_graphs: list[str]) -> bool:
    if not explicit_graphs:
        return False
    graphs = graph_files(explicit_graphs)
    if not graphs:
        return False
    for graph_path in graphs:
        state = _graph_runner_state(graph_path)
        if not state.get("ok"):
            return False
        if not state.get("all_terminal"):
            return False
        if state.get("has_active"):
            return False
        if state.get("ready_nodes"):
            return False
    return True


def detect_stale_scheduler_runners(apply_cleanup: bool = False) -> list[dict[str, Any]]:
    registry_rows: dict[int, dict[str, Any]] = {}
    for pid_file in SCHEDULER_PID_DIR.glob("scheduler-*.json"):
        payload = read_task_status(pid_file)
        if not payload:
            continue
        try:
            pid = int(payload.get("pid"))
        except Exception:
            continue
        registry_rows[pid] = payload

    ps_rows = {int(row["pid"]): row for row in _scheduler_process_rows()}
    combined_pids = sorted(set(registry_rows) | set(ps_rows))
    rows: list[dict[str, Any]] = []
    for pid in combined_pids:
        reg = registry_rows.get(pid) or {}
        ps_row = ps_rows.get(pid) or {}
        command = str(ps_row.get("command") or reg.get("command") or "")
        graphs = list(reg.get("graphs") or _extract_graph_args(command))
        if not graphs:
            rows.append({
                "pid": pid,
                "graph": "N/A",
                "sprint_id": "N/A",
                "elapsed": str(ps_row.get("elapsed") or "N/A"),
                "rss_mb": round(float(ps_row.get("rss_kb") or 0) / 1024.0, 1),
                "log": str(reg.get("log") or _scheduler_log_file(pid)),
                "reason": "no_explicit_graph",
                "stale": False,
                "action": "keep",
                "started_at": str(reg.get("started_at") or "N/A"),
            })
            continue
        graph_states = [_graph_runner_state(Path(graph_path)) for graph_path in graphs]
        stale = bool(graph_states) and all(
            state.get("ok")
            and state.get("all_terminal")
            and not state.get("has_active")
            and not state.get("ready_nodes")
            for state in graph_states
        )
        action = "keep"
        if stale and apply_cleanup and _pid_is_alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
                action = "sigterm"
                _append_scheduler_log("stale_cleanup_sigterm", pid)
            except OSError as exc:
                action = f"sigterm_error:{exc}"
        for state in graph_states:
            rows.append({
                "pid": pid,
                "graph": str(state.get("graph") or "N/A"),
                "sprint_id": str(state.get("sid") or "N/A"),
                "elapsed": str(ps_row.get("elapsed") or "N/A"),
                "rss_mb": round(float(ps_row.get("rss_kb") or 0) / 1024.0, 1),
                "log": str(reg.get("log") or _scheduler_log_file(pid)),
                "reason": str(state.get("reason") or "N/A"),
                "stale": stale,
                "action": action,
                "started_at": str(reg.get("started_at") or "N/A"),
            })
    return rows


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
        path = Path(graph_path).expanduser()
        if not path.is_absolute():
            candidates = [Path.cwd() / path, HARNESS_DIR / path, SPRINTS_DIR / path.name]
            for candidate in candidates:
                if candidate.exists():
                    path = candidate
                    break
        graph = load_graph(path)
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
    exact_result = correlated_terminal_result(row)
    if exact_result is not None:
        return str(exact_result.get("status") or current).strip().lower()
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


def task_work_label(row: dict[str, Any]) -> str:
    status = str(row.get("effective_status") or row.get("status") or "").lower()
    return "ACTIVE" if status in ACTIVE_TASK_STATUSES else "hist"


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


def tmux_window_records() -> list[dict[str, str]]:
    try:
        out = subprocess.check_output(
            [
                "tmux",
                "list-windows",
                "-t",
                SESSION,
                "-F",
                "#{window_id}\t#{window_name}\t#{window_active}\t#{pane_current_command}\t#{pane_dead}\t#{pane_pid}",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        return []
    windows: list[dict[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        window_id = parts[0].strip() if parts else ""
        name = parts[1].strip() if len(parts) > 1 else ""
        if not name:
            continue
        windows.append({
            "window_id": window_id,
            "window": name,
            "target": f"{SESSION}:{window_id}" if window_id else f"{SESSION}:{name}",
            "active": parts[2].strip() if len(parts) > 2 else "",
            "command": parts[3].strip() if len(parts) > 3 else "",
            "dead": parts[4].strip() if len(parts) > 4 else "",
            "pane_pid": parts[5].strip() if len(parts) > 5 else "",
        })
    return windows


def tmux_window_map() -> dict[str, dict[str, str]]:
    windows: dict[str, dict[str, str]] = {}
    for record in tmux_window_records():
        # Status rendering is name-based for compatibility. Lifecycle code
        # uses tmux_window_records() so duplicate names retain distinct IDs.
        windows.setdefault(str(record.get("window") or ""), record)
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
    enriched["work"] = task_work_label(enriched)
    age_s = task_age_s(enriched)
    enriched["age_s"] = age_s
    enriched["age"] = format_age_s(age_s)
    enriched["data_class"] = task_data_class(enriched)
    return enriched


def _finalize_terminal_attribution(row: dict[str, Any]) -> None:
    """Durably backfill the node-keyed completion attribution (exit_code/status) for a terminal task.

    The tmux runner writes the final exit_code to the worker's RUN_DIR status.json but never co-locates it
    with the sprint; this mirrors it into the durable per-node snapshot. Idempotent (skips when the snapshot
    already records this completion) so the hot status path does not write-amplify. Best-effort."""
    try:
        status = str(row.get("status") or "").lower()
        if status not in TERMINAL_TASK_STATUSES:
            return
        sid = str(row.get("sprint_id") or "").strip()
        node_id = str(row.get("node_id") or "").strip()
        if not sid or not node_id:
            return
        import node_runstate

        runstate_root = Path(str(row.get("node_runstate_root") or SPRINTS_DIR))
        snap = node_runstate.read_snapshot(runstate_root, sid, node_id)
        attr = snap.get("build_attribution") if isinstance(snap.get("build_attribution"), dict) else {}
        if not attr:
            attr = snap.get("attribution") if isinstance(snap.get("attribution"), dict) else {}
        row_dispatch_id = str(row.get("id") or row.get("task_id") or "").strip()
        attributed_dispatch_id = str(attr.get("dispatch_id") or "").strip()
        # list_task_rows() scans retained history as well as the current run.
        # A terminal status for an older task sharing the same sprint/node must
        # never replace the active attempt's attribution.  Correlate by the
        # immutable dispatch id before finalizing; the current task was already
        # recorded at launch by _record_node_attribution().
        if attributed_dispatch_id and row_dispatch_id != attributed_dispatch_id:
            return
        if attr.get("phase") == "completed" and attr.get("status") == status and attr.get("exit_code") == row.get("exit_code"):
            return
        node_runstate.record(runstate_root, sid, node_id, "attribution", {
            "phase": "completed",
            "status": status,
            "exit_code": row.get("exit_code"),
            "backend": row.get("backend"),
            "vendor": row.get("operator_vendor") or row.get("provider"),
            "model": row.get("operator_model") or row.get("model"),
            "provider": row.get("provider"),
            "operator_id": row.get("operator_id"),
            "profile": row.get("profile"),
            "role": row.get("role"),
            "dispatch_id": row_dispatch_id,
        })
    except Exception:
        pass


def list_task_rows() -> list[dict[str, Any]]:
    if not RUN_DIR.exists():
        return []
    windows = tmux_window_map()
    rows: list[dict[str, Any]] = []
    for path in sorted(RUN_DIR.glob("*/status.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        row = read_task_status(path)
        if row:
            _finalize_terminal_attribution(row)
            rows.append(enrich_task_row(row, windows))
    return rows


def active_tasks() -> list[dict[str, Any]]:
    return [row for row in list_task_rows() if str(row.get("effective_status") or row.get("status", "")).lower() in ACTIVE_TASK_STATUSES]


def idle_tmux_window_candidates(
    tasks: list[dict[str, Any]] | None = None,
    windows: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Return terminal-task and orphan shell windows that are safe to reuse."""
    rows = tasks if tasks is not None else list_task_rows()
    window_records = windows if windows is not None else tmux_window_records()
    candidates: list[dict[str, Any]] = []
    tracked_targets: set[str] = set()
    seen_targets: set[str] = set()
    client_window_ids = {
        str(client.get("window_id") or "")
        for client in tmux_client_records()
        if str(client.get("window_id") or "")
    }

    for row in rows:
        effective_status = str(row.get("effective_status") or row.get("status") or "").lower()
        if (
            effective_status not in EFFECTIVE_TERMINAL_TASK_STATUSES
            and not effective_status.startswith("reaped")
        ):
            continue
        window = str(row.get("window") or "").strip()
        if not window:
            continue
        updated_at = str(row.get("updated_at") or row.get("created_at") or "")
        updated_ts = parse_iso(updated_at)
        for info in window_records:
            if str(info.get("window") or "") != window:
                continue
            if str(info.get("window_id") or "") in client_window_ids:
                continue
            if str(info.get("dead") or "") == "1" or str(info.get("active") or "") == "1":
                continue
            command = str(info.get("command") or "").strip().lower()
            if command not in REUSABLE_WINDOW_COMMANDS:
                continue
            target = str(info.get("target") or f"{SESSION}:{window}")
            if target in seen_targets:
                continue
            tracked_targets.add(target)
            seen_targets.add(target)
            candidates.append({
                "window": window,
                "window_target": target,
                "window_id": str(info.get("window_id") or ""),
                "task_id": str(row.get("id") or ""),
                "kind": "tracked",
                "effective_status": effective_status,
                "updated_at": updated_at or "N/A",
                "updated_ts": updated_ts if updated_ts is not None else -1.0,
                "command": command,
            })

    for info in window_records:
        target = str(info.get("target") or "")
        if target in tracked_targets or target in seen_targets:
            continue
        if str(info.get("window_id") or "") in client_window_ids:
            continue
        if str(info.get("dead") or "") == "1" or str(info.get("active") or "") == "1":
            continue
        command = str(info.get("command") or "").strip().lower()
        if command not in REUSABLE_WINDOW_COMMANDS:
            continue
        seen_targets.add(target)
        window = str(info.get("window") or "")
        candidates.append({
            "window": window,
            "window_target": target or f"{SESSION}:{window}",
            "window_id": str(info.get("window_id") or ""),
            "task_id": "N/A",
            "kind": "orphan",
            "effective_status": "orphan_shell",
            "updated_at": "N/A",
            "updated_ts": -1.0,
            "command": command,
        })

    return candidates


def historical_active_tmux_windows(
    tasks: list[dict[str, Any]] | None = None,
    windows: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Return terminal task shells occupying the session's active window."""
    rows = tasks if tasks is not None else list_task_rows()
    window_records = windows if windows is not None else tmux_window_records()
    records_by_name: dict[str, list[dict[str, str]]] = {}
    for info in window_records:
        records_by_name.setdefault(str(info.get("window") or ""), []).append(info)

    seen_targets: set[str] = set()
    results: list[dict[str, Any]] = []
    for row in rows:
        effective_status = str(row.get("effective_status") or row.get("status") or "").lower()
        if (
            effective_status not in EFFECTIVE_TERMINAL_TASK_STATUSES
            and not effective_status.startswith("reaped")
        ):
            continue
        window = str(row.get("window") or "").strip()
        if not window:
            continue
        for info in records_by_name.get(window, []):
            if str(info.get("active") or "") != "1" or str(info.get("dead") or "") == "1":
                continue
            command = str(info.get("command") or "").strip().lower()
            if command not in REUSABLE_WINDOW_COMMANDS:
                continue
            target = str(info.get("target") or f"{SESSION}:{window}")
            if target in seen_targets:
                continue
            seen_targets.add(target)
            results.append({
                "window": window,
                "window_target": target,
                "window_id": str(info.get("window_id") or ""),
                "task_id": str(row.get("id") or ""),
                "effective_status": effective_status,
                "command": command,
            })
    return results


def tmux_client_records() -> list[dict[str, str]]:
    try:
        out = subprocess.check_output(
            [
                "tmux", "list-clients", "-t", SESSION, "-F",
                "#{client_tty}\t#{window_id}\t#{session_name}",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        return []
    rows: list[dict[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        tty = parts[0].strip() if parts else ""
        if not tty:
            continue
        rows.append({
            "tty": tty,
            "window_id": parts[1].strip() if len(parts) > 1 else "",
            "session": parts[2].strip() if len(parts) > 2 else "",
        })
    return rows


def _anchor_window_name() -> str:
    return short_window("mt-idle-anchor")


def ensure_tmux_anchor_window(cwd: Path | None = None) -> tuple[str, bool]:
    for info in tmux_window_records():
        if str(info.get("window") or "") == _anchor_window_name():
            return str(info.get("target") or f"{SESSION}:{_anchor_window_name()}"), False
    workdir = str(cwd or Path.cwd())
    command = "exec ${SHELL:-/bin/sh}"
    if tmux_session_exists():
        subprocess.check_call([
            "tmux", "new-window", "-d", "-t", SESSION, "-n",
            _anchor_window_name(), "-c", workdir, command,
        ])
    else:
        subprocess.check_call([
            "tmux", "new-session", "-d", "-s", SESSION, "-n",
            _anchor_window_name(), "-c", workdir, command,
        ])
    for info in tmux_window_records():
        if str(info.get("window") or "") == _anchor_window_name():
            return str(info.get("target") or f"{SESSION}:{_anchor_window_name()}"), True
    return f"{SESSION}:{_anchor_window_name()}", True


def detach_and_anchor(cwd: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    target = f"{SESSION}:{_anchor_window_name()}"
    created = False
    if not dry_run:
        target, created = ensure_tmux_anchor_window(cwd=cwd)
        subprocess.run(
            ["tmux", "select-window", "-t", target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return {
        "target": target,
        "created_anchor": created,
        "action": "dry-run" if dry_run else "selected",
    }


def select_reusable_tmux_window(
    preferred_window: str,
    tasks: list[dict[str, Any]] | None = None,
    windows: list[dict[str, str]] | None = None,
) -> tuple[str, bool, str, str]:
    """Select one safe historical shell without reusing active agent panes."""
    if not REUSE_TERMINAL_WINDOWS:
        return preferred_window, False, "", ""
    candidates = idle_tmux_window_candidates(tasks=tasks, windows=windows)
    candidates.sort(key=lambda item: (
        0 if item.get("kind") == "tracked" else 1,
        -float(item.get("updated_ts") or -1.0),
        str(item.get("window") or ""),
    ))
    for candidate in candidates:
        return (
            str(candidate.get("window") or preferred_window),
            True,
            str(candidate.get("task_id") or ""),
            str(candidate.get("window_target") or ""),
        )
    return preferred_window, False, "", ""


def prune_idle_tmux_windows(
    target_keep: int = IDLE_WINDOW_POOL_TARGET,
    dry_run: bool = False,
    keep_windows: set[str] | None = None,
    tasks: list[dict[str, Any]] | None = None,
    windows: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    keep = set(keep_windows or set())
    candidates = idle_tmux_window_candidates(tasks=tasks, windows=windows)
    protected = [row for row in candidates if str(row.get("window_target") or "") in keep]
    prunable = [row for row in candidates if str(row.get("window_target") or "") not in keep]
    retain_budget = max(0, max(0, int(target_keep)) - len(protected))
    prunable.sort(key=lambda item: (
        0 if item.get("kind") == "orphan" else 1,
        float(item.get("updated_ts") or -1.0),
        str(item.get("window") or ""),
    ))
    keepers = prunable[-retain_budget:] if retain_budget > 0 else []
    keeper_targets = {str(item.get("window_target") or "") for item in keepers}
    killed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []

    for candidate in prunable:
        window_target = str(candidate.get("window_target") or "")
        if window_target in keeper_targets:
            kept.append(candidate)
            continue
        action = "dry-run"
        if not dry_run and window_target:
            returncode = subprocess.run(
                ["tmux", "kill-window", "-t", window_target],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            action = "killed-window" if returncode == 0 else "missing-window"
        elif not dry_run:
            action = "no-window"
        result = dict(candidate)
        result["action"] = action
        killed.append(result)

    return {
        "target_keep": max(0, int(target_keep)),
        "candidate_count": len(candidates),
        "protected": protected,
        "kept": kept + protected,
        "killed": killed,
    }


def compact_tmux_session(
    target_keep: int = IDLE_WINDOW_POOL_TARGET,
    dry_run: bool = False,
    cwd: Path | None = None,
) -> dict[str, Any]:
    tasks = list_task_rows()
    windows = tmux_window_records()
    historical = historical_active_tmux_windows(tasks=tasks, windows=windows)
    reusable = idle_tmux_window_candidates(tasks=tasks, windows=windows)

    destination_target = ""
    created_anchor = False
    historical_targets = {str(item.get("window_target") or "") for item in historical}
    orphan_targets = [
        str(item.get("window_target") or "")
        for item in reusable
        if str(item.get("kind") or "") == "orphan"
        and str(item.get("window_target") or "") not in historical_targets
    ]
    if orphan_targets:
        destination_target = orphan_targets[0]
    elif historical and not dry_run:
        destination_target, created_anchor = ensure_tmux_anchor_window(cwd=cwd)

    switches: list[dict[str, str]] = []
    if historical and destination_target:
        active_window_ids = {str(item.get("window_id") or "") for item in historical}
        for client in tmux_client_records():
            if str(client.get("window_id") or "") not in active_window_ids:
                continue
            tty = str(client.get("tty") or "")
            action = "dry-run"
            if not dry_run and tty:
                subprocess.run(
                    ["tmux", "switch-client", "-c", tty, "-t", destination_target],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                action = "switched"
            switches.append({
                "tty": tty or "N/A",
                "from_window_id": str(client.get("window_id") or ""),
                "to_target": destination_target,
                "action": action,
            })
        if not dry_run:
            subprocess.run(
                ["tmux", "select-window", "-t", destination_target],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    closed: list[dict[str, str]] = []
    for item in historical:
        target = str(item.get("window_target") or "")
        action = "dry-run"
        if not dry_run and target:
            returncode = subprocess.run(
                ["tmux", "kill-window", "-t", target],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            action = "killed-window" if returncode == 0 else "missing-window"
        closed.append({
            "window": str(item.get("window") or ""),
            "window_target": target or "N/A",
            "task_id": str(item.get("task_id") or "N/A"),
            "action": action,
        })

    shrink = prune_idle_tmux_windows(
        target_keep=target_keep,
        dry_run=dry_run,
        keep_windows={destination_target} if destination_target else set(),
        tasks=list_task_rows() if not dry_run else tasks,
        windows=tmux_window_records() if not dry_run else windows,
    )
    return {
        "historical_active": historical,
        "destination_target": destination_target or "N/A",
        "created_anchor": created_anchor,
        "switches": switches,
        "closed": closed,
        "shrink": shrink,
        "dry_run": dry_run,
        "target_keep": target_keep,
    }


def active_task_for_node(sid: str, node_id: str, tasks: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Return an active worker row for this exact graph node, if one already exists."""
    sid = str(sid or "").strip()
    node_id = str(node_id or "").strip()
    if not sid or not node_id:
        return None
    for task in tasks if tasks is not None else active_tasks():
        if str(task.get("sprint_id") or "").strip() != sid:
            continue
        if str(task.get("node_id") or "").strip() != node_id:
            continue
        status = str(task.get("effective_status") or task.get("status") or "").strip().lower()
        if status in ACTIVE_TASK_STATUSES:
            return task
    return None


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


def worker_activity_projection(
    tmux_live: bool,
    inventory: dict[str, Any],
    active_count: int,
    has_tasks: bool,
) -> dict[str, Any]:
    live = int(inventory.get("live", 0) or 0)
    if tmux_live:
        data_source = "live" if live else "idle:no_active_workers"
        ok = True
    else:
        data_source = "history:no_multi_task_session" if has_tasks else "no_live_workers"
        ok = not has_tasks
    return {
        "ok": ok,
        "data_source": data_source,
        "active_workers": f"{live} live / {int(active_count)} active",
    }


def monitor_summary(result: dict[str, Any], _messages: list[str]) -> dict[str, Any]:
    tasks = list_task_rows()
    inventory = task_inventory(tasks)
    active_count = sum(
        1
        for task in tasks
        if str(task.get("effective_status") or task.get("status") or "").lower() in ACTIVE_TASK_STATUSES
    )
    projection = worker_activity_projection(tmux_session_exists(), inventory, active_count, bool(tasks))
    findings: list[dict[str, Any]] = []
    for graph in result.get("graphs") or []:
        if graph.get("ready") and active_count == 0:
            findings.append({
                "type": "ready_graph_idle",
                "sid": str(graph.get("sid") or "N/A"),
                "ready": list(graph.get("ready") or []),
            })
    status = "warn" if findings or not projection.get("ok") else "ok"
    return {
        "status": status,
        "data_source": projection.get("data_source"),
        "active_workers": projection.get("active_workers"),
        "findings": findings,
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


def _activate_scheduler_runtime_root(runtime_dir: str | Path) -> Path:
    """Keep every scheduler participant on the projection's runtime root.

    ``--scheduler-runtime-dir`` historically changed only where SchedulerInput
    wrote its graph and state projection.  The runner, dispatcher, evaluator
    broker, and status writer continued resolving handoffs and sidecars from
    the import-time ``HARNESS_SPRINTS_DIR`` instead.  Pin both supported child
    environment names and refresh already-imported scheduler modules so the
    whole run uses one artifact root.
    """
    runtime_root = Path(runtime_dir).expanduser().resolve()
    os.environ["HARNESS_SPRINTS_DIR"] = str(runtime_root)
    os.environ["SOLAR_HARNESS_SPRINTS_DIR"] = str(runtime_root)

    global SPRINTS_DIR
    SPRINTS_DIR = runtime_root
    for module_name in ("graph_scheduler", "graph_node_dispatcher"):
        module = sys.modules.get(module_name)
        if module is not None:
            setattr(module, "SPRINTS_DIR", runtime_root)
    return runtime_root


def prepare_scheduler_input_args(args: argparse.Namespace) -> list[str]:
    """Validate frozen SchedulerInput files and append compatibility projections."""
    inputs = list(getattr(args, "scheduler_input", []) or [])
    if not inputs:
        return list(getattr(args, "graph", []) or [])
    import scheduler_input

    output_dir = _activate_scheduler_runtime_root(
        getattr(args, "scheduler_runtime_dir", "") or SPRINTS_DIR
    )
    artifact_bindings: dict[str, str] = {}
    for raw_binding in list(getattr(args, "artifact_binding", []) or []):
        artifact_type, separator, path = str(raw_binding).partition("=")
        if not separator or not artifact_type.strip() or not path.strip():
            raise ValueError(f"invalid --artifact-binding (expected TYPE=PATH): {raw_binding}")
        artifact_bindings[artifact_type.strip()] = path.strip()
    graphs = list(getattr(args, "graph", []) or [])
    for source in inputs:
        graph_path = scheduler_input.prepare_runtime_graph(
            source,
            output_dir,
            run_contract_path=(getattr(args, "run_contract", "") or None),
            artifact_bindings=artifact_bindings,
        )
        graph_value = str(graph_path)
        if graph_value not in graphs:
            graphs.append(graph_value)
    args.graph = graphs
    return graphs


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
    if graph.get("schema_version") == "solar.scheduler_runtime_projection.v1":
        try:
            import scheduler_input

            verification = scheduler_input.verify_runtime_projection(
                graph,
                graph_path=graph_path,
            )
        except Exception:
            return 0
        if not verification.get("ok"):
            return 0
    profiles: dict[str, Any] | None = None
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
        failure_reason = output_log_failure_kind(dispatch_id)
        if failure_reason not in {"auth_expired", "quota_exhausted"}:
            continue
        frozen_candidates = isinstance(node.get("physical_candidates"), list)
        if graph.get("schema_version") == "solar.scheduler_runtime_projection.v1" or frozen_candidates:
            # SchedulerInput owns both fallback order and attempt budget. Never
            # use the legacy profile ladder to authorize a frozen retry.
            failure_policy = (
                node.get("failure_policy")
                if isinstance(node.get("failure_policy"), dict)
                else {}
            )
            try:
                max_attempts = max(1, int(failure_policy.get("max_attempts") or 1))
            except (TypeError, ValueError):
                max_attempts = 1
            attempt_record = (
                node.get("execution_attempt")
                if isinstance(node.get("execution_attempt"), dict)
                else {}
            )
            try:
                attempt_sequence = max(1, int(attempt_record.get("sequence") or 1))
            except (TypeError, ValueError):
                attempt_sequence = 1
            exhausted_policy = str(failure_policy.get("on_exhausted") or "block_dependents")
            field_prefix = _recoverable_failure_field_prefix(failure_reason)
            node[f"{field_prefix}_reason"] = _recoverable_failure_label(failure_reason)
            node[f"{field_prefix}_task_id"] = dispatch_id
            node[f"{field_prefix}_recovered_at"] = now_iso()
            if attempt_sequence >= max_attempts:
                node["failure_policy_exhausted"] = {
                    "attempt": attempt_sequence,
                    "max_attempts": max_attempts,
                    "on_exhausted": exhausted_policy,
                    "reason": _recoverable_failure_label(failure_reason),
                    "recorded_at": now_iso(),
                }
                node["blocking_reason"] = (
                    f"failure_policy_attempt_budget_exhausted:{attempt_sequence}/{max_attempts}"
                )
                set_node_status(graph, node_id, "failed", dispatch_id=dispatch_id or None)
                if exhausted_policy == "fail_run":
                    for other in graph_nodes(graph):
                        other_id = str(other.get("id") or "")
                        if not other_id or other_id == node_id:
                            continue
                        other_status = str(node_status(graph, other_id) or "").lower()
                        if other_status not in {
                            "passed", "failed", "skipped", "cancelled", "needs_human_review"
                        }:
                            set_node_status(graph, other_id, "cancelled")
                result = graph.setdefault("node_results", {}).setdefault(node_id, {})
                result["blocking_reason"] = node["blocking_reason"]
                result["failure_policy_exhausted"] = deepcopy(node["failure_policy_exhausted"])
            else:
                # Re-open the same planner node. The next select_profile call
                # re-evaluates only physical_candidates in ascending rank.
                prior_status = str(current_status or "failed")
                if isinstance(graph.get("node_results"), dict):
                    graph["node_results"].pop(node_id, None)
                node["status"] = "pending"
                node["updated_at"] = now_iso()
                for key in (
                    "assigned_to",
                    "dispatch_id",
                    "pane",
                    "blocking_reason",
                    "monitor_blocker",
                    "scheduler_candidate_observations",
                ):
                    node.pop(key, None)
                if _gs_ledger_transition is not None:
                    try:
                        _gs_ledger_transition(
                            graph,
                            node_id,
                            prior_status,
                            "pending",
                            "recover_quota_failed_nodes",
                            note="frozen_candidate_retry",
                        )
                    except Exception:
                        pass
            changed += 1
            continue
        if profiles is None:
            profiles = load_profiles().get("profiles") or {}
        status = read_task_status(RUN_DIR / dispatch_id / "status.json") if dispatch_id else None
        profile_name = normalize_profile_name(
            str((status or {}).get("profile") or node.get("preferred_profile") or node.get("profile") or ""),
            profiles,
        )
        recovered_ids = set(_as_string_list(node.get("quota_recovery_task_ids")))
        try:
            recovery_count = int(node.get("quota_recovery_count") or 0)
        except Exception:
            recovery_count = 0
        max_recoveries = int(os.environ.get("SOLAR_MULTI_TASK_MAX_QUOTA_RECOVERIES_PER_NODE", "4") or "4")
        if (dispatch_id and dispatch_id in recovered_ids) or recovery_count >= max_recoveries:
            # Persist the terminal status in the runtime state plane before
            # save_graph strips inline node status from the immutable spec.
            # Without this, a capped failure silently reloads as pending.
            set_node_status(graph, node_id, "failed", dispatch_id=dispatch_id or None)
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
            # Round-4 G3: this terminal->pending reopen (plus the node_results
            # pop above) changes effective status and must leave a ledger record.
            if _gs_ledger_transition is not None:
                try:
                    _gs_ledger_transition(
                        graph, node_id, str(current_status or ""), "pending",
                        "recover_quota_failed_nodes",
                        note=f"quota_fallback:{profile_name or 'unknown'}->{fallback}",
                    )
                except Exception:
                    pass
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
    handoff_root = (
        Path(graph_path).parent
        if graph.get("schema_version") == "solar.scheduler_runtime_projection.v1"
        else SPRINTS_DIR
    )
    handoff = handoff_root / f"{sid}.{node_id}-handoff.md"
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

    def _structured_validation_block(write_scope: Any) -> str:
        # Closeout/review nodes emit machine-parsed files (e.g. review_decision.yaml). A common LLM error
        # is malformed YAML/JSON (e.g. a mapping key at the same indent as block-sequence items), which the
        # evaluator correctly fails. Require the worker to validate each structured deliverable parses.
        items = write_scope if isinstance(write_scope, (list, tuple)) else ([write_scope] if write_scope else [])
        cmds: list[str] = []
        for raw in items:
            path = str(raw).strip()
            low = path.lower()
            if low.endswith((".yaml", ".yml")):
                cmds.append('python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1])); print(\'YAML_OK\')" ' + path)
            elif low.endswith(".json"):
                cmds.append('python3 -c "import json,sys; json.load(open(sys.argv[1])); print(\'JSON_OK\')" ' + path)
        if not cmds:
            return ""
        body = "\n".join(cmds)
        return (
            "\n## Structured Output Validation (REQUIRED)\n\n"
            "Your Write Scope includes machine-parsed file(s). BEFORE writing the handoff you MUST run the"
            " check(s) below and FIX any syntax error until each prints OK:\n\n"
            "```bash\n" + body + "\n```\n\n"
            "A structured deliverable that does not parse FAILS acceptance even if its content is correct."
            " Common YAML error: a mapping key (`key:`) at the SAME indent as block-sequence items (`- item`)"
            " under the same parent -- give the mapping its own key or nest it correctly.\n"
        )

    structured_validation = _structured_validation_block(node.get("write_scope"))

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
{structured_validation}
## Frozen Artifact Contract

Consumes:
{lines((node.get("artifact_contract") or {}).get("consumes"))}

Produces:
{lines((node.get("artifact_contract") or {}).get("produces"))}

## Frozen Evaluation Binding

{lines(node.get("evaluation_binding"))}

## Requirement Trace

{lines(node.get("requirement_ids"))}

## Capability Capsule Binding

{lines(node.get("capsule_binding"))}

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


# Product-env allowlist embedded into generated worker runners (P2 smoke
# 20260707T180639Z): pool workers execute in tmux windows whose environment
# comes from the tmux SERVER, so flag-gated product behavior (gate-ledger route
# records, product mode, provider pinning) silently degrades unless the runner
# script carries a generation-time snapshot of these values itself.
_PRODUCT_ENV_ALLOWLIST = (
    "SOLAR_GATE_LEDGER",
    "SOLAR_PRODUCT_MODE",
    "SOLAR_WORKFLOW_ROUTER",
    "SOLAR_MULTI_TASK_DEFAULT_PROVIDERS",
    "SOLAR_PM_DEFAULT_PROVIDERS",
    "HARNESS_SPRINTS_DIR",
)


def _product_env_exports() -> str:
    lines: list[str] = []
    for var in _PRODUCT_ENV_ALLOWLIST:
        value = os.environ.get(var)
        if value is not None and str(value).strip() != "":
            lines.append(f"export {var}={shlex.quote(str(value))}")
    return "\n".join(lines)


def _product_env_prefix() -> str:
    """Inline VAR=value prefix for tmux window commands.

    tmux windows inherit the tmux SERVER's environment, not the spawning
    process's — on a machine with a long-lived server, flag-gated product
    behavior silently degrades in anything tmux hosts (and in anything those
    processes auto-kick, e.g. operatord). Prefixing the command itself makes
    propagation independent of server state (P2 smoke 20260707T190540Z:
    second consecutive zero-route-record run)."""
    parts: list[str] = []
    for var in _PRODUCT_ENV_ALLOWLIST:
        value = os.environ.get(var)
        if value is not None and str(value).strip() != "":
            parts.append(f"{var}={shlex.quote(str(value))}")
    return (" ".join(parts) + " ") if parts else ""


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
    window_name = str(payload.get("window") or "")
    window_target = str(payload.get("window_target") or "")
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
    product_env_exports = _product_env_exports()
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
HANDOFF={shlex.quote(str(handoff))}
HARNESS={shlex.quote(str(harness))}
WORK_DIR={shlex.quote(work_dir)}
MT_SESSION={shlex.quote(SESSION)}
WINDOW_NAME={shlex.quote(window_name)}
WINDOW_TARGET={shlex.quote(window_target)}
AUTO_CLOSE_TERMINAL_WINDOWS={"1" if AUTO_CLOSE_TERMINAL_WINDOWS else "0"}
AUTO_CLOSE_DELAY_SEC={shlex.quote(str(AUTO_CLOSE_DELAY_SEC))}
export TASK_DIR STATUS_FILE DISPATCH_FILE OUTPUT_LOG RUN_STARTED_MARKER HARNESS_DIR HARNESS_BIN SPRINTS_DIR GRAPH NODE_ID SID ROLE PROFILE BACKEND MODEL PROVIDER CAPABILITY_STATUS HANDOFF HARNESS WORK_DIR MT_SESSION WINDOW_NAME WINDOW_TARGET AUTO_CLOSE_TERMINAL_WINDOWS AUTO_CLOSE_DELAY_SEC
export PATH="$HARNESS_BIN:$PATH"
export SOLAR_SAFE_FIND_ROOT="$WORK_DIR"
{product_env_exports}

pane_title() {{
  local title="$1"
  if [[ -n "${{TMUX:-}}" ]]; then
    tmux select-pane -T "$title" >/dev/null 2>&1 || true
  fi
}}

auto_close_window() {{
  local reason="${{1:-terminal}}"
  [[ "$AUTO_CLOSE_TERMINAL_WINDOWS" == "1" ]] || return 0
  [[ -n "$WINDOW_NAME" || -n "$WINDOW_TARGET" ]] || return 0
  [[ -n "${{TMUX:-}}" ]] || return 0
  (
    sleep "$AUTO_CLOSE_DELAY_SEC"
    if [[ -n "$WINDOW_TARGET" ]]; then
      tmux kill-window -t "$WINDOW_TARGET" >/dev/null 2>&1 || true
    else
      tmux kill-window -t "${{MT_SESSION}}:${{WINDOW_NAME}}" >/dev/null 2>&1 || true
    fi
  ) >/dev/null 2>&1 &
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
  "$HARNESS" graph-scheduler mark --graph "$GRAPH" --node "$NODE_ID" --status reviewing --in-place >> "$OUTPUT_LOG" 2>&1 || true
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
auto_close_window "terminal"
exit "$rc"
"""
    runner.write_text(script, encoding="utf-8")
    runner.chmod(0o755)
    return runner


def tmux_start(
    window: str,
    runner: Path,
    cwd: Path,
    dry_run: bool = False,
    reuse: bool = False,
    reuse_target: str = "",
) -> None:
    if dry_run:
        return
    cmd = f"{_product_env_prefix()}bash {shlex.quote(str(runner))}; exec ${{SHELL:-/bin/zsh}}"
    reuse_window_target = reuse_target or f"{SESSION}:{window}"
    previous_active_target = ""
    if reuse:
        for info in tmux_window_records():
            candidate = str(info.get("target") or "")
            if str(info.get("active") or "") == "1" and candidate != reuse_window_target:
                previous_active_target = candidate
                break
    if subprocess.run(["tmux", "has-session", "-t", SESSION], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        if reuse:
            subprocess.check_call([
                "tmux", "respawn-window", "-k", "-t",
                reuse_window_target, "-c", str(cwd), cmd,
            ])
            # tmux makes a respawned window current even when it was selected
            # only as an idle pool member. Restore the previous current window
            # so background dispatch never steals an attached user's focus.
            if previous_active_target:
                subprocess.run(
                    ["tmux", "select-window", "-t", previous_active_target],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        else:
            subprocess.check_call(["tmux", "new-window", "-d", "-t", SESSION, "-n", window, "-c", str(cwd), cmd])
    else:
        subprocess.check_call(["tmux", "new-session", "-d", "-s", SESSION, "-n", window, "-c", str(cwd), cmd])
    target = reuse_window_target if reuse else f"{SESSION}:{window}"
    subprocess.run(["tmux", "set-window-option", "-t", target, "pane-border-status", "bottom"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(
        ["tmux", "set-window-option", "-t", target, "pane-border-format", "#[fg=cyan] #T #[default]"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def prepare_tmux_window(preferred_window: str, dry_run: bool = False) -> tuple[str, bool, str, str]:
    """Select a reusable shell and prune only excess idle windows."""
    if dry_run:
        return preferred_window, False, "", ""
    tasks = list_task_rows()
    windows = tmux_window_records()
    actual_window, reused, reused_task_id, reused_window_target = select_reusable_tmux_window(
        preferred_window,
        tasks=tasks,
        windows=windows,
    )
    prune_idle_tmux_windows(
        target_keep=IDLE_WINDOW_POOL_TARGET,
        dry_run=False,
        keep_windows={reused_window_target} if reused and reused_window_target else set(),
        tasks=tasks,
        windows=windows,
    )
    return actual_window, reused, reused_task_id, reused_window_target


def _operator_submit_eligible(profile: dict[str, Any], dry_run: bool = False) -> bool:
    operator_id = str(profile.get("operator_id") or "").strip()
    return (
        OPERATORD_SUBMIT_ENABLED
        and not dry_run
        and operator_id not in {"", "N/A"}
    )


def _operator_submit_rejection_reason(error: Exception) -> str:
    """Classify an operatord refusal that must never launch duplicate work."""
    reason = str(getattr(error, "reason", "") or "").strip()
    if reason in {"operator_busy", "operator_unavailable"}:
        return reason
    text = str(error or "").strip().lower()
    if any(
        marker in text
        for marker in (
            "admission_failed:",
            "unknown operator",
            "task envelope missing required keys",
            "persona",
        )
    ):
        return "operator_admission_failed"
    if "duplicate active lease" in text:
        return "operator_busy"
    if "not dispatchable" in text and any(
        marker in text
        for marker in (
            "state=leased",
            "state=running",
            "state=draining",
        )
    ):
        return "operator_busy"
    if "not dispatchable" in text and any(
        marker in text
        for marker in (
            "state=disabled",
            "state=cooldown",
            "state=quota_exhausted",
            "state=auth_expired",
        )
    ):
        return "operator_unavailable"
    return ""


def _requires_leased_operator_dispatch(graph: dict[str, Any], node: dict[str, Any]) -> bool:
    """Return whether this node is forbidden from using the legacy tmux path.

    A scheduler runtime projection and a node carrying the planner's frozen
    physical-candidate list both require dispatch through operatord so lease
    ownership remains authoritative.  An unclassified submit failure must not
    silently bypass that contract by launching an unleased legacy worker.
    """
    return (
        graph.get("schema_version") == "solar.scheduler_runtime_projection.v1"
        or isinstance(node.get("physical_candidates"), list)
    )


def _profile_attribution_operator_id(profile: dict[str, Any]) -> str:
    """Return a durable operator label for status/runstate without changing submit routing.

    Physical-operator dispatch requires a concrete profile["operator_id"]. Command-backed
    multi-task profiles such as codex-evaluator intentionally lack one, so they should stay on
    the legacy command/tmux path. Still, recording "N/A" erases provider proof for successful
    command-backed runs. Use the profile name as a stable attribution label only for command
    profiles; _operator_submit_eligible continues to use the raw operator_id.
    """
    operator_id = str(profile.get("operator_id") or "").strip()
    if operator_id and operator_id != "N/A":
        return operator_id
    if str(profile.get("backend") or "").strip().lower() == "command":
        name = str(profile.get("name") or "").strip()
        if name:
            return name
    return "N/A"


def _profile_dispatch_mode(profile: dict[str, Any]) -> str:
    backend = str(profile.get("backend") or "").strip().lower()
    if backend == "command":
        return "multi_task_command"
    return "multi_task_tmux"


def _operator_result_path(operator_id: str, dispatch_id: str) -> Path:
    return HARNESS_DIR / "run" / "operator-results" / operator_id / dispatch_id / "result.json"


def _build_operator_envelope(
    dispatch_id: str,
    sid: str,
    node_id: str,
    node: dict[str, Any],
    profile: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task_id": dispatch_id,
        "sprint_id": sid,
        "node_id": node_id,
        "operator_id": str(profile.get("operator_id") or "").strip(),
        "task_type": str(node.get("dispatch_task_type") or profile.get("role") or "builder"),
        "objective": str(node.get("goal") or node.get("title") or node_id),
        **({"retrieval_contract": deepcopy(node["retrieval_contract"])} if node.get("retrieval_contract") else {}),
        "command": profile.get("command"),
        "backend": profile.get("backend"),
        "model": profile.get("model"),
        "profile": profile.get("name"),
        "write_scope": payload.get("write_scope") or [],
        "handoff_path": payload.get("handoff"),
        "dispatch_file": payload.get("dispatch_file"),
        "graph_path": payload.get("graph"),
        "work_dir": payload.get("work_dir"),
        "approval_mode": profile.get("approval_mode"),
        "requirement_ids": deepcopy(node.get("requirement_ids") or []),
        "capsule_binding": deepcopy(node.get("capsule_binding") or {}),
        "capability_capsule_id": node.get("capability_capsule_id"),
        "artifact_contract": deepcopy(node.get("artifact_contract") or {}),
        "artifact_routes": deepcopy(node.get("artifact_routes") or {}),
        "evaluation_binding": deepcopy(node.get("evaluation_binding") or {}),
        "resource_requirements": deepcopy(node.get("resource_requirements") or {}),
        **({"execution_authority": deepcopy(node["execution_authority"])} if "execution_authority" in node else {}),
        "effects": deepcopy(node.get("effects") or []),
        "physical_candidate_rank": profile.get("scheduler_candidate_rank"),
        "runtime_binding": deepcopy(profile.get("runtime_binding") or {}),
    }


def _poll_operator_result(result_path: Path, timeout_sec: float, interval_sec: float) -> dict[str, Any] | None:
    deadline = time.time() + max(0.0, timeout_sec)
    interval = max(0.01, interval_sec)
    while time.time() <= deadline:
        if result_path.exists():
            try:
                return json.loads(result_path.read_text(encoding="utf-8"))
            except Exception:
                return None
        time.sleep(interval)
    return None


def _record_node_attribution(sid: str, node_id: str, payload: dict[str, Any], task_dir: Path, phase: str) -> None:
    """Persist a durable, node-keyed worker-attribution record next to the sprint.

    The same facts already live in RUN_DIR/<dispatch_id>/status.json, but that is keyed by dispatch_id
    and reaped after SOLAR_MULTI_TASK_REAP_TTL_MIN. This co-locates a node-keyed copy with the sprint so
    "node N1 ran on backend/vendor/model/operator X (exit_code Y)" stays provable after reaping. Best-effort."""
    try:
        import node_runstate

        runstate_root = Path(str(payload.get("node_runstate_root") or SPRINTS_DIR))
        node_runstate.record(runstate_root, sid, node_id, "attribution", {
            "dispatch_id": payload.get("id"),
            "backend": payload.get("backend"),
            "vendor": payload.get("operator_vendor") or payload.get("provider"),
            "model": payload.get("operator_model") or payload.get("model"),
            "provider": payload.get("provider"),
            "operator_id": payload.get("operator_id"),
            "profile": payload.get("profile"),
            "role": payload.get("role"),
            "dispatch_mode": payload.get("dispatch_mode") or payload.get("submit_mode"),
            "submit_mode": payload.get("submit_mode"),
            "work_dir": payload.get("work_dir"),
            "status_path": str(status_path(task_dir)),
            "phase": phase or payload.get("status"),
            "status": payload.get("status"),
            "exit_code": payload.get("exit_code"),
            "created_at": payload.get("created_at"),
        })
    except Exception:
        pass


def _plan_validator_env_on() -> bool:
    # G4 default-on: the validator is the runtime default; explicit 0 kills it.
    return str(os.environ.get("SOLAR_PLAN_VALIDATOR") or "").strip().lower() not in {"0", "false", "no", "off"}


def _plan_validator_launch_refusal(
    graph: dict[str, Any],
    graph_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Validator dispatch guard shared by schedule_once and launch_node.

    launch_node() is a public dispatch surface: a direct caller skips the
    schedule_once guard, so the check must run again BEFORE any dispatch/
    status/runstate write (G2b fix-round 2 finding 1). Returns a refusal
    record ({reason, errors}) or None when dispatch may proceed."""
    if graph.get("schema_version") == "solar.scheduler_runtime_projection.v1":
        try:
            import scheduler_input

            verdict = scheduler_input.verify_runtime_projection(graph, graph_path=graph_path)
        except Exception as guard_exc:
            verdict = {"ok": False, "errors": [f"SCHEDULER_INPUT_UNCHECKABLE:{type(guard_exc).__name__}"]}
        if verdict.get("ok"):
            return None
        return {"reason": "scheduler_input_dispatch_refused", "errors": verdict.get("errors") or []}
    try:
        import plan_validator  # type: ignore

        plan_guard = plan_validator.check_planner_graph_dispatchable(
            graph,
            sprints_dir=SPRINTS_DIR,
            sid=str(graph.get("sprint_id") or ""),
        )
    except Exception as guard_exc:
        if _plan_validator_env_on():
            return {
                "reason": "plan_validator_dispatch_refused",
                "errors": [f"PLAN_VALIDATOR_UNCHECKABLE:{type(guard_exc).__name__}"],
            }
        return None
    if plan_guard.get("ok"):
        return None
    try:
        # G3 fix: a PASS-certified graph refused for hash mismatch is
        # unrecoverable at dispatch time — terminalize the sprint truthfully
        # instead of re-refusing every scheduler tick (helper is scoped to
        # PLAN_CERTIFICATE_HASH_MISMATCH; uncertified refusals untouched).
        plan_validator.record_certificate_mismatch_refusal(
            SPRINTS_DIR, graph, plan_guard.get("errors")
        )
    except Exception:
        pass
    errors = []
    for error in plan_guard.get("errors") or []:
        if isinstance(error, dict):
            errors.append(f"{error.get('code')}:{error.get('node_id', '?')}")
        else:
            errors.append(str(error))
    return {"reason": "plan_validator_dispatch_refused", "errors": errors}


def _scheduler_preflight_failure_record(
    graph_path: Path,
    graph: dict[str, Any],
    *,
    reason: str,
    node_id: str = "",
    error: str = "",
    errors: list[Any] | None = None,
) -> str:
    """Persist one scheduler refusal beside the runtime graph for GUI pickup."""
    sid = sprint_id_for(graph, graph_path)
    identity = str(node_id or "graph")
    safe_identity = re.sub(r"[^A-Za-z0-9_.-]+", "-", identity).strip("-.")[:32] or "graph"
    suffix = uuid.uuid5(uuid.NAMESPACE_URL, f"{graph_path.resolve()}:{identity}").hex[:10]
    record_path = graph_path.parent / "scheduler-records" / "preflight" / f"{safe_identity}-{suffix}.json"
    payload = {
        "schema_version": "solar.scheduler_preflight_failure.v1",
        "artifact_role": "mutable_scheduler_failure_evidence",
        "status": "blocked" if not node_id else "queued",
        "reason": str(reason),
        "error": str(error),
        "errors": [str(item) for item in (errors or [])],
        "sprint_id": sid,
        "node_id": str(node_id),
        "graph_path": str(graph_path.resolve()),
        "recorded_at": now_iso(),
    }
    json_write(record_path, payload)
    return str(record_path)


def _persist_frozen_preflight_queue(
    graph_path: Path,
    graph: dict[str, Any],
    node: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    """Keep a temporarily unavailable frozen node queued with durable evidence."""
    node_id = str(node.get("id") or "")
    detail = str(exc) or type(exc).__name__
    blocking_reason = f"frozen_scheduler_preflight_unavailable:{detail}"
    authoritative = next(
        (
            item for item in graph.get("nodes") or []
            if isinstance(item, dict) and str(item.get("id") or "") == node_id
        ),
        None,
    )
    observations = deepcopy(node.get("scheduler_candidate_observations") or [])
    if isinstance(authoritative, dict):
        authoritative["blocking_reason"] = blocking_reason
        if observations:
            authoritative["scheduler_candidate_observations"] = observations
        set_node_status(graph, node_id, "queued")
        result = graph.setdefault("node_results", {}).setdefault(node_id, {})
        result["blocking_reason"] = blocking_reason
        if observations:
            result["scheduler_candidate_observations"] = observations
        save_graph(graph_path, graph)
    failure_record = _scheduler_preflight_failure_record(
        graph_path,
        graph,
        reason="frozen_scheduler_preflight_unavailable",
        node_id=node_id,
        error=detail,
    )
    return {
        "reason": "frozen_scheduler_preflight_unavailable",
        "error": detail,
        "blocking_reason": blocking_reason,
        "failure_record": failure_record,
    }


def launch_node(graph_path: Path, graph: dict[str, Any], node: dict[str, Any], args: argparse.Namespace,
                dry_run: bool = False) -> dict[str, Any]:
    refusal = _plan_validator_launch_refusal(graph, graph_path)
    if refusal is not None:
        refusal = dict(refusal)
        refusal["failure_record"] = _scheduler_preflight_failure_record(
            graph_path,
            graph,
            reason=str(refusal.get("reason") or "scheduler_input_dispatch_refused"),
            node_id=str(node.get("id") or ""),
            errors=list(refusal.get("errors") or []),
        )
        return {
            "status": "plan_validator_dispatch_refused",
            "graph": str(graph_path),
            "sprint_id": sprint_id_for(graph, graph_path),
            "node_id": str(node.get("id") or ""),
            **refusal,
        }
    sid = sprint_id_for(graph, graph_path)
    node_id = str(node.get("id") or "")
    authoritative_node = next(
        (
            candidate
            for candidate in (graph.get("nodes") or [])
            if isinstance(candidate, dict) and str(candidate.get("id") or "") == node_id
        ),
        None,
    )
    if authoritative_node is None:
        raise ValueError(f"unknown graph node: {node_id}")
    node = authoritative_node
    profile = select_profile(node, getattr(args, "profile", "") or "", getattr(args, "model", "") or "", getattr(args, "backend", "") or "")
    capability = capability_for_profile(profile)
    dispatch_id = task_id(sid, node_id)
    requested_window = short_window(f"{dispatch_id}-{profile.get('role')}-{node_id}")
    window = requested_window
    task_dir = RUN_DIR / dispatch_id
    runtime_root = (
        Path(graph_path).parent
        if graph.get("schema_version") == "solar.scheduler_runtime_projection.v1"
        else SPRINTS_DIR
    )
    handoff = runtime_root / f"{sid}.{node_id}-handoff.md"
    task_dir.mkdir(parents=True, exist_ok=True)
    # Default the agent's working directory to a clean per-sprint workspace so produced
    # deliverables land predictably (and the dashboard's SPRINTS_DIR scan finds them),
    # instead of wherever multi-task happened to be launched (os.getcwd()).
    sprint_workdir = Path(str(graph.get("runtime_work_dir") or (SPRINTS_DIR / sid / "workdir")))
    sprint_workdir.mkdir(parents=True, exist_ok=True)

    dispatch = build_dispatch_text(graph_path, graph, node, dispatch_id, window, profile)
    (task_dir / "dispatch.md").write_text(dispatch, encoding="utf-8")
    payload = {
        "id": dispatch_id,
        "status": "dry_run" if dry_run else "dispatched",
        "session": SESSION,
        "window": window,
        "window_target": f"{SESSION}:{window}",
        "requested_window": requested_window,
        "window_reused": False,
        "window_reused_from_task": "N/A",
        "profile": profile.get("name"),
        "role": profile.get("role"),
        "persona": profile.get("persona"),
        "backend": profile.get("backend"),
        "model": profile.get("model"),
        "command": profile.get("command"),
        "provider": capability.get("provider"),
        "capability_status": capability.get("status"),
        "approval_mode": profile.get("approval_mode"),
        "operator_id": _profile_attribution_operator_id(profile),
        "operator_vendor": profile.get("operator_vendor") or capability.get("provider") or "N/A",
        "operator_model": profile.get("operator_model") or profile.get("model") or "N/A",
        "operator_pane": profile.get("operator_pane") or "N/A",
        "operator_quota_refresh_at": profile.get("operator_quota_refresh_at") or "N/A",
        "operator_fallback_reason": profile.get("operator_fallback_reason") or "",
        "dispatch_mode": _profile_dispatch_mode(profile),
        "submit_mode": "",
        "quota_fallback_from": profile.get("quota_fallback_from") or node.get("quota_fallback_from") or "",
        "quota_fallback_reason": profile.get("quota_fallback_reason") or node.get("quota_fallback_reason") or "",
        "graph": str(graph_path),
        "node_runstate_root": str(runtime_root),
        "sprint_id": sid,
        "node_id": node_id,
        "title": str(node.get("goal") or node.get("title") or node_id)[:120],
        "write_scope": node.get("write_scope") or [],
        "handoff": str(handoff),
        "dispatch_file": str(task_dir / "dispatch.md"),
        "work_dir": str(os.environ.get("SOLAR_MULTI_TASK_WORK_DIR") or sprint_workdir),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "exit_code": None,
    }
    json_write(status_path(task_dir), payload)
    _record_node_attribution(sid, node_id, payload, task_dir, "dispatched")

    if _operator_submit_eligible(profile, dry_run=dry_run):
        try:
            import operator_runtime

            envelope = _build_operator_envelope(dispatch_id, sid, node_id, node, profile, payload)
            submit_result = operator_runtime.submit(envelope)
            operator_id = str(submit_result.get("operator_id") or envelope["operator_id"])
            result_path = _operator_result_path(operator_id, dispatch_id)
            payload.update(submit_result)
            payload["submit_mode"] = "operatord"
            payload["dispatch_mode"] = "operatord"
            payload["result_path"] = str(result_path)
            payload["updated_at"] = now_iso()
            activate_execution_attempt(
                node,
                task_id=dispatch_id,
                dispatch_id=dispatch_id,
                operator_id=operator_id,
                source="multi_task_operatord",
                logical_role=str(profile.get("role") or "builder"),
                status=str(payload.get("status") or "submitted"),
                requires_operator_result=True,
                sprint_id=sid,
                node_id=node_id,
                result_path=str(result_path),
                now=str(payload.get("updated_at") or ""),
            )
            if graph.get("schema_version") == "solar.scheduler_runtime_projection.v1":
                import scheduler_input

                payload.update(
                    scheduler_input.write_dispatch_records(
                        Path(graph_path).parent / "scheduler-records",
                        graph=graph,
                        node=node,
                        profile=profile,
                        submit_result=submit_result,
                        dispatch_id=dispatch_id,
                    )
                )
            json_write(status_path(task_dir), payload)
            set_node_status(graph, node_id, "dispatched", pane=f"operator:{operator_id}", dispatch_id=dispatch_id)
            save_graph(graph_path, graph)
            set_last_launch()

            if OPERATORD_RESULT_TIMEOUT_SEC > 0:
                result = _poll_operator_result(
                    result_path,
                    OPERATORD_RESULT_TIMEOUT_SEC,
                    OPERATORD_RESULT_POLL_INTERVAL_SEC,
                )
                if result is None:
                    # The result can land between the poller's final read and
                    # the timeout write.  Re-read and correlate the exact
                    # task identity so a stale timeout never overwrites a
                    # durable terminal result.
                    result = correlated_terminal_result(
                        {**payload, "result_path": str(result_path)}
                    )
                if result is None:
                    payload["status"] = "result_timeout"
                    _record_operator_runtime_failure(operator_id, "result_timeout")
                else:
                    payload["status"] = str(result.get("status") or "completed")
                    payload["exit_code"] = result.get("exit_code")
                    payload["operator_result"] = result
                    if str(payload["status"]).lower() in {"failed", "error"} or (
                        result.get("exit_code") not in (0, None)
                    ):
                        _record_operator_runtime_failure(operator_id, f"status={payload['status']} exit={result.get('exit_code')}")
                payload["updated_at"] = now_iso()
                json_write(status_path(task_dir), payload)
                _record_node_attribution(sid, node_id, payload, task_dir, "completed")
            return payload
        except (RuntimeError, ValueError) as exc:
            rejection_reason = _operator_submit_rejection_reason(exc)
            if rejection_reason:
                payload["status"] = "submit_rejected"
                payload["submit_mode"] = "operatord"
                payload["dispatch_mode"] = "operatord"
                payload["operator_submit_reason"] = rejection_reason
                payload["operator_submit_error"] = str(exc)
                payload["updated_at"] = now_iso()
                json_write(status_path(task_dir), payload)
                if rejection_reason == "operator_admission_failed":
                    node["blocking_reason"] = str(exc)
                    node["next_action"] = "repair scheduler input or capsule admission contract"
                    set_node_status(graph, node_id, "needs_human_review")
                    save_graph(graph_path, graph)
                _record_node_attribution(
                    sid,
                    node_id,
                    payload,
                    task_dir,
                    "submit_rejected",
                )
                return payload
            if _requires_leased_operator_dispatch(graph, node):
                # Frozen scheduler assignments may only execute under an
                # operatord lease.  The exception was not a classified
                # busy/unavailable race, so retrying another candidate is not
                # justified and legacy tmux would create an unleased dispatch.
                blocking_reason = (
                    f"operator_submit_failed:{type(exc).__name__}:{str(exc) or 'no detail'}"
                )
                next_action = "inspect operator submit configuration and retry after repair"
                payload["status"] = "submit_rejected"
                payload["submit_mode"] = "operatord"
                payload["dispatch_mode"] = "operatord"
                payload["operator_submit_reason"] = "operator_submit_failed"
                payload["operator_submit_error"] = str(exc)
                payload["blocking_reason"] = blocking_reason
                payload["next_action"] = next_action
                payload["updated_at"] = now_iso()
                json_write(status_path(task_dir), payload)
                node["blocking_reason"] = blocking_reason
                node["next_action"] = next_action
                enter_node_human_review(
                    graph,
                    node_id,
                    reason=blocking_reason,
                    next_action=next_action,
                    writer="multi_task_runner.operator_submit",
                )
                node_result = graph.setdefault("node_results", {}).setdefault(node_id, {})
                node_result.update({
                    "blocking_reason": blocking_reason,
                    "next_action": next_action,
                    "operator_submit_reason": "operator_submit_failed",
                    "operator_submit_error": str(exc),
                })
                save_graph(graph_path, graph)
                _record_node_attribution(
                    sid,
                    node_id,
                    payload,
                    task_dir,
                    "submit_rejected",
                )
                return payload
            payload["operator_submit_fallback"] = "legacy"
            payload["submit_mode"] = ""
            payload["dispatch_mode"] = _profile_dispatch_mode(profile)
            payload["operator_submit_error"] = str(exc)
            payload["updated_at"] = now_iso()
            json_write(status_path(task_dir), payload)

    # Tmux lifecycle applies only to the legacy pane path. Operatord tasks do
    # not own a tmux window, so selecting/pruning one before submit would be an
    # unrelated side effect. If operatord falls back, choose a safe shell now
    # and rebuild the dispatch text with the actual window identity.
    window, reused_window, reused_task_id, reused_window_target = prepare_tmux_window(
        requested_window,
        dry_run=dry_run,
    )
    if window != requested_window:
        dispatch = build_dispatch_text(graph_path, graph, node, dispatch_id, window, profile)
        (task_dir / "dispatch.md").write_text(dispatch, encoding="utf-8")
    payload.update({
        "window": window,
        "window_target": reused_window_target or f"{SESSION}:{window}",
        "window_reused": reused_window,
        "window_reused_from_task": reused_task_id or "N/A",
        "updated_at": now_iso(),
    })
    json_write(status_path(task_dir), payload)
    runner = runner_script(task_dir, payload)

    if not dry_run:
        try:
            tmux_start(
                window,
                runner,
                Path.cwd(),
                reuse=reused_window,
                reuse_target=reused_window_target,
            )
        except Exception as exc:
            payload["status"] = "failed_launch"
            payload["updated_at"] = now_iso()
            payload["error"] = str(exc)
            json_write(status_path(task_dir), payload)
            (task_dir / "output.log").write_text(f"ERROR: tmux launch failed: {exc}\n", encoding="utf-8")
            return payload
        activate_execution_attempt(
            node,
            task_id=dispatch_id,
            dispatch_id=dispatch_id,
            operator_id=str(payload.get("operator_id") or ""),
            source="multi_task_tmux",
            logical_role=str(profile.get("role") or "builder"),
            status="dispatched",
            requires_operator_result=False,
            sprint_id=sid,
            node_id=node_id,
            now=str(payload.get("updated_at") or ""),
        )
        set_node_status(graph, node_id, "dispatched", pane=f"multi-task:{window}", dispatch_id=dispatch_id)
        save_graph(graph_path, graph)
        set_last_launch()

    return payload


# --- Operator runtime-failure cooldown -------------------------------------------------------------
# operator_dispatchable() only checks config/quota/auth, not whether the backend actually runs. An
# operator whose CLI fails at runtime (e.g. an unconfigured gemini/antigravity command -> exit 1) would
# otherwise keep getting selected over a working Claude builder. Record runtime failures and deprioritize
# recently-failed operators in selection (cooldown auto-expires; never a hard exclude).
OPERATOR_FAILURE_LEDGER_PATH = Path(os.environ.get("SOLAR_MULTI_TASK_OPERATOR_FAILURE_LEDGER", RUN_DIR / "operator-failures.json"))
OPERATOR_FAILURE_COOLDOWN_SEC = int(os.environ.get("SOLAR_MULTI_TASK_OPERATOR_FAILURE_COOLDOWN_SEC", "900") or "900")


def _read_operator_failures() -> dict[str, Any]:
    try:
        data = json.loads(OPERATOR_FAILURE_LEDGER_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _record_operator_runtime_failure(operator_id: str, reason: str = "") -> None:
    op = str(operator_id or "").strip()
    if not op or op == "N/A":
        return
    try:
        data = _read_operator_failures()
        prior = data.get(op) if isinstance(data.get(op), dict) else {}
        data[op] = {"at": now_iso(), "reason": str(reason)[:200], "count": int(prior.get("count") or 0) + 1}
        json_write(OPERATOR_FAILURE_LEDGER_PATH, data)
    except Exception:
        pass


def operator_in_failure_cooldown(operator_id: str) -> bool:
    if OPERATOR_FAILURE_COOLDOWN_SEC <= 0:
        return False
    op = str(operator_id or "").strip()
    if not op:
        return False
    rec = _read_operator_failures().get(op)
    if not isinstance(rec, dict):
        return False
    ts = parse_iso(str(rec.get("at") or ""))
    if ts is None:
        return False
    return (time.time() - ts) < OPERATOR_FAILURE_COOLDOWN_SEC


# --- Auto-advance: make a multi-task DAG self-complete build -> eval -> verdict -> next node ---------
AUTO_ADVANCE_ENABLED = os.environ.get("SOLAR_MULTI_TASK_AUTO_ADVANCE", "1").strip().lower() not in {"0", "false", "off", "no"}
# Consecutive no-progress ticks (no active task, nothing ready, not all-terminal, no eval/reconcile
# progress) before the loop exits cleanly instead of spinning on a FAIL/needs_human_review deadlock.
STUCK_EXIT_TICKS = int(os.environ.get("SOLAR_MULTI_TASK_STUCK_EXIT_TICKS", "3") or "3")


def _advance_graph(graph_path: Path | str) -> dict[str, Any]:
    """Self-advance one multi-task DAG by a step the build scheduler does NOT do: dispatch evals for
    `reviewing` nodes (through the operator pool) and reconcile results (apply eval verdicts ->
    passed/failed, reset failed builds to pending + cooldown their operator, escalate stuck evals).
    Dispatch of newly-ready downstream nodes stays with schedule_once. Best-effort; never raises.
    Does NOT weaken gates -- it just runs the same dispatch_node_evals + reconcile the coordinator would."""
    summary: dict[str, Any] = {"graph": str(graph_path), "eval_dispatched": [], "reconciled": [], "terminalized": []}
    try:
        # Auto-advance evaluates multi-task DAG nodes that finish in `reviewing` with no cockpit
        # evaluator pane; route those evals through the operatord evaluator pool (builder-safe flag).
        os.environ.setdefault("SOLAR_GRAPH_EVAL_OPERATOR_POOL", "1")
        import graph_node_dispatcher as gnd

        try:
            ev = gnd.dispatch_node_evals(str(graph_path))
            summary["eval_dispatched"] = [str(x.get("node")) for x in (ev.get("dispatched") or [])]
            summary["terminalized"] = ev.get("terminalized") or []
        except Exception as exc:
            summary["eval_error"] = f"{type(exc).__name__}: {exc}"
        try:
            graph = gnd.load_graph(str(graph_path))
            reconciled = gnd._reconcile_existing_dispatches(graph, str(graph_path))
            if reconciled:
                gnd.save_graph(str(graph_path), graph)
                summary["reconciled"] = [
                    {"node": r.get("node"), "status": r.get("status"), "reason": r.get("reason")}
                    for r in reconciled
                ]
                # Cooldown operators whose build closeout failed, so re-dispatch avoids them.
                for r in reconciled:
                    closeout = r.get("last_operator_closeout_failure") if isinstance(r, dict) else None
                    op_id = ""
                    if isinstance(closeout, dict):
                        op_id = str(closeout.get("operator_id") or "")
                    if op_id:
                        _record_operator_runtime_failure(op_id, str(r.get("reason") or "closeout"))
            # Projection sync must NOT be gated on `if reconciled` — when a
            # concurrent loop (the coordinator's dispatch-ready tick) consumes
            # the final node's eval first, this reconcile is empty and the
            # parent projection would never converge (P3 run 4: status.json
            # froze at active with a fully-passed graph until wrapper timeout).
            # The sync is idempotent; run it every advance tick.
            try:
                import graph_scheduler

                summary["status_sync"] = graph_scheduler.sync_status_cache_from_graph(
                    graph,
                    str(graph_path),
                    actor="multi_task_runner",
                    event="multi_task_auto_advance_reconciled",
                )
            except Exception as sync_exc:
                summary["status_sync_error"] = f"{type(sync_exc).__name__}: {sync_exc}"
        except Exception as exc:
            summary["reconcile_error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
    return summary


def _advance_graphs(graph_arg: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for graph_path in graph_files(graph_arg):
        out.append(_advance_graph(graph_path))
    return out


def schedule_once(args: argparse.Namespace) -> dict[str, Any]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    max_workers = effective_scheduler_max_workers(max(1, int(args.max_workers)))
    # Self-advance reviewing nodes (eval dispatch + verdict reconcile) BEFORE dispatching builds, so a
    # node that just passed unblocks its downstream in the same tick. Gated + best-effort.
    advance: list[dict[str, Any]] = []
    if AUTO_ADVANCE_ENABLED and getattr(args, "graph", None):
        advance = _advance_graphs(getattr(args, "graph", []))
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
            "advance": advance,
        }

    for graph_path in graph_files(args.graph):
        if slots <= 0 and not args.dry_run:
            break
        try:
            graph = load_graph(graph_path)
            summaries.append(status_summary_for_graph(graph_path))
            refusal = _plan_validator_launch_refusal(graph, graph_path)
            if refusal is not None:
                refusal = dict(refusal)
                refusal["failure_record"] = _scheduler_preflight_failure_record(
                    graph_path,
                    graph,
                    reason=str(refusal.get("reason") or "scheduler_input_dispatch_refused"),
                    errors=list(refusal.get("errors") or []),
                )
                skipped.append({"graph": str(graph_path), **refusal})
                continue
            candidates = sorted(
                ready_nodes(graph),
                key=lambda item: (-int(item.get("priority") or 0), str(item.get("id") or "")),
            )
        except Exception as exc:
            skipped.append({"graph": str(graph_path), "reason": "graph_error", "error": str(exc)})
            continue
        sid = sprint_id_for(graph, graph_path)
        for node in candidates:
            if slots <= 0 and not args.dry_run:
                break
            already_active = active_task_for_node(sid, str(node.get("id") or ""), active_rows)
            if already_active:
                skipped.append({
                    "graph": str(graph_path),
                    "node": node.get("id"),
                    "reason": "node_already_active",
                    "task": already_active.get("id"),
                    "status": already_active.get("effective_status") or already_active.get("status"),
                })
                continue
            if scope_conflicts_with_active(node):
                skipped.append({"graph": str(graph_path), "node": node.get("id"), "reason": "write_scope_conflict_with_active"})
                continue
            try:
                profile = select_profile(node, getattr(args, "profile", "") or "", getattr(args, "model", "") or "", getattr(args, "backend", "") or "")
                capability = capability_for_profile(profile)
            except Exception as exc:
                if _requires_leased_operator_dispatch(graph, node):
                    skipped.append({
                        "graph": str(graph_path),
                        "node": node.get("id"),
                        **_persist_frozen_preflight_queue(graph_path, graph, node, exc),
                    })
                else:
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
        "advance": advance,
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
        _clip_display(str(t.get("work", "N/A")), 8),
        _clip_display(str(t.get("effective_status") or t.get("status", "N/A")), 18),
        _clip_display(str(t.get("data_class", "N/A")), 12),
        _clip_display(str(t.get("pane_type", "N/A")), 22),
        _clip_display(str(t.get("operator_id") or "N/A"), 18),
        _clip_display(str(t.get("operator_vendor") or t.get("provider") or "N/A"), 12),
        _clip_display(str(t.get("operator_pane") or "N/A"), 16),
        _clip_display(
            _display_tmux_status(
                str(t.get("effective_status") or t.get("status", "N/A")),
                str(t.get("tmux_status", "N/A")),
            ),
            10,
        ),
        _clip_display(f"{t.get('sprint_id', 'N/A')}#{t.get('node_id', 'N/A')}", 32),
        _clip_display(str(t.get("age", "N/A")), 8),
    ] for t in tasks]
    print()
    print_table(
        ["multi_task", "work", "status", "class", "pane_type", "operator", "vendor", "op_pane", "tmux", "sprint#node", "age"],
        task_rows or [["N/A", "hist", "pending", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"]],
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
    tasks = view_model.get("tasks") or []
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

    for task in tasks[:2]:
        if len(lines) >= height:
            break
        lines.append(_clip_display(
            f"TASK [{task.get('work', 'hist')}] {task.get('task', 'N/A')} -> {task.get('target', 'N/A')}",
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
        lines.append(_clip_display(
            f"DAG {dag_sprint}  {counts_str}  ready={dag_ready}  用 status 查看完整视图",
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
    active_tasks = [t for t in tasks if str(t.get("effective_status") or t.get("status") or "").lower() in ACTIVE_TASK_STATUSES]
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

    dag: dict[str, Any] = {"sprint": "N/A", "counts": {"pass": 0, "pending": 0, "reviewing": 0}, "ready": "N/A"}
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
        }

    degraded: list[dict[str, Any]] = []
    if not tmux_live:
        degraded.append({"source": "multi_task_session", "reason": "tmux_not_live"})
    if not panes_src:
        degraded.append({"source": "panes", "reason": "empty"})

    task_summary = [{
        "task": _clip_display(str(task.get("id", "N/A")).replace("mt-", ""), 16),
        "work": str(task.get("work", "hist")),
        "target": _clip_display(f"{task.get('sprint_id', 'N/A')}#{task.get('node_id', 'N/A')}", 28),
        "state": _clip_display(
            f"{task.get('effective_status') or task.get('status', 'N/A')}/"
            f"{_display_tmux_status(str(task.get('effective_status') or task.get('status', 'N/A')), str(task.get('tmux_status', 'N/A')))}",
            16,
        ),
    } for task in tasks[:4]]

    return {
        "schema_version": SCREEN_VIEW_MODEL_SCHEMA,
        "generated_at": now_iso(),
        "health": {"verdict": overall_verdict, "capsules": capsules},
        "panes": panes_out,
        "workers": workers,
        "tasks": task_summary,
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
            {"id": "tasks", "type": "table", "data": view_model.get("tasks") or []},
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
    active = [t for t in tasks if str(t.get("effective_status") or t.get("status") or "").lower() in ACTIVE_TASK_STATUSES]
    inventory = task_inventory(tasks)
    tmux_live = tmux_session_exists()
    cap_summary = result.get("capability") or capability_summary()
    data_source = "live" if tmux_live and inventory["live"] else ("history:no_multi_task_session" if tasks and not tmux_live else "no_live_workers")
    task_rows = [{
        "task": _clip_display(str(t.get("id", "N/A")).replace("mt-", ""), 18),
        "work": _clip_display(str(t.get("work", "hist")), 8),
        "state": _clip_display(
            f"{t.get('effective_status') or t.get('status', 'N/A')}/"
            f"{_display_tmux_status(str(t.get('effective_status') or t.get('status', 'N/A')), str(t.get('tmux_status', 'N/A')))}",
            16,
        ),
        "class": _clip_display(str(t.get("data_class", "N/A")), 12),
        "pane_type": _clip_display(str(t.get("pane_type", "N/A")), 16),
        "operator": _clip_display(str(t.get("operator_id") or "N/A"), 16),
        "vendor": _clip_display(str(t.get("operator_vendor") or t.get("provider") or "N/A"), 10),
        "sprint_node": _clip_display(f"{t.get('sprint_id', 'N/A')}#{t.get('node_id', 'N/A')}", 28),
        "age": _clip_display(str(t.get("age", "N/A")), 8),
    } for t in tasks] or [{
        "task": "N/A", "work": "hist", "state": "pending", "class": "N/A", "pane_type": "N/A", "operator": "N/A", "vendor": "N/A", "sprint_node": "N/A", "age": "N/A",
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
                {"key": "work", "label": "work", "width": 8},
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
    readline = _screen_readline()
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
    readline = _screen_readline()
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
    readline = _screen_readline()
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
    tmux_bin = shutil.which("tmux")
    if tmux_bin and window:
        subprocess.run([tmux_bin, "kill-window", "-t", f"{SESSION}:{window}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    screen.add_argument("--scheduler-input", action="append", default=[], help="frozen scheduler_input.json path; can repeat")
    screen.add_argument("--scheduler-runtime-dir", default="", help="directory for runtime graph/state projections")
    screen.add_argument("--run-contract", default="", help="optional run_contract.frozen.json binding")
    screen.add_argument("--artifact-binding", action="append", default=[], help="runtime input artifact TYPE=PATH; can repeat")
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
    start.add_argument("--scheduler-input", action="append", default=[], help="frozen scheduler_input.json path; can repeat")
    start.add_argument("--scheduler-runtime-dir", default="", help="directory for runtime graph/state projections")
    start.add_argument("--run-contract", default="", help="optional run_contract.frozen.json binding")
    start.add_argument("--artifact-binding", action="append", default=[], help="runtime input artifact TYPE=PATH; can repeat")
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
    status.add_argument("--scheduler-input", action="append", default=[])
    status.add_argument("--scheduler-runtime-dir", default="")
    status.add_argument("--run-contract", default="")
    status.add_argument("--artifact-binding", action="append", default=[])
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
    reap_p.add_argument("--ttl-min", "--ttl-minutes", dest="ttl_min", type=int, default=int(os.environ.get("SOLAR_MULTI_TASK_REAP_TTL_MIN", "120") or "120"))
    reap_p.add_argument("--stale-active-min", type=int, default=int(os.environ.get("SOLAR_MULTI_TASK_STALE_ACTIVE_MIN", "0") or "0"))
    reap_p.add_argument("--dry-run", action="store_true")
    shrink_p = sub.add_parser("shrink-idle", help="prune reusable idle/orphan multi-task shell windows")
    shrink_p.add_argument("--target-keep", type=int, default=IDLE_WINDOW_POOL_TARGET)
    shrink_p.add_argument("--dry-run", action="store_true")
    compact_p = sub.add_parser("compact-session", help="safely close historical active shells and compact the multi-task session")
    compact_p.add_argument("--target-keep", type=int, default=IDLE_WINDOW_POOL_TARGET)
    compact_p.add_argument("--dry-run", action="store_true")
    anchor_p = sub.add_parser("detach-and-anchor", help="select the neutral anchor window for the multi-task session")
    anchor_p.add_argument("--dry-run", action="store_true")
    stale_p = sub.add_parser("stale-schedulers", help="report or terminate exact stale multi-task scheduler processes")
    stale_p.add_argument("--apply", action="store_true", help="send SIGTERM to exact stale completed-graph scheduler runners")
    stale_p.add_argument("--json", action="store_true")
    probe_p = sub.add_parser("probe", help="run a minimal real model call for one worker profile")
    probe_p.add_argument("profile", help=f"worker profile: {','.join(profile_names())}")
    probe_p.add_argument("--timeout-sec", type=int, default=90)
    sub.add_parser("matrix", help="show role/model/backend capability matrix")
    sub.add_parser("profiles", help="list worker profiles and model/task affinity")
    sub.add_parser("doctor", help="check multi-task external backends")
    return p


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_console()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["screen"]
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd in {None, "start", "screen", "status"}:
        try:
            prepare_scheduler_input_args(args)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))

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
    if args.cmd == "shrink-idle":
        result = prune_idle_tmux_windows(args.target_keep, args.dry_run)
        rows = [[
            str(row.get("window", "N/A"))[:48],
            str(row.get("kind", "N/A")),
            str(row.get("effective_status", "N/A")),
            str(row.get("task_id", "N/A"))[:36],
            str(row.get("action", "N/A")),
        ] for row in result.get("killed", [])]
        print_table(
            ["window", "kind", "status", "task", "action"],
            rows or [["N/A", "N/A", "N/A", "N/A", "none"]],
        )
        return 0
    if args.cmd == "compact-session":
        result = compact_tmux_session(args.target_keep, args.dry_run, cwd=Path.cwd())
        rows = [[
            str(row.get("window", "N/A"))[:48],
            str(row.get("task_id", "N/A"))[:36],
            str(row.get("action", "N/A")),
        ] for row in result.get("closed", [])]
        print_table(
            ["window", "task", "close"],
            rows or [["N/A", "N/A", "none"]],
        )
        switch_rows = [[
            str(row.get("tty", "N/A"))[:18],
            str(row.get("from_window_id", "N/A")),
            str(row.get("to_target", "N/A"))[:28],
            str(row.get("action", "N/A")),
        ] for row in result.get("switches", [])]
        print_table(
            ["tty", "from", "to", "action"],
            switch_rows or [["N/A", "N/A", "N/A", "none"]],
        )
        return 0
    if args.cmd == "detach-and-anchor":
        result = detach_and_anchor(cwd=Path.cwd(), dry_run=args.dry_run)
        print_table(
            ["target", "created_anchor", "action"],
            [[
                str(result.get("target", "N/A")),
                str(result.get("created_anchor", False)),
                str(result.get("action", "N/A")),
            ]],
        )
        return 0
    if args.cmd == "stale-schedulers":
        rows = detect_stale_scheduler_runners(apply_cleanup=bool(args.apply))
        if getattr(args, "json", False):
            print(json.dumps({"rows": rows, "apply": bool(args.apply)}, ensure_ascii=False, indent=2))
            return 0
        table_rows = [[
            str(row.get("pid", "N/A")),
            _clip_display(str(row.get("sprint_id", "N/A")), 26),
            _clip_display(str(row.get("graph", "N/A")), 36),
            str(row.get("elapsed", "N/A")),
            str(row.get("rss_mb", "N/A")),
            str(row.get("stale", False)).lower(),
            _clip_display(str(row.get("reason", "N/A")), 24),
            _clip_display(str(row.get("action", "keep")), 18),
        ] for row in rows]
        print_table(
            ["pid", "sprint", "graph", "elapsed", "rss_mb", "stale", "reason", "action"],
            table_rows or [["N/A", "N/A", "N/A", "N/A", "N/A", "false", "none", "keep"]],
        )
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
        explicit_graphs = [str(path) for path in graph_files(getattr(args, "graph", []))] if getattr(args, "graph", []) else []
        registered = False
        try:
            if explicit_graphs:
                _register_scheduler_pid(explicit_graphs)
                registered = True
            no_progress_ticks = 0
            while True:
                result = schedule_once(args)
                render_result(result, args)
                if args.once:
                    return 0
                if explicit_graphs and _all_graphs_terminal(explicit_graphs) and not active_tasks():
                    _append_scheduler_log("all_graphs_terminal_no_active_tasks_exit")
                    return 0
                # Stuck/deadlock exit: a FAIL or needs_human_review blocks all remaining nodes (none
                # active, nothing ready, not all-terminal) and there is no eval/reconcile/launch progress.
                # Without this the loop would spin forever. Require STUCK_EXIT_TICKS consecutive dead ticks
                # to avoid exiting on a transient settle window.
                if explicit_graphs and not args.dry_run:
                    states = [_graph_runner_state(gp) for gp in graph_files(explicit_graphs)]
                    deadlocked = bool(states) and all(
                        s.get("ok") and not s.get("has_active") and not s.get("ready_nodes") and not s.get("all_terminal")
                        for s in states
                    ) and not active_tasks()
                    progressed = bool(result.get("launched")) or any(
                        a.get("eval_dispatched") or a.get("reconciled") or a.get("terminalized")
                        for a in (result.get("advance") or [])
                    )
                    if deadlocked and not progressed:
                        no_progress_ticks += 1
                    else:
                        no_progress_ticks = 0
                    if no_progress_ticks >= STUCK_EXIT_TICKS:
                        _append_scheduler_log(f"multi_task_dag_deadlocked_no_progress_exit:{no_progress_ticks}_ticks")
                        return 0
                time.sleep(max(1, int(args.interval)))
        finally:
            if registered:
                _unregister_scheduler_pid()

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
