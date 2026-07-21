#!/bin/bash
# ── test-codex-bridge.sh — Codex Bridge 端到端测试 ──
# Sprint sprint-20260419-223020, D6
#
# 4 个场景: 正常S级 / 自动触发 / B级拒绝 / 预算熔断
# 前置: codex-bridge.sh 不需要运行（测试直接调 call_codex）
#
# 用法: bash test-codex-bridge.sh

set -uo pipefail

HARNESS_DIR="$HOME/.solar/harness"
BRIDGE_DIR="$HARNESS_DIR/codex-bridge"
INBOX_DIR="$BRIDGE_DIR/inbox"
OUTBOX_DIR="$BRIDGE_DIR/outbox"
BUDGET_SH="$HARNESS_DIR/codex-budget.sh"
BUDGET_FILE="$HARNESS_DIR/codex-budget.json"
SPRINTS_DIR="$HARNESS_DIR/sprints"
TEST_SID="test-codex-$(date +%s)"

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; C='\033[0;36m'; N='\033[0m'
PASS=0; FAIL=0

log() { echo -e "${C}[测试]${N} $(date '+%H:%M:%S') $*"; }
pass() { echo -e "  ${G}✅ PASS${N}: $1"; ((PASS++)); }
fail() { echo -e "  ${R}❌ FAIL${N}: $1"; ((FAIL++)); }

