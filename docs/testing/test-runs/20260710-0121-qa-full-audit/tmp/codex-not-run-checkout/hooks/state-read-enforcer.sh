#!/bin/bash
# STATE.md 读取强制器
# PreToolUse Write/Edit 时检查是否先读过 STATE.md
# 如果没读过，exit 2 阻断执行
#
# 核心铁律：先读后写，不依赖"记得"

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

# 只处理 Write 和 Edit
if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
    echo '{"continue": true}'
    exit 0
fi

# 检查标记文件
SESSION_ID="${CLAUDE_SESSION_ID:-$(date +%Y%m%d%H)}"
MARKER_FILE="/tmp/solar-state-markers/state-read-$SESSION_ID"

# 允许的豁免路径（不需要先读 STATE.md 的文件）
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
EXEMPT_PATTERNS=(
    "/tmp/"
    "node_modules/"
    ".git/"
    "package-lock.json"
    "bun.lock"
)

for pattern in "${EXEMPT_PATTERNS[@]}"; do
    if [[ "$FILE_PATH" == *"$pattern"* ]]; then
        echo '{"continue": true}'
        exit 0
    fi
done

# 动态规则注入 (Write/Edit 操作)
TOOL_NAME_CHECK=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

# 检查是否已读过 STATE.md
if [[ -f "$MARKER_FILE" ]]; then
    # 已读过，放行 + 规则提醒
    echo '{"continue": true}'
    case "$TOOL_NAME_CHECK" in
        Write|Edit)
            echo "💡 no-mock 规则: 新文件/修改必须真实实现，禁止 TODO/桩/模拟输出"
            ;;
    esac
    exit 0
fi

# 未读过，阻断！
cat >&2 << 'EOF'

╔═══════════════════════════════════════════════════════════════════════════╗
║  ⛔ 阻断：你还没读 STATE.md！                                              ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║  铁律：先读后写                                                           ║
║                                                                           ║
║  请先执行：                                                               ║
║  Read ~/.solar/STATE.md                                             ║
║                                                                           ║
║  读完后再尝试 Write/Edit                                                  ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝

EOF

exit 2
