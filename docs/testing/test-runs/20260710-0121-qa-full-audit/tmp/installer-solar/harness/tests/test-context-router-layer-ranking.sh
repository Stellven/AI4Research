#!/usr/bin/env bash
# Regression: compiled KB layers outrank raw evidence in default context routers.
set -euo pipefail

HARNESS="${HARNESS_DIR:-$HOME/.solar/harness}"

python3 - <<'PY'
import importlib.util
import sys
from pathlib import Path

harness = Path.home() / ".solar" / "harness"
sys.path.insert(0, str(harness / "lib"))

def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

unified = load("solar_unified_context", harness / "lib" / "solar-unified-context.py")
kb = load("solar_knowledge_context", harness / "lib" / "solar-knowledge-context.py")
mirage = load("mirage_search", harness / "lib" / "mirage_search.py")

unified_hits = [
    {"source": "qmd", "path": "qmd://solar-wiki/raw/a.md", "title": "raw", "score": 999},
    {"source": "solar_db", "path": "obsidian:~/Knowledge/references/a.md", "title": "ref", "score": 0.1},
    {"source": "qmd", "path": "qmd://solar-wiki/concepts/a.md", "title": "concept", "score": 0.2},
    {"source": "qmd", "path": "qmd://solar-wiki/synthesis/a.md", "title": "synthesis", "score": 0.3},
]
ordered = unified._sort_context_hits(unified_hits)
assert [h["layer"] for h in ordered] == ["synthesis", "concepts", "references", "raw-evidence"], ordered

unified_topic_hits = [
    {"source": "qmd", "path": "qmd://solar-wiki/references/solar-harness-pm-1210-context-inject-fix-20260512.md", "title": "fix", "snippet": "太空数据中心 context inject", "score": 0.99},
    {"source": "qmd", "path": "qmd://solar-wiki/references/太空数据中心散热方案.md", "title": "太空数据中心散热方案", "snippet": "太空数据中心散热", "score": 0.90},
    {"source": "solar_db", "path": "~/Knowledge/references/太空数据中心散热方案.md", "title": "太空数据中心散热方案", "snippet": "太空数据中心散热", "score": 0.80},
]
ordered_topic = unified._sort_context_hits(unified_topic_hits, "太空数据中心 space data center orbital data center")
assert ordered_topic[0]["title"] == "太空数据中心散热方案", ordered_topic
filtered_topic = unified._filter_runtime_noise(ordered_topic, "太空数据中心 space data center orbital data center")
assert all("1210" not in h["path"] for h in filtered_topic), filtered_topic

kb_hits = [
    {"path": "qmd://solar-wiki/raw/a.md", "id": "raw", "title": "raw", "snippet": "", "score": 999},
    {"path": "~/Knowledge/references/a.md", "id": "ref", "title": "ref", "snippet": "", "score": 0.1},
    {"path": "~/Knowledge/concepts/a.md", "id": "concept", "title": "concept", "snippet": "", "score": 0.2},
    {"path": "~/Knowledge/synthesis/a.md", "id": "synthesis", "title": "synthesis", "snippet": "", "score": 0.3},
]
ordered = kb._rank_hits(kb_hits, "a")
assert [h["layer"] for h in ordered] == ["synthesis", "concepts", "references", "raw-evidence"], ordered

mirage_hits = [
    {"source_type": "qmd", "path": "qmd://solar-wiki/raw/a.md", "score_or_rank": 999},
    {"source_type": "solar_db", "path": "~/Knowledge/references/a.md", "score_or_rank": 0.1},
]
assert mirage._layer_priority(mirage_hits[1]) < mirage._layer_priority(mirage_hits[0])

variants = mirage._query_variants("太空数据中心 space data center orbital data center")
assert "太空数据中心" in variants, variants

mixed_hits = [
    {"source_type": "qmd", "path": "qmd://solar-wiki/concepts/solar-harness-symphony-backend.md", "snippet": "data center"},
    {"source_type": "qmd", "path": "qmd://solar-wiki/concepts/orbital-data-center.md", "snippet": "轨道数据中心和太空数据中心"},
]
ordered_mixed = sorted(
    mixed_hits,
    key=lambda h: (
        mirage._layer_priority(h),
        -mirage._topic_relevance(h, "太空数据中心 space data center orbital data center"),
    ),
)
assert "orbital-data-center" in ordered_mixed[0]["path"], ordered_mixed

print("PASS context router layer ranking")
PY

live_json="$("$HARNESS/solar-harness.sh" context inject \
  --query "Solar-Harness Skills Readiness Certify" \
  --json --max-hits 8 --max-chars 5000)"

LIVE_JSON="$live_json" python3 - <<'PY'
import json, os
d = json.loads(os.environ["LIVE_JSON"])
hits = d.get("hits") or []
layers = [h.get("layer") for h in hits]
assert "references" in layers, layers
assert "raw-evidence" in layers, layers
assert layers.index("references") < layers.index("raw-evidence"), layers
print("PASS live context references before raw")
PY
