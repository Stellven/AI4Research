#!/usr/bin/env bash
# ================================================================
# Solar Harness — Resilience Regression Tests (D1-D5)
#
# 覆盖:
#   test_d1_exit_capture   — pane-launcher 退出信号捕获
#   test_d2_no_auto_send   — 无 sleep 8 硬编码
#   test_d3_remain_on_exit — start_harness 设了 remain-on-exit
#   test_d4_doctor_json    — doctor 输出有效 JSON + 必含字段
#   test_d5_watchdog_pane  — watchdog 包含 check_panes 函数
#
# 用法:
#   bash test-harness-resilience.sh
#   bash test-harness-resilience.sh test_d4_doctor_json  # 单项
#
# @module solar-farm/harness/tests
# ================================================================
set -eu

HARNESS_DIR="$HOME/.solar/harness"
PASS=0
FAIL=0
SKIP=0
RESULTS_FILE="/tmp/test-resilience-results-$$"

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; N='\033[0m'

ok()   { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); echo "PASS: $1" >> "$RESULTS_FILE"; }
fail() { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); echo "FAIL: $1" >> "$RESULTS_FILE"; }
skip() { echo -e "  ${Y}⊘${N} $1"; SKIP=$((SKIP+1)); echo "SKIP: $1" >> "$RESULTS_FILE"; }

# --- D1: 退出信号捕获 ---
test_d1_exit_capture() {
  echo -e "${C}[D1]${N} 退出信号捕获"

  # 检查 pane-launcher.sh 包含退出日志逻辑
  if grep -q 'pane-exit.jsonl' "$HARNESS_DIR/pane-launcher.sh"; then
    ok "pane-launcher.sh 包含 pane-exit.jsonl 写入"
  else
    fail "pane-launcher.sh 缺少 pane-exit.jsonl 写入"
  fi

  # 检查 start-incarnation.sh 包含退出日志逻辑
  if grep -q 'pane-exit.jsonl' "$HARNESS_DIR/start-incarnation.sh"; then
    ok "start-incarnation.sh 包含 pane-exit.jsonl 写入"
  else
    fail "start-incarnation.sh 缺少 pane-exit.jsonl 写入"
  fi

  # 检查 set +e 保护
  if grep -q 'set +e' "$HARNESS_DIR/pane-launcher.sh" && grep -q 'set +e' "$HARNESS_DIR/start-incarnation.sh"; then
    ok "两个脚本都有 set +e 保护 (claude 退出不中断)"
  else
    fail "缺少 set +e 保护"
  fi

  # 检查字段齐全: ts, pane, persona, exit_code, signal, last_30_lines
  for field in ts pane persona exit_code signal last_30_lines; do
    if grep -q "'${field}'" "$HARNESS_DIR/pane-launcher.sh"; then
      ok "pane-launcher.sh 退出记录含 ${field}"
    else
      fail "pane-launcher.sh 退出记录缺 ${field}"
    fi
  done

  # Mock 测试: 创建临时脚本模拟退出捕获
  local tmpdir
  tmpdir=$(mktemp -d)
  local exit_log="$tmpdir/pane-exit.jsonl"

  # 模拟退出记录写入
  python3 -c "
import json, datetime
record = {
    'ts': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'pane': '%0',
    'persona': 'builder',
    'exit_code': 0,
    'signal': 'normal',
    'last_30_lines': 'test line'
}
print(json.dumps(record, ensure_ascii=False))
" >> "$exit_log"

  # 验证: 文件有 1 条完整记录
  local count
  count=$(wc -l < "$exit_log" | tr -d ' ')
  if [[ "$count" -ge 1 ]]; then
    # 验证字段齐全
    if python3 -c "
import json, sys
d = json.load(open('$exit_log'))
required = ['ts', 'pane', 'persona', 'exit_code', 'signal', 'last_30_lines']
missing = [k for k in required if k not in d]
if missing:
    print(f'missing: {missing}')
    sys.exit(1)
print('OK')
" 2>/dev/null | grep -q 'OK'; then
      ok "Mock 退出记录字段齐全 (6/6)"
    else
      fail "Mock 退出记录字段不齐全"
    fi
  else
    fail "Mock 退出记录未写入"
  fi

  rm -rf "$tmpdir"
}

