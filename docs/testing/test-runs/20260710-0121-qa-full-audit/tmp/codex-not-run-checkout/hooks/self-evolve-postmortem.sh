#!/bin/bash
# ── self-evolve-postmortem.sh ──
# Sprint sprint-20260417-213604, D3: 自进化钩子 (扩展版)
#
# 功能:
#   (a) 提取改进建议 → pending-improvements.jsonl
#   (b) 提取失败原因 → lessons.jsonl (去重)
#   (c) 调用 capability-scorer.sh 更新能力图谱
#   (d) 更新 kpi.json
# 调用方: coordinator.sh 的 handle_passed / handle_failed_review
#
# 用法: self-evolve-postmortem.sh <sprint_id>

set -uo pipefail

SID="${1:?用法: $0 <sprint_id>}"
HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
EVAL_FILE="$SPRINTS_DIR/${SID}.eval.md"
IMPROVEMENTS_FILE="$HARNESS_DIR/pending-improvements.jsonl"
LESSONS_FILE="$HARNESS_DIR/brain/lessons.jsonl"
KPI_FILE="$HARNESS_DIR/kpi.json"
COORD_LOG="$HARNESS_DIR/.coordinator.log"

# eval.md 不存在则跳过
[[ -f "$EVAL_FILE" ]] || { echo "[postmortem] eval.md 不存在: $EVAL_FILE" >&2; exit 0; }

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

log() { echo "[postmortem] $*" >&2; }

# ── (a) 提取改进建议 → pending-improvements.jsonl ──

touch "$IMPROVEMENTS_FILE"

