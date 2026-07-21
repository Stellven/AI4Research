#!/bin/bash
# D5: 端到端验证 chain-watcher 通过 tmux send-keys 通知 pane 0
# sprint-20260503-150911
#
# 流程:
#   (a) 备份 pane 0 capture (确认初始状态)
#   (b) 写 disposable from-codex/review-test-pane0-$$.md
#   (c) 跑 chain-watcher 扫描函数一轮 (不重启 daemon)
#   (d) tmux capture-pane 验证含 [CODEX-NOTIFY] + disposable 文件名
#   (e) 清理 disposable + .processed + throttle 残留
#
# 注意: 测试会真往 pane 0 (planner) 发 send-keys, 但内容只是一行文本通知.
# claude TUI 收到后会 queue 处理 — 这正是生产场景, 测试无副作用.
set -e

CODEX_INBOX="$HOME/.solar/codex-bridge/from-codex"
PROCESSED="$CODEX_INBOX/.processed"
PLANNER_INBOX="$HOME/.solar/harness/PLANNER-INBOX.md"
THROTTLE_FILE="$HOME/.solar/harness/.chain-watcher-pane0-throttle"
PANE_TARGET="solar-harness:0.0"

# 前置: tmux session 必须在
if ! tmux has-session -t solar-harness 2>/dev/null; then
  echo "FAIL: tmux session 'solar-harness' not running"
  exit 1
fi

mkdir -p "$CODEX_INBOX" "$PROCESSED"
touch "$PLANNER_INBOX"

# 清 throttle 状态 (避免之前测试残留)
rm -f "$THROTTLE_FILE"

# (a) 备份 pane 0 当前 capture (作 baseline)
PANE_BEFORE=$(tmux capture-pane -t "$PANE_TARGET" -p 2>/dev/null | wc -l | tr -d ' ')

# (b) 写 disposable review
DISPOSABLE="review-test-pane0-$$-$(date +%s).md"
cat > "$CODEX_INBOX/$DISPOSABLE" << 'EOF'
## verdict: TEST_PANE0_NOTIFY (disposable)
This is a test disposable file. Safe to ignore.
EOF
rm -f "$PROCESSED/$DISPOSABLE"

INBOX_BEFORE=$(wc -l < "$PLANNER_INBOX" | tr -d ' ')

# (c) 跑 chain-watcher 扫描 — source 整个文件 (但跳过 main while loop)
# 提取函数定义到子 shell, 然后调用 ingest_codex_all_files
bash -c '
  set +e
  CODEX_INBOX="$HOME/.solar/codex-bridge/from-codex"
  CODEX_PROCESSED="$CODEX_INBOX/.processed"
  PLANNER_INBOX="$HOME/.solar/harness/PLANNER-INBOX.md"
  PANE0_TARGET="solar-harness:0.0"
  PANE0_THROTTLE_FILE="$HOME/.solar/harness/.chain-watcher-pane0-throttle"
  PANE0_THROTTLE_WINDOW=60
  mkdir -p "$CODEX_PROCESSED"

  # 提取并 eval 三个函数 (sed 范围 — 找 function name() 到下一个独立 } 行)
  '"$(sed -n '/^notify_planner_codex_file()/,/^}$/p' "$HOME/.solar/harness/chain-watcher.sh")"'
  '"$(sed -n '/^notify_pane0_planner()/,/^}$/p' "$HOME/.solar/harness/chain-watcher.sh")"'
  '"$(sed -n '/^ingest_single_contract()/,/^}$/p' "$HOME/.solar/harness/chain-watcher.sh")"'
  '"$(sed -n '/^ingest_codex_all_files()/,/^}$/p' "$HOME/.solar/harness/chain-watcher.sh")"'

  ingest_codex_all_files
'

# 给 tmux 一点时间 ingest send-keys 内容到 pane buffer
sleep 1

# (d) 验证 — capture pane 0 当前内容, 找 CODEX-NOTIFY + disposable basename
PANE_NOW=$(tmux capture-pane -t "$PANE_TARGET" -p 2>/dev/null)

PASS=1
if echo "$PANE_NOW" | grep -q "CODEX-NOTIFY"; then
  echo "OK: pane 0 contains CODEX-NOTIFY marker"
else
  echo "FAIL: pane 0 missing CODEX-NOTIFY marker (after_lines=$(echo "$PANE_NOW" | wc -l), before=$PANE_BEFORE)"
  PASS=0
fi

if echo "$PANE_NOW" | grep -q "$DISPOSABLE"; then
  echo "OK: pane 0 contains disposable filename $DISPOSABLE"
else
  echo "FAIL: pane 0 missing disposable filename $DISPOSABLE"
  PASS=0
fi

# 同时验证 PLANNER-INBOX 也有这条 (D4 旧功能不破坏)
INBOX_AFTER=$(wc -l < "$PLANNER_INBOX" | tr -d ' ')
if grep -q "\[CODEX-REVIEW\].*$DISPOSABLE" "$PLANNER_INBOX"; then
  echo "OK: PLANNER-INBOX has CODEX-REVIEW line for $DISPOSABLE (lines $INBOX_BEFORE -> $INBOX_AFTER)"
else
  echo "FAIL: PLANNER-INBOX missing CODEX-REVIEW for $DISPOSABLE"
  PASS=0
fi

# (e) 清理
rm -f "$PROCESSED/$DISPOSABLE" "$THROTTLE_FILE"

if [ "$PASS" = "1" ]; then
  echo "PASS"
  exit 0
else
  echo "FAIL"
  exit 1
fi
