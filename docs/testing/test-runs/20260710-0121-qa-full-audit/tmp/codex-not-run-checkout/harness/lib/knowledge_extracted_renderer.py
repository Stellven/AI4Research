#!/usr/bin/env python3
"""Deterministic renderer for Solar Knowledge extracted JSON candidates."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


UTC = dt.timezone.utc
RENDER_SCHEMA_VERSION = "extracted-md-v2"


def now_iso() -> str:
    return dt.datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _list_text(values: list[Any]) -> str:
    if not values:
        return "N/A"
    return ", ".join(str(v) for v in values) or "N/A"


def _evidence(values: list[str] | None) -> str:
    values = values or []
    return ", ".join(f"raw:{v}" if not str(v).startswith("raw:") else str(v) for v in values) or "N/A"


def _table_escape(value: Any) -> str:
    text = str(value if value is not None else "N/A")
    return text.replace("|", "\\|").replace("\n", " ")


def render_extracted_markdown(candidate: dict[str, Any], *, generated_at: str | None = None) -> str:
    generated_at = generated_at or now_iso()
    meta = {
        "doc_id": candidate.get("doc_id", "N/A"),
        "source_kind": candidate.get("source_kind", "N/A"),
        "doc_type": candidate.get("doc_type", "N/A"),
        "source_path": candidate.get("source_path", "N/A"),
        "source_sha256": candidate.get("source_sha256", "N/A"),
        "derived": "true",
        "extractor": "thunderomlx",
        "profile": candidate.get("profile", "knowledge-extractor"),
        "proxy_model": candidate.get("proxy_model", "mini-thunderomlx-qwen36-knowledge"),
        "local_model": candidate.get("local_model", "ThunderOMLX backend"),
        "prompt_version": candidate.get("prompt_version", "knowledge-extract-v2"),
        "schema_version": candidate.get("schema_version", "extracted-json-v2"),
        "render_schema_version": RENDER_SCHEMA_VERSION,
        "generated_at": generated_at,
    }
    lines = ["---"]
    lines.extend(f"{key}: {value}" for key, value in meta.items())
    lines.extend(["---", "", "# Semantic Extraction", ""])

    summary = candidate.get("summary") or {}
    lines.extend(
        [
            "## Summary",
            "",
            str(summary.get("claim") or "N/A"),
            "",
            f"Evidence: {_evidence(summary.get('evidence'))}",
            "",
        ]
    )

    lines.extend(["## Core Facts", "", "| Fact | Evidence | Confidence |", "|---|---|---|"])
    facts = candidate.get("core_facts") or []
    if not facts:
        facts = [{"claim": "N/A", "evidence": [], "confidence": "low"}]
    for fact in facts:
        lines.append(f"| {_table_escape(fact.get('claim', 'N/A'))} | {_table_escape(_evidence(fact.get('evidence')))} | {_table_escape(fact.get('confidence', 'N/A'))} |")
    lines.append("")

    lines.extend(["## Functional Modules", ""])
    modules = candidate.get("functional_modules") or []
    if not modules:
        modules = [{"name": "N/A", "role": "N/A", "inputs": [], "outputs": [], "dependencies": [], "evidence": []}]
    for module in modules:
        lines.extend(
            [
                f"### {module.get('name') or 'N/A'}",
                "",
                f"- Role: {module.get('role') or 'N/A'}",
                f"- Inputs: {_list_text(module.get('inputs') or [])}",
                f"- Outputs: {_list_text(module.get('outputs') or [])}",
                f"- Dependencies: {_list_text(module.get('dependencies') or [])}",
                f"- Evidence: {_evidence(module.get('evidence'))}",
                "",
            ]
        )

    lines.extend(["## Architecture", "", "| Component | Description | Evidence |", "|---|---|---|"])
    architecture = candidate.get("architecture") or []
    if not architecture:
        architecture = [{"component": "N/A", "description": "N/A", "evidence": []}]
    for item in architecture:
        lines.append(f"| {_table_escape(item.get('component', 'N/A'))} | {_table_escape(item.get('description', 'N/A'))} | {_table_escape(_evidence(item.get('evidence')))} |")
    lines.append("")

    lines.extend(["## Commands / API / Config", "", "| Kind | Name | Value | Purpose | Evidence |", "|---|---|---|---|---|"])
    commands = candidate.get("commands_api_config") or []
    if not commands:
        commands = [{"kind": "N/A", "name": "N/A", "value": "N/A", "purpose": "原文未提供", "evidence": []}]
    for item in commands:
        lines.append(
            f"| {_table_escape(item.get('kind', 'N/A'))} | {_table_escape(item.get('name', 'N/A'))} | "
            f"{_table_escape(item.get('value', 'N/A'))} | {_table_escape(item.get('purpose', 'N/A'))} | {_table_escape(_evidence(item.get('evidence')))} |"
        )
    lines.append("")

    lines.extend(["## Risks", "", "| Risk | Impact | Mitigation | Evidence |", "|---|---|---|---|"])
    risks = candidate.get("risks") or []
    if not risks:
        risks = [{"risk": "N/A", "impact": "N/A", "mitigation": "N/A", "evidence": []}]
    for risk in risks:
        lines.append(
            f"| {_table_escape(risk.get('risk', 'N/A'))} | {_table_escape(risk.get('impact', 'N/A'))} | "
            f"{_table_escape(risk.get('mitigation', 'N/A'))} | {_table_escape(_evidence(risk.get('evidence')))} |"
        )
    lines.append("")

    lines.extend(["## Open Questions", ""])
    questions = candidate.get("open_questions") or []
    if not questions:
        questions = [{"question": "N/A", "reason": "N/A", "evidence": []}]
    for question in questions:
        lines.extend(
            [
                f"- {question.get('question') or 'N/A'}",
                f"  Reason: {question.get('reason') or 'N/A'}",
                f"  Evidence: {_evidence(question.get('evidence'))}",
            ]
        )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render extracted JSON to Markdown")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidate_path = Path(args.candidate).expanduser()
    output_path = Path(args.output).expanduser()
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # B3 naming migration: ensure output is *.semantic.md
    if output_path.name.endswith(".extracted.md"):
        semantic_path = output_path.with_name(output_path.name.replace(".extracted.md", ".semantic.md"))
    elif output_path.suffix == ".md" and not output_path.name.endswith(".semantic.md"):
        semantic_path = output_path.with_name(output_path.stem + ".semantic.md")
    else:
        semantic_path = output_path

    markdown = render_extracted_markdown(candidate)
    semantic_path.write_text(markdown, encoding="utf-8")

    # Create symlink: *.extracted.md → *.semantic.md (backward compat)
    symlink_path = semantic_path.with_name(
        semantic_path.name.replace(".semantic.md", ".extracted.md")
    )
    if symlink_path == semantic_path:
        symlink_path = semantic_path  # no symlink needed if names match
    if symlink_path != semantic_path:
        try:
            if symlink_path.is_symlink() or symlink_path.exists():
                symlink_path.unlink()
            symlink_path.symlink_to(semantic_path.name)
        except OSError:
            pass  # non-critical: symlink creation best-effort

    payload = {"ok": True, "output": str(semantic_path), "symlink": str(symlink_path), "chars": len(markdown)}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"wrote {semantic_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