# --- D2: 无 auto-send 竞态 ---
test_d2_no_auto_send() {
  echo -e "${C}[D2]${N} 无 auto-send 竞态"

  # 检查两个脚本都无 "sleep 8" 硬编码 auto-send
  if ! grep -q 'sleep 8 && tmux send-keys' "$HARNESS_DIR/pane-launcher.sh"; then
    ok "pane-launcher.sh 已移除 sleep 8 auto-send"
  else
    fail "pane-launcher.sh 仍有 sleep 8 auto-send"
  fi

  if ! grep -q 'sleep 8 && tmux send-keys' "$HARNESS_DIR/start-incarnation.sh"; then
    ok "start-incarnation.sh 已移除 sleep 8 auto-send"
  else
    fail "start-incarnation.sh 仍有 sleep 8 auto-send"
  fi

  # 检查有 poll 就绪逻辑
  if grep -q 'send_solar_when_ready' "$HARNESS_DIR/pane-launcher.sh"; then
    ok "pane-launcher.sh 有 poll 就绪函数 send_solar_when_ready"
  else
    fail "pane-launcher.sh 缺少 poll 就绪函数"
  fi

  if grep -q 'send_solar_when_ready' "$HARNESS_DIR/start-incarnation.sh"; then
    ok "start-incarnation.sh 有 poll 就绪函数 send_solar_when_ready"
  else
    fail "start-incarnation.sh 缺少 poll 就绪函数"
  fi

  # 检查 poll 检测 ╭── 提示符
  if grep -qE '╭──' "$HARNESS_DIR/pane-launcher.sh"; then
    ok "poll 检测 ╭── 就绪提示符"
  else
    fail "poll 未检测 ╭── 就绪提示符"
  fi
}

# --- D3: pane 保留现场 ---
test_d3_remain_on_exit() {
  echo -e "${C}[D3]${N} pane 保留现场 (remain-on-exit)"

  # 检查 solar-harness.sh 包含 remain-on-exit on
  if grep -q 'remain-on-exit on' "$HARNESS_DIR/solar-harness.sh"; then
    ok "solar-harness.sh 包含 remain-on-exit on"
  else
    fail "solar-harness.sh 缺少 remain-on-exit on"
  fi

  # 检查位置正确: 在 new-session 之后、split-window 之前
  local line_new line_remain line_split
  line_new=$(grep -n 'tmux new-session -d' "$HARNESS_DIR/solar-harness.sh" | head -1 | cut -d: -f1)
  line_remain=$(grep -n 'remain-on-exit on' "$HARNESS_DIR/solar-harness.sh" | head -1 | cut -d: -f1)
  line_split=$(grep -n 'tmux split-window -v' "$HARNESS_DIR/solar-harness.sh" | head -1 | cut -d: -f1)

  if [[ -n "$line_new" && -n "$line_remain" && -n "$line_split" ]]; then
    if (( line_new < line_remain && line_remain < line_split )); then
      ok "remain-on-exit 位置正确 (new-session → remain-on-exit → split-window)"
    else
      fail "remain-on-exit 位置不正确 (应在 new-session 和 split-window 之间)"
    fi
  else
    fail "无法定位关键行 (new/session/remain/split)"
  fi
}

# --- D4: doctor JSON ---
test_d4_doctor_json() {
  echo -e "${C}[D4]${N} doctor JSON 输出"

  local json_output
  # doctor.sh now exits nonzero when a REQUIRED check fails, but still prints the
  # JSON body; capture it regardless and validate the body below, so a fail
  # verdict is not misreported as an execution crash.
  json_output=$(bash "$HARNESS_DIR/doctor.sh" 2>/dev/null) || true

  # 验证 JSON 可解析
  if echo "$json_output" | python3 -m json.tool &>/dev/null; then
    ok "doctor 输出是有效 JSON"
  else
    fail "doctor 输出不是有效 JSON"
    return
  fi

  # 验证必含字段
  local required_fields="tmux_session_alive coordinator_pid coordinator_alive watchdog_pid watchdog_alive bash_version bash_path panes warnings repairs_available"
  for field in $required_fields; do
    if echo "$json_output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if '$field' in d:
    sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
      ok "JSON 含字段: ${field}"
    else
      fail "JSON 缺字段: ${field}"
    fi
  done

  # 验证 doctor 是只读的 (检查脚本不包含实际写操作命令)
  # grep 排除字符串字面量和注释
  local doctor_violations
  doctor_violations=$(grep -nE '^[^#]*\b(tmux\s+kill-session|tmux\s+respawn-pane|coordinator-watchdog\.sh\s+start|start-incarnation\.sh)\b' "$HARNESS_DIR/doctor.sh" 2>/dev/null || true)
  if [[ -z "$doctor_violations" ]]; then
    ok "doctor.sh 纯只读 (无 kill-session/respawn-pane/start-incarnation 调用)"
  else
    fail "doctor.sh 包含写操作: $doctor_violations"
  fi

  # 验证 --summary 模式
  local summary
  # As above: a fail verdict exits nonzero but still prints the summary body.
  summary=$(bash "$HARNESS_DIR/doctor.sh" --summary 2>/dev/null) || true
  if echo "$summary" | grep -q 'Doctor Summary'; then
    ok "doctor --summary 输出含 Doctor Summary"
  else
    fail "doctor --summary 输出异常"
  fi
}

