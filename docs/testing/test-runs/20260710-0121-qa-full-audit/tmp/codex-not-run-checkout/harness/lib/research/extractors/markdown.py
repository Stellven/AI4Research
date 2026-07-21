"""Markdown file extractor for DeepResearch.

Parses .md files into SourceDocument instances. No HTTP imports.
Reads from local filesystem only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .. import hashing
from ..schemas import SourceDocument


class MarkdownExtractor:
    """Extract SourceDocument from a local .md file."""

    connector_id = "internal_mirage"

    def __init__(self, connector_id: str = "internal_mirage") -> None:
        self.connector_id = connector_id

    def extract(self, file_path: str | Path, source_hit_id: Optional[str] = None) -> SourceDocument:
        """Parse a markdown file into a SourceDocument.

        Args:
            file_path: Path to the .md file.
            source_hit_id: Optional link back to the SourceHit that led here.

        Returns:
            SourceDocument with full raw_text, content_hash, and metadata.

        Raises:
            FileNotFoundError: If file_path does not exist.
            ValueError: If file is empty or not .md.
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Markdown file not found: {path}")

        if path.suffix.lower() not in (".md", ".markdown"):
            raise ValueError(f"Expected .md file, got {path.suffix!r}")

        raw_text = path.read_text(encoding="utf-8")
        if not raw_text.strip():
            raise ValueError(f"Markdown file is empty: {path}")

        title = self._extract_title(raw_text) or path.stem
        content_hash = hashing.content_hash(raw_text)

        return SourceDocument(
            doc_id=f"doc:{self.connector_id}:{path}",
            connector_id=self.connector_id,
            title=title,
            raw_text=raw_text,
            content_hash=content_hash,
            content_length=len(raw_text),
            source_hit_id=source_hit_id,
            source_url=str(path),
            metadata={
                "file_extension": path.suffix,
                "file_size": path.stat().st_size,
                "line_count": raw_text.count("\n") + 1,
                "has_frontmatter": raw_text.startswith("---"),
            },
        )

    def extract_frontmatter(self, raw_text: str) -> dict[str, str]:
        """Extract YAML frontmatter from markdown text."""
        if not raw_text.startswith("---"):
            return {}
        match = re.match(r"^---\s*\n(.*?)\n---", raw_text, re.DOTALL)
        if not match:
            return {}
        fm: dict[str, str] = {}
        for line in match.group(1).split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                fm[key.strip()] = value.strip().strip('"').strip("'")
        return fm

    def _extract_title(self, raw_text: str) -> Optional[str]:
        """Extract first H1 heading from markdown text."""
        for line in raw_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped[2:].strip()
        return None
