"""test_sources_mirage — Verify InternalMirageConnector."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from research.sources.internal_mirage import InternalMirageConnector


class TestInternalMirageConnector:
    def test_class_attributes(self):
        c = InternalMirageConnector()
        assert c.connector_id == "internal_mirage"
        assert c.connector_type == "internal_mirage"
        assert c.source_tier == "internal"

    def test_custom_vault_path(self, tmp_path):
        c = InternalMirageConnector(vault_path=tmp_path)
        assert c.vault_path == tmp_path

    def test_fetch_existing_file(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("# Test Title\nSome content here.", encoding="utf-8")
        c = InternalMirageConnector(vault_path=tmp_path)
        result = c.fetch(f"mirage:test.md")
        assert result.fetch_status == "fetched"
        assert "Test Title" in result.raw_text
        assert result.title == "test"
        assert result.content_length > 0

    def test_fetch_missing_file(self, tmp_path):
        c = InternalMirageConnector(vault_path=tmp_path)
        result = c.fetch("mirage:nonexistent.md")
        assert result.fetch_status == "failed"
        assert "not found" in (result.fetch_error or "").lower()

    def test_fetch_invalid_source_id(self, tmp_path):
        c = InternalMirageConnector(vault_path=tmp_path)
        result = c.fetch("bad_id_format")
        assert result.fetch_status == "failed"
        assert "invalid" in (result.fetch_error or "").lower()

    def test_search_returns_list(self, tmp_path):
        c = InternalMirageConnector(vault_path=tmp_path)
        results = c.search("test query", max_hits=5)
        assert isinstance(results, list)

    def test_search_graceful_on_missing_cmd(self, tmp_path):
        c = InternalMirageConnector(vault_path=tmp_path)
        results = c.search("unlikely-to-crash-query", max_hits=3)
        assert isinstance(results, list)

    def test_is_subclass_of_base(self):
        from research.sources.base import BaseSourceConnector
        assert issubclass(InternalMirageConnector, BaseSourceConnector)
