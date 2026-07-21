#!/bin/bash
# D6: 限频测试 — 同 type 60s 内只发 1 条 send-keys, 但 INBOX 全收
# sprint-20260503-150911
#
# 流程:
#   (a) 清空 .chain-watcher-pane0-throttle (干净起点)
#   (b) 1 秒内连写 3 个 review-test-throttle-N.md
#   (c) 跑 chain-watcher 扫描函数一轮
#   (d) 验证: PLANNER-INBOX 多 3 行 (INBOX 不限频)
#       pane 0 capture 只有 1 条新 CODEX-NOTIFY (限频生效)
#       chain-watcher 输出含 'pane0-throttle' 跳过 log
#   (e) 清理
set -e

CODEX_INBOX="$HOME/.solar/codex-bridge/from-codex"
PROCESSED="$CODEX_INBOX/.processed"
PLANNER_INBOX="$HOME/.solar/harness/PLANNER-INBOX.md"
THROTTLE_FILE="$HOME/.solar/harness/.chain-watcher-pane0-throttle"
PANE_TARGET="solar-harness:0.0"

if ! tmux has-session -t solar-harness 2>/dev/null; then
  echo "FAIL: tmux session 'solar-harness' not running"
  exit 1
fi

mkdir -p "$CODEX_INBOX" "$PROCESSED"
touch "$PLANNER_INBOX"

# (a) 清 throttle
rm -f "$THROTTLE_FILE"

# (b) 1秒内写 3 个 review (同 type)
STAMP="$$-$(date +%s)"
F1="review-test-throttle-1-${STAMP}.md"
F2="review-test-throttle-2-${STAMP}.md"
F3="review-test-throttle-3-${STAMP}.md"

for f in "$F1" "$F2" "$F3"; do
  echo "## verdict: throttle test $f" > "$CODEX_INBOX/$f"
  rm -f "$PROCESSED/$f"
done

# pane 0 baseline: 在 capture 抓一段, 用于 diff
PANE_BEFORE=$(tmux capture-pane -t "$PANE_TARGET" -p 2>/dev/null)
NOTIFY_BEFORE=$(echo "$PANE_BEFORE" | grep -c "CODEX-NOTIFY" || true)

INBOX_BEFORE=$(wc -l < "$PLANNER_INBOX" | tr -d ' ')

# (c) 跑 chain-watcher 扫描 — 一次性扫所有 3 个文件
SCAN_OUTPUT=$(bash -c '
  set +e
  CODEX_INBOX="$HOME/.solar/codex-bridge/from-codex"
  CODEX_PROCESSED="$CODEX_INBOX/.processed"
  PLANNER_INBOX="$HOME/.solar/harness/PLANNER-INBOX.md"
  PANE0_TARGET="solar-harness:0.0"
  PANE0_THROTTLE_FILE="$HOME/.solar/harness/.chain-watcher-pane0-throttle"
  PANE0_THROTTLE_WINDOW=60
  mkdir -p "$CODEX_PROCESSED"

  '"$(sed -n '/^notify_planner_codex_file()/,/^}$/p' "$HOME/.solar/harness/chain-watcher.sh")"'
  '"$(sed -n '/^notify_pane0_planner()/,/^}$/p' "$HOME/.solar/harness/chain-watcher.sh")"'
  '"$(sed -n '/^ingest_single_contract()/,/^}$/p' "$HOME/.solar/harness/chain-watcher.sh")"'
  '"$(sed -n '/^ingest_codex_all_files()/,/^}$/p' "$HOME/.solar/harness/chain-watcher.sh")"'

  ingest_codex_all_files
' 2>&1)

echo "--- chain-watcher scan output ---"
echo "$SCAN_OUTPUT"
echo "--- end scan output ---"

sleep 1

PANE_AFTER=$(tmux capture-pane -t "$PANE_TARGET" -p 2>/dev/null)
NOTIFY_AFTER=$(echo "$PANE_AFTER" | grep -c "CODEX-NOTIFY" || true)
NOTIFY_DELTA=$(( NOTIFY_AFTER - NOTIFY_BEFORE ))

INBOX_AFTER=$(wc -l < "$PLANNER_INBOX" | tr -d ' ')
INBOX_DELTA=$(( INBOX_AFTER - INBOX_BEFORE ))

PASS=1

# (d.1) PLANNER-INBOX 应增 3 行 (3 个文件全部记录)
if [ "$INBOX_DELTA" -ge 3 ]; then
  echo "OK: PLANNER-INBOX +${INBOX_DELTA} lines (>=3, INBOX 不限频)"
else
  echo "FAIL: PLANNER-INBOX only +${INBOX_DELTA} lines, expected >=3"
  PASS=0
fi

# 3 个文件名都应在 INBOX
INBOX_HITS=0
for f in "$F1" "$F2" "$F3"; do
  if grep -q "$f" "$PLANNER_INBOX"; then
    INBOX_HITS=$(( INBOX_HITS + 1 ))
  fi
done
if [ "$INBOX_HITS" -eq 3 ]; then
  echo "OK: PLANNER-INBOX contains all 3 disposable files"
else
  echo "FAIL: PLANNER-INBOX only has $INBOX_HITS/3 disposable files"
  PASS=0
fi

# (d.2) pane 0 capture 应只多 1 条 CODEX-NOTIFY (其余被 throttle 跳过)
# 注意: pane 0 capture buffer 滚动可能会丢旧行, NOTIFY_DELTA 可能 <= 1 (老行被滚走)
# 关键检查: scan output 应有 2 条 'pane0-throttle' skipped log
if [ "$NOTIFY_DELTA" -ge 1 ] && [ "$NOTIFY_DELTA" -le 1 ]; then
  echo "OK: pane 0 capture has +${NOTIFY_DELTA} CODEX-NOTIFY (限频, 期望 1)"
elif [ "$NOTIFY_DELTA" -gt 1 ]; then
  echo "FAIL: pane 0 capture +${NOTIFY_DELTA} CODEX-NOTIFY (限频失效, 期望 1)"
  PASS=0
else
  # NOTIFY_DELTA == 0 — pane buffer 可能滚走, 用 scan output 兜底
  if echo "$SCAN_OUTPUT" | grep -q "pane 0 notified\|pane 0 busy"; then
    echo "OK: scan output 显示发了 1 条 send-keys (capture 滚走)"
  else
    echo "FAIL: scan output 没显示发任何 send-keys"
    PASS=0
  fi
fi

# (d.3) scan output 必须含 2 条 'pane0-throttle' skipped log
THROTTLE_LOGS=$(echo "$SCAN_OUTPUT" | grep -c "pane0-throttle.*skipped" || true)
if [ "$THROTTLE_LOGS" -ge 2 ]; then
  echo "OK: scan output 显示 ${THROTTLE_LOGS} 条 throttle skipped (>=2, 即 3-1=2 被跳过)"
else
  echo "FAIL: scan output throttle skipped 只有 ${THROTTLE_LOGS}, 期望 >=2"
  PASS=0
fi

# (e) 清理
for f in "$F1" "$F2" "$F3"; do
  rm -f "$PROCESSED/$f"
done
rm -f "$THROTTLE_FILE"

if [ "$PASS" = "1" ]; then
  echo "PASS"
  exit 0
else
  echo "FAIL"
  exit 1
fi
