#!/bin/bash
# ── planner-review-drafting.sh ──
# Sprint sprint-20260418-065434, D4: 规划者审核 drafting Sprint
#
# 扫描所有 auto_generated drafting Sprint, 若 Done >= 3 条 → 通知规划者
# 调用方: coordinator.sh 主循环 (每 10 次迭代)
#
# 用法: planner-review-drafting.sh

set -uo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
INBOX="$HARNESS_DIR/PLANNER-INBOX.md"
NOTIFIED_FILE="$HARNESS_DIR/.drafting-notified"

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# 遍历 drafting Sprint
for sf in "$SPRINTS_DIR"/sprint-*.status.json; do
  [[ -f "$sf" ]] || continue

  # 检查是否 auto_generated + drafting
  local_status=$(python3 -c "
import json
d=json.load(open('$sf'))
print(f\"{d.get('status','')}|{d.get('auto_generated',False)}\")
" 2>/dev/null || continue)

  [[ "$local_status" == "drafting|True" ]] || continue

  sid=$(python3 -c "import json; print(json.load(open('$sf')).get('title',''))" 2>/dev/null || echo "unknown")
  sid_file=$(basename "$sf" .status.json)

  # 检查是否已通知过
  [[ -f "$NOTIFIED_FILE" ]] && grep -q "$sid_file" "$NOTIFIED_FILE" 2>/dev/null && continue

  # 检查 Done 条件数量
  local_cf="$SPRINTS_DIR/${sid_file}.contract.md"
  [[ -f "$local_cf" ]] || continue

  done_count=$(grep -c '^\- \[ \] \*\*D' "$local_cf" 2>/dev/null || true)

  if [[ "$done_count" -ge 3 ]]; then
    # Done 条件完整 → 通知规划者
    echo "- [ ] [${TS}] Drafting Sprint 就绪: ${sid_file} (${done_count} Done 条件, 需审核)" >> "$INBOX"
    echo "${sid_file}" >> "$NOTIFIED_FILE"
    echo "[drafting-review] 通知: ${sid_file} (${done_count} Done)"
  else
    echo "[drafting-review] ${sid_file} Done 不足 (${done_count}/3), 等待补充"
  fi
done

exit 0