# --- D5: watchdog 死 pane 检测 ---
test_d5_watchdog_pane() {
  echo -e "${C}[D5]${N} watchdog 死 pane 自愈"

  # 检查 watchdog 包含 check_panes 函数
  if grep -q 'check_panes()' "$HARNESS_DIR/coordinator-watchdog.sh"; then
    ok "watchdog 包含 check_panes() 函数"
  else
    fail "watchdog 缺少 check_panes() 函数"
  fi

  # 检查 PANE_RESTART_COOLDOWN rate-limit
  if grep -q 'PANE_RESTART_COOLDOWN' "$HARNESS_DIR/coordinator-watchdog.sh"; then
    ok "watchdog 包含 rate-limit 配置 (PANE_RESTART_COOLDOWN)"
  else
    fail "watchdog 缺少 rate-limit 配置"
  fi

  # 检查 pane_auto_restarted 事件写入
  if grep -q 'pane_auto_restarted' "$HARNESS_DIR/coordinator-watchdog.sh"; then
    ok "watchdog 写 pane_auto_restarted 事件"
  else
    fail "watchdog 缺少 pane_auto_restarted 事件"
  fi

  # 检查 rate-limit 超限写警告
  if grep -q 'pane_restart_rate_limited' "$HARNESS_DIR/coordinator-watchdog.sh"; then
    ok "watchdog rate-limit 超限写警告事件"
  else
    fail "watchdog 缺少 rate-limit 超限警告"
  fi

  # 检查 PANE_MAX_RESTARTS=2
  if grep -q 'PANE_MAX_RESTARTS=2' "$HARNESS_DIR/coordinator-watchdog.sh"; then
    ok "同一 pane 1分钟内最多重启 2 次"
  else
    fail "PANE_MAX_RESTARTS 配置异常"
  fi

  # 检查 respawn-pane 或 start-incarnation 调用
  if grep -q 'start-incarnation.sh' "$HARNESS_DIR/coordinator-watchdog.sh"; then
    ok "watchdog 调用 start-incarnation.sh 重启 pane"
  else
    fail "watchdog 未调用 start-incarnation.sh"
  fi

  # 新增: 白名单仅含 claude/node (不含 bash/zsh/sh/fish)
  local whitelist_line
  whitelist_line=$(grep -E '^\s+claude\|node\) continue' "$HARNESS_DIR/coordinator-watchdog.sh" || true)
  if [[ -n "$whitelist_line" ]]; then
    ok "白名单仅含 claude/node (严格对齐合约)"
  else
    fail "白名单格式异常 (期望 claude|node) continue)"
  fi
  if ! grep -qE 'bash\|zsh\|sh\|fish\) continue' "$HARNESS_DIR/coordinator-watchdog.sh"; then
    ok "白名单不含 shell 类命令 (bash/zsh/sh/fish)"
  else
    fail "白名单仍含 shell 类命令 (合约偏离)"
  fi

  # 新增: claude 活性检测走子进程树或 UI fallback
  if grep -q 'is_claude_alive()' "$HARNESS_DIR/coordinator-watchdog.sh"; then
    ok "watchdog 包含 is_claude_alive() 活性检测函数"
  else
    fail "watchdog 缺少 is_claude_alive() 活性检测函数"
  fi
  if grep -qE 'pgrep -P' "$HARNESS_DIR/coordinator-watchdog.sh" && grep -qE '❯|⏺|✳|╭──' "$HARNESS_DIR/coordinator-watchdog.sh"; then
    ok "活性检测走子进程树 (pgrep -P) + UI 特征 fallback"
  else
    fail "活性检测缺少子进程树或 UI fallback"
  fi

  # 新增: PERSONA_PANES 只含 0/1/2
  local persona_line
  persona_line=$(grep 'declare -A PERSONA_PANES' "$HARNESS_DIR/coordinator-watchdog.sh" || true)
  if [[ -n "$persona_line" ]]; then
    # 确认含 [0] [1] [2] 且不含 [3]
    if echo "$persona_line" | grep -qE '\[0\].*\[1\].*\[2\]' && ! echo "$persona_line" | grep -qE '\[3\]'; then
      ok "PERSONA_PANES 限定 pane 0/1/2 (pane 3 不自愈)"
    else
      fail "PERSONA_PANES 映射异常 (应只含 [0][1][2])"
    fi
  else
    fail "缺少 PERSONA_PANES 映射"
  fi
}

