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
            "best_for": ["knowledge-extraction", "knowledge-preprocess", "evidence-atom", "wiki-ingest", "qmd-indexing"],
            "command": "PATH=\"/opt/homebrew/bin:/usr/local/bin:$PATH\" python3 \"$HARNESS_DIR/tools/thunderomlx_knowledge_extract_agent.py\"",
            "max_parallel": 1,
        },
        "thunderomlx-benchmark": {
            "role": "builder",
            "label": "ThunderOMLX 缓存基准",
            "persona": "builder",
            "backend": "command",
            "model": "thunderomlx",
            "approval_mode": "default",
            "best_for": ["benchmark", "cache-metrics", "knowledge-extraction"],
            "command": "PATH=\"/opt/homebrew/bin:/usr/local/bin:$PATH\" python3 \"$HARNESS_DIR/tools/thunderomlx_cache_benchmark_agent.py\"",
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
TERMINAL_TASK_STATUSES = {"completed", "failed", "failed_missing_handoff", "cancelled"}
TASK_STALE_WARN_SEC = int(os.environ.get("SOLAR_MULTI_TASK_STALE_WARN_SEC", "1800") or "1800")
QUOTA_RE = re.compile(
    r"rate[- ]?limit|quota|you(?:'|’)ve hit your limit|resets\s+\d|"
    r"api usage billing|429|upgrade your plan",
    re.I,
)


def load_profiles() -> dict[str, Any]:
    if PROFILE_PATH.exists():
        try:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            if isinstance(data.get("profiles"), dict):
                return data
        except Exception:
            pass
    return DEFAULT_PROFILE_CONFIG


def profile_names() -> list[str]:
    return sorted((load_profiles().get("profiles") or {}).keys())


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
        or node.get("persona")
        or node.get("worker_role")
        or node.get("handoff_to")
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
        "product": "pm",
        "product-manager": "pm",
        "planning": "planner",
        "architect": "planner",
    }
    return aliases.get(value, value or "builder")


def select_profile(node: dict[str, Any], profile_override: str = "", model_override: str = "", backend_override: str = "") -> dict[str, Any]:
    config = load_profiles()
    profiles = config.get("profiles") or {}
    profile_name = profile_override or str(node.get("preferred_profile") or node.get("profile") or "")
    if not profile_name:
        role = role_from_node(node)
        for name, spec in profiles.items():
            if str(spec.get("role", "")).lower() == role and not str(name).startswith(("gemini-", "deepseek-", "glm-", "thunder")):
                profile_name = str(name)
                break
    profile_name = profile_name or str((config.get("defaults") or {}).get("profile") or "builder")
    if profile_name not in profiles:
        raise ValueError(f"unknown multi-task profile: {profile_name}")
    selected = dict(profiles[profile_name])
    selected["name"] = profile_name
    selected["role"] = str(selected.get("role") or role_from_node(node))
    selected["persona"] = str(selected.get("persona") or selected["role"])
    selected["model"] = str(model_override or node.get("preferred_model") or selected.get("model") or "sonnet")
    selected["backend"] = str(backend_override or selected.get("backend") or (config.get("defaults") or {}).get("backend") or "claude-cli")
    selected["approval_mode"] = str(selected.get("approval_mode") or "auto_edit")
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
            "export CLAUDE_CODE_MAX_OUTPUT_TOKENS=${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-4096}",
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
    status = str(row.get("status") or "").lower()
    tmux_status = str(row.get("tmux_status") or "").lower()
    age_s = task_age_s(row, now_ts)
    stale = age_s is not None and age_s >= TASK_STALE_WARN_SEC
    if status in ACTIVE_TASK_STATUSES:
        if tmux_status == "live":
            return "live"
        return "stale_active" if stale else "pending"
    if status == "dry_run":
        return "stale" if stale else "dry_run"
    if status in TERMINAL_TASK_STATUSES or status.startswith("reaped"):
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
    return [row for row in list_task_rows() if str(row.get("status", "")).lower() in ACTIVE_TASK_STATUSES]


