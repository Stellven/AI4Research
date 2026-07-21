#!/bin/bash
# SMA Session End Consolidate Hook
# Hook 类型: SessionEnd
#
# 功能:
# 1. 记录 session 结束事件到 session-state.jsonl
# 2. 后台调用 lifecycle-manager cleanup --force
# 3. 后台调用 lifecycle-manager status 生成报告
# 4. 所有操作非阻塞，不延迟 Claude Code 关闭

set -euo pipefail

# 配置
SESSION_LOG="$HOME/.solar/session-state.jsonl"
LIFECYCLE_MANAGER="$HOME/.claude/core/solar-farm/lifecycle-manager.ts"
LIFECYCLE_REPORT="$HOME/.solar/lifecycle-report.log"

# Step 1: 消耗 stdin
cat > /dev/null

# Step 2: 记录 session 结束事件
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SESSION_ID="${CLAUDE_PROJECT_ID:-unknown}"
echo "{\"ts\":\"$TS\",\"event\":\"session_end\",\"session_id\":\"$SESSION_ID\",\"source\":\"sma-hook\"}" >> "$SESSION_LOG"

# Step 3: 后台执行 lifecycle cleanup + report (完全不阻塞)
(
    # 等待 2 秒让 Claude Code 完成关闭流程
    sleep 2

    # 确保目录存在
    mkdir -p "$HOME/.solar"

    # 追加分隔线
    echo "" >> "$LIFECYCLE_REPORT"
    echo "=== Session End Report: $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LIFECYCLE_REPORT"

    # 执行 cleanup --force
    if [ -f "$LIFECYCLE_MANAGER" ] && [ -f "$HOME/.solar/solar.db" ]; then
        bun "$LIFECYCLE_MANAGER" cleanup --force >> "$LIFECYCLE_REPORT" 2>&1 || true
        echo "" >> "$LIFECYCLE_REPORT"

        # 生成状态摘要
        bun "$LIFECYCLE_MANAGER" status >> "$LIFECYCLE_REPORT" 2>&1 || true
    else
        echo "lifecycle-manager or solar.db not found, skipping" >> "$LIFECYCLE_REPORT" 2>&1
    fi
) &

# 立即退出，不等待后台进程
exit 0
