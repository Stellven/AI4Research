#!/bin/bash
# D7 test: 验证 contract-*.md 仍然走起 sprint 路径，不写 PLANNER-INBOX
# sprint-20260503-111139
set -e

CODEX_INBOX="$HOME/.solar/codex-bridge/from-codex"
PLANNER_INBOX="$HOME/.solar/harness/PLANNER-INBOX.md"
PROCESSED="$CODEX_INBOX/.processed"
SPRINTS_DIR="$HOME/.solar/harness/sprints"

touch "$PLANNER_INBOX"
INBOX_BEFORE=$(wc -l < "$PLANNER_INBOX" | tr -d ' ')

# 记录 sprint 数量
SPRINTS_BEFORE=$(ls "$SPRINTS_DIR"/sprint-*.status.json 2>/dev/null | wc -l | tr -d ' ')

# 创建 disposable contract 文件 (完整 frontmatter)
DISPOSABLE="contract-test-regression-$$-$(date +%s).md"
cat > "$CODEX_INBOX/$DISPOSABLE" << EOF
---
title: test regression contract
priority: low
topology: standard
estimated_hours: 0.1
---
# Regression Test Contract
This is a disposable test to verify contract ingestion still works.
EOF

rm -f "$PROCESSED/$DISPOSABLE"

# 运行扫描函数
bash -c '
  CODEX_INBOX="$HOME/.solar/codex-bridge/from-codex"
  CODEX_PROCESSED="$CODEX_INBOX/.processed"
  PLANNER_INBOX="$HOME/.solar/harness/PLANNER-INBOX.md"
  SPRINTS_DIR="$HOME/.solar/harness/sprints"
  mkdir -p "$CODEX_PROCESSED"
  '"$(sed -n '/^ingest_single_contract()/,/^}/p' "$HOME/.solar/harness/chain-watcher.sh")"'
  '"$(sed -n '/^notify_planner_codex_file()/,/^}/p' "$HOME/.solar/harness/chain-watcher.sh")"'
  '"$(sed -n '/^ingest_codex_all_files()/,/^}/p' "$HOME/.solar/harness/chain-watcher.sh")"'
  ingest_codex_all_files
'

# 验证 (a) 新 sprint 被创建
SPRINTS_AFTER=$(ls "$SPRINTS_DIR"/sprint-*.status.json 2>/dev/null | wc -l | tr -d ' ')
if [ "$SPRINTS_AFTER" -gt "$SPRINTS_BEFORE" ]; then
  echo "OK: new sprint created (before=$SPRINTS_BEFORE after=$SPRINTS_AFTER)"
else
  echo "FAIL: no new sprint created"
  # 清理
  rm -f "$CODEX_INBOX/$DISPOSABLE"
  exit 1
fi

# 验证 (b) contract 文件移到 .processed/
if [ -f "$PROCESSED/$DISPOSABLE" ]; then
  echo "OK: $DISPOSABLE moved to .processed/"
else
  echo "FAIL: $DISPOSABLE not in .processed/"
  exit 1
fi

# 验证 (c) PLANNER-INBOX 没有新增 CODEX-* 行 (contract 走起 sprint 路径不走通知路径)
INBOX_AFTER=$(wc -l < "$PLANNER_INBOX" | tr -d ' ')
if grep "\[CODEX-" "$PLANNER_INBOX" | tail -1 | grep -q "$DISPOSABLE"; then
  echo "FAIL: PLANNER_INBOX has CODEX-* line for contract file (should not notify)"
  exit 1
else
  echo "OK: PLANNER_INBOX has no CODEX-* line for contract file"
fi

# 清理新创建的 sprint
NEW_SID=$(ls -t "$SPRINTS_DIR"/sprint-*.status.json 2>/dev/null | head -1)
if [ -n "$NEW_SID" ]; then
  SID=$(python3 -c "import json; print(json.load(open('$NEW_SID')).get('id',''))" 2>/dev/null)
  if [ -n "$SID" ]; then
    python3 -c "
import json
d=json.load(open('$NEW_SID'))
d['status']='cancelled'
json.dump(d,open('$NEW_SID','w'),indent=2)
"
    echo "OK: cancelled test sprint $SID"
  fi
fi
rm -f "$PROCESSED/$DISPOSABLE"

echo "PASS"
