#!/bin/bash
# Context Monitor v2.0 - 主动式上下文监控
#
# 功能：
# 1. 监控上下文长度
# 2. 超过阈值时自动调用摘要器
# 3. 输出提醒给 Solar
#
# 触发时机：PostToolUse (每3次工具调用检查一次)

set -e

STATE_FILE="$HOME/.solar/STATE.md"
SUMMARIZER="$HOME/.claude/core/auto-summarizer.ts"
COUNTER_FILE="/tmp/solar_tool_call_counter"
SUMMARY_MARKER="/tmp/solar_last_auto_summary"
[[ -f "$HOME/.solar/harness/lib/portable.sh" ]] && . "$HOME/.solar/harness/lib/portable.sh"
if ! type solar_file_mtime >/dev/null 2>&1; then
    solar_file_mtime() {
        stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0
    }
fi

# 阈值配置
THRESHOLD_PERCENT=80          # 80% 触发摘要
MIN_INTERVAL_MINUTES=10       # 最少间隔 10 分钟

# 初始化计数器
if [[ ! -f "$COUNTER_FILE" ]]; then
    echo "0" > "$COUNTER_FILE"
fi

# 递增计数器
COUNTER=$(cat "$COUNTER_FILE" 2>/dev/null || echo "0")
COUNTER=$((COUNTER + 1))

# 每3次工具调用检查一次
if [[ $((COUNTER % 3)) -ne 0 ]]; then
    echo "$COUNTER" > "$COUNTER_FILE"
    exit 0
fi

# 重置计数器（触发检查时）
echo "0" > "$COUNTER_FILE"

# ─────────────────────────────────────────────────────────────────
# 估算上下文使用率
# ─────────────────────────────────────────────────────────────────

# Derive the current project's transcript dir from the cwd (Claude Code encodes
# the project path as ~/.claude/projects/<cwd with '/' -> '-'>). Portable; if it
# does not exist the readiness check below exits cleanly.
PROJECT_DIR="$HOME/.claude/projects/$(printf '%s' "$PWD" | sed 's#/#-#g')"
CURRENT_SESSION=$(ls -t "$PROJECT_DIR"/*.jsonl 2>/dev/null | head -1)

if [[ -z "$CURRENT_SESSION" ]]; then
    exit 0
fi

# 统计总字符数（粗略估算）
TOTAL_CHARS=$(wc -c < "$CURRENT_SESSION" 2>/dev/null || echo "0")

# Claude Opus 4 上下文：200K tokens ≈ 600K 字符（中英文混合）
# 80% 阈值 = 480K 字符
THRESHOLD_CHARS=480000

if [[ $TOTAL_CHARS -lt $THRESHOLD_CHARS ]]; then
    # 低于阈值，静默退出
    exit 0
fi

# 计算使用率
USAGE_PERCENT=$((TOTAL_CHARS * 100 / 600000))

# ─────────────────────────────────────────────────────────────────
# 检查是否最近已经生成过摘要（避免频繁触发）
# ─────────────────────────────────────────────────────────────────

if [[ -f "$SUMMARY_MARKER" ]]; then
    LAST_SUMMARY=$(solar_file_mtime "$SUMMARY_MARKER" 2>/dev/null || echo "0")
    CURRENT_TIME=$(date +%s)
    TIME_DIFF=$((CURRENT_TIME - LAST_SUMMARY))
    MIN_INTERVAL_SECONDS=$((MIN_INTERVAL_MINUTES * 60))

    if [[ $TIME_DIFF -lt $MIN_INTERVAL_SECONDS ]]; then
        # 最近已触发，只输出提醒
        cat << REMINDER

┌─ ⏰ 上下文检查 ────────────────────────────────────┐
│                                                     │
│  当前使用率: ${USAGE_PERCENT}%                               │
│  最近摘要: $((TIME_DIFF / 60)) 分钟前                      │
│                                                     │
│  💡 提醒: 如需手动保存，说 "保存快照" 或执行 /save   │
│                                                     │
└─────────────────────────────────────────────────────┘

REMINDER
        exit 0
    fi
fi

# ─────────────────────────────────────────────────────────────────
# 自动执行摘要
# ─────────────────────────────────────────────────────────────────

cat << WARNING

┌─ 🔄 自动摘要触发 ───────────────────────────────────┐
│                                                     │
│  当前上下文: ${USAGE_PERCENT}% (超过 ${THRESHOLD_PERCENT}% 阈值)          │
│  会话文件: $(basename "$CURRENT_SESSION" | cut -c1-20)...              │
│                                                     │
│  正在调用自动摘要器...                              │
│                                                     │
└─────────────────────────────────────────────────────┘

WARNING

# 执行自动摘要
if [[ -f "$SUMMARIZER" ]]; then
    # 调用摘要器（后台执行，不阻塞）
    (
        bun "$SUMMARIZER" 2>&1 | while read -r line; do
            echo "[AutoSummary] $line"
        done

        # 标记已执行
        touch "$SUMMARY_MARKER"

        echo ""
        echo "✅ 自动摘要完成！STATE.md 已更新。"
        echo ""
    ) &

    # 等待一小段时间让输出显示
    sleep 0.5
else
    # 摘要器不存在，回退到手动提醒
    cat << MANUAL

┌─ ⚠️  自动摘要器未安装 ──────────────────────────────┐
│                                                     │
│  请手动执行 Checkpoint：                            │
│                                                     │
│  1. 更新 STATE.md 五段式：                          │
│     • Mission: 当前目标                             │
│     • Progress: Done / In-Progress / Blocked       │
│     • Decisions: 重要决策                           │
│     • Next Actions: 下一步精确操作                  │
│                                                     │
│  2. git commit -m "checkpoint: [描述]"              │
│                                                     │
└─────────────────────────────────────────────────────┘

MANUAL
fi

exit 0
