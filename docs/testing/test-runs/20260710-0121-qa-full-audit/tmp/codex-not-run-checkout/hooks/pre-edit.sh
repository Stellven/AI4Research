#!/bin/bash
# Pre-edit hook: 检查文件是否受保护

# 读取工具输入
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# 受保护文件模式
PROTECTED_PATTERNS=(
    ".env"
    ".env.*"
    "*.pem"
    "*.key"
    "*secret*"
    "*credential*"
    "*password*"
)

# 检查是否匹配保护模式
for pattern in "${PROTECTED_PATTERNS[@]}"; do
    if [[ "$(basename "$FILE_PATH")" == $pattern ]]; then
        echo "错误: 文件 $FILE_PATH 受保护，禁止修改" >&2
        exit 2
    fi
done

exit 0
