"""Chief-editor pass for human-readable survey reports."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from research.report_metrics import append_model_usage_event, build_model_usage_event, parse_model_cli_output


INTRO_HEADINGS = {"核心结论", "证据基础"}
FOOTNOTE_HEADING = "证据脚注"
FORBIDDEN_PATTERNS = [
    re.compile(r"\[claim:", re.I),
    re.compile(r"\[evidence:", re.I),
    re.compile(r"Prompt Packet", re.I),
    re.compile(r"Contribution Matrix", re.I),
    re.compile(r"Technical Summary", re.I),
    re.compile(r"Claim Map", re.I),
    re.compile(r"Evidence Map", re.I),
    re.compile(r"Source Map", re.I),
]

REPORT_SUFFIXES = {".md", ".json", ".jsonl", ".html"}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _split_h2(text: str) -> tuple[str, list[dict[str, str]], str]:
    title_match = re.match(r"(?s)\A(# .+?\n+)(.*)\Z", text or "")
    title = title_match.group(1).strip() if title_match else "# Professor-Grade Survey"
    body = title_match.group(2) if title_match else text
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", body or ""))
    if not matches:
        return title, [], ""
    sections: list[dict[str, str]] = []
    footnotes = ""
    for idx, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        block = body[start:end].strip()
        if heading == FOOTNOTE_HEADING:
            footnotes = f"## {heading}\n\n{block}".strip()
        else:
            sections.append({"heading": heading, "body": block})
    return title, sections, footnotes


def _chapter_prompt(title: str, heading: str, body: str) -> str:
    return f"""你是教授级技术 survey 的 chief editor。请把下面章节重写成自然、专业、可发表的中文章节。

硬规则：
- 只输出该章节 Markdown，从 `## {heading}` 开始。
- 保留事实边界、风险边界、脚注标记，例如 `[^1]`。
- 不要输出 Prompt Packet、Claim Map、Evidence Map、Source Map、Contribution Matrix。
- 不要出现 `[claim:...]` 或 `[evidence:...]` 调试标签。
- 不要编造论文、URL、benchmark 数字、发布日期。
- 删除“本节立场/本节绑定/本节通过”这类生成器口吻，改成自然论述。
- 保留明确判断、争议、局限和未解问题，不要写成宣传稿。

报告题目：
{title}

待重写章节：
## {heading}

