#!/bin/bash
# STATE.md 读取追踪器
# PostToolUse Read 时检测是否读了 STATE.md，设置标记
#
# 目的：配合 state-read-enforcer.sh 实现"先读后写"强制机制

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

# 只处理 Read 工具
if [[ "$TOOL_NAME" != "Read" ]]; then
    exit 0
fi

# 获取读取的文件路径
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

# 检查是否是 STATE.md（支持多种路径）
if [[ "$FILE_PATH" == *"STATE.md"* ]] || [[ "$FILE_PATH" == *".solar/STATE.md"* ]]; then
    # 设置标记文件
    SESSION_ID="${CLAUDE_SESSION_ID:-$(date +%Y%m%d%H)}"
    MARKER_DIR="/tmp/solar-state-markers"
    mkdir -p "$MARKER_DIR"

    # 写入标记
    touch "$MARKER_DIR/state-read-$SESSION_ID"

    # 可选：记录读取时间
    date +%s > "$MARKER_DIR/state-read-$SESSION_ID"
fi

exit 0
