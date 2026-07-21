#!/bin/bash
# ── capability-scorer.sh ──
# Sprint sprint-20260417-213604, D2: 能力自动评分
#
# 功能: 读 eval.md 的"能力覆盖清单"段, 更新 capability-graph.jsonl
# 调用方: self-evolve-postmortem.sh (Sprint passed 时)
#
# 用法: capability-scorer.sh <sprint_id>

set -uo pipefail

SID="${1:?用法: $0 <sprint_id>}"
HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
GRAPH_FILE="$HARNESS_DIR/capability-graph.jsonl"
EVAL_FILE="$SPRINTS_DIR/${SID}.eval.md"
NEEDS_IMP_FILE="$HARNESS_DIR/needs-improvement.md"

# 文件不存在则跳过
[[ -f "$EVAL_FILE" ]] || { echo "[scorer] eval.md 不存在: $EVAL_FILE" >&2; exit 0; }
[[ -f "$GRAPH_FILE" ]] || { echo "[scorer] capability-graph.jsonl 不存在" >&2; exit 0; }

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UPDATED=0

# 从 eval.md 提取能力覆盖段
# 支持格式: "✅ 能力名" / "⚠️ 能力名" / "❌ 能力名"
# 也支持: "| 能力名 | ✅ |"
extract_capabilities() {
  local in_section=false
  while IFS= read -r line; do
    # 检测能力覆盖段落标题
    if echo "$line" | grep -qiE '能力覆盖|capability.*cover|能力清单'; then
      in_section=true
      continue
    fi
    # 遇到下一个 ## 标题则退出
    if [[ "$in_section" == true ]] && [[ "$line" =~ ^##\  ]]; then
      break
    fi
    if [[ "$in_section" == true ]]; then
      # 提取 ✅/⚠️/❌ 后的能力名
      local cap status
      if echo "$line" | grep -q '✅'; then
        status="good"
        cap=$(echo "$line" | sed 's/.*✅[[:space:]]*//' | sed 's/[[:space:]]*—.*//' | sed 's/[[:space:]]*|.*//' | xargs)
      elif echo "$line" | grep -q '⚠️'; then
        status="partial"
        cap=$(echo "$line" | sed 's/.*⚠️[[:space:]]*//' | sed 's/[[:space:]]*—.*//' | sed 's/[[:space:]]*|.*//' | xargs)
      elif echo "$line" | grep -q '❌'; then
        status="bad"
        cap=$(echo "$line" | sed 's/.*❌[[:space:]]*//' | sed 's/[[:space:]]*—.*//' | sed 's/[[:space:]]*|.*//' | xargs)
      else
        continue
      fi
      [[ -n "$cap" ]] && echo "${status}|${cap}"
    fi
done < "$EVAL_FILE"
}

# 读取能力图谱最新状态 (按 capability_id 去重取最新)
get_latest() {
  local cap_id="$1"
  # 从末尾往前找第一个匹配的 capability_id
  tac "$GRAPH_FILE" 2>/dev/null | python3 -c "
import sys, json
target = '$cap_id'
for line in sys.stdin:
    try:
        d = json.loads(line.strip())
        if d.get('capability_id') == target:
            print(json.dumps(d))
            break
    except: pass
" 2>/dev/null
}

# 更新能力图谱
while IFS='|' read -r status cap_name; do
  [[ -z "$cap_name" ]] && continue
  # 尝试模糊匹配 capability_id
  local cap_id
  cap_id=$(grep -i "$cap_name" "$GRAPH_FILE" 2>/dev/null | tail -1 | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line.strip())
        print(d.get('capability_id',''))
        break
    except: pass
" 2>/dev/null || echo "")

  if [[ -z "$cap_id" ]]; then
    # 未找到匹配, 跳过
    continue
  fi

  # 获取最新状态
  local latest
  latest=$(get_latest "$cap_id")

  local old_score=0.5 old_used=0 old_right=0
  if [[ -n "$latest" ]]; then
    old_score=$(echo "$latest" | python3 -c "import sys,json; print(json.load(sys.stdin).get('quality_score',0.5))" 2>/dev/null || echo 0.5)
    old_used=$(echo "$latest" | python3 -c "import sys,json; print(json.load(sys.stdin).get('used_count',0))" 2>/dev/null || echo 0)
    old_right=$(echo "$latest" | python3 -c "import sys,json; print(json.load(sys.stdin).get('right_use_rate',0))" 2>/dev/null || echo 0)
  fi

  # 计算新分数
  local new_score
  case "$status" in
    good)   new_score=1.0 ;;
    partial) new_score=0.5 ;;
    bad)    new_score=0.0 ;;
    *)      new_score=0.5 ;;
  esac

  # 加权移动平均: 80% old + 20% new
  local updated_score
  updated_score=$(python3 -c "print(round(0.8*$old_score + 0.2*$new_score, 3))" 2>/dev/null || echo $old_score)

  local new_used=$((old_used + 1))
  local new_right
  new_right=$(python3 -c "print(round(($old_right*$old_used + (1 if '$status'=='good' else 0))/$new_used, 3))" 2>/dev/null || echo $old_right)

  # 获取 name 和 category (从图谱)
  local name category
  name=$(echo "$latest" | python3 -c "import sys,json; print(json.load(sys.stdin).get('name',''))" 2>/dev/null)
  category=$(echo "$latest" | python3 -c "import sys,json; print(json.load(sys.stdin).get('category','Z_Unknown'))" 2>/dev/null)

  # 追加新行
  printf '{"capability_id":"%s","name":"%s","category":"%s","last_used_at":"%s","used_count":%d,"quality_score":%.3f,"right_use_rate":%.3f}\n' \
    "$cap_id" "$name" "$category" "$TS" "$new_used" "$updated_score" "$new_right" >> "$GRAPH_FILE"

  ((UPDATED++))
done < <(extract_capabilities)

echo "[scorer] 更新 ${UPDATED} 项能力评分" >&2

# ── D5: 刷新 needs-improvement.md ──
python3 << 'PYEOF' 2>/dev/null
import json, sys
graph_file = "$GRAPH_FILE"
imp_file = "$NEEDS_IMP_FILE"

# 读取每项能力最新状态
latest = {}
try:
    for line in open(graph_file):
        d = json.loads(line.strip())
        cid = d.get("capability_id","")
        latest[cid] = d
except: pass

# 筛选低分能力
low_score = []
for cid, d in latest.items():
    qs = d.get("quality_score", 1.0)
    uc = d.get("used_count", 0)
    if qs < 0.5 and uc >= 3:
        low_score.append((cid, d.get("name",""), qs, uc))

with open(imp_file, "w") as f:
    f.write("# Needs Improvement — 能力低分告警\n")
    f.write("# Auto-generated by capability-scorer.sh\n\n")
    if not low_score:
        f.write("无低分能力 (所有 quality_score >= 0.5 或 used_count < 3)\n")
    else:
        f.write("| Capability | Name | Quality Score | Used Count |\n")
        f.write("|------------|------|---------------|------------|\n")
        for cid, name, qs, uc in sorted(low_score, key=lambda x: x[2]):
            f.write(f"| {cid} | {name} | {qs:.3f} | {uc} |\n")
PYEOF

echo "[scorer] needs-improvement.md 已刷新" >&2
exit 0
