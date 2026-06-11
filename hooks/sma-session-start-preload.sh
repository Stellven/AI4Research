#!/bin/bash
# SMA Session Start Preload Hook
# Hook 类型: SessionStart
#
# 功能:
# 1. 检查 solar.db 完整性
# 2. 读取 lifecycle-report.log 最后 10 行
# 3. 输出关键数据指标到 stdout (注入对话)
# 4. 总输出 < 500 字符, 执行时间 < 3 秒

set -euo pipefail

# 配置
DB_PATH="$HOME/.solar/db/solar.db"
LIFECYCLE_REPORT="$HOME/.solar/lifecycle-report.log"

# Step 1: 消耗 stdin
cat > /dev/null

# Step 2: 检查数据库是否存在
if [ ! -f "$DB_PATH" ]; then
    echo "<sma-preload>"
    echo "WARNING: solar.db not found at $DB_PATH"
    echo "</sma-preload>"
    exit 0
fi

# Step 3: 数据库完整性检查
INTEGRITY=$(sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>/dev/null | head -1)

if [ "$INTEGRITY" != "ok" ]; then
    echo "<sma-preload>"
    echo "WARNING: solar.db integrity check failed: $INTEGRITY"
    echo "</sma-preload>"
    exit 0
fi

# Step 4: 收集关键指标
DB_SIZE_KB=$(du -k "$DB_PATH" 2>/dev/null | cut -f1)
DB_SIZE_MB=$(echo "scale=1; $DB_SIZE_KB / 1024" | bc 2>/dev/null || echo "$DB_SIZE_KB")
if [ "$DB_SIZE_KB" -ge 1024 ]; then
    DB_SIZE_STR="${DB_SIZE_MB} MB"
else
    DB_SIZE_STR="${DB_SIZE_KB} KB"
fi

SESSION_LOG_ROWS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM session_log;" 2>/dev/null || echo "0")
FAVORITES_ROWS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sys_favorites;" 2>/dev/null || echo "0")
CORTEX_ROWS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM cortex_sources;" 2>/dev/null || echo "0")

# 获取上次清理时间 (从 lifecycle-report.log 最后一条)
LAST_CLEANUP="N/A"
if [ -f "$LIFECYCLE_REPORT" ]; then
    LAST_CLEANUP=$(grep -o 'Session End Report: [0-9-]* [0-9:]*' "$LIFECYCLE_REPORT" 2>/dev/null | tail -1 | sed 's/Session End Report: //' || echo "N/A")
fi

# Step 5: 输出 (控制在 500 字符以内)
cat << SMAEOF
<sma-preload>
Solar DB: ${DB_SIZE_STR} | session_log: ${SESSION_LOG_ROWS} | favorites: ${FAVORITES_ROWS} | cortex: ${CORTEX_ROWS} | last_cleanup: ${LAST_CLEANUP}
</sma-preload>
SMAEOF

exit 0
