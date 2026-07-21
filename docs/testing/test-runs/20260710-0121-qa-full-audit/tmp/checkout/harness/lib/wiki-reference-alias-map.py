#!/usr/bin/env python3
"""Create explicit reference alias/bridge pages for broken wiki links.

The generated pages are graph repair artifacts. They do not claim to be deep
knowledge notes; each page either redirects to an existing canonical note or
bridges an old artifact-catalog slug back to its catalog/provenance page.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VAULT = Path.home() / "Knowledge"


ALIASES: dict[str, dict[str, Any]] = {
    "references/20260508t225447z-0005-精品文章-hotchip-2025_day2-ai芯片和光互连": {
        "title": "HotChip 2025 Day2 AI芯片和光互连",
        "canonical": "references/精品文章-hotchip-2025_day2-ai芯片和光互连",
    },
    "references/revisiting-reinforcement-learning-for-llm-reasoning-from-a-cross-domain-perspect": {
        "title": "Revisiting Reinforcement Learning for LLM Reasoning",
        "canonical": "references/论文集合-reasoning-强化学习-revisiting-reinforcement-learning-for-llm-reasoning-from-a-cross-domai",
    },
    "references/dynamic-and-generalizable-process-reward-modeling": {
        "title": "Dynamic and Generalizable Process Reward Modeling",
        "canonical": "references/论文集合-reasoning-强化学习-dynamic-and-generalizable-process-reward-modeling",
    },
    "references/open-universe-assistance-games-arxiv2508": {
        "title": "Open Universe Assistance Games",
        "canonical": "references/20260509T033800Z-open-universe-assistance-games-arxiv2508",
    },
    "references/20260508t225447z-0003-精品文章-hotchip-2025_-day1网络篇": {
        "title": "HotChip 2025 Day1 网络篇",
        "canonical": "references/精品文章-hotchip-2025_-day1网络篇",
    },
    "references/hotchip-2025_day2-ai芯片和光互连": {
        "title": "HotChip 2025 Day2 AI芯片和光互连",
        "canonical": "references/精品文章-hotchip-2025_day2-ai芯片和光互连",
    },
    "references/20260508t225447z-0002-精品文章-google-deepmind-ai下一阶段的预测-hot-chips-2025-主题演讲": {
        "title": "Google DeepMind AI 下一阶段预测 Hot Chips 2025",
        "canonical": "references/精品文章-google-deepmind-ai下一阶段的预测-hot-chips-2025-主题演讲",
    },
    "references/20260508t225447z-0004-精品文章-hotchip-2025_day1处理器_安全篇": {
        "title": "HotChip 2025 Day1 处理器安全篇",
        "canonical": "references/精品文章-hotchip-2025_day1处理器_安全篇",
    },
    "references/dynamic-generalizable-process-reward-modeling-arxiv2507": {
        "title": "Dynamic Generalizable Process Reward Modeling arXiv 2507",
        "canonical": "references/20260509T034007Z-dynamic-generalizable-process-reward-modeling-arxiv2507",
    },
    "references/rethinking-reasoning-quality-enhanced-cot-rl-arxiv2509": {
        "title": "Rethinking Reasoning Quality Enhanced CoT RL arXiv 2509",
        "canonical": "references/20260509T034006Z-rethinking-reasoning-quality-enhanced-cot-rl-arxiv2509",
    },
    "references/memory_system_architecture": {
        "title": "Memory System Architecture",
        "canonical": "references/solar-cortex-9-memory-system-architecture",
    },
    "references/solar_core_architecture": {
        "title": "Solar Core Architecture",
        "canonical": "references/solar-namespace-architecture",
    },
    "references/solar-architecture": {
        "title": "Solar Architecture",
        "canonical": "references/solar-system-architecture-20260508",
    },
    "references/nvidia-gtc-2026": {
        "title": "NVIDIA GTC 2026",
        "canonical": "references/nvidia-gtc-2026-compute-architecture-forecast",
    },
    "references/solar-intent-engine": {
        "title": "Solar Intent Engine",
        "canonical": "references/solar-cortex-126-intent-engine",
    },
    "references/architecture-mac-mini-remote-runner": {
        "title": "Mac mini Remote Runner Architecture",
        "canonical": "references/solar-infrastructure-mac-mini",
    },
    "references/solar-farm-niuma-roster": {
        "title": "Solar Farm Niuma Roster",
        "canonical": "references/solar-concept-niuma-workers",
    },
    "references/brain-router-mcp": {
        "title": "Brain Router MCP",
        "canonical": "references/solar-concept-t8-brain-router-task",
        "related": ["concepts/brain-router-design"],
    },
    "references/no-mock-principle": {
        "title": "No Mock Principle",
        "canonical": "rules/no-mock",
        "related": ["references/lesson-questioning-todowrite-glm-mock"],
    },
    "references/feedback-verify-deliverables-not-claims": {
        "title": "Verify Deliverables, Not Claims",
        "canonical": "references/lesson-questioning-todowrite-glm-mock",
        "related": ["rules/no-mock", "references/solar-harness-skills-readiness-certify"],
    },
    "references/multi-expert-analysis": {
        "title": "Multi Expert Analysis",
        "canonical": "references/solar-farm-lesson-multi-niuma-wisdom",
        "related": ["rules/solar-farm", "rules/delegate-first"],
    },
}


ARTIFACT_BRIDGES = [
    "references/ai_native_os_architecture",
    "references/capsule_architecture",
    "references/codex-usage-policy",
    "references/community_neural_network_design",
    "references/coordinator-dispatch-flow",
    "references/mermaid-viewer-integration",
    "references/mineru-document-explorer-integration",
    "references/mirage-cortex-access-test-20260508",
    "references/mirage-data-substrate-codex-solar",
    "references/mirage-unified-vfs",
    "references/obsidian-wiki-integration",
    "references/persona_engine_design",
    "references/solar-kb-obsidian-autouse",
    "references/solar-workstream-verification-20260508",
    "references/solar_data_agent_design",
    "references/solar_data_agent_design_v2",
    "references/solar_organism_architecture",
    "references/solar_technical_report_v2",
    "references/symphony-integration-adr",
    "references/wiki-upload-ingest-closure",
]


def title_from_slug(slug: str) -> str:
    name = Path(slug).name
    return name.replace("_", " ").replace("-", " ").strip().title()


def target_path(vault: Path, rel_no_ext: str) -> Path:
    return vault / f"{rel_no_ext}.md"


def canonical_exists(vault: Path, rel_no_ext: str) -> bool:
    return target_path(vault, rel_no_ext).exists()


def render_alias(slug: str, spec: dict[str, Any], vault: Path) -> str:
    canonical = spec["canonical"]
    related = spec.get("related") or []
    related_lines = "\n".join(f"- [[{item}]]" for item in related)
    if related_lines:
        related_block = f"\n## Related\n\n{related_lines}\n"
    else:
        related_block = ""
    exists = "ok" if canonical_exists(vault, canonical) else "warn"
    return f"""---
