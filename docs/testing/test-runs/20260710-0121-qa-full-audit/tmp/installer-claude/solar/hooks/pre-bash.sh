#!/bin/bash
# Pre-bash hook: 验证命令安全性

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

if [[ -z "$COMMAND" ]]; then
    exit 0
fi

# 危险命令模式
DANGEROUS_PATTERNS=(
    "rm -rf /"
    "rm -rf /*"
    "rm -rf ~"
    "dd if=/dev/"
    "mkfs"
    "> /dev/sd"
    "chmod -R 777 /"
    "curl.*| *sh"
    "wget.*| *sh"
    ":(){ :|:& };:"
)

# 检查危险命令
for pattern in "${DANGEROUS_PATTERNS[@]}"; do
    if [[ "$COMMAND" == *"$pattern"* ]]; then
        echo "错误: 危险命令被阻止: $pattern" >&2
        exit 2
    fi
done

exit 0
