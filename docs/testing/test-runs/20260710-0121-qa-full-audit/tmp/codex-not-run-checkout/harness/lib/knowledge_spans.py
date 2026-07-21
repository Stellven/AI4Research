#!/usr/bin/env python3
"""Sidecar span builder for Solar Knowledge ingest.

Spans are stable, local evidence anchors (S001, S002, ...) for a single source
document. The registry stores globally unique span IDs as doc_id:S001 while the
sidecar keeps the local IDs that extraction prompts can cite.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import knowledge_ingest_registry as registry


def _heading_level(line: str) -> int | None:
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None
    prefix = stripped.split(" ", 1)[0]
    if prefix and all(ch == "#" for ch in prefix):
        return len(prefix)
    return None


def build_markdown_spans(path: Path, *, max_lines: int = 120) -> dict[str, Any]:
    """Build heading-aware spans without splitting fenced code blocks or tables."""
    text = path.read_text(encoding="utf-8", errors="replace")
    source_sha = registry.hashlib.sha256(path.read_bytes()).hexdigest()
    lines = text.splitlines()
    spans: list[dict[str, Any]] = []
    heading_stack: list[str] = []
    current_start = 1
    current_lines: list[str] = []
    current_heading_path: list[str] = []
    in_fence = False

    def flush(end_line: int) -> None:
        nonlocal current_start, current_lines, current_heading_path
        while current_lines and not current_lines[0].strip():
            current_lines = current_lines[1:]
            current_start += 1
        while current_lines and not current_lines[-1].strip():
            current_lines = current_lines[:-1]
            end_line -= 1
        if not current_lines:
            return
        span_text = "\n".join(current_lines)
        spans.append(
            {
                "span_id": f"S{len(spans) + 1:03d}",
                "start_line": current_start,
                "end_line": end_line,
                "heading_path": list(current_heading_path),
                "text_sha256": registry.sha256_text(span_text),
                "char_count": len(span_text),
                "text": span_text,
            }
        )

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence

        level = None if in_fence else _heading_level(line)
        if level is not None and current_lines:
            flush(idx - 1)
            current_start = idx
            current_lines = []

        if level is not None:
            title = line.lstrip("#").strip()
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(title)
            current_heading_path = list(heading_stack)
        elif not current_heading_path:
            current_heading_path = list(heading_stack)

        should_split = (
            current_lines
            and not in_fence
            and level is None
            and len(current_lines) >= max_lines
            and not line.startswith("|")
            and not (current_lines[-1].startswith("|") if current_lines else False)
        )
        if should_split:
            flush(idx - 1)
            current_start = idx
            current_lines = []
            current_heading_path = list(heading_stack)

        current_lines.append(line)

    flush(len(lines))
    if not spans and text:
        spans.append(
            {
                "span_id": "S001",
                "start_line": 1,
                "end_line": max(1, len(lines)),
                "heading_path": [],
                "text_sha256": registry.sha256_text(text),
                "char_count": len(text),
                "text": text,
            }
        )
    return {
        "source_path": str(path),
        "source_sha256": source_sha,
        "spans": spans,
    }


def default_sidecar_path(source_path: Path, *, root: Path | None = None, doc_id: str | None = None) -> Path:
    if root is None:
        return source_path.with_suffix(source_path.suffix + ".spans.json")
    safe_name = (doc_id or registry.sha256_text(str(source_path))[:16]).replace("/", "_").replace(":", "_")
    return root / f"{safe_name}.spans.json"


def write_span_sidecar(
    *,
    source_path: Path,
    doc_id: str,
    source_kind: str,
    output_path: Path,
    max_lines: int = 120,
) -> dict[str, Any]:
    payload = build_markdown_spans(source_path, max_lines=max_lines)
    payload.update(
        {
            "doc_id": doc_id,
            "source_kind": source_kind,
            "schema_version": "spans-v1",
        }
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload | {"sidecar_path": str(output_path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Solar Knowledge sidecar spans")
    parser.add_argument("--source", required=True)
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--source-kind", default="raw")
    parser.add_argument("--output")
    parser.add_argument("--max-lines", type=int, default=120)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.source).expanduser()
    output = Path(args.output).expanduser() if args.output else default_sidecar_path(source)
    payload = write_span_sidecar(
        source_path=source,
        doc_id=args.doc_id,
        source_kind=args.source_kind,
        output_path=output,
        max_lines=args.max_lines,
    )
    if args.json:
        print(json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
