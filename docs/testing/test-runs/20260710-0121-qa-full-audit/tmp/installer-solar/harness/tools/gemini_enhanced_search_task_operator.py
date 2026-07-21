#!/usr/bin/env python3
"""Command backend adapter for Gemini enhanced-search logical operator tasks."""
from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

import gemini_enhanced_search as ges  # noqa: E402
import operator_flow_control as ofc  # noqa: E402


DEFAULT_OPERATOR_ID = "mini-gemini-enhanced-search"


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


def _operator_id(envelope: dict[str, Any]) -> str:
    value = str(envelope.get("operator_id") or "").strip()
    return value or DEFAULT_OPERATOR_ID


def _request_payload_from_file(path_value: str) -> dict[str, Any]:
    payload = json.loads(Path(path_value).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("gemini enhanced search request file must contain JSON object")
    return payload


def build_request(envelope: dict[str, Any], *, task_dir: Path | None = None) -> dict[str, Any]:
    raw = envelope.get("gemini_enhanced_search_request")
    if isinstance(raw, dict):
        request = deepcopy(raw)
    else:
        file_ref = str(envelope.get("gemini_enhanced_search_request_file") or "").strip()
        if file_ref:
            request = _request_payload_from_file(file_ref)
        else:
            request = {}
            for key in (
                "prompt",
                "prompt_file",
                "gem_name",
                "rewrite_model",
                "research_model",
                "print_timeout",
                "subprocess_timeout_sec",
                "require_direct_gem",
            ):
                if key in envelope:
                    request[key] = deepcopy(envelope[key])
    if not str(request.get("prompt") or "").strip():
        prompt_file = str(request.get("prompt_file") or envelope.get("prompt_file") or "").strip()
        if prompt_file:
            request["prompt"] = Path(prompt_file).expanduser().read_text(encoding="utf-8")
    if task_dir is not None:
        request.setdefault("output_dir", str(task_dir.resolve()))
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
            envelope.get("gemini_success_cooldown_seconds")
            or os.environ.get("SOLAR_GEMINI_SUCCESS_COOLDOWN_SECONDS")
            or flow_control.get("success_cooldown_seconds"),
            180,
        ),
        "rate_limit_cooldown_seconds": ofc.int_value(
            envelope.get("gemini_rate_limit_cooldown_seconds")
            or os.environ.get("SOLAR_GEMINI_RATE_LIMIT_COOLDOWN_SECONDS")
            or flow_control.get("rate_limit_cooldown_seconds"),
            3600,
        ),
        "auth_cooldown_seconds": ofc.int_value(
            envelope.get("gemini_auth_cooldown_seconds")
            or os.environ.get("SOLAR_GEMINI_AUTH_COOLDOWN_SECONDS")
            or flow_control.get("auth_cooldown_seconds"),
            21600,
        ),
        "defer_on_cooldown": ofc.bool_value(
            envelope.get("gemini_defer_on_cooldown")
            or os.environ.get("SOLAR_GEMINI_DEFER_ON_COOLDOWN")
            or flow_control.get("defer_on_cooldown"),
            True,
        ),
        "defer_on_auth": ofc.bool_value(
            envelope.get("gemini_defer_on_auth")
            or os.environ.get("SOLAR_GEMINI_DEFER_ON_AUTH")
            or flow_control.get("defer_on_auth"),
            True,
        ),
    }


def _summary_markdown(response: dict[str, Any]) -> str:
    citations = response.get("citations") if isinstance(response.get("citations"), list) else []
    lines = [
        "# Gemini Enhanced Search Result",
        "",
        "## 已完成",
        f"- gem_name: {response.get('gem_name') or 'N/A'}",
        f"- rewritten_prompt_chars: {len(str(response.get('rewritten_prompt') or ''))}",
        f"- citation_count: {len(citations)}",
        "",
        "## 说明",
        "- 输出已包含改写后的提示词、Deep Research 分析和引用链接。",
    ]
    return "\n".join(lines)


def run_request(request: dict[str, Any], *, task_dir: Path) -> dict[str, Any]:
    prompt = str(request.get("prompt") or "").strip()
    if not prompt:
        raise RuntimeError("Gemini enhanced search requires prompt")
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "gemini-enhanced-search-request.json").write_text(
        json.dumps(request, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (task_dir / "gemini-enhanced-search-prompt.txt").write_text(prompt, encoding="utf-8")
    result = ges.run_pipeline(
        prompt,
        gem_name=str(request.get("gem_name") or ges.DEFAULT_GEM_NAME),
        rewrite_model=str(request.get("rewrite_model") or ges.DEFAULT_REWRITE_MODEL),
        research_model=str(request.get("research_model") or ges.DEFAULT_RESEARCH_MODEL),
        print_timeout=str(request.get("print_timeout") or ges.DEFAULT_PRINT_TIMEOUT),
        subprocess_timeout_sec=ofc.int_value(
            request.get("subprocess_timeout_sec"),
            ges.DEFAULT_SUBPROCESS_TIMEOUT_SEC,
        ),
        require_direct_gem=ofc.bool_value(
            request.get("require_direct_gem"),
            ofc.bool_value(os.environ.get(ges.REQUIRE_DIRECT_GEM_ENV), False),
        ),
    )
    (task_dir / "gemini-enhanced-search-result.json").write_text(
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
        decision = ofc.apply_failure_flow_control(
            task_dir,
            operator_id=operator_id,
            failure_text=str(exc),
            rate_limit_cooldown_seconds=int(rate_control.get("rate_limit_cooldown_seconds") or 0),
            auth_cooldown_seconds=int(rate_control.get("auth_cooldown_seconds") or 0),
            defer_on_cooldown=bool(rate_control.get("defer_on_cooldown")),
            defer_on_auth=bool(rate_control.get("defer_on_auth")),
        )
        print(
            "gemini_enhanced_search_task_operator failed: "
            f"{type(exc).__name__}: {exc} state={decision.get('runtime_state') or 'none'}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
