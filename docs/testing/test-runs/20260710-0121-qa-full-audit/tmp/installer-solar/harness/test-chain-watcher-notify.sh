#!/bin/bash
# D6 test: 端到端验证 review-* 文件通知到 PLANNER-INBOX
# sprint-20260503-111139
set -e

CODEX_INBOX="$HOME/.solar/codex-bridge/from-codex"
PLANNER_INBOX="$HOME/.solar/harness/PLANNER-INBOX.md"
PROCESSED="$CODEX_INBOX/.processed"
SPRINTS_DIR="$HOME/.solar/harness/sprints"

# 确保 PLANNER_INBOX 存在
touch "$PLANNER_INBOX"

# 记录前置状态
INBOX_BEFORE=$(wc -l < "$PLANNER_INBOX" | tr -d ' ')

# 创建 disposable review 文件
DISPOSABLE="review-test-$$-$(date +%s).md"
cat > "$CODEX_INBOX/$DISPOSABLE" << 'EOF'
## verdict: TEST_NOTIFY
This is a disposable test file for chain-watcher notification.
EOF

# 确保 .processed 里没有同名文件 (dedup 跳过)
rm -f "$PROCESSED/$DISPOSABLE"

# 加载函数并执行一轮扫描
source <(sed -n '/^CODEX_INBOX=/,/^ingest_codex_all_files()/p' "$HOME/.solar/harness/chain-watcher.sh" | head -n -1)
# 直接用 bash 运行扫描函数 (隔离方式)
bash -c '
  CODEX_INBOX="$HOME/.solar/codex-bridge/from-codex"
  CODEX_PROCESSED="$CODEX_INBOX/.processed"
  PLANNER_INBOX="$HOME/.solar/harness/PLANNER-INBOX.md"
  SPRINTS_DIR="$HOME/.solar/harness/sprints"
  mkdir -p "$CODEX_PROCESSED"
  '"$(sed -n '/^notify_planner_codex_file()/,/^}/p' "$HOME/.solar/harness/chain-watcher.sh")"'
  '"$(sed -n '/^ingest_codex_all_files()/,/^}/p' "$HOME/.solar/harness/chain-watcher.sh")"'
  ingest_codex_all_files
'

# 验证 PLANNER_INBOX 多了含 CODEX-REVIEW 的行
INBOX_AFTER=$(wc -l < "$PLANNER_INBOX" | tr -d ' ')
NEW_LINES=$(( INBOX_AFTER - INBOX_BEFORE ))

if grep -q "\[CODEX-REVIEW\].*$DISPOSABLE" "$PLANNER_INBOX"; then
  echo "OK: PLANNER_INBOX has CODEX-REVIEW line for $DISPOSABLE (+${NEW_LINES} lines)"
else
  echo "FAIL: PLANNER_INBOX missing CODEX-REVIEW for $DISPOSABLE"
  exit 1
fi

# 验证 disposable 被移到 .processed/
if [ -f "$PROCESSED/$DISPOSABLE" ]; then
  echo "OK: $DISPOSABLE moved to .processed/"
else
  echo "FAIL: $DISPOSABLE not in .processed/"
  exit 1
fi

# 清理
rm -f "$PROCESSED/$DISPOSABLE"

echo "PASS"
