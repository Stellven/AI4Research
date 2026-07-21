#!/usr/bin/env python3
"""Command backend adapter for ChatGPT browser-agent logical operator tasks."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

import operator_flow_control as ofc  # noqa: E402


DEFAULT_OPERATOR_ID = "mini-chatgpt-deep-research"
DEFAULT_PROJECT_NAME = "杂项"
DEFAULT_WRAPPER = ROOT / "scripts" / "browser_agent_chatgpt_wrapper.py"
DEFAULT_BROWSER_USE_PYTHON = Path.home() / ".claude" / "mcp-servers" / "browser-use" / ".venv" / "bin" / "python"
DEFAULT_LOCAL_PROFILE_POLICY = Path.home() / ".solar" / "harness" / "browser-agent-chatgpt-local.json"


def _load_envelope() -> dict[str, Any]:
    path = str(os.environ.get("SOLAR_OPERATOR_ENVELOPE_JSON") or "").strip()
    if not path:
        raise RuntimeError("SOLAR_OPERATOR_ENVELOPE_JSON missing")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("operator envelope must be a JSON object")
    return payload


def _task_dir() -> Path:
    raw = str(os.environ.get("TASK_DIR") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path.cwd()


def _wrapper_cmd() -> list[str]:
    raw = (
        os.environ.get("TECH_HOTSPOT_BROWSER_CHATGPT_CMD")
        or os.environ.get("BROWSER_AGENT_CHATGPT_CMD")
        or ""
    ).strip()
    if raw:
        return shlex.split(raw)
    if DEFAULT_WRAPPER.exists() and DEFAULT_BROWSER_USE_PYTHON.exists():
        return [str(DEFAULT_BROWSER_USE_PYTHON), str(DEFAULT_WRAPPER)]
    return []


def _profile_policy_path() -> Path | None:
    disabled = (
        os.environ.get("BROWSER_AGENT_CHATGPT_PROFILE_POLICY_DISABLED")
        or os.environ.get("TECH_HOTSPOT_BROWSER_CHATGPT_PROFILE_POLICY_DISABLED")
        or ""
    ).strip().lower()
    if disabled in {"1", "true", "yes", "on"}:
        return None
    raw = (
        os.environ.get("BROWSER_AGENT_CHATGPT_PROFILE_POLICY_FILE")
        or os.environ.get("TECH_HOTSPOT_BROWSER_CHATGPT_PROFILE_POLICY_FILE")
        or ""
    ).strip()
    return Path(raw).expanduser() if raw else DEFAULT_LOCAL_PROFILE_POLICY


def _load_profile_policy() -> dict[str, Any]:
    path = _profile_policy_path()
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"invalid_browser_agent_profile_policy:{path}:root_not_object")
    policies = data.get("policies") or {}
    if not isinstance(policies, dict):
        raise RuntimeError(f"invalid_browser_agent_profile_policy:{path}:policies_not_object")
    return {"path": str(path), "policies": policies}


def _pick_policy_key(request: dict[str, Any]) -> str:
    purpose = str(request.get("purpose") or os.environ.get("BROWSER_AGENT_PURPOSE") or "").strip().lower()
    if purpose.startswith(("hf-paper-l7-high-reasoning", "hf-paper-report-plan", "hf-paper-report-section")):
        return "hf_paper_insight"
    if purpose.startswith("github-trend-report"):
        return "github_trend_report"
    if purpose.startswith("ai-influence-report"):
        return "ai_influence_report"
    return "default"


def _pick_profile(purpose: str, profiles: list[str], selection: str) -> str:
    clean = [item for item in profiles if str(item).strip()]
    if not clean:
        return ""
    if len(clean) == 1 or selection == "first":
        return clean[0]
    import hashlib

    digest = hashlib.sha256(str(purpose or "").encode("utf-8")).hexdigest()
    return clean[int(digest[:8], 16) % len(clean)]


def _enforce_no_default_profile_for_scoped_chatgpt(policy_key: str, policy: dict[str, Any], resolved_profile: str, purpose: str) -> None:
    protected_keys = {"hf_paper_insight", "github_trend_report", "ai_influence_report"}
    allow_default = bool(policy.get("allow_default_profile") or policy.get("allow_default_chatgpt_profile"))
    if policy_key in protected_keys and not allow_default and resolved_profile == "Default":
        raise RuntimeError(
            "browser_agent_profile_policy_default_profile_forbidden:"
            f"purpose={purpose or 'N/A'}:policy_key={policy_key}:actual=Default"
        )


def _is_protected_scoped_chatgpt(policy_key: str) -> bool:
    return policy_key in {"hf_paper_insight", "github_trend_report", "ai_influence_report"}


def apply_profile_policy(env: dict[str, str], request: dict[str, Any]) -> dict[str, Any]:
    loaded = _load_profile_policy()
    if not loaded:
        return {"enabled": False}
    policies = loaded["policies"]
    key = _pick_policy_key(request)
    default_policy = policies.get("default") if isinstance(policies.get("default"), dict) else {}
    scoped_policy = policies.get(key) if isinstance(policies.get(key), dict) else {}
    policy = {**default_policy, **scoped_policy}
    purpose = str(request.get("purpose") or os.environ.get("BROWSER_AGENT_PURPOSE") or "")
    allowed_profiles = [str(item).strip() for item in (policy.get("allowed_profiles") or []) if str(item).strip()]
    expected_account = str(policy.get("expected_account_email") or "").strip()
    selection = str(policy.get("selection") or "first").strip().lower()
    profile_strategy = str(policy.get("profile_strategy") or "persistent").strip().lower()
    user_data_dir = str(policy.get("user_data_dir") or "").strip()

    explicit_profile = str(env.get("BROWSER_AGENT_PROFILE_DIRECTORY") or "").strip()
    explicit_account = str(
        env.get("BROWSER_AGENT_CHATGPT_ACCOUNT_EMAIL")
        or env.get("BROWSER_AGENT_TARGET_ACCOUNT_EMAIL")
        or ""
    ).strip()
    if expected_account and explicit_account and explicit_account.lower() != expected_account.lower():
        raise RuntimeError(
            "browser_agent_profile_policy_account_mismatch:"
            f"purpose={purpose or 'N/A'}:expected={expected_account}:actual={explicit_account}"
        )
    if allowed_profiles and explicit_profile and explicit_profile not in allowed_profiles:
        raise RuntimeError(
            "browser_agent_profile_policy_profile_mismatch:"
            f"purpose={purpose or 'N/A'}:allowed={','.join(allowed_profiles)}:actual={explicit_profile}"
        )

    resolved_profile = explicit_profile or _pick_profile(purpose, allowed_profiles, selection)
    resolved_account = explicit_account or expected_account
    _enforce_no_default_profile_for_scoped_chatgpt(key, policy, resolved_profile, purpose)
    if resolved_profile:
        env["BROWSER_AGENT_PROFILE_DIRECTORY"] = resolved_profile
    if resolved_account:
        env["BROWSER_AGENT_TARGET_ACCOUNT_EMAIL"] = resolved_account
        env["BROWSER_AGENT_CHATGPT_ACCOUNT_EMAIL"] = resolved_account
    if profile_strategy:
        env["BROWSER_AGENT_PROFILE_STRATEGY"] = profile_strategy
        env["BROWSER_AGENT_CHATGPT_PROFILE_STRATEGY"] = profile_strategy
    if user_data_dir and not env.get("BROWSER_AGENT_USER_DATA_DIR"):
        env["BROWSER_AGENT_USER_DATA_DIR"] = user_data_dir
    if _is_protected_scoped_chatgpt(key) and not bool(policy.get("allow_headless")):
        env["BROWSER_AGENT_HEADLESS"] = "false"
        env["TECH_HOTSPOT_BROWSER_CHATGPT_HEADLESS"] = "false"
        env["BROWSER_AGENT_CHATGPT_ALLOW_HEADED"] = "true"
        env["TECH_HOTSPOT_BROWSER_CHATGPT_ALLOW_HEADED"] = "true"
        env["BROWSER_AGENT_ALLOW_HEADED"] = "true"
    env["BROWSER_AGENT_CHATGPT_PROFILE_POLICY_KEY"] = key
    return {
        "enabled": True,
        "policy_key": key,
        "policy_path": loaded.get("path") or "",
        "selected_profile_directory": resolved_profile,
        "selected_account_email": resolved_account,
        "profile_strategy": profile_strategy,
        "user_data_dir_set": bool(env.get("BROWSER_AGENT_USER_DATA_DIR")),
        "headless_forced": _is_protected_scoped_chatgpt(key) and not bool(policy.get("allow_headless")),
    }


def _operator_id(envelope: dict[str, Any]) -> str:
    return str(envelope.get("operator_id") or "").strip() or DEFAULT_OPERATOR_ID


def _read_request_file(path_value: str) -> dict[str, Any]:
    payload = json.loads(Path(path_value).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("chatgpt browser-agent request file must contain JSON object")
    return payload


def build_request(envelope: dict[str, Any], *, task_dir: Path | None = None) -> dict[str, Any]:
    raw = envelope.get("chatgpt_browser_agent_request")
    if isinstance(raw, dict):
        request = deepcopy(raw)
    else:
        file_ref = str(envelope.get("chatgpt_browser_agent_request_file") or "").strip()
        if file_ref:
            request = _read_request_file(file_ref)
        else:
            request = {}
            for key in (
                "prompt",
                "prompt_file",
                "expected_output",
                "model",
                "reasoning_effort",
                "project_name",
                "model_mode",
                "tool_mode",
                "require_ui_mode",
                "require_deep_research",
                "account_email",
                "action",
                "timeout_seconds",
            ):
                if key in envelope:
                    request[key] = deepcopy(envelope[key])
    if not str(request.get("prompt") or "").strip():
        prompt_file = str(request.get("prompt_file") or envelope.get("prompt_file") or "").strip()
        if prompt_file:
            request["prompt"] = Path(prompt_file).expanduser().read_text(encoding="utf-8")
    if task_dir is not None:
        request.setdefault("request_dir", str((task_dir / "chatgpt-browser-agent-request").resolve()))
    request.setdefault("expected_output", "markdown")
    request.setdefault("model", "chatgpt-5.5")
    request.setdefault("reasoning_effort", "high")
    request.setdefault("model_mode", "thinking")
    request.setdefault("tool_mode", "none")
    request.setdefault("require_ui_mode", True)
    request.setdefault("require_deep_research", False)
    request.setdefault("action", "run")
    request.setdefault("project_name", DEFAULT_PROJECT_NAME)
    return request


def _rate_control_settings(envelope: dict[str, Any]) -> dict[str, Any]:
    operator_id = _operator_id(envelope)
    flow_control: dict[str, Any] = {}
    try:
        import operator_runtime  # type: ignore

        config = operator_runtime.get_operator_config(operator_id) or {}
        if isinstance(config.get("flow_control"), dict):
            flow_control = dict(config["flow_control"])
    except Exception:
        flow_control = {}
    return {
        "operator_id": operator_id,
        "success_cooldown_seconds": ofc.int_value(
            envelope.get("chatgpt_success_cooldown_seconds")
            or os.environ.get("SOLAR_CHATGPT_SUCCESS_COOLDOWN_SECONDS")
            or flow_control.get("success_cooldown_seconds"),
            180,
        ),
        "rate_limit_cooldown_seconds": ofc.int_value(
            envelope.get("chatgpt_rate_limit_cooldown_seconds")
            or os.environ.get("SOLAR_CHATGPT_RATE_LIMIT_COOLDOWN_SECONDS")
            or flow_control.get("rate_limit_cooldown_seconds"),
            3600,
        ),
        "auth_cooldown_seconds": ofc.int_value(
            envelope.get("chatgpt_auth_cooldown_seconds")
            or os.environ.get("SOLAR_CHATGPT_AUTH_COOLDOWN_SECONDS")
            or flow_control.get("auth_cooldown_seconds"),
            21600,
        ),
        "defer_on_cooldown": ofc.bool_value(
            envelope.get("chatgpt_defer_on_cooldown")
            or os.environ.get("SOLAR_CHATGPT_DEFER_ON_COOLDOWN")
            or flow_control.get("defer_on_cooldown"),
            True,
        ),
        "defer_on_auth": ofc.bool_value(
            envelope.get("chatgpt_defer_on_auth")
            or os.environ.get("SOLAR_CHATGPT_DEFER_ON_AUTH")
            or flow_control.get("defer_on_auth"),
            True,
        ),
    }


def _summary_markdown(response: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# ChatGPT Browser Agent Result",
            "",
            "## 已完成",
            f"- model: {response.get('model') or 'N/A'}",
            f"- project_name: {response.get('project_name') or 'N/A'}",
            f"- expected_output: {response.get('expected_output') or 'N/A'}",
        ]
    )


def run_request(request: dict[str, Any], *, task_dir: Path) -> dict[str, Any]:
    prompt = str(request.get("prompt") or "").strip()
    if not prompt:
        raise RuntimeError("ChatGPT browser-agent operator requires prompt")
    cmd = _wrapper_cmd()
    if not cmd:
        raise RuntimeError("ChatGPT browser-agent wrapper command is not configured")
    task_dir.mkdir(parents=True, exist_ok=True)
    request_dir = Path(str(request.get("request_dir") or (task_dir / "chatgpt-browser-agent-request"))).expanduser()
    request_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "chatgpt-browser-agent-request.json").write_text(
        json.dumps(request, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "BROWSER_AGENT_REQUEST_DIR": str(request_dir),
            "BROWSER_AGENT_EXPECTED_OUTPUT": str(request.get("expected_output") or "markdown"),
            "CHATGPT_MODEL": str(request.get("model") or "chatgpt-5.5"),
            "CHATGPT_REASONING_EFFORT": str(request.get("reasoning_effort") or "high"),
            "BROWSER_AGENT_CHATGPT_MODEL_MODE": str(request.get("model_mode") or "thinking"),
            "BROWSER_AGENT_CHATGPT_TOOL_MODE": str(request.get("tool_mode") or "none"),
            "BROWSER_AGENT_CHATGPT_REQUIRE_UI_MODE": "true"
            if bool(request.get("require_ui_mode", True))
            else "false",
            "BROWSER_AGENT_CHATGPT_REQUIRE_DEEP_RESEARCH": "true"
            if bool(request.get("require_deep_research", False))
            else "false",
            "BROWSER_AGENT_CHATGPT_ACTION": str(request.get("action") or "run"),
            "BROWSER_AGENT_CHATGPT_PROJECT_NAME": str(request.get("project_name") or DEFAULT_PROJECT_NAME),
            "BROWSER_AGENT_CHATGPT_REQUIRE_PROJECT": "true",
        }
    )
    account_email = str(request.get("account_email") or "").strip()
    if account_email:
        env["BROWSER_AGENT_CHATGPT_ACCOUNT_EMAIL"] = account_email
        env["BROWSER_AGENT_TARGET_ACCOUNT_EMAIL"] = account_email
    profile_policy = apply_profile_policy(env, request)
    (task_dir / "chatgpt-browser-agent-profile-policy.json").write_text(
        json.dumps(profile_policy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    timeout = ofc.int_value(request.get("timeout_seconds") or os.environ.get("BROWSER_AGENT_CHATGPT_TIMEOUT"), 1800)
    proc = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        capture_output=True,
        env=env,
        timeout=timeout,
    )
    combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    (task_dir / "chatgpt-browser-agent-output.txt").write_text(
        combined + ("\n" if combined else ""),
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ChatGPT browser-agent failed rc={proc.returncode}: {combined[-1000:]}")
    text = str(proc.stdout or "").strip()
    if not text:
        raise RuntimeError("ChatGPT browser-agent returned empty output")
    result = {
        "ok": True,
        "model": str(request.get("model") or "chatgpt-5.5"),
        "project_name": str(request.get("project_name") or DEFAULT_PROJECT_NAME),
        "expected_output": str(request.get("expected_output") or "markdown"),
        "request_dir": str(request_dir),
        "text": text,
    }
    (task_dir / "chatgpt-browser-agent-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(_summary_markdown(result))
    return result


def main() -> int:
    envelope = _load_envelope()
    task_dir = _task_dir()
    ofc.clear_task_control(task_dir)
    request = build_request(envelope, task_dir=task_dir)
    rate_control = _rate_control_settings(envelope)
    operator_id = str(rate_control["operator_id"])
    try:
        ofc.ensure_operator_available(operator_id)
        run_request(request, task_dir=task_dir)
        ofc.apply_success_cooldown(
            operator_id,
            success_cooldown_seconds=int(rate_control.get("success_cooldown_seconds") or 0),
        )
        return 0
    except Exception as exc:
        ofc.apply_failure_flow_control(
            task_dir,
            operator_id=operator_id,
            failure_text=str(exc),
            rate_limit_cooldown_seconds=int(rate_control.get("rate_limit_cooldown_seconds") or 0),
            auth_cooldown_seconds=int(rate_control.get("auth_cooldown_seconds") or 0),
            defer_on_cooldown=bool(rate_control.get("defer_on_cooldown")),
            defer_on_auth=bool(rate_control.get("defer_on_auth")),
        )
        print(f"chatgpt_browser_agent_task_operator failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
