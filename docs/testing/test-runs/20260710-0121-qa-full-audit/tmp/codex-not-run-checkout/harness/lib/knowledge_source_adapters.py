#!/usr/bin/env python3
"""Source adapter helpers for Solar Knowledge ingest."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


DEFAULT_VAULT_FOLDERS = ("concepts", "references", "synthesis", "projects")
SUPPORTED_SOURCE_SUFFIXES = {".md", ".markdown", ".json", ".jsonl", ".txt", ".html", ".htm"}


# ── B4 Adapter Registry ──────────────────────────────────────────
ADAPTER_REGISTRY: dict[str, dict[str, str]] = {
    "youtube_transcript": {
        "source_kind": "youtube_transcript",
        "source_adapter": "youtube_adapter",
        "declared_doc_type": "youtube_transcript",
        "root_subdir": "youtube-influence-digest",
    },
    "github_trends": {
        "source_kind": "github_trends",
        "source_adapter": "github_adapter",
        "declared_doc_type": "github_digest",
        "root_subdir": "github-trends-digest",
    },
    "pdf_manual": {
        "source_kind": "pdf_manual",
        "source_adapter": "pdf_adapter",
        "declared_doc_type": "pdf_manual",
        "root_subdir": "pdf-manuals",
    },
    "accepted_sprint": {
        "source_kind": "accepted_sprint",
        "source_adapter": "accepted_adapter",
        "declared_doc_type": "accepted_sprint",
        "root_subdir": "accepted",
    },
    "solar_artifact": {
        "source_kind": "solar_artifact",
        "source_adapter": "solar_adapter",
        "declared_doc_type": "solar_artifact",
        "root_subdir": "solar-harness",
    },
}


def iter_adapter_sources(
    raw_root: Path, adapter_key: str, *, limit: int | None = None
) -> Iterable[tuple[Path, str, str, str]]:
    """Iterate sources for a specific adapter from ADAPTER_REGISTRY.

    Returns (path, source_kind, source_adapter, declared_doc_type) tuples.
    """
    info = ADAPTER_REGISTRY.get(adapter_key)
    if info is None:
        return
    subdir = info["root_subdir"]
    target_dir = raw_root / subdir
    if not target_dir.exists():
        # Fallback: scan entire raw_root and classify
        target_dir = raw_root
    count = 0
    for path in sorted(target_dir.rglob("*.md")):
        text_path = str(path)
        if "/_extracted/" in text_path or "/.spans/" in text_path:
            continue
        # Verify this matches the adapter via classify_raw_source
        classified_kind, _, _ = classify_raw_source(path, raw_root)
        # Accept if classified matches or if scanning from specific subdir
        yield path, info["source_kind"], info["source_adapter"], info["declared_doc_type"]
        count += 1
        if limit and count >= limit:
            return


def classify_raw_source(path: Path, raw_root: Path) -> tuple[str, str, str]:
    """Return (source_kind, adapter, declared_doc_type) for known raw sources."""
    try:
        rel = path.resolve().relative_to(raw_root.resolve())
    except Exception:
        rel = path
    parts = [p.lower() for p in rel.parts]
    abs_parts = [p.lower() for p in path.resolve().parts]
    text = "/".join(parts)
    abs_text = "/".join(abs_parts)
    name = path.name.lower()

    if ".dispatch" in parts or ".dispatch" in abs_parts or name.endswith(".dispatch.md"):
        return "raw_dispatch", "dispatch_control_adapter", "dispatch_control_file"
    if "ai-influence-daily-digest" in parts or "ai-influence-daily-digest" in abs_parts or "nitter" in name:
        return "raw_social", "social_signal_adapter", "social_signal"
    if "chatgpt-extension-inbox" in parts or "chatgpt-extension-inbox" in abs_parts or "chatgpt" in text or "chatgpt" in abs_text:
        return "raw_chatgpt", "chatgpt_adapter", "chatgpt_conversation"
    if "youtube-influence-digest" in parts or "youtube-influence-digest" in abs_parts or "youtube" in text or "youtube" in abs_text or "transcript" in name:
        return "raw_youtube", "youtube_transcript_adapter", "youtube_transcript"
    if "github-trends-digest" in parts or "github-trends-digest" in abs_parts or "github" in text or "github" in abs_text:
        return "raw_github", "github_report_adapter", "github_digest"
    if "web-captures" in parts or "web-captures" in abs_parts or "web" in text or "web" in abs_text or "capture" in name:
        return "raw_web", "web_capture_adapter", "web_capture"
    if ("solar-harness" in parts and "accepted" in parts) or ("solar-harness" in abs_parts and "accepted" in abs_parts) or name.endswith(".accepted.md"):
        return "accepted_sprint", "accepted_artifact_adapter", "accepted_sprint"
    if "solar-harness" in text or "solar-harness" in abs_text or name.startswith("solar-") or "solar_harness" in text or "solar_harness" in abs_text:
        return "raw_solar", "solar_artifact_adapter", "solar_artifact"
    return "raw", "raw_adapter", "markdown"


def iter_raw_markdown(root: Path, *, limit: int | None = None) -> Iterable[Path]:
    count = 0
    for path in sorted(root.rglob("*.md")):
        text_path = str(path)
        if "/_extracted/" in text_path or "/.dispatch/" in text_path:
            continue
        if path.name.endswith(".summary.md") and "/accepted/" not in text_path:
            # Summary docs are accepted for raw, but avoid obvious duplicate sidecar summaries elsewhere.
            pass
        yield path
        count += 1
        if limit and count >= limit:
            return


def iter_raw_sources(root: Path, *, limit: int | None = None, include_dispatch: bool = False) -> Iterable[Path]:
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        text_path = str(path)
        if "/_extracted/" in text_path or "/.spans/" in text_path or "/.materialized/" in text_path:
            continue
        if "/.dispatch/" in text_path and not include_dispatch:
            continue
        if path.suffix.lower() not in SUPPORTED_SOURCE_SUFFIXES:
            continue
        yield path
        count += 1
        if limit and count >= limit:
            return


def iter_vault_markdown(vault_root: Path, *, include: list[str] | None = None, limit: int | None = None) -> Iterable[tuple[Path, str]]:
    folders = include or list(DEFAULT_VAULT_FOLDERS)
    count = 0
    for folder in folders:
        base = vault_root / folder
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            if ".obsidian" in path.parts or "templates" in path.parts:
                continue
            yield path, folder
            count += 1
            if limit and count >= limit:
                return


def doc_type_for_vault_folder(folder: str) -> str:
    mapping = {
        "concepts": "concept",
        "references": "reference",
        "synthesis": "synthesis",
        "projects": "project",
    }
    return mapping.get(folder, folder.rstrip("s") or "vault")


def materialize_to_markdown(source_path: Path, *, target_root: Path, source_kind: str, max_chars: int = 120000) -> Path:
    """Convert non-Markdown raw source artifacts into deterministic Markdown."""
    if source_path.suffix.lower() in {".md", ".markdown"}:
        return source_path
    source_bytes = source_path.read_bytes()
    text = source_bytes.decode("utf-8", errors="replace")
    rel_name = source_path.name.replace("/", "_")
    out_dir = target_root / source_kind
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{source_path.stem}.materialized.md"
    body = ""
    if source_path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
            title = data.get("title") if isinstance(data, dict) else None
            body = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
            heading = str(title or source_path.stem)
        except Exception:
            body = text
            heading = source_path.stem
    elif source_path.suffix.lower() == ".jsonl":
        rows = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                rows.append({"raw": line})
        body = json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True)
        heading = source_path.stem
    else:
        body = text
        heading = source_path.stem
    if len(body) > max_chars:
        body = body[:max_chars] + "\n\n[TRUNCATED_BY_KNOWLEDGE_MATERIALIZER]\n"
    out.write_text(
        "\n".join(
            [
                "---",
                f"source_path: {source_path}",
                f"source_kind: {source_kind}",
                "materialized: true",
                "---",
                "",
                f"# {heading}",
                "",
                f"- Source file: `{source_path}`",
                f"- Original filename: `{rel_name}`",
                "",
                "## Content",
                "",
                "```text" if source_path.suffix.lower() not in {".html", ".htm"} else "```html",
                body,
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return out
