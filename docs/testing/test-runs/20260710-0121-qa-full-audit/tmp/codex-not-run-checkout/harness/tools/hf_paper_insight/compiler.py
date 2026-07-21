"""Compiler for seven output assets in HF Paper Insight runtime."""
from __future__ import annotations

import json

from schema import PaperEvidencePacket


def _load_packet_json(packet: PaperEvidencePacket, field_name: str) -> dict:
    raw = getattr(packet, field_name, "{}") or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


class Compiler:
    """Compiles a validated packet into seven downstream content assets."""

    OUTPUT_KEYS = (
        "report",
        "cards",
        "seeds",
        "topics",
        "experiments",
        "projects",
        "deep_research",
    )

    def compile_outputs(self, packet: PaperEvidencePacket, reasoning: dict, resonance: dict) -> dict[str, str]:
        canonical = _load_packet_json(packet, "canonical_summary_json")
        taxonomy = _load_packet_json(packet, "taxonomy_summary_json")
        scores = _load_packet_json(packet, "score_summary_json")
        title = str(canonical.get("title") or packet.paper_id)
        authors = canonical.get("authors", [])
        author_names = ", ".join(
            item.get("name", "") if isinstance(item, dict) else str(item)
            for item in authors[:4]
        ) or "N/A"
        resonance_level = str(resonance.get("resonance_level") or "R0")
        top_dimensions = reasoning.get("top_dimensions", [])
        top_dim_text = ", ".join(f"{item['name']}={item['score']:.3f}" for item in top_dimensions) or "N/A"

        base = {
            "title": title,
            "paper_id": packet.paper_id,
            "domain": taxonomy.get("domain", "other"),
            "stack_layer": taxonomy.get("stack_layer", "model"),
            "research_route": taxonomy.get("research_route", "applied_research"),
            "resonance_level": resonance_level,
            "top_dimensions": top_dim_text,
        }

        outputs = {
            "report": self._report_markdown(base, author_names, reasoning, resonance),
            "cards": self._cards_markdown(base, reasoning, resonance),
            "seeds": self._seeds_markdown(base, reasoning),
            "topics": self._topics_markdown(base, taxonomy, scores),
            "experiments": self._experiments_markdown(base, reasoning),
            "projects": self._projects_markdown(base, reasoning),
            "deep_research": self._deep_research_markdown(base, reasoning, resonance),
        }
        return outputs

    def _report_markdown(self, base: dict, author_names: str, reasoning: dict, resonance: dict) -> str:
        hypotheses = "\n".join(f"- {item}" for item in reasoning.get("hypotheses", []))
        reasons = "\n".join(f"- {item}" for item in resonance.get("reasons", []))
        return f"""# HF Insight Report: {base['title']}

- `paper_id`: {base['paper_id']}
- `authors`: {author_names}
- `domain`: {base['domain']}
- `stack_layer`: {base['stack_layer']}
- `research_route`: {base['research_route']}
- `resonance_level`: {base['resonance_level']}
- `top_dimensions`: {base['top_dimensions']}

## Judgment

{reasoning.get('summary', 'N/A')}

## Hypotheses

{hypotheses or '- N/A'}

## Resonance Reasons

{reasons or '- N/A'}
"""

    def _cards_markdown(self, base: dict, reasoning: dict, resonance: dict) -> str:
        return f"""# Paper Insight Cards

- 标题: {base['title']}
- 共振等级: {base['resonance_level']}
- 候选资产: {', '.join(resonance.get('candidate_assets', []))}
- 速记: {reasoning.get('summary', 'N/A')}
"""

    def _seeds_markdown(self, base: dict, reasoning: dict) -> str:
        questions = "\n".join(f"- {item}" for item in reasoning.get("strategic_questions", []))
        return f"""# Three-source Resonance Seeds

- seed_theme: {base['domain']} / {base['stack_layer']}
- driver: {base['top_dimensions']}

## Questions

{questions or '- N/A'}
"""

    def _topics_markdown(self, base: dict, taxonomy: dict, scores: dict) -> str:
        return f"""# AI Influence Topic Pool

- topic: {taxonomy.get('domain', 'other')}
- method: {taxonomy.get('method', 'other')}
- task: {taxonomy.get('task', 'other')}
- route: {taxonomy.get('research_route', 'applied_research')}
- novelty: {scores.get('novelty', 0.0)}
- industry_coupling: {scores.get('industry_coupling', 0.0)}
"""

    def _experiments_markdown(self, base: dict, reasoning: dict) -> str:
        return f"""# Experiment Tasks

1. 验证 {base['stack_layer']} 路径的关键假设
2. 对照 {base['domain']} 基线做复现实验
3. 根据 `{base['top_dimensions']}` 设计最小 sanity-check

> {reasoning.get('summary', 'N/A')}
"""

    def _projects_markdown(self, base: dict, reasoning: dict) -> str:
        return f"""# Open-source Project Briefs

- project_direction: {base['research_route']}
- target_layer: {base['stack_layer']}
- resonance: {base['resonance_level']}
- build_note: {reasoning.get('summary', 'N/A')}
"""

    def _deep_research_markdown(self, base: dict, reasoning: dict, resonance: dict) -> str:
        assets = ", ".join(resonance.get("candidate_assets", []))
        questions = "\n".join(f"- {item}" for item in reasoning.get("strategic_questions", []))
        return f"""# Deep Research Seed Pack

- topic: {base['title']}
- route: {base['research_route']}
- resonance: {base['resonance_level']}
- candidate_assets: {assets}

## Follow-up Questions

{questions or '- N/A'}
"""
