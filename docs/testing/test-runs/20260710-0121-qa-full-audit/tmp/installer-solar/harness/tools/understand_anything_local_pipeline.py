#!/usr/bin/env python3
"""Deterministic repo scan + ThunderOMLX semantic phase for understand-anything."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = os.environ.get("THUNDEROMLX_BASE_URL", "http://127.0.0.1:8002").rstrip("/")
API_KEY = os.environ.get("THUNDEROMLX_AUTH_TOKEN", "local-thunderomlx")
PROXY_MODEL = os.environ.get("THUNDEROMLX_ANTHROPIC_MODEL", os.environ.get("THUNDEROMLX_LOCAL_MODEL", "Qwen3.6-35b-a3b"))
MAX_TOKENS = int(os.environ.get("SOLAR_UNDERSTAND_ANYTHING_MAX_TOKENS", "2200") or "2200")
SCAN_FILE_LIMIT = int(os.environ.get("SOLAR_UNDERSTAND_ANYTHING_SCAN_FILE_LIMIT", "1800") or "1800")
SNIPPET_LIMIT = int(os.environ.get("SOLAR_UNDERSTAND_ANYTHING_SNIPPET_LIMIT", "18") or "18")
SNIPPET_CHARS_PER_FILE = int(os.environ.get("SOLAR_UNDERSTAND_ANYTHING_SNIPPET_CHARS_PER_FILE", "1600") or "1600")
SNIPPET_TOTAL_CHARS = int(os.environ.get("SOLAR_UNDERSTAND_ANYTHING_SNIPPET_TOTAL_CHARS", "22000") or "22000")
SEMANTIC_CHUNK_SNIPPETS = int(os.environ.get("SOLAR_UNDERSTAND_ANYTHING_SEMANTIC_CHUNK_SNIPPETS", "4") or "4")
SEMANTIC_CHUNK_TOTAL_CHARS = int(os.environ.get("SOLAR_UNDERSTAND_ANYTHING_SEMANTIC_CHUNK_TOTAL_CHARS", "5200") or "5200")
FINAL_SYNTHESIS_GROUP_ITEMS = int(os.environ.get("SOLAR_UNDERSTAND_ANYTHING_FINAL_SYNTHESIS_GROUP_ITEMS", "6") or "6")
FINAL_SYNTHESIS_GROUP_TOTAL_CHARS = int(os.environ.get("SOLAR_UNDERSTAND_ANYTHING_FINAL_SYNTHESIS_GROUP_TOTAL_CHARS", "7000") or "7000")

EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "target",
    ".next",
    ".turbo",
    ".solar",
    ".understand-anything",
}
PRIORITY_FILES = (
    "README.md",
    "README.zh-CN.md",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "requirements.txt",
    "AGENTS.md",
)
TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml", ".toml", ".sh",
    ".go", ".rs", ".java", ".kt", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".rb",
    ".php", ".html", ".css", ".scss", ".sql",
}
LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sql": "SQL",
    ".md": "Markdown",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".sh": "Shell",
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_read_text(path: Path, max_chars: int) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception:
        return ""


def _extract_symbols(text: str) -> list[str]:
    patterns = (
        r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*interface\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s*=",
    )
    symbols: list[str] = []
    for pattern in patterns:
        symbols.extend(re.findall(pattern, text, re.M))
    seen: set[str] = set()
    ordered: list[str] = []
    for symbol in symbols:
        if symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)
    return ordered[:12]


def _language_for_path(path: Path) -> str:
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "Other")


def deterministic_scan_repo(repo_path: str, *, language: str = "zh") -> dict[str, Any]:
    root = Path(repo_path).expanduser().resolve()
    if not root.exists():
        raise RuntimeError(f"repo_path does not exist: {root}")

    file_entries: list[dict[str, Any]] = []
    language_counts: dict[str, int] = {}
    manifest_hits: list[str] = []
    for priority in PRIORITY_FILES:
        candidate = root / priority
        if candidate.exists() and candidate.is_file():
            manifest_hits.append(priority)

    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in EXCLUDED_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            rel = path.relative_to(root).as_posix()
            scanned += 1
            if scanned > SCAN_FILE_LIMIT:
                break
            suffix = path.suffix.lower()
            lang = _language_for_path(path)
            language_counts[lang] = language_counts.get(lang, 0) + 1
            file_entries.append(
                {
                    "path": rel,
                    "language": lang,
                    "size": path.stat().st_size if path.exists() else 0,
                    "priority": int(rel in PRIORITY_FILES or Path(rel).name in PRIORITY_FILES),
                    "text_candidate": suffix in TEXT_SUFFIXES,
                }
            )
        if scanned > SCAN_FILE_LIMIT:
            break

    ranked = sorted(
        file_entries,
        key=lambda item: (
            -int(item["priority"]),
            0 if item["text_candidate"] else 1,
            len(str(item["path"])),
            str(item["path"]),
        ),
    )

    snippets: list[dict[str, Any]] = []
    remaining_chars = SNIPPET_TOTAL_CHARS
    for item in ranked:
        if len(snippets) >= SNIPPET_LIMIT or remaining_chars <= 0:
            break
        if not item["text_candidate"]:
            continue
        path = root / str(item["path"])
        text = _safe_read_text(path, min(SNIPPET_CHARS_PER_FILE, remaining_chars))
        if not text.strip():
            continue
        symbols = _extract_symbols(text)
        snippets.append(
            {
                "path": str(item["path"]),
                "language": item["language"],
                "symbols": symbols,
                "snippet": text,
            }
        )
        remaining_chars -= len(text)

    directories = sorted(
        {
            Path(str(item["path"])).parts[0]
            for item in ranked
            if Path(str(item["path"])).parts
        }
    )[:40]

    return {
        "schema_version": "solar.understand_anything.repo_scan.v1",
        "generated_at": now(),
        "repo_path": str(root),
        "language": language,
        "file_count_scanned": len(file_entries),
        "scan_limit_reached": len(file_entries) >= SCAN_FILE_LIMIT,
        "languages": language_counts,
        "directories": directories,
        "priority_files": manifest_hits,
        "representative_files": [item["path"] for item in ranked[:32]],
        "snippets": snippets,
    }


def build_semantic_prompt(scan: dict[str, Any], *, objective: str = "", language: str = "zh") -> str:
    snippet_blocks = []
    for item in scan.get("snippets", []):
        snippet_blocks.append(
            "\n".join(
                [
                    f"### File: {item.get('path')}",
                    f"- language: {item.get('language')}",
                    f"- symbols: {', '.join(item.get('symbols') or []) or 'N/A'}",
                    "```text",
                    str(item.get("snippet") or ""),
                    "```",
                ]
            )
        )
    return "\n".join(
        [
            "你是 Solar Harness 的 ThunderOMLX 代码库语义分析器。",
            "请只基于下面给出的 deterministic 仓库扫描结果做中文语义分析，不要编造未观察到的实现细节。",
            "",
            "输出格式要求：",
            "1. 一句话定位",
            "2. 模块分层",
            "3. 关键入口与数据流",
            "4. 关键文件/命令",
            "5. 风险与边界",
            "6. onboarding 建议",
            "",
            f"- objective: {objective or 'N/A'}",
            f"- repo_path: {scan.get('repo_path') or 'N/A'}",
            f"- requested_language: {language or 'zh'}",
            "",
            "## Scan Summary",
            f"- file_count_scanned: {scan.get('file_count_scanned')}",
            f"- scan_limit_reached: {scan.get('scan_limit_reached')}",
            f"- directories: {', '.join(scan.get('directories') or []) or 'N/A'}",
            f"- priority_files: {', '.join(scan.get('priority_files') or []) or 'N/A'}",
            f"- languages: {json.dumps(scan.get('languages') or {}, ensure_ascii=False)}",
            "",
            "## Representative Files",
            json.dumps(scan.get("representative_files") or [], ensure_ascii=False, indent=2),
            "",
            "## Snippets",
            "\n\n".join(snippet_blocks) or "N/A",
        ]
    )


def build_chunk_semantic_prompt(
    scan: dict[str, Any],
    chunk: dict[str, Any],
    *,
    objective: str = "",
    language: str = "zh",
) -> str:
    snippet_blocks = []
    for item in chunk.get("snippets", []):
        snippet_blocks.append(
            "\n".join(
                [
                    f"### File: {item.get('path')}",
                    f"- language: {item.get('language')}",
                    f"- symbols: {', '.join(item.get('symbols') or []) or 'N/A'}",
                    "```text",
                    str(item.get("snippet") or ""),
                    "```",
                ]
            )
        )
    return "\n".join(
        [
            "你是 Solar Harness 的 ThunderOMLX 分片代码库语义分析器。",
            "请仅基于当前这个仓库分片里的 deterministic 代码片段做中文分析，不要补全未看到的实现。",
            "你的职责是给后续总汇编阶段提供高密度、可验证的局部摘要。",
            "",
            "输出格式要求：",
            "1. 这一分片覆盖的模块/目录",
            "2. 关键入口/符号",
            "3. 明确观察到的数据流/控制流",
            "4. 该分片暴露的风险/边界",
            "5. 必须继续查看的相邻模块",
            "",
            f"- objective: {objective or 'N/A'}",
            f"- repo_path: {scan.get('repo_path') or 'N/A'}",
            f"- requested_language: {language or 'zh'}",
            f"- chunk_id: {chunk.get('chunk_id') or 'N/A'}",
            f"- chunk_paths: {', '.join(chunk.get('paths') or []) or 'N/A'}",
            "",
            "## Repo Scan Summary",
            f"- file_count_scanned: {scan.get('file_count_scanned')}",
            f"- directories: {', '.join(scan.get('directories') or []) or 'N/A'}",
            f"- languages: {json.dumps(scan.get('languages') or {}, ensure_ascii=False)}",
            "",
            "## Chunk Snippets",
            "\n\n".join(snippet_blocks) or "N/A",
        ]
    )


def build_final_synthesis_prompt(
    scan: dict[str, Any],
    chunk_summaries: list[dict[str, Any]],
    *,
    objective: str = "",
    language: str = "zh",
) -> str:
    summary_blocks = []
    for item in chunk_summaries:
        summary_blocks.append(
            "\n".join(
                [
                    f"### {item.get('chunk_id')}",
                    f"- paths: {', '.join(item.get('paths') or []) or 'N/A'}",
                    str(item.get("summary") or "").strip(),
                ]
            )
        )
    return "\n".join(
        [
            "你是 Solar Harness 的 ThunderOMLX 代码库总汇编分析器。",
            "下面给你的是 deterministic 仓库扫描摘要，以及多个分片语义摘要。",
            "请把它们汇编成一个面向工程落地的中文 knowledge summary。",
            "不要编造分片里没出现的细节；如果存在不确定性，要明确写出来。",
            "",
            "输出格式要求：",
            "1. 一句话定位",
            "2. 模块分层",
            "3. 关键入口与数据流",
            "4. 关键文件/命令",
            "5. 风险与边界",
            "6. onboarding 建议",
            "",
            f"- objective: {objective or 'N/A'}",
            f"- repo_path: {scan.get('repo_path') or 'N/A'}",
            f"- requested_language: {language or 'zh'}",
            f"- chunk_count: {len(chunk_summaries)}",
            "",
            "## Repo Scan Summary",
            f"- file_count_scanned: {scan.get('file_count_scanned')}",
            f"- scan_limit_reached: {scan.get('scan_limit_reached')}",
            f"- directories: {', '.join(scan.get('directories') or []) or 'N/A'}",
            f"- priority_files: {', '.join(scan.get('priority_files') or []) or 'N/A'}",
            f"- languages: {json.dumps(scan.get('languages') or {}, ensure_ascii=False)}",
            "",
            "## Representative Files",
            json.dumps(scan.get("representative_files") or [], ensure_ascii=False, indent=2),
            "",
            "## Chunk Summaries",
            "\n\n".join(summary_blocks) or "N/A",
        ]
    )


def _chunk_summary_groups(chunk_summaries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for item in chunk_summaries:
        summary_text = str(item.get("summary") or "")
        item_chars = len(summary_text)
        should_flush = bool(current) and (
            len(current) >= FINAL_SYNTHESIS_GROUP_ITEMS
            or current_chars + item_chars > FINAL_SYNTHESIS_GROUP_TOTAL_CHARS
        )
        if should_flush:
            groups.append(current)
            current = []
            current_chars = 0
        current.append(item)
        current_chars += item_chars
    if current:
        groups.append(current)
    return groups


def _run_grouped_final_synthesis(
    scan: dict[str, Any],
    chunk_summaries: list[dict[str, Any]],
    *,
    out_dir: Path,
    objective: str,
    language: str,
    runner,
    resume_path: Path,
    total_usage: dict[str, int],
 ) -> tuple[str, dict[str, Any], Path, Path]:
    final_prompt_path = out_dir / "semantic-prompt.md"
    final_response_path = out_dir / "semantic-response.json"
    final_summary_path = out_dir / "semantic-summary.md"
    summary_groups = _chunk_summary_groups(chunk_summaries)
    if len(summary_groups) <= 1:
        final_prompt = build_final_synthesis_prompt(scan, chunk_summaries, objective=objective, language=language)
        _write_text(final_prompt_path, final_prompt.rstrip() + "\n")
        final_response = runner(final_prompt)
        _write_json(final_response_path, final_response)
        semantic_text = content_text(final_response)
        if not semantic_text.strip():
            raise RuntimeError("ThunderOMLX returned empty final semantic summary")
        _write_text(final_summary_path, semantic_text.rstrip() + "\n")
        return semantic_text, final_response, final_prompt_path, final_summary_path

    synthesis_dir = out_dir / "synthesis-artifacts"
    synthesis_prompt_dir = synthesis_dir / "prompts"
    synthesis_response_dir = synthesis_dir / "responses"
    synthesis_summary_dir = synthesis_dir / "summaries"
    synthesis_prompt_dir.mkdir(parents=True, exist_ok=True)
    synthesis_response_dir.mkdir(parents=True, exist_ok=True)
    synthesis_summary_dir.mkdir(parents=True, exist_ok=True)
    completed_groups = set(_load_json_if_exists(resume_path).get("completed_synthesis_groups") or [])
    grouped_summaries: list[dict[str, Any]] = []
    for index, group in enumerate(summary_groups, start=1):
        group_id = f"synthesis-group-{index:03d}"
        prompt_path = synthesis_prompt_dir / f"{group_id}.md"
        response_path = synthesis_response_dir / f"{group_id}.json"
        summary_path = synthesis_summary_dir / f"{group_id}.md"
        if group_id in completed_groups and response_path.exists() and summary_path.exists():
            group_response = _load_json_if_exists(response_path)
            group_summary_text = _load_text_if_exists(summary_path).strip()
        else:
            group_prompt = build_final_synthesis_prompt(scan, group, objective=objective, language=language)
            _write_text(prompt_path, group_prompt.rstrip() + "\n")
            group_response = runner(group_prompt)
            _write_json(response_path, group_response)
            group_summary_text = content_text(group_response)
            if not group_summary_text.strip():
                raise RuntimeError(f"ThunderOMLX returned empty grouped synthesis summary for {group_id}")
            _write_text(summary_path, group_summary_text.rstrip() + "\n")
            completed_groups.add(group_id)
            _update_resume_state(
                resume_path,
                {
                    "completed_synthesis_groups": sorted(completed_groups),
                    "last_completed_synthesis_group": group_id,
                    "final_synthesis_completed": False,
                },
            )
        usage = group_response.get("usage") or {}
        for key, value in usage.items():
            if isinstance(value, int):
                total_usage[key] = total_usage.get(key, 0) + value
        grouped_summaries.append(
            {
                "chunk_id": group_id,
                "paths": sorted({path for item in group for path in (item.get("paths") or [])}),
                "summary": group_summary_text,
                "usage": usage,
            }
        )

    final_prompt = build_final_synthesis_prompt(scan, grouped_summaries, objective=objective, language=language)
    _write_text(final_prompt_path, final_prompt.rstrip() + "\n")
    final_response = runner(final_prompt)
    _write_json(final_response_path, final_response)
    semantic_text = content_text(final_response)
    if not semantic_text.strip():
        raise RuntimeError("ThunderOMLX returned empty final semantic summary")
    _write_text(final_summary_path, semantic_text.rstrip() + "\n")
    return semantic_text, final_response, final_prompt_path, final_summary_path


def _chunk_snippets(scan: dict[str, Any]) -> list[dict[str, Any]]:
    snippets = list(scan.get("snippets") or [])
    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for item in snippets:
        text = str(item.get("snippet") or "")
        item_chars = len(text)
        should_flush = bool(current) and (
            len(current) >= SEMANTIC_CHUNK_SNIPPETS
            or current_chars + item_chars > SEMANTIC_CHUNK_TOTAL_CHARS
        )
        if should_flush:
            chunk_id = f"chunk-{len(chunks) + 1:03d}"
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "snippets": current,
                    "paths": [str(x.get("path") or "") for x in current],
                    "snippet_count": len(current),
                    "total_chars": current_chars,
                }
            )
            current = []
            current_chars = 0
        current.append(item)
        current_chars += item_chars
    if current:
        chunk_id = f"chunk-{len(chunks) + 1:03d}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "snippets": current,
                "paths": [str(x.get("path") or "") for x in current],
                "snippet_count": len(current),
                "total_chars": current_chars,
            }
        )
    return chunks


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _update_resume_state(path: Path, payload: dict[str, Any]) -> None:
    existing = _load_json_if_exists(path)
    merged = dict(existing)
    merged.update(payload)
    merged["updated_at"] = now()
    _write_json(path, merged)


def strip_thinking_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"(?is)<think>.*?</think>\s*", "", text).strip()
    for pattern in (
        r"(?is)\bFinal Answer\s*:\s*",
        r"(?is)\bFinal\s*:\s*",
        r"(?is)最终答案\s*[:：]\s*",
        r"(?is)正式输出\s*[:：]\s*",
        r"(?is)答案\s*[:：]\s*",
    ):
        matches = list(re.finditer(pattern, text))
        if matches:
            return text[matches[-1].end():].strip()
    return text


def content_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for choice in response.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message") or {}
        if isinstance(message, dict):
            parts.append(str(message.get("content") or "").strip())
            reasoning = str(message.get("reasoning_content") or "").strip()
            if reasoning:
                parts.append(reasoning)
        if "text" in choice:
            parts.append(str(choice.get("text") or ""))
    for item in response.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
    return strip_thinking_text("\n".join(parts))


def call_thunderomlx(prompt: str) -> dict[str, Any]:
    payload = {
        "model": PROXY_MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"ThunderOMLX HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"ThunderOMLX connection failed: {exc}") from exc


def run_pipeline(
    repo_path: str,
    *,
    output_dir: str,
    language: str = "zh",
    objective: str = "",
    semantic_runner=None,
) -> dict[str, Any]:
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    scan = deterministic_scan_repo(repo_path, language=language)
    runner = semantic_runner or call_thunderomlx
    chunks = _chunk_snippets(scan)

    chunk_dir = out_dir / "chunk-artifacts"
    prompt_dir = chunk_dir / "prompts"
    response_dir = chunk_dir / "responses"
    summary_dir = chunk_dir / "summaries"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    response_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": "solar.understand_anything.chunk_manifest.v1",
        "generated_at": now(),
        "repo_path": scan["repo_path"],
        "chunk_count": len(chunks),
        "chunks": [
            {
                "chunk_id": chunk["chunk_id"],
                "paths": chunk["paths"],
                "snippet_count": chunk["snippet_count"],
                "total_chars": chunk["total_chars"],
            }
            for chunk in chunks
        ],
    }
    manifest_path = out_dir / "chunk-manifest.json"
    resume_path = out_dir / "resume-state.json"
    _write_json(manifest_path, manifest)
    _update_resume_state(
        resume_path,
        {
            "schema_version": "solar.understand_anything.resume_state.v1",
            "repo_path": scan["repo_path"],
            "chunk_count": len(chunks),
            "chunk_ids": [chunk["chunk_id"] for chunk in chunks],
        },
    )

    chunk_summaries: list[dict[str, Any]] = []
    completed_chunks = set(_load_json_if_exists(resume_path).get("completed_chunks") or [])
    resumed = False
    total_usage: dict[str, int] = {}
    for chunk in chunks:
        chunk_id = str(chunk["chunk_id"])
        chunk_prompt_path = prompt_dir / f"{chunk_id}.md"
        chunk_response_path = response_dir / f"{chunk_id}.json"
        chunk_summary_path = summary_dir / f"{chunk_id}.md"
        if chunk_id in completed_chunks and chunk_summary_path.exists() and chunk_response_path.exists():
            resumed = True
            chunk_summary_text = _load_text_if_exists(chunk_summary_path).strip()
            chunk_response = _load_json_if_exists(chunk_response_path)
        else:
            chunk_prompt = build_chunk_semantic_prompt(scan, chunk, objective=objective, language=language)
            _write_text(chunk_prompt_path, chunk_prompt.rstrip() + "\n")
            chunk_response = runner(chunk_prompt)
            _write_json(chunk_response_path, chunk_response)
            chunk_summary_text = content_text(chunk_response)
            if not chunk_summary_text.strip():
                raise RuntimeError(f"ThunderOMLX returned empty semantic summary for {chunk_id}")
            _write_text(chunk_summary_path, chunk_summary_text.rstrip() + "\n")
            completed_chunks.add(chunk_id)
            _update_resume_state(
                resume_path,
                {
                    "completed_chunks": sorted(completed_chunks),
                    "last_completed_chunk": chunk_id,
                    "final_synthesis_completed": False,
                },
            )
        usage = chunk_response.get("usage") or {}
        for key, value in usage.items():
            if isinstance(value, int):
                total_usage[key] = total_usage.get(key, 0) + value
        chunk_summaries.append(
            {
                "chunk_id": chunk_id,
                "paths": chunk.get("paths") or [],
                "summary": chunk_summary_text,
                "usage": usage,
            }
        )

    semantic_text, final_response, final_prompt_path, final_summary_path = _run_grouped_final_synthesis(
        scan,
        chunk_summaries,
        out_dir=out_dir,
        objective=objective,
        language=language,
        runner=runner,
        resume_path=resume_path,
        total_usage=total_usage,
    )
    final_usage = final_response.get("usage") or {}
    for key, value in final_usage.items():
        if isinstance(value, int):
            total_usage[key] = total_usage.get(key, 0) + value
    _update_resume_state(
        resume_path,
        {
            "completed_chunks": sorted(completed_chunks),
            "last_completed_chunk": sorted(completed_chunks)[-1] if completed_chunks else "",
            "final_synthesis_completed": True,
        },
    )

    config = {
        "schema_version": "solar.understand_anything.config.v1",
        "generated_at": now(),
        "repo_path": scan["repo_path"],
        "language": language,
        "execution_surface": "deterministic_scan_and_thunderomlx_semantic",
        "semantic_backend": "ThunderOMLX",
        "semantic_model": PROXY_MODEL,
    }
    meta = {
        "schema_version": "solar.understand_anything.meta.v1",
        "generated_at": now(),
        "backend": "ThunderOMLX",
        "base_url": BASE_URL,
        "proxy_model": PROXY_MODEL,
        "usage": total_usage,
        "chunk_usage": [item.get("usage") or {} for item in chunk_summaries],
        "final_usage": final_usage,
        "file_count_scanned": scan["file_count_scanned"],
        "scan_limit_reached": scan["scan_limit_reached"],
        "chunks_total": len(chunks),
        "chunks_completed": len(completed_chunks),
        "resumed": resumed,
    }
    knowledge_graph = {
        "schema_version": "solar.understand_anything.knowledge_graph.v1",
        "generated_at": now(),
        "repo_path": scan["repo_path"],
        "deterministic_scan": scan,
        "chunk_summaries": [
            {
                "chunk_id": item["chunk_id"],
                "paths": item["paths"],
                "summary": item["summary"],
            }
            for item in chunk_summaries
        ],
        "semantic_summary": semantic_text,
        "provenance": {
            "execution_surface": "deterministic_scan_and_thunderomlx_semantic",
            "semantic_backend": "ThunderOMLX",
            "semantic_model": PROXY_MODEL,
            "plugin_native_understand_invoked": False,
            "resume_supported": True,
        },
    }

    config_path = out_dir / "config.json"
    meta_path = out_dir / "meta.json"
    scan_path = out_dir / "repo-scan.json"
    graph_path = out_dir / "knowledge-graph.json"
    _write_json(config_path, config)
    _write_json(meta_path, meta)
    _write_json(scan_path, scan)
    _write_json(graph_path, knowledge_graph)
    return {
        "ok": True,
        "repo_path": scan["repo_path"],
        "output_dir": str(out_dir),
        "knowledge_graph_path": str(graph_path),
        "config_path": str(config_path),
        "meta_path": str(meta_path),
        "scan_path": str(scan_path),
        "manifest_path": str(manifest_path),
        "resume_state_path": str(resume_path),
        "prompt_path": str(final_prompt_path),
        "summary_path": str(final_summary_path),
        "usage": meta["usage"],
        "chunks_total": len(chunks),
        "chunks_completed": len(completed_chunks),
        "resumed": resumed,
        "semantic_backend": "ThunderOMLX",
        "semantic_model": PROXY_MODEL,
        "execution_surface": "deterministic_scan_and_thunderomlx_semantic",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--language", default="zh")
    ap.add_argument("--objective", default="")
    args = ap.parse_args()
    result = run_pipeline(args.repo, output_dir=args.output_dir, language=args.language, objective=args.objective)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
