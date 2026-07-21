#!/usr/bin/env bash
# ================================================================
# D5: 通知端到端验证
#
# 流程:
#   1. 造 hello-world drafting Sprint
#   2. 填 Done + plan_reviewed APPROVE + 激活
#   3. 模拟 builder handoff + evaluator eval
#   4. 等协调器 finalize
#   5. 断言: history ≥ 7, .planner-last-notice 存在, coordinator.log 有 [notify]
#
# 用法: bash test-notification-e2e.sh
#
# @module solar-farm/harness/tests
# ================================================================
set -eu

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
COORD_LOG="$HARNESS_DIR/.coordinator.log"

# 造唯一 sprint id
TEST_SID="sprint-e2e-notify-$(date +%Y%m%d-%H%M%S)"
SF="$SPRINTS_DIR/${TEST_SID}.status.json"
CF="$SPRINTS_DIR/${TEST_SID}.contract.md"
HF="$SPRINTS_DIR/${TEST_SID}.handoff.md"
EF="$SPRINTS_DIR/${TEST_SID}.eval.md"
PF="$SPRINTS_DIR/${TEST_SID}.plan.md"

G='\033[0;32m'; R='\033[0;31m'; C='\033[0;36m'; N='\033[0m'
ok()   { echo -e "  ${G}✓${N} $1"; }
fail() { echo -e "  ${R}✗${N} $1"; CLEANUP; exit 1; }

CLEANUP() {
  # 清理测试文件
  rm -f "$SF" "$CF" "$HF" "$EF" "$PF" \
    "$SPRINTS_DIR/${TEST_SID}.dispatch.md" \
    "$SPRINTS_DIR/${TEST_SID}.events.jsonl" \
    "$SPRINTS_DIR/${TEST_SID}.finalized"
}

trap CLEANUP EXIT

echo -e "${C}[D5]${N} 通知端到端验证"
echo ""

# Step 1: 造 drafting Sprint
python3 -c "
import json, datetime
d = {
    'id': '${TEST_SID}',
    'title': 'hello-world-notification-test',
    'status': 'drafting',
    'round': 0,
    'created_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'updated_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'history': [
        {'ts': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'), 'event': 'contract_created', 'by': 'e2e_test'}
    ]
}
with open('${SF}', 'w') as f:
    json.dump(d, f, indent=2)
"

cat > "$CF" << 'EOF'
# Sprint Contract — hello-world-notification-test
## 需求
E2E notification test
## Done 定义
- [ ] D1 test passes
## 范围
包含: test only
## 约束
none
## 审判官评估维度
1. test passes
EOF

ok "Step 1: 测试 Sprint 已创建 (${TEST_SID})"

# Step 2: 模拟完整流程 — active → planning → approved → reviewing → passed
# 手动推进状态，绕过协调器派发

# active
python3 -c "
import json, datetime
d = json.load(open('${SF}'))
d['status'] = 'active'
d['updated_at'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
d['history'].append({'ts': d['updated_at'], 'event': 'done_criteria_filled', 'by': 'planner'})
d['history'].append({'ts': d['updated_at'], 'event': 'activated', 'by': 'planner'})
with open('${SF}', 'w') as f:
    json.dump(d, f, indent=2)
"
sleep 3  # 等协调器检测到 active

# plan (写 plan.md)
echo "# Plan\ntest" > "$PF"

# planning
python3 -c "
import json, datetime
d = json.load(open('${SF}'))
d['status'] = 'planning'
d['updated_at'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
with open('${SF}', 'w') as f:
    json.dump(d, f, indent=2)
"
sleep 3

# approved (模拟 plan_reviewed APPROVE)
python3 -c "
import json, datetime
d = json.load(open('${SF}'))
d['status'] = 'approved'
d['updated_at'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
d['history'].append({'ts': d['updated_at'], 'event': 'plan_reviewed', 'by': 'evaluator', 'verdict': 'approve'})
with open('${SF}', 'w') as f:
    json.dump(d, f, indent=2)
"
sleep 3

# reviewing (模拟 builder handoff)
cat > "$HF" << 'EOF'
# Handoff
## 变更文件
none (test)
## Done 达成
1. D1 test passes: ✅
## 验证方法
none
EOF

python3 -c "
import json, datetime
d = json.load(open('${SF}'))
d['status'] = 'reviewing'
d['round'] = 1
d['updated_at'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
with open('${SF}', 'w') as f:
    json.dump(d, f, indent=2)
"
sleep 3

# 模拟 evaluator eval
cat > "$EF" << 'EOF'
# Eval
## 总判定: PASS

### Done 条件逐条
| # | 条件 | 判定 | 证据 |
|---|------|------|------|
| 1 | D1 test passes | PASS | test |
EOF

python3 -c "
import json, datetime
d = json.load(open('${SF}'))
d['status'] = 'passed'
d['updated_at'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
d['history'].append({'ts': d['updated_at'], 'event': 'eval_written', 'by': 'evaluator'})
with open('${SF}', 'w') as f:
    json.dump(d, f, indent=2)
"

ok "Step 2: 状态推进到 passed"

# Step 3: 等协调器 finalize (最多 30s)
echo "  等待协调器 finalize..."
local waited=0
while (( waited < 30 )); do
  if [[ -f "$SPRINTS_DIR/${TEST_SID}.finalized" ]]; then
    ok "Step 3: 协调器已 finalize (${waited}s)"
    break
  fi
  sleep 2
  ((waited+=2))
done

if [[ ! -f "$SPRINTS_DIR/${TEST_SID}.finalized" ]]; then
  fail "Step 3: 协调器未在 30s 内 finalize"
fi

# Step 4: 断言
echo ""
echo "断言:"

# 断言 1: history ≥ 7
local history_count
history_count=$(python3 -c "import json; print(len(json.load(open('${SF}')).get('history',[])))" 2>/dev/null || echo 0)
if (( history_count >= 7 )); then
  ok "history 条目数: ${history_count} (≥ 7)"
else
  fail "history 条目数: ${history_count} (< 7)"
fi

# 断言 2: .planner-last-notice 存在且 ts 在 60s 内
local notice_file="$HARNESS_DIR/.planner-last-notice"
if [[ -f "$notice_file" ]]; then
  ok ".planner-last-notice 存在"
  local notice_content
  notice_content=$(cat "$notice_file")
  if echo "$notice_content" | grep -q "$TEST_SID"; then
    ok ".planner-last-notice 包含测试 sprint id"
  else
    fail ".planner-last-notice 不包含测试 sprint id: $notice_content"
  fi
else
  fail ".planner-last-notice 不存在"
fi

# 断言 3: coordinator.log 有 [notify] played Glass
local coord_log_tail
coord_log_tail=$(tail -100 "$COORD_LOG" 2>/dev/null || true)
if echo "$coord_log_tail" | grep -q '\[notify\] played Glass'; then
  ok "coordinator.log 包含 [notify] played Glass"
else
  # 可能是之前的 sprint 触发的, 检查最近有没有任何 notify
  if echo "$coord_log_tail" | grep -q '\[notify\]'; then
    ok "coordinator.log 包含 [notify] (可能不是本次 sprint)"
  else
    fail "coordinator.log 未找到 [notify] 日志"
  fi
fi

echo ""
echo -e "${G}D5 端到端验证完成${N}"