def task_inventory(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    latest: dict[str, Any] | None = None
    latest_ts = -1.0
    for task in tasks:
        data_class = str(task.get("data_class") or "observed")
        status = str(task.get("status") or "N/A").lower()
        counts[data_class] = counts.get(data_class, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1
        updated_ts = parse_iso(str(task.get("updated_at") or task.get("created_at") or ""))
        if updated_ts is not None and updated_ts > latest_ts:
            latest = task
            latest_ts = updated_ts
    live = counts.get("live", 0)
    active = sum(1 for task in tasks if str(task.get("status", "")).lower() in ACTIVE_TASK_STATUSES)
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
                hits.append({"task": log.parent.name, "log": str(log)})
    if hits:
        return {"ok": False, "reason": "recent_quota_or_rate_limit", "hits": hits[:5]}
    return {"ok": True, "reason": "no_recent_quota_hit"}


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
    agent_cmd = str(payload.get("command") or os.environ.get("SOLAR_MULTI_TASK_AGENT_CMD", "")).strip()
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
HARNESS_DIR={shlex.quote(str(HARNESS_DIR))}
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
export TASK_DIR STATUS_FILE DISPATCH_FILE OUTPUT_LOG HARNESS_DIR SPRINTS_DIR GRAPH NODE_ID SID ROLE PROFILE BACKEND MODEL PROVIDER CAPABILITY_STATUS HANDOFF HARNESS

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
write_status running
pane_title "MT $ROLE/$PROFILE | 模型:$MODEL | provider:$PROVIDER | 状态:running"

if [[ "${{SOLAR_MULTI_TASK_SANITIZE_ENV:-1}}" != "0" ]]; then
  unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_EXECPATH
  unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY
fi

{{
  echo "[solar-harness multi-task] sid=$SID node=$NODE_ID backend=$BACKEND model=$MODEL start=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
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
}} > >(tee -a "$OUTPUT_LOG") 2>&1
rc=$?

if [[ "$rc" -eq 0 && -s "$HANDOFF" ]]; then
  "$HARNESS" graph-scheduler mark --graph "$GRAPH" --node "$NODE_ID" --status reviewing --in-place >> "$OUTPUT_LOG" 2>&1 || true
  write_status completed "$rc"
  pane_title "MT $ROLE/$PROFILE | 模型:$MODEL | provider:$PROVIDER | 状态:completed"
elif [[ "$rc" -eq 0 ]]; then
  echo "ERROR: missing handoff: $HANDOFF" | tee -a "$OUTPUT_LOG"
  "$HARNESS" graph-scheduler mark --graph "$GRAPH" --node "$NODE_ID" --status failed --in-place >> "$OUTPUT_LOG" 2>&1 || true
  write_status failed_missing_handoff 65
  pane_title "MT $ROLE/$PROFILE | 模型:$MODEL | provider:$PROVIDER | 状态:failed_missing_handoff"
  rc=65
else
  "$HARNESS" graph-scheduler mark --graph "$GRAPH" --node "$NODE_ID" --status failed --in-place >> "$OUTPUT_LOG" 2>&1 || true
  write_status failed "$rc"
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
    max_workers = max(1, int(args.max_workers))
    guard = launch_guard(max_workers, args.memory_reserve_gb, args.cooldown_sec, args.quota_backoff_sec)
    slots = max(0, max_workers - len(active_tasks()))
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
    }


def status_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    """Read current worker and DAG state without dispatching new work."""
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    max_workers = max(1, int(getattr(args, "max_workers", DEFAULT_MAX_WORKERS)))
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
    active = [t for t in tasks if str(t.get("status", "")).lower() in ACTIVE_TASK_STATUSES]
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
        _clip_display(str(t.get("status", "N/A")), 12),
        _clip_display(str(t.get("data_class", "N/A")), 12),
        _clip_display(str(t.get("pane_type", "N/A")), 22),
        _clip_display(str(t.get("tmux_status", "N/A")), 10),
        _clip_display(f"{t.get('sprint_id', 'N/A')}#{t.get('node_id', 'N/A')}", 32),
        _clip_display(str(t.get("age", "N/A")), 8),
    ] for t in tasks]
    print()
    print_table(
        ["multi_task", "status", "class", "pane_type", "tmux", "sprint#node", "age"],
        task_rows or [["N/A", "pending", "N/A", "N/A", "N/A", "N/A", "N/A"]],
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


def render_screen_status_lines(result: dict[str, Any], width: int, max_lines: int) -> list[str]:
    """Compact screen-only view; avoid nesting wide tables inside the screen box."""
    content_width = max(40, width)
    guard = result.get("guard") or {}
    cap_summary = result.get("capability") or capability_summary()
    panes = result.get("panes") or []
    tasks = list_task_rows()
    active = [t for t in tasks if str(t.get("status", "")).lower() in ACTIVE_TASK_STATUSES]
    inventory = task_inventory(tasks)
    dispatches = result.get("dispatches") or []
    graphs = result.get("graphs") or []

    def role_label(role: str, pane: str) -> str:
        normalized = role.lower()
        if normalized == "pm":
            return "PM"
        if normalized == "planner":
            return "PLAN"
        if normalized == "builder":
            return "BUILD"
        if normalized == "evaluator":
            return "EVAL"
        if "lab" in normalized:
            suffix = pane.split(":")[-1].split(".")[-1]
            return f"LAB{suffix}"
        return normalized[:5].upper() or "N/A"

    def display_pane_id(pane_id: str, compact: bool = False) -> str:
        if pane_id.startswith(f"{MAIN_SESSION}:"):
            suffix = pane_id.split(":", 1)[1].split(".")[-1]
            return f"main:{suffix}"
        if pane_id.startswith(f"{LAB_SESSION}:"):
            suffix = pane_id.split(":", 1)[1].split(".")[-1]
            return f"lab:{suffix}"
        return pane_id

    def compact_sprint(value: Any, terse: bool = False) -> str:
        sid = str(value or "N/A")
        match = re.match(r"^(?:sprint|epic)-(\d{8})-(.+)$", sid)
        if not match:
            return _clip_display(sid, 34)
        date, tail = match.groups()
        s_match = re.search(r"(s\d{2}(?:-[a-z0-9]+){0,2})$", tail)
        if s_match:
            if terse:
                return f"{date}/{s_match.group(1).split('-', 1)[0]}"
            return f"{date}/{s_match.group(1)}"
        parts = [p for p in tail.split("-") if p]
        if terse and parts:
            return f"{date}/{parts[-1]}"
        return f"{date}/{'-'.join(parts[-3:])}" if parts else date

    def compact_time(value: Any) -> str:
        text = str(value or "N/A")
        match = re.search(r"T(\d{2}:\d{2}:\d{2})", text)
        return match.group(1) if match else text.replace("2026-", "")

    def compact_counts(counts: dict[str, Any]) -> str:
        aliases = {
            "active": "act",
            "dispatched": "disp",
            "passed": "pass",
            "pending": "pend",
            "ready": "ready",
            "reviewing": "rev",
            "running": "run",
        }
        parts = []
        for key, value in sorted(counts.items()):
            parts.append(f"{aliases.get(str(key), str(key)[:4])}:{value}")
        return ",".join(parts) or "N/A"

    def compact_state(value: Any) -> str:
        text = str(value or "N/A")
        if text.startswith("working"):
            return "work"
        if text.startswith("ready"):
            return "ready"
        return text

    def model_name(value: Any, width_: int) -> str:
        text = str(value or "N/A")
        text = text.replace("GLM-5.1", "GLM").replace("Sonnet", "Sonn")
        return _clip_display(text, width_)

    def pane_row(pane: dict[str, Any] | None, width_: int) -> str:
        if not pane:
            return ""
        pane_id = str(pane.get("pane", "N/A"))
        role = role_label(str(pane.get("role", "N/A")), pane_id)
        state = str(pane.get("state", "N/A"))
        marker = ">" if state.startswith("working") else " "
        return _clip_display(
            f"{marker}{role:<5} {_clip_display(display_pane_id(pane_id), 7):<7} "
            f"{model_name(pane.get('model', 'N/A'), 5):<5} {_clip_display(compact_state(state), 5):<5}",
            width_,
        )

    def pair(left: str, right: str = "") -> str:
        if content_width < 76:
            return _clip_display(left, content_width)
        left_width = 30
        right_width = max(20, content_width - left_width - 3)
        return _clip_display(
            _pad_display(_clip_display(left, left_width), left_width) + " | " + _clip_display(right, right_width),
            content_width,
        )

    lines: list[str] = []
    tmux_state = "live" if tmux_session_exists() else "missing"
    guard_state = str(guard.get("reason", "N/A"))
    pane_count = len([p for p in panes if p.get("plane") != "multi-task"])
    lines.append(_clip_display(
        f"Solar Harness Multi-Task  {result.get('refresh_mode', 'cached')}  panes={pane_count}  live={inventory['live']} tracked={inventory['total']} stale={inventory['stale']}",
        content_width,
    ))
    lines.append(_clip_display(
        f"[{'ok' if tmux_state == 'live' else 'warn'}] mt={tmux_state}  "
        f"[{'ok' if guard.get('ok') else 'warn'}] guard={guard_state.replace('low_memory', 'low_mem')}  "
        f"age={inventory['latest_age']} models 可派={len(cap_summary.get('enabled') or [])} "
        f"ok={cap_summary.get('ok', 0)} warn={cap_summary.get('warn', 0)} err={cap_summary.get('error', 0)}",
        content_width,
    ))

    main_panes = [p for p in panes if p.get("plane") == "four-pane"]
    lab_panes = [p for p in panes if p.get("plane") == "builder-lab"]
    lines.append(pair("PANE MAP", "Builder Lab"))
    max_rows = max(len(main_panes[:4]), len(lab_panes[:4]))
    for idx in range(max_rows):
        left = pane_row(main_panes[idx] if idx < len(main_panes[:4]) else None, 30)
        right = pane_row(lab_panes[idx] if idx < len(lab_panes[:4]) else None, 30)
        lines.append(pair(left, right))

    counts_text = ",".join(f"{k}:{v}" for k, v in sorted((inventory.get("statuses") or {}).items())) or "N/A"
    if tasks and len(lines) < max_lines:
        worker_line = f"WORKERS live={inventory['live']} active={len(active)} history={inventory['historical']} stale={inventory['stale']} {counts_text}"
        useful_tasks = [t for t in tasks if str(t.get("status", "")).lower() in ACTIVE_TASK_STATUSES]
        if not useful_tasks:
            useful_tasks = sorted(tasks, key=lambda t: str(t.get("updated_at", "")), reverse=True)[:1]
        if useful_tasks:
            task = useful_tasks[0]
            pane_type = str(task.get("pane_type", "N/A")).split(":")[-1]
            worker_line += f"  latest {task.get('data_class', 'N/A')}:{pane_type}->{compact_sprint(task.get('sprint_id'))}#{task.get('node_id', 'N/A')}"
        lines.append(_clip_display(worker_line, content_width))

    if dispatches and len(lines) < max_lines:
        item = dispatches[0]
        terse = content_width < 90
        lines.append(_clip_display(
            f"DISPATCH {compact_time(item.get('time'))} {item.get('role', 'N/A')} "
            f"{display_pane_id(str(item.get('pane', 'N/A')))} -> {compact_sprint(item.get('sprint'), terse=terse)}#{item.get('node', 'N/A')}",
            content_width,
        ))

    if graphs and len(lines) < max_lines:
        graph = graphs[0]
        counts = compact_counts(graph.get("counts") or {})
        ready = ",".join(graph.get("ready") or []) or "N/A"
        terse = content_width < 90
        lines.append(_clip_display(
            f"DAG {compact_sprint(graph.get('sid'), terse=terse)}  {counts}  ready={ready}  用 status 查看完整视图",
            content_width,
        ))
    elif len(lines) < max_lines:
        lines.append(_clip_display("用 status 查看完整视图", content_width))

    if len(lines) > max_lines:
        return lines[: max(0, max_lines - 1)] + [_clip_display(f"... 已省略 {len(lines) - max_lines + 1} 行；用 status 查看完整视图", content_width)]
    return lines


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
        "sprint_node": _clip_display(f"{t.get('sprint_id', 'N/A')}#{t.get('node_id', 'N/A')}", 28),
        "age": _clip_display(str(t.get("age", "N/A")), 8),
    } for t in tasks] or [{
        "task": "N/A", "state": "pending", "class": "N/A", "pane_type": "N/A", "sprint_node": "N/A", "age": "N/A",
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
                {"key": "sprint_node", "label": "sprint#node", "width": 26},
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
    status_lines = render_screen_status_lines(result, max(40, cols - 4), max(1, top_h - 2))
    fixed_input_lines = [
        _screen_selection_line(args),
        "输入: 自然语言需求 / status / profiles / doctor / foreground latest / logs latest / q",
        f"history: ↑/↓ {SCREEN_HISTORY_PATH.name}; intent_log=screen-commands.jsonl",
    ]
    input_body_height = max(0, bottom_h - 2)
    message_slots = max(1, input_body_height - len(fixed_input_lines))
    input_lines = fixed_input_lines + messages[-message_slots:]
    print("\n".join(_box_lines("后台 pane 状态 / DAG worker 池", status_lines, cols, top_h)))
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
        current = str(status.get("status") or "").lower()
        updated_ts = parse_iso(str(status.get("updated_at") or status.get("created_at") or ""))
        age = None if updated_ts is None else now - updated_ts
        terminal_old = current in TERMINAL_TASK_STATUSES and age is not None and age >= ttl
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
