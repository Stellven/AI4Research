#!/bin/bash
# Hook 通用日志模块
# 用法: source ~/.claude/hooks/hook-logger.sh
# 然后调用: hook_log <event_type> <hook_name> <status> [duration_ms] [detail]

HOOK_TELEMETRY_LOG="$HOME/.solar/logs/hook-telemetry.jsonl"
HOOK_TELEMETRY_DIR="$HOME/.solar/logs"

# 确保日志目录存在
mkdir -p "$HOOK_TELEMETRY_DIR"

# 记录 hook 执行
# $1: event_type (UserPromptSubmit/SessionStart/etc)
# $2: hook_name (文件名不含路径)
# $3: status (ok/error/skip/block)
# $4: duration_ms (可选, 执行耗时)
# $5: detail (可选, 额外信息)
hook_log() {
    local event_type="$1"
    local hook_name="$2"
    local _hook_status="${3:-ok}"
    local duration="${4:-0}"
    local detail="${5:-}"
    local ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    printf '{"ts":"%s","event":"%s","hook":"%s","status":"%s","duration_ms":%s,"detail":"%s"}\n' \
        "$ts" "$event_type" "$hook_name" "$_hook_status" "$duration" "$detail" >> "$HOOK_TELEMETRY_LOG"
}

# 获取当前毫秒时间戳 (用于计算执行时间)
hook_time_ms() {
    python3 -c 'import time; print(int(time.time() * 1000))'
}
