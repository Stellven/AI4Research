#!/usr/bin/env bash
# solidifier-cron.sh — 每日代码固化维护
# 触发: SessionEnd hook 或手动执行
#
# 功能:
#   1. scan    — 扫描 evolve_executions 找固化候选
#   2. promote — 提升达到阈值的候选
#   3. decay   — 置信度衰减 + 清理过期

set -euo pipefail

SOLIDIFIER="$HOME/.claude/core/solar-farm/skill-solidifier.ts"

if [[ ! -f "$SOLIDIFIER" ]]; then
  echo "[solidifier-cron] skill-solidifier.ts not found, skipping"
  exit 0
fi

echo "[solidifier-cron] Running daily solidification maintenance..."

# Step 1: Scan candidates
echo "[solidifier-cron] Scanning candidates..."
SCAN_OUTPUT=$(bun "$SOLIDIFIER" scan 2>&1 || true)
echo "$SCAN_OUTPUT" | tail -5

# Step 2: Auto-promote (promote-all handles threshold check)
echo "[solidifier-cron] Promoting eligible candidates..."
PROMOTE_OUTPUT=$(bun "$SOLIDIFIER" promote-all 2>&1 || true)
echo "$PROMOTE_OUTPUT" | tail -3

# Step 3: Decay expired entries
echo "[solidifier-cron] Running decay..."
DECAY_OUTPUT=$(bun "$SOLIDIFIER" decay 2>&1 || true)
echo "$DECAY_OUTPUT"

# Summary
echo "[solidifier-cron] Done."
bun "$SOLIDIFIER" stats 2>&1 | tail -8 || true
