"""test_extractors_markdown — Verify MarkdownExtractor."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from research.extractors.markdown import MarkdownExtractor
from research.schemas import SourceDocument


class TestMarkdownExtractor:
    def test_extract_basic_md(self, tmp_path):
        md = tmp_path / "doc.md"
        md.write_text("# My Title\n\nParagraph content.\n", encoding="utf-8")
        ext = MarkdownExtractor()
        doc = ext.extract(md)
        assert isinstance(doc, SourceDocument)
        assert doc.title == "My Title"
        assert "Paragraph content" in doc.raw_text
        assert doc.content_length > 0
        assert doc.connector_id == "internal_mirage"

    def test_extract_preserves_content_hash(self, tmp_path):
        md = tmp_path / "hash_test.md"
        content = "# Title\nContent line."
        md.write_text(content, encoding="utf-8")
        ext = MarkdownExtractor()
        doc = ext.extract(md)
        from research import hashing
        assert doc.content_hash == hashing.content_hash(content)

    def test_extract_missing_file_raises(self, tmp_path):
        ext = MarkdownExtractor()
        with pytest.raises(FileNotFoundError):
            ext.extract(tmp_path / "nonexistent.md")

    def test_extract_non_md_raises(self, tmp_path):
        txt = tmp_path / "doc.txt"
        txt.write_text("not markdown", encoding="utf-8")
        ext = MarkdownExtractor()
        with pytest.raises(ValueError, match="Expected .md"):
            ext.extract(txt)

    def test_extract_empty_file_raises(self, tmp_path):
        md = tmp_path / "empty.md"
        md.write_text("   \n  \n", encoding="utf-8")
        ext = MarkdownExtractor()
        with pytest.raises(ValueError, match="empty"):
            ext.extract(md)

    def test_extract_no_title_uses_filename(self, tmp_path):
        md = tmp_path / "my_document.md"
        md.write_text("No heading here.\nJust text.", encoding="utf-8")
        ext = MarkdownExtractor()
        doc = ext.extract(md)
        assert doc.title == "my_document"

    def test_extract_frontmatter(self):
        ext = MarkdownExtractor()
        text = "---\ntitle: Hello\nauthor: Test\n---\n# Content"
        fm = ext.extract_frontmatter(text)
        assert fm.get("title") == "Hello"
        assert fm.get("author") == "Test"

    def test_extract_no_frontmatter(self):
        ext = MarkdownExtractor()
        fm = ext.extract_frontmatter("No frontmatter here")
        assert fm == {}

    def test_metadata_includes_line_count(self, tmp_path):
        md = tmp_path / "multi.md"
        md.write_text("# Title\nLine 1\nLine 2\nLine 3", encoding="utf-8")
        ext = MarkdownExtractor()
        doc = ext.extract(md)
        assert doc.metadata["line_count"] == 4
        assert doc.metadata["has_frontmatter"] is False

    def test_with_source_hit_id(self, tmp_path):
        md = tmp_path / "linked.md"
        md.write_text("# Linked\nContent", encoding="utf-8")
        ext = MarkdownExtractor()
        doc = ext.extract(md, source_hit_id="hit-123")
        assert doc.source_hit_id == "hit-123"

    def test_no_http_imports(self):
        """Verify zero HTTP imports in sources/ and extractors/."""
        import subprocess
        result = subprocess.run(
            ["grep", "-rc", "import requests\\|import urllib.request\\|import httpx",
             str(Path(__file__).resolve().parent.parent.parent / "lib" / "research" / "sources"),
             str(Path(__file__).resolve().parent.parent.parent / "lib" / "research" / "extractors")],
            capture_output=True, text=True,
        )
        lines = [l for l in result.stdout.strip().split("\n") if l and not l.endswith(":0")]
        assert lines == [], f"HTTP imports found: {lines}"
