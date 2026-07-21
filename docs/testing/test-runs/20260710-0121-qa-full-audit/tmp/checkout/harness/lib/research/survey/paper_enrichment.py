"""Recursive paper enrichment and trend clustering for survey DeepResearch."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Callable

SearchFn = Callable[[str, int, str], tuple[list[dict[str, Any]], list[str]]]


THEME_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "agent_architecture",
        "Agent Architecture & Composition",
        ("agent", "multi-agent", "architecture", "composition", "context", "memory", "tool", "workflow", "blueprint"),
    ),
    (
        "evaluation_benchmarking",
        "Evaluation, Benchmarking & Cost",
        ("benchmark", "evaluation", "metric", "cost", "robust", "adversarial", "performance", "accuracy"),
    ),
    (
        "security_privacy",
        "Security, Privacy & Governance",
        ("security", "privacy", "attack", "incident", "governance", "safety", "adversarial", "risk"),
    ),
    (
        "optimization_efficiency",
        "Optimization & System Efficiency",
        ("optimization", "optimize", "latency", "throughput", "scheduling", "parallel", "efficiency", "resource"),
    ),
    (
        "workflow_operations",
        "Workflow Products & Operations",
        ("production", "workflow", "e-commerce", "pull request", "business", "operations", "deployment", "ticket"),
    ),
    (
        "deep_research",
        "Deep Research & Evidence Operations",
        ("deep research", "research agent", "retrieval", "evidence", "citation", "source", "reasoning tools"),
    ),
]


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _clean_text(value: Any, limit: int = 1200) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _title_from_blob(blob: str) -> str:
    text = _clean_text(blob, 500)
    if ". " in text:
        return text.split(". ", 1)[0].strip()
    return text[:160]


def _title_from_url(url: str) -> str:
    path = urlparse(str(url or "")).path.strip("/")
    if not path:
        return ""
    slug = path.split("/")[-1]
    slug = re.sub(r"[-_]+", " ", slug)
    slug = re.sub(r"\s+", " ", slug).strip()
    if not slug or len(slug.split()) < 3:
        return ""
    return slug.title()


def _seed_from_catalog_item(item: dict[str, Any]) -> dict[str, Any]:
    blob = _clean_text(item.get("title_blob") or item.get("title") or "")
    url = _clean_text(item.get("url") or "", 500)
    title = _clean_text(item.get("title") or _title_from_url(url) or _title_from_blob(blob), 220)
    return {
        "seed_id": _stable_id("seed", title or blob),
        "title": title,
        "url": url,
        "abstract": blob,
        "pillar": _clean_text(item.get("pillar") or "", 120),
        "source": "catalog",
    }


def _load_catalog_seeds(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, Any]] = []
    for key in ("papers", "demos", "items"):
        values = payload.get(key)
        if isinstance(values, list):
            rows.extend(_seed_from_catalog_item(item) for item in values if isinstance(item, dict))
    return rows


def _load_title_seeds(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    payload = None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    rows: list[dict[str, Any]] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                title = _clean_text(item.get("title") or item.get("name") or "", 220)
                abstract = _clean_text(item.get("abstract") or item.get("summary") or item.get("snippet") or "", 1200)
                if title:
                    rows.append({
                        "seed_id": _stable_id("seed", title),
                        "title": title,
                        "url": _clean_text(item.get("url") or "", 500),
                        "abstract": abstract,
                        "pillar": _clean_text(item.get("pillar") or "", 120),
                        "source": "input_titles_json",
                    })
            elif str(item).strip():
                title = _clean_text(item, 220)
                rows.append({"seed_id": _stable_id("seed", title), "title": title, "url": "", "abstract": "", "pillar": "", "source": "input_titles"})
    else:
        for line in text.splitlines():
            title = _clean_text(line, 220)
            if title and not title.startswith("#"):
                rows.append({"seed_id": _stable_id("seed", title), "title": title, "url": "", "abstract": "", "pillar": "", "source": "input_titles"})
    return rows


def _load_source_seeds(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in _read_jsonl(root / "sources.jsonl"):
        source_type = str(source.get("source_type") or "").lower()
        title = _clean_text(source.get("title") or "", 220)
        if source_type != "paper" or not title:
            continue
        rows.append({
            "seed_id": _stable_id("seed", title),
            "title": title,
            "url": _clean_text(source.get("url") or "", 500),
            "abstract": _clean_text(source.get("text") or source.get("snippet") or source.get("summary") or "", 1200),
            "pillar": "",
            "source": "sources_jsonl",
        })
    return rows


def load_paper_seeds(
    output_dir: str | Path,
    *,
    input_titles: str | Path = "",
    catalog_json: str | Path = "",
    max_papers: int = 40,
) -> list[dict[str, Any]]:
    root = Path(output_dir).expanduser()
    candidates: list[dict[str, Any]] = []
    if input_titles:
        candidates.extend(_load_title_seeds(Path(input_titles).expanduser()))
    catalog_path = Path(catalog_json).expanduser() if catalog_json else root / "cais2026_catalog.json"
    if catalog_path.exists():
        candidates.extend(_load_catalog_seeds(catalog_path))
    candidates.extend(_load_source_seeds(root))

    seen: set[str] = set()
    seeds: list[dict[str, Any]] = []
    for row in candidates:
        title = _clean_text(row.get("title") or "", 220)
        if not title:
            continue
        key = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        row = dict(row)
        row["title"] = title
        row["seed_id"] = row.get("seed_id") or _stable_id("seed", title)
        seeds.append(row)
        if len(seeds) >= max_papers:
            break
    return seeds


def _paper_from_seed(seed: dict[str, Any]) -> dict[str, Any]:
    title = _clean_text(seed.get("title"), 220)
    abstract = _clean_text(seed.get("abstract"), 1600)
    return {
        "paper_id": _stable_id("paper", title + "|" + _clean_text(seed.get("url"), 500)),
        "seed_title": title,
        "title": title,
        "url": _clean_text(seed.get("url"), 500),
        "abstract": abstract,
        "pillar": _clean_text(seed.get("pillar"), 120),
        "discovery_depth": 0,
        "queries": [],
        "source": seed.get("source") or "seed",
    }


def _merge_paper(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key in ("url", "abstract", "pillar"):
        if not merged.get(key) and update.get(key):
            merged[key] = update[key]
    if len(str(update.get("abstract") or "")) > len(str(merged.get("abstract") or "")):
        merged["abstract"] = update.get("abstract")
    merged["discovery_depth"] = min(int(merged.get("discovery_depth") or 0), int(update.get("discovery_depth") or 0))
    queries = list(merged.get("queries") or [])
    for query in update.get("queries") or []:
        if query not in queries:
            queries.append(query)
    merged["queries"] = queries
    return merged


def _hit_to_paper(seed: dict[str, Any], hit: dict[str, Any], *, query: str, depth: int) -> dict[str, Any]:
    title = _clean_text(hit.get("title") or seed.get("title") or "", 220)
    snippet = _clean_text(hit.get("snippet") or "", 1600)
    url = _clean_text(hit.get("url") or "", 500)
    return {
        "paper_id": _stable_id("paper", title + "|" + url),
        "seed_title": _clean_text(seed.get("title"), 220),
        "title": title,
        "url": url,
        "abstract": snippet,
        "pillar": _clean_text(seed.get("pillar"), 120),
        "discovery_depth": depth,
        "queries": [query],
        "source": _clean_text(hit.get("connector") or hit.get("source") or "search", 80),
    }


def _queries_for_seed(seed: dict[str, Any], depth: int) -> list[str]:
    title = _clean_text(seed.get("title"), 220)
    if not title:
        return []
    if depth <= 0:
        return [f'"{title}" paper abstract']
    return [
        f'"{title}" method evaluation benchmark',
        f'"{title}" related work agent system',
    ]


def enrich_papers(
    output_dir: str | Path,
    *,
    input_titles: str | Path = "",
    catalog_json: str | Path = "",
    provider: str = "auto",
    max_papers: int = 40,
    max_results: int = 3,
    recursion_depth: int = 1,
    allow_search: bool = False,
    search_fn: SearchFn | None = None,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    seeds = load_paper_seeds(root, input_titles=input_titles, catalog_json=catalog_json, max_papers=max_papers)
    by_id: dict[str, dict[str, Any]] = {}
    search_errors: list[str] = []

    for seed in seeds:
        paper = _paper_from_seed(seed)
        by_id[paper["paper_id"]] = _merge_paper(by_id.get(paper["paper_id"], paper), paper)
        if not allow_search or search_fn is None:
            continue
        for depth in range(max(1, recursion_depth)):
            for query in _queries_for_seed(seed, depth):
                hits, errors = search_fn(query, max_results, provider)
                search_errors.extend(errors)
                for hit in hits[:max_results]:
                    discovered = _hit_to_paper(seed, hit, query=query, depth=depth + 1)
                    by_id[discovered["paper_id"]] = _merge_paper(by_id.get(discovered["paper_id"], discovered), discovered)

    papers = sorted(by_id.values(), key=lambda row: (int(row.get("discovery_depth") or 0), str(row.get("title") or "")))
    clusters = cluster_papers(papers)
    trends = synthesize_trends(clusters)
    payload = {
        "ok": bool(papers),
        "seed_count": len(seeds),
        "paper_count": len(papers),
        "allow_search": allow_search,
        "provider": provider,
        "recursion_depth": recursion_depth,
        "max_results": max_results,
        "papers": papers,
        "clusters": clusters,
        "trends": trends,
        "search_errors": search_errors[:50],
        "files": {
            "papers": str(root / "paper_enrichment.json"),
            "clusters": str(root / "paper_theme_clusters.json"),
            "trends_md": str(root / "paper_trend_synthesis.md"),
        },
    }
    (root / "paper_enrichment.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "paper_theme_clusters.json").write_text(json.dumps({"ok": bool(clusters), "clusters": clusters, "trends": trends}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "paper_trend_synthesis.md").write_text(render_trend_markdown(payload), encoding="utf-8")
    return payload


def _themes_for_paper(paper: dict[str, Any]) -> list[str]:
    text = " ".join(str(paper.get(key) or "") for key in ("title", "abstract", "pillar")).lower()
    themes: list[str] = []
    for theme_id, _label, keywords in THEME_RULES:
        if any(keyword in text for keyword in keywords):
            themes.append(theme_id)
    return themes or ["agent_architecture"]


def cluster_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters_by_id: dict[str, dict[str, Any]] = {
        theme_id: {"theme_id": theme_id, "label": label, "paper_ids": [], "paper_titles": [], "evidence_count": 0, "keywords": list(keywords)}
        for theme_id, label, keywords in THEME_RULES
    }
    for paper in papers:
        themes = _themes_for_paper(paper)
        paper["themes"] = themes
        for theme_id in themes:
            cluster = clusters_by_id.setdefault(theme_id, {"theme_id": theme_id, "label": theme_id, "paper_ids": [], "paper_titles": [], "evidence_count": 0, "keywords": []})
            cluster["paper_ids"].append(paper["paper_id"])
            cluster["paper_titles"].append(paper["title"])
            cluster["evidence_count"] += 1
    return [
        cluster
        for cluster in sorted(clusters_by_id.values(), key=lambda row: (-int(row.get("evidence_count") or 0), str(row.get("label") or "")))
        if int(cluster.get("evidence_count") or 0) > 0
    ]


def synthesize_trends(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trend_templates = {
        "agent_architecture": "Agent 系统设计正在从 prompt wrapper 转向可组合、可描述、可演化的 compound architecture。",
        "evaluation_benchmarking": "评测正在从单一正确率扩展为质量、成本、鲁棒性和部署外推的多目标判断。",
        "security_privacy": "安全与隐私不再是附加项，而是在检索、工具调用、记忆和权限边界上反向塑造 runtime。",
        "optimization_efficiency": "效率优化正在从模型选择转向任务调度、并发环境、上下文压缩和系统吞吐。",
        "workflow_operations": "Agent demo 的价值重心从会话交互转向可运营 workflow product。",
        "deep_research": "Deep Research 的核心能力正在从搜索聚合转向证据运营、引用审计和结构化推理。",
    }
    trends: list[dict[str, Any]] = []
    for cluster in clusters:
        theme_id = str(cluster.get("theme_id") or "")
        titles = list(cluster.get("paper_titles") or [])[:5]
        trends.append({
            "trend_id": _stable_id("trend", theme_id),
            "theme_id": theme_id,
            "label": cluster.get("label") or theme_id,
            "claim": trend_templates.get(theme_id, f"{cluster.get('label') or theme_id} 是一个高频主题，需要进一步证据核查。"),
            "evidence_count": int(cluster.get("evidence_count") or 0),
            "representative_titles": titles,
            "confidence": "high" if int(cluster.get("evidence_count") or 0) >= 5 else "medium",
        })
    return trends


def render_trend_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Paper Enrichment Trend Synthesis",
        "",
        f"- Seed papers: {payload.get('seed_count', 0)}",
        f"- Enriched papers: {payload.get('paper_count', 0)}",
        f"- Recursive search: {'enabled' if payload.get('allow_search') else 'disabled'}",
        f"- Provider: {payload.get('provider')}",
        "",
        "## Trends",
        "",
    ]
    for trend in payload.get("trends") or []:
        lines.extend([
            f"### {trend.get('label')}",
            "",
            str(trend.get("claim") or ""),
            "",
            f"- Evidence count: {trend.get('evidence_count')}",
            f"- Confidence: {trend.get('confidence')}",
            "- Representative papers:",
        ])
        for title in trend.get("representative_titles") or []:
            lines.append(f"  - {title}")
        lines.append("")
    if payload.get("search_errors"):
        lines.extend(["## Search Warnings", ""])
        for error in payload.get("search_errors") or []:
            lines.append(f"- {error}")
    return "\n".join(lines).rstrip() + "\n"


def load_matching_paper_trends(output_dir: str | Path, section: dict[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    root = Path(output_dir).expanduser()
    payload = _read_json(root / "paper_theme_clusters.json")
    if not isinstance(payload, dict):
        return []
    trends = payload.get("trends")
    if not isinstance(trends, list):
        return []
    section_text = " ".join(str(section.get(key) or "") for key in ("section_id", "title", "research_question", "objective")).lower()
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for idx, trend in enumerate(trends):
        hay = " ".join([str(trend.get("label") or ""), str(trend.get("claim") or ""), " ".join(trend.get("representative_titles") or [])]).lower()
        score = len(set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", section_text)) & set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", hay)))
        scored.append((-score, idx, trend))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [trend for _score, _idx, trend in scored[:limit]]