extract_suggestions() {
  local in_section=false
  while IFS= read -r line; do
    if echo "$line" | grep -qiE '^##\ (改进建议|Suggestions|Next\ Steps|Recommendations)'; then
      in_section=true; continue
    fi
    if [[ "$in_section" == true ]] && [[ "$line" =~ ^##\  ]]; then break; fi
    if [[ "$in_section" == true ]] && [[ -n "$line" ]] && [[ ! "$line" =~ ^[[:space:]]*$ ]]; then
      local cleaned
      cleaned=$(echo "$line" | sed 's/^[-*]\s*//' | sed 's/^[0-9]\+\.\s*//' | xargs)
      [[ -n "$cleaned" ]] && echo "$cleaned"
    fi
  done < "$EVAL_FILE"
}

SUGGEST_COUNT=0
while IFS= read -r suggestion; do
  [[ -z "$suggestion" ]] && continue
  local priority="low"
  if echo "$suggestion" | grep -qiE '高|important|critical|urgent|must'; then
    priority="high"
  elif echo "$suggestion" | grep -qiE '中|moderate|should'; then
    priority="medium"
  fi
  local escaped
  escaped=$(echo "$suggestion" | sed 's/"/\\"/g' | tr '\n' ' ')
  printf '{"sprint_id":"%s","suggestion":"%s","priority":"%s","created_at":"%s"}\n' \
    "$SID" "$escaped" "$priority" "$TS" >> "$IMPROVEMENTS_FILE"
  ((SUGGEST_COUNT++))
done < <(extract_suggestions)

log "改进建议: ${SUGGEST_COUNT} 条"

# ── (b) 提取失败原因 → lessons.jsonl (去重) ──

touch "$LESSONS_FILE"

extract_failures() {
  local in_section=false
  while IFS= read -r line; do
    if echo "$line" | grep -qiE '^##\ (失败|FAIL|Errors|失败原因|问题)'; then
      in_section=true; continue
    fi
    if [[ "$in_section" == true ]] && [[ "$line" =~ ^##\  ]]; then break; fi
    if [[ "$in_section" == true ]] && echo "$line" | grep -qE '^\s*[-*]\s' ; then
      local cleaned
      cleaned=$(echo "$line" | sed 's/^[-*]\s*//' | sed 's/^[0-9]\+\.\s*//' | xargs)
      [[ -n "$cleaned" ]] && echo "$cleaned"
    fi
  done < "$EVAL_FILE"
}

LESSON_COUNT=0
while IFS= read -r lesson_text; do
  [[ -z "$lesson_text" ]] && continue
  # 去重: 检查 lessons.jsonl 中是否已有相似内容
  local short_text
  short_text=$(echo "$lesson_text" | cut -c1-40)
  if grep -q "$short_text" "$LESSONS_FILE" 2>/dev/null; then
    continue  # 已存在, 跳过
  fi
  local escaped_lesson
  escaped_lesson=$(echo "$lesson_text" | sed 's/"/\\"/g' | tr '\n' ' ')
  printf '{"ts":"%s","sprint_id":"%s","lesson":"%s","source":"postmortem","confidence":0.8,"tags":["postmortem","auto"]}\n' \
    "$TS" "$SID" "$escaped_lesson" >> "$LESSONS_FILE"
  ((LESSON_COUNT++))
done < <(extract_failures)

log "失败教训: ${LESSON_COUNT} 条 (去重后)"

# ── (c) 调用 capability-scorer.sh ──

if [[ -x "$HOME/.claude/hooks/capability-scorer.sh" ]]; then
  bash "$HOME/.claude/hooks/capability-scorer.sh" "$SID" 2>&1 | while read -r line; do log "$line"; done
else
  log "capability-scorer.sh 不存在或不可执行, 跳过评分"
fi

# ── (d) 更新 kpi.json ──

if [[ -x "$HOME/.solar/harness/update-kpi.sh" ]] || true; then
  python3 << 'PYEOF' 2>/dev/null || true
import json, os, glob, datetime

kpi_file = os.path.expanduser("$KPI_FILE")
sprints_dir = os.path.expanduser("$SPRINTS_DIR")

# 统计 Sprint 数据
files = glob.glob(os.path.join(sprints_dir, "sprint-*.status.json"))
total = 0
passed = 0
rounds_sum = 0
rounds_count = 0

for f in files:
    try:
        d = json.load(open(f))
        st = d.get("status", "")
        if st in ("drafting", "cancelled", "superseded"): continue
        total += 1
        if st in ("passed", "eval_pass"):
            passed += 1
            r = d.get("round", 1)
            rounds_sum += r
            rounds_count += 1
    except: pass

pass_rate = round(passed / total, 3) if total > 0 else 0
avg_rounds = round(rounds_sum / rounds_count, 2) if rounds_count > 0 else 0

# 能力图谱平均分
graph_file = os.path.join(os.path.dirname(kpi_file), "capability-graph.jsonl")
latest_caps = {}
try:
    for line in open(graph_file):
        d = json.loads(line.strip())
        cid = d.get("capability_id","")
        latest_caps[cid] = d.get("quality_score", 0.5)
except: pass
avg_quality = round(sum(latest_caps.values()) / len(latest_caps), 3) if latest_caps else 0.5

# 读取旧 KPI
old_kpi = {}
if os.path.exists(kpi_file):
    try: old_kpi = json.load(open(kpi_file))
    except: pass

kpi = {
    "sprints_total": total,
    "sprints_passed": passed,
    "pass_rate": pass_rate,
    "median_activation_seconds": old_kpi.get("median_activation_seconds"),
    "avg_rounds": avg_rounds,
    "avg_quality_score": avg_quality,
    "user_interventions_per_sprint": old_kpi.get("user_interventions_per_sprint"),
    "updated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "history": old_kpi.get("history", [])
}

# 追加历史记录 (最多保留最近 50 条)
kpi["history"].append({
    "ts": kpi["updated_at"],
    "sprint_id": "$SID",
    "pass_rate": pass_rate,
    "avg_rounds": avg_rounds,
    "avg_quality": avg_quality
})
kpi["history"] = kpi["history"][-50:]

json.dump(kpi, open(kpi_file, "w"), indent=2)
PYEOF
  log "kpi.json 已更新"
fi

log "完成: 建议=${SUGGEST_COUNT} 教训=${LESSON_COUNT}"
exit 0