title: "{spec['title']}"
category: references
tags: [alias, reference-redirect, knowledge-graph-repair]
source: solar-harness
created: 2026-05-12
updated: 2026-05-12
lifecycle: alias
alias_for: {slug}
canonical: {canonical}
canonical_exists: {exists}
---

# {spec['title']}

This page is a graph-repair alias for the legacy link `{slug}`.

## Canonical Target

- [[{canonical}]]
{related_block}
## Boundary

This is not a deep synthesis note. It exists to preserve legacy links and route
readers to the canonical knowledge page.
"""


def render_bridge(slug: str) -> str:
    title = title_from_slug(slug)
    return f"""---
title: "{title}"
category: references
tags: [alias, artifact-bridge, knowledge-graph-repair]
source: solar-harness
created: 2026-05-12
updated: 2026-05-12
lifecycle: artifact-bridge
alias_for: {slug}
canonical: references/solar-artifact-ingest-catalog-20260508
canonical_exists: ok
---

# {title}

This page is a legacy artifact bridge for `{slug}`.

## Canonical Catalog

- [[references/solar-artifact-ingest-catalog-20260508]]

## Boundary

The original link referred to an artifact-catalog entry, not a completed deep
knowledge note. This bridge keeps the graph connected without pretending that a
separate synthesis page exists.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply explicit reference alias map")
    parser.add_argument("--vault", default=str(VAULT))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    vault = Path(args.vault)
    planned: list[dict[str, str]] = []
    for slug, spec in sorted(ALIASES.items()):
        out = target_path(vault, slug)
        planned.append({"slug": slug, "path": str(out), "mode": "alias", "canonical": spec["canonical"]})
        if args.apply:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render_alias(slug, spec, vault), encoding="utf-8")
    for slug in sorted(ARTIFACT_BRIDGES):
        out = target_path(vault, slug)
        planned.append({"slug": slug, "path": str(out), "mode": "artifact-bridge", "canonical": "references/solar-artifact-ingest-catalog-20260508"})
        if args.apply:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render_bridge(slug), encoding="utf-8")

    result = {"apply": args.apply, "count": len(planned), "planned": planned}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"apply={args.apply} count={len(planned)}")
        for item in planned:
            print(f"{item['mode']} {item['slug']} -> {item['canonical']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
