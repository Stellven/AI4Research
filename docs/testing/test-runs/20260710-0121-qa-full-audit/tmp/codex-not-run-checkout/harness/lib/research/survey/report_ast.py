"""Report AST helpers for survey-grade DeepResearch."""

from __future__ import annotations

import json
from pathlib import Path


def load_report_ast(path: str | Path) -> dict:
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def section_specs(ast: dict) -> list[dict]:
    sections = ast.get("sections")
    if isinstance(sections, list):
        return [section for section in sections if isinstance(section, dict)]
    collected: list[dict] = []
    for chapter in ast.get("chapters", []):
        for section in chapter.get("sections", []):
            if isinstance(section, dict):
                row = dict(section)
                row.setdefault("chapter_id", chapter.get("chapter_id"))
                collected.append(row)
    return collected


def chapter_specs(ast: dict) -> list[dict]:
    chapters = ast.get("chapters")
    return [chapter for chapter in chapters if isinstance(chapter, dict)] if isinstance(chapters, list) else []
