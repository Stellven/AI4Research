#!/usr/bin/env python3
"""Gemini enhanced search pipeline with prompt rewrite + deep research stages."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_GEM_NAME = "李教授提示词大师"
DEFAULT_PRINT_TIMEOUT = "10m"
DEFAULT_SUBPROCESS_TIMEOUT_SEC = 900
DEFAULT_REWRITE_MODEL = "gemini-3.5-flash-high"
DEFAULT_RESEARCH_MODEL = "gemini-3.1-pro"
REWRITE_CMD_ENV = "SOLAR_GEMINI_GEM_REWRITE_CMD"
RESEARCH_CMD_ENV = "SOLAR_GEMINI_DEEP_RESEARCH_CMD"
REQUIRE_DIRECT_GEM_ENV = "SOLAR_GEMINI_REQUIRE_DIRECT_GEM"
QUOTA_RE = re.compile(r"RESOURCE_EXHAUSTED|quota|rate[- ]?limit|429|resets in", re.I)
AUTH_RE = re.compile(r"not logged in|auth(?:entication)? failed|oauth|permission denied", re.I)
JSON_FENCE_RE = re.compile(r"```json\s*(.*?)\s*```", re.S | re.I)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _agy_path() -> str:
    return os.environ.get("AGY_BIN") or shutil.which("agy") or "~/.local/bin/agy"


def _doctor() -> dict[str, Any]:
    agy = _agy_path()
    agy_exists = Path(agy).exists() if agy.startswith("/") else bool(shutil.which(agy))
    rewrite_template = bool(str(os.environ.get(REWRITE_CMD_ENV) or "").strip())
    research_template = bool(str(os.environ.get(RESEARCH_CMD_ENV) or "").strip())
    require_direct = _truthy(os.environ.get(REQUIRE_DIRECT_GEM_ENV))
    return {
        "ok": bool(agy_exists or (rewrite_template and research_template)),
        "runner": {
            "agy_path": agy if agy_exists else "",
            "agy_ready": agy_exists,
        },
        "stages": {
            "rewrite": {
                "mode": "command_template" if rewrite_template else "persona_fallback",
                "direct_gem_ready": rewrite_template,
            },
            "research": {
                "mode": "command_template" if research_template else "agy_prompt",
                "direct_research_ready": research_template,
            },
        },
        "policy": {
            "require_direct_gem": require_direct,
        },
    }


def _extract_json_text(text: str) -> str:
    fenced = JSON_FENCE_RE.search(text or "")
    if fenced:
        return fenced.group(1).strip()
    start = -1
    depth = 0
    for i, char in enumerate(text or ""):
        if char == "{":
            if depth == 0:
                start = i
            depth += 1
        elif char == "}":
            if depth:
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = (text or "")[start : i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except Exception:
                        start = -1
    raise ValueError("No valid JSON object found in model output")


def _parse_json_payload(text: str) -> dict[str, Any]:
    payload = json.loads(_extract_json_text(text))
    if not isinstance(payload, dict):
        raise ValueError("Model output JSON must be an object")
    return payload


def _normalize_citations(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        rows.append(
            {
                "title": str(item.get("title") or "").strip(),
                "url": url,
                "publisher": str(item.get("publisher") or "").strip(),
                "why_relevant": str(item.get("why_relevant") or "").strip(),
            }
        )
    return rows


def _build_rewrite_prompt(input_prompt: str, gem_name: str) -> str:
    return "\n".join(
        [
            "你现在负责 Gemini 增强搜索链的第一阶段：提示词改写。",
            f"目标 Gem 名称：{gem_name}",
            "如果当前运行时无法直接调用保存的 Gem，请等价模拟这个 Gem 的职责，而不是解释限制。",
            "请把用户原始请求改写成更适合 Gemini Deep Research 的高质量研究提示词。",
            "改写时请补足：研究目标、关键比较维度、证据要求、时间边界、反例/争议、输出结构。",
            "不要开始分析任务本身。",
            "只输出 JSON，不要输出额外说明。",
            'JSON schema: {"rewritten_prompt":"string","rewrite_notes":["string"],"search_focus":["string"]}',
            "",
            "用户原始请求：",
            input_prompt.strip(),
        ]
    )


def _build_research_prompt(original_prompt: str, rewritten_prompt: str) -> str:
    return "\n".join(
        [
            "你现在负责 Gemini 增强搜索链的第二阶段：Deep Research 风格分析。",
            "请基于下面的改写提示词完成高质量研究分析，并给出可点击的引用源链接。",
            "输出必须只包含 JSON，不要有额外前后缀。",
            "要求：",
            "- `analysis_markdown` 用 Markdown，直接给后续流程消费。",
            "- `citations` 必须只保留真实引用源链接。",
            "- `citations` 每项包含 `title`、`url`、可选 `publisher`、`why_relevant`。",
            "- 如果某个结论没有把握，请在分析正文里明确不确定性。",
            'JSON schema: {"analysis_markdown":"string","citations":[{"title":"string","url":"string","publisher":"string","why_relevant":"string"}]}',
            "",
            "原始请求：",
            original_prompt.strip(),
            "",
            "改写后的 Deep Research 提示词：",
            rewritten_prompt.strip(),
        ]
    )


def _write_temp_prompt(prompt: str) -> Path:
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".prompt.txt", delete=False)
    with handle:
        handle.write(prompt)
    return Path(handle.name)


def _run_shell_stage(
    command: str,
    *,
    stage: str,
    prompt_file: Path,
    gem_name: str,
    model: str,
    print_timeout: str,
    subprocess_timeout_sec: int,
) -> tuple[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "SOLAR_GEMINI_STAGE": stage,
            "SOLAR_GEMINI_STAGE_PROMPT_FILE": str(prompt_file),
            "SOLAR_GEMINI_GEM_NAME": gem_name,
            "SOLAR_GEMINI_MODEL": model,
            "SOLAR_GEMINI_PRINT_TIMEOUT": print_timeout,
        }
    )
    proc = subprocess.run(
        ["bash", "-lc", command],
        text=True,
        capture_output=True,
        env=env,
        timeout=subprocess_timeout_sec,
    )
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        raise RuntimeError(f"{stage} command template failed: rc={proc.returncode} output={output[-800:]}")
    return output, "command_template"


def _run_agy_stage(
    prompt: str,
    *,
    stage: str,
    model: str,
    print_timeout: str,
    subprocess_timeout_sec: int,
) -> tuple[str, str]:
    agy = _agy_path()
    cmd = [
        agy,
        "--dangerously-skip-permissions",
        "--print-timeout",
        print_timeout,
        "--print",
        prompt,
    ]
    env = dict(os.environ)
    env.setdefault("AGY_MODEL", model)
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        env=env,
        timeout=subprocess_timeout_sec,
    )
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        raise RuntimeError(f"{stage} agy call failed: rc={proc.returncode} output={output[-800:]}")
    if QUOTA_RE.search(output):
        raise RuntimeError(f"{stage} failed: Gemini quota exhausted")
    if AUTH_RE.search(output):
        raise RuntimeError(f"{stage} failed: Gemini auth expired")
    return output, "agy_prompt"


def _run_rewrite_stage(
    input_prompt: str,
    *,
    gem_name: str,
    rewrite_model: str,
    print_timeout: str,
    subprocess_timeout_sec: int,
    require_direct_gem: bool,
) -> tuple[dict[str, Any], dict[str, str]]:
    template = str(os.environ.get(REWRITE_CMD_ENV) or "").strip()
    rewrite_prompt = _build_rewrite_prompt(input_prompt, gem_name)
    prompt_file = _write_temp_prompt(rewrite_prompt)
    try:
        if template:
            output, mode = _run_shell_stage(
                template,
                stage="rewrite",
                prompt_file=prompt_file,
                gem_name=gem_name,
                model=rewrite_model,
                print_timeout=print_timeout,
                subprocess_timeout_sec=subprocess_timeout_sec,
            )
        else:
            if require_direct_gem:
                raise RuntimeError("direct Gem invocation required but no SOLAR_GEMINI_GEM_REWRITE_CMD configured")
            output, mode = _run_agy_stage(
                rewrite_prompt,
                stage="rewrite",
                model=rewrite_model,
                print_timeout=print_timeout,
                subprocess_timeout_sec=subprocess_timeout_sec,
            )
        payload = _parse_json_payload(output)
        rewritten_prompt = str(payload.get("rewritten_prompt") or "").strip()
        if not rewritten_prompt:
            raise ValueError("rewrite stage returned empty rewritten_prompt")
        return payload, {"mode": mode, "model": rewrite_model}
    finally:
        prompt_file.unlink(missing_ok=True)


def _run_research_stage(
    original_prompt: str,
    rewritten_prompt: str,
    *,
    gem_name: str,
    research_model: str,
    print_timeout: str,
    subprocess_timeout_sec: int,
) -> tuple[dict[str, Any], dict[str, str]]:
    template = str(os.environ.get(RESEARCH_CMD_ENV) or "").strip()
    research_prompt = _build_research_prompt(original_prompt, rewritten_prompt)
    prompt_file = _write_temp_prompt(research_prompt)
    try:
        if template:
            output, mode = _run_shell_stage(
                template,
                stage="deep_research",
                prompt_file=prompt_file,
                gem_name=gem_name,
                model=research_model,
                print_timeout=print_timeout,
                subprocess_timeout_sec=subprocess_timeout_sec,
            )
        else:
            output, mode = _run_agy_stage(
                research_prompt,
                stage="deep_research",
                model=research_model,
                print_timeout=print_timeout,
                subprocess_timeout_sec=subprocess_timeout_sec,
            )
        payload = _parse_json_payload(output)
        analysis_markdown = str(payload.get("analysis_markdown") or "").strip()
        if not analysis_markdown:
            raise ValueError("deep research stage returned empty analysis_markdown")
        payload["citations"] = _normalize_citations(payload.get("citations"))
        return payload, {"mode": mode, "model": research_model}
    finally:
        prompt_file.unlink(missing_ok=True)


def run_pipeline(
    input_prompt: str,
    *,
    gem_name: str = DEFAULT_GEM_NAME,
    rewrite_model: str = DEFAULT_REWRITE_MODEL,
    research_model: str = DEFAULT_RESEARCH_MODEL,
    print_timeout: str = DEFAULT_PRINT_TIMEOUT,
    subprocess_timeout_sec: int = DEFAULT_SUBPROCESS_TIMEOUT_SEC,
    require_direct_gem: bool = False,
) -> dict[str, Any]:
    rewrite_payload, rewrite_meta = _run_rewrite_stage(
        input_prompt,
        gem_name=gem_name,
        rewrite_model=rewrite_model,
        print_timeout=print_timeout,
        subprocess_timeout_sec=subprocess_timeout_sec,
        require_direct_gem=require_direct_gem,
    )
    rewritten_prompt = str(rewrite_payload["rewritten_prompt"]).strip()
    research_payload, research_meta = _run_research_stage(
        input_prompt,
        rewritten_prompt,
        gem_name=gem_name,
        research_model=research_model,
        print_timeout=print_timeout,
        subprocess_timeout_sec=subprocess_timeout_sec,
    )
    return {
        "ok": True,
        "gem_name": gem_name,
        "input_prompt": input_prompt,
        "rewritten_prompt": rewritten_prompt,
        "rewrite_notes": rewrite_payload.get("rewrite_notes") or [],
        "search_focus": rewrite_payload.get("search_focus") or [],
        "analysis_markdown": str(research_payload.get("analysis_markdown") or "").strip(),
        "citations": _normalize_citations(research_payload.get("citations")),
        "provider_metadata": {
            "rewrite": rewrite_meta,
            "deep_research": research_meta,
            "require_direct_gem": require_direct_gem,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gemini_enhanced_search.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    run = sub.add_parser("run")
    run.add_argument("--prompt-file", required=True)
    run.add_argument("--gem-name", default=os.environ.get("SOLAR_GEMINI_GEM_NAME", DEFAULT_GEM_NAME))
    run.add_argument("--rewrite-model", default=os.environ.get("SOLAR_GEMINI_REWRITE_MODEL", DEFAULT_REWRITE_MODEL))
    run.add_argument("--research-model", default=os.environ.get("SOLAR_GEMINI_RESEARCH_MODEL", DEFAULT_RESEARCH_MODEL))
    run.add_argument("--print-timeout", default=os.environ.get("SOLAR_GEMINI_ENHANCED_PRINT_TIMEOUT", DEFAULT_PRINT_TIMEOUT))
    run.add_argument("--subprocess-timeout-sec", type=int, default=int(os.environ.get("SOLAR_GEMINI_ENHANCED_TIMEOUT_SEC", DEFAULT_SUBPROCESS_TIMEOUT_SEC)))
    run.add_argument("--require-direct-gem", action="store_true", default=_truthy(os.environ.get(REQUIRE_DIRECT_GEM_ENV)))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "doctor":
        payload = _doctor()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") else 1

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    payload = run_pipeline(
        prompt,
        gem_name=args.gem_name,
        rewrite_model=args.rewrite_model,
        research_model=args.research_model,
        print_timeout=args.print_timeout,
        subprocess_timeout_sec=args.subprocess_timeout_sec,
        require_direct_gem=args.require_direct_gem,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