{body}
"""


def _normalize_model_result(value: Any) -> tuple[str, dict[str, int]]:
    if isinstance(value, tuple) and len(value) == 2:
        text, usage = value
        return str(text), usage if isinstance(usage, dict) else {}
    return str(value), {}


def _run_command(command: str, prompt: str, timeout: int) -> tuple[str, dict[str, int]]:
    if not command.strip():
        raise RuntimeError("chief_editor_command_missing")
    result = subprocess.run(
        command,
        input=prompt,
        text=True,
        shell=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip().replace("\n", " ")[:500]
        raise RuntimeError(f"chief_editor_command_failed:{result.returncode}:{stderr}")
    output, usage, _ = parse_model_cli_output(result.stdout or "", result.stderr or "")
    if not output:
        raise RuntimeError("chief_editor_command_empty_stdout")
    return output, usage


def _run_claude(prompt: str, *, model: str, timeout: int, max_budget_usd: float) -> tuple[str, dict[str, int]]:
    claude = shutil.which("claude")
    if not claude:
        raise RuntimeError("claude_cli_missing")
    # Keep the Claude CLI invocation conservative. Some gateway-compatible
    # deployments reject client-only flags such as tool lists or budget caps.
    cmd = [
        claude,
        "--bare",
        "-p",
        "--output-format",
        "json",
        "--max-budget-usd",
        str(max_budget_usd),
        "--model",
        model,
    ]
    result = subprocess.run(cmd, input=prompt, text=True, capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().replace("\n", " ")[:500]
        raise RuntimeError(f"claude_cli_failed:{result.returncode}:{detail}")
    output, usage, _ = parse_model_cli_output(result.stdout or "", result.stderr or "")
    if not output:
        raise RuntimeError("claude_cli_empty_stdout")
    return output, usage


def _model_candidates(model: str, fallback_models: str) -> list[str]:
    candidates: list[str] = []
    for raw in [model, *re.split(r"[, ]+", fallback_models or "")]:
        item = raw.strip()
        if item and item not in candidates:
            candidates.append(item)
    return candidates or ["opus"]


def _quality_gate(text: str, chapter_headings: list[str], min_chars: int) -> dict[str, Any]:
    issues: list[str] = []
    if len(text) < min_chars:
        issues.append(f"chief_editor_chars_low:{len(text)}<{min_chars}")
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            issues.append(f"chief_editor_forbidden_pattern:{pattern.pattern}")
    missing = [heading for heading in chapter_headings if f"## {heading}" not in text]
    if missing:
        issues.append("chief_editor_missing_chapters:" + ",".join(missing[:8]))
    if len(re.findall(r"(?m)^##\s+", text)) < max(1, len(chapter_headings)):
        issues.append("chief_editor_heading_count_low")
    return {
        "ok": not issues,
        "char_count": len(text),
        "chapter_count": len(chapter_headings),
        "issues": issues,
    }


def _write_hitl(path: Path, payload: dict[str, Any], output_path: Path) -> None:
    issues = payload.get("quality_gate", {}).get("issues") or []
    lines = [
        "# Chief Editor HITL Review",
        "",
        f"- Output: `{output_path}`",
        f"- Quality gate: `{payload.get('quality_gate', {}).get('ok')}`",
        f"- Backend: `{payload.get('backend')}`",
        "",
        "## Issues",
        "",
        *(f"- {issue}" for issue in issues),
        "",
        "## Approval",
        "",
        "Create the sibling file `chief_editor_approval.txt` containing exactly `APPROVED` after manual review.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _first_heading(path: Path) -> str:
    text = _read_text(path)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _status_projection_status(root: Path, chief_payload: dict[str, Any]) -> str:
    chief_ok = bool(chief_payload.get("ok"))
    survey_eval = _read_json(root / "survey_eval.json")
    if chief_ok and survey_eval.get("ok") is True:
        return "passed"
    if chief_ok:
        return "partial"
    return "failed"


def _status_projection_title(root: Path, target: Path) -> str:
    summary = _read_json(root / "survey_final_summary.json")
    title = str(summary.get("title") or "").strip()
    if title:
        return title
    return _first_heading(target) or root.name


def _status_projection_counts(root: Path) -> dict[str, Any]:
    gap = _read_json(root / "survey_source_gap.json")
    factual = _read_json(root / "survey_section_factual_audit.json")
    scorecard = _read_json(root / "survey_section_scorecard.json")
    human_summary = _read_json(root / "survey_human_final_summary.json")
    human_metrics = _read_json(root / "survey_human_execution_metrics.json")
    return {
        "source_count": int(gap.get("source_count") or 0),
        "evidence_count": int(gap.get("evidence_count") or 0),
        "claim_count": int(gap.get("claim_count") or 0),
        "section_count": int(scorecard.get("section_count") or human_summary.get("chapter_count") or 0),
        "citation_accuracy": float(factual.get("section_grounding_accuracy") or 0.0),
        "execution_metrics": human_metrics if human_metrics else {},
        "topic": str(gap.get("brief") or "").strip(),
    }


def _publish_status_projection(root: Path, target: Path, chief_payload: dict[str, Any]) -> dict[str, str]:
    harness_dir = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness"))).expanduser()
    reports_dir = harness_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    root_resolved = root.resolve()
    reports_resolved = reports_dir.resolve()
    destination = root
    try:
        root_resolved.relative_to(reports_resolved)
    except ValueError:
        destination = reports_dir / root.name
        destination.mkdir(parents=True, exist_ok=True)
        for item in root.iterdir():
            if item.is_file() and item.suffix.lower() in REPORT_SUFFIXES:
                shutil.copy2(item, destination / item.name)

    report_target = destination / target.name
    title = _status_projection_title(root, report_target if report_target.exists() else target)
    counts = _status_projection_counts(root)
    manifest = {
        "run_id": destination.name,
        "status": _status_projection_status(root, chief_payload),
        "title": title,
        "task_title": title,
        "topic": counts["topic"],
        "output_dir": str(destination),
        "final_md": str(report_target if report_target.exists() else target),
        "source_count": counts["source_count"],
        "evidence_count": counts["evidence_count"],
        "claim_count": counts["claim_count"],
        "section_count": counts["section_count"],
        "citation_accuracy": counts["citation_accuracy"],
        "execution_metrics": counts["execution_metrics"],
        "chief_editor_final": str(report_target if report_target.exists() else target),
        "human_final_md": str(destination / "human_final.md") if (destination / "human_final.md").exists() else "",
    }
    manifest_path = destination / f"{destination.name}-research_eval.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "status_projection_dir": str(destination),
        "status_projection_eval_json": str(manifest_path),
        "status_projection_report": str(report_target if report_target.exists() else target),
    }


def run_chief_editor(
    output_dir: str | Path,
    *,
    source_path: str | Path = "",
    output_path: str | Path = "",
    backend: str = "claude-cli",
    model: str = "opus",
    command: str = "",
    timeout: int = 240,
    max_budget_usd: float = 3.0,
    fallback_models: str = "",
    min_chars: int = 8000,
    require_hitl: bool = False,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    source = Path(source_path).expanduser() if source_path else root / "human_final.md"
    target = Path(output_path).expanduser() if output_path else root / "chief_editor_final.md"
    text = _read_text(source)
    if not text.strip():
        return {"ok": False, "reason": "source_human_final_missing", "source_path": str(source)}

    title, sections, footnotes = _split_h2(text)
    if not sections:
        return {"ok": False, "reason": "source_human_final_has_no_sections", "source_path": str(source)}
    intro = [section for section in sections if section["heading"] in INTRO_HEADINGS]
    chapters = [section for section in sections if section["heading"] not in INTRO_HEADINGS]

    work_dir = root / "chief_editor"
    prompt_dir = work_dir / "prompts"
    chapter_dir = work_dir / "chapters"
    usage_path = root / "model_usage.jsonl"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    chapter_dir.mkdir(parents=True, exist_ok=True)

    rewritten: list[str] = [title, ""]
    for item in intro:
        rewritten.extend([f"## {item['heading']}", "", item["body"].strip(), ""])

    normalized_backend = backend.strip().lower()
    requested_model = model
    active_model = model
    model_candidates = _model_candidates(model, fallback_models)
    model_attempts: list[dict[str, Any]] = []
    chapter_results: list[dict[str, Any]] = []
    for idx, chapter in enumerate(chapters, start=1):
        heading = chapter["heading"]
        prompt = _chapter_prompt(title, heading, chapter["body"])
        prompt_path = prompt_dir / f"{idx:02d}-{re.sub(r'[^0-9A-Za-z_-]+', '-', heading).strip('-') or 'chapter'}.md"
        out_path = chapter_dir / f"{idx:02d}.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        if normalized_backend == "deterministic":
            chapter_text = f"## {heading}\n\n{chapter['body'].strip()}\n"
            chapter_usage: dict[str, int] = {}
        elif normalized_backend in {"local-command", "command"}:
            chapter_text, chapter_usage = _normalize_model_result(_run_command(command, prompt, timeout))
        elif normalized_backend in {"claude-cli", "opus", "claude"}:
            last_error = ""
            chapter_text = ""
            chapter_usage = {}
            for candidate in ([active_model] if active_model else model_candidates):
                try:
                    chapter_text, chapter_usage = _normalize_model_result(
                        _run_claude(prompt, model=candidate, timeout=timeout, max_budget_usd=max_budget_usd)
                    )
                    active_model = candidate
                    model_attempts.append({"chapter": heading, "model": candidate, "ok": True})
                    break
                except RuntimeError as exc:
                    last_error = str(exc)
                    model_attempts.append({"chapter": heading, "model": candidate, "ok": False, "reason": last_error})
                    if active_model == candidate:
                        active_model = ""
            if not chapter_text:
                for candidate in model_candidates:
                    if any(item.get("chapter") == heading and item.get("model") == candidate for item in model_attempts):
                        continue
                    try:
                        chapter_text, chapter_usage = _normalize_model_result(
                            _run_claude(prompt, model=candidate, timeout=timeout, max_budget_usd=max_budget_usd)
                        )
                        active_model = candidate
                        model_attempts.append({"chapter": heading, "model": candidate, "ok": True})
                        break
                    except RuntimeError as exc:
                        last_error = str(exc)
                        model_attempts.append({"chapter": heading, "model": candidate, "ok": False, "reason": last_error})
            if not chapter_text:
                raise RuntimeError(last_error or "claude_cli_failed_all_models")
        else:
            raise ValueError(f"unsupported_chief_editor_backend:{backend}")
        if not chapter_text.lstrip().startswith("## "):
            chapter_text = f"## {heading}\n\n{chapter_text.strip()}\n"
        if normalized_backend != "deterministic":
            append_model_usage_event(
                usage_path,
                build_model_usage_event(
                    backend=normalized_backend,
                    model=active_model if normalized_backend in {"claude-cli", "opus", "claude"} else command,
                    prompt=prompt,
                    output=chapter_text,
                    usage=chapter_usage,
                    metadata={
                        "stage": "chief_editor",
                        "chapter": heading,
                        "prompt_path": str(prompt_path),
                        "output_path": str(out_path),
                    },
                ),
            )
        out_path.write_text(chapter_text.strip() + "\n", encoding="utf-8")
        rewritten.extend([chapter_text.strip(), ""])
        chapter_results.append({
            "heading": heading,
            "prompt_path": str(prompt_path),
            "output_path": str(out_path),
            "char_count": len(chapter_text),
        })

    if footnotes:
        rewritten.extend([footnotes, ""])
    final_text = "\n".join(rewritten).strip() + "\n"
    target.write_text(final_text, encoding="utf-8")
    quality = _quality_gate(final_text, [item["heading"] for item in chapters], min_chars)
    approval_path = root / "chief_editor_approval.txt"
    hitl_path = root / "survey_chief_editor_hitl.md"
    payload: dict[str, Any] = {
        "ok": bool(quality["ok"]),
        "backend": normalized_backend,
        "model": active_model if normalized_backend in {"claude-cli", "opus", "claude"} else model,
        "requested_model": requested_model,
        "fallback_models": model_candidates[1:],
        "model_attempts": model_attempts,
        "source_path": str(source),
        "chief_editor_final": str(target),
        "chapter_results": chapter_results,
        "quality_gate": quality,
        "model_usage_path": str(usage_path),
        "hitl_path": str(hitl_path),
        "approval_path": str(approval_path),
        "hitl_required": require_hitl,
    }
    if require_hitl:
        approved = approval_path.exists() and approval_path.read_text(encoding="utf-8").strip() == "APPROVED"
        payload["hitl_approved"] = approved
        if not approved:
            payload["ok"] = False
            payload["reason"] = "hitl_approval_required"
    _write_hitl(hitl_path, payload, target)
    if payload.get("ok"):
        payload.update(_publish_status_projection(root, target, payload))
    (root / "survey_chief_editor_backend.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
