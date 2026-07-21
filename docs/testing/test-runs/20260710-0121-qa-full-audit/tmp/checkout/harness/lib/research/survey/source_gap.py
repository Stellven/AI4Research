"""Survey-specific source gap detection and human-search handoff rendering."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

RESEARCH_ANGLES = {
    "literature_lineage": "文献谱系 / Literature lineage",
    "method_taxonomy": "方法分类 / Method taxonomy",
    "evaluation_protocol": "评估协议 / Evaluation protocol",
    "controversy": "争议反证 / Controversy and negative evidence",
    "engineering": "工程部署 / Engineering and deployment",
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def assess_source_gap(
    output_dir: str | Path,
    *,
    brief: str = "",
    min_sources: int = 4,
    min_evidence: int = 8,
    min_claims: int = 8,
    required_source_types: list[str] | None = None,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    ast = _read_json(root / "survey_report_ast.json")
    source_matrix = _read_json(root / "survey_source_matrix.json")
    matrix_rows = source_matrix.get("source_matrix") if isinstance(source_matrix.get("source_matrix"), list) else source_matrix
    required = set(required_source_types or [])
    if isinstance(matrix_rows, list):
        for row in matrix_rows:
            if not isinstance(row, dict):
                continue
            required.update(str(item) for item in row.get("required_source_types", []) if item)
    if not required:
        required.update(["paper", "official_doc", "code", "benchmark"])
    sources = _read_jsonl(root / "sources.jsonl")
    evidence = _read_jsonl(root / "evidence.jsonl")
    claims = _read_jsonl(root / "claims.jsonl")
    observed_types = {str(row.get("source_type") or "") for row in sources if row.get("source_type")}
    source_type_counts: dict[str, int] = {}
    for row in sources:
        source_type = str(row.get("source_type") or "unknown")
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
    missing_types = sorted(required - observed_types)
    issues: list[str] = []
    if len(sources) < min_sources:
        issues.append(f"source_count_low:{len(sources)}<{min_sources}")
    if len(evidence) < min_evidence:
        issues.append(f"evidence_count_low:{len(evidence)}<{min_evidence}")
    if len(claims) < min_claims:
        issues.append(f"claim_count_low:{len(claims)}<{min_claims}")
    if missing_types:
        issues.append("missing_source_types:" + ",".join(missing_types))
    payload = {
        "ok": not issues,
        "brief": brief or ast.get("title") or root.name,
        "output_dir": str(root),
        "source_count": len(sources),
        "evidence_count": len(evidence),
        "claim_count": len(claims),
        "min_sources": min_sources,
        "min_evidence": min_evidence,
        "min_claims": min_claims,
        "source_type_counts": source_type_counts,
        "required_source_types": sorted(required),
        "missing_source_types": missing_types,
        "issues": issues,
        "handoff_path": str(root / "survey_source_gap_handoff.md"),
    }
    (root / "survey_source_gap.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def render_source_gap_handoff(gap: dict[str, Any], *, max_results: int = 12) -> str:
    brief = str(gap.get("brief") or "N/A")
    missing = list(gap.get("missing_source_types") or [])
    if not missing:
        missing = list(gap.get("required_source_types") or ["paper", "official_doc", "code", "benchmark"])
    evidence_gap = max(int(gap.get("min_evidence", 0) or 0) - int(gap.get("evidence_count", 0) or 0), 0)
    claim_gap = max(int(gap.get("min_claims", 0) or 0) - int(gap.get("claim_count", 0) or 0), 0)
    required_types = list(gap.get("required_source_types") or [])
    needed_results = max(
        int(max_results or 0),
        len(required_types) * 2,
        math.ceil(evidence_gap / 2) if evidence_gap else 0,
        math.ceil(claim_gap / 2) if claim_gap else 0,
    )
    needed_results = max(needed_results, 1)
    query_plan = "\n".join(
        f"| {source_type} | {max(2, math.ceil(needed_results / max(len(missing), 1)))} | `{brief} {source_type} primary source literature lineage method taxonomy evaluation protocol controversy engineering` |"
        for source_type in missing
    )
    angle_plan = "\n".join(
        f"| {angle} | {label} | `{brief} {label} primary source` |"
        for angle, label in RESEARCH_ANGLES.items()
    )
    issues = "\n".join(f"- {item}" for item in gap.get("issues", [])) or "- N/A"
    slot_types = (missing or list(gap.get("required_source_types") or [])) or ["paper", "official_doc", "code", "benchmark"]
    template_blocks = []
    for idx in range(1, needed_results + 1):
        source_type = slot_types[(idx - 1) % len(slot_types)]
        angle = list(RESEARCH_ANGLES.keys())[(idx - 1) % len(RESEARCH_ANGLES)]
        template_blocks.append(f"""## Source {idx}: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: {source_type}
