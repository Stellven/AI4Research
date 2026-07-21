#!/usr/bin/env python3
"""Generate topic backlink indexes for isolated wiki reference batches.

This utility is intentionally conservative: it only creates/updates synthesis
index pages that link to existing notes. It does not rewrite source notes or
delete any content.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


VAULT = Path.home() / "Knowledge"
ROOTS = ("references", "concepts", "synthesis", "entities", "projects", "skills", "rules", "analysis")


def iter_docs(vault: Path) -> list[Path]:
    docs: list[Path] = []
    for root_name in ROOTS:
        root = vault / root_name
        if root.is_dir():
            docs.extend(p for p in root.rglob("*.md") if p.is_file())
    return sorted(docs)


def normalize_target(raw: str) -> str:
    target = raw.split("|", 1)[0].split("#", 1)[0].strip()
    if target.endswith(".md"):
        target = target[:-3]
    return target.lower()


def graph_state(vault: Path) -> dict[str, Any]:
    docs = iter_docs(vault)
    by_key: dict[str, str] = {}
    rels: list[str] = []
    for path in docs:
        rel = str(path.relative_to(vault)).replace("\\", "/")
        rels.append(rel)
        no_ext = rel[:-3].lower()
        by_key[no_ext] = rel
        by_key.setdefault(path.stem.lower(), rel)

    incoming: dict[str, set[str]] = {rel: set() for rel in rels}
    outgoing: dict[str, set[str]] = {rel: set() for rel in rels}
    link_re = re.compile(r"\[\[([^\]]+)\]\]")
    for path in docs:
        rel = str(path.relative_to(vault)).replace("\\", "/")
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in link_re.finditer(text):
            target = normalize_target(match.group(1))
            if not target:
                continue
            matched = by_key.get(target) or by_key.get(Path(target).stem.lower())
            if matched and matched != rel:
                outgoing[rel].add(matched)
                incoming[matched].add(rel)

    orphans = sorted(rel for rel in rels if not incoming.get(rel) and not outgoing.get(rel))
    return {"orphans": orphans, "incoming": incoming, "outgoing": outgoing, "doc_count": len(rels)}


def paper_topic(rel: str) -> str:
    stem = Path(rel).stem
    parts = stem.split("-", 2)
    return parts[1] if len(parts) >= 3 and parts[0] == "论文集合" else "其他"


def slugify(text: str) -> str:
    aliases = {
        "大模型高效架构": "llm-efficient-architecture",
        "reasoning": "reasoning",
        "未来计算架构": "future-computing-architecture",
        "高效训推": "efficient-training-inference",
        "多模态大模型": "multimodal-llm",
        "多模态与统一表征": "multimodal-unified-representation",
        "benchmarking": "benchmarking",
        "ai4science": "ai4science",
        "物理": "physical-ai",
        "数据底座": "data-foundation",
        "数据库": "database",
        "data": "data",
        "群体智能": "collective-intelligence",
        "agentic": "agentic",
        "gpu": "gpu",
        "how": "how-people-use-chatgpt",
        "生成式人工智能是资历偏见型技术变革": "generative-ai-seniority-biased-change",
    }
    if text in aliases:
        return aliases[text]
    normalized = unicodedata.normalize("NFKD", text)
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in normalized if ord(ch) < 128)
    out = re.sub(r"-+", "-", out).strip("-")
    return out or "other"


def render_index(topic: str, rels: list[str]) -> str:
    title = f"Paper Collection Index: {topic}"
    links = "\n".join(f"- [[{rel[:-3]}]]" for rel in sorted(rels, key=str.lower))
    return f"""---
title: "{title}"
category: synthesis
tags: [paper-collection, knowledge-graph, backlink-index, auto-generated]
source: solar-harness
created: 2026-05-12
updated: 2026-05-12
lifecycle: generated-index
---

# {title}

## Purpose

This generated index links historical batch-imported paper/reference notes back
into the Solar knowledge graph. It is a graph repair index, not a replacement
for deep synthesis.

## Notes

```text
topic: {topic}
count: {len(rels)}
repair_target: paper_collection_orphans
```

## Indexed References

{links}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate backlink indexes for paper collection orphans")
    parser.add_argument("--vault", default=str(VAULT))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    vault = Path(args.vault)
    state = graph_state(vault)
    paper_orphans = [rel for rel in state["orphans"] if rel.startswith("references/论文集合-")]
    clusters: dict[str, list[str]] = defaultdict(list)
    for rel in paper_orphans:
        clusters[paper_topic(rel)].append(rel)

    outputs = []
    out_dir = vault / "synthesis"
    for topic, rels in sorted(clusters.items(), key=lambda item: (-len(item[1]), item[0])):
        out_path = out_dir / f"paper-collection-index-{slugify(topic)}.md"
        outputs.append({"topic": topic, "count": len(rels), "path": str(out_path)})
        if args.apply:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(render_index(topic, rels), encoding="utf-8")

    result = {
        "apply": args.apply,
        "doc_count": state["doc_count"],
        "paper_orphan_count": len(paper_orphans),
        "index_count": len(outputs),
        "outputs": outputs,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"paper_orphan_count={len(paper_orphans)} index_count={len(outputs)} apply={args.apply}")
        for item in outputs:
            print(f"{item['count']:4d} {item['topic']} -> {item['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
