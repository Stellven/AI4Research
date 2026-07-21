from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.cli import main
from research.survey.evidence_pack import build_evidence_packs
from research.survey.paper_enrichment import enrich_papers


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def test_paper_enrichment_clusters_catalog_abstracts(tmp_path):
    catalog = {
        "papers": [
            {
                "url": "https://example.test/optany",
                "pillar": "System Optimization & Efficiency",
                "title_blob": "optimize_anything: Unified Text Optimization. An agent optimization system improves scheduling cost and benchmark accuracy.",
            },
            {
                "url": "https://example.test/security",
                "pillar": "Security & Privacy",
                "title_blob": "Retrieval-Augmented LLMs for Security Incident Analysis. The paper studies security incident workflows, risk, and evaluation.",
            },
            {
                "url": "https://example.test/deepresearch",
                "pillar": "Architectural Patterns & Composition",
                "title_blob": "EigentSearch-Q+: Enhancing Deep Research Agents with Structured Reasoning Tools. The demo connects retrieval, evidence, and citation workflows.",
            },
        ]
    }
    (tmp_path / "cais2026_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    payload = enrich_papers(tmp_path, max_papers=10, allow_search=False)

    assert payload["ok"] is True
    assert payload["seed_count"] == 3
    assert payload["paper_count"] == 3
    assert payload["papers"][0]["title"].startswith("EigentSearch-Q+")
    assert len(payload["clusters"]) >= 3
    assert any(trend["theme_id"] == "deep_research" for trend in payload["trends"])
    assert (tmp_path / "paper_enrichment.json").exists()
    assert (tmp_path / "paper_theme_clusters.json").exists()
    assert (tmp_path / "paper_trend_synthesis.md").exists()


def test_paper_enrichment_recursive_search_uses_title_queries(tmp_path):
    title_file = tmp_path / "titles.txt"
    title_file.write_text("A Language for Describing Agentic LLM Contexts\n", encoding="utf-8")
    queries: list[str] = []

    def fake_search(query: str, max_results: int, provider: str):
        queries.append(query)
        return [
            {
                "title": "A Language for Describing Agentic LLM Contexts",
                "url": "https://example.test/paper",
                "snippet": "Agent context architecture memory tool composition and evaluation.",
                "connector": provider,
            }
        ], []

    payload = enrich_papers(
        tmp_path,
        input_titles=title_file,
        allow_search=True,
        search_fn=fake_search,
        provider="serper",
        recursion_depth=2,
        max_results=1,
    )

    assert payload["ok"] is True
    assert len(queries) == 3
    assert queries[0] == '"A Language for Describing Agentic LLM Contexts" paper abstract'
    assert any("related work agent system" in query for query in queries)
    assert payload["papers"][0]["queries"] or payload["papers"][1]["queries"]


def test_survey_pack_attaches_matching_paper_trends(tmp_path):
    (tmp_path / "paper_theme_clusters.json").write_text(json.dumps({
        "ok": True,
        "trends": [
            {
                "trend_id": "trend_agent",
                "theme_id": "agent_architecture",
                "label": "Agent Architecture & Composition",
                "claim": "Agent architecture uses context, tool, memory, and workflow composition.",
                "representative_titles": ["A Language for Describing Agentic LLM Contexts"],
            }
        ],
    }), encoding="utf-8")
    _write_jsonl(tmp_path / "sources.jsonl", [
        {"id": "src_1", "source_type": "paper", "title": "A Language for Describing Agentic LLM Contexts"},
        {"id": "src_2", "source_type": "code", "title": "Agent Context Runtime"},
    ])
    _write_jsonl(tmp_path / "evidence.jsonl", [
        {"id": "ev_1", "source_id": "src_1", "content": "agent context architecture memory tool workflow"},
        {"id": "ev_2", "source_id": "src_2", "content": "agent context runtime code"},
    ])
    _write_jsonl(tmp_path / "claims.jsonl", [
        {"id": "cl_1", "claim_text": "agent context architecture requires tool and memory composition"},
        {"id": "cl_2", "claim_text": "agent runtime code implements context workflow"},
        {"id": "cl_3", "claim_text": "agent architecture needs evaluation"},
    ])
    _write_jsonl(tmp_path / "claim_evidence.jsonl", [
        {"claim_id": "cl_1", "evidence_id": "ev_1"},
        {"claim_id": "cl_2", "evidence_id": "ev_2"},
        {"claim_id": "cl_3", "evidence_id": "ev_1"},
    ])
    ast = {
        "sections": [
            {
                "section_id": "ch01/sec01",
                "title": "Agent context architecture",
                "research_question": "How do context, tool, and memory composition shape agent architecture?",
                "min_evidence": 2,
                "min_claims": 3,
                "required_source_types": ["paper", "code"],
            }
        ]
    }

    payload = build_evidence_packs(tmp_path, ast)
    pack = payload["packs"][0]

    assert pack["status"] == "ready"
    assert pack["paper_trend_ids"] == ["trend_agent"]
    assert (tmp_path / "sections" / "ch01" / "sec01" / "evidence_pack.json").exists()


def test_survey_enrich_papers_cli(tmp_path, capsys):
    title_file = tmp_path / "titles.txt"
    title_file.write_text("Parallel Environments for Agents\n", encoding="utf-8")
    rc = main([
        "survey-enrich-papers",
        "--output-dir", str(tmp_path),
        "--input-titles", str(title_file),
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["seed_count"] == 1
