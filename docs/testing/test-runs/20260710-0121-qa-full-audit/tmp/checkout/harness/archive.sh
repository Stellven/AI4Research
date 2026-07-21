#!/bin/bash
# ================================================================
# Solar Harness — Sprint Archive
#
# 归档已完成的 Sprint，压缩 events.jsonl 为 summary.md
# 保持主目录清洁，支持可逆恢复
#
# 用法:
#   archive.sh archive <sid>   归档指定 Sprint
#   archive.sh restore <sid>   恢复已归档 Sprint
#   archive.sh auto            自动归档 (保留最近 3 个 passed)
#   archive.sh status          查看归档状态
#
# @module solar-farm/harness/archive
# ================================================================
set -eu

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
ARCHIVE_DIR="$SPRINTS_DIR/archive"

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; C='\033[0;36m'; N='\033[0m'
log()  { echo -e "${C}[Archive]${N} $*"; }
ok()   { echo -e "${G}[Archive]${N} $*"; }
warn() { echo -e "${Y}[Archive]${N} $*"; }
err()  { echo -e "${R}[Archive]${N} $*"; }

mkdir -p "$ARCHIVE_DIR"

# --- 生成 summary.md ---
generate_summary() {
  local sid="$1"
  local sf="$SPRINTS_DIR/${sid}.status.json"
  local events_file="$SPRINTS_DIR/${sid}.events.jsonl"
  local summary_file="$SPRINTS_DIR/${sid}.summary.md"

  local title status created_at round
  title=$(python3 -c "import json; print(json.load(open('$sf')).get('title',''))" 2>/dev/null || echo "unknown")
  status=$(python3 -c "import json; print(json.load(open('$sf')).get('status',''))" 2>/dev/null || echo "unknown")
  created_at=$(python3 -c "import json; print(json.load(open('$sf')).get('created_at',''))" 2>/dev/null || echo "unknown")
  round=$(python3 -c "import json; print(json.load(open('$sf')).get('round',0))" 2>/dev/null || echo "0")
  local updated_at
  updated_at=$(python3 -c "import json; print(json.load(open('$sf')).get('updated_at',''))" 2>/dev/null || echo "unknown")

  # 从 events.jsonl 提取关键事件
  local key_events=""
  if [[ -f "$events_file" ]]; then
    key_events=$(python3 -c "
import json, sys
lines = [l.strip() for l in open('${events_file}') if l.strip()]
# 提取关键事件: dispatched, waked, passed, failed, watchdog_restart
key_types = {'dispatched', 'waked', 'state_changed', 'watchdog_restart', 'watchdog_circuit_break'}
result = []
for line in lines:
    try:
        d = json.loads(line)
        evt = d.get('event', '')
        if evt in key_types or 'passed' in evt.lower() or 'fail' in evt.lower():
            result.append(f\"- {d.get('ts','')} [{d.get('by','')}] {evt}\" + (f\": {d.get('data',{}).get('to','') if isinstance(d.get('data'),dict) else ''}\" if isinstance(d.get('data'),dict) else ''))
    except:
        pass
# 最多 20 条
for r in result[:20]:
    print(r)
" 2>/dev/null || echo "- (无法解析事件)")
  fi

  # 从 eval.md 提取失败原因 (如有)
  local fail_reason=""
  local eval_file="$SPRINTS_DIR/${sid}.eval.md"
  if [[ -f "$eval_file" ]]; then
    fail_reason=$(grep -A5 "FAIL" "$eval_file" 2>/dev/null | head -5 || true)
  fi

  # 从 eval.json 提取失败条件 (如有)
  local eval_json_file="$SPRINTS_DIR/${sid}.eval.json"
  local json_fail=""
  if [[ -f "$eval_json_file" ]]; then
    json_fail=$(python3 -c "
import json
d = json.load(open('$eval_json_file'))
fc = d.get('failed_conditions', [])
if fc:
    print('失败条件: ' + ', '.join(fc))
    for e in d.get('errors', []):
        print(f\"  - {e.get('cond','')}: {e.get('fix_hint','')}\")
" 2>/dev/null || true)
  fi

  cat > "$summary_file" << SUMMARY_EOF
# Sprint 归档摘要 — ${sid}

- **标题**: ${title}
- **状态**: ${status}
- **轮次**: ${round}
- **创建**: ${created_at}
- **完成**: ${updated_at}
- **Sprint ID**: ${sid}

## 关键事件
${key_events:-无事件流}

## 评估结果
${json_fail:-无 eval.json}
${fail_reason:+## 失败详情
${fail_reason}}

---
*归档时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)*
SUMMARY_EOF

  echo "$summary_file"
}

# --- archive: 归档 Sprint ---
do_archive() {
  local sid="$1"
  local sf="$SPRINTS_DIR/${sid}.status.json"

  [[ -f "$sf" ]] || { err "Sprint 不存在: $sid"; exit 1; }

  local st
  st=$(python3 -c "import json; print(json.load(open('$sf')).get('status',''))" 2>/dev/null)

  case "$st" in
    passed|done|failed|eval_pass) ;;
    *) err "Sprint ${sid} 状态为 ${st}，只能归档终态 Sprint"; exit 1 ;;
  esac

  # 检查是否已归档 (events.jsonl 或 handoff.md 在 archive 中)
  if [[ -f "$ARCHIVE_DIR/${sid}.events.jsonl" ]] || [[ -f "$ARCHIVE_DIR/${sid}.handoff.md" ]]; then
    warn "Sprint ${sid} 已在归档中"
    return 0
  fi

  # 生成 summary
  local summary_file
  summary_file=$(generate_summary "$sid")
  ok "生成摘要: ${summary_file}"

  # 移动 events.jsonl 到 archive (先写 archived_at 事件)
  local events_file="$SPRINTS_DIR/${sid}.events.jsonl"
  if [[ -f "$events_file" ]]; then
    echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"event\":\"archived\",\"by\":\"archive.sh\"}" >> "$events_file"
    mv "$events_file" "$ARCHIVE_DIR/${sid}.events.jsonl"
    log "events.jsonl → archive/ (含 archived_at 事件)"
  fi

  # 移动 eval.md 相关文件 (保留在主目录供查看，只移大的 events.jsonl)
  # 也移动 dispatch.md (如果有)
  local dispatch_file="$SPRINTS_DIR/${sid}.dispatch.md"
  if [[ -f "$dispatch_file" ]]; then
    mv "$dispatch_file" "$ARCHIVE_DIR/${sid}.dispatch.md" 2>/dev/null || true
  fi

  # 移动 plan.md (如果有)
  local plan_file="$SPRINTS_DIR/${sid}.plan.md"
  if [[ -f "$plan_file" ]]; then
    mv "$plan_file" "$ARCHIVE_DIR/${sid}.plan.md" 2>/dev/null || true
  fi

  # 移动 handoff.md (如果有)
  local handoff_file="$SPRINTS_DIR/${sid}.handoff.md"
  if [[ -f "$handoff_file" ]]; then
    mv "$handoff_file" "$ARCHIVE_DIR/${sid}.handoff.md" 2>/dev/null || true
  fi

  ok "Sprint ${sid} 已归档 (保留 status.json + contract.md + summary.md)"
}

# --- restore: 恢复已归档 Sprint ---
do_restore() {
  local sid="$1"

  # 检查 archive 目录是否有该 sprint 的任何文件
  local has_any=false
  for ext in events.jsonl dispatch.md plan.md handoff.md; do
    if [[ -f "$ARCHIVE_DIR/${sid}.${ext}" ]]; then
      has_any=true
      break
    fi
  done

  if ! $has_any; then
    err "归档中无 ${sid} 的任何文件"
    exit 1
  fi

  # 移回 events.jsonl (如果有的话，legacy sprint 可能没有)
  local archived_events="$ARCHIVE_DIR/${sid}.events.jsonl"
  if [[ -f "$archived_events" ]]; then
    mv "$archived_events" "$SPRINTS_DIR/${sid}.events.jsonl"
    log "events.jsonl 已恢复"
  else
    warn "无 events.jsonl (legacy sprint，原本就没有)"
  fi

  # 恢复其他文件
  for ext in dispatch.md plan.md handoff.md; do
    local archived="$ARCHIVE_DIR/${sid}.${ext}"
    if [[ -f "$archived" ]]; then
      mv "$archived" "$SPRINTS_DIR/${sid}.${ext}" 2>/dev/null || true
      log "${ext} 已恢复"
    fi
  done

  # 删除 summary.md
  rm -f "$SPRINTS_DIR/${sid}.summary.md"

  ok "Sprint ${sid} 已恢复"
}

# --- auto: 自动归档 ---
do_auto() {
  log "扫描可归档的 Sprint..."

  # 策略: 只归档 passed 且 >24h 的 sprint，保留最近 3 个
  local candidates
  candidates=$(python3 -c "
import json, os, glob, time

cutoff = time.time() - 86400  # 24h 保护
sprints = glob.glob('$SPRINTS_DIR/*.status.json')
passed = []
for f in sprints:
    try:
        d = json.load(open(f))
        if d.get('status') in ('passed', 'done', 'eval_pass'):
            mtime = os.path.getmtime(f)
            if mtime < cutoff:
                passed.append((mtime, d['id']))
    except:
        pass
passed.sort(reverse=True)
# 保留最近 3 个 (按 mtime 排序)
for _, sid in passed[3:]:
    print(sid)
" 2>/dev/null)

  local count=0
  for sid in $candidates; do
    [[ -z "$sid" ]] && continue
    # 跳过已有 archive 的 (检查 events.jsonl 或 handoff.md)
    [[ -f "$ARCHIVE_DIR/${sid}.events.jsonl" ]] && continue
    [[ -f "$ARCHIVE_DIR/${sid}.handoff.md" ]] && continue
    log "归档: ${sid}"
    do_archive "$sid"
    count=$((count + 1))
  done

  if [[ "$count" -eq 0 ]]; then
    ok "无需归档 (已归档/未超过 3 个/未满 24h)"
  else
    ok "已归档 ${count} 个 Sprint"
  fi
}

# --- status: 查看归档状态 ---
do_status() {
  echo ""
  local archived_count
  archived_count=$(ls "$ARCHIVE_DIR"/*.events.jsonl 2>/dev/null | wc -l | tr -d ' ')
  local active_count
  active_count=$(ls "$SPRINTS_DIR"/*.events.jsonl 2>/dev/null | wc -l | tr -d ' ')

  ok "活跃 Sprint (有 events.jsonl): ${active_count}"
  ok "已归档: ${archived_count}"
  echo ""

  if [[ "$archived_count" -gt 0 ]]; then
    log "已归档列表:"
    for f in "$ARCHIVE_DIR"/*.events.jsonl; do
      [[ -f "$f" ]] || continue
      local sid
      sid=$(basename "$f" .events.jsonl)
      local summary="$SPRINTS_DIR/${sid}.summary.md"
      if [[ -f "$summary" ]]; then
        local st round
        st=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${sid}.status.json')).get('status',''))" 2>/dev/null || echo "?")
        round=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${sid}.status.json')).get('round',0))" 2>/dev/null || echo "?")
        echo -e "  ${C}${sid}${N}  ${st}  R${round}"
      else
        echo -e "  ${Y}${sid}${N}  (无 summary)"
      fi
    done
  fi
  echo ""
}

# --- 命令入口 ---
case "${1:-help}" in
  archive)
    [[ -z "${2:-}" ]] && { err "用法: archive.sh archive <sid>"; exit 1; }
    do_archive "$2"
    ;;
  restore)
    [[ -z "${2:-}" ]] && { err "用法: archive.sh restore <sid>"; exit 1; }
    do_restore "$2"
    ;;
  auto)
    do_auto
    ;;
  status)
    do_status
    ;;
  help|--help|-h|"")
    echo "Solar Harness — Sprint Archive"
    echo ""
    echo "用法:"
    echo "  $0 archive <sid>   归档指定 Sprint (移 events.jsonl 到 archive/)"
    echo "  $0 restore <sid>   恢复已归档 Sprint (可逆)"
    echo "  $0 auto            自动归档 (保留最近 3 个 passed)"
    echo "  $0 status          查看归档状态"
    ;;
  *)
    err "未知命令: $1"
    exit 1
    ;;
esac