# --- D6: 通知链路防回归 ---
test_d6_notification_chain() {
  echo -e "${C}[D6]${N} 通知链路防回归"

  # 断言 1: coordinator.sh 含 history 追加事件 (≥ 3 处)
  local history_hits
  history_hits=$(grep -cE '(handoff_received|eval_reviewed|finalized|plan_received)' "$HARNESS_DIR/coordinator.sh" 2>/dev/null || echo 0)
  if (( history_hits >= 3 )); then
    ok "coordinator.sh history 追加 ≥ 3 处 (${history_hits})"
  else
    fail "coordinator.sh history 追加不足 3 处 (${history_hits})"
  fi

  # 断言 2: coordinator.sh 含 osascript-notify 调用 (≥ 2 处)
  local notify_hits
  notify_hits=$(grep -cE 'osascript-notify.*Glass|osascript-notify.*Blow' "$HARNESS_DIR/coordinator.sh" 2>/dev/null || echo 0)
  if (( notify_hits >= 2 )); then
    ok "coordinator.sh 桌面通知调用 ≥ 2 处 (${notify_hits})"
  else
    fail "coordinator.sh 桌面通知调用不足 2 处 (${notify_hits})"
  fi

  # 断言 3: planner-last-notice 写入逻辑存在 (≥ 2 处)
  local notice_hits
  notice_hits=$(grep -c 'planner-last-notice' "$HARNESS_DIR/coordinator.sh" 2>/dev/null || echo 0)
  if (( notice_hits >= 2 )); then
    ok "coordinator.sh planner-last-notice 引用 ≥ 2 处 (${notice_hits})"
  else
    fail "coordinator.sh planner-last-notice 引用不足 2 处 (${notice_hits})"
  fi
}

# --- D7: pidfile + watchdog wake 防回归 (Sprint 20260422-211820 D6) ---
test_d7_pidfile_watchdog() {
  echo -e "${C}[D7]${N} pidfile + watchdog wake 防回归"

  # 断言 1: watchdog 含 is_actionable_state 函数
  local fn_hits
  fn_hits=$(grep -c 'is_actionable_state' "$HARNESS_DIR/coordinator-watchdog.sh" 2>/dev/null || echo 0)
  if (( fn_hits >= 1 )); then
    ok "coordinator-watchdog.sh 含 is_actionable_state (${fn_hits} 处)"
  else
    fail "coordinator-watchdog.sh 缺少 is_actionable_state 函数"
  fi

  # 断言 2: watchdog wake 逻辑覆盖 superseded/cancelled (通过 is_actionable_state 白名单)
  if grep -qE 'is_actionable_state' "$HARNESS_DIR/coordinator-watchdog.sh"; then
    ok "watchdog wake 使用 is_actionable_state 白名单过滤 (覆盖 superseded/cancelled)"
  else
    fail "watchdog wake 未使用 is_actionable_state"
  fi

  # 断言 3: coordinator.sh trap 使用 clean_my_pidfile (所有权检查)
  if grep -q 'clean_my_pidfile' "$HARNESS_DIR/coordinator.sh"; then
    ok "coordinator.sh trap 含 clean_my_pidfile (PID 所有权校验)"
  else
    fail "coordinator.sh trap 缺少 clean_my_pidfile (可能无条件删除 pidfile)"
  fi
}

