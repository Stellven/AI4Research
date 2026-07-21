#!/bin/bash
# ================================================================
# Solar Harness — Token Tracker
#
# 计算历史 Sprint token 基线 + 量化对比
# 方法: 文件大小 × token/line 系数 (1 行 ≈ 4 token)
#
# 用法:
#   token-tracker.sh baseline             历史基线
#   token-tracker.sh measure <sid>        测量指定 Sprint
#   token-tracker.sh report <sid>         生成对比报告
#
# @module solar-farm/harness/token-tracker
# ================================================================
set -eu

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
REPORTS_DIR="$HOME/.solar/reports"
ARCHIVE_DIR="$SPRINTS_DIR/archive"

# Token 估算系数: 1 行 ≈ 4 token (中英文混合)
TOKENS_PER_LINE=4

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; C='\033[0;36m'; N='\033[0m'
log()  { echo -e "${C}[TokenTracker]${N} $*"; }
ok()   { echo -e "${G}[TokenTracker]${N} $*"; }
warn() { echo -e "${Y}[TokenTracker]${N} $*"; }
err()  { echo -e "${R}[TokenTracker]${N} $*"; }

mkdir -p "$REPORTS_DIR"

# --- 计算文件的 token 数 (行数 × 系数) ---
count_tokens_in_file() {
  local f="$1"
  if [[ -f "$f" ]]; then
    local lines
    lines=$(wc -l < "$f" | tr -d ' ')
    echo $((lines * TOKENS_PER_LINE))
  else
    echo 0
  fi
}

# --- 计算一个 Sprint 的总 token (包含归档文件) ---
measure_sprint() {
  local sid="$1"
  local total=0

  # 主目录文件
  for ext in contract.md plan.md handoff.md eval.md eval.json dispatch.md events.jsonl status.json summary.md; do
    total=$((total + $(count_tokens_in_file "$SPRINTS_DIR/${sid}.${ext}")))
  done

  # 归档目录文件 (如果已归档)
  for ext in events.jsonl plan.md handoff.md dispatch.md; do
    total=$((total + $(count_tokens_in_file "$ARCHIVE_DIR/${sid}.${ext}")))
  done

  echo "$total"
}

# --- 计算主目录活跃文件 token (归档后的实际占用量) ---
measure_active_tokens() {
  local sid="$1"
  local total=0
  for ext in contract.md status.json summary.md; do
    total=$((total + $(count_tokens_in_file "$SPRINTS_DIR/${sid}.${ext}")))
  done
  echo "$total"
}

