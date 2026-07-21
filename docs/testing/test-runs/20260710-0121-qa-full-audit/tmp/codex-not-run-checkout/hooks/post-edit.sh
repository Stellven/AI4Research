#!/bin/bash
# Post-edit hook: 自动格式化代码

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

if [[ -z "$FILE_PATH" ]] || [[ ! -f "$FILE_PATH" ]]; then
    exit 0
fi

# 根据文件类型格式化
case "$FILE_PATH" in
    *.js|*.ts|*.jsx|*.tsx|*.json)
        if command -v npx &> /dev/null; then
            npx prettier --write "$FILE_PATH" 2>/dev/null
        fi
        ;;
    *.py)
        if command -v black &> /dev/null; then
            black -q "$FILE_PATH" 2>/dev/null
        fi
        ;;
    *.go)
        if command -v gofmt &> /dev/null; then
            gofmt -w "$FILE_PATH" 2>/dev/null
        fi
        ;;
    *.cpp|*.h|*.hpp|*.c)
        if command -v clang-format &> /dev/null; then
            clang-format -i "$FILE_PATH" 2>/dev/null
        fi
        ;;
    *.rs)
        if command -v rustfmt &> /dev/null; then
            rustfmt "$FILE_PATH" 2>/dev/null
        fi
        ;;
esac

exit 0
