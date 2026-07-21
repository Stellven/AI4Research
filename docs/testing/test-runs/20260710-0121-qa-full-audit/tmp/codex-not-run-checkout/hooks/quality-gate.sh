#!/bin/bash
# Quality gate hook: 任务完成时的质量检查

# 检查是否有未提交的变更
if git rev-parse --is-inside-work-tree &>/dev/null; then
    CHANGES=$(git status --porcelain 2>/dev/null)
    if [[ -n "$CHANGES" ]]; then
        echo "提醒: 有未提交的变更" >&2
        echo "$CHANGES" | head -5 >&2
    fi
fi

exit 0
