"""DeepDive-only brief expansion.

This intentionally copies the raw-requirement expansion idea from the normal
requirement pipeline, but keeps routing, schema, and artifacts separate so
DeepDive cannot contaminate PM/Planner requirement compilation.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "solar.deepdive.brief_expansion.v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: str) -> str:
    return "\n".join(line.rstrip() for line in str(value or "").strip().splitlines()).strip()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_deepdive_expansion_prompt(raw_brief: str) -> str:
    brief = _normalize_text(raw_brief)
    return "\n".join(
        [
            "# DeepDiveBriefExpander 固化执行协议",
            "",
            "你是 DeepDiveBriefExpander，只服务 DeepDive 研究任务启动入口。",
            "你的任务是把用户原始研究 brief 展开成适合 source/evidence/chapter/chief-editor 流程执行的研究 brief。",
            "",
            "必须遵守：",
            "1. 只扩展研究问题、证据范围、章节目标、反证边界和质量要求。",
            "2. 不输出普通需求管道 schema，不写 raw_intent/requirement_ir，不提 PM/Planner 路由。",
            "3. 不把 DeepDive 任务改写成开发 sprint。",
            "4. 信息不足时写成 evidence_gap 或待验证事项，不补故事。",
            "",
            "输出 Markdown，建议包含：",
            "- 研究目标",
            "- 核心问题",
            "- 证据范围",
            "- 章节建议",
            "- 反证与边界",
            "- 质量门",
            "",
            "## 用户原始 brief",
            "",
            brief,
        ]
    ).strip() + "\n"


def _run_expander_command(prompt: str, output_dir: Path, timeout: int) -> dict[str, Any]:
    cmd = os.environ.get("SOLAR_DEEPDIVE_BRIEF_EXPANDER_CMD", "").strip()
    if not cmd:
        return {
            "attempted": False,
            "status": "deterministic_passthrough",
            "content": "",
            "reason": "SOLAR_DEEPDIVE_BRIEF_EXPANDER_CMD_not_set",
        }
    env = dict(os.environ)
    env["SOLAR_DEEPDIVE_BRIEF_EXPANDER_PROMPT"] = str(output_dir / "deepdive_brief_expansion_prompt.md")
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"attempted": True, "status": "timeout", "content": ""}
    content = (proc.stdout or "").strip()
    return {
        "attempted": True,
        "status": "ok" if proc.returncode == 0 and content else "failed",
        "exit_code": proc.returncode,
        "stderr_tail": (proc.stderr or "")[-2000:],
        "content": content,
    }


def expand_deepdive_brief(
    raw_brief: str,
    output_dir: str | Path,
    *,
    timeout: int | None = None,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_text(raw_brief)
    if not normalized:
        raise ValueError("raw_brief is required")

    prompt = build_deepdive_expansion_prompt(normalized)
    prompt_path = root / "deepdive_brief_expansion_prompt.md"
    md_path = root / "deepdive_brief_expansion.md"
    json_path = root / "deepdive_brief_expansion.json"
    prompt_path.write_text(prompt, encoding="utf-8")

    result = _run_expander_command(
        prompt,
        root,
        int(timeout if timeout is not None else os.environ.get("SOLAR_DEEPDIVE_BRIEF_EXPANDER_TIMEOUT_SEC", "900") or "900"),
    )
    content = str(result.get("content") or "").strip()
    expanded = content or normalized
    md_path.write_text(expanded.rstrip() + "\n", encoding="utf-8")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "operator": "DeepDiveBriefExpander",
        "created_at": _now_iso(),
        "status": result.get("status"),
        "attempted": bool(result.get("attempted")),
        "raw_brief": normalized,
        "expanded_brief": expanded,
        "prompt_path": str(prompt_path),
        "output_md_path": str(md_path),
        "normal_requirement_pipeline_import_allowed": False,
        "result_meta": {k: v for k, v in result.items() if k != "content"},
    }
    write_json(json_path, payload)
    payload["output_json_path"] = str(json_path)
    return payload
