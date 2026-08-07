"""Store path resolution + persistence isolation tests."""
import os

import pytest

from lib.influence import store


def test_resolve_root_prefers_argument(tmp_path):
    assert store.resolve_root(tmp_path) == tmp_path


def test_resolve_root_uses_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KNOWLEDGE_ROOT", str(tmp_path))
    assert store.resolve_root() == tmp_path


def test_extracted_dir_rejects_unknown_bucket(isolated_knowledge_root):
    with pytest.raises(ValueError):
        store.extracted_dir("not_a_bucket")


def test_persist_writes_within_root(isolated_knowledge_root):
    path = store.persist("statements", "stmt-1", {"k": "v"})
    assert path.exists()
    assert str(isolated_knowledge_root) in str(path)
    assert store.read_json(path) == {"k": "v"}


def test_raw_dir_known_sources(isolated_knowledge_root):
    p = store.raw_dir("x_backend")
    assert "_raw" in str(p)
    with pytest.raises(ValueError):
        store.raw_dir("unknown_source")