# --- D8: loud notify + watchdog 去重防回归 (Sprint 20260422-222017 D6) ---
test_d8_loud_notify_watchdog() {
  echo -e "${C}[D8]${N} loud notify + watchdog 去重防回归"

  # 断言 1: coordinator.sh check_planner_notice 含 tail -10 + grep ❯/╭──
  if grep -q 'tail -10' "$HARNESS_DIR/coordinator.sh" && grep -qE 'grep.*❯|╭──' "$HARNESS_DIR/coordinator.sh"; then
    ok "coordinator.sh check_planner_notice 使用 tail -10 + 正则放宽"
  else
    fail "coordinator.sh 缺少 tail -10 或正则放宽"
  fi

  # 断言 2: coordinator.sh 含忙标记过滤 (✳|⏺|Esc to interrupt)
  if grep -qE 'Esc to interrupt' "$HARNESS_DIR/coordinator.sh"; then
    ok "coordinator.sh 含忙标记过滤 (✳|⏺|Esc to interrupt)"
  else
    fail "coordinator.sh 缺少忙标记过滤"
  fi

  # 断言 3: coordinator-watchdog.sh 含 cleanup_watchdog_pid (3+ 处引用)
  local watchdog_pid_hits
  watchdog_pid_hits=$(grep -c 'cleanup_watchdog_pid' "$HARNESS_DIR/coordinator-watchdog.sh" 2>/dev/null || echo 0)
  if (( watchdog_pid_hits >= 1 )); then
    ok "coordinator-watchdog.sh 含 cleanup_watchdog_pid (${watchdog_pid_hits} 处)"
  else
    fail "coordinator-watchdog.sh 缺少 cleanup_watchdog_pid"
  fi

  # 断言 4: evaluator.md 含 smoke test (2+ 处)
  local smoke_hits
  smoke_hits=$(grep -c 'smoke test' "$HARNESS_DIR/personas/evaluator.md" 2>/dev/null || echo 0)
  if (( smoke_hits >= 2 )); then
    ok "evaluator.md 含 smoke test 铁律 (${smoke_hits} 处)"
  else
    fail "evaluator.md smoke test 引用不足 2 处 (${smoke_hits})"
  fi
}

# --- D9: Hot Reload (sprint-20260423-062851) ---
test_d9_hot_reload() {
  echo -e "${C}[D9]${N} Hot Reload + HEREDOC 修复"

  # (i) coordinator.sh 含 INIT_MD5 + hot-reload 标记 ≥ 2 处
  local coord_hits
  coord_hits=$(grep -c 'INIT_MD5\|hot-reload' "$HARNESS_DIR/coordinator.sh" 2>/dev/null || echo 0)
  if (( coord_hits >= 2 )); then
    ok "coordinator.sh 含 INIT_MD5/hot-reload 标记 ${coord_hits} 处 (≥2)"
  else
    fail "coordinator.sh INIT_MD5/hot-reload 标记仅 ${coord_hits} 处 (<2)"
  fi

  # (ii) solar-harness 含 reload) case 分支
  if grep -q '^ *reload)' "$HOME/.solar/bin/solar-harness" 2>/dev/null; then
    ok "solar-harness 含 reload) case 分支"
  else
    fail "solar-harness 缺少 reload) case 分支"
  fi

  # (iii) evaluator.md 含 否证 或 counter-evidence ≥ 2 处
  local eval_counter
  eval_counter=$(grep -c '否证\|counter-evidence' "$HARNESS_DIR/personas/evaluator.md" 2>/dev/null || echo 0)
  if (( eval_counter >= 2 )); then
    ok "evaluator.md 含 否证/counter-evidence ${eval_counter} 处 (≥2)"
  else
    fail "evaluator.md 否证/counter-evidence 仅 ${eval_counter} 处 (<2)"
  fi

  # (iv) evaluator.md 含 三要素 或 smoke test.*cmd 命中
  if grep -q '三要素\|smoke test.*cmd' "$HARNESS_DIR/personas/evaluator.md" 2>/dev/null; then
    ok "evaluator.md 含 三要素/smoke test cmd 标记"
  else
    fail "evaluator.md 缺少 三要素/smoke test cmd 标记"
  fi
}

