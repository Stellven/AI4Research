#!/usr/bin/env bash
# test-plan-stuck.sh — Bug A reproduction: plan-review 卡死
# 模拟: sprint status=planning, plan.md 末尾有 REJECT 标记, 但 status 未推进
set -euo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HOME/.solar/harness/sprints"
TEST_SID="test-plan-stuck-$$"

cleanup() {
  rm -f "$SPRINTS_DIR/${TEST_SID}.status.json"
  rm -f "$SPRINTS_DIR/${TEST_SID}.plan.md"
  rm -f "$SPRINTS_DIR/${TEST_SID}.finalized"
  rm -f "$SPRINTS_DIR/${TEST_SID}.events.jsonl"
}
trap cleanup EXIT

echo "=== Bug A Reproduction: plan-review stuck ==="

# 1. 创建 mock sprint: status=planning + plan.md 带 REJECT 标记
cat > "$SPRINTS_DIR/${TEST_SID}.status.json" << 'SJ'
{
  "id": "test-plan-stuck",
  "title": "Bug A reproduction",
  "status": "planning",
  "created_at": "2026-04-20T10:00:00Z",
  "round": 0,
  "history": [
    {"ts": "2026-04-20T10:00:00Z", "event": "contract_created", "by": "user"}
  ],
  "updated_at": "2026-04-20T10:00:00Z"
}
SJ

cat > "$SPRINTS_DIR/${TEST_SID}.plan.md" << 'PM'
# Plan for Bug A reproduction

## Implementation
Some plan content here.

## 审判官审批意见 — REJECT

这个计划有问题，需要修改。
PM

echo "Mock sprint created: $TEST_SID (status=planning, plan.md has REJECT)"

# 2. 模拟 handle_planning 自愈逻辑: 扫 plan.md 末尾 APPROVE/REJECT
REJECT_MARKER=$(tail -20 "$SPRINTS_DIR/${TEST_SID}.plan.md" | grep -oE '(APPROVE|REJECT)' | tail -1 || true)

if [[ "$REJECT_MARKER" == "REJECT" ]]; then
  # 检查 status 是否仍为 planning
  CURRENT_STATUS=$(python3 -c "import json; d=json.load(open('$SPRINTS_DIR/${TEST_SID}.status.json')); print(d['status'])")
  if [[ "$CURRENT_STATUS" == "planning" ]]; then
    echo "STUCK_CONFIRMED: plan.md has REJECT but status still planning — Bug A reproduced"
    echo "[heal] plan-review stuck detected, auto-advancing via plan-verdict"
    # 3. 调用 plan-verdict 原子命令修复
    bash "$HARNESS_DIR/solar-harness.sh" plan-verdict "$TEST_SID" reject "Bug A reproduction test"
    # 4. 验证 status 已推进
    NEW_STATUS=$(python3 -c "import json; d=json.load(open('$SPRINTS_DIR/${TEST_SID}.status.json')); print(d['status'])")
    if [[ "$NEW_STATUS" == "active" ]]; then
      echo "PASS: plan-verdict auto-healed stuck state planning→active"
      exit 0
    else
      echo "FAIL: expected status=active, got status=$NEW_STATUS"
      exit 1
    fi
  else
    echo "SKIP: status already advanced to $CURRENT_STATUS"
    exit 0
  fi
else
  echo "FAIL: REJECT marker not found in plan.md (got: $REJECT_MARKER)"
  exit 1
fi
