#!/usr/bin/env bash
# 验证 round-N+1 active 派发路径存在
set -eu

HARNESS_DIR="$HOME/.solar/harness"
COORD="$HARNESS_DIR/coordinator.sh"

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

[[ -f "$COORD" ]] || fail "coordinator.sh 不存在"

grep -q 'if \[\[ "\${round:-0}" -ge 2 \]\]' "$COORD" || fail "缺 round>=2 分支"
grep -q 'build_round_contract_summary' "$COORD" || fail "缺合约摘要注入"
grep -q '不要回到写计划模式' "$COORD" || fail "缺 builder 角色重申"
grep -q '"round_dispatched"' "$COORD" || fail "缺 round_dispatched 事件"
grep -q 'active_round_n_plus_1' "$COORD" || fail "缺 round-N+1 路径标记"

pass "round-N+1 active 派发路径齐全"