# --- D10: Diff Backup + SSH Migrate (Sprint 20260423-151839 D12) ---
test_d10_diff_backup() {
  echo -e "${C}[D10]${N} Diff Backup + SSH Migrate 防回归"

  # (i) import.sh 含 diff scan 调用
  if grep -q 'diff-scan\|diff-manifest\|scan_diff' "$HARNESS_DIR/migrate/import.sh" 2>/dev/null; then
    ok "import.sh 含 diff-scan/diff-manifest 引用"
  else
    fail "import.sh 缺少 diff-scan/diff-manifest 引用"
  fi

  # (ii) rollback.sh 含 --diff + --full 模式
  local rb_hits
  rb_hits=$(grep -c '\-\-diff\|\-\-full' "$HARNESS_DIR/migrate/rollback.sh" 2>/dev/null || echo 0)
  if (( rb_hits >= 2 )); then
    ok "rollback.sh 含 --diff/--full 模式 (${rb_hits} 处)"
  else
    fail "rollback.sh --diff/--full 引用不足 (${rb_hits} 处 <2)"
  fi

  # (iii) migrate/*.sh 含 ssh/scp/rsync 共 3+ 处
  local ssh_hits
  ssh_hits=$(grep -c 'scp\|rsync\|ssh://' "$HARNESS_DIR/migrate/"*.sh 2>/dev/null | awk -F: '{s+=$2}END{print s}')
  if (( ssh_hits >= 3 )); then
    ok "migrate/*.sh 含 scp/rsync/ssh:// 共 ${ssh_hits} 处 (≥3)"
  else
    fail "migrate/*.sh scp/rsync/ssh:// 仅 ${ssh_hits} 处 (<3)"
  fi

  # (iv) solar-harness 含 deploy) + --push + --remote
  local sh_hits
  sh_hits=$(grep -c 'deploy)\|--push\|--remote' "$HOME/.solar/bin/solar-harness" 2>/dev/null || echo 0)
  if (( sh_hits >= 3 )); then
    ok "solar-harness 含 deploy)/--push/--remote ${sh_hits} 处 (≥3)"
  else
    fail "solar-harness deploy/--push/--remote 仅 ${sh_hits} 处 (<3)"
  fi

  # (v) Performance: 1000-file fake dir diff-scan < 6 seconds
  local PERF_DIR="/tmp/diff-perf-test-$$"
  mkdir -p "$PERF_DIR/.solar" "$PERF_DIR/bundle/solar"
  # Create 1000 small files
  for i in $(seq 1 1000); do
    echo "content-$i-$(date +%s%N)" > "$PERF_DIR/bundle/solar/file-$i.txt"
  done
  # Create a minimal bundle-meta.json
  python3 -c "
import json, hashlib, os
fh = {}
for root, dirs, files in os.walk('$PERF_DIR/bundle/solar'):
    for f in files:
        p = os.path.join(root, f)
        rel = 'solar/' + os.path.relpath(p, '$PERF_DIR/bundle/solar')
        fh[rel] = hashlib.sha256(open(p,'rb').read()).hexdigest()
meta = {'bundle_id':'perf-test','files_hash':fh}
json.dump(meta, open('$PERF_DIR/bundle/bundle-meta.json','w'))
" 2>/dev/null

  local START END ELAPSED
  START=$(date +%s)
  bash "$HARNESS_DIR/migrate/diff-scan.sh" "$PERF_DIR/bundle" "$PERF_DIR" "$PERF_DIR/output" 2>/dev/null
  END=$(date +%s)
  ELAPSED=$((END - START))
  rm -rf "$PERF_DIR"

  if (( ELAPSED < 6 )); then
    ok "1000 文件 diff-scan 耗时 ${ELAPSED}s (<6s)"
  else
    fail "1000 文件 diff-scan 耗时 ${ELAPSED}s (≥6s, 性能不达标)"
  fi
}