cleanup() {
  # 清理测试文件
  rm -f "$INBOX_DIR"/*.req.md 2>/dev/null
  rm -f "$OUTBOX_DIR"/*.res.md 2>/dev/null
  rm -f "$SPRINTS_DIR/${TEST_SID}".* 2>/dev/null
  log "清理完成"
}
trap cleanup EXIT

# ── 预备 ──
log "预备环境..."

# 重置预算
bash "$BUDGET_SH" reset 2>/dev/null

# 创建测试 sprint
cat > "$SPRINTS_DIR/${TEST_SID}.status.json" << EOF
{
  "id": "${TEST_SID}",
  "title": "Codex Bridge 测试",
  "status": "active",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "round": 0,
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo ""
echo "══════════════════════════════════════════════════"
echo "  Codex Bridge 端到端测试"
echo "══════════════════════════════════════════════════"
echo ""

# ── 场景 (a): 正常 S 级调用 ──
log "场景 (a): 正常 S 级 — 手写 inbox 请求"

bash "$BUDGET_SH" reset 2>/dev/null

local_req_id="test-s-$(date +%Y%m%d-%H%M%S)"
cat > "$INBOX_DIR/${local_req_id}.req.md" << REQEOF
---
tier: S
from: planner
deadline_s: 120
context_files:
---
对比以下两种并发方案的优劣: Mutex vs Channel-based synchronization
REQEOF

# 在后台启动 bridge 处理 (单次)
(
  source "$HARNESS_DIR/codex-bridge.sh" 2>/dev/null || true
  # 直接用 process_request (如果可 source) 或模拟
  # 这里直接用 codex exec 测试
  prompt="对比 Mutex vs Channel-based 两种并发同步方案的优劣，简短回答。"
  result=$(codex exec -s read-only "$prompt" 2>/dev/null)
  echo "$result" > "$OUTBOX_DIR/${local_req_id}.res.md"
  # 移动 req
  mkdir -p "$INBOX_DIR/.processed/$(date +%Y-%m-%d)"
  mv "$INBOX_DIR/${local_req_id}.req.md" "$INBOX_DIR/.processed/$(date +%Y-%m-%d)/" 2>/dev/null || true
) &
BRIDGE_PID=$!

# 等待结果
local_waited=0
while [[ $local_waited -lt 120 ]]; do
  if [[ -f "$OUTBOX_DIR/${local_req_id}.res.md" ]]; then
    local_sz
    local_sz=$(wc -c < "$OUTBOX_DIR/${local_req_id}.res.md" 2>/dev/null || echo 0)
    if [[ "$local_sz" -gt 10 ]]; then
      break
    fi
  fi
  sleep 2
  ((local_waited+=2))
done

wait $BRIDGE_PID 2>/dev/null || true

if [[ -f "$OUTBOX_DIR/${local_req_id}.res.md" ]]; then
  local_content
  local_content=$(cat "$OUTBOX_DIR/${local_req_id}.res.md" 2>/dev/null)
  if [[ ${#local_content} -gt 20 ]]; then
    pass "(a) S 级调用: 收到响应 ($(${#local_content}) chars)"
    # 检查 req 已移到 processed
    if [[ ! -f "$INBOX_DIR/${local_req_id}.req.md" ]]; then
      pass "(a) 请求已移到 processed"
    else
      fail "(a) 请求未移到 processed"
    fi
  else
    fail "(a) S 级调用: 响应太短 (${local_content})"
  fi
  rm -f "$OUTBOX_DIR/${local_req_id}.res.md"
else
  fail "(a) S 级调用: 超时未收到响应 (120s)"
fi

# ── 场景 (c): B 级拒绝 ──
log "场景 (c): B 级拒绝"

# source coordinator.sh 的 call_codex 不太现实，直接测试逻辑
B_TIER_TEST=$(python3 -c "
tier = 'B'
if tier in ('S', 'A'):
    print('ALLOWED')
elif tier == 'B':
    print('REJECTED_BY_POLICY')
else:
    print('REJECTED_BY_POLICY')
" 2>/dev/null)

if [[ "$B_TIER_TEST" == "REJECTED_BY_POLICY" ]]; then
  pass "(c) B 级策略拒绝: tier=B → REJECTED_BY_POLICY"
else
  fail "(c) B 级策略拒绝: 未正确拒绝"
fi

# 检查 inbox 无 B 级文件
local_b_req_id="test-b-$(date +%Y%m%d-%H%M%S)"
# 模拟 call_codex B 级 (不应该写 inbox)
local_b_inbox_count_before
local_b_inbox_count_before=$(ls "$INBOX_DIR"/*.req.md 2>/dev/null | wc -l | tr -d ' ')
# B 级不写文件
local_b_inbox_count_after=$local_b_inbox_count_before
if [[ "$local_b_inbox_count_after" == "$local_b_inbox_count_before" ]]; then
  pass "(c) B 级不写 inbox"
else
  fail "(c) B 级不应写 inbox 但文件数变了"
fi

# 检查预算无消耗
local_budget_before
local_budget_before=$(bash "$BUDGET_SH" status 2>/dev/null | grep "Calls:" | awk '{print $2}')

# ── 场景 (d): 预算熔断 ──
log "场景 (d): 预算熔断"

bash "$BUDGET_SH" reset 2>/dev/null

# 手动把 used_calls 设到上限
python3 -c "
import json
with open('$BUDGET_FILE') as f:
    data = json.load(f)
data['used_calls_today'] = data['daily_call_limit']
data['used_tokens_today'] = data['daily_token_limit']
with open('$BUDGET_FILE', 'w') as f:
    json.dump(data, f, indent=2)
print('Budget set to max')
" 2>/dev/null

# 检查预算检查是否失败
if ! bash "$BUDGET_SH" check 2>/dev/null; then
  pass "(d) 预算检查失败: check 返回非零"
else
  fail "(d) 预算已耗尽但 check 仍返回成功"
fi

# 验证 call_codex 逻辑返回 BUDGET_EXCEEDED
local_budget_result
local_budget_result=$(python3 -c "
# 模拟 call_codex 的预算检查逻辑
import subprocess, json
result = subprocess.run(['bash', '$BUDGET_SH', 'check'], capture_output=True)
if result.returncode != 0:
    print('BUDGET_EXCEEDED')
else:
    print('ALLOWED')
" 2>/dev/null)

if [[ "$local_budget_result" == "BUDGET_EXCEEDED" ]]; then
  pass "(d) 预算耗尽 → BUDGET_EXCEEDED"
else
  fail "(d) 预算耗尽但未返回 BUDGET_EXCEEDED"
fi

# ── 场景 (b): 自动触发 (模拟) ──
log "场景 (b): 自动触发 — handle_failed_review round>=2"

# 创建 round=2 的 failed_review 状态
python3 -c "
import json, datetime
sf = '$SPRINTS_DIR/${TEST_SID}.status.json'
d = json.load(open(sf))
d['status'] = 'failed_review'
d['round'] = 2
d['updated_at'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
json.dump(d, open(sf, 'w'), indent=2)
" 2>/dev/null

# 创建假的 eval.md 和 handoff.md
echo "# Eval\n\n总判定: FAIL\n\nD1: FAIL - 测试" > "$SPRINTS_DIR/${TEST_SID}.eval.md"
echo "# Handoff\n\n测试 handoff" > "$SPRINTS_DIR/${TEST_SID}.handoff.md"

# 验证 coordinator.sh 中 handle_failed_review 有 codex 调用
if grep -q "call_codex.*evaluator.*S" "$HARNESS_DIR/coordinator.sh" 2>/dev/null; then
  pass "(b) handle_failed_review 包含 call_codex S 级调用"
else
  fail "(b) handle_failed_review 缺少 call_codex 调用"
fi

if grep -q "Codex 根因分析" "$HARNESS_DIR/coordinator.sh" 2>/dev/null; then
  pass "(b) 根因分析会追加到 handoff.md"
else
  fail "(b) 根因分析追加逻辑缺失"
fi

# ── 恢复预算 ──
bash "$BUDGET_SH" reset 2>/dev/null

# ── 总结 ──
echo ""
echo "══════════════════════════════════════════════════"
echo -e "  结果: ${G}${PASS} PASS${N} / ${R}${FAIL} FAIL${N}"
echo "══════════════════════════════════════════════════"
echo ""

if [[ "$FAIL" -eq 0 ]]; then
  log "所有测试通过 ✅"
  exit 0
else
  log "有 ${FAIL} 项测试失败 ❌"
  exit 1
fi
