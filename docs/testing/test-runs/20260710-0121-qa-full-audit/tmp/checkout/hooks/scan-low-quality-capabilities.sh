#!/bin/bash
# ── scan-low-quality-capabilities.sh ──
# Sprint sprint-20260418-065438, D1: 低分能力扫描
#
# 读 capability-graph.jsonl, 按 capability_id 取最新,
# 过滤 quality_score < threshold AND used_count >= min_used
# 输出 JSON 数组到 low-quality-capabilities.json
#
# 用法: scan-low-quality-capabilities.sh

set -uo pipefail

HARNESS_DIR="$HOME/.solar/harness"
GRAPH_FILE="$HARNESS_DIR/capability-graph.jsonl"
OUTPUT_FILE="$HARNESS_DIR/low-quality-capabilities.json"
CONFIG_FILE="$HARNESS_DIR/auto-boost-config.json"

# 读配置 (无则用默认)
THRESHOLD=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('quality_threshold',0.5))" 2>/dev/null || echo "0.5")
MIN_USED=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('min_used_count',3))" 2>/dev/null || echo "3")

[[ -f "$GRAPH_FILE" ]] || { echo "[]"; echo "[]" > "$OUTPUT_FILE"; exit 0; }

python3 << PYEOF
import json

graph_file = "$GRAPH_FILE"
output_file = "$OUTPUT_FILE"
threshold = float("$THRESHOLD")
min_used = int("$MIN_USED")

# 按 capability_id 取最新
latest = {}
with open(graph_file) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            d = json.loads(line)
            cid = d.get("capability_id", "")
            if cid:
                latest[cid] = d
        except:
            pass

# 过滤低分
low = []
for cid, d in latest.items():
    qs = d.get("quality_score", 1.0)
    uc = d.get("used_count", 0)
    name = d.get("name", cid)
    cat = d.get("category", "")
    if qs < threshold and uc >= min_used:
        low.append({
            "capability_id": cid,
            "name": name,
            "category": cat,
            "quality_score": qs,
            "used_count": uc,
            "target_score": 0.7
        })

# 按 quality_score 升序 (最低分优先)
low.sort(key=lambda x: x["quality_score"])

with open(output_file, "w") as f:
    json.dump(low, f, indent=2, ensure_ascii=False)

print(f"[scan] {len(low)} 项低分能力 (< {threshold} & >= {min_used} 次)")
for item in low:
    print(f"  {item['name']}: {item['quality_score']:.2f} (used {item['used_count']})")
PYEOF

exit 0