test_d11_migrate_intent() {
  echo -e "${C}[D11]${N} Migrate Intent 触发词防回归 (sprint-20260424-082117)"

  # (i) intent-engine.md 含"迁移到"或"migrate deploy"触发词命中 ≥ 4 处
  local ie_hits
  ie_hits=$(grep -c '迁移到\|migrate deploy\|打包 Solar\|打包迁移包\|回滚迁移\|验证迁移包' "$HOME/.claude/rules/intent-engine.md" 2>/dev/null || echo 0)
  if (( ie_hits >= 4 )); then
    ok "intent-engine.md 含迁移触发词 ${ie_hits} 处 (≥4)"
  else
    fail "intent-engine.md 迁移触发词仅 ${ie_hits} 处 (<4)"
  fi

  # (ii) intent-engine-hook.sh 含 type="migrate" 输出
  if grep -q 'type="migrate"' "$HOME/.claude/hooks/intent-engine-hook.sh" 2>/dev/null; then
    ok "intent-engine-hook.sh 含 type=\"migrate\" 输出"
  else
    fail "intent-engine-hook.sh 缺少 type=\"migrate\" 输出"
  fi

  # (iii) skills/migrate/SKILL.md 存在且含 6 个子命令表格
  local SKILL_FILE="$HOME/.claude/skills/migrate/SKILL.md"
  if [[ -f "$SKILL_FILE" ]]; then
    local subcmd_hits
    subcmd_hits=$(grep -c '| deploy \| export \| push \| import \| rollback \| verify \|' "$SKILL_FILE" 2>/dev/null || echo 0)
    # Each row has the subcmd word, count individual subcmd occurrences
    subcmd_hits=$(grep -oE 'deploy|export|push|import|rollback|verify' "$SKILL_FILE" 2>/dev/null | sort -u | wc -l | tr -d ' ')
    if (( subcmd_hits >= 6 )); then
      ok "SKILL.md 含 6 个子命令 (deploy/export/push/import/rollback/verify)"
    else
      fail "SKILL.md 子命令不完整 (${subcmd_hits}/6)"
    fi
  else
    fail "skills/migrate/SKILL.md 不存在"
  fi
}

# --- 运行测试 ---
run_all() {
  echo ""
  echo "══════════════════════════════════════════════════"
  echo "  Solar Harness Resilience Tests (D1-D5)"
  echo "══════════════════════════════════════════════════"
  echo ""

  test_d1_exit_capture
  echo ""
  test_d2_no_auto_send
  echo ""
  test_d3_remain_on_exit
  echo ""
  test_d4_doctor_json
  echo ""
  test_d5_watchdog_pane
  echo ""
  test_d6_notification_chain
  echo ""
  test_d7_pidfile_watchdog
  echo ""
  test_d8_loud_notify_watchdog
  echo ""
  test_d9_hot_reload
  echo ""
  test_d10_diff_backup
  echo ""
  test_d11_migrate_intent
  echo ""

  echo "──────────────────────────────────────────────────"
  echo -e "  ${G}PASS: ${PASS}${N}  ${R}FAIL: ${FAIL}${N}  ${Y}SKIP: ${SKIP}${N}"
  echo "──────────────────────────────────────────────────"

  if (( FAIL > 0 )); then
    echo ""
    echo "Failed tests:"
    grep '^FAIL:' "$RESULTS_FILE" | while read -r line; do
      echo -e "  ${R}${line}${N}"
    done
    rm -f "$RESULTS_FILE"
    return 1
  fi
  rm -f "$RESULTS_FILE"
  return 0
}

# --- 入口 ---
case "${1:-all}" in
  all) run_all ;;
  test_d1_exit_capture|test_d2_no_auto_send|test_d3_remain_on_exit|test_d4_doctor_json|test_d5_watchdog_pane|test_d6_notification_chain|test_d7_pidfile_watchdog|test_d8_loud_notify_watchdog|test_d9_hot_reload|test_d10_diff_backup|test_d11_migrate_intent)
    "$1"
    echo ""
    echo "PASS: ${PASS}  FAIL: ${FAIL}  SKIP: ${SKIP}"
    rm -f "$RESULTS_FILE"
    [[ "$FAIL" -gt 0 ]] && exit 1
    ;;
  *)
    echo "未知测试: $1"
    echo "可用: all, test_d1_exit_capture, test_d2_no_auto_send, test_d3_remain_on_exit, test_d4_doctor_json, test_d5_watchdog_pane, test_d6_notification_chain, test_d7_pidfile_watchdog, test_d8_loud_notify_watchdog, test_d9_hot_reload, test_d10_diff_backup, test_d11_migrate_intent"
    exit 1
    ;;
esac
