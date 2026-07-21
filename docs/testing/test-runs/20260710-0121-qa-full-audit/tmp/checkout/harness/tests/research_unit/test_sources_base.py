"""test_sources_base — Verify BaseSourceConnector abstract interface."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from research.sources.base import BaseSourceConnector, SearchResult, FetchResult


class ConcreteConnector(BaseSourceConnector):
    connector_id = "test_connector"
    connector_type = "file"
    source_tier = "internal"
    display_name = "Test Connector"

    def search(self, query, max_hits=10, **kwargs):
        return [SearchResult(source_id="test:1", connector_id=self.connector_id, title=f"Hit for {query}")]

    def fetch(self, source_id):
        return FetchResult(source_id=source_id, connector_id=self.connector_id, title="Test Doc", raw_text="content")


class TestSearchResult:
    def test_basic_creation(self):
        sr = SearchResult(source_id="s1", connector_id="c1", title="Test")
        assert sr.source_id == "s1"
        assert sr.score == 0.0
        assert sr.metadata == {}

    def test_with_all_fields(self):
        sr = SearchResult(source_id="s1", connector_id="c1", title="T", snippet="snip", score=0.9)
        assert sr.snippet == "snip"
        assert sr.score == 0.9


class TestFetchResult:
    def test_auto_content_length(self):
        fr = FetchResult(source_id="s1", connector_id="c1", title="T", raw_text="hello world")
        assert fr.content_length == 11

    def test_failed_without_error_raises(self):
        with pytest.raises(ValueError, match="fetch_error"):
            FetchResult(source_id="s1", connector_id="c1", title="T", raw_text="", fetch_status="failed")

    def test_failed_with_error_ok(self):
        fr = FetchResult(source_id="s1", connector_id="c1", title="T", raw_text="", fetch_status="failed", fetch_error="timeout")
        assert fr.fetch_error == "timeout"


class TestBaseSourceConnector:
    def test_concrete_subclass_instantiates(self):
        c = ConcreteConnector()
        assert c.connector_id == "test_connector"

    def test_search_returns_results(self):
        c = ConcreteConnector()
        results = c.search("test query")
        assert len(results) == 1
        assert "test query" in results[0].title

    def test_fetch_returns_result(self):
        c = ConcreteConnector()
        fr = c.fetch("test:1")
        assert fr.raw_text == "content"

    def test_health_check_default(self):
        c = ConcreteConnector()
        health = c.health_check()
        assert health["status"] == "active"

    def test_repr(self):
        c = ConcreteConnector()
        assert "test_connector" in repr(c)

    def test_missing_class_attr_raises(self):
        with pytest.raises(TypeError, match="connector_id"):
            class BadConnector(BaseSourceConnector):
                connector_type = "file"
                source_tier = "internal"
                display_name = "Bad"

                def search(self, query, max_hits=10, **kwargs): return []
                def fetch(self, source_id): pass
