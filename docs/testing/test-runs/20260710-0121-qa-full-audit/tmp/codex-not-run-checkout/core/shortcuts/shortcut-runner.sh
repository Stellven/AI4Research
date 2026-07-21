#!/bin/bash
# Solar Shortcut Runner
# 执行 Apple Shortcuts 并返回 JSON 结果

set -e

SHORTCUT_NAME="$1"
INPUT_JSON="$2"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

usage() {
    echo "Usage: shortcut-runner.sh <shortcut_name> [input_json]"
    echo ""
    echo "Examples:"
    echo "  shortcut-runner.sh solar_get_weather"
    echo "  shortcut-runner.sh solar_set_reminder '{\"title\":\"开会\",\"datetime\":\"2026-01-31T15:00:00\"}'"
    exit 1
}

# 检查参数
if [ -z "$SHORTCUT_NAME" ]; then
    usage
fi

# 检查 shortcuts 命令是否可用
if ! command -v shortcuts &> /dev/null; then
    echo '{"success":false,"error":"shortcuts command not found. Requires macOS 12+"}'
    exit 1
fi

# 执行 shortcut
execute_shortcut() {
    local name="$1"
    local input="$2"
    local start_time=$(date +%s%3N)
    local result
    local exit_code

    if [ -n "$input" ]; then
        # 有输入参数
        result=$(echo "$input" | shortcuts run "$name" --input-type "json" 2>&1) || exit_code=$?
    else
        # 无输入参数
        result=$(shortcuts run "$name" 2>&1) || exit_code=$?
    fi

    local end_time=$(date +%s%3N)
    local duration=$((end_time - start_time))

    if [ -z "$exit_code" ] || [ "$exit_code" -eq 0 ]; then
        # 成功
        # 尝试解析为 JSON，如果失败则包装为字符串
        if echo "$result" | jq -e . &>/dev/null; then
            echo "{\"success\":true,\"shortcut\":\"$name\",\"result\":$result,\"duration_ms\":$duration}"
        else
            # 转义结果字符串
            escaped=$(echo "$result" | jq -Rs .)
            echo "{\"success\":true,\"shortcut\":\"$name\",\"result\":$escaped,\"duration_ms\":$duration}"
        fi
    else
        # 失败
        escaped=$(echo "$result" | jq -Rs .)
        echo "{\"success\":false,\"shortcut\":\"$name\",\"error\":$escaped,\"exit_code\":$exit_code,\"duration_ms\":$duration}"
    fi
}

# 列出所有可用的 shortcuts
list_shortcuts() {
    shortcuts list 2>/dev/null | jq -R -s 'split("\n") | map(select(length > 0))'
}

# 检查 shortcut 是否存在
check_shortcut() {
    local name="$1"
    shortcuts list 2>/dev/null | grep -q "^${name}$"
}

# 主逻辑
case "$SHORTCUT_NAME" in
    --list)
        list_shortcuts
        ;;
    --check)
        if check_shortcut "$INPUT_JSON"; then
            echo '{"exists":true}'
        else
            echo '{"exists":false}'
        fi
        ;;
    *)
        execute_shortcut "$SHORTCUT_NAME" "$INPUT_JSON"
        ;;
esac
