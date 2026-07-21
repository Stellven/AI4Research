#!/bin/bash
#
# Solar Farm - 绩效自动刷新 Hook
# 每个会话首次检查是否需要刷新绩效（避免重复检查）
# 如果距离上次刷新超过24小时，自动执行 perf-refresh.ts
#

DB_PATH="$HOME/.solar/solar.db"
REFRESH_SCRIPT="$HOME/.claude/scripts/perf-refresh.ts"
LAST_REFRESH_FILE="$HOME/.solar/.perf_last_refresh"
SESSION_LOCK="$HOME/.solar/.perf_session_$$"
REFRESH_INTERVAL=86400  # 24小时 = 86400秒

# 如果本会话已经检查过，直接退出
if [[ -f "$SESSION_LOCK" ]]; then
    exit 0
fi

# 标记本会话已检查
touch "$SESSION_LOCK"

# 清理旧的会话锁（超过1天的）
find "$HOME/.solar" -name ".perf_session_*" -mtime +1 -delete 2>/dev/null

# 检查数据库是否存在
if [[ ! -f "$DB_PATH" ]]; then
    exit 0
fi

# 获取上次刷新时间
if [[ -f "$LAST_REFRESH_FILE" ]]; then
    last_refresh=$(cat "$LAST_REFRESH_FILE")
else
    last_refresh=0
fi

# 获取当前时间
current_time=$(date +%s)
time_diff=$((current_time - last_refresh))

# 如果超过24小时，执行刷新
if [[ $time_diff -gt $REFRESH_INTERVAL ]]; then
    echo ""
    echo "┌─────────────────────────────────────────────────────────────────┐"
    echo "│  🔄 Solar Farm 绩效自动刷新 (距上次: $((time_diff/3600))小时)                     │"
    echo "├─────────────────────────────────────────────────────────────────┤"

    # 执行刷新
    if [[ -f "$REFRESH_SCRIPT" ]]; then
        cd "$HOME/.claude/scripts"
        output=$(bun perf-refresh.ts 2>&1)
        echo "$output" | head -10 | sed 's/^/│  /'

        # 记录刷新时间
        echo "$current_time" > "$LAST_REFRESH_FILE"

        echo "│                                                                 │"
        echo "│  ✅ 牛马绩效已刷新注入到人格配置                                │"
    else
        echo "│  ⚠️ 刷新脚本不存在                                              │"
    fi

    echo "└─────────────────────────────────────────────────────────────────┘"
    echo ""
fi

exit 0
