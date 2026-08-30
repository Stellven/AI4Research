from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


HARNESS = Path(__file__).resolve().parents[3] / "harness"
PLUGIN = HARNESS / "plugins" / "autosci"
sys.path.insert(0, str(PLUGIN))

from services import production_research  # noqa: E402


PLANNER_SCOPE = """Discover a ranked literature shortlist for KV cache efficiency.

Authoritative discovery scope:
- [R2] Treat the task as an end-to-end research workflow, rather than a one-off answer. Required coverage: end-to-end research workflow
- [R3] Use the project name KV Cache Efficiency Landscape for Long-Context LLM Inference. Required coverage: KV Cache Efficiency Landscape for Long-Context LLM Inference
- [R4] Cover KV cache compression, quantization, selection, eviction, and sparsification. Required coverage: compression; quantization; selection; eviction; sparsification
- [R5] Study the methods for long-context large language model inference. Required coverage: long-context large language model inference
- [R6] The report must be comprehensive. Required coverage: comprehensive
- [R7] Include an explicit evidence chain that is auditable and extensible for future research. Required coverage: explicit; auditable; extensible for future research
"""


def test_planner_scope_distills_provider_query_to_retrieval_subject() -> None:
    query = production_research._topic_from_snapshot(
        {"seeds": [{"seed_kind": "topic", "content": PLANNER_SCOPE}]},
        {"task_contract": {"user_intent": PLANNER_SCOPE}},
    )

    assert "KV Cache Efficiency Landscape" in query
    assert "compression" in query
    assert "quantization" in query
    assert "sparsification" in query
    assert "end-to-end research workflow" not in query
    assert "auditable" not in query


def test_relevance_gate_allows_specialists_and_enforces_collective_coverage() -> None:
    candidates = [
        {
            "source_id": "paper:kivi",
            "canonical_id": "https://example.test/kivi",
            "title": "KIVI: KV Cache Quantization and Compression",
            "provider": "semantic_scholar",
            "content_summary": "An efficiency landscape for long-context LLM inference using large language model key value cache quantization and compression.",
        },
        {
            "source_id": "paper:h2o",
            "canonical_id": "https://example.test/h2o",
            "title": "H2O: Heavy-Hitter KV Cache Eviction",
            "provider": "arxiv",
            "content_summary": "Token selection and eviction for long context large language model inference.",
        },
        {
            "source_id": "paper:scissorhands",
            "canonical_id": "https://example.test/scissorhands",
            "title": "Scissorhands: Sparse KV Cache Pruning",
            "provider": "openalex",
            "content_summary": "Pruning for efficient long context LLM inference.",
        },
        {
            "source_id": "paper:driving",
            "canonical_id": "https://example.test/driving",
            "title": "End-to-End Autonomous Driving",
            "provider": "arxiv",
            "content_summary": "A vision language model workflow for motion planning.",
        },
    ]

    accepted, audit = production_research.apply_discovery_relevance_gate(PLANNER_SCOPE, candidates)

    assert audit["status"] == "passed"
    assert audit["accepted_candidate_count"] == 3
    assert {item["source_id"] for item in accepted} == {
        "paper:kivi",
        "paper:h2o",
        "paper:scissorhands",
    }
    assert "workflow" not in audit["query_terms"]


def test_coverage_recovery_query_targets_the_missing_method() -> None:
    _, audit = production_research.apply_discovery_relevance_gate(
        PLANNER_SCOPE,
        [
            {
                "source_id": "paper:kivi",
                "canonical_id": "https://example.test/kivi",
                "title": "KV Cache Quantization Compression Selection and Eviction",
                "provider": "arxiv",
                "content_summary": "Efficiency landscape for long context LLM large language model inference.",
            }
        ],
        minimum_relevant_candidates=1,
    )

    queries = production_research._coverage_recovery_queries(PLANNER_SCOPE, audit)

    assert any("sparsification" in query for query in queries)
    assert any("sparse pruning" in query for query in queries)
    assert all("workflow" not in query for query in queries)


def test_installed_bridge_does_not_adopt_an_unrelated_parent_tool(monkeypatch, tmp_path: Path) -> None:
    bridge_path = PLUGIN / "bin" / "autosci_bridge.py"
    sys.path.insert(0, str(PLUGIN / "bin"))
    spec = importlib.util.spec_from_file_location("_test_autosci_bridge", bridge_path)
    assert spec is not None and spec.loader is not None
    bridge = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = bridge
    spec.loader.exec_module(bridge)

    runtime = tmp_path / "installed" / "harness"
    runtime.mkdir(parents=True)
    unrelated = runtime.parent / "tools"
    unrelated.mkdir()
    unrelated.joinpath("discover.py").write_text("raise SystemExit(99)\n", encoding="utf-8")
    monkeypatch.setattr(bridge, "HARNESS_DIR", runtime)
    monkeypatch.setattr(bridge, "REPO_HARNESS_DIR", runtime)

    assert bridge._resolve_root_tool("discover.py") == (None, None)

    runtime_tool = runtime / "tools" / "discover.py"
    runtime_tool.parent.mkdir()
    runtime_tool.write_text("print('{}')\n", encoding="utf-8")
    assert bridge._resolve_root_tool("discover.py") == (runtime_tool.resolve(), runtime)
