#!/usr/bin/env bash
# 验证 coordinator dispatch 对 thinking pane 的修复护栏存在
set -eu

HARNESS_DIR="$HOME/.solar/harness"
COORD="$HARNESS_DIR/coordinator.sh"

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

[[ -f "$COORD" ]] || fail "coordinator.sh 不存在"

grep -q 'export LANG="en_US.UTF-8"' "$COORD" || fail "缺 LANG UTF-8 导出"
grep -q 'export LC_ALL="en_US.UTF-8"' "$COORD" || fail "缺 LC_ALL UTF-8 导出"
grep -q 'pane_is_thinking_snapshot' "$COORD" || fail "缺 thinking snapshot 检测"
grep -q 'tmux send-keys -t "\$pane" C-c' "$COORD" || fail "缺 C-c 解锁"
grep -q 'local max_tries=3' "$COORD" || fail "缺三次重试"
grep -q '"dispatch_failed"' "$COORD" || fail "缺 dispatch_failed 事件"
grep -q 'dispatch_keyword=$(basename "\$instruction_file")' "$COORD" || fail "缺派发关键字校验"

pass "dispatch thinking 护栏齐全"