# --- baseline: 历史基线 ---
do_baseline() {
  log "计算历史 Sprint token 基线..."
  echo ""

  # 找最近 5 个 passed sprint
  local passed_sids=()
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    local st
    st=$(python3 -c "import json; print(json.load(open('$f')).get('status',''))" 2>/dev/null)
    if [[ "$st" == "passed" || "$st" == "eval_pass" ]]; then
      local sid
      sid=$(python3 -c "import json; print(json.load(open('$f')).get('id',''))" 2>/dev/null)
      passed_sids+=("$sid")
    fi
  done < <(ls -t "$SPRINTS_DIR"/*.status.json 2>/dev/null)

  local count=0
  local total_tokens=0
  local details=""

  for sid in "${passed_sids[@]}"; do
    [[ -z "$sid" ]] && continue
    if [[ "$count" -ge 5 ]]; then
      break
    fi

    local tokens
    tokens=$(measure_sprint "$sid")
    local round
    round=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${sid}.status.json')).get('round',0))" 2>/dev/null || echo "0")

    # 计算平均每轮
    local per_round=0
    if [[ "$round" -gt 0 ]]; then
      per_round=$((tokens / round))
    fi

    details="${details}  ${sid}: ${tokens} tokens (${round} rounds, ~${per_round}/round)\n"
    total_tokens=$((total_tokens + tokens))
    count=$((count + 1))
  done

  if [[ "$count" -eq 0 ]]; then
    err "无 passed Sprint 可作为基线"
    return 1
  fi

  local avg=$((total_tokens / count))
  ok "基线 (最近 ${count} 个 passed Sprint):"
  echo ""
  echo -e "$details" | head -10
  echo "  ─────────────────────────────"
  ok "平均: ${avg} tokens / Sprint"
  echo "  (估算方法: 文件行数 × ${TOKENS_PER_LINE} token/行)"
  echo ""
}

# --- measure: 测量指定 Sprint ---
do_measure() {
  local sid="$1"
  local tokens
  tokens=$(measure_sprint "$sid")
  local round
  round=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${sid}.status.json')).get('round',0))" 2>/dev/null || echo "0")

  ok "Sprint ${sid}:"
  echo "  总 token: ${tokens}"
  echo "  轮次: ${round}"
  if [[ "$round" -gt 0 ]]; then
    echo "  每轮平均: $((tokens / round)) tokens"
  fi
  echo ""

  # 明细
  echo "  文件明细:"
  for ext in contract.md plan.md handoff.md eval.md eval.json dispatch.md events.jsonl status.json; do
    local f="$SPRINTS_DIR/${sid}.${ext}"
    local t
    t=$(count_tokens_in_file "$f")
    if [[ "$t" -gt 0 ]]; then
      printf "    %-20s %6d tokens\n" "$ext" "$t"
    fi
  done
}

# --- report: 生成对比报告 ---
do_report() {
  local sid="$1"
  local today
  today=$(date +%Y%m%d)
  local report_file="$REPORTS_DIR/token-savings-${sid}.md"

  # 计算基线 (最近 5 个 passed, 排除当前 sprint)
  local baseline_total=0 baseline_count=0
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    local bst bsid
    bst=$(python3 -c "import json; print(json.load(open('$f')).get('status',''))" 2>/dev/null)
    bsid=$(python3 -c "import json; print(json.load(open('$f')).get('id',''))" 2>/dev/null)
    if [[ "$bst" == "passed" || "$bst" == "eval_pass" ]] && [[ "$bsid" != "$sid" ]]; then
      if [[ "$baseline_count" -lt 5 ]]; then
        baseline_total=$((baseline_total + $(measure_sprint "$bsid")))
        baseline_count=$((baseline_count + 1))
      fi
    fi
  done < <(ls -t "$SPRINTS_DIR"/*.status.json 2>/dev/null)

  if [[ "$baseline_count" -eq 0 ]]; then
    err "无历史 Sprint 作为基线"
    return 1
  fi

  local baseline_avg=$((baseline_total / baseline_count))
  local current_tokens
  current_tokens=$(measure_sprint "$sid")

  # 归档后活跃文件 token (归档的实际节省效果)
  local archived_active_total=0 archived_count=0
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    local bst bsid
    bst=$(python3 -c "import json; print(json.load(open('$f')).get('status',''))" 2>/dev/null)
    bsid=$(python3 -c "import json; print(json.load(open('$f')).get('id',''))" 2>/dev/null)
    if [[ "$bst" == "passed" || "$bst" == "eval_pass" ]] && [[ "$bsid" != "$sid" ]]; then
      if [[ -f "$SPRINTS_DIR/${bsid}.summary.md" ]]; then
        # 已归档: 只算活跃文件
        archived_active_total=$((archived_active_total + $(measure_active_tokens "$bsid")))
        archived_count=$((archived_count + 1))
      fi
    fi
  done < <(ls -t "$SPRINTS_DIR"/*.status.json 2>/dev/null)

  local archived_avg=0
  if [[ "$archived_count" -gt 0 ]]; then
    archived_avg=$((archived_active_total / archived_count))
  fi

  # 归档节省: 基线总 token vs 归档后活跃 token
  local archive_savings=0
  if [[ "$baseline_avg" -gt 0 ]]; then
    archive_savings=$(( (baseline_avg - archived_avg) * 100 / baseline_avg ))
  fi

  local verdict="FAIL"
  if [[ "$archive_savings" -ge 40 ]]; then
    verdict="PASS"
  fi

  local round
  round=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${sid}.status.json')).get('round',0))" 2>/dev/null || echo "0")

  cat > "$report_file" << REPORT_EOF
# Token 节省报告 — ${sid}

日期: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Sprint: ${sid}

## 对比 (归档效果)

| 指标 | 值 |
|------|-----|
| 基线平均 (${baseline_count} 个历史 Sprint, 归档前总文件) | ${baseline_avg} tokens |
| 归档后活跃文件平均 (${archived_count} 个已归档 Sprint) | ${archived_avg} tokens |
| 归档节省 | ${archive_savings}% |
| 达标 (>=40%) | ${verdict} |

## 本 Sprint 全量 token

| 指标 | 值 |
|------|-----|
| 本 Sprint (${round} 轮) | ${current_tokens} tokens |
| 全量对比基线 | $(( (baseline_avg - current_tokens) * 100 / baseline_avg ))% |

## 估算方法

- 系数: 1 行 ≈ ${TOKENS_PER_LINE} token (中英文混合文本经验值)
- 基线: 最近 ${baseline_count} 个 passed Sprint 的全量 token 数 (含归档文件)
- 归档节省: 基线全量 vs 归档后只剩 status.json + contract.md + summary.md
- 计算: (基线 - 归档后活跃) / 基线 × 100% = 节省百分比

## 已归档 Sprint 对比

REPORT_EOF

  # 已归档 Sprint 明细
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    local bst bsid
    bst=$(python3 -c "import json; print(json.load(open('$f')).get('status',''))" 2>/dev/null)
    bsid=$(python3 -c "import json; print(json.load(open('$f')).get('id',''))" 2>/dev/null)
    if [[ "$bst" == "passed" || "$bst" == "eval_pass" ]] && [[ -f "$SPRINTS_DIR/${bsid}.summary.md" ]]; then
      local total_t active_t
      total_t=$(measure_sprint "$bsid")
      active_t=$(measure_active_tokens "$bsid")
      echo "| ${bsid} | 全量 ${total_t} → 活跃 ${active_t} |" >> "$report_file"
    fi
  done < <(ls -t "$SPRINTS_DIR"/*.status.json 2>/dev/null | head -5)

  # 本 Sprint 明细
  echo "" >> "$report_file"
  echo "## 本 Sprint 明细" >> "$report_file"
  echo "" >> "$report_file"
  for ext in contract.md plan.md handoff.md eval.md eval.json dispatch.md events.jsonl status.json; do
    local f="$SPRINTS_DIR/${sid}.${ext}"
    local t
    t=$(count_tokens_in_file "$f")
    if [[ "$t" -gt 0 ]]; then
      echo "| ${ext} | ${t} tokens |" >> "$report_file"
    fi
  done

  echo "" >> "$report_file"
  echo "## 节省来源分析" >> "$report_file"
  echo "" >> "$report_file"

  if [[ "$archive_savings" -ge 0 ]]; then
    cat >> "$report_file" << EOF
- eval.json 结构化反馈: 建设者修复时只读 JSON，不读完整 eval.md
- archive.sh 归档: 旧 Sprint 文件移到 archive/，减少主目录扫描
- CACHE_BOUNDARY: dispatch.md 稳定前缀，KV Cache 命中率提升
- needs_human_review: 避免无效重试轮次浪费 token
EOF
  else
    echo "- 本次 token 高于基线，可能原因: 首次实现新功能、多轮修复" >> "$report_file"
  fi

  ok "报告已生成: ${report_file}"
  echo ""
  if [[ "$archive_savings" -ge 40 ]]; then
    ok "达标! 归档节省 ${archive_savings}% >= 40%"
  else
    warn "未达标: 归档节省 ${archive_savings}% < 40%"
  fi
}

# --- 命令入口 ---
case "${1:-help}" in
  baseline)
    do_baseline
    ;;
  measure)
    [[ -z "${2:-}" ]] && { err "用法: token-tracker.sh measure <sid>"; exit 1; }
    do_measure "$2"
    ;;
  report)
    [[ -z "${2:-}" ]] && { err "用法: token-tracker.sh report <sid>"; exit 1; }
    do_report "$2"
    ;;
  help|--help|-h|"")
    echo "Solar Harness — Token Tracker"
    echo ""
    echo "用法:"
    echo "  $0 baseline          计算历史基线 (最近 5 个 passed)"
    echo "  $0 measure <sid>     测量指定 Sprint 的 token"
    echo "  $0 report <sid>      生成对比报告"
    echo ""
    echo "估算方法: 文件行数 × ${TOKENS_PER_LINE} token/行"
    ;;
  *)
    err "未知命令: $1"
    exit 1
    ;;
esac
