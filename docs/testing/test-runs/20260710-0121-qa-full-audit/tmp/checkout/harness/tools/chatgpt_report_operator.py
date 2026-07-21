#!/usr/bin/env python3
"""Specialized Browser Agent ChatGPT report operators.

This stdin/stdout adapter exposes three logical report operators over the same
browser automation backend:

- ChatGPT Report Planner
- ChatGPT Report Chapter Writer
- ChatGPT Report Deep Writer

Secrets stay outside the repository. Account hints, profile paths and wrapper
commands are read from environment variables only.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_NAME = "杂项"
DEFAULT_WRAPPER = ROOT / "scripts" / "browser_agent_chatgpt_wrapper.py"
DEFAULT_BROWSER_USE_PYTHON = Path.home() / ".claude" / "mcp-servers" / "browser-use" / ".venv" / "bin" / "python"
DEFAULT_LOCAL_PROFILE_POLICY = Path.home() / ".solar" / "harness" / "browser-agent-chatgpt-local.json"


def infer_kind(purpose: str, explicit: str = "") -> str:
    value = explicit.strip().lower().replace("-", "_")
    if value in {"planner", "chapter_writer", "deep_writer"}:
        return value
    lowered = purpose.lower()
    if "deep" in lowered or "research" in lowered:
        return "deep_writer"
    if "plan" in lowered or "grouping" in lowered:
        return "planner"
    return "chapter_writer"


def wrapper_cmd() -> list[str]:
    raw = os.environ.get("BROWSER_AGENT_CHATGPT_WRAPPER_CMD", "").strip()
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
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_LOCAL_PROFILE_POLICY


def _load_profile_policy() -> dict[str, Any]:
    path = _profile_policy_path()
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"invalid_browser_agent_profile_policy:{path}:{type(exc).__name__}:{exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"invalid_browser_agent_profile_policy:{path}:root_not_object")
    policies = data.get("policies") or {}
    if not isinstance(policies, dict):
        raise RuntimeError(f"invalid_browser_agent_profile_policy:{path}:policies_not_object")
    return {
        "path": str(path),
        "version": data.get("version") or 1,
        "policies": policies,
    }


def _policy_key_for_purpose(purpose: str) -> str:
    lowered = str(purpose or "").strip().lower()
    if (
        lowered.startswith("hf-paper-l7-high-reasoning")
        or lowered.startswith("hf-paper-report-plan")
        or lowered.startswith("hf-paper-report-section")
    ):
        return "hf_paper_insight"
    if lowered.startswith("github-trend-report"):
        return "github_trend_report"
    if lowered.startswith("ai-influence-report"):
        return "ai_influence_report"
    return "default"


def _merge_policy(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in (override or {}).items():
        merged[key] = value
    return merged


def _pick_profile_from_pool(purpose: str, allowed_profiles: list[str], selection: str) -> str:
    clean = [item for item in allowed_profiles if str(item).strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if selection == "first":
        return clean[0]
    digest = hashlib.sha256(str(purpose or "").encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(clean)
    return clean[index]


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


def apply_profile_policy(env: dict[str, str], *, purpose: str) -> dict[str, Any]:
    loaded = _load_profile_policy()
    if not loaded:
        return {
            "enabled": False,
            "policy_key": "default",
            "policy_path": "",
            "selected_profile_directory": env.get("BROWSER_AGENT_PROFILE_DIRECTORY") or "",
            "selected_account_email": env.get("BROWSER_AGENT_CHATGPT_ACCOUNT_EMAIL")
            or env.get("BROWSER_AGENT_TARGET_ACCOUNT_EMAIL")
            or "",
            "allowed_profiles": [],
        }

    policies = loaded["policies"]
    key = _policy_key_for_purpose(purpose)
    default_policy = policies.get("default") if isinstance(policies.get("default"), dict) else {}
    scoped_policy = policies.get(key) if isinstance(policies.get(key), dict) else {}
    policy = _merge_policy(default_policy, scoped_policy)
    allowed_profiles = [str(item).strip() for item in (policy.get("allowed_profiles") or []) if str(item).strip()]
    expected_account_email = str(policy.get("expected_account_email") or "").strip()
    selection = str(policy.get("selection") or "hash").strip().lower()
    profile_strategy = str(policy.get("profile_strategy") or "persistent").strip().lower()
    user_data_dir = str(policy.get("user_data_dir") or "").strip()
    explicit_profile = str(env.get("BROWSER_AGENT_PROFILE_DIRECTORY") or "").strip()
    explicit_account = str(
        env.get("BROWSER_AGENT_CHATGPT_ACCOUNT_EMAIL")
        or env.get("BROWSER_AGENT_TARGET_ACCOUNT_EMAIL")
        or ""
    ).strip()

    if expected_account_email and explicit_account and explicit_account.lower() != expected_account_email.lower():
        raise RuntimeError(
            "browser_agent_profile_policy_account_mismatch:"
            f"purpose={purpose or 'N/A'}:expected={expected_account_email}:actual={explicit_account}"
        )
    if allowed_profiles and explicit_profile and explicit_profile not in allowed_profiles:
        raise RuntimeError(
            "browser_agent_profile_policy_profile_mismatch:"
            f"purpose={purpose or 'N/A'}:allowed={','.join(allowed_profiles)}:actual={explicit_profile}"
        )

    resolved_profile = explicit_profile or _pick_profile_from_pool(purpose, allowed_profiles, selection)
    resolved_account = explicit_account or expected_account_email
    if allowed_profiles and not resolved_profile:
        raise RuntimeError(
            "browser_agent_profile_policy_missing_profile:"
            f"purpose={purpose or 'N/A'}:allowed={','.join(allowed_profiles)}"
        )
    if expected_account_email and not resolved_account:
        raise RuntimeError(
            "browser_agent_profile_policy_missing_account:"
            f"purpose={purpose or 'N/A'}:expected={expected_account_email}"
        )
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
    force_headed = bool(policy.get("force_headed") or policy.get("require_headed"))
    if _is_protected_scoped_chatgpt(key) and force_headed:
        env["BROWSER_AGENT_HEADLESS"] = "false"
        env["TECH_HOTSPOT_BROWSER_CHATGPT_HEADLESS"] = "false"
        env["BROWSER_AGENT_CHATGPT_ALLOW_HEADED"] = "true"
        env["TECH_HOTSPOT_BROWSER_CHATGPT_ALLOW_HEADED"] = "true"
        env["BROWSER_AGENT_ALLOW_HEADED"] = "true"
    env["BROWSER_AGENT_CHATGPT_PROFILE_POLICY_KEY"] = key

    return {
        "enabled": True,
        "policy_key": key,
        "policy_path": str(loaded.get("path") or ""),
        "selected_profile_directory": resolved_profile,
        "selected_account_email": resolved_account,
        "allowed_profiles": allowed_profiles,
        "selection": selection,
        "profile_strategy": profile_strategy,
        "user_data_dir_set": bool(env.get("BROWSER_AGENT_USER_DATA_DIR")),
        "headless_forced": _is_protected_scoped_chatgpt(key) and force_headed,
    }


def stage_policy(kind: str, expected: str) -> dict[str, Any]:
    if kind == "planner":
        return {
            "display_name": "ChatGPT Report Planner",
            "model_mode": "thinking",
            "reasoning_effort": "high",
            "tool_mode": "none",
            "model": os.environ.get("CHATGPT_REPORT_PLANNER_MODEL") or os.environ.get("CHATGPT_MODEL") or "chatgpt-5.5",
            "instruction": (
            "你是 ChatGPT Report Planner。你的任务不是写正文，而是输出可执行的报告规划。"
            "必须规划：报告拆成几章、每章几节、每节写什么、素材约束、风格约束、证据使用规则、"
            "禁止事项、最终输出格式。风格约束必须包含：禁止使用“更硬”；“信号”只能少量使用，"
            "优先改成“迹象 / 线索 / 依据 / 变化 / 材料 / 观察点”。如果素材是大咖访谈、播客、圆桌、keynote 或具名专家演讲，"
            "必须规划“访谈原意摘要与观点归纳”章节，先还原嘉宾观点、论证顺序、例子和保留意见，再规划趋势分析。"
            "若 expected_output=json，必须只输出 JSON。"
            ),
        }
    if kind == "deep_writer":
        return {
            "display_name": "ChatGPT Report Deep Writer",
            "model_mode": "pro",
            "reasoning_effort": "deep_research",
            "tool_mode": "deep_research",
            "model": os.environ.get("CHATGPT_REPORT_DEEP_MODEL") or os.environ.get("CHATGPT_MODEL") or "chatgpt-pro",
            "instruction": (
            "你是 ChatGPT Report Deep Writer。你必须使用 Pro / Deep Research 模式处理长程研究写作。"
            "如果界面提出研究澄清问题，应选择继续研究、扩大证据覆盖、保持技术分析深度，"
            "不要请求人工介入。输出必须是可直接发布的深度研究章节或报告。"
            "文风必须克制、自然，禁止使用“更硬”；“信号”只能少量使用，优先写成迹象、线索、依据或变化。"
            "禁止输出 `**判断：**`、`**证据链：**` 这类 Markdown 加粗标签；需要强调时用自然小标题或普通段落。"
            ),
        }
    return {
        "display_name": "ChatGPT Report Chapter Writer",
        "model_mode": "thinking",
        "reasoning_effort": "high",
        "tool_mode": "none",
        "model": os.environ.get("CHATGPT_REPORT_CHAPTER_MODEL") or os.environ.get("CHATGPT_MODEL") or "chatgpt-5.5",
        "instruction": (
            "你是 ChatGPT Report Chapter Writer。你只写当前指定章节，不重写整份报告规划。"
            "必须严格遵守 Planner 给出的章节目标、风格、约束和素材边界；必须把素材转成面向读者的判断，"
            "不要输出内部处理字段、video_id、transcript_status、raw id。"
            "如果当前章节是访谈/对谈/演讲摘要，必须先忠实呈现嘉宾或主讲人的原始观点结构、论据、例子和边界，"
            "明确区分嘉宾原意和报告作者判断，不要一上来改写成宏观趋势。"
            "文风必须克制、自然，禁止使用“更硬”；“信号”只能少量使用，优先写成迹象、线索、依据或变化。"
            "禁止输出 `**判断：**`、`**证据链：**` 这类 Markdown 加粗标签；需要强调时用自然小标题或普通段落。"
        ),
    }


def build_prompt(user_prompt: str, *, kind: str, expected: str, purpose: str) -> str:
    policy = stage_policy(kind, expected)
    return "\n\n".join(
        [
            f"# {policy['display_name']} 固化执行协议",
            f"- operator_kind: {kind}",
            f"- purpose: {purpose or 'N/A'}",
            f"- expected_output: {expected}",
            f"- model_mode: {policy['model_mode']}",
            f"- reasoning_effort: {policy['reasoning_effort']}",
            "",
            "## 必须遵守",
            policy["instruction"],
            "所有结论必须来自用户输入或上游算子提供的素材；不能编造素材；不能暴露内部流水线字段。",
            "如果信息不足，要明确写成限制或待验证事项，而不是补故事。",
            "",
            "## 用户/上游输入",
            user_prompt.strip(),
        ]
    )


def run_wrapper_process(cmd: list[str], *, prompt: str, env: dict[str, str], timeout: int) -> tuple[int, str]:
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        start_new_session=True,
    )
    try:
        stdout, _ = proc.communicate(prompt, timeout=timeout)
        return proc.returncode or 0, stdout or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            proc.terminate()
        try:
            stdout, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                proc.kill()
            stdout, _ = proc.communicate()
        return 124, (stdout or "") + f"\nchatgpt_report_operator: wrapper timed out after {timeout}s"


def main() -> int:
    user_prompt = sys.stdin.read()
    action = (os.environ.get("CHATGPT_REPORT_ACTION") or "run").strip().lower()
    if action not in {"run", "submit", "poll", "collect"}:
        print(f"chatgpt_report_operator: invalid CHATGPT_REPORT_ACTION={action}", file=sys.stderr)
        return 2
    if not user_prompt.strip() and action not in {"poll", "collect"}:
        print("chatgpt_report_operator: stdin prompt is empty", file=sys.stderr)
        return 2
    expected = (os.environ.get("BROWSER_AGENT_EXPECTED_OUTPUT") or "markdown").strip().lower()
    purpose = (os.environ.get("BROWSER_AGENT_PURPOSE") or "").strip()
    kind = infer_kind(purpose, os.environ.get("CHATGPT_REPORT_OPERATOR_KIND", ""))
    policy = stage_policy(kind, expected)
    prompt = build_prompt(user_prompt, kind=kind, expected=expected, purpose=purpose) if user_prompt.strip() else "poll/collect"
    cmd = wrapper_cmd()
    if not cmd:
        print("chatgpt_report_operator: Browser Agent ChatGPT wrapper not configured", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env.update(
        {
            "CHATGPT_MODEL": str(policy["model"]),
            "CHATGPT_REASONING_EFFORT": str(policy["reasoning_effort"]),
            "BROWSER_AGENT_EXPECTED_OUTPUT": expected,
            "BROWSER_AGENT_CHATGPT_MODEL_MODE": str(policy["model_mode"]),
            "BROWSER_AGENT_CHATGPT_TOOL_MODE": str(policy["tool_mode"]),
            "BROWSER_AGENT_CHATGPT_PROJECT_NAME": env.get("BROWSER_AGENT_CHATGPT_PROJECT_NAME") or DEFAULT_PROJECT_NAME,
            "BROWSER_AGENT_CHATGPT_OPEN_PROJECT_FIRST": env.get("BROWSER_AGENT_CHATGPT_OPEN_PROJECT_FIRST") or "true",
            "BROWSER_AGENT_CHATGPT_REQUIRE_PROJECT": env.get("BROWSER_AGENT_CHATGPT_REQUIRE_PROJECT") or "true",
            "BROWSER_AGENT_CHATGPT_ACTION": action,
        }
    )
    try:
        policy_meta = apply_profile_policy(env, purpose=purpose)
    except RuntimeError as exc:
        print(f"chatgpt_report_operator: {exc}", file=sys.stderr)
        return 2
    if kind == "deep_writer":
        env["BROWSER_AGENT_CHATGPT_REQUIRE_DEEP_RESEARCH"] = (
            env.get("BROWSER_AGENT_CHATGPT_REQUIRE_DEEP_RESEARCH") or "true"
        )
    else:
        env["BROWSER_AGENT_CHATGPT_REQUIRE_UI_MODE"] = (
            env.get("BROWSER_AGENT_CHATGPT_REQUIRE_UI_MODE") or "true"
        )
    request_dir = env.get("BROWSER_AGENT_REQUEST_DIR")
    if request_dir:
        Path(request_dir).expanduser().mkdir(parents=True, exist_ok=True)
        (Path(request_dir).expanduser() / "report-operator-request.json").write_text(
            json.dumps(
                {
                    "operator_kind": kind,
                    "display_name": policy["display_name"],
                    "expected_output": expected,
                    "purpose": purpose,
                    "model": policy["model"],
                    "model_mode": policy["model_mode"],
                    "reasoning_effort": policy["reasoning_effort"],
                    "tool_mode": policy["tool_mode"],
                    "project_name": env.get("BROWSER_AGENT_CHATGPT_PROJECT_NAME") or DEFAULT_PROJECT_NAME,
                    "profile_directory": env.get("BROWSER_AGENT_PROFILE_DIRECTORY") or "",
                    "target_account_email": env.get("BROWSER_AGENT_CHATGPT_ACCOUNT_EMAIL")
                    or env.get("BROWSER_AGENT_TARGET_ACCOUNT_EMAIL")
                    or "",
                    "profile_policy": policy_meta,
                    "account_email_hint_present": bool(
                        env.get("BROWSER_AGENT_CHATGPT_ACCOUNT_EMAIL")
                        or env.get("BROWSER_AGENT_TARGET_ACCOUNT_EMAIL")
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if action in {"poll", "collect"} and not env.get("BROWSER_AGENT_CHATGPT_CONVERSATION_URL"):
            submitted_path = Path(request_dir).expanduser() / "submitted-run.json"
            if submitted_path.exists():
                try:
                    submitted = json.loads(submitted_path.read_text(encoding="utf-8"))
                    if submitted.get("url"):
                        env["BROWSER_AGENT_CHATGPT_CONVERSATION_URL"] = str(submitted["url"])
                except Exception:
                    pass

    timeout = int(env.get("BROWSER_AGENT_CHATGPT_TIMEOUT") or ("7200" if kind == "deep_writer" else "1800"))
    returncode, raw_output = run_wrapper_process(cmd, prompt=prompt, env=env, timeout=timeout)
    output = (raw_output or "").strip()
    if returncode != 0:
        print(output, file=sys.stderr)
        return returncode
    if kind == "deep_writer":
        if not request_dir:
            print("chatgpt_report_operator: deep_writer missing BROWSER_AGENT_REQUEST_DIR for Deep Research proof", file=sys.stderr)
            return 1
        proof_path = Path(request_dir).expanduser() / "deep-research-state.json"
        if not proof_path.exists():
            print(
                "chatgpt_report_operator: deep_writer did not produce deep-research-state.json; "
                "normal chat output is not accepted as Deep Research",
                file=sys.stderr,
            )
            return 1
        try:
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"chatgpt_report_operator: invalid deep-research-state.json: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        if not proof.get("ok"):
            print(
                "chatgpt_report_operator: Deep Research mode not confirmed: "
                + json.dumps(proof, ensure_ascii=False),
                file=sys.stderr,
            )
            return 1
    else:
        if not request_dir:
            print("chatgpt_report_operator: missing BROWSER_AGENT_REQUEST_DIR for UI mode proof", file=sys.stderr)
            return 1
        request_path = Path(request_dir).expanduser()
        proof_path = request_path / "chatgpt-mode-state.json"
        post_submit_proof_path = request_path / "chatgpt-mode-post-submit-state.json"
        if not proof_path.exists():
            print(
                "chatgpt_report_operator: planner/chapter did not produce chatgpt-mode-state.json; "
                "normal ChatGPT output is not accepted as Thinking High",
                file=sys.stderr,
            )
            return 1
        try:
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"chatgpt_report_operator: invalid chatgpt-mode-state.json: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        if not proof.get("ok"):
            if post_submit_proof_path.exists():
                try:
                    post_submit_proof = json.loads(post_submit_proof_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    print(f"chatgpt_report_operator: invalid chatgpt-mode-post-submit-state.json: {type(exc).__name__}: {exc}", file=sys.stderr)
                    return 1
                if post_submit_proof.get("ok"):
                    proof = post_submit_proof
                else:
                    print(
                        "chatgpt_report_operator: required ChatGPT UI mode not confirmed: "
                        + json.dumps(post_submit_proof, ensure_ascii=False),
                        file=sys.stderr,
                    )
                    return 1
            else:
                print(
                    "chatgpt_report_operator: required ChatGPT UI mode not confirmed: "
                    + json.dumps(proof, ensure_ascii=False),
                    file=sys.stderr,
                )
                return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
