"""Shared writing contract for high-density DeepResearch reports."""

from __future__ import annotations

from typing import Any


GOLDEN_STYLE_CONTRACT: dict[str, Any] = {
    "policy_id": "solar.survey.golden_style.v1",
    "goal": "Produce a report that reads like an expert chapter, not a stitched evidence ledger or smoke-test summary.",
    "minimum_shape": [
        "Every major chapter opens with a thesis judgment, not a neutral topic summary.",
        "Every mechanism subsection explains what problem the technique solves and what new failure mode it introduces.",
        "Every evaluation subsection includes an interpretation paragraph: what the experiment does and does not prove.",
        "Every chapter ends with a final judgment that can be challenged against evidence.",
    ],
    "rhetorical_moves": [
        "Use '不是 X，而是 Y' when correcting a common but wrong framing.",
        "Use explicit labels such as '评价', '硬伤', '实验怎么读', '最终判断', and '关键机制' when they fit the evidence.",
        "Prefer cause-and-effect explanations over source-by-source summaries.",
        "Name the tradeoff: accuracy vs cost, observability vs capability, throughput vs latency, or benchmark fit vs deployment fit.",
    ],
    "section_blocks": [
        "Problem framing",
        "Mechanism",
        "What this solves",
        "Experiment or evidence reading",
        "Limitations and hard failures",
        "Final judgment",
    ],
    "forbidden_patterns": [
        "No prompt residue, packet names, claim/evidence debug tags, or scaffold language in human-facing output.",
        "No generic 'future work' paragraph unless it names the missing experiment, source family, or deployment boundary.",
        "No source dump: citations must support a claim, contrast, or limitation.",
    ],
    "quality_targets": {
        "min_final_chars_with_benchmark": ">= 45% of approved HTML benchmark plain-text chars, floor 30000",
        "min_word_count_with_benchmark": ">= 55% of approved HTML benchmark word score, floor 8000",
        "min_heading_count_with_benchmark": ">= 35% of approved HTML benchmark headings, floor 35",
        "style_density": "Enough judgment terms and interpretive labels to avoid neutral summaries",
    },
}


def render_golden_style_contract_markdown(contract: dict[str, Any] | None = None) -> str:
    payload = contract or GOLDEN_STYLE_CONTRACT
    lines = [
        "## Golden-Style Writing Contract",
        "",
        f"- Policy: `{payload.get('policy_id', 'unknown')}`",
        f"- Goal: {payload.get('goal', '')}",
        "",
        "### Minimum Shape",
        "",
    ]
    lines.extend(f"- {item}" for item in payload.get("minimum_shape", []))
    lines.extend(["", "### Rhetorical Moves", ""])
    lines.extend(f"- {item}" for item in payload.get("rhetorical_moves", []))
    lines.extend(["", "### Required Section Blocks", ""])
    lines.extend(f"- {item}" for item in payload.get("section_blocks", []))
    lines.extend(["", "### Forbidden Patterns", ""])
    lines.extend(f"- {item}" for item in payload.get("forbidden_patterns", []))
    targets = payload.get("quality_targets", {})
    if isinstance(targets, dict) and targets:
        lines.extend(["", "### Quality Targets", ""])
        for key, value in targets.items():
            lines.append(f"- {key}: {value}")
    return "\n".join(lines).strip() + "\n"