Research Angles: {angle}

Summary:
- <2-5 factual bullets covering the selected Research Angles>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

Why this source fixes the gap:
- <which missing source type, research angle, or claim gap it covers>
""")
    returned_template = "\n\n".join([f"# External Search Results: {brief}", *template_blocks])
    return f"""# Solar DeepResearch Survey Source Gap Handoff

你现在扮演外部搜索研究员。请联网搜索并返回可导入 Solar DeepResearch 的 Markdown。不要写最终报告，只补证据。

## Survey Brief
{brief}

## Current Gap
- Output dir: `{gap.get("output_dir", "")}`
- Sources: `{gap.get("source_count", 0)}`
- Evidence: `{gap.get("evidence_count", 0)}/{gap.get("min_evidence", "N/A")}`
- Claims: `{gap.get("claim_count", 0)}/{gap.get("min_claims", "N/A")}`
- Required returned Source blocks: `{needed_results}` minimum
- Required source types: `{", ".join(gap.get("required_source_types") or [])}`
- Missing source types: `{", ".join(missing)}`
- Issues:
{issues}

## Query Plan

| Source Type | Min Results | Query |
|---|---:|---|
{query_plan}

## Required Research Angles

每个返回源必须填写 `Research Angles:`，并且整份 `returned_sources.md` 至少覆盖以下五类。一个 source 可以覆盖多类，用逗号分隔；不要只堆链接，必须说明它补的是谱系、方法、评估、争议还是工程缺口。

| Angle Key | Meaning | Query |
|---|---|---|
{angle_plan}

## How To Use

1. Copy the entire block under `Copy/Paste returned_sources.md Template`.
2. Ask Gemini/GPT/browser research to fill every `## Source N:` block with real sources.
3. Save the filled Markdown as `{gap.get('output_dir', '')}/returned_sources.md`.
4. Continue with:

```bash
solar-harness research survey-continue --output-dir "{gap.get('output_dir', '')}" --brief "{brief}" --returned-md "{gap.get('output_dir', '')}/returned_sources.md" --require-complete --json
```

## Rules
- Fill all {needed_results} `## Source N:` blocks. Each block should include at least two Key Claims and enough quote/summary detail to import as evidence.
- Every source must include `Research Angles:` using one or more keys: `{", ".join(RESEARCH_ANGLES)}`.
- Across the whole file, cover all five research angles at least once: literature lineage, method taxonomy, evaluation protocol, controversy/negative evidence, and engineering/deployment.
- Prefer primary/canonical sources: papers, official docs, GitHub repos, benchmarks, standards, model cards.
- Do not invent links, paper names, benchmark numbers, or quotes.
- Include contradiction/negative evidence when found.
- Keep summaries factual and citation-ready.
- Use Source Type values: `paper`, `official_doc`, `code`, `benchmark`, `dataset`, `standard`, `web`, `other`.

## Copy/Paste returned_sources.md Template

```markdown
{returned_template}
```
"""


def write_source_gap_handoff(
    output_dir: str | Path,
    *,
    brief: str = "",
    min_sources: int = 4,
    min_evidence: int = 8,
    min_claims: int = 8,
    required_source_types: list[str] | None = None,
    max_results: int = 12,
) -> dict[str, Any]:
    gap = assess_source_gap(
        output_dir,
        brief=brief,
        min_sources=min_sources,
        min_evidence=min_evidence,
        min_claims=min_claims,
        required_source_types=required_source_types,
    )
    path = Path(gap["handoff_path"]).expanduser()
    path.write_text(render_source_gap_handoff(gap, max_results=max_results), encoding="utf-8")
    gap["handoff_written"] = True
    (Path(output_dir).expanduser() / "survey_source_gap.json").write_text(json.dumps(gap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return gap
