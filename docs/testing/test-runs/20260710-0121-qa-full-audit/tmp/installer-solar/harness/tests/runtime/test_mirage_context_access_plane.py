import importlib.util
import json
import os
from pathlib import Path


HARNESS = Path.home() / ".solar" / "harness"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_mirage_search_registers_cocoindex_degraded_code_hits():
    mirage_search = load_module("mirage_search_test_coco", HARNESS / "lib" / "mirage_search.py")

    result = mirage_search.unified_search(
        "unified_search",
        max_hits=5,
        max_chars=2000,
        sources=["cocoindex"],
    )

    assert any(hit["source_type"] == "cocoindex" for hit in result["hits"])
    assert all(hit["layer"].startswith("code-") for hit in result["hits"])
    assert any("cocoindex" in item for item in result["degraded_sources"])
    assert result["source_counts"].get("cocoindex", 0) >= 1
    assert result["lineage_refs"]
    assert result["source_hash_refs"]


def test_understanding_adapter_reads_real_artifact_store(tmp_path, monkeypatch):
    store = tmp_path / "understanding" / "ua-test"
    store.mkdir(parents=True)
    (store / "artifact.json").write_text(
        json.dumps(
            {
                "artifact_id": "ua-test",
                "source_path": "/docs/runtime.md",
                "source_hash": "sha256:test",
                "summary": "Runtime sidecar records context lineage.",
                "claims": [{"text": "Context usage is replayable.", "confidence": 0.9}],
                "confidence": 0.8,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SOLAR_UNDERSTANDING_STORE", str(tmp_path / "understanding"))
    ua = load_module("understand_anything_adapter_test", HARNESS / "lib" / "understand_anything_adapter.py")

    hits, ok, reason = ua.search("lineage", limit=3)

    assert ok is True
    assert reason is None
    assert hits[0]["source_type"] == "understanding"
    assert hits[0]["layer"] == "understanding-summary"
    assert hits[0]["lineage"]


def test_context_usage_verifier_requires_code_source():
    verifier = load_module("context_usage_test", HARNESS / "lib" / "verifier" / "context_usage.py")

    result = verifier.verify_sidecar(
        {
            "task_kind": "code",
            "context_sources": {"cocoindex": 1, "mirage_path": 1},
            "lineage_refs": ["file:lib/mirage_search.py"],
            "source_hash_refs": ["sha256:abc"],
        }
    )

    assert result["ok"] is True
    assert result["required_sources"] == ["cocoindex"]
    assert result["missing_sources"] == []


def test_context_usage_verifier_fails_missing_required_source():
    verifier = load_module("context_usage_test_missing", HARNESS / "lib" / "verifier" / "context_usage.py")

    result = verifier.verify_sidecar(
        {
            "task_kind": "paper",
            "context_sources": {"mirage_path": 1},
            "lineage_refs": ["file:/docs/paper.pdf"],
        }
    )

    assert result["ok"] is False
    assert result["missing_sources"] == ["understanding"]
